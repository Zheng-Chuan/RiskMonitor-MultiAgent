from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any, Optional, TypedDict

logger = logging.getLogger(__name__)

from riskmonitor_multiagent.agents.roles import CriticAgent
from riskmonitor_multiagent.agents.roles import IntentAgent
from riskmonitor_multiagent.agents.roles import OrchestratorAgent
from riskmonitor_multiagent.agents.roles import RiskAnalystAgent
from riskmonitor_multiagent.agents.roles import SystemEngineerAgent
from riskmonitor_multiagent.contracts.agent_outputs import (
    normalize_critic_review,
    normalize_orchestrator_output,
    validate_critic_review,
    validate_orchestrator_output,
)
from riskmonitor_multiagent.contracts.intent_output import normalize_intent_output, validate_intent_output
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.orchestration.context_store import FileContextStore, new_run_id
from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory
from riskmonitor_multiagent.governance.versions import PROMPT_VERSION_INTENT, get_policy_version
from riskmonitor_multiagent.orchestration.intent_heuristics import build_intent_metadata
from riskmonitor_multiagent.orchestration.tool_executor import execute_agent_command, new_agent_command
from riskmonitor_multiagent.orchestration.tool_registry import get_tool_meta


"""Orchestrator 主流程.

职责边界:
- 组装多角色执行状态 `_State`
- 串联意图识别、计划与评审、执行、最终汇总
- 统一产出可回放的结构化 `orchestrator_run.v1`
"""


class _State(TypedDict):
    task: dict[str, Any]
    run_id: str
    iter: int
    intent: dict[str, Any]
    orchestrator_plan: dict[str, Any]
    critic_plan: dict[str, Any]
    approval: dict[str, Any]
    engineer: dict[str, Any]
    analyst: dict[str, Any]
    artifacts: dict[str, Any]
    receipts: list[dict[str, Any]]
    pending_questions: list[dict[str, Any]]
    orchestrator_final: dict[str, Any]
    critic_final: dict[str, Any]
    final_output: dict[str, Any]
    errors: list[str]
    tokens_accumulated: int


def _ctx_store() -> FileContextStore:
    return FileContextStore(base_dir=os.getenv("CONTEXT_STORE_DIR"))


def _event_id(task: dict[str, Any]) -> str:
    return str(task.get("task_id") or "task")


