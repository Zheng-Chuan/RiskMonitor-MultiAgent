from __future__ import annotations

import os
import time
import uuid
from typing import Any, Literal, Optional

from riskmonitor_multiagent import config
from riskmonitor_multiagent.agents.base import BaseAgent
from riskmonitor_multiagent.agents.roles import ManagerAgent, RiskAnalystAgent, SystemEngineerAgent
from riskmonitor_multiagent.contracts.agent_outputs import (
    normalize_manager_output,
    normalize_risk_analyst_output,
    normalize_system_engineer_output,
    validate_manager_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.risk_event import validate_risk_event
from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms, set_gauge
from riskmonitor_multiagent.orchestration.context_store import FileContextStore, new_run_id
from riskmonitor_multiagent.orchestration.tool_executor import RBAC_POLICY_VERSION, execute_agent_command, new_agent_command
from riskmonitor_multiagent.orchestration.tool_registry import TOOL_REGISTRY_VERSION, is_side_effect_action
from riskmonitor_multiagent.data_access import audit_repository
from riskmonitor_multiagent.governance.versions import (
    PROMPT_VERSION_MANAGER,
    PROMPT_VERSION_RISK_ANALYST,
    PROMPT_VERSION_SYSTEM_ENGINEER,
    get_policy_version,
)

try:
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict
except Exception as e:  # pylint: disable=broad-except
    END = None
    START = None
    StateGraph = None
    TypedDict = object
    _LANGGRAPH_IMPORT_ERROR = e


class _State(TypedDict):
    event: dict[str, Any]
    run_id: str
    replayed: bool
    engineer: dict[str, Any]
    observations: list[dict[str, Any]]
    facts: dict[str, Any]
    rag: dict[str, Any]
    analyst: dict[str, Any]
    manager: dict[str, Any]
    commands: list[dict[str, Any]]
    receipts: list[dict[str, Any]]
    observation_failed: bool
    approval: dict[str, Any]
    final_output: dict[str, Any]
    errors: list[str]
    rewrite_count: int
    need_rewrite: bool
    budget: dict[str, Any]
    run_meta: dict[str, Any]


def _ctx_store() -> FileContextStore:
    return FileContextStore(base_dir=os.getenv("CONTEXT_STORE_DIR"))


def _should_use_langgraph() -> bool:
    return os.getenv("ENABLE_LANGGRAPH", "1").strip() not in {"0", "false", "False"}


def _is_auto_approved() -> bool:
    return os.getenv("HITL_AUTO_APPROVE", "1").strip() not in {"0", "false", "False"}


def _judge_mode() -> str:
    return os.getenv("QUALITY_GATE_JUDGE_MODE", "rule").strip() or "rule"


def _judge_min_score() -> float:
    v = os.getenv("QUALITY_GATE_JUDGE_MIN_SCORE", "0.6").strip() or "0.6"
    try:
        return float(v)
    except Exception:
        return 0.6


def _get_token_budget() -> int:
    return int(os.getenv("TOKEN_BUDGET", "2000"))


def _get_tool_budget() -> int:
    return int(os.getenv("TOOL_BUDGET", "10"))


def _get_time_budget_ms() -> int:
    return int(os.getenv("TIME_BUDGET_MS", "15000"))


def _budget_remaining(budget: dict[str, Any], *, kind: str) -> int:
    if kind == "token":
        return int(budget.get("token_budget") or 0) - int(budget.get("token_used") or 0)
    if kind == "tool":
        return int(budget.get("tool_budget") or 0) - int(budget.get("tool_used") or 0)
    if kind == "time_ms":
        return int(budget.get("time_budget_ms") or 0) - int(budget.get("elapsed_ms") or 0)
    return 0


def _mark_budget(budget: dict[str, Any], *, exceeded_type: str, node: str, reason: str) -> dict[str, Any]:
    budget = dict(budget)
    budget["exceeded"] = True
    budget["exceeded_type"] = exceeded_type
    budget["exceeded_node"] = node
    budget["exceeded_reason"] = reason
    inc_counter("rm_budget_exceeded_total", labels={"type": exceeded_type, "node": node})
    return budget


def _refresh_budget_elapsed(budget: dict[str, Any]) -> dict[str, Any]:
    started_mono = budget.get("started_monotonic")
    if not isinstance(started_mono, (int, float)):
        return budget
    elapsed_ms = int(max(0.0, (time.monotonic() - float(started_mono)) * 1000.0))
    budget = dict(budget)
    budget["elapsed_ms"] = elapsed_ms
    return budget


def _budget_snapshot_for_ctx(budget: dict[str, Any]) -> dict[str, Any]:
    budget = _refresh_budget_elapsed(budget)
    return {
        "token_budget": int(budget.get("token_budget") or 0),
        "token_used": int(budget.get("token_used") or 0),
        "tool_budget": int(budget.get("tool_budget") or 0),
        "tool_used": int(budget.get("tool_used") or 0),
        "time_budget_ms": int(budget.get("time_budget_ms") or 0),
        "elapsed_ms": int(budget.get("elapsed_ms") or 0),
        "exceeded": bool(budget.get("exceeded") is True),
        "exceeded_type": budget.get("exceeded_type"),
        "exceeded_node": budget.get("exceeded_node"),
        "exceeded_reason": budget.get("exceeded_reason"),
    }


def _rule_judge_analyst(*, event: dict[str, Any], analyst: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    desk = payload.get("desk")
    exposure = payload.get("exposure")

    key_facts = analyst.get("key_facts") if isinstance(analyst.get("key_facts"), dict) else {}
    evidence = analyst.get("evidence") if isinstance(analyst.get("evidence"), dict) else {}
    confidence = analyst.get("confidence")

    reasons: list[str] = []
    score = 1.0

    if not isinstance(key_facts, dict) or len(key_facts.keys()) == 0:
        reasons.append("key_facts_empty")
        score -= 0.4
    else:
        if key_facts.get("desk") is None and isinstance(desk, str) and desk:
            reasons.append("key_facts_missing_desk")
            score -= 0.2
        if key_facts.get("exposure") is None and isinstance(exposure, (int, float)):
            reasons.append("key_facts_missing_exposure")
            score -= 0.2

    if not isinstance(evidence, dict) or len(evidence.keys()) == 0:
        reasons.append("missing_evidence")
        score -= 0.4

    if isinstance(confidence, (int, float)) and float(confidence) < 0.4:
        reasons.append("confidence_too_low")
        score -= 0.4

    score = max(0.0, min(1.0, float(score)))
    ok = score >= _judge_min_score()
    return {"schema_version": "quality_judge.v1", "mode": "rule", "ok": bool(ok), "score": float(score), "reasons": reasons}


async def _llm_judge_analyst(*, run_id: str, event: dict[str, Any], analyst: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    fallback = _rule_judge_analyst(event=event, analyst=analyst)
    agent = BaseAgent(
        name="quality_judge",
        system_prompt=(
            "You are a strict evaluation judge for an AI risk analyst output.\n"
            "Return only valid JSON.\n"
            "Keys: schema_version, mode, ok, score, reasons.\n"
            "schema_version must be quality_judge.v1.\n"
            "mode must be llm.\n"
            "ok must be boolean.\n"
            "score must be a number between 0 and 1.\n"
            "reasons must be a list of short snake_case strings.\n"
            "Judge only based on the provided event, analyst output and context.\n"
            "Never invent evidence.\n"
        ),
        prompt_version="quality_judge_prompt.v1",
        policy_version=get_policy_version(),
    )
    result = await agent.ask_json(
        user_prompt=(
            "Event:\n"
            f"{event}\n\n"
            "Analyst output:\n"
            f"{analyst}\n\n"
            "Context:\n"
            f"{context}\n\n"
            "Evaluate if the analyst output is actionable, grounded and complete.\n"
            f"Minimum score threshold: {_judge_min_score()}.\n"
        ),
        fallback=fallback,
        max_tokens=256,
    )
    out = dict(result.output) if isinstance(result.output, dict) else dict(fallback)
    out.setdefault("schema_version", "quality_judge.v1")
    out["mode"] = "llm"
    if not isinstance(out.get("ok"), bool):
        out["ok"] = bool(fallback.get("ok") is True)
    if not isinstance(out.get("score"), (int, float)):
        out["score"] = float(fallback.get("score") or 0.0)
    if not isinstance(out.get("reasons"), list):
        out["reasons"] = list(fallback.get("reasons") or [])
    store = _ctx_store()
    store.upsert(run_id=run_id, event_id=str(event.get("event_id") or "unknown"), patch={"llm_meta_quality_judge": result.meta or {}})
    return out



def _node_normalize(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    event = state["event"]
    ok, errors = validate_risk_event(event)
    budget = {
        "token_budget": _get_token_budget(),
        "token_used": 0,
        "tool_budget": _get_tool_budget(),
        "tool_used": 0,
        "time_budget_ms": _get_time_budget_ms(),
        "elapsed_ms": 0,
        "started_ms": int(time.time() * 1000),
        "started_monotonic": float(time.monotonic()),
    }
    run_meta = {
        "policy_version": get_policy_version(),
        "tool_registry_version": TOOL_REGISTRY_VERSION,
        "rbac_policy_version": RBAC_POLICY_VERSION,
        "prompt_versions": {
            "system_engineer": PROMPT_VERSION_SYSTEM_ENGINEER,
            "risk_analyst": PROMPT_VERSION_RISK_ANALYST,
            "manager": PROMPT_VERSION_MANAGER,
        },
        "enable_langgraph": _should_use_langgraph(),
        "hitl_auto_approve": _is_auto_approved(),
    }
    run_id = state.get("run_id") or new_run_id(event_id=str(event.get("event_id") or "unknown"))

    store = _ctx_store()
    store.upsert(
        run_id=run_id,
        event_id=str(event.get("event_id") or "unknown"),
        patch={"event_snapshot": event, "budget": _budget_snapshot_for_ctx(budget), "run_meta": run_meta},
    )

    replayed_final = store.get_final_by_event_id(event_id=str(event.get("event_id") or ""))
    if replayed_final is not None:
        inc_counter("rm_state_machine_replay_total")
        store.upsert(run_id=run_id, event_id=str(event.get("event_id") or "unknown"), patch={"final_output": replayed_final})
        observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "normalize"})
        return {
            "run_id": run_id,
            "replayed": True,
            "final_output": replayed_final,
            "errors": ["replayed"],
            "budget": budget,
            "run_meta": run_meta,
        }

    if not ok:
        inc_counter("rm_state_machine_invalid_event_total")
        store.upsert(run_id=run_id, event_id=str(event.get("event_id") or "unknown"), patch={"errors": errors})
        observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "normalize"})
        return {"run_id": run_id, "errors": errors, "replayed": False}

    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "normalize"})
    return {"run_id": run_id, "errors": [], "replayed": False, "budget": budget, "run_meta": run_meta}


