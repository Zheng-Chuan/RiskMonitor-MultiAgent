from __future__ import annotations

import os
import time
from typing import Any, Literal, Optional

from riskmonitor_multiagent.agents.roles import CriticAgent
from riskmonitor_multiagent.agents.roles import OrchestratorAgent
from riskmonitor_multiagent.agents.roles import RiskAnalystAgent
from riskmonitor_multiagent.agents.roles import SystemEngineerAgent
from riskmonitor_multiagent.contracts.agent_outputs import (
    normalize_critic_review,
    normalize_orchestrator_output,
    validate_critic_review,
    validate_orchestrator_output,
)
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.orchestration.context_store import FileContextStore, new_run_id
from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory

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
    task: dict[str, Any]
    run_id: str
    iter: int
    orchestrator_plan: dict[str, Any]
    critic_plan: dict[str, Any]
    approval: dict[str, Any]
    engineer: dict[str, Any]
    analyst: dict[str, Any]
    orchestrator_final: dict[str, Any]
    critic_final: dict[str, Any]
    final_output: dict[str, Any]
    errors: list[str]


def _ctx_store() -> FileContextStore:
    return FileContextStore(base_dir=os.getenv("CONTEXT_STORE_DIR"))


def _should_use_langgraph() -> bool:
    return os.getenv("ENABLE_LANGGRAPH", "1").strip() not in {"0", "false", "False"}


def _is_auto_approved() -> bool:
    return os.getenv("HITL_AUTO_APPROVE", "1").strip() not in {"0", "false", "False"}


def _node_normalize(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    run_id = state.get("run_id") or new_run_id(event_id=str(task.get("task_id") or "task"))
    store = _ctx_store()
    store.upsert(run_id=run_id, event_id=str(task.get("task_id") or "task"), patch={"task_snapshot": task})
    try:
        import asyncio

        loop = asyncio.get_running_loop()
        mem = _memory()
        mem_entry = {
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "task",
            "session_id": str(task.get("session_id") or "default"),
            "run_id": run_id,
            "content": {"text": f"source={task.get('source')} content={(task.get('payload') or {}).get('content') if isinstance(task.get('payload'), dict) else ''}"},
        }
        loop.create_task(mem.append(mem_entry))
    except Exception:
        pass
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "orchestrator_normalize"})
    return {"run_id": run_id, "iter": 0, "errors": []}


async def _node_orchestrator_plan(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = OrchestratorAgent()
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    context = {
        "phase": "plan",
        "critic": state.get("critic_plan"),
    }
    result = await agent.orchestrate(task=task, context=context)
    out = normalize_orchestrator_output(result.output if isinstance(result.output, dict) else {})
    ok_out, errors = validate_orchestrator_output(out)
    if not ok_out:
        out["schema_errors"] = errors
    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(task.get("task_id") or "task"), patch={"orchestrator_plan": out})
    try:
        mem = _memory()
        session_id = str(task.get("session_id") or "default")
        intent = out.get("intent") if isinstance(out.get("intent"), dict) else {}
        plan_steps = out.get("plan_steps") if isinstance(out.get("plan_steps"), list) else []
        step_kinds = [s.get("kind") for s in plan_steps if isinstance(s, dict) and isinstance(s.get("kind"), str)]
        text = f"intent={intent.get('type')} steps={','.join(step_kinds[:10])}"
        await mem.append(
            {
                "agent_id": "orchestrator",
                "scope": "shared",
                "kind": "plan",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": text, "intent": intent, "plan_steps": plan_steps},
            }
        )
    except Exception:
        pass
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "orchestrator_plan"})
    return {"orchestrator_plan": out}


async def _node_critic_plan(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = CriticAgent()
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    orchestrator_plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
    result = await agent.review(task=task, orchestrator=orchestrator_plan)
    out = normalize_critic_review(result.output if isinstance(result.output, dict) else {})
    ok_out, errors = validate_critic_review(out)
    if not ok_out:
        out["schema_errors"] = errors
    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(task.get("task_id") or "task"), patch={"critic_plan": out})
    require = bool(out.get("require_human_approval") is True)
    approved = True if not require else _is_auto_approved()
    approval = {"required": require, "approved": bool(approved), "reason": "critic_required" if require else None}
    store.upsert(run_id=state["run_id"], event_id=str(task.get("task_id") or "task"), patch={"approval": approval})
    try:
        mem = _memory()
        session_id = str(task.get("session_id") or "default")
        text = f"ok={out.get('ok')} risk_level={out.get('risk_level')}"
        await mem.append(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "review",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": text, "review": out},
            }
        )
    except Exception:
        pass
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "critic_plan"})
    return {"critic_plan": out, "approval": approval}


