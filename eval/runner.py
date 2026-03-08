"""评估 runner：只负责调度 case、调业务接口、组 record、汇总，不感知工作流内部结构."""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from riskmonitor_multiagent.orchestration.eval_adapter import workflow_output_to_eval_record
from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow

from eval.case_schema import BenchmarkCase
from eval.metrics import summarize_benchmark_records


def _resolve_config(config: dict[str, Any]) -> dict[str, Any]:
    """用环境变量补全 config 中为空的 model / policy_version / prompt_version."""
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


def _apply_env(config: dict[str, Any]) -> tuple[list[str], dict[str, str | None]]:
    changed: list[str] = []
    before: dict[str, str | None] = {}
    for key, env_key in (("policy_version", "POLICY_VERSION"), ("model", "LLM_MODEL")):
        if key not in config or config.get(key) is None:
            continue
        before[env_key] = os.getenv(env_key)
        os.environ[env_key] = str(config.get(key))
        changed.append(env_key)
    if config.get("hitl_auto_approve") is not None:
        env_key = "HITL_AUTO_APPROVE"
        before[env_key] = os.getenv(env_key)
        os.environ[env_key] = "1" if bool(config["hitl_auto_approve"]) else "0"
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
    for env_key, value in profiles.get(profile, {}).items():
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
                record = workflow_output_to_eval_record(
                    out, case_id=c.case_id, tags=c.tags, config=config
                )
                record["run_tag"] = run_tag
                record["repeat_index"] = rep
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