def _route_after_normalize(state: _State) -> Literal["end", "retrieve_context"]:
    if state.get("replayed"):
        return "end"
    if state.get("errors"):
        return "end"
    return "retrieve_context"


async def _node_engineer_check(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = SystemEngineerAgent()
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    budget = _refresh_budget_elapsed(budget)
    result = await agent.analyze(
        event=state["event"],
        context={
            "facts": state.get("facts"),
            "observations": state.get("observations"),
            "receipts": state.get("receipts"),
            "budget": _budget_snapshot_for_ctx(budget),
        },
    )
    out = result.output if isinstance(result.output, dict) else {}
    ok_out, errors = validate_system_engineer_output(out)
    if not ok_out:
        out["schema_errors"] = errors
    evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
    evidence.setdefault("run_id", state.get("run_id"))
    out["evidence"] = evidence

    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(state["event"].get("event_id") or "unknown"), patch={"engineer": out})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "engineer_check"})
    return {"engineer": out}


def _route_after_engineer(state: _State) -> Literal["end", "risk_analyst"]:
    engineer = state.get("engineer") or {}
    if engineer.get("system_issue") is True:
        return "end"
    return "risk_analyst"


def _node_retrieve_context(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    run_id = state["run_id"]
    event = state["event"]
    event_id = str(event.get("event_id") or "unknown")
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    desk = payload.get("desk") if isinstance(payload.get("desk"), str) else ""
    source_meta = payload.get("source_payload_meta") if isinstance(payload.get("source_payload_meta"), dict) else {}
    message_ts_ms = source_meta.get("message_ts_ms")

    observations: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    budget = _refresh_budget_elapsed(budget)

    if _budget_remaining(budget, kind="time_ms") <= 0:
        budget = _mark_budget(budget, exceeded_type="time", node="retrieve_context", reason="time_budget_exceeded")
        facts = {"desk": desk, "event_id": event_id, "required_observations_ok": False, "budget": _budget_snapshot_for_ctx(budget)}
        store = _ctx_store()
        store.upsert(run_id=run_id, event_id=event_id, patch={"facts": facts, "budget": _budget_snapshot_for_ctx(budget), "observation_failed": True})
        return {"observations": [], "receipts": [], "rag": {"query": "", "hits": None, "memory_hits": []}, "facts": facts, "observation_failed": True, "budget": budget}
    if _budget_remaining(budget, kind="tool") <= 0:
        budget = _mark_budget(budget, exceeded_type="tool", node="retrieve_context", reason="tool_budget_exceeded")
        facts = {"desk": desk, "event_id": event_id, "required_observations_ok": False, "budget": _budget_snapshot_for_ctx(budget)}
        store = _ctx_store()
        store.upsert(run_id=run_id, event_id=event_id, patch={"facts": facts, "budget": _budget_snapshot_for_ctx(budget), "observation_failed": True})
        return {"observations": [], "receipts": [], "rag": {"query": "", "hits": None, "memory_hits": []}, "facts": facts, "observation_failed": True, "budget": budget}

    def _exec_tool(cmd: dict[str, Any]) -> dict[str, Any]:
        nonlocal budget
        budget = _refresh_budget_elapsed(budget)
        if _budget_remaining(budget, kind="time_ms") <= 0:
            budget = _mark_budget(budget, exceeded_type="time", node="retrieve_context", reason="time_budget_exceeded")
            return {"schema_version": "agent_receipt.v1", "run_id": run_id, "command_id": cmd.get("command_id"), "target_agent": cmd.get("target_agent"), "ok": False, "latency_ms": 0.0, "evidence": {"reason": "time_budget_exceeded"}, "artifacts": [], "error": "time_budget_exceeded", "output": None}
        if _budget_remaining(budget, kind="tool") <= 0:
            budget = _mark_budget(budget, exceeded_type="tool", node="retrieve_context", reason="tool_budget_exceeded")
            return {"schema_version": "agent_receipt.v1", "run_id": run_id, "command_id": cmd.get("command_id"), "target_agent": cmd.get("target_agent"), "ok": False, "latency_ms": 0.0, "evidence": {"reason": "tool_budget_exceeded"}, "artifacts": [], "error": "tool_budget_exceeded", "output": None}
        budget["tool_used"] = int(budget.get("tool_used") or 0) + 1
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="tool")), labels={"type": "tool"})
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="time_ms")), labels={"type": "time_ms"})
        return execute_agent_command(cmd)

    cmd1 = new_agent_command(
        run_id=run_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        target_agent="system_engineer",
        action="collect_metrics",
        params={},
        timeout_ms=3000,
        expected_output_schema="tool_result.v1",
    )
    receipts.append(_exec_tool(cmd1))
    observations.append({"tool": "collect_metrics"})

    cmd_kafka = new_agent_command(
        run_id=run_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        target_agent="system_engineer",
        action="kafka_lag",
        params={"message_ts_ms": message_ts_ms},
        timeout_ms=1000,
        expected_output_schema="tool_result.v1",
    )
    receipts.append(_exec_tool(cmd_kafka))
    observations.append({"tool": "kafka_lag"})

    cmd2 = new_agent_command(
        run_id=run_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        target_agent="system_engineer",
        action="mysql_health",
        params={},
        timeout_ms=3000,
        expected_output_schema="tool_result.v1",
    )
    receipts.append(_exec_tool(cmd2))
    observations.append({"tool": "mysql_health"})

    cmd_chroma = new_agent_command(
        run_id=run_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        target_agent="system_engineer",
        action="chroma_health",
        params={},
        timeout_ms=3000,
        expected_output_schema="tool_result.v1",
    )
    receipts.append(_exec_tool(cmd_chroma))
    observations.append({"tool": "chroma_health"})

    query_text = f"desk={desk} signal=desk_exposure_breach"
    cmd3 = new_agent_command(
        run_id=run_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        target_agent="risk_analyst",
        action="search_similar_alerts",
        params={"query": query_text, "top_k": 5},
        timeout_ms=5000,
        expected_output_schema="tool_result.v1",
    )
    receipts.append(_exec_tool(cmd3))

    rag_hits = receipts[-1].get("output")
    memory_available = True
    memory_query_error = None
    try:
        memory_store = ChromaVectorStore(collection=config.get_chroma_memory_collection())
        memory_hits = [
            {
                "doc_id": r.doc_id,
                "similarity": r.similarity,
                "metadata": r.metadata,
                "snippet": r.document[:200],
            }
            for r in memory_store.query_alerts(query_text=query_text, top_k=3)
        ]
    except Exception as e:  # pylint: disable=broad-except
        memory_hits = []
        memory_available = False
        memory_query_error = str(e)
        observations.append({"tool": "memory_query_error", "error": str(e)})

    rag = {"query": query_text, "hits": rag_hits, "memory_hits": memory_hits}

    required_actions = {"collect_metrics", "kafka_lag", "mysql_health", "chroma_health"}
    required_receipts = [
        r
        for r in receipts
        if isinstance(r, dict)
        and r.get("schema_version") == "agent_receipt.v1"
        and isinstance(r.get("output"), dict)
        and isinstance(r.get("output", {}).get("action"), str)
        and r.get("output", {}).get("action") in required_actions
    ]
    observation_failed = any(r.get("ok") is not True for r in required_receipts)

    facts = {
        "desk": desk,
        "event_id": event_id,
        "required_observations_ok": not observation_failed,
        "memory_available": bool(memory_available),
        "memory_query_error": memory_query_error,
        "receipt_command_ids": [r.get("command_id") for r in receipts if isinstance(r, dict) and isinstance(r.get("command_id"), str)],
        "budget": _budget_snapshot_for_ctx(budget),
    }

    store = _ctx_store()
    store.upsert(
        run_id=run_id,
        event_id=event_id,
        patch={"observations": observations, "receipts": receipts, "rag": rag, "facts": facts, "observation_failed": observation_failed, "budget": _budget_snapshot_for_ctx(budget)},
    )
    for r in receipts:
        if not isinstance(r, dict):
            continue
        out = r.get("output")
        if not isinstance(out, dict) or out.get("action") != "kafka_lag":
            continue
        res = out.get("result")
        if isinstance(res, dict) and isinstance(res.get("lag_ms"), int):
            set_gauge("rm_kafka_lag_ms", float(res.get("lag_ms")))
        break
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "retrieve_context"})
    return {"observations": observations, "receipts": receipts, "rag": rag, "facts": facts, "observation_failed": observation_failed, "budget": budget}


