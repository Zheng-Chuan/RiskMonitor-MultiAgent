from __future__ import annotations

import os
import time
import uuid
from typing import Any, Literal, Optional

from riskmonitor_multiagent import config
from riskmonitor_multiagent.agents.roles import ManagerAgent, RiskAnalystAgent, SystemEngineerAgent
from riskmonitor_multiagent.contracts.agent_outputs import (
    validate_manager_output,
    validate_risk_analyst_output,
    validate_system_engineer_output,
)
from riskmonitor_multiagent.contracts.risk_event import validate_risk_event
from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms, set_gauge
from riskmonitor_multiagent.orchestration.context_store import FileContextStore, new_run_id
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command

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


def _ctx_store() -> FileContextStore:
    return FileContextStore(base_dir=os.getenv("CONTEXT_STORE_DIR"))


def _should_use_langgraph() -> bool:
    return os.getenv("ENABLE_LANGGRAPH", "1").strip() not in {"0", "false", "False"}


def _is_auto_approved() -> bool:
    return os.getenv("HITL_AUTO_APPROVE", "1").strip() not in {"0", "false", "False"}


def _node_normalize(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    event = state["event"]
    ok, errors = validate_risk_event(event)
    run_id = state.get("run_id") or new_run_id(event_id=str(event.get("event_id") or "unknown"))

    store = _ctx_store()
    store.upsert(run_id=run_id, event_id=str(event.get("event_id") or "unknown"), patch={"event_snapshot": event})

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
        }

    if not ok:
        inc_counter("rm_state_machine_invalid_event_total")
        store.upsert(run_id=run_id, event_id=str(event.get("event_id") or "unknown"), patch={"errors": errors})
        observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "normalize"})
        return {"run_id": run_id, "errors": errors, "replayed": False}

    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "normalize"})
    return {"run_id": run_id, "errors": [], "replayed": False}


def _route_after_normalize(state: _State) -> Literal["end", "engineer_check"]:
    if state.get("replayed"):
        return "end"
    if state.get("errors"):
        return "end"
    return "engineer_check"


def _node_engineer_check(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = SystemEngineerAgent()
    result = agent.analyze(event=state["event"])
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


def _route_after_engineer(state: _State) -> Literal["end", "retrieve_context"]:
    engineer = state.get("engineer") or {}
    if engineer.get("system_issue") is True:
        return "end"
    return "retrieve_context"


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

    cmd1 = new_agent_command(
        run_id=run_id,
        command_id=f"cmd_{uuid.uuid4().hex}",
        target_agent="system_engineer",
        action="collect_metrics",
        params={},
        timeout_ms=3000,
        expected_output_schema="tool_result.v1",
    )
    receipts.append(execute_agent_command(cmd1))
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
    receipts.append(execute_agent_command(cmd_kafka))
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
    receipts.append(execute_agent_command(cmd2))
    observations.append({"tool": "mysql_health"})

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
    receipts.append(execute_agent_command(cmd3))

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

    required_actions = {"collect_metrics", "kafka_lag", "mysql_health"}
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
    }

    store = _ctx_store()
    store.upsert(
        run_id=run_id,
        event_id=event_id,
        patch={"observations": observations, "receipts": receipts, "rag": rag, "facts": facts, "observation_failed": observation_failed},
    )
    set_gauge("rm_kafka_lag_ms", float((receipts[1].get("output", {}).get("result", {}).get("lag_ms") or 0) if isinstance(receipts[1], dict) else 0.0))
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "retrieve_context"})
    return {"observations": observations, "receipts": receipts, "rag": rag, "facts": facts, "observation_failed": observation_failed}


async def _node_risk_analyst(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = RiskAnalystAgent()
    event = dict(state["event"])
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
    payload["_context"] = {
        "facts": state.get("facts"),
        "observations": state.get("observations"),
        "rag": state.get("rag"),
        "receipts": state.get("receipts"),
    }
    event["payload"] = payload

    result = await agent.analyze(event=event)
    out = result.output if isinstance(result.output, dict) else {}
    ok_out, errors = validate_risk_analyst_output(out)
    if not ok_out:
        out["schema_errors"] = errors
    evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else {}
    evidence.setdefault("run_id", state.get("run_id"))
    evidence.setdefault("facts_ref", "facts")
    out["evidence"] = evidence

    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(state["event"].get("event_id") or "unknown"), patch={"analyst": out})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "risk_analyst"})
    return {"analyst": out}


