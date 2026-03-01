from __future__ import annotations

import time
import os
from datetime import datetime, timezone
from typing import Any

from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.agents.base import BaseAgent
from riskmonitor_multiagent.contracts.agent_outputs import (
    MANAGER_OUTPUT_SCHEMA_VERSION,
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
    SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
    normalize_critic_review,
    normalize_manager_output,
    normalize_orchestrator_output,
    normalize_risk_analyst_output,
    normalize_system_engineer_output,
    validate_critic_review,
    validate_manager_output,
    validate_orchestrator_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.risk_event import validate_risk_event
from riskmonitor_multiagent.governance.versions import (
    PROMPT_VERSION_SYSTEM_ENGINEER,
    PROMPT_VERSION_MANAGER,
    PROMPT_VERSION_RISK_ANALYST,
    PROMPT_VERSION_ORCHESTRATOR,
    PROMPT_VERSION_CRITIC,
    get_policy_version,
)


class SystemEngineerAgent:
    def __init__(self, *, max_event_latency_ms: int = 60000) -> None:
        self._max_event_latency_ms = int(max_event_latency_ms)
        self._agent = BaseAgent(
            name="system_engineer",
            system_prompt=(
                "You are a system engineer agent focusing on real time infrastructure health.\n"
                "Use only the provided receipts/observations to judge system health.\n"
                "Return only valid JSON.\n"
                "Keys: schema_version, system_issue, reason, latency_ms, evidence, summary, findings, recommendations.\n"
                "schema_version must be system_engineer_output.v1.\n"
                "system_issue must be boolean.\n"
                "reason must be a short snake_case string.\n"
                "summary must be a short Chinese paragraph using only English punctuation.\n"
                "evidence must be an object and must cite receipt command_id when available.\n"
                "Never invent metrics.\n"
            ),
            prompt_version=PROMPT_VERSION_SYSTEM_ENGINEER,
            policy_version=get_policy_version(),
        )

    async def analyze(self, *, event: dict[str, Any], context: dict[str, Any] | None = None, max_tokens: int | None = 512) -> AgentResult:
        ok_event, event_errors = validate_risk_event(event)
        if not ok_event:
            output = {
                "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
                "system_issue": True,
                "reason": "invalid_event_contract",
                "latency_ms": None,
                "evidence": {"event_errors": event_errors},
            }
            output = normalize_system_engineer_output(output)
            return AgentResult(ok=False, output=output)

        now_ms = int(time.time() * 1000)
        occurred_at = event.get("occurred_at")
        latency_ms = None
        if isinstance(occurred_at, str):
            try:
                dt = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
                dt = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
                latency_ms = max(0, now_ms - int(dt.timestamp() * 1000))
            except ValueError:
                latency_ms = None

        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        desk = payload.get("desk")
        exposure = payload.get("exposure")

        if not isinstance(desk, str) or not desk.strip():
            output = {
                "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
                "system_issue": True,
                "reason": "missing_desk",
                "latency_ms": latency_ms,
                "evidence": {"payload_keys": list(payload.keys())},
            }
            output = normalize_system_engineer_output(output)
            ok_out, _ = validate_system_engineer_output(output)
            return AgentResult(ok=ok_out, output=output)

        if exposure is None or not isinstance(exposure, (int, float)):
            output = {
                "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
                "system_issue": True,
                "reason": "bad_exposure",
                "latency_ms": latency_ms,
                "evidence": {"exposure_type": str(type(exposure))},
            }
            output = normalize_system_engineer_output(output)
            ok_out, _ = validate_system_engineer_output(output)
            return AgentResult(ok=ok_out, output=output)

        if latency_ms is not None and latency_ms > self._max_event_latency_ms:
            output = {
                "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
                "system_issue": True,
                "reason": f"event_latency_too_high_ms={latency_ms}",
                "latency_ms": latency_ms,
                "evidence": {"max_event_latency_ms": self._max_event_latency_ms},
            }
            output = normalize_system_engineer_output(output)
            ok_out, _ = validate_system_engineer_output(output)
            return AgentResult(ok=ok_out, output=output)

        receipts = (context or {}).get("receipts") if isinstance(context, dict) else None
        facts = (context or {}).get("facts") if isinstance(context, dict) else None
        observations = (context or {}).get("observations") if isinstance(context, dict) else None

        def _find_tool_result(action: str) -> dict[str, Any] | None:
            if not isinstance(receipts, list):
                return None
            for r in receipts:
                if not isinstance(r, dict) or r.get("schema_version") != "agent_receipt.v1":
                    continue
                out = r.get("output")
                if not isinstance(out, dict):
                    continue
                if out.get("action") != action:
                    continue
                res = out.get("result")
                return res if isinstance(res, dict) else None
            return None

        mysql = _find_tool_result("mysql_health") or {}
        chroma = _find_tool_result("chroma_health") or {}
        kafka = _find_tool_result("kafka_lag") or {}
        service = _find_tool_result("collect_metrics") or {}

        system_issue = False
        reason = "ok"
        block_mode = os.getenv("SYSTEM_ENGINEER_BLOCK_MODE", "block").strip().lower()
        block_on_unhealthy = block_mode in {"block", "strict"}
        if isinstance(mysql.get("ok"), bool) and mysql.get("ok") is False:
            system_issue = bool(block_on_unhealthy)
            reason = "mysql_unhealthy" if block_on_unhealthy else "mysql_unhealthy_degraded"
        elif isinstance(chroma.get("ok"), bool) and chroma.get("ok") is False:
            system_issue = bool(block_on_unhealthy)
            reason = "chroma_unhealthy" if block_on_unhealthy else "chroma_unhealthy_degraded"
        else:
            lag_ms = kafka.get("lag_ms")
            if isinstance(lag_ms, int) and lag_ms >= 120000:
                system_issue = bool(block_on_unhealthy)
                reason = "kafka_lag_high" if block_on_unhealthy else "kafka_lag_high_degraded"

        fallback = {
            "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
            "system_issue": bool(system_issue),
            "reason": reason,
            "latency_ms": latency_ms,
            "summary": "已完成基础设施观测结果的快速检查 并给出是否存在系统性问题的判断",
            "evidence": {
                "event_id": event.get("event_id"),
                "fields": ["payload.desk", "payload.exposure"],
                "facts": facts if isinstance(facts, dict) else None,
                "observations": observations if isinstance(observations, list) else None,
            },
            "findings": {
                "mysql_health": mysql if isinstance(mysql, dict) else None,
                "chroma_health": chroma if isinstance(chroma, dict) else None,
                "kafka_lag": kafka if isinstance(kafka, dict) else None,
                "service_metrics": service if isinstance(service, dict) else None,
            },
            "recommendations": [
                "如存在系统性问题 请先恢复依赖服务再进行后续自动化处置",
                "必要时将事件升级给值班人员并附上观测证据",
            ],
        }

        result = await self._agent.ask_json(
            user_prompt=(
                "Input event:\n"
                f"{event}\n\n"
                "Context facts:\n"
                f"{facts}\n\n"
                "Observations:\n"
                f"{observations}\n\n"
                "Receipts:\n"
                f"{receipts}\n\n"
                "Decide if there is a system issue that should block downstream actions.\n"
                "Focus on kafka/mysql/chroma load, throughput, lag, errors and readiness.\n"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_system_engineer_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_system_engineer_output(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)

    async def analyze_task(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        source = task.get("source") if isinstance(task.get("source"), str) else ""
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        fallback = {
            "schema_version": SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
            "system_issue": False,
            "reason": "ok",
            "latency_ms": None,
            "summary": "已完成系统侧快速排查 并给出初步判断",
            "evidence": {"fields": ["task.source", "task.payload.content"]},
            "findings": {"source": source, "content": content[:200]},
            "recommendations": ["如需要更深入排查 请补充系统指标 日志 与时间范围"],
        }
        result = await self._agent.ask_json(
            user_prompt=(
                "Input task:\n"
                f"{task}\n\n"
                "Context:\n"
                f"{context}\n\n"
                "Act as a system engineer. Identify infra symptoms, likely causes, and safe next steps.\n"
                "Use only evidence from task and context.\n"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_system_engineer_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_system_engineer_output(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)


class RiskAnalystAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="risk_analyst",
            system_prompt=(
                "You are a risk analyst.\n"
                "Return only valid JSON.\n"
                "Keys: schema_version, report, key_facts, confidence, evidence.\n"
                "report must be a short Chinese paragraph using only English punctuation.\n"
                "key_facts must be an object.\n"
                "schema_version must be risk_analyst_output.v1.\n"
                "confidence must be a number between 0 and 1.\n"
                "evidence must be an object with references to input fields.\n"
            ),
            prompt_version=PROMPT_VERSION_RISK_ANALYST,
            policy_version=get_policy_version(),
        )

    async def analyze(self, *, event: dict[str, Any], extra_instruction: str | None = None, max_tokens: int | None = 512) -> AgentResult:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        desk = payload.get("desk")
        exposure = payload.get("exposure")
        fallback = {
            "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
            "report": f"检测到 desk={desk} 的敞口变化值为 {exposure} 已触发阈值 需要进一步确认来源与影响范围",
            "key_facts": {"desk": desk, "exposure": exposure},
            "confidence": 0.7,
            "evidence": {"event_id": event.get("event_id"), "fields": ["payload.desk", "payload.exposure"]},
        }
        extra = extra_instruction.strip() if isinstance(extra_instruction, str) and extra_instruction.strip() else ""
        result = await self._agent.ask_json(
            user_prompt=(
                "Input event:\n"
                f"{event}\n\n"
                "Summarize key facts and write a short report.\n"
                f"{extra}"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_risk_analyst_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_risk_analyst_output(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)

    async def analyze_task(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        source = task.get("source") if isinstance(task.get("source"), str) else ""
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        fallback = {
            "schema_version": RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
            "report": "已完成业务侧初步分析 并给出影响范围与建议下一步",
            "key_facts": {"source": source, "content_snippet": content[:200]},
            "confidence": 0.3,
            "evidence": {"fields": ["task.source", "task.payload.content"]},
        }
        result = await self._agent.ask_json(
            user_prompt=(
                "Input task:\n"
                f"{task}\n\n"
                "Context:\n"
                f"{context}\n\n"
                "Act as a risk analyst. Summarize business impact, key facts, and safe recommendations.\n"
                "Use only evidence from task and context.\n"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_risk_analyst_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_risk_analyst_output(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)


class ManagerAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="manager",
            system_prompt=(
                "You are a manager agent.\n"
                "Return only valid JSON.\n"
                "Keys: schema_version, decision, action, rationale, plan_steps, commands, evidence, degraded, degraded_reason, degraded_scope.\n"
                "schema_version must be manager_output.v1.\n"
                "decision must be one of WATCH or CRITICAL.\n"
                "action and rationale must be Chinese text using only English punctuation.\n"
                "plan_steps must be a list or null.\n"
                "commands must be a list or null.\n"
                "If commands is a list, each item must be an AgentCommand with schema_version=agent_command.v1.\n"
                "AgentCommand keys: schema_version, run_id, command_id, target_agent, action, params, timeout_ms, expected_output_schema.\n"
                "evidence must be an object and must cite receipt command_id when available.\n"
                "evidence must include at least one of: fields, receipt_command_ids, rag_hit_ids.\n"
                "degraded must be a boolean.\n"
                "If degraded is true, degraded_reason must be a short string and degraded_scope must be a non empty list.\n"
            ),
            prompt_version=PROMPT_VERSION_MANAGER,
            policy_version=get_policy_version(),
        )

    async def decide(self, *, event: dict[str, Any], analyst_report: dict[str, Any], max_tokens: int | None = 512) -> AgentResult:
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        exposure = payload.get("exposure")
        level = "CRITICAL" if isinstance(exposure, (int, float)) and abs(exposure) >= 100000 else "WATCH"
        run_id = payload.get("_run_id") if isinstance(payload.get("_run_id"), str) else "run_unknown"
        fallback = {
            "schema_version": MANAGER_OUTPUT_SCHEMA_VERSION,
            "decision": level,
            "action": "建议立刻通知值班人员 并要求 desk 提供敞口变化原因",
            "rationale": "基于当前敞口变化幅度触发预警 需要人工确认是否为真实交易导致",
            "degraded": True,
            "degraded_reason": "llm_skipped",
            "degraded_scope": ["manager_decision"],
            "plan_steps": [
                {"kind": "agent_instruction", "target_agent": "system_engineer", "action": "collect_metrics"},
                {"kind": "agent_instruction", "target_agent": "risk_analyst", "action": "search_similar_alerts"},
                {"kind": "decision", "action": "notify_oncall"},
            ],
            "commands": [
                {
                    "schema_version": "agent_command.v1",
                    "run_id": run_id,
                    "command_id": "cmd_fallback_collect_metrics",
                    "target_agent": "system_engineer",
                    "action": "collect_metrics",
                    "params": {},
                    "timeout_ms": 3000,
                    "expected_output_schema": "tool_result.v1",
                }
            ],
            "evidence": {
                "event_id": event.get("event_id"),
                "analyst_keys": list(analyst_report.keys()) if isinstance(analyst_report, dict) else [],
                "fields": ["payload.exposure"],
                "receipt_command_ids": ["cmd_fallback_collect_metrics"],
            },
        }
        result = await self._agent.ask_json(
            user_prompt=(
                "Input event:\n"
                f"{event}\n\n"
                "Analyst report:\n"
                f"{analyst_report}\n\n"
                "Make a decision and propose an action.\n"
                "If you need more evidence, propose commands for other agents to collect it."
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_manager_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_manager_output(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)


class OrchestratorAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="orchestrator",
            system_prompt=(
                "You are an orchestrator agent.\n"
                "Your job is to understand human or system intent, produce a multi step plan, and optionally propose tool commands.\n"
                "Return only valid JSON.\n"
                "Keys: schema_version, intent, plan_steps, commands, evidence, degraded, degraded_reason, degraded_scope.\n"
                "schema_version must be orchestrator_output.v1.\n"
                "intent must be an object with keys: type, confidence, slots.\n"
                "plan_steps must be a list of step objects.\n"
                "Each step must include kind and may include: step_id, target_agent, instruction, command.\n"
                "commands must be a list or null.\n"
                "If commands is a list, each item must be an AgentCommand with schema_version=agent_command.v1.\n"
                "evidence must be an object and must include at least one of: fields, receipt_command_ids, rag_hit_ids.\n"
                "degraded must be boolean.\n"
                "If degraded is true, degraded_reason must be a short string and degraded_scope must be a non empty list.\n"
                "Write Chinese text using only English punctuation.\n"
                "Never invent tool outputs.\n"
            ),
            prompt_version=PROMPT_VERSION_ORCHESTRATOR,
            policy_version=get_policy_version(),
        )

    async def orchestrate(
        self,
        *,
        task: dict[str, Any],
        context: dict[str, Any] | None = None,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        source = task.get("source") if isinstance(task.get("source"), str) else ""
        fallback = {
            "schema_version": "orchestrator_output.v1",
            "intent": {"type": "unknown", "confidence": 0.0, "slots": {}},
            "plan_steps": [
                {"kind": "delegate", "step_id": "s1", "target_agent": "system_engineer", "instruction": "分析系统层面可能原因并给出证据"},
                {"kind": "delegate", "step_id": "s2", "target_agent": "risk_analyst", "instruction": "分析业务层面影响范围并给出证据"},
                {"kind": "finalize", "step_id": "s3", "instruction": "基于两份分析做最终结论与下一步建议"},
            ],
            "commands": None,
            "evidence": {"fields": ["task.source", "task.payload.content"]},
            "degraded": True,
            "degraded_reason": "llm_skipped",
            "degraded_scope": ["orchestrator"],
        }
        result = await self._agent.ask_json(
            user_prompt=(
                "Input task:\n"
                f"{task}\n\n"
                "Context:\n"
                f"{context}\n\n"
                f"Source={source}\n"
                f"Content={content}\n\n"
                "Produce intent, a plan, and if needed propose commands for other agents or tools.\n"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_orchestrator_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_orchestrator_output(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)


class CriticAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="critic",
            system_prompt=(
                "You are a critic agent.\n"
                "Your job is to review orchestrator plans and specialist outputs for risks.\n"
                "Return only valid JSON.\n"
                "Keys: schema_version, ok, risk_level, issues, require_human_approval, suggested_fixes, evidence.\n"
                "schema_version must be critic_review.v1.\n"
                "ok must be boolean.\n"
                "risk_level must be one of LOW, MEDIUM, HIGH.\n"
                "issues must be a list of issue objects.\n"
                "Each issue must include code, message, severity.\n"
                "require_human_approval must be boolean.\n"
                "suggested_fixes must be a list of short strings.\n"
                "evidence must be an object.\n"
                "Write Chinese text using only English punctuation.\n"
                "Never invent evidence.\n"
            ),
            prompt_version=PROMPT_VERSION_CRITIC,
            policy_version=get_policy_version(),
        )

    async def review(
        self,
        *,
        task: dict[str, Any],
        orchestrator: dict[str, Any],
        engineer: dict[str, Any] | None = None,
        analyst: dict[str, Any] | None = None,
        receipts: list[dict[str, Any]] | None = None,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        fallback = {
            "schema_version": "critic_review.v1",
            "ok": False,
            "risk_level": "HIGH",
            "issues": [
                {"code": "llm_skipped", "message": "critic 未调用 llm 已触发保守策略", "severity": "HIGH"},
            ],
            "require_human_approval": True,
            "suggested_fixes": ["补齐证据链", "缩小副作用范围", "必要时要求人工确认"],
            "evidence": {"fields": ["task", "orchestrator"]},
        }
        result = await self._agent.ask_json(
            user_prompt=(
                "Input task:\n"
                f"{task}\n\n"
                "Orchestrator output:\n"
                f"{orchestrator}\n\n"
                "System engineer output:\n"
                f"{engineer}\n\n"
                "Risk analyst output:\n"
                f"{analyst}\n\n"
                "Receipts:\n"
                f"{receipts}\n\n"
                "Review risks: hallucination, missing evidence, unsafe side effects, overconfidence, data privacy.\n"
                "Decide if human approval is required.\n"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_critic_review(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_critic_review(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)