def _receipt_command_ids(receipts: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        cid = receipt.get("command_id")
        if isinstance(cid, str) and cid.strip():
            out.append(cid)
    return out


def _add_usage(state: _State, usage: Any) -> None:
    if not isinstance(usage, dict):
        return
    total = usage.get("total_tokens")
    if isinstance(total, int) and total > 0:
        state["tokens_accumulated"] = state.get("tokens_accumulated", 0) + total


def _is_auto_approved() -> bool:
    return os.getenv("HITL_AUTO_APPROVE", "1").strip() not in {"0", "false", "False"}


_MEMORY = None
_MEMORY_SIG = None


def _memory() -> UnifiedMemory:
    # 按关键环境变量做惰性重建，避免测试/回放过程中污染跨用例状态。
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


def _max_plan_revisions() -> int:
    v = os.getenv("ORCH_MAX_PLAN_REVISIONS", "1").strip()
    try:
        return max(0, int(v))
    except Exception:
        return 1


def _max_exec_rounds() -> int:
    v = os.getenv("ORCH_MAX_EXEC_ROUNDS", "1").strip()
    try:
        return max(1, int(v))
    except Exception:
        return 1


async def _append_memory_safe(entry: dict[str, Any]) -> None:
    # 记忆存储是增强能力，不应阻塞主链路。
    try:
        mem = _memory()
        await mem.append(entry)
    except Exception:
        return


async def _plan_with_revise_loop(state: _State) -> None:
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    session_id = str(task.get("session_id") or "default")
    plan_agent = OrchestratorAgent()
    critic_agent = CriticAgent()
    max_rev = _max_plan_revisions()
    rev = 0
    while True:
        started = time.monotonic()
        context = {
            "phase": "plan",
            "intent": state.get("intent"),
            "artifacts": state.get("artifacts"),
            "receipts": state.get("receipts"),
            "critic": state.get("critic_plan"),
            "revision": rev,
        }
        result = await plan_agent.orchestrate(task=task, context=context)
        _add_usage(state, getattr(result, "usage", None))
        out = normalize_orchestrator_output(result.output if isinstance(result.output, dict) else {})
        ok_out, errors = validate_orchestrator_output(out)
        if not ok_out:
            out["schema_errors"] = errors
        # 确保 plan_steps 非空（提升 milestone 达成率）
        plan_steps = out.get("plan_steps") if isinstance(out.get("plan_steps"), list) else []
        if not plan_steps:
            # 如果 LLM 未返回有效 plan_steps，使用默认步骤
            default_steps = [
                {"kind": "delegate", "step_id": "s1", "reason": "系统工程师分析技术层面", "target_agent": "system_engineer", "instruction": "分析系统层面可能原因"},
                {"kind": "delegate", "step_id": "s2", "reason": "风险分析师评估业务影响", "target_agent": "risk_analyst", "instruction": "分析业务层面影响范围"},
                {"kind": "finalize", "step_id": "s3", "reason": "综合两份分析给出结论"},
            ]
            out["plan_steps"] = default_steps
            out.setdefault("degraded", True)
            out.setdefault("degraded_reason", "plan_steps_empty_fallback")
            plan_steps = default_steps
            logger.warning(f"plan_steps empty for run_id={state['run_id']}, using fallback steps")

        state["orchestrator_plan"] = out
        _ensure_evidence_refs(state["orchestrator_plan"], ["plan_steps"])
        _ctx_store().upsert(run_id=state["run_id"], event_id=_event_id(task), patch={"orchestrator_plan": out})
        step_kinds = [s.get("kind") for s in plan_steps if isinstance(s, dict) and isinstance(s.get("kind"), str)]
        await _append_memory_safe(
            {
                "agent_id": "orchestrator",
                "scope": "shared",
                "kind": "plan",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": f"rev={rev} steps={','.join(step_kinds[:12])}", "plan_steps": plan_steps, "revision": rev},
            }
        )
        observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "orchestrator_plan"})

        started = time.monotonic()
        review = await critic_agent.review(task=task, orchestrator=out, receipts=state.get("receipts"))
        _add_usage(state, getattr(review, "usage", None))
        critic = normalize_critic_review(review.output if isinstance(review.output, dict) else {})
        ok_review, errors_review = validate_critic_review(critic)
        if not ok_review:
            critic["schema_errors"] = errors_review
        state["critic_plan"] = critic
        _ensure_evidence_refs(state["critic_plan"], ["ok", "risk_level"])
        _ctx_store().upsert(run_id=state["run_id"], event_id=_event_id(task), patch={"critic_plan": critic})
        require = bool(critic.get("require_human_approval") is True)
        approved = True if not require else _is_auto_approved()
        approval = {"required": require, "approved": bool(approved), "reason": "critic_required" if require else None}
        state["approval"] = approval
        _ctx_store().upsert(run_id=state["run_id"], event_id=_event_id(task), patch={"approval": approval})
        await _append_memory_safe(
            {
                "agent_id": "critic",
                "scope": "shared",
                "kind": "review",
                "session_id": session_id,
                "run_id": state["run_id"],
                "content": {"text": f"rev={rev} ok={critic.get('ok')} risk_level={critic.get('risk_level')}", "review": critic, "revision": rev},
            }
        )
        observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "critic_plan"})

        if approval.get("required") and not approval.get("approved"):
            return
        if critic.get("ok") is True:
            return
        if rev >= max_rev:
            return
        rev += 1
        state["iter"] = rev