def _node_quality_gate(state: _State) -> dict[str, Any]:
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

    rewrite_count = int(state.get("rewrite_count") or 0)
    need_rewrite = len(gate_errors) > 0 and rewrite_count < 2

    store = _ctx_store()
    store.upsert(
        run_id=state["run_id"],
        event_id=str(state["event"].get("event_id") or "unknown"),
        patch={"quality_gate": {"ok": not need_rewrite, "errors": gate_errors, "rewrite_count": rewrite_count}},
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
    event = dict(state["event"])
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
    payload["_context"] = {
        "facts": state.get("facts"),
        "observations": state.get("observations"),
        "rag": state.get("rag"),
        "receipts": state.get("receipts"),
    }
    event["payload"] = payload

    instruction = f"Fix output contract errors: {state.get('errors')}. Return valid JSON."
    result = await agent.analyze(event=event, extra_instruction=instruction)
    out = result.output if isinstance(result.output, dict) else {}

    store = _ctx_store()
    store.upsert(
        run_id=state["run_id"],
        event_id=str(state["event"].get("event_id") or "unknown"),
        patch={"analyst": out, "rewrite_count": rewrite_count},
    )
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "rewrite"})
    return {"analyst": out, "rewrite_count": rewrite_count}


async def _node_manager(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = ManagerAgent()
    event = dict(state["event"])
    payload = dict(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else {}
    payload["_run_id"] = state["run_id"]
    payload["_context"] = {
        "facts": state.get("facts"),
        "observations": state.get("observations"),
        "rag": state.get("rag"),
        "receipts": state.get("receipts"),
    }
    event["payload"] = payload
    analyst_report = state.get("analyst") or {}
    result = await agent.decide(event=event, analyst_report=analyst_report)
    out = result.output if isinstance(result.output, dict) else {}
    ok_out, errors = validate_manager_output(out)
    if not ok_out:
        out["schema_errors"] = errors

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
        patch={"manager": out, "commands": commands},
    )
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "manager"})
    return {"manager": out, "commands": commands}


def _node_human_approval(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    event = state["event"]
    severity = event.get("severity")
    actionability = event.get("actionability")
    decision = (state.get("manager") or {}).get("decision")
    require_action = bool(severity == "CRITICAL" and actionability is True and decision == "CRITICAL")
    require_observation = bool(state.get("observation_failed") is True)
    require = bool(require_action or require_observation)
    approved = True if not require else _is_auto_approved()
    approval = {"required": require, "approved": approved, "reason": "observation_failed" if require_observation else "critical_action" if require_action else None}

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
    commands = state.get("commands") or []
    receipts: list[dict[str, Any]] = list(state.get("receipts") or [])

    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        receipt = execute_agent_command(cmd)
        receipts.append(receipt)

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
        "engineer": state.get("engineer"),
        "analyst": state.get("analyst"),
        "manager": state.get("manager"),
        "facts": state.get("facts"),
        "rag": state.get("rag"),
        "memory": memory_status,
        "receipts": receipts,
        "approval": state.get("approval"),
    }

    store = _ctx_store()
    store.upsert(run_id=run_id, event_id=event_id, patch={"final_output": final_output, "receipts": receipts})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "execute"})
    return {"final_output": final_output, "receipts": receipts}


def _node_end(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    event = state.get("event") or {}
    event_id = str(event.get("event_id") or "unknown")
    run_id = state.get("run_id") or new_run_id(event_id=event_id)

    if state.get("final_output"):
        return {"final_output": state["final_output"]}

    final_output = {
        "run_id": run_id,
        "event_id": event_id,
        "blocked": True,
        "engineer": state.get("engineer"),
        "errors": state.get("errors"),
        "approval": state.get("approval"),
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
    graph.add_conditional_edges("normalize", _route_after_normalize, {"engineer_check": "engineer_check", "end": "end"})
    graph.add_conditional_edges("engineer_check", _route_after_engineer, {"retrieve_context": "retrieve_context", "end": "end"})
    graph.add_edge("retrieve_context", "risk_analyst")
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