async def _node_risk_analyst(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = RiskAnalystAgent()
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    budget = _refresh_budget_elapsed(budget)
    event = dict(state["event"])
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
    payload["_context"] = {
        "facts": state.get("facts"),
        "observations": state.get("observations"),
        "rag": state.get("rag"),
        "receipts": state.get("receipts"),
        "budget": _budget_snapshot_for_ctx(budget),
    }
    event["payload"] = payload

    if budget.get("exceeded") is True:
        out = {
            "schema_version": "risk_analyst_output.v1",
            "report": "budget exceeded, skip llm call",
            "key_facts": {"event_id": event.get("event_id")},
            "confidence": 0.0,
            "evidence": {"budget_exceeded": True, "reason": budget.get("exceeded_reason"), "type": budget.get("exceeded_type")},
        }
    elif _budget_remaining(budget, kind="time_ms") <= 0:
        budget = _mark_budget(budget, exceeded_type="time", node="risk_analyst", reason="time_budget_exceeded")
        payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        out = {
            "schema_version": "risk_analyst_output.v1",
            "report": "budget exceeded, skip llm call",
            "key_facts": {"event_id": event.get("event_id")},
            "confidence": 0.0,
            "evidence": {"budget_exceeded": True, "reason": "time_budget_exceeded"},
        }
    elif _budget_remaining(budget, kind="token") <= 0:
        budget = _mark_budget(budget, exceeded_type="token", node="risk_analyst", reason="token_budget_exceeded")
        out = {
            "schema_version": "risk_analyst_output.v1",
            "report": "budget exceeded, skip llm call",
            "key_facts": {"event_id": event.get("event_id")},
            "confidence": 0.0,
            "evidence": {"budget_exceeded": True, "reason": "token_budget_exceeded"},
        }
    else:
        remaining = _budget_remaining(budget, kind="token")
        max_tokens = int(min(512, max(16, remaining)))
        result = await agent.analyze(event=event) if max_tokens == 512 else await agent.analyze(event=event, max_tokens=max_tokens)
        if isinstance(result.usage, dict):
            used = result.usage.get("total_tokens")
            if isinstance(used, int) and used > 0:
                budget["token_used"] = int(budget.get("token_used") or 0) + int(used)
        if _budget_remaining(budget, kind="token") <= 0:
            budget = _mark_budget(budget, exceeded_type="token", node="risk_analyst", reason="token_budget_exceeded")
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="token")), labels={"type": "token"})
        out = result.output if isinstance(result.output, dict) else {}
        store = _ctx_store()
        store.upsert(run_id=state["run_id"], event_id=str(state["event"].get("event_id") or "unknown"), patch={"llm_meta_risk_analyst": result.meta or {}, "budget": _budget_snapshot_for_ctx(budget)})
    ok_out, errors = validate_risk_analyst_output(out)
    if not ok_out:
        out["schema_errors"] = errors
    evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
    evidence.setdefault("run_id", state.get("run_id"))
    evidence.setdefault("facts_ref", "facts")
    out["evidence"] = evidence

    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(state["event"].get("event_id") or "unknown"), patch={"analyst": out, "budget": _budget_snapshot_for_ctx(budget)})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "risk_analyst"})
    return {"analyst": out, "budget": budget}