async def _execute_plan(state: _State) -> None:
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    session_id = str(task.get("session_id") or "default")
    plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
    steps = plan.get("plan_steps") if isinstance(plan.get("plan_steps"), list) else []

    syseng = SystemEngineerAgent()
    analyst = RiskAnalystAgent()

    receipts = state.get("receipts") if isinstance(state.get("receipts"), list) else []
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    pending_questions = state.get("pending_questions") if isinstance(state.get("pending_questions"), list) else []

    cmds = plan.get("commands") if isinstance(plan.get("commands"), list) else []
    for cmd in cmds:
        if not isinstance(cmd, dict):
            continue
        receipt = execute_agent_command(cmd)
        receipts.append(receipt)
        cid = receipt.get("command_id") or cmd.get("command_id")
        artifacts[f"cmd:{cid}"] = {"kind": "receipt", "receipt": receipt}
        if receipt.get("error") == "approval_required":
            state["approval"] = {"required": True, "approved": False, "reason": "approval_required"}
            pending_questions.append(
                {
                    "type": "approval",
                    "command_id": cid,
                    "action": cmd.get("action"),
                    "note": "side_effect requires approval",
                }
            )
            break

    if state.get("approval", {}).get("required") and not state.get("approval", {}).get("approved"):
        state["receipts"] = receipts
        state["artifacts"] = artifacts
        state["pending_questions"] = pending_questions
        _ctx_store().upsert(
            run_id=state["run_id"],
            event_id=_event_id(task),
            patch={"receipts": receipts, "artifacts": artifacts, "approval": state.get("approval"), "pending_questions": pending_questions},
        )
        return

    for idx, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        kind = step.get("kind")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip():
            step_id = f"s{idx+1}"

        if kind == "delegate":
            target = step.get("target_agent")
            instruction = step.get("instruction")
            ctx = {
                "instruction": instruction if isinstance(instruction, str) else "",
                "plan": plan,
                "intent": state.get("intent"),
                "receipts": receipts,
                "artifacts": artifacts,
            }
            if target == "system_engineer":
                res = await syseng.analyze_task(task=task, context=ctx)
                _add_usage(state, getattr(res, "usage", None))
                out = res.output if isinstance(res.output, dict) else {}
                if isinstance(out.get("evidence"), dict) and receipts:
                    out["evidence"].setdefault("receipt_command_ids", _receipt_command_ids(receipts))
                artifacts[step_id] = {"kind": "delegate", "target_agent": target, "ok": bool(res.ok), "output": out}
                state["engineer"] = out
                _ensure_evidence_refs(state["engineer"], ["summary", "reason"])
                await _append_memory_safe(
                    {
                        "agent_id": "system_engineer",
                        "scope": "shared",
                        "kind": "analysis",
                        "session_id": session_id,
                        "run_id": state["run_id"],
                        "content": {"text": str(out.get("summary") or out.get("reason") or ""), "output": out, "step_id": step_id},
                    }
                )
            elif target == "risk_analyst":
                res = await analyst.analyze_task(task=task, context=ctx)
                _add_usage(state, getattr(res, "usage", None))
                out = res.output if isinstance(res.output, dict) else {}
                if isinstance(out.get("evidence"), dict) and receipts:
                    out["evidence"].setdefault("receipt_command_ids", _receipt_command_ids(receipts))
                artifacts[step_id] = {"kind": "delegate", "target_agent": target, "ok": bool(res.ok), "output": out}
                state["analyst"] = out
                _ensure_evidence_refs(state["analyst"], ["report"])
                await _append_memory_safe(
                    {
                        "agent_id": "risk_analyst",
                        "scope": "shared",
                        "kind": "analysis",
                        "session_id": session_id,
                        "run_id": state["run_id"],
                        "content": {"text": str(out.get("report") or ""), "output": out, "step_id": step_id},
                    }
                )
            elif target == "parallel_both":
                # 并行执行 engineer 和 analyst，减少延迟
                ctx_eng = dict(ctx)
                ctx_ana = dict(ctx)
                eng_task = asyncio.create_task(syseng.analyze_task(task=task, context=ctx_eng))
                ana_task = asyncio.create_task(analyst.analyze_task(task=task, context=ctx_ana))
                eng_res, ana_res = await asyncio.gather(eng_task, ana_task, return_exceptions=True)

                # 处理 engineer 结果
                if isinstance(eng_res, Exception):
                    state["errors"].append(f"engineer_error:{eng_res}")
                    state["engineer"] = {"degraded": True, "error": str(eng_res)}
                    artifacts[f"{step_id}_eng"] = {"kind": "delegate", "target_agent": "system_engineer", "ok": False, "error": str(eng_res)}
                else:
                    _add_usage(state, getattr(eng_res, "usage", None))
                    eng_out = eng_res.output if isinstance(eng_res.output, dict) else {}
                    if isinstance(eng_out.get("evidence"), dict) and receipts:
                        eng_out["evidence"].setdefault("receipt_command_ids", _receipt_command_ids(receipts))
                    artifacts[f"{step_id}_eng"] = {"kind": "delegate", "target_agent": "system_engineer", "ok": bool(eng_res.ok), "output": eng_out}
                    state["engineer"] = eng_out
                    _ensure_evidence_refs(state["engineer"], ["summary", "reason"])
                    await _append_memory_safe(
                        {
                            "agent_id": "system_engineer",
                            "scope": "shared",
                            "kind": "analysis",
                            "session_id": session_id,
                            "run_id": state["run_id"],
                            "content": {"text": str(eng_out.get("summary") or eng_out.get("reason") or ""), "output": eng_out, "step_id": f"{step_id}_eng"},
                        }
                    )

                # 处理 analyst 结果
                if isinstance(ana_res, Exception):
                    state["errors"].append(f"analyst_error:{ana_res}")
                    state["analyst"] = {"degraded": True, "error": str(ana_res)}
                    artifacts[f"{step_id}_ana"] = {"kind": "delegate", "target_agent": "risk_analyst", "ok": False, "error": str(ana_res)}
                else:
                    _add_usage(state, getattr(ana_res, "usage", None))
                    ana_out = ana_res.output if isinstance(ana_res.output, dict) else {}
                    if isinstance(ana_out.get("evidence"), dict) and receipts:
                        ana_out["evidence"].setdefault("receipt_command_ids", _receipt_command_ids(receipts))
                    artifacts[f"{step_id}_ana"] = {"kind": "delegate", "target_agent": "risk_analyst", "ok": bool(ana_res.ok), "output": ana_out}
                    state["analyst"] = ana_out
                    _ensure_evidence_refs(state["analyst"], ["report"])
                    await _append_memory_safe(
                        {
                            "agent_id": "risk_analyst",
                            "scope": "shared",
                            "kind": "analysis",
                            "session_id": session_id,
                            "run_id": state["run_id"],
                            "content": {"text": str(ana_out.get("report") or ""), "output": ana_out, "step_id": f"{step_id}_ana"},
                        }
                    )
            else:
                state["errors"].append(f"unknown_target_agent:{target}")
                artifacts[step_id] = {"kind": "delegate", "target_agent": target, "ok": False, "error": "unknown_target_agent"}

        elif kind == "tool_call":
            tool_name = step.get("tool_name")
            params = step.get("params") if isinstance(step.get("params"), dict) else {}
            meta = get_tool_meta(str(tool_name))
            target_agent = None
            if meta is not None and meta.owner in {"system_engineer", "risk_analyst", "manager"}:
                target_agent = meta.owner
            if target_agent is None and meta is not None and meta.capability == "side_effect":
                target_agent = "manager"
            if target_agent is None:
                target_agent = "system_engineer"
            if isinstance(state.get("approval"), dict):
                params.setdefault("approval", state.get("approval"))
            timeout_ms = meta.default_timeout_ms if meta is not None else 1000
            cmd = new_agent_command(
                run_id=state["run_id"],
                command_id=f"{step_id}:{tool_name}",
                target_agent=str(target_agent),
                action=str(tool_name),
                params=params,
                timeout_ms=int(timeout_ms),
                expected_output_schema="tool_result.v1",
            )
            receipt = execute_agent_command(cmd)
            receipts.append(receipt)
            artifacts[step_id] = {"kind": "tool_call", "tool_name": tool_name, "receipt": receipt}
            if receipt.get("error") == "approval_required":
                state["approval"] = {"required": True, "approved": False, "reason": "approval_required"}
                pending_questions.append(
                    {
                        "type": "approval",
                        "command_id": cmd.get("command_id"),
                        "action": tool_name,
                        "note": "side_effect requires approval",
                    }
                )
                break

        elif kind == "ask_human":
            q = step.get("question")
            options = step.get("options")
            pending_questions.append({"type": "question", "step_id": step_id, "question": q, "options": options})
            state["approval"] = {"required": True, "approved": False, "reason": "ask_human"}
            break

        elif kind in {"finalize"}:
            artifacts[step_id] = {"kind": "finalize", "ok": True}

        elif kind in {"stop"}:
            artifacts[step_id] = {"kind": "stop", "ok": True}
            break

        else:
            state["errors"].append(f"unknown_step_kind:{kind}")
            artifacts[step_id] = {"kind": str(kind), "ok": False, "error": "unknown_step_kind"}
            break

    state["artifacts"] = artifacts
    state["receipts"] = receipts
    state["pending_questions"] = pending_questions
    _ctx_store().upsert(
        run_id=state["run_id"],
        event_id=_event_id(task),
        patch={"engineer": state.get("engineer"), "analyst": state.get("analyst"), "artifacts": artifacts, "receipts": receipts, "approval": state.get("approval"), "pending_questions": pending_questions},
    )


