"""评估 runner：只负责调度 case、调业务接口、组 record、汇总，不感知工作流内部结构."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from typing import Any

from riskmonitor_multiagent.orchestration.eval_adapter import workflow_output_to_eval_record
from riskmonitor_multiagent.orchestration.orchestrator_workflow import run_orchestrator_workflow

from eval.case_schema import BenchmarkCase
from eval.metrics import summarize_benchmark_records


def _print_progress(
    current: int,
    total: int,
    repeat_index: int,
    total_repeats: int,
    case_id: str,
    tags: list[str],
    elapsed_s: float,
) -> None:
    """打印进度信息."""
    percentage = (current / total) * 100
    case_tag_str = ", ".join(tags) if tags else ""
    tag_display = f" [{case_tag_str}]" if case_tag_str else ""
    
    bar_length = 40
    filled_length = int(bar_length * current // total)
    bar = "█" * filled_length + "░" * (bar_length - filled_length)
    
    if total_repeats > 1:
        repeat_info = f" (Repeat {repeat_index + 1}/{total_repeats})"
    else:
        repeat_info = ""
    
    sys.stdout.write("\r" + " " * 120 + "\r")
    sys.stdout.flush()
    
    line = (
        f"\r[{bar}] {percentage:5.1f}% | "
        f"{current}/{total} | "
        f"Case: {case_id}{tag_display}{repeat_info} | "
        f"Elapsed: {elapsed_s:.1f}s"
    )
    sys.stdout.write(line)
    sys.stdout.flush()


def _log(message: str, level: str = "INFO") -> None:
    """带时间戳的日志输出."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    sys.stdout.write(f"\n[{timestamp}] [{level}] {message}\n")
    sys.stdout.flush()


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
    
    total_cases = len(cases)
    total_runs = total_cases * r
    
    _log("=" * 80, "INFO")
    _log(f"开始评估运行: {run_tag}", "INFO")
    _log(f"配置: model={config.get('model')}, policy={config.get('policy_version')}", "INFO")
    _log(f"测试用例数: {total_cases}, 重复次数: {r}, 总运行数: {total_runs}", "INFO")
    _log("=" * 80, "INFO")
    
    success_count = 0
    failure_count = 0
    
    try:
        for rep in range(r):
            if r > 1:
                _log(f"开始第 {rep + 1}/{r} 轮重复", "INFO")
            
            for idx, c in enumerate(cases):
                current_run = rep * total_cases + idx + 1
                elapsed_s = time.monotonic() - started
                
                _print_progress(
                    current=idx + 1,
                    total=total_cases,
                    repeat_index=rep,
                    total_repeats=r,
                    case_id=c.case_id,
                    tags=c.tags,
                    elapsed_s=elapsed_s,
                )
                
                if idx > 0:
                    delay_s = float(os.getenv("EVAL_DELAY_BETWEEN_CASES_S", "0"))
                    if delay_s > 0:
                        await asyncio.sleep(delay_s)
                
                try:
                    out = await run_orchestrator_workflow(task=c.task)
                    record = workflow_output_to_eval_record(
                        out, case_id=c.case_id, tags=c.tags, config=config
                    )
                    record["run_tag"] = run_tag
                    record["repeat_index"] = rep
                    records.append(record)
                    
                    if record.get("ok"):
                        success_count += 1
                    else:
                        failure_count += 1
                        _log(f"Case {c.case_id} 失败", "WARN")
                        
                except Exception as e:
                    _log(f"Case {c.case_id} 执行异常: {e}", "ERROR")
                    failure_count += 1
                    error_record = {
                        "run_tag": run_tag,
                        "case_id": c.case_id,
                        "repeat_index": rep,
                        "tags": c.tags,
                        "ok": False,
                        "latency_ms": 0.0,
                        "errors": [str(e)],
                        "tokens_total": 0,
                        "config": config,
                    }
                    records.append(error_record)
    
    finally:
        _restore_env(changed, before)
        sys.stdout.write("\n")
        sys.stdout.flush()
    
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
    summary["stats"] = {
        "success_count": success_count,
        "failure_count": failure_count,
    }
    
    _log("=" * 80, "INFO")
    _log(f"评估完成!", "INFO")
    _log(f"成功: {success_count}, 失败: {failure_count}", "INFO")
    _log(f"总耗时: {(time.monotonic() - started):.1f}s", "INFO")
    _log("=" * 80, "INFO")
    
    return {"records": records, "summary": summary}