async def _node_quality_gate(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    analyst = state.get("analyst") or {}
    ok, errors = validate_risk_analyst_output(analyst)
    confidence = analyst.get("confidence")
    evidence = analyst.get("evidence")

    gate_errors: list[str] = []
    if not ok:
        gate_errors.extend(errors)
    if isinstance(confidence, (int, float)) and float(confidence) < 0.4:
        gate_errors.append("confidence_too_low")
    if not isinstance(evidence, dict) or len(evidence.keys()) == 0:
        gate_errors.append("missing_evidence")

    run_id = state["run_id"]
    event = state["event"]
    judge_mode = _judge_mode()
    judge: dict[str, Any] | None = None
    if judge_mode == "llm":
        judge = await _llm_judge_analyst(
            run_id=run_id,
            event=event,
            analyst=analyst if isinstance(analyst, dict) else {},
            context={
                "facts": state.get("facts"),
                "observations": state.get("observations"),
                "rag": state.get("rag"),
                "receipts": state.get("receipts"),
            },
        )
    else:
        judge = _rule_judge_analyst(event=event, analyst=analyst if isinstance(analyst, dict) else {})
    if isinstance(judge, dict):
        score = judge.get("score")
        ok_judge = judge.get("ok")
        if not isinstance(ok_judge, bool) or ok_judge is not True:
            gate_errors.append("judge_failed")
        if isinstance(score, (int, float)) and float(score) < _judge_min_score():
            gate_errors.append("judge_score_too_low")

    rewrite_count = int(state.get("rewrite_count") or 0)
    need_rewrite = len(gate_errors) > 0 and rewrite_count < 2

    store = _ctx_store()
    store.upsert(
        run_id=run_id,
        event_id=str(event.get("event_id") or "unknown"),
        patch={"quality_gate": {"ok": not need_rewrite, "errors": gate_errors, "rewrite_count": rewrite_count, "judge": judge}},
    )

    if need_rewrite:
        inc_counter("rm_quality_gate_rewrite_total")
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "quality_gate"})
    return {"errors": gate_errors, "rewrite_count": rewrite_count, "need_rewrite": need_rewrite}