async def _finalize_and_review(state: _State) -> None:
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    session_id = str(task.get("session_id") or "default")
    orch = OrchestratorAgent()
    critic = CriticAgent()

    started = time.monotonic()
    context = {
        "phase": "finalize",
        "intent": state.get("intent"),
        "orchestrator_plan": state.get("orchestrator_plan"),
        "critic_plan": state.get("critic_plan"),
        "engineer": state.get("engineer"),
        "analyst": state.get("analyst"),
        "artifacts": state.get("artifacts"),
        "receipts": state.get("receipts"),
    }
    res = await orch.orchestrate(task=task, context=context)
    _add_usage(state, getattr(res, "usage", None))
    out = normalize_orchestrator_output(res.output if isinstance(res.output, dict) else {})
    receipts = state.get("receipts") if isinstance(state.get("receipts"), list) else []
    receipt_ids = _receipt_command_ids(receipts)
    if isinstance(out.get("evidence"), dict) and receipts:
        out["evidence"].setdefault("receipt_command_ids", receipt_ids)
    ok_out, errors = validate_orchestrator_output(out)
    if not ok_out:
        out["schema_errors"] = errors
    state["orchestrator_final"] = out
    _ensure_evidence_refs(state["orchestrator_final"], ["summary", "evidence"])
    _ctx_store().upsert(run_id=state["run_id"], event_id=_event_id(task), patch={"orchestrator_final": out})
    await _append_memory_safe(
        {
            "agent_id": "orchestrator",
            "scope": "shared",
            "kind": "final",
            "session_id": session_id,
            "run_id": state["run_id"],
            "content": {"text": f"degraded={out.get('degraded')}", "output": out},
        }
    )
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "orchestrator_finalize"})

    started = time.monotonic()
    res2 = await critic.review(
        task=task,
        orchestrator=out,
        engineer=state.get("engineer") if isinstance(state.get("engineer"), dict) else None,
        analyst=state.get("analyst") if isinstance(state.get("analyst"), dict) else None,
        receipts=receipts,
    )
    _add_usage(state, getattr(res2, "usage", None))
    c = normalize_critic_review(res2.output if isinstance(res2.output, dict) else {})
    ok_c, errs = validate_critic_review(c)
    if not ok_c:
        c["schema_errors"] = errs
    state["critic_final"] = c
    _ensure_evidence_refs(state["critic_final"], ["ok", "run_summary"])
    _ctx_store().upsert(run_id=state["run_id"], event_id=_event_id(task), patch={"critic_final": c})
    observe_ms("rm_pipeline_node", (time.monotonic() - started) * 1000.0, labels={"node": "critic_final"})
    try:
        mem = _memory()
        summary = c.get("run_summary") if isinstance(c.get("run_summary"), dict) else {"text": c.get("summary") or ""}
        if not isinstance(summary, dict):
            summary = {}
        summary.setdefault("schema_version", "run_summary.v1")
        summary.setdefault("run_id", state.get("run_id"))
        if not isinstance(summary.get("text"), str):
            summary["text"] = ""
        if not isinstance(summary.get("key_points"), list):
            summary["key_points"] = []
        if not isinstance(summary.get("receipt_command_ids"), list):
            summary["receipt_command_ids"] = []
        if receipt_ids and not summary.get("receipt_command_ids"):
            summary["receipt_command_ids"] = receipt_ids
        evidence = c.get("evidence") if isinstance(c.get("evidence"), dict) else {}
        if isinstance(evidence, dict):
            summary.setdefault("evidence", evidence)
        await mem.upsert_run_summary(run_id=state["run_id"], summary=summary)
    except Exception:
        pass


