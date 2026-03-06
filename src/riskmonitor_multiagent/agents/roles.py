from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.agents.base import AgentResult
from riskmonitor_multiagent.agents.base import BaseAgent
from riskmonitor_multiagent.contracts.agent_outputs import (
    RISK_ANALYST_OUTPUT_SCHEMA_VERSION,
    SYSTEM_ENGINEER_OUTPUT_SCHEMA_VERSION,
    normalize_critic_review,
    normalize_orchestrator_output,
    normalize_risk_analyst_output,
    normalize_system_engineer_output,
    validate_critic_review,
    validate_orchestrator_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.intent_output import (
    INTENT_OUTPUT_SCHEMA_VERSION,
    normalize_intent_output,
    validate_intent_output,
)
from riskmonitor_multiagent.governance.versions import (
    PROMPT_VERSION_SYSTEM_ENGINEER,
    PROMPT_VERSION_RISK_ANALYST,
    PROMPT_VERSION_INTENT,
    PROMPT_VERSION_ORCHESTRATOR,
    PROMPT_VERSION_CRITIC,
    get_policy_version,
)
from riskmonitor_multiagent.orchestration.intent_heuristics import guess_risk_level, guess_side_effects


class SystemEngineerAgent:
    def __init__(self) -> None:
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


class IntentAgent:
    def __init__(self) -> None:
        self._agent = BaseAgent(
            name="intent",
            system_prompt=(
                "You are an intent extraction agent.\n"
                "Return only valid JSON.\n"
                "Keys: schema_version, primary_intent_type, intents, disambiguation, risk_level, permission_requirements, evidence, degraded, degraded_reason, degraded_scope.\n"
                "schema_version must be intent_output.v2.\n"
                "primary_intent_type must be a short snake_case string.\n"
                "intents must be a non-empty list.\n"
                "Each intents item must include: intent_type, slots, confidence.\n"
                "risk_level must be one of LOW, MEDIUM, HIGH.\n"
                "permission_requirements must include: side_effects(boolean), requires_human_approval(boolean), allowed_tools(list or null).\n"
                "disambiguation must include: has_multiple(boolean), explanation(string), notes(list).\n"
                "evidence must include at least one of: fields, receipt_command_ids, rag_hit_ids.\n"
                "If there are multiple possible intents, include multiple items in intents and explain the differences in disambiguation.explanation.\n"
                "Use only evidence from task and provided metadata.\n"
            ),
            prompt_version=PROMPT_VERSION_INTENT,
            policy_version=get_policy_version(),
        )

    async def recognize(
        self,
        *,
        task: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        max_tokens: int | None = 384,
    ) -> AgentResult:
        payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        side_effects = guess_side_effects(text=content)
        risk_level = guess_risk_level(text=content, side_effects=side_effects)
        primary_intent_type = "unknown"
        fallback = {
            "schema_version": INTENT_OUTPUT_SCHEMA_VERSION,
            "primary_intent_type": primary_intent_type,
            "intents": [{"intent_type": primary_intent_type, "slots": {}, "confidence": 0.2}],
            "disambiguation": {"has_multiple": False, "explanation": "", "notes": []},
            "risk_level": risk_level,
            "permission_requirements": {"side_effects": side_effects, "requires_human_approval": bool(side_effects), "allowed_tools": None},
            "evidence": {"fields": ["task.payload.content"]},
            "degraded": True,
            "degraded_reason": "llm_skipped",
            "degraded_scope": ["intent"],
        }
        result = await self._agent.ask_json(
            user_prompt=(
                "Input task:\n"
                f"{task}\n\n"
                "Metadata:\n"
                f"{metadata}\n\n"
                "Extract primary_intent_type and a list of intents with slots and confidence.\n"
            ),
            fallback=fallback,
            max_tokens=max_tokens,
        )
        out = normalize_intent_output(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_intent_output(out)
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
                "plan_steps must be a list of executable step objects.\n"
                "Each step must include kind and step_id.\n"
                "Each step must include reason as a short Chinese sentence using only English punctuation.\n"
                "Allowed step kinds: delegate, tool_call, ask_human, finalize, stop.\n"
                "If kind is delegate, keys: target_agent, instruction.\n"
                "If kind is tool_call, keys: tool_name, params.\n"
                "If kind is ask_human, keys: question, options.\n"
                "If kind is finalize, keys: instruction.\n"
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
        session_id = task.get("session_id")
        user_id = task.get("user_id")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = session_id if isinstance(session_id, str) and session_id.strip() else "unknown"
        text = content.strip()
        priority = "non_critical" if ("?" in text or "查询" in text or "query" in text.lower()) else "default"
        fallback = {
            "schema_version": "orchestrator_output.v1",
            "intent": {"type": "unknown", "confidence": 0.0, "slots": {}},
            "plan_steps": [
                {"kind": "delegate", "step_id": "s1", "reason": "先确认系统侧是否存在可观测异常", "target_agent": "system_engineer", "instruction": "分析系统层面可能原因并给出证据"},
                {"kind": "delegate", "step_id": "s2", "reason": "再评估业务影响避免只看技术视角", "target_agent": "risk_analyst", "instruction": "分析业务层面影响范围并给出证据"},
                {"kind": "finalize", "step_id": "s3", "reason": "综合双视角输出可执行结论", "instruction": "基于两份分析做最终结论与下一步建议"},
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
            governance={"user_id": user_id, "priority": priority},
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
                "Keys: schema_version, ok, risk_level, issues, require_human_approval, suggested_fixes, evidence, run_summary.\n"
                "schema_version must be critic_review.v1.\n"
                "ok must be boolean.\n"
                "risk_level must be one of LOW, MEDIUM, HIGH.\n"
                "issues must be a list of issue objects.\n"
                "Each issue must include code, message, severity.\n"
                "require_human_approval must be boolean.\n"
                "suggested_fixes must be a list of short strings.\n"
                "evidence must be an object.\n"
                "run_summary must be an object with keys: text, key_points, receipt_command_ids.\n"
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
        session_id = task.get("session_id")
        user_id = task.get("user_id")
        if not isinstance(user_id, str) or not user_id.strip():
            user_id = session_id if isinstance(session_id, str) and session_id.strip() else "unknown"
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
            "run_summary": {"text": "critic 未生成 run_summary", "key_points": [], "receipt_command_ids": []},
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
            governance={"user_id": user_id, "priority": "default"},
            max_tokens=max_tokens,
        )
        out = normalize_critic_review(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_critic_review(out)
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)