def _route_after_quality_gate(state: _State) -> Literal["rewrite", "manager"]:
    return "rewrite" if state.get("need_rewrite") else "manager"


async def _node_rewrite(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    rewrite_count = int(state.get("rewrite_count") or 0) + 1
    agent = RiskAnalystAgent()
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    budget = _refresh_budget_elapsed(budget)
    event = dict(state["event"])
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
    payload["_context"] = {
        "facts": state.get("facts"),
        "observations": state.get("observations"),
        "rag": state.get("rag"),
        "receipts": state.get("receipts"),
        "budget": _budget_snapshot_for_ctx(budget),
    }
    event["payload"] = payload

    instruction = f"Fix output contract errors: {state.get('errors')}. Return valid JSON."
    if budget.get("exceeded") is True:
        out = {
            "schema_version": "risk_analyst_output.v1",
            "report": "budget exceeded, skip llm rewrite",
            "key_facts": {"event_id": event.get("event_id")},
            "confidence": 0.0,
            "evidence": {"budget_exceeded": True, "reason": budget.get("exceeded_reason"), "type": budget.get("exceeded_type")},
        }
    elif _budget_remaining(budget, kind="time_ms") <= 0 or _budget_remaining(budget, kind="token") <= 0:
        if _budget_remaining(budget, kind="time_ms") <= 0:
            budget = _mark_budget(budget, exceeded_type="time", node="rewrite", reason="time_budget_exceeded")
            reason = "time_budget_exceeded"
        else:
            budget = _mark_budget(budget, exceeded_type="token", node="rewrite", reason="token_budget_exceeded")
            reason = "token_budget_exceeded"
        out = {
            "schema_version": "risk_analyst_output.v1",
            "report": "budget exceeded, skip llm rewrite",
            "key_facts": {"event_id": event.get("event_id")},
            "confidence": 0.0,
            "evidence": {"budget_exceeded": True, "reason": reason},
        }
    else:
        remaining = _budget_remaining(budget, kind="token")
        max_tokens = int(min(512, max(16, remaining)))
        if max_tokens == 512:
            result = await agent.analyze(event=event, extra_instruction=instruction)
        else:
            result = await agent.analyze(event=event, extra_instruction=instruction, max_tokens=max_tokens)
        if isinstance(result.usage, dict):
            used = result.usage.get("total_tokens")
            if isinstance(used, int) and used > 0:
                budget["token_used"] = int(budget.get("token_used") or 0) + int(used)
        if _budget_remaining(budget, kind="token") <= 0:
            budget = _mark_budget(budget, exceeded_type="token", node="rewrite", reason="token_budget_exceeded")
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="token")), labels={"type": "token"})
        out = result.output if isinstance(result.output, dict) else {}
        store = _ctx_store()
        store.upsert(run_id=state["run_id"], event_id=str(state["event"].get("event_id") or "unknown"), patch={"llm_meta_rewrite": result.meta or {}, "budget": _budget_snapshot_for_ctx(budget)})

    store = _ctx_store()
    store.upsert(
        run_id=state["run_id"],
        event_id=str(state["event"].get("event_id") or "unknown"),
        patch={"analyst": out, "rewrite_count": rewrite_count, "budget": _budget_snapshot_for_ctx(budget)},
    )
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "rewrite"})
    return {"analyst": out, "rewrite_count": rewrite_count, "budget": budget}