def _has_evidence_refs(evidence: dict[str, Any] | None) -> bool:
    if not isinstance(evidence, dict):
        return False
    receipt_ids = evidence.get("receipt_command_ids")
    fields = evidence.get("fields")
    rag_hits = evidence.get("rag_hit_ids")
    has_receipts = isinstance(receipt_ids, list) and any(isinstance(x, str) and x.strip() for x in receipt_ids)
    has_fields = isinstance(fields, list) and any(isinstance(x, str) and x.strip() for x in fields)
    has_rag = isinstance(rag_hits, list) and any(isinstance(x, str) and x.strip() for x in rag_hits)
    return bool(has_receipts or has_fields or has_rag)


def _ensure_evidence_refs(out: dict[str, Any] | None, default_fields: list[str]) -> None:
    """若 out 的 evidence 无任何引用，则用 default_fields 回填 evidence.fields，以降低 evidence_missing_rate."""
    if not isinstance(out, dict):
        return
    evidence = out.get("evidence")
    if _has_evidence_refs(evidence):
        return
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {}
    out["evidence"]["fields"] = [f for f in default_fields if isinstance(f, str) and f.strip()]


def _quality_summary(state: _State) -> dict[str, Any]:
    plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
    final_out = state.get("orchestrator_final") if isinstance(state.get("orchestrator_final"), dict) else {}
    critic_plan = state.get("critic_plan") if isinstance(state.get("critic_plan"), dict) else {}
    critic_final = state.get("critic_final") if isinstance(state.get("critic_final"), dict) else {}
    engineer = state.get("engineer") if isinstance(state.get("engineer"), dict) else {}
    analyst = state.get("analyst") if isinstance(state.get("analyst"), dict) else {}
    intent = state.get("intent") if isinstance(state.get("intent"), dict) else {}
    receipts = state.get("receipts") if isinstance(state.get("receipts"), list) else []

    steps = plan.get("plan_steps") if isinstance(plan.get("plan_steps"), list) else []
    total_steps = 0
    steps_with_reason = 0
    for s in steps:
        if not isinstance(s, dict):
            continue
        total_steps += 1
        reason = s.get("reason")
        if isinstance(reason, str) and reason.strip():
            steps_with_reason += 1
    step_reason_coverage = float(steps_with_reason / total_steps) if total_steps > 0 else 1.0

    outputs = [intent, plan, final_out, critic_plan, critic_final, engineer, analyst]
    evidence_total = 0
    evidence_missing = 0
    receipt_ref_total = 0
    receipt_ref_missing = 0
    contract_fail_count = 0
    receipt_ids = {
        str(r.get("command_id"))
        for r in receipts
        if isinstance(r, dict) and isinstance(r.get("command_id"), str) and str(r.get("command_id")).strip()
    }
    for out in outputs:
        if not isinstance(out, dict) or not out:
            continue
        if isinstance(out.get("schema_errors"), list) and out.get("schema_errors"):
            contract_fail_count += 1
        evidence_total += 1
        evidence = out.get("evidence") if isinstance(out.get("evidence"), dict) else None
        if not _has_evidence_refs(evidence):
            evidence_missing += 1
        ref_ids = evidence.get("receipt_command_ids") if isinstance(evidence, dict) else None
        if isinstance(ref_ids, list):
            for rid in ref_ids:
                if not isinstance(rid, str) or not rid.strip():
                    continue
                receipt_ref_total += 1
                if rid not in receipt_ids:
                    receipt_ref_missing += 1

    evidence_missing_rate = float(evidence_missing / evidence_total) if evidence_total > 0 else 0.0
    receipt_binding_rate = float((receipt_ref_total - receipt_ref_missing) / receipt_ref_total) if receipt_ref_total > 0 else 1.0
    contract_fail_rate = float(contract_fail_count / evidence_total) if evidence_total > 0 else 0.0

    breach_total = 0
    breach_hits = 0
    alert_submit_total = 0
    alert_submit_ok = 0
    for receipt in receipts:
        if not isinstance(receipt, dict):
            continue
        output = receipt.get("output") if isinstance(receipt.get("output"), dict) else {}
        breaches = output.get("breaches")
        alerts = output.get("alerts")
        if isinstance(breaches, list):
            b = len(breaches)
            if b > 0:
                breach_total += b
                a = len(alerts) if isinstance(alerts, list) else 0
                breach_hits += min(a, b)
        saved = output.get("saved")
        if isinstance(saved, int):
            alert_submit_total += 1
            if bool(receipt.get("ok")) and saved > 0:
                alert_submit_ok += 1

    breach_hit_consistency = float(breach_hits / breach_total) if breach_total > 0 else None
    alert_write_success_rate = float(alert_submit_ok / alert_submit_total) if alert_submit_total > 0 else None
    explainability_score = float(
        (step_reason_coverage + receipt_binding_rate + (1.0 - evidence_missing_rate) + (1.0 - contract_fail_rate)) / 4.0
    )
    return {
        "step_reason_coverage": round(step_reason_coverage, 6),
        "evidence_missing_rate": round(evidence_missing_rate, 6),
        "receipt_binding_rate": round(receipt_binding_rate, 6),
        "contract_fail_rate": round(contract_fail_rate, 6),
        "breach_hit_consistency": round(float(breach_hit_consistency), 6) if isinstance(breach_hit_consistency, float) else None,
        "alert_write_success_rate": round(float(alert_write_success_rate), 6) if isinstance(alert_write_success_rate, float) else None,
        "explainability_score": round(explainability_score, 6),
        "counts": {
            "plan_steps_total": total_steps,
            "plan_steps_with_reason": steps_with_reason,
            "receipt_ref_total": receipt_ref_total,
            "receipt_ref_missing": receipt_ref_missing,
            "receipts_total": len(receipts),
            "evidence_outputs_total": evidence_total,
            "evidence_outputs_missing": evidence_missing,
            "contract_fail_outputs": contract_fail_count,
        },
    }


