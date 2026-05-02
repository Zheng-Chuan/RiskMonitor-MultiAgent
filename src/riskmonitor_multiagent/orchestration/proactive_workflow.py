"""
主动多 Agent 协作工作流.

使用具备 BDI + ReAct + 后台监控的主动 Agent.
"""

from __future__ import annotations

import asyncio
import logging
import os
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
from riskmonitor_multiagent.memory import get_memory_store
from riskmonitor_multiagent.orchestration.message_bus import get_message_bus
from riskmonitor_multiagent.observability.run_trace import (
    build_run_trace_snapshot,
    get_run_trace_store,
)
from riskmonitor_multiagent.orchestration.task_graph_executor import TaskGraphExecutor
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms

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
            failed = self._build_invalid_event_result(
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
            blocked = self._build_blocked_event_result(
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
            candidate_agents=candidate_agents or self._default_candidate_agents_for_event(normalized_event),
            context={
                "run_id": run_context.get("run_id"),
                "entry_type": run_context.get("entry_type"),
                "task": {"task_id": provisional_task_id or normalized_event.get("event_id")},
            },
        )
        task = self._build_task_from_event(
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
            resume_request = self._apply_approval_decision_to_resume_request(
                resume_request=resume_request,
            )
            task = self._apply_resume_context(
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
                await self._persist_intent_memory(
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
                planning_memory = self._merge_resume_memory_into_planning_memory(
                    planning_memory=planning_memory,
                    resume_request=resume_request,
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
                orchestrator_result = self._ensure_proactive_result(
                    await self._orchestrator_agent.orchestrate(
                        task=task,
                        context=self._extend_orchestrator_context(
                            task=task,
                            base_context=self._build_orchestrator_context(
                                phase="plan",
                                intent=intent_result.output,
                                memory_enabled=memory_enabled,
                                planning_memory=planning_memory,
                            ),
                        ),
                    ),
                    agent_name="orchestrator",
                )
                logger.info(f"[ProactiveWorkflow] Plan created with {len(orchestrator_result.output.get('plan_steps', []))} steps")
                if memory_enabled:
                    await self._persist_plan_memory(
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
                if self._should_replan(critic_result.output):
                    logger.info("[ProactiveWorkflow] Critic rejected plan. Starting replan")
                    replan_result = self._ensure_proactive_result(
                        await self._orchestrator_agent.orchestrate(
                            task=task,
                            context=self._extend_orchestrator_context(
                                task=task,
                                base_context={
                                    "phase": "replan",
                                    **self._build_orchestrator_context(
                                        phase="replan",
                                        intent=intent_result.output,
                                        memory_enabled=memory_enabled,
                                        planning_memory=planning_memory,
                                    ),
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
                        reason=self._build_replan_reason(critic_result.output),
                    )
                    replan_details = {
                        "trigger": "critic_rejected",
                        "reason": self._build_replan_reason(critic_result.output),
                        "orchestrator_plan": replan_result.output,
                    }
                    logger.info(
                        "[ProactiveWorkflow] Replan completed with %s nodes",
                        len(active_task_graph.get("nodes", [])) if isinstance(active_task_graph, dict) else 0,
                    )
            
            async def _record_node_memory(*, node, trace_entry, node_result) -> None:
                if not memory_enabled:
                    return
                await memory_store.record_working_memory(
                    run_id=run_id,
                    task=task,
                    trace_entry=trace_entry,
                )

            executor = TaskGraphExecutor(
                delegate_handlers={
                    "system_engineer": self._engineer_agent.analyze_task,
                    "engineer": self._engineer_agent.analyze_task,
                    "risk_analyst": self._analyst_agent.analyze_task,
                    "analyst": self._analyst_agent.analyze_task,
                },
                on_node_completed=_record_node_memory if memory_enabled else None,
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
            critic_final_output = self._normalize_critic_final_output(
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
            if memory_enabled and not self._requires_manual_approval(
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
            
            result = self._build_result(
                run_id=run_id,
                task=task,
                memory_enabled=memory_enabled,
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
                        "run_summary": result.get("run_summary", {}),
                        "procedural_lesson": result.get("procedural_lesson", {}),
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
    
    def _build_result(
        self,
        *,
        run_id: str,
        task: dict[str, Any],
        memory_enabled: bool,
        planning_memory: dict[str, Any],
        resume_request: dict[str, Any],
        persisted_memory: dict[str, Any],
        run_context: dict[str, Any],
        intent_result: Any,
        orchestrator_result: Any,
        critic_result: Any,
        critic_final_result: Any,
        engineer_result: Any,
        analyst_result: Any,
        execution_result: dict[str, Any],
        replan_details: dict[str, Any] | None,
        route_decision: dict[str, Any] | None,
        start_time: float,
    ) -> dict[str, Any]:
        """构建结果."""
        latency_ms = (time.time() - start_time) * 1000
        
        all_react_steps = []
        all_react_steps.extend(intent_result.react_steps)
        all_react_steps.extend(orchestrator_result.react_steps)
        all_react_steps.extend(critic_result.react_steps)
        all_react_steps.extend(critic_final_result.react_steps)
        all_react_steps.extend(engineer_result.react_steps)
        all_react_steps.extend(analyst_result.react_steps)
        
        all_llm_interactions = []
        all_llm_interactions.extend(intent_result.llm_interactions)
        all_llm_interactions.extend(orchestrator_result.llm_interactions)
        all_llm_interactions.extend(critic_result.llm_interactions)
        all_llm_interactions.extend(critic_final_result.llm_interactions)
        all_llm_interactions.extend(engineer_result.llm_interactions)
        all_llm_interactions.extend(analyst_result.llm_interactions)

        receipts = execution_result.get("receipts", [])
        approval_trace = self._build_approval_trace_items(
            approval_records=execution_result.get("approval_records", []),
            receipts=receipts,
        )

        result = {
            "status": execution_result.get("status", "completed"),
            "run_id": run_id,
            "entry_type": run_context.get("entry_type"),
            "run_context": run_context,
            "task_id": task.get("task_id"),
            "task": task,
            "route_decision": route_decision or {},
            "intent": intent_result.output,
            "task_graph": execution_result.get("task_graph", orchestrator_result.output.get("task_graph", {})),
            "task_graph_execution": execution_result.get("task_graph_execution", {}),
            "orchestrator_plan": orchestrator_result.output,
            "critic_plan": critic_result.output,
            "critic_final": critic_final_result.output,
            "replan": replan_details or {},
            "receipts": receipts,
            "approval_trace": approval_trace,
            "engineer": engineer_result.output,
            "analyst": analyst_result.output,
            "final_output": self._merge_final_with_critic(
                final_output=execution_result.get("final_output", {}),
                critic_final=critic_final_result.output,
            ),
            "react_steps": [
                {
                    "step_id": s.step_id,
                    "thought": s.thought,
                    "reasoning": s.reasoning,
                    "evidence": s.evidence,
                    "action_type": s.action_type,
                    "observation": s.observation,
                }
                for s in all_react_steps
            ],
            "bdi_states": {
                "intent": intent_result.bdi_state,
                "orchestrator": orchestrator_result.bdi_state,
                "critic": critic_result.bdi_state,
                "critic_final": critic_final_result.bdi_state,
                "engineer": engineer_result.bdi_state,
                "analyst": analyst_result.bdi_state,
            },
            "llm_interactions": all_llm_interactions,
            "latency_ms": latency_ms,
            "errors": execution_result.get("task_graph_execution", {}).get("errors", []),
        }
        if memory_enabled:
            result["memory_hits"] = planning_memory.get("hits", [])
            result["planning_memory"] = planning_memory.get("summary", {})
            result["resume_memory_state"] = resume_request.get("memory_state", [])
            result["run_summary"] = persisted_memory.get("run_summary", {})
            result["procedural_lesson"] = (
                persisted_memory.get("lesson_entry")
                if isinstance(persisted_memory.get("lesson_entry"), dict)
                else {}
            )
            result["approval_memory"] = []
        if isinstance(task.get("trigger_event_id"), str) and task.get("trigger_event_id"):
            result["trigger"] = {
                "event_id": task.get("trigger_event_id"),
                "reason": task.get("trigger_reason"),
                "evidence": task.get("trigger_evidence", {}),
            }
        return result

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

    def _normalize_critic_final_output(
        self,
        *,
        critic_output: dict[str, Any],
        receipts: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """确保最终审查结果总是带上可追溯的 receipt 证据链."""
        normalized = dict(critic_output) if isinstance(critic_output, dict) else {}
        receipt_command_ids = [
            receipt.get("command_id")
            for receipt in (receipts or [])
            if isinstance(receipt, dict) and isinstance(receipt.get("command_id"), str)
        ]

        evidence = normalized.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}
        evidence["receipt_command_ids"] = receipt_command_ids
        normalized["evidence"] = evidence

        run_summary = normalized.get("run_summary")
        if not isinstance(run_summary, dict):
            run_summary = {}
        run_summary["receipt_command_ids"] = receipt_command_ids
        normalized["run_summary"] = run_summary

        normalized.setdefault("ok", True)
        normalized.setdefault("issues", [])
        normalized.setdefault("suggested_fixes", [])
        return normalized

    def _build_orchestrator_context(
        self,
        *,
        phase: str,
        intent: dict[str, Any],
        memory_enabled: bool,
        planning_memory: dict[str, Any],
    ) -> dict[str, Any]:
        context = {"phase": phase, "intent": intent}
        if memory_enabled:
            context["memory"] = planning_memory.get("summary", {})
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

    def _default_candidate_agents_for_event(self, event: dict[str, Any]) -> list[str]:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        event_type = str(event.get("event_type") or "")
        if event_type == "risk_breach_detected":
            return ["risk_analyst", "critic", "orchestrator"]
        if event_type == "approval_required":
            return ["human", "critic", "orchestrator"]
        if event_type == "tool_finished" and payload.get("success") is False:
            return ["system_engineer", "critic", "orchestrator"]
        return ["orchestrator", "critic", "risk_analyst", "system_engineer"]

    def _build_task_from_event(
        self,
        *,
        event: dict[str, Any],
        route_decision: dict[str, Any],
    ) -> dict[str, Any]:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        base_task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
        task = dict(base_task)
        task.setdefault("task_id", str(payload.get("task_id") or event.get("event_id") or "event_task"))
        task.setdefault("session_id", str(payload.get("session_id") or f"event_{event.get('source_agent') or 'system'}"))
        task.setdefault("source", "system_event")
        task.setdefault("payload", {})
        if not isinstance(task.get("payload"), dict):
            task["payload"] = {}
        content = (
            payload.get("content")
            or payload.get("summary")
            or payload.get("reason")
            or f"处理系统事件 {event.get('event_type')}"
        )
        task["payload"].setdefault("content", str(content))
        task["payload"].setdefault("event_payload", payload)
        task["payload"].setdefault("trigger_event_id", event.get("event_id"))
        task["payload"].setdefault("trigger_reason", route_decision.get("reason"))
        task["payload"].setdefault(
            "trigger_evidence",
            {
                "event_type": event.get("event_type"),
                "source_agent": event.get("source_agent"),
                "payload": payload,
            },
        )
        task["trigger_event_id"] = event.get("event_id")
        task["trigger_reason"] = route_decision.get("reason")
        task["trigger_evidence"] = {
            "event_type": event.get("event_type"),
            "source_agent": event.get("source_agent"),
            "payload": payload,
        }
        return task

    def _requires_manual_approval(
        self,
        *,
        critic_output: dict[str, Any],
        receipts: list[dict[str, Any]] | None,
        approval_records: list[dict[str, Any]] | None,
    ) -> bool:
        auto_approve = os.getenv("HITL_AUTO_APPROVE", "1").strip() not in {"0", "false", "False"}
        if isinstance(approval_records, list):
            for record in approval_records:
                if not isinstance(record, dict):
                    continue
                state = record.get("approval_state") or record.get("state")
                if state in {"resumed", "approved", "approved_but_failed"}:
                    continue
                if state in {"pending", "rejected", "expired"}:
                    return True
        if isinstance(receipts, list):
            for receipt in receipts:
                if not isinstance(receipt, dict):
                    continue
                if receipt.get("approval_state") in {"approved", "approved_but_failed", "resumed"}:
                    return False
                if receipt.get("approval_state") in {"pending", "rejected", "expired"}:
                    return True
        if isinstance(critic_output, dict) and critic_output.get("require_human_approval"):
            return not auto_approve
        return False

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

    def _build_blocked_event_result(
        self,
        *,
        event: dict[str, Any],
        run_context: dict[str, Any],
        reason: str,
        budget_evidence: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "blocked",
            "run_id": run_context.get("run_id"),
            "entry_type": run_context.get("entry_type"),
            "run_context": run_context,
            "task_id": run_context.get("task_id"),
            "task": {
                "task_id": run_context.get("task_id"),
                "source": "system_event",
                "payload": event.get("payload", {}),
            },
            "route_decision": {},
            "intent": {},
            "task_graph": {},
            "task_graph_execution": {},
            "orchestrator_plan": {},
            "critic_plan": {},
            "critic_final": {},
            "replan": {},
            "receipts": [],
            "approval_trace": [],
            "engineer": {},
            "analyst": {},
            "final_output": {},
            "react_steps": [],
            "bdi_states": {},
            "llm_interactions": [],
            "latency_ms": 0.0,
            "errors": [reason],
            "trigger": {
                "event_id": event.get("event_id"),
                "reason": reason,
                "evidence": budget_evidence,
            },
            "governance": {
                "proactive_budget": {
                    "allowed": False,
                    "reason": reason,
                    "evidence": budget_evidence,
                }
            },
        }

    def _build_invalid_event_result(
        self,
        *,
        event: dict[str, Any],
        run_context: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        return {
            "status": "failed",
            "run_id": run_context.get("run_id"),
            "entry_type": run_context.get("entry_type"),
            "run_context": run_context,
            "task_id": run_context.get("task_id"),
            "task": {"task_id": run_context.get("task_id"), "source": "system_event", "payload": event.get("payload", {})},
            "route_decision": {},
            "intent": {},
            "task_graph": {},
            "task_graph_execution": {},
            "orchestrator_plan": {},
            "critic_plan": {},
            "critic_final": {},
            "replan": {},
            "receipts": [],
            "approval_trace": [],
            "engineer": {},
            "analyst": {},
            "final_output": {},
            "react_steps": [],
            "bdi_states": {},
            "llm_interactions": [],
            "latency_ms": 0.0,
            "errors": [reason],
            "trigger": {
                "event_id": event.get("event_id"),
                "reason": reason,
                "evidence": {"event_type": event.get("event_type")},
            },
        }

    def _apply_resume_context(
        self,
        *,
        task: dict[str, Any],
        resume_request: dict[str, Any],
    ) -> dict[str, Any]:
        if not resume_request:
            return task
        enriched = dict(task)
        enriched["resume"] = dict(resume_request)
        enriched["resume_context"] = {
            "run_id": resume_request.get("run_id"),
            "resume_from_step_id": resume_request.get("resume_from_step_id"),
            "memory_state": list(resume_request.get("memory_state") or []),
            "run_summary": dict(resume_request.get("run_summary") or {}) if isinstance(resume_request.get("run_summary"), dict) else {},
            "approval_decision": dict(resume_request.get("approval_decision") or {}) if isinstance(resume_request.get("approval_decision"), dict) else {},
        }
        return enriched

    def _apply_approval_decision_to_resume_request(
        self,
        *,
        resume_request: dict[str, Any],
    ) -> dict[str, Any]:
        if not resume_request:
            return resume_request
        approval_decision = (
            dict(resume_request.get("approval_decision"))
            if isinstance(resume_request.get("approval_decision"), dict)
            else {}
        )
        task_graph = resume_request.get("task_graph")
        if not approval_decision or not isinstance(task_graph, dict):
            return resume_request

        execution_state = resume_request.get("execution_state") if isinstance(resume_request.get("execution_state"), dict) else {}
        target_step_id = (
            approval_decision.get("step_id")
            or resume_request.get("resume_from_step_id")
            or execution_state.get("blocked_step_id")
        )
        if not isinstance(target_step_id, str) or not target_step_id:
            return resume_request

        updated = dict(resume_request)
        cloned_graph = {
            "schema_version": task_graph.get("schema_version"),
            "nodes": [dict(node) for node in task_graph.get("nodes", []) if isinstance(node, dict)],
            "edges": [dict(edge) for edge in task_graph.get("edges", []) if isinstance(edge, dict)],
        }
        state = str(approval_decision.get("state") or "approved").strip().lower()
        for node in cloned_graph["nodes"]:
            if node.get("step_id") != target_step_id:
                continue
            if node.get("kind") == "tool_call":
                params = dict(node.get("params")) if isinstance(node.get("params"), dict) else {}
                existing = dict(params.get("approval")) if isinstance(params.get("approval"), dict) else {}
                existing.update(
                    {
                        "approved": state in {"approved", "resumed"},
                        "state": state,
                        "actor": approval_decision.get("actor"),
                        "note": approval_decision.get("note"),
                        "reason": approval_decision.get("reason"),
                        "risk_level": approval_decision.get("risk_level"),
                        "impact_scope": approval_decision.get("impact_scope"),
                        "recommended_action": approval_decision.get("recommended_action"),
                    }
                )
                params["approval"] = existing
                node["params"] = params
            node_approval = dict(node.get("approval")) if isinstance(node.get("approval"), dict) else {}
            if node_approval.get("required") is True:
                node_approval.update(
                    {
                        "state": state,
                        "actor": approval_decision.get("actor"),
                        "note": approval_decision.get("note"),
                        "reason": approval_decision.get("reason") or node_approval.get("reason"),
                        "risk_level": approval_decision.get("risk_level") or node_approval.get("risk_level"),
                        "impact_scope": approval_decision.get("impact_scope") or node_approval.get("impact_scope"),
                        "recommended_action": approval_decision.get("recommended_action") or node_approval.get("recommended_action"),
                    }
                )
                node["approval"] = node_approval
        updated["task_graph"] = cloned_graph
        updated["resume_from_step_id"] = target_step_id
        return updated

    def _merge_resume_memory_into_planning_memory(
        self,
        *,
        planning_memory: dict[str, Any],
        resume_request: dict[str, Any],
    ) -> dict[str, Any]:
        if not resume_request:
            return planning_memory
        merged = {
            "hits": list(planning_memory.get("hits", [])),
            "summary": dict(planning_memory.get("summary", {})),
        }
        memory_state = resume_request.get("memory_state")
        if isinstance(memory_state, list) and memory_state:
            merged["hits"].extend([item for item in memory_state if isinstance(item, dict)])
            merged["summary"]["resume_memory_state_count"] = len(memory_state)
        run_summary = resume_request.get("run_summary")
        if isinstance(run_summary, dict) and run_summary:
            merged["summary"]["resume_run_summary"] = dict(run_summary)
        return merged

    def _build_approval_trace_items(
        self,
        *,
        approval_records: list[dict[str, Any]] | None,
        receipts: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        trace_items: list[dict[str, Any]] = []
        if isinstance(approval_records, list):
            for record in approval_records:
                if not isinstance(record, dict):
                    continue
                trace_items.append(
                    {
                        "approval_id": record.get("approval_id"),
                        "level": record.get("level"),
                        "step_id": record.get("step_id"),
                        "command_id": record.get("command_id"),
                        "tool_name": record.get("tool_name"),
                        "approval_state": record.get("state"),
                        "required": record.get("required"),
                        "reason": record.get("reason"),
                        "risk_level": record.get("risk_level"),
                        "impact_scope": record.get("impact_scope", []),
                        "recommended_action": record.get("recommended_action"),
                        "actor": record.get("actor"),
                        "note": record.get("note"),
                        "approval_trace": {
                            "required": record.get("required"),
                            "current_state": record.get("state"),
                            "history": [{"state": record.get("state"), "reason": record.get("error") or record.get("reason")}],
                        },
                    }
                )
        if trace_items:
            return trace_items
        if not isinstance(receipts, list):
            return []
        return [
            {
                "approval_id": f"command:{receipt.get('command_id')}",
                "level": "command",
                "step_id": receipt.get("step_id"),
                "command_id": receipt.get("command_id"),
                "tool_name": receipt.get("tool_name"),
                "approval_state": receipt.get("approval_state"),
                "required": (receipt.get("approval_trace") or {}).get("required"),
                "reason": ((receipt.get("evidence") or {}).get("reason") if isinstance(receipt.get("evidence"), dict) else None),
                "risk_level": ((((receipt.get("inputs") or {}).get("_event") or {}).get("severity")) if isinstance((receipt.get("inputs") or {}).get("_event"), dict) else None),
                "impact_scope": [],
                "recommended_action": None,
                "actor": ((receipt.get("inputs") or {}).get("approval") or {}).get("actor") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None,
                "note": ((receipt.get("inputs") or {}).get("approval") or {}).get("note") if isinstance((receipt.get("inputs") or {}).get("approval"), dict) else None,
                "approval_trace": receipt.get("approval_trace"),
            }
            for receipt in receipts
            if isinstance(receipt, dict)
            and receipt.get("side_effect") is True
        ]

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
    ) -> dict[str, Any] | None:
        if is_resume:
            return None
        if not self._should_runtime_replan(execution_result):
            return None

        reason = self._build_runtime_replan_reason(execution_result)
        replan_result = self._ensure_proactive_result(
            await self._orchestrator_agent.orchestrate(
                task=task,
                context=self._extend_orchestrator_context(
                    task=task,
                    base_context={
                        "phase": "runtime_replan",
                        **self._build_orchestrator_context(
                            phase="runtime_replan",
                            intent=intent_result.output,
                            memory_enabled=memory_enabled,
                            planning_memory=planning_memory,
                        ),
                        "critic": critic_result.output,
                        "prior_task_graph": active_task_graph,
                        "execution_failure": self._extract_execution_failure(execution_result),
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
                "prior_execution": self._extract_execution_failure(execution_result),
            },
        }

    def _should_runtime_replan(self, execution_result: dict[str, Any]) -> bool:
        if execution_result.get("status") != "failed":
            return False
        failure = self._extract_execution_failure(execution_result)
        classification = failure.get("failure_classification")
        return classification in {"runtime", "dependency", "timeout", "validation"}

    def _extract_execution_failure(self, execution_result: dict[str, Any]) -> dict[str, Any]:
        trace = (execution_result.get("task_graph_execution") or {}).get("trace") or []
        failed = {}
        for item in reversed(trace):
            if isinstance(item, dict) and item.get("status") == "failed":
                failed = dict(item)
                break
        failed_step_id = (execution_result.get("task_graph_execution") or {}).get("failed_step_id")
        if isinstance(failed_step_id, str) and failed_step_id:
            failed.setdefault("failed_step_id", failed_step_id)
        return failed

    def _build_runtime_replan_reason(self, execution_result: dict[str, Any]) -> str:
        failure = self._extract_execution_failure(execution_result)
        error = failure.get("error")
        classification = failure.get("failure_classification")
        step_id = failure.get("failed_step_id") or failure.get("step_id")
        pieces = [part for part in [str(classification or "").strip(), str(error or "").strip(), str(step_id or "").strip()] if part]
        if pieces:
            return " | ".join(pieces)
        return "execution_failed_runtime_replan"

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

    async def _persist_plan_memory(
        self,
        *,
        memory_store: Any,
        run_id: str,
        task: dict[str, Any],
        orchestrator_output: dict[str, Any],
    ) -> None:
        plan_steps = orchestrator_output.get("plan_steps") if isinstance(orchestrator_output.get("plan_steps"), list) else []
        plan_text = " ; ".join(
            str(step.get("reason") or step.get("instruction") or step.get("kind") or "")
            for step in plan_steps
            if isinstance(step, dict)
        )
        await memory_store.append(
            {
                "agent_id": "orchestrator",
                "scope": "shared",
                "kind": "plan",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "orchestrator_plan",
                "created_by": "orchestrator",
                "trace_ref": {"run_id": run_id},
                "content": {
                    "text": plan_text or "plan generated",
                    "plan_steps": plan_steps,
                    "task_id": task.get("task_id"),
                },
                "tags": ["plan"],
            }
        )

    async def _persist_intent_memory(
        self,
        *,
        memory_store: Any,
        run_id: str,
        task: dict[str, Any],
        intent_output: dict[str, Any],
    ) -> None:
        disambiguation = intent_output.get("disambiguation")
        intents = intent_output.get("intents")
        if not isinstance(disambiguation, dict) or disambiguation.get("has_multiple") is not True:
            return
        if not isinstance(intents, list):
            intents = []
        await memory_store.append(
            {
                "agent_id": "intent",
                "scope": "shared",
                "kind": "intent_disambiguation",
                "memory_type": "episodic",
                "session_id": task.get("session_id") if isinstance(task.get("session_id"), str) else None,
                "run_id": run_id,
                "source": "intent_agent",
                "created_by": "intent",
                "trace_ref": {"run_id": run_id},
                "content": {
                    "text": str(disambiguation.get("explanation") or "multi intent detected"),
                    "intents": intents,
                    "primary_intent_type": intent_output.get("primary_intent_type"),
                },
                "tags": ["intent", "disambiguation"],
            }
        )

    def _merge_final_with_critic(
        self,
        *,
        final_output: dict[str, Any],
        critic_final: dict[str, Any],
    ) -> dict[str, Any]:
        merged = dict(final_output) if isinstance(final_output, dict) else {}
        if isinstance(critic_final, dict):
            summary = critic_final.get("run_summary")
            if isinstance(summary, dict):
                merged["critic_run_summary"] = summary
            evidence = critic_final.get("evidence")
            if isinstance(evidence, dict) and isinstance(evidence.get("receipt_command_ids"), list):
                merged.setdefault("receipt_command_ids", evidence.get("receipt_command_ids"))
        return merged

    def _should_replan(self, critic_output: dict[str, Any]) -> bool:
        """判断是否需要重规划."""
        if not isinstance(critic_output, dict):
            return False
        if critic_output.get("ok") is False:
            return True
        return False

    def _build_replan_reason(self, critic_output: dict[str, Any]) -> str:
        """构造重规划原因."""
        if not isinstance(critic_output, dict):
            return "critic rejected previous plan"

        issues = critic_output.get("issues")
        if isinstance(issues, list) and issues:
            first_issue = issues[0]
            if isinstance(first_issue, str) and first_issue.strip():
                return first_issue.strip()

        fixes = critic_output.get("suggested_fixes")
        if isinstance(fixes, list) and fixes:
            first_fix = fixes[0]
            if isinstance(first_fix, str) and first_fix.strip():
                return first_fix.strip()

        return "critic rejected previous plan"


_proactive_workflow: Optional[ProactiveMultiAgentWorkflow] = None


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
    "get_proactive_workflow",
    "reset_proactive_workflow",
]