async def _node_manager(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = ManagerAgent()
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    budget = _refresh_budget_elapsed(budget)
    event = dict(state["event"])
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
    payload["_run_id"] = state["run_id"]
    payload["_context"] = {
        "facts": state.get("facts"),
        "observations": state.get("observations"),
        "rag": state.get("rag"),
        "receipts": state.get("receipts"),
        "budget": _budget_snapshot_for_ctx(budget),
    }
    event["payload"] = payload
    analyst_report = state.get("analyst") or {}
    if budget.get("exceeded") is True:
        out = {
            "schema_version": "manager_output.v1",
            "decision": "WATCH",
            "action": "budget exceeded, skip llm call",
            "rationale": "budget exceeded",
            "degraded": True,
            "degraded_reason": "budget_exceeded",
            "degraded_scope": ["manager_decision"],
            "plan_steps": None,
            "commands": None,
            "evidence": {"budget_exceeded": True, "reason": budget.get("exceeded_reason"), "type": budget.get("exceeded_type"), "fields": ["budget.exceeded"]},
        }
    elif _budget_remaining(budget, kind="time_ms") <= 0:
        budget = _mark_budget(budget, exceeded_type="time", node="manager", reason="time_budget_exceeded")
        out = {
            "schema_version": "manager_output.v1",
            "decision": "WATCH",
            "action": "budget exceeded, skip llm call",
            "rationale": "time budget exceeded",
            "degraded": True,
            "degraded_reason": "time_budget_exceeded",
            "degraded_scope": ["manager_decision"],
            "plan_steps": None,
            "commands": None,
            "evidence": {"budget_exceeded": True, "reason": "time_budget_exceeded", "fields": ["budget.time_ms"]},
        }
    elif _budget_remaining(budget, kind="token") <= 0:
        budget = _mark_budget(budget, exceeded_type="token", node="manager", reason="token_budget_exceeded")
        out = {
            "schema_version": "manager_output.v1",
            "decision": "WATCH",
            "action": "budget exceeded, skip llm call",
            "rationale": "token budget exceeded",
            "degraded": True,
            "degraded_reason": "token_budget_exceeded",
            "degraded_scope": ["manager_decision"],
            "plan_steps": None,
            "commands": None,
            "evidence": {"budget_exceeded": True, "reason": "token_budget_exceeded", "fields": ["budget.token"]},
        }
    else:
        remaining = _budget_remaining(budget, kind="token")
        max_tokens = int(min(512, max(16, remaining)))
        result = await agent.decide(event=event, analyst_report=analyst_report) if max_tokens == 512 else await agent.decide(event=event, analyst_report=analyst_report, max_tokens=max_tokens)
        if isinstance(result.usage, dict):
            used = result.usage.get("total_tokens")
            if isinstance(used, int) and used > 0:
                budget["token_used"] = int(budget.get("token_used") or 0) + int(used)
        if _budget_remaining(budget, kind="token") <= 0:
            budget = _mark_budget(budget, exceeded_type="token", node="manager", reason="token_budget_exceeded")
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="token")), labels={"type": "token"})
        out = result.output if isinstance(result.output, dict) else {}
        store = _ctx_store()
        store.upsert(run_id=state["run_id"], event_id=str(state["event"].get("event_id") or "unknown"), patch={"llm_meta_manager": result.meta or {}, "budget": _budget_snapshot_for_ctx(budget)})
    ok_out, errors = validate_manager_output(out)
    if not ok_out:
        out["schema_errors"] = errors
        if isinstance(out, dict):
            out["degraded"] = True
            out["degraded_reason"] = "schema_invalid"
            out["degraded_scope"] = ["manager_decision"]

    commands = out.get("commands")
    if not isinstance(commands, list):
        commands = []

    receipts = state.get("receipts") or []
    receipt_ids = [r.get("command_id") for r in receipts if isinstance(r, dict) and isinstance(r.get("command_id"), str)]
    evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
    if receipt_ids and "receipt_command_ids" not in evidence:
        evidence["receipt_command_ids"] = receipt_ids[:3]
        out["evidence"] = evidence

    if out.get("plan_steps") is None:
        out["plan_steps"] = [
            {"kind": "agent_instruction", "target_agent": "system_engineer", "action": "collect_metrics"},
            {"kind": "tool_result_ref", "receipt_command_id": receipt_ids[0] if receipt_ids else None},
            {"kind": "decision", "decision": out.get("decision")},
        ]

    store = _ctx_store()
    store.upsert(
        run_id=state["run_id"],
        event_id=str(event.get("event_id") or "unknown"),
        patch={"manager": out, "commands": commands, "budget": _budget_snapshot_for_ctx(budget)},
    )
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "manager"})
    return {"manager": out, "commands": commands, "budget": budget}


def _node_human_approval(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    event = state["event"]
    severity = event.get("severity")
    actionability = event.get("actionability")
    decision = (state.get("manager") or {}).get("decision")
    require_action = bool(severity == "CRITICAL" and actionability is True and decision == "CRITICAL")
    require_observation = bool(state.get("observation_failed") is True)
    commands = state.get("commands") or []
    require_side_effect = any(
        isinstance(c, dict) and is_side_effect_action(str(c.get("action") or "")) for c in commands
    )
    require = bool(require_action or require_observation or require_side_effect)
    approved = True if not require else _is_auto_approved()
    reason = (
        "side_effect_required"
        if require_side_effect
        else "observation_failed"
        if require_observation
        else "critical_action"
        if require_action
        else None
    )
    note = "auto_approved" if require and approved else None
    approval = {"required": require, "approved": approved, "reason": reason, "note": note}

    store = _ctx_store()
    store.upsert(
        run_id=state["run_id"],
        event_id=str(event.get("event_id") or "unknown"),
        patch={"approval": approval},
    )
    if require and not approved:
        inc_counter("rm_human_approval_required_total", labels={"reason": str(approval.get("reason") or "unknown")})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "human_approval"})
    return {"approval": approval}


def _route_after_approval(state: _State) -> Literal["execute", "end"]:
    approval = state.get("approval") or {}
    if approval.get("required") and not approval.get("approved"):
        return "end"
    return "execute"