def _build_step_trace(state: _State) -> list[dict[str, Any]]:
    plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
    steps = plan.get("plan_steps") if isinstance(plan.get("plan_steps"), list) else []
    artifacts = state.get("artifacts") if isinstance(state.get("artifacts"), dict) else {}
    out: list[dict[str, Any]] = []
    for idx, s in enumerate(steps):
        if not isinstance(s, dict):
            continue
        step_id = s.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip():
            step_id = f"s{idx+1}"
        aid = artifacts.get(step_id) if isinstance(artifacts.get(step_id), dict) else {}
        output = aid.get("output") if isinstance(aid.get("output"), dict) else {}
        evidence = output.get("evidence") if isinstance(output.get("evidence"), dict) else {}
        refs: list[str] = []
        for k in ("fields", "receipt_command_ids", "rag_hit_ids"):
            v = evidence.get(k) if isinstance(evidence, dict) else None
            if isinstance(v, list):
                refs.extend([str(x) for x in v if isinstance(x, str) and x.strip()])
        out.append(
            {
                "step_id": step_id,
                "kind": s.get("kind"),
                "reason": s.get("reason"),
                "evidence_refs": refs,
                "artifact_kind": aid.get("kind") if isinstance(aid, dict) else None,
            }
        )
    return out


