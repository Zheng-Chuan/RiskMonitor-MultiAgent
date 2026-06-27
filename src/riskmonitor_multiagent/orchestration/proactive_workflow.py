"""
主动多 Agent 协作工作流.

使用具备 BDI + ReAct + 后台监控的主动 Agent.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Optional

from riskmonitor_multiagent.proactive_agents import (
    ModeratorAgent,
    ProactiveAgentResult,
    ProactiveIntentAgent,
    ProactiveOrchestratorAgent,
    ProactiveCriticAgent,
    ProactiveSystemEngineerAgent,
    ProactiveRiskAnalystAgent,
)
from riskmonitor_multiagent.contracts.event import normalize_event, validate_event
from riskmonitor_multiagent.contracts.run_context import (
    new_run_context,
    normalize_run_context,
    validate_run_context,
)
from riskmonitor_multiagent.contracts.task_graph import append_replan_subgraph
from riskmonitor_multiagent.governance.proactive_budget import get_proactive_budget_manager
from riskmonitor_multiagent.memory import get_memory_store, SessionSegmenter
from riskmonitor_multiagent.orchestration.message_bus import get_message_bus
from riskmonitor_multiagent.observability.run_trace import (
    build_run_trace_snapshot,
    get_run_trace_store,
)
from riskmonitor_multiagent.orchestration.task_graph_executor import TaskGraphExecutor
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.utils.ids import new_run_id

from riskmonitor_multiagent.orchestration.workflow_result_builder import (
    build_workflow_result,
    build_blocked_event_result,
    build_invalid_event_result,
    normalize_critic_final_output,
    build_workflow_output,
)
from riskmonitor_multiagent.orchestration.workflow_resume import (
    apply_resume_context,
    apply_approval_decision_to_resume_request,
    merge_resume_memory_into_planning_memory,
    should_replan,
    build_replan_reason,
    should_runtime_replan,
    extract_execution_failure,
    build_runtime_replan_reason,
)
from riskmonitor_multiagent.orchestration.workflow_memory import (
    persist_plan_memory,
    persist_intent_memory,
)
from riskmonitor_multiagent.orchestration.workflow_events import (
    default_candidate_agents_for_event,
    build_task_from_event,
    requires_manual_approval,
)
from riskmonitor_multiagent.scheduling.cron_manager import CronTask
from riskmonitor_multiagent.skills import (
    SkillInjector,
    SkillProposer,
    SkillReviser,
    SkillStore,
    SkillUsageTracker,
)

logger = logging.getLogger(__name__)


class ProactiveMultiAgentWorkflow:
    """
    主动多 Agent 协作工作流.
    
    核心特点:
    1. 每个 Agent 都具备 BDI 模型
    2. 每个 Agent 都使用 ReAct 循环
    3. 每个 Agent 都有后台监控线程
    4. 动态协作,非固定流程
    """
    
    def __init__(self) -> None:
        self._intent_agent = ProactiveIntentAgent()
        self._orchestrator_agent = ProactiveOrchestratorAgent()
        self._critic_agent = ProactiveCriticAgent()
        self._engineer_agent = ProactiveSystemEngineerAgent()
        self._analyst_agent = ProactiveRiskAnalystAgent()
        self._message_bus = get_message_bus()
        self._moderator = ModeratorAgent(message_bus=self._message_bus)
        self._proactive_budget = get_proactive_budget_manager()
        self._run_trace_store = get_run_trace_store()
        self._skill_store = SkillStore()
        self._skill_usage_tracker = SkillUsageTracker(self._skill_store)
        self._session_segmenter = SessionSegmenter()

        self._agents_started = False
    
    async def start_agents(self) -> None:
        """启动所有 Agent 的后台监控."""
        if self._agents_started:
            return
        
        await asyncio.gather(
            self._intent_agent.start_background_monitor(),
            self._orchestrator_agent.start_background_monitor(),
            self._critic_agent.start_background_monitor(),
            self._engineer_agent.start_background_monitor(),
            self._analyst_agent.start_background_monitor(),
        )
        
        self._agents_started = True
        logger.info("All proactive agents started with background monitoring")
    
    async def stop_agents(self) -> None:
        """停止所有 Agent 的后台监控."""
        if not self._agents_started:
            return
        
        await asyncio.gather(
            self._intent_agent.stop_background_monitor(),
            self._orchestrator_agent.stop_background_monitor(),
            self._critic_agent.stop_background_monitor(),
            self._engineer_agent.stop_background_monitor(),
            self._analyst_agent.stop_background_monitor(),
        )
        
        self._agents_started = False
        logger.info("All proactive agents stopped")
    
    async def run(self, task: dict[str, Any]) -> dict[str, Any]:
        """
        运行主动多 Agent 协作.
        
        流程:
        1. Intent Agent 识别意图(使用 ReAct)
        2. Orchestrator Agent 制定计划(使用 ReAct)
        3. Critic Agent 评审计划(使用 ReAct)
        4. Engineer 和 Analyst 并行执行(使用 ReAct)
        5. 汇总结果
        
        Args:
            task: 任务定义
            
        Returns:
            协作结果
        """
        run_context = self._resolve_run_context(task=task)
        task_with_context = dict(task)
        task_with_context["run_context"] = run_context
        result = await self._run_internal(task=task_with_context, run_context=run_context)
        self._record_run_trace_snapshot(
            result=result,
            source_event=None,
        )
        return result

    async def start_from_event(
        self,
        *,
        event: dict[str, Any],
        candidate_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """从系统事件启动统一工作流."""
        normalized_event = normalize_event(event)
        accepted_event, event_error = await self._accept_system_event(normalized_event)
        if event_error is not None:
            run_context = new_run_context(
                entry_type="system_event",
                task_id=str((normalized_event.get("payload") or {}).get("task_id") or normalized_event.get("event_id") or "") or None,
                trigger_event_id=str(normalized_event.get("event_id") or ""),
                trigger_reason="invalid_event",
                trigger_evidence={"validation_errors": [event_error]},
                metadata={
                    "source_agent": normalized_event.get("source_agent"),
                    "event_type": normalized_event.get("event_type"),
                },
            )
            failed = build_invalid_event_result(
                event=normalized_event,
                run_context=run_context,
                reason=event_error,
            )
            self._record_run_trace_snapshot(result=failed, source_event=normalized_event)
            return failed
        normalized_event = accepted_event
        task_payload = normalized_event.get("payload") if isinstance(normalized_event.get("payload"), dict) else {}
        provisional_task_id = str(task_payload.get("task_id") or normalized_event.get("event_id") or "")
        run_context = new_run_context(
            entry_type="system_event",
            task_id=provisional_task_id or None,
            trigger_event_id=str(normalized_event.get("event_id") or ""),
            trigger_reason="pending_moderation",
            trigger_evidence={
                "event_type": normalized_event.get("event_type"),
                "source_agent": normalized_event.get("source_agent"),
                "payload": task_payload,
            },
            metadata={
                "source_agent": normalized_event.get("source_agent"),
                "event_type": normalized_event.get("event_type"),
            },
        )
        budget_decision = self._proactive_budget.evaluate_and_reserve(
            run_id=str(run_context.get("run_id") or ""),
            event=normalized_event,
        )
        if not budget_decision.allowed:
            blocked = build_blocked_event_result(
                event=normalized_event,
                run_context=run_context,
                reason=budget_decision.reason,
                budget_evidence=budget_decision.evidence,
            )
            self._record_run_trace_snapshot(
                result=blocked,
                source_event=normalized_event,
            )
            self._proactive_budget.release_run(
                run_id=str(run_context.get("run_id") or ""),
                status="blocked",
            )
            return blocked

        decision = await self._moderator.moderate(
            event=normalized_event,
            candidate_agents=candidate_agents or default_candidate_agents_for_event(normalized_event),
            context={
                "run_id": run_context.get("run_id"),
                "entry_type": run_context.get("entry_type"),
                "task": {"task_id": provisional_task_id or normalized_event.get("event_id")},
            },
        )
        task = build_task_from_event(
            event=normalized_event,
            route_decision=decision,
        )
        run_context["task_id"] = str(task.get("task_id") or "")
        run_context["trigger_reason"] = str(decision.get("reason") or "")
        run_context["route_decision"] = dict(decision)
        task["run_context"] = run_context
        task["event_context"] = {
            "event": normalized_event,
            "route_decision": decision,
        }
        result = await self._run_internal(
            task=task,
            run_context=run_context,
            route_decision=decision,
            source_event=normalized_event,
        )
        self._record_run_trace_snapshot(
            result=result,
            source_event=normalized_event,
        )
        self._proactive_budget.release_run(
            run_id=str(run_context.get("run_id") or ""),
            status=str(result.get("status") or "failed"),
        )
        return result

    async def run_cron_triggered_workflow(self, cron_task: CronTask) -> dict[str, Any]:
        """Cron 触发的任务统一走 system_event → ModeratorAgent → TaskGraphExecutor 主链.

        不允许调度任务绕过治理体系.

        Args:
            cron_task: Cron 定时任务定义.

        Returns:
            工作流执行结果.
        """
        # 1. 构建 system_event
        event = {
            "event_id": f"cron_{cron_task.task_id}_{int(time.time() * 1000)}",
            "event_type": "cron_triggered",
            "source_agent": "cron_manager",
            "payload": {
                **cron_task.task_template,
                "task_id": cron_task.task_id,
            },
            "priority": str((cron_task.trigger_config or {}).get("priority", "normal")),
        }
        trigger_reason = f"Cron task: {cron_task.name}"
        event["payload"]["trigger_reason"] = trigger_reason

        logger.info(
            "[ProactiveWorkflow] Cron triggered: task_id=%s name=%s expr=%s",
            cron_task.task_id,
            cron_task.name,
            cron_task.cron_expression,
        )

        # 2. 调用现有的 start_from_event (system_event 入口)
        try:
            result = await self.start_from_event(event=event)
        except Exception as exc:
            logger.exception(
                "[ProactiveWorkflow] Cron workflow failed: task_id=%s err=%s",
                cron_task.task_id,
                exc,
            )
            result = {
                "status": "failed",
                "entry_type": "system_event",
                "task_id": cron_task.task_id,
                "errors": [str(exc)],
                "cron_task_id": cron_task.task_id,
                "cron_task_name": cron_task.name,
            }

        # 3. 补充 cron 上下文信息
        if isinstance(result, dict):
            result.setdefault("cron_task_id", cron_task.task_id)
            result.setdefault("cron_task_name", cron_task.name)
            result.setdefault("cron_expression", cron_task.cron_expression)
            result.setdefault("trigger_count", cron_task.trigger_count)

        return result

    async def _run_internal(
        self,
        *,
        task: dict[str, Any],
        run_context: dict[str, Any],
        route_decision: dict[str, Any] | None = None,
        source_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        start_time = time.time()
        run_id = str(run_context.get("run_id") or "")
        
        logger.info(f"[ProactiveWorkflow] Starting for task: {task.get('task_id') or run_id}")
        
        try:
            await self.start_agents()
            memory_store = get_memory_store()
            memory_enabled = task.get("memory_enabled", True) is not False
            private_memory_enabled = memory_enabled and task.get("private_memory_enabled", True) is not False
            resume_request = task.get("resume") if isinstance(task.get("resume"), dict) else {}
            if memory_enabled and isinstance(resume_request.get("run_id"), str) and not isinstance(resume_request.get("task_graph"), dict):
                loaded_resume = await memory_store.build_resume_payload(
                    run_id=resume_request["run_id"],
                    resume_from_step_id=resume_request.get("resume_from_step_id"),
                )
                if isinstance(loaded_resume, dict):
                    merged_resume = dict(loaded_resume)
                    merged_resume.update(resume_request)
                    resume_request = merged_resume
            resume_request = apply_approval_decision_to_resume_request(
                resume_request=resume_request,
            )
            task = apply_resume_context(
                task=task,
                resume_request=resume_request,
            )
            intent_result = self._ensure_proactive_result(
                await self._intent_agent.recognize(task=task),
                agent_name="intent",
            )
            logger.info(f"[ProactiveWorkflow] Intent recognized: {intent_result.output.get('primary_intent_type')}")

            planning_memory = {"hits": [], "summary": {}}
            if memory_enabled:
                await persist_intent_memory(
                    memory_store=memory_store,
                    run_id=run_id,
                    task=task,
                    intent_output=intent_result.output,
                )
                planning_memory = await memory_store.retrieve_for_planning(
                    task=task,
                    intent=intent_result.output,
                    limit=5,
                )
                planning_memory = merge_resume_memory_into_planning_memory(
                    planning_memory=planning_memory,
                    resume_request=resume_request,
                    private_memory_enabled=private_memory_enabled,
                )
            is_resume = bool(resume_request)

            replan_details: dict[str, Any] | None = None
            execution_state = resume_request.get("execution_state") if is_resume else None
            resume_from_step_id = (
                resume_request.get("resume_from_step_id")
                or (execution_state.get("failed_step_id") if isinstance(execution_state, dict) else None)
            ) if is_resume else None

            if is_resume:
                orchestrator_result = self._new_placeholder_result(
                    output=resume_request.get("task_graph") if isinstance(resume_request.get("task_graph"), dict) else {},
                    agent_name="orchestrator",
                )
                critic_result = self._new_placeholder_result(
                    output={"ok": True, "resumed": True},
                    agent_name="critic",
                )
                active_task_graph = resume_request.get("task_graph") if isinstance(resume_request.get("task_graph"), dict) else {}
                replan_details = {
                    "trigger": "manual_resume",
                    "reason": f"resume_from_step:{resume_from_step_id or 'unknown'}",
                }
            else:
                plan_context = await self._build_orchestrator_context(
                    phase="plan",
                    task=task,
                    intent=intent_result.output,
                    memory_enabled=memory_enabled,
                    planning_memory=planning_memory,
                    run_id=run_id,
                )
                orchestrator_result = self._ensure_proactive_result(
                    await self._orchestrator_agent.orchestrate(
                        task=task,
                        context=self._extend_orchestrator_context(
                            task=task,
                            base_context=plan_context,
                        ),
                    ),
                    agent_name="orchestrator",
                )
                logger.info(f"[ProactiveWorkflow] Plan created with {len(orchestrator_result.output.get('plan_steps', []))} steps")
                if memory_enabled:
                    await persist_plan_memory(
                        memory_store=memory_store,
                        run_id=run_id,
                        task=task,
                        orchestrator_output=orchestrator_result.output,
                    )
                
                critic_result = await self._call_critic_review(
                    task=task,
                    orchestrator=orchestrator_result.output,
                )
                logger.info(f"[ProactiveWorkflow] Review completed: ok={critic_result.output.get('ok')}")

                active_task_graph = orchestrator_result.output
                if should_replan(critic_result.output):
                    logger.info("[ProactiveWorkflow] Critic rejected plan. Starting replan")
                    replan_base = await self._build_orchestrator_context(
                        phase="replan",
                        task=task,
                        intent=intent_result.output,
                        memory_enabled=memory_enabled,
                        planning_memory=planning_memory,
                        run_id=run_id,
                    )
                    replan_result = self._ensure_proactive_result(
                        await self._orchestrator_agent.orchestrate(
                            task=task,
                            context=self._extend_orchestrator_context(
                                task=task,
                                base_context={
                                    "phase": "replan",
                                    **replan_base,
                                    "critic": critic_result.output,
                                    "prior_orchestrator_plan": orchestrator_result.output,
                                    "prior_task_graph": active_task_graph,
                                },
                            ),
                        ),
                        agent_name="orchestrator",
                    )
                    active_task_graph = append_replan_subgraph(
                        active_task_graph,
                        replan_result.output,
                        reason=build_replan_reason(critic_result.output),
                    )
                    replan_details = {
                        "trigger": "critic_rejected",
                        "reason": build_replan_reason(critic_result.output),
                        "orchestrator_plan": replan_result.output,
                    }
                    logger.info(
                        "[ProactiveWorkflow] Replan completed with %s nodes",
                        len(active_task_graph.get("nodes", [])) if isinstance(active_task_graph, dict) else 0,
                    )
            
            completed_step_records: list[dict[str, Any]] = []
            current_segment_id: str | None = None

            async def _on_node_completed(*, node, trace_entry, node_result) -> None:
                nonlocal current_segment_id
                # Memory recording
                if memory_enabled:
                    await memory_store.record_working_memory(
                        run_id=run_id,
                        task=task,
                        trace_entry=trace_entry,
                        node=node,
                        node_result=node_result,
                        private_memory_enabled=private_memory_enabled,
                    )
                # Session segmentation
                try:
                    completed_step_records.append({
                        "step_id": str(node.get("step_id") or ""),
                        "kind": node.get("kind"),
                        "status": trace_entry.get("status"),
                        "tool_name": trace_entry.get("tool_name"),
                        "target_agent": trace_entry.get("target_agent"),
                    })
                    step_count = len(completed_step_records)
                    if self._session_segmenter.should_segment(step_count):
                        checkpoint = await self._session_segmenter.create_checkpoint(
                            run_id=run_id,
                            step_count=step_count,
                            steps=list(completed_step_records),
                            parent_segment_id=current_segment_id,
                            context={
                                "intent": intent_result.output,
                                "task": {
                                    k: v
                                    for k, v in task.items()
                                    if k in ("task_id", "content", "source")
                                },
                            },
                        )
                        current_segment_id = checkpoint.segment_id
                        completed_step_records.clear()
                        logger.info(
                            "Session segmented at step %d: segment %d",
                            step_count,
                            checkpoint.segment_index,
                        )
                except Exception as seg_exc:
                    logger.warning("Session segmentation failed, continuing: %s", seg_exc)

            executor = TaskGraphExecutor(
                delegate_handlers={
                    "system_engineer": self._engineer_agent.analyze_task,
                    "engineer": self._engineer_agent.analyze_task,
                    "risk_analyst": self._analyst_agent.analyze_task,
                    "analyst": self._analyst_agent.analyze_task,
                },
                on_node_completed=_on_node_completed,
            )
            execution_result = await executor.execute(
                task=task,
                task_graph=active_task_graph,
                execution_state=execution_state,
                resume_from_step_id=resume_from_step_id if isinstance(resume_from_step_id, str) else None,
            )
            runtime_replan = await self._maybe_runtime_replan(
                task=task,
                intent_result=intent_result,
                critic_result=critic_result,
                memory_enabled=memory_enabled,
                planning_memory=planning_memory,
                active_task_graph=active_task_graph,
                execution_result=execution_result,
                executor=executor,
                is_resume=is_resume,
                run_id=run_id,
            )
            if runtime_replan is not None:
                active_task_graph = runtime_replan["task_graph"]
                execution_result = runtime_replan["execution_result"]
                replan_details = runtime_replan["replan_details"]
            logger.info(
                "[ProactiveWorkflow] TaskGraph execution completed with status=%s",
                execution_result.get("status"),
            )

            delegate_results = execution_result.get("delegate_results", {})
            engineer_result = delegate_results.get("system_engineer") or delegate_results.get("engineer") or ProactiveAgentResult(
                ok=True,
                output={},
            )
            analyst_result = delegate_results.get("risk_analyst") or delegate_results.get("analyst") or ProactiveAgentResult(
                ok=True,
                output={},
            )
            critic_final_result = await self._call_critic_review(
                task=task,
                orchestrator=orchestrator_result.output if isinstance(orchestrator_result.output, dict) else {},
                receipts=execution_result.get("receipts", []),
                final_output=execution_result.get("final_output", {}),
                phase="final_review",
            )
            critic_final_output = normalize_critic_final_output(
                critic_output=critic_final_result.output,
                receipts=execution_result.get("receipts", []),
            )
            critic_final_result = self._replace_output(
                critic_final_result,
                output=critic_final_output,
            )
            persisted_memory = {
                "run_summary": {},
                "summary_entry": None,
                "lesson_entry": None,
            }
            if memory_enabled and not requires_manual_approval(
                critic_output=critic_result.output,
                receipts=execution_result.get("receipts", []),
                approval_records=execution_result.get("approval_records", []),
            ):
                persisted_memory = await memory_store.persist_run_artifacts(
                    run_id=run_id,
                    task=task,
                    final_output=execution_result.get("final_output", {}),
                    critic_final=critic_final_result.output,
                )
            
            # Skill 置信度更新: 基于执行结果和 Critic 评审更新被注入 Skill 的置信度
            tracked_skill_ids = self._skill_usage_tracker.get_tracked_skills(run_id)
            try:
                execution_had_failures = execution_result.get("status") != "completed"
                skill_updates = await self._skill_usage_tracker.update_after_execution(
                    run_id=run_id,
                    execution_success=not execution_had_failures,
                    critic_ok=critic_final_result.output.get("ok", False),
                )
                for update in skill_updates:
                    logger.info(
                        "Skill %s confidence updated: %.2f -> %.2f (status: %s -> %s)",
                        update["skill_id"],
                        update["old_confidence"],
                        update["new_confidence"],
                        update["old_status"],
                        update["new_status"],
                    )
            except Exception as exc:
                logger.warning("Skill confidence update failed: %s", exc)
            finally:
                self._skill_usage_tracker.clear_tracking(run_id)

            # Skill 改进闭环: 当 Skill 被使用但产生次优结果时, 提议修订
            try:
                reviser = SkillReviser(self._skill_store)
                for skill_id in tracked_skill_ids:
                    proposal = await reviser.check_and_propose_revision(
                        skill_id=skill_id,
                        run_id=run_id,
                        execution_result=execution_result.get("final_output", {}),
                        critic_final=critic_final_result.output,
                    )
                    if proposal:
                        result = await reviser.apply_revision(skill_id=skill_id, proposal=proposal)
                        logger.info("Skill %s revised: %s", skill_id, proposal.reason)
            except Exception as exc:
                logger.warning("Skill revision failed: %s", exc)

            # SkillProposer: 从高质量完成的 run 中提取可复用模式
            try:
                skill_proposer = SkillProposer(self._skill_store)
                skill_proposal = await skill_proposer.propose(
                    run_id=run_id,
                    task=task,
                    critic_final=critic_final_result.output,
                    orchestrator_output=(
                        orchestrator_result.output
                        if isinstance(orchestrator_result.output, dict)
                        else {}
                    ),
                    receipts=execution_result.get("receipts", []),
                )
                logger.info("skill_proposal: %s", skill_proposal)
            except Exception as exc:
                logger.warning("Skill proposal failed: %s", exc)
                skill_proposal = {"action": "skipped", "reason": f"error: {exc}"}
            
            result = build_workflow_result(
                run_id=run_id,
                task=task,
                memory_enabled=memory_enabled,
                private_memory_enabled=private_memory_enabled,
                planning_memory=planning_memory,
                resume_request=resume_request,
                persisted_memory=persisted_memory,
                run_context=run_context,
                intent_result=intent_result,
                orchestrator_result=orchestrator_result,
                critic_result=critic_result,
                critic_final_result=critic_final_result,
                engineer_result=engineer_result,
                analyst_result=analyst_result,
                execution_result=execution_result,
                replan_details=replan_details,
                route_decision=route_decision,
                start_time=start_time,
            )
            if memory_enabled and isinstance(result.get("approval_trace"), list) and result.get("approval_trace"):
                result["approval_memory"] = await memory_store.persist_approval_memory(
                    run_id=run_id,
                    task=task,
                    approval_records=result.get("approval_trace", []),
                )
            if memory_enabled:
                await memory_store.save_run_context(
                    run_id=run_id,
                    event_id=str(
                        (source_event or {}).get("event_id")
                        or task.get("task_id")
                        or run_id
                    ),
                    data={
                        "status": result.get("status"),
                        "entry_type": result.get("entry_type"),
                        "run_context": result.get("run_context", {}),
                        "task": task,
                        "source_event": source_event or {},
                        "route_decision": route_decision or {},
                        "intent": result.get("intent", {}),
                        "task_graph": result.get("task_graph", {}),
                        "task_graph_execution": result.get("task_graph_execution", {}),
                        "receipts": result.get("receipts", []),
                        "approval_trace": result.get("approval_trace", []),
                        "memory_hits": result.get("memory_hits", []),
                        "planning_memory": result.get("planning_memory", {}),
                        "shared_memory_board": result.get("shared_memory_board", []),
                        "private_memory_state": result.get("private_memory_state", {}),
                        "run_summary": result.get("run_summary", {}),
                        "procedural_lesson": result.get("procedural_lesson", {}),
                        "long_term_experience": result.get("long_term_experience", {}),
                        "rejected_experience": result.get("rejected_experience", {}),
                        "memory_policy": result.get("memory_policy", {}),
                        "final_output": result.get("final_output", {}),
                    },
                )
            
            return result
            
        except Exception as e:
            logger.exception(f"[ProactiveWorkflow] Failed: {e}")
            return {
                "status": "failed",
                "run_id": run_id,
                "entry_type": run_context.get("entry_type"),
                "run_context": run_context,
                "task_id": task.get("task_id"),
                "errors": [str(e)],
            }

    def _new_placeholder_result(self, *, output: dict[str, Any], agent_name: str) -> ProactiveAgentResult:
        """构造恢复执行时的占位结果."""
        return ProactiveAgentResult(
            ok=True,
            output=output if isinstance(output, dict) else {},
            meta={"agent_name": agent_name, "placeholder": True},
        )

    async def _call_critic_review(
        self,
        *,
        task: dict[str, Any],
        orchestrator: dict[str, Any],
        receipts: list[dict[str, Any]] | None = None,
        final_output: dict[str, Any] | None = None,
        phase: str = "plan_review",
    ) -> ProactiveAgentResult:
        """兼容旧签名并统一向 critic 透传 receipt 上下文."""
        try:
            return self._ensure_proactive_result(
                await self._critic_agent.review(
                    task=task,
                    orchestrator=orchestrator,
                    receipts=receipts,
                    final_output=final_output,
                    phase=phase,
                ),
                agent_name="critic",
            )
        except TypeError as exc:
            if "unexpected keyword argument" not in str(exc):
                raise
            try:
                return self._ensure_proactive_result(
                    await self._critic_agent.review(
                        task=task,
                        orchestrator=orchestrator,
                        receipts=receipts,
                    ),
                    agent_name="critic",
                )
            except TypeError as inner_exc:
                if "unexpected keyword argument" not in str(inner_exc):
                    raise
                return self._ensure_proactive_result(
                    await self._critic_agent.review(
                        task=task,
                        orchestrator=orchestrator,
                    ),
                    agent_name="critic",
                )

    async def _build_orchestrator_context(
        self,
        *,
        phase: str,
        task: dict[str, Any],
        intent: dict[str, Any],
        memory_enabled: bool,
        planning_memory: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        context = {"phase": phase, "intent": intent}
        if memory_enabled:
            context["memory"] = planning_memory.get("summary", {})
        # Skill 注入: 以结构化 few-shot 形式增强规划能力
        try:
            skill_injector = SkillInjector(self._skill_store)
            intent_str: str | None = None
            if isinstance(intent, dict):
                intent_str = intent.get("primary_intent_type") or intent.get("type")
            skill_payload = await skill_injector.retrieve_applicable_skills(
                task=task,
                intent=intent_str if isinstance(intent_str, str) else None,
                skill_enabled=memory_enabled,
            )
            context["skills"] = skill_payload
            # Skill 使用跟踪: 记录被注入的 skill_id 用于后续置信度更新
            if run_id is not None:
                for skill in skill_payload.get("skills", []):
                    skill_id = skill.get("skill_id")
                    if skill_id:
                        self._skill_usage_tracker.track_usage(
                            skill_id, run_id=run_id, phase=phase
                        )
        except Exception as exc:
            logger.warning("Skill injection failed: %s", exc)
            context["skills"] = {
                "skill_enabled": memory_enabled,
                "skills": [],
                "skill_count": 0,
                "injection_summary": f"Skill injection error: {exc}",
            }
        return context

    def _extend_orchestrator_context(
        self,
        *,
        task: dict[str, Any],
        base_context: dict[str, Any],
    ) -> dict[str, Any]:
        context = dict(base_context)
        if isinstance(task.get("run_context"), dict):
            context["run_context"] = dict(task.get("run_context", {}))
        if isinstance(task.get("event_context"), dict):
            context["event_context"] = dict(task.get("event_context", {}))
        if isinstance(task.get("resume_context"), dict):
            context["resume_context"] = dict(task.get("resume_context", {}))
        return context

    def _resolve_run_context(self, *, task: dict[str, Any]) -> dict[str, Any]:
        existing = task.get("run_context") if isinstance(task.get("run_context"), dict) else {}
        if existing:
            normalized = normalize_run_context(existing)
            is_valid, _errors = validate_run_context(normalized)
            if is_valid:
                return normalized
        return new_run_context(
            entry_type="user_task",
            task_id=str(task.get("task_id") or "") or None,
            metadata={
                "source": task.get("source"),
            },
        )

    def _record_run_trace_snapshot(
        self,
        *,
        result: dict[str, Any],
        source_event: dict[str, Any] | None,
    ) -> None:
        run_id = result.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return
        root_event_id = None
        if isinstance(source_event, dict):
            root_event_id = str(source_event.get("event_id") or "") or None
        snapshot = build_run_trace_snapshot(
            result=result,
            source_event=source_event,
            related_events=self._message_bus.get_related_event_history(
                root_event_id=root_event_id,
                run_id=run_id,
            ),
            related_event_trace=self._message_bus.get_related_event_trace(
                root_event_id=root_event_id,
                run_id=run_id,
            ),
        )
        self._run_trace_store.save_snapshot(snapshot)
        result["run_trace"] = snapshot.to_dict()

    async def _accept_system_event(
        self,
        event: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        is_valid, errors = validate_event(event)
        if not is_valid:
            return dict(event), f"invalid_event:{','.join(errors)}"
        existing = self._message_bus.get_event_history()
        if any(isinstance(item, dict) and item.get("event_id") == event.get("event_id") for item in existing):
            return dict(event), None
        accepted = await self._message_bus.publish_event(event)
        return accepted, None

    async def _maybe_runtime_replan(
        self,
        *,
        task: dict[str, Any],
        intent_result: ProactiveAgentResult,
        critic_result: ProactiveAgentResult,
        memory_enabled: bool,
        planning_memory: dict[str, Any],
        active_task_graph: dict[str, Any],
        execution_result: dict[str, Any],
        executor: TaskGraphExecutor,
        is_resume: bool,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        if is_resume:
            return None
        if not should_runtime_replan(execution_result):
            return None

        reason = build_runtime_replan_reason(execution_result)
        runtime_replan_base = await self._build_orchestrator_context(
            phase="runtime_replan",
            task=task,
            intent=intent_result.output,
            memory_enabled=memory_enabled,
            planning_memory=planning_memory,
            run_id=run_id,
        )
        replan_result = self._ensure_proactive_result(
            await self._orchestrator_agent.orchestrate(
                task=task,
                context=self._extend_orchestrator_context(
                    task=task,
                    base_context={
                        "phase": "runtime_replan",
                        **runtime_replan_base,
                        "critic": critic_result.output,
                        "prior_task_graph": active_task_graph,
                        "execution_failure": extract_execution_failure(execution_result),
                    },
                ),
            ),
            agent_name="orchestrator",
        )
        runtime_execution = await executor.execute(
            task=task,
            task_graph=replan_result.output,
        )
        return {
            "task_graph": replan_result.output,
            "execution_result": runtime_execution,
            "replan_details": {
                "trigger": "execution_failed",
                "reason": reason,
                "orchestrator_plan": replan_result.output,
                "prior_execution": extract_execution_failure(execution_result),
            },
        }

    def _ensure_proactive_result(
        self,
        result: Any,
        *,
        agent_name: str,
    ) -> ProactiveAgentResult:
        if isinstance(result, ProactiveAgentResult):
            return result
        output = result.output if isinstance(getattr(result, "output", None), dict) else {}
        usage = result.usage if isinstance(getattr(result, "usage", None), dict) else None
        meta = result.meta if isinstance(getattr(result, "meta", None), dict) else {}
        meta = dict(meta or {})
        meta.setdefault("agent_name", agent_name)
        return ProactiveAgentResult(
            ok=bool(getattr(result, "ok", False)),
            output=output,
            usage=usage,
            meta=meta,
            react_steps=list(getattr(result, "react_steps", []) or []),
            bdi_state=dict(getattr(result, "bdi_state", {}) or {}),
            llm_interactions=list(getattr(result, "llm_interactions", []) or []),
        )

    def _replace_output(
        self,
        result: ProactiveAgentResult,
        *,
        output: dict[str, Any],
    ) -> ProactiveAgentResult:
        return ProactiveAgentResult(
            ok=result.ok,
            output=output,
            usage=result.usage,
            meta=result.meta,
            react_steps=result.react_steps,
            bdi_state=result.bdi_state,
            llm_interactions=result.llm_interactions,
        )


_proactive_workflow: Optional[ProactiveMultiAgentWorkflow] = None


async def run_proactive_workflow(*, task: dict[str, Any]) -> dict[str, Any]:
    """运行统一主动工作流并补充最小观测字段."""
    inc_counter("orchestrator_runs_total")
    start_time = time.time()

    run_id = new_run_id("proactive")
    logger.info(f"Starting proactive multi-agent orchestration for task: {task.get('task_id') or run_id}")

    try:
        reset_proactive_workflow()
        workflow = get_proactive_workflow()
        result = await workflow.run(task)

        out = build_workflow_output(
            task=task,
            run_id=run_id,
            result=result,
            start_time=start_time,
        )

        latency_ms = (time.time() - start_time) * 1000
        observe_ms("orchestrator_latency_ms", latency_ms)
        inc_counter("orchestrator_runs_success")
        return out
    except Exception as e:
        latency_ms = (time.time() - start_time) * 1000
        observe_ms("orchestrator_latency_ms", latency_ms)
        inc_counter("orchestrator_runs_error")
        logger.exception(f"Proactive orchestration failed for task {task.get('task_id') or run_id}")
        return {
            "ok": False,
            "latency_ms": latency_ms,
            "result": {
                "run_id": run_id,
                "task_id": task.get("task_id"),
                "errors": [str(e)],
                "tokens_total": 0,
            },
        }


def get_proactive_workflow() -> ProactiveMultiAgentWorkflow:
    """获取主动工作流单例."""
    global _proactive_workflow
    if _proactive_workflow is None:
        _proactive_workflow = ProactiveMultiAgentWorkflow()
    return _proactive_workflow


def reset_proactive_workflow() -> None:
    """重置主动工作流."""
    global _proactive_workflow
    _proactive_workflow = None


__all__ = [
    "ProactiveMultiAgentWorkflow",
    "run_proactive_workflow",
    "get_proactive_workflow",
    "reset_proactive_workflow",
]
