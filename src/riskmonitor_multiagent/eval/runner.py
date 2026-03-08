from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from riskmonitor_multiagent.eval.case_schema import BenchmarkCase
from riskmonitor_multiagent.eval.metrics import summarize_benchmark_records
from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow


def _resolve_config(config: dict[str, Any]) -> dict[str, Any]:
    """用环境变量补全 config 中为空的 model / policy_version / prompt_version，便于 summary 可追溯."""
    out = dict(config)
    if not out.get("model"):
        try:
            from riskmonitor_multiagent import config as rm_config
            out["model"] = rm_config.get_llm_model()
        except Exception:
            out["model"] = os.getenv("LLM_MODEL", "")
    if not out.get("policy_version"):
        try:
            from riskmonitor_multiagent.governance.versions import get_policy_version
            out["policy_version"] = get_policy_version()
        except Exception:
            out["policy_version"] = os.getenv("POLICY_VERSION", "")
    if not out.get("prompt_version"):
        out["prompt_version"] = os.getenv("PROMPT_VERSION", "orchestrator_prompt.v1")
    return out


def _has_evidence_refs(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    refs = (
        evidence.get("fields"),
        evidence.get("receipt_command_ids"),
        evidence.get("rag_hit_ids"),
    )
    for v in refs:
        if isinstance(v, list) and any(isinstance(x, str) and x.strip() for x in v):
            return True
    return False


def _apply_env(config: dict[str, Any]) -> tuple[list[str], dict[str, str | None]]:
    mapping = {
        "policy_version": "POLICY_VERSION",
        "model": "LLM_MODEL",
    }
    changed: list[str] = []
    before: dict[str, str | None] = {}
    for key, env_key in mapping.items():
        if key not in config or config.get(key) is None:
            continue
        before[env_key] = os.getenv(env_key)
        os.environ[env_key] = str(config.get(key))
        changed.append(env_key)

    if "hitl_auto_approve" in config and config.get("hitl_auto_approve") is not None:
        env_key = "HITL_AUTO_APPROVE"
        before[env_key] = os.getenv(env_key)
        os.environ[env_key] = "1" if bool(config.get("hitl_auto_approve")) else "0"
        changed.append(env_key)

    profile = str(config.get("budget_profile") or "").strip().lower()
    profiles: dict[str, dict[str, str]] = {
        "strict": {
            "LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT": "1200",
            "LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT": "1200",
            "LLM_RATE_LIMIT_TOKENS_PER_MIN_NON_CRITICAL": "400",
            "LLM_RATE_LIMIT_BURST_TOKENS_NON_CRITICAL": "400",
        },
        "balanced": {
            "LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT": "10000",
            "LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT": "10000",
            "LLM_RATE_LIMIT_TOKENS_PER_MIN_NON_CRITICAL": "3000",
            "LLM_RATE_LIMIT_BURST_TOKENS_NON_CRITICAL": "3000",
        },
        "loose": {
            "LLM_RATE_LIMIT_TOKENS_PER_MIN_DEFAULT": "60000",
            "LLM_RATE_LIMIT_BURST_TOKENS_DEFAULT": "60000",
            "LLM_RATE_LIMIT_TOKENS_PER_MIN_NON_CRITICAL": "8000",
            "LLM_RATE_LIMIT_BURST_TOKENS_NON_CRITICAL": "8000",
        },
    }
    budget_vars = profiles.get(profile, {})
    for env_key, value in budget_vars.items():
        before[env_key] = os.getenv(env_key)
        os.environ[env_key] = value
        changed.append(env_key)
    return changed, before


def _restore_env(changed: list[str], before: dict[str, str | None]) -> None:
    for env_key in changed:
        old = before.get(env_key)
        if old is None:
            if env_key in os.environ:
                del os.environ[env_key]
        else:
            os.environ[env_key] = old


async def run_benchmark(
    cases: list[BenchmarkCase], *, run_tag: str, config: dict[str, Any], repeats: int = 1
) -> dict[str, Any]:
    config = _resolve_config(config)
    changed, before = _apply_env(config)
    records: list[dict[str, Any]] = []
    started = time.monotonic()
    r = max(1, int(repeats))
    try:
        for rep in range(r):
            for idx, c in enumerate(cases):
                if idx > 0:
                    delay_s = float(os.getenv("EVAL_DELAY_BETWEEN_CASES_S", "0"))
                    if delay_s > 0:
                        await asyncio.sleep(delay_s)
                out = await run_orchestrator_workflow(task=c.task)
                result = out.get("result") if isinstance(out.get("result"), dict) else {}
                quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
                receipts = result.get("receipts") if isinstance(result.get("receipts"), list) else []
                artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
                approval = result.get("approval") if isinstance(result.get("approval"), dict) else {}
                governance_blocked = sum(
                    1
                    for x in receipts
                    if isinstance(x, dict) and isinstance(x.get("error"), str) and x.get("error") in {"approval_required", "rbac_denied"}
                )
                degraded_count = sum(
                    1
                    for x in (
                        result.get("intent"),
                        result.get("orchestrator_plan"),
                        result.get("orchestrator_final"),
                        result.get("critic_plan"),
                        result.get("critic_final"),
                        result.get("engineer"),
                        result.get("analyst"),
                    )
                    if isinstance(x, dict) and x.get("degraded") is True
                )
                evidence_missing_steps: list[str] = []
                for sid, a in artifacts.items():
                    if not isinstance(sid, str) or not isinstance(a, dict):
                        continue
                    output = a.get("output") if isinstance(a.get("output"), dict) else None
                    if isinstance(output, dict) and isinstance(output.get("evidence"), dict):
                        if not _has_evidence_refs(output.get("evidence")):
                            evidence_missing_steps.append(sid)
                record = {
                    "run_tag": run_tag,
                    "case_id": c.case_id,
                    "repeat_index": rep,
                    "tags": c.tags,
                    "ok": bool(out.get("ok")),
                    "latency_ms": float(out.get("latency_ms") or 0.0),
                    "run_id": result.get("run_id"),
                    "task_id": result.get("task_id"),
                    "approval": approval,
                    "quality": quality,
                    "errors": result.get("errors") if isinstance(result.get("errors"), list) else [],
                    "tokens_total": int(result.get("tokens_total", 0) or 0),
                    "governance_blocked_count": governance_blocked,
                    "degraded_count": degraded_count,
                    "approval_required": bool(approval.get("required")),
                    "evidence_missing_steps": evidence_missing_steps,
                    "config": {
                        "policy_version": config.get("policy_version"),
                        "prompt_version": config.get("prompt_version"),
                        "model": config.get("model"),
                        "hitl_auto_approve": config.get("hitl_auto_approve"),
                        "budget_profile": config.get("budget_profile"),
                    },
                }
                records.append(record)
    finally:
        _restore_env(changed, before)

    summary = summarize_benchmark_records(records)
    summary["run_tag"] = run_tag
    summary["duration_ms"] = round((time.monotonic() - started) * 1000.0, 6)
    summary["config"] = {
        "policy_version": config.get("policy_version"),
        "prompt_version": config.get("prompt_version"),
        "model": config.get("model"),
        "hitl_auto_approve": config.get("hitl_auto_approve"),
        "budget_profile": config.get("budget_profile"),
    }
    return {"records": records, "summary": summary}