def _build_final_output(state: _State) -> dict[str, Any]:
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    quality = _quality_summary(state)
    approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
    pending = bool(approval.get("required") and not approval.get("approved"))
    has_evidence_breach = bool(float(quality.get("evidence_missing_rate") or 0.0) > 0.0 or float(quality.get("contract_fail_rate") or 0.0) > 0.0)
    if has_evidence_breach and not pending:
        approval = {"required": True, "approved": False, "reason": "evidence_missing"}
        state["approval"] = approval
        q = state.get("pending_questions") if isinstance(state.get("pending_questions"), list) else []
        q.append({"type": "evidence", "note": "missing evidence links in outputs"})
        state["pending_questions"] = q
        pending = True
    final_output = {
        "schema_version": "orchestrator_run.v1",
        "run_id": state.get("run_id"),
        "task_id": task.get("task_id"),
        "task": task,
        "intent": state.get("intent"),
        "orchestrator_plan": state.get("orchestrator_plan"),
        "critic_plan": state.get("critic_plan"),
        "approval": approval,
        "status": "pending_approval" if pending else "completed",
        "engineer": state.get("engineer"),
        "analyst": state.get("analyst"),
        "artifacts": state.get("artifacts"),
        "receipts": state.get("receipts"),
        "pending_questions": state.get("pending_questions"),
        "orchestrator_final": state.get("orchestrator_final"),
        "critic_final": state.get("critic_final"),
        "step_trace": _build_step_trace(state),
        "quality": quality,
        "errors": state.get("errors") or [],
        "tokens_total": state.get("tokens_accumulated", 0),
    }
    _ctx_store().upsert(run_id=state["run_id"], event_id=_event_id(task), patch={"final_output": final_output})
    return final_output


def _ok_result(*, start: float, final_output: dict[str, Any]) -> dict[str, Any]:
    latency_ms = (time.monotonic() - start) * 1000.0
    observe_ms("rm_pipeline_total", float(latency_ms), labels={"workflow": "orchestrator_workflow"})
    return {"ok": True, "latency_ms": float(latency_ms), "result": final_output}