def _node_execute(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    run_id = state["run_id"]
    event = state["event"]
    event_id = str(event.get("event_id") or "unknown")
    correlation_id = event.get("correlation_id") if isinstance(event.get("correlation_id"), str) else None
    commands = state.get("commands") or []
    receipts: list[dict[str, Any]] = list(state.get("receipts") or [])
    approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
    audit_records: list[dict[str, Any]] = []
    budget = state.get("budget") if isinstance(state.get("budget"), dict) else {}
    budget = _refresh_budget_elapsed(budget)

    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        budget = _refresh_budget_elapsed(budget)
        if _budget_remaining(budget, kind="time_ms") <= 0:
            budget = _mark_budget(budget, exceeded_type="time", node="execute", reason="time_budget_exceeded")
        if _budget_remaining(budget, kind="tool") <= 0:
            budget = _mark_budget(budget, exceeded_type="tool", node="execute", reason="tool_budget_exceeded")
        if budget.get("exceeded") is True:
            receipts.append(
                {
                    "schema_version": "agent_receipt.v1",
                    "run_id": run_id,
                    "command_id": cmd.get("command_id"),
                    "target_agent": cmd.get("target_agent"),
                    "ok": False,
                    "latency_ms": 0.0,
                    "evidence": {"reason": budget.get("exceeded_reason"), "exceeded_type": budget.get("exceeded_type")},
                    "artifacts": [],
                    "error": budget.get("exceeded_reason"),
                    "output": None,
                }
            )
            continue
        budget["tool_used"] = int(budget.get("tool_used") or 0) + 1
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="tool")), labels={"type": "tool"})
        set_gauge("rm_budget_remaining", float(_budget_remaining(budget, kind="time_ms")), labels={"type": "time_ms"})
        if "event_id" not in cmd:
            cmd = dict(cmd)
            cmd["event_id"] = event_id
        params = cmd.get("params") if isinstance(cmd.get("params"), dict) else {}
        if "_event" not in params:
            params = dict(params)
            params["_event"] = {"event_id": event_id, "correlation_id": correlation_id, "severity": event.get("severity"), "actionability": event.get("actionability")}
        if "approval" not in params:
            params = dict(params)
            params["approval"] = approval
            cmd = dict(cmd)
            cmd["params"] = params
        receipt = execute_agent_command(cmd)
        receipts.append(receipt)
        action = str(cmd.get("action") or "")
        if is_side_effect_action(action):
            approved_by = "auto" if approval.get("required") and approval.get("approved") else None
            audit_records.append(
                {
                    "audit_id": str(uuid.uuid4()),
                    "ts_ms": int(time.time() * 1000),
                    "event_id": event_id,
                    "correlation_id": correlation_id,
                    "run_id": run_id,
                    "command_id": cmd.get("command_id"),
                    "target_agent": cmd.get("target_agent"),
                    "action": action,
                    "actor": "state_machine",
                    "approved": bool(approval.get("approved")),
                    "approved_by": approved_by,
                    "approval_reason": approval.get("reason"),
                    "ok": bool(receipt.get("ok")) if isinstance(receipt, dict) else False,
                    "error": receipt.get("error") if isinstance(receipt, dict) else None,
                }
            )

    audit_db_status: dict[str, Any] = {"enabled": os.getenv("ENABLE_AUDIT_DB_WRITE", "0").strip() not in {"0", "false", "False"}, "write_ok": None, "write_error": None}
    if audit_db_status["enabled"] and audit_records:
        try:
            audit_repository.save_audit_records_batch(audit_records)
            audit_db_status["write_ok"] = True
        except Exception as e:  # pylint: disable=broad-except
            audit_db_status["write_ok"] = False
            audit_db_status["write_error"] = str(e)

    memory_status: dict[str, Any] = {
        "available": bool((state.get("facts") or {}).get("memory_available", True)),
        "query_error": (state.get("facts") or {}).get("memory_query_error"),
        "write_ok": None,
        "write_error": None,
    }

    try:
        manager = state.get("manager") or {}
        analyst = state.get("analyst") or {}
        desk = ""
        try:
            desk = (event.get("payload") or {}).get("desk") if isinstance(event.get("payload"), dict) else ""
        except Exception:
            desk = ""
        summary = f"event_id={event_id} desk={desk} decision={manager.get('decision')} action={manager.get('action')} rationale={manager.get('rationale')} analyst={analyst.get('report')}"
        memory_store = ChromaVectorStore(collection=config.get_chroma_memory_collection())
        memory_store.upsert_alert(
            alert_id=f"summary:{run_id}",
            document=summary,
            metadata={"type": "state_machine_summary", "event_id": event_id, "run_id": run_id, "desk": desk},
        )
        memory_status["write_ok"] = True
        store = _ctx_store()
        store.upsert(run_id=run_id, event_id=event_id, patch={"memory_write_ok": True})
    except Exception as e:  # pylint: disable=broad-except
        memory_status["write_ok"] = False
        memory_status["write_error"] = str(e)
        store = _ctx_store()
        store.upsert(run_id=run_id, event_id=event_id, patch={"memory_write_ok": False, "memory_write_error": str(e)})
        inc_counter("rm_memory_write_errors_total")

    final_output = {
        "run_id": run_id,
        "event_id": event_id,
        "blocked": bool(budget.get("exceeded") is True),
        "run_meta": state.get("run_meta"),
        "engineer": state.get("engineer"),
        "analyst": state.get("analyst"),
        "manager": state.get("manager"),
        "facts": state.get("facts"),
        "rag": state.get("rag"),
        "budget": _budget_snapshot_for_ctx(budget),
        "memory": memory_status,
        "receipts": receipts,
        "approval": state.get("approval"),
        "audit_records": audit_records,
        "audit_db": audit_db_status,
    }

    store = _ctx_store()
    store.upsert(run_id=run_id, event_id=event_id, patch={"final_output": final_output, "receipts": receipts, "audit_records": audit_records, "audit_db": audit_db_status, "budget": _budget_snapshot_for_ctx(budget)})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "execute"})
    return {"final_output": final_output, "receipts": receipts, "budget": budget}