def _route_after_plan(state: _State) -> Literal["revise", "dispatch", "end"]:
    approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
    if approval.get("required") and not approval.get("approved"):
        return "end"
    critic = state.get("critic_plan") if isinstance(state.get("critic_plan"), dict) else {}
    iter_n = int(state.get("iter") or 0)
    if critic.get("ok") is True:
        return "dispatch"
    if iter_n >= 1:
        return "dispatch"
    return "revise"


def _node_iter_inc(state: _State) -> dict[str, Any]:
    n = int(state.get("iter") or 0) + 1
    return {"iter": n}


async def _node_dispatch_specialists(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
    steps = plan.get("plan_steps") if isinstance(plan.get("plan_steps"), list) else []

    engineer_instruction = ""
    analyst_instruction = ""
    for s in steps:
        if not isinstance(s, dict):
            continue
        if s.get("kind") != "delegate":
            continue
        tgt = s.get("target_agent")
        instr = s.get("instruction")
        if tgt == "system_engineer" and isinstance(instr, str):
            engineer_instruction = instr
        if tgt == "risk_analyst" and isinstance(instr, str):
            analyst_instruction = instr

    engineer_agent = SystemEngineerAgent()
    analyst_agent = RiskAnalystAgent()

    engineer_res = await engineer_agent.analyze_task(task=task, context={"instruction": engineer_instruction, "plan": plan})
    analyst_res = await analyst_agent.analyze_task(task=task, context={"instruction": analyst_instruction, "plan": plan})

    engineer_out = engineer_res.output if isinstance(engineer_res.output, dict) else {}
    analyst_out = analyst_res.output if isinstance(analyst_res.output, dict) else {}

    store = _ctx_store()
    store.upsert(
        run_id=state["run_id"],
        event_id=str(task.get("task_id") or "task"),
        patch={"engineer": engineer_out, "analyst": analyst_out},
    )
    try:
        mem = _memory()
        session_id = str(task.get("session_id") or "default")
        await mem.append(
            {
                "agent_id": "system_engineer",
                "scope": "shared",
                "kind": "analysis",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": str(engineer_out.get("summary") or engineer_out.get("reason") or ""), "output": engineer_out},
            }
        )
        await mem.append(
            {
                "agent_id": "risk_analyst",
                "scope": "shared",
                "kind": "analysis",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": str(analyst_out.get("report") or ""), "output": analyst_out},
            }
        )
    except Exception:
        pass
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "dispatch_specialists"})
    return {"engineer": engineer_out, "analyst": analyst_out}


async def _node_orchestrator_finalize(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = OrchestratorAgent()
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    context = {
        "phase": "finalize",
        "orchestrator_plan": state.get("orchestrator_plan"),
        "critic_plan": state.get("critic_plan"),
        "engineer": state.get("engineer"),
        "analyst": state.get("analyst"),
    }
    result = await agent.orchestrate(task=task, context=context)
    out = normalize_orchestrator_output(result.output if isinstance(result.output, dict) else {})
    ok_out, errors = validate_orchestrator_output(out)
    if not ok_out:
        out["schema_errors"] = errors
    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(task.get("task_id") or "task"), patch={"orchestrator_final": out})
    try:
        mem = _memory()
        session_id = str(task.get("session_id") or "default")
        intent = out.get("intent") if isinstance(out.get("intent"), dict) else {}
        text = f"final intent={intent.get('type')} degraded={out.get('degraded')}"
        await mem.append(
            {
                "agent_id": "orchestrator",
                "scope": "shared",
                "kind": "final",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": text, "output": out},
            }
        )
    except Exception:
        pass
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "orchestrator_finalize"})
    return {"orchestrator_final": out}


async def _node_critic_final(state: _State) -> dict[str, Any]:
    started = time.monotonic()
    agent = CriticAgent()
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    orchestrator_final = state.get("orchestrator_final") if isinstance(state.get("orchestrator_final"), dict) else {}
    result = await agent.review(
        task=task,
        orchestrator=orchestrator_final,
        engineer=state.get("engineer") if isinstance(state.get("engineer"), dict) else None,
        analyst=state.get("analyst") if isinstance(state.get("analyst"), dict) else None,
        receipts=None,
    )
    out = normalize_critic_review(result.output if isinstance(result.output, dict) else {})
    ok_out, errors = validate_critic_review(out)
    if not ok_out:
        out["schema_errors"] = errors
    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(task.get("task_id") or "task"), patch={"critic_final": out})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "critic_final"})
    return {"critic_final": out}