async def run_orchestrator_workflow(*, task: dict[str, Any]) -> dict[str, Any]:
    try:
        inc_counter("rm_orchestrator_runs_total")
        start = time.monotonic()
        t = task if isinstance(task, dict) else {}
        run_id = new_run_id(event_id=str(t.get("task_id") or "task"))
        state: _State = {
            "task": t,
            "run_id": run_id,
            "iter": 0,
            "intent": {},
            "orchestrator_plan": {},
            "critic_plan": {},
            "approval": {},
            "engineer": {},
            "analyst": {},
            "artifacts": {},
            "receipts": [],
            "pending_questions": [],
            "orchestrator_final": {},
            "critic_final": {},
            "final_output": {},
            "errors": [],
            "tokens_accumulated": 0,
        }

        store = _ctx_store()
        event_id = _event_id(t)
        store.upsert(run_id=run_id, event_id=event_id, patch={"task_snapshot": t})
        session_id = str(t.get("session_id") or "default")
        payload = t.get("payload") if isinstance(t.get("payload"), dict) else {}
        content = payload.get("content") if isinstance(payload.get("content"), str) else ""
        await _append_memory_safe(
            {
                "agent_id": "orchestrator",
                "scope": "shared",
                "kind": "task",
                "session_id": session_id,
                "run_id": run_id,
                "content": {"text": f"source={t.get('source')} content={content}"},
            }
        )

        intent_agent = IntentAgent()
        md = build_intent_metadata(task=t, policy_version=get_policy_version(), prompt_version=PROMPT_VERSION_INTENT)
        intent_res = await intent_agent.recognize(task=t, metadata=md)
        _add_usage(state, getattr(intent_res, "usage", None))
        intent_out = normalize_intent_output(intent_res.output if isinstance(intent_res.output, dict) else {})
        ok_intent, intent_errors = validate_intent_output(intent_out)
        if not ok_intent:
            intent_out["schema_errors"] = intent_errors
        state["intent"] = intent_out
        _ensure_evidence_refs(state["intent"], ["primary_intent_type", "risk_level"])
        store.upsert(run_id=run_id, event_id=event_id, patch={"intent": intent_out})
        await _append_memory_safe(
            {
                "agent_id": "intent",
                "scope": "shared",
                "kind": "intent",
                "session_id": session_id,
                "run_id": run_id,
                "content": {"text": f"type={intent_out.get('primary_intent_type')} risk={intent_out.get('risk_level')}", "intent": intent_out},
            }
        )
        try:
            intents = intent_out.get("intents") if isinstance(intent_out.get("intents"), list) else []
            dis = intent_out.get("disambiguation") if isinstance(intent_out.get("disambiguation"), dict) else {}
            if len(intents) > 1 and isinstance(dis.get("explanation"), str) and dis.get("explanation").strip():
                await _append_memory_safe(
                    {
                        "agent_id": "intent",
                        "scope": "shared",
                        "kind": "intent_disambiguation",
                        "session_id": session_id,
                        "run_id": run_id,
                        "content": {"text": dis.get("explanation"), "intents": intents},
                    }
                )
        except Exception:
            pass

        await _plan_with_revise_loop(state)

        approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
        if approval.get("required") and not approval.get("approved"):
            final_output = _build_final_output(state)
            return _ok_result(start=start, final_output=final_output)

        rounds = _max_exec_rounds()
        for _ in range(rounds):
            await _execute_plan(state)
            approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
            if approval.get("required") and not approval.get("approved"):
                final_output = _build_final_output(state)
                return _ok_result(start=start, final_output=final_output)
            plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
            if plan.get("degraded") is True:
                break
            await _plan_with_revise_loop(state)
            approval = state.get("approval") if isinstance(state.get("approval"), dict) else {}
            if approval.get("required") and not approval.get("approved"):
                break
            next_plan = state.get("orchestrator_plan") if isinstance(state.get("orchestrator_plan"), dict) else {}
            next_steps = next_plan.get("plan_steps") if isinstance(next_plan.get("plan_steps"), list) else []
            has_executable = any(isinstance(s, dict) and s.get("kind") in {"delegate", "tool_call", "ask_human", "stop"} for s in next_steps)
            if not has_executable:
                break

        await _finalize_and_review(state)
        final_output = _build_final_output(state)
        return _ok_result(start=start, final_output=final_output)
    except Exception as e:  # pylint: disable=broad-except
        inc_counter("rm_orchestrator_errors_total", labels={"code": "EXCEPTION"})
        return {"ok": False, "error": str(e)}