def _node_end(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    event = state.get("event") or {}
    event_id = str(event.get("event_id") or "unknown")
    run_id = state.get("run_id") or new_run_id(event_id=event_id)

    if state.get("final_output"):
        return {"final_output": state["final_output"]}

    manager = state.get("manager") if isinstance(state.get("manager"), dict) else {}
    if not manager:
        manager = normalize_manager_output(
            {
                "schema_version": "manager_output.v1",
                "decision": "WATCH",
                "action": "blocked, skip decision",
                "rationale": "workflow ended early",
                "degraded": True,
                "degraded_reason": "blocked",
                "degraded_scope": ["manager_decision"],
                "plan_steps": None,
                "commands": None,
                "evidence": {"event_id": event_id, "fields": ["event.event_id"]},
            }
        )
    analyst = state.get("analyst") if isinstance(state.get("analyst"), dict) else {}
    if not analyst:
        analyst = normalize_risk_analyst_output(
            {
                "schema_version": "risk_analyst_output.v1",
                "report": "流程提前结束 已降级输出",
                "key_facts": {},
                "confidence": None,
                "evidence": {"fields": ["workflow.blocked"]},
            }
        )
    engineer = state.get("engineer") if isinstance(state.get("engineer"), dict) else {}
    if not engineer:
        engineer = normalize_system_engineer_output(
            {
                "schema_version": "system_engineer_output.v1",
                "system_issue": True,
                "reason": "workflow_ended",
                "latency_ms": None,
                "evidence": {"fields": ["workflow.blocked"]},
            }
        )
    final_output = {
        "run_id": run_id,
        "event_id": event_id,
        "blocked": True,
        "run_meta": state.get("run_meta"),
        "engineer": engineer,
        "analyst": analyst,
        "manager": manager,
        "facts": state.get("facts"),
        "rag": state.get("rag"),
        "budget": state.get("budget"),
        "memory": None,
        "receipts": state.get("receipts"),
        "approval": state.get("approval"),
        "audit_records": None,
        "audit_db": None,
        "errors": state.get("errors"),
    }
    store = _ctx_store()
    store.upsert(run_id=run_id, event_id=event_id, patch={"final_output": final_output})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "end"})
    return {"final_output": final_output}


def _build_graph():
    if StateGraph is None:
        raise RuntimeError(f"langgraph_import_failed: {_LANGGRAPH_IMPORT_ERROR}")
    graph = StateGraph(_State)
    graph.add_node("normalize", _node_normalize)
    graph.add_node("engineer_check", _node_engineer_check)
    graph.add_node("retrieve_context", _node_retrieve_context)
    graph.add_node("risk_analyst", _node_risk_analyst)
    graph.add_node("quality_gate", _node_quality_gate)
    graph.add_node("rewrite", _node_rewrite)
    graph.add_node("manager", _node_manager)
    graph.add_node("human_approval", _node_human_approval)
    graph.add_node("execute", _node_execute)
    graph.add_node("end", _node_end)

    graph.add_edge(START, "normalize")
    graph.add_conditional_edges("normalize", _route_after_normalize, {"retrieve_context": "retrieve_context", "end": "end"})
    graph.add_edge("retrieve_context", "engineer_check")
    graph.add_conditional_edges("engineer_check", _route_after_engineer, {"risk_analyst": "risk_analyst", "end": "end"})
    graph.add_edge("risk_analyst", "quality_gate")
    graph.add_conditional_edges("quality_gate", _route_after_quality_gate, {"rewrite": "rewrite", "manager": "manager"})
    graph.add_edge("rewrite", "quality_gate")
    graph.add_edge("manager", "human_approval")
    graph.add_conditional_edges("human_approval", _route_after_approval, {"execute": "execute", "end": "end"})
    graph.add_edge("execute", END)
    graph.add_edge("end", END)
    return graph.compile()


_COMPILED_GRAPH = None


async def run_state_machine(*, event: dict[str, Any]) -> dict[str, Any]:
    if not _should_use_langgraph():
        return {"ok": False, "error": "langgraph_disabled"}
    global _COMPILED_GRAPH  # pylint: disable=global-statement
    try:
        inc_counter("rm_state_machine_runs_total")
        if _COMPILED_GRAPH is None:
            _COMPILED_GRAPH = _build_graph()
        start = time.monotonic()
        out = await _COMPILED_GRAPH.ainvoke(
            {
                "event": event,
                "run_id": "",
                "replayed": False,
                "engineer": {},
                "observations": [],
                "facts": {},
                "rag": {},
                "analyst": {},
                "manager": {},
                "commands": [],
                "receipts": [],
                "observation_failed": False,
                "approval": {},
                "final_output": {},
                "errors": [],
                "rewrite_count": 0,
                "need_rewrite": False,
            }
        )
        latency_ms = (time.monotonic() - start) * 1000.0
        observe_ms("rm_pipeline_total", float(latency_ms), labels={"workflow": "state_machine"})
        final_output = out.get("final_output") if isinstance(out, dict) else None
        return {"ok": True, "latency_ms": float(latency_ms), "result": final_output}
    except Exception as e:  # pylint: disable=broad-except
        inc_counter("rm_state_machine_errors_total", labels={"code": "EXCEPTION"})
        return {"ok": False, "error": str(e)}