def _node_end(state: _State) -> dict[str, Any]:
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    final_output = {
        "schema_version": "orchestrator_run.v1",
        "run_id": state.get("run_id"),
        "task_id": task.get("task_id"),
        "task": task,
        "orchestrator_plan": state.get("orchestrator_plan"),
        "critic_plan": state.get("critic_plan"),
        "approval": state.get("approval"),
        "engineer": state.get("engineer"),
        "analyst": state.get("analyst"),
        "orchestrator_final": state.get("orchestrator_final"),
        "critic_final": state.get("critic_final"),
        "errors": state.get("errors") or [],
    }
    store = _ctx_store()
    store.upsert(run_id=state["run_id"], event_id=str(task.get("task_id") or "task"), patch={"final_output": final_output})
    return {"final_output": final_output}


def _build_graph():
    if StateGraph is None:
        raise RuntimeError(f"langgraph_import_failed: {_LANGGRAPH_IMPORT_ERROR}")
    graph = StateGraph(_State)
    graph.add_node("normalize", _node_normalize)
    graph.add_node("orchestrator_plan", _node_orchestrator_plan)
    graph.add_node("critic_plan", _node_critic_plan)
    graph.add_node("iter_inc", _node_iter_inc)
    graph.add_node("dispatch_specialists", _node_dispatch_specialists)
    graph.add_node("orchestrator_finalize", _node_orchestrator_finalize)
    graph.add_node("critic_final", _node_critic_final)
    graph.add_node("end", _node_end)

    graph.add_edge(START, "normalize")
    graph.add_edge("normalize", "orchestrator_plan")
    graph.add_edge("orchestrator_plan", "critic_plan")
    graph.add_conditional_edges("critic_plan", _route_after_plan, {"revise": "iter_inc", "dispatch": "dispatch_specialists", "end": "end"})
    graph.add_edge("iter_inc", "orchestrator_plan")
    graph.add_edge("dispatch_specialists", "orchestrator_finalize")
    graph.add_edge("orchestrator_finalize", "critic_final")
    graph.add_edge("critic_final", "end")
    graph.add_edge("end", END)
    return graph.compile()


_COMPILED_GRAPH = None
_MEMORY = None
_MEMORY_SIG = None


def _memory() -> UnifiedMemory:
    global _MEMORY, _MEMORY_SIG  # pylint: disable=global-statement
    sig = (
        os.getenv("WORKING_MEMORY_BACKEND", "").strip(),
        os.getenv("REDIS_URL", "").strip(),
        os.getenv("LONG_TERM_MEMORY_DB_URL", "").strip(),
        os.getenv("MEMORY_SQLITE_PATH", "").strip(),
        os.getenv("CHROMA_PERSIST_DIR", "").strip(),
    )
    if _MEMORY is None or _MEMORY_SIG != sig:
        _MEMORY = UnifiedMemory()
        _MEMORY_SIG = sig
    return _MEMORY


async def run_orchestrator_workflow(*, task: dict[str, Any]) -> dict[str, Any]:
    if not _should_use_langgraph():
        return {"ok": False, "error": "langgraph_disabled"}
    global _COMPILED_GRAPH  # pylint: disable=global-statement
    try:
        inc_counter("rm_orchestrator_runs_total")
        if _COMPILED_GRAPH is None:
            _COMPILED_GRAPH = _build_graph()
        start = time.monotonic()
        out = await _COMPILED_GRAPH.ainvoke(
            {
                "task": task,
                "run_id": "",
                "iter": 0,
                "orchestrator_plan": {},
                "critic_plan": {},
                "approval": {},
                "engineer": {},
                "analyst": {},
                "orchestrator_final": {},
                "critic_final": {},
                "final_output": {},
                "errors": [],
            }
        )
        latency_ms = (time.monotonic() - start) * 1000.0
        observe_ms("rm_pipeline_total", float(latency_ms), labels={"workflow": "orchestrator_workflow"})
        final_output = out.get("final_output") if isinstance(out, dict) else None
        return {"ok": True, "latency_ms": float(latency_ms), "result": final_output}
    except Exception as e:  # pylint: disable=broad-except
        inc_counter("rm_orchestrator_errors_total", labels={"code": "EXCEPTION"})
        return {"ok": False, "error": str(e)}
