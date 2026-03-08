from __future__ import annotations

import json
import logging
import os
import time
import asyncio
from dataclasses import dataclass
from typing import Any

from riskmonitor_multiagent import config
from riskmonitor_multiagent.llm import LlmClient
from riskmonitor_multiagent.llm import LLMError
from riskmonitor_multiagent.llm import extract_first_text
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.governance.llm_cost_governance import get_llm_cost_governor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResult:
    ok: bool
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        client: LlmClient | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        policy_version: str | None = None,
    ) -> None:
        self._name = name
        self._system_prompt = system_prompt
        self._client = client
        self._model = model
        self._prompt_version = prompt_version
        self._policy_version = policy_version

    async def ask_json(
        self,
        *,
        user_prompt: str,
        fallback: dict[str, Any],
        governance: dict[str, Any] | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        started = time.monotonic()
        model_label = (self._model or "").strip() or "default"
        try:
            try:
                api_key = config.get_llm_api_key().strip()
            except Exception as e:
                raise LLMError(code="MISSING_API_KEY", message=str(e)) from e
            if not api_key:
                raise LLMError(code="MISSING_API_KEY", message="LLM_API_KEY is empty")
            if os.getenv("DISABLE_LLM", "0").strip() not in {"0", "false", "False"}:
                raise LLMError(code="LLM_DISABLED", message="DISABLE_LLM is set")

            g = dict(governance) if isinstance(governance, dict) else {}
            user_id = str(g.get("user_id") or os.getenv("RM_USER_ID", "") or "unknown")
            priority = str(g.get("priority") or "default")
            est = int(max_tokens) if isinstance(max_tokens, int) else 512
            governor = get_llm_cost_governor()
            allowed, gov_meta = governor.allow(agent=self._name, user_id=user_id, priority=priority, estimated_tokens=est)
            if not allowed:
                inc_counter(
                    "rm_llm_circuit_break_total",
                    labels={"agent": self._name, "model": model_label, "priority": str(gov_meta.get("priority") or "default")},
                )
                raise LLMError(code="GOVERNANCE_BLOCKED", message=str(gov_meta))

            client = self._client or LlmClient()
            max_attempts = 3
            last_error: LLMError | None = None

            for attempt in range(max_attempts):
                try:
                    resp = await client.chat_completions(
                        messages=[
                            {"role": "system", "content": self._system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        model=self._model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    latency_ms = (time.monotonic() - started) * 1000.0
                    observe_ms("rm_llm_call", float(latency_ms), labels={"agent": self._name, "model": model_label})
                    inc_counter("rm_llm_calls_total", labels={"agent": self._name, "model": model_label})
                    if isinstance(governance, dict):
                        inc_counter("rm_llm_calls_by_user_total", labels={"agent": self._name, "model": model_label, "user": user_id, "priority": str(gov_meta.get("priority") or priority)})
                    usage = resp.get("usage") if isinstance(resp, dict) else None
                    meta = {
                        "agent": self._name,
                        "model": model_label,
                        "temperature": float(temperature),
                        "max_tokens": int(max_tokens) if isinstance(max_tokens, int) else None,
                        "prompt_version": self._prompt_version,
                        "policy_version": self._policy_version,
                        "governance": {"blocked": False, "user": user_id, "priority": str(gov_meta.get("priority") or priority), "detail": gov_meta},
                    }
                    if isinstance(usage, dict):
                        for k, metric in (
                            ("prompt_tokens", "prompt"),
                            ("completion_tokens", "completion"),
                            ("total_tokens", "total"),
                        ):
                            v = usage.get(k)
                            if isinstance(v, int) and v > 0:
                                inc_counter("rm_llm_tokens_total", labels={"agent": self._name, "model": model_label, "type": metric}, value=v)
                                inc_counter("rm_llm_tokens_by_user_total", labels={"agent": self._name, "model": model_label, "type": metric, "user": user_id, "priority": str(gov_meta.get("priority") or priority)}, value=v)
                    text = extract_first_text(resp).strip()
                    try:
                        data = json.loads(text)
                    except Exception as e:
                        raise LLMError(code="BAD_LLM_OUTPUT", message="response is not valid JSON", cause=e) from e
                    if not isinstance(data, dict):
                        raise LLMError(code="BAD_LLM_OUTPUT", message="response JSON is not an object")
                    return AgentResult(ok=True, output=data, usage=usage if isinstance(usage, dict) else None, meta=meta)
                except LLMError as e:
                    last_error = e
                    if e.code == "BAD_LLM_OUTPUT" and attempt < max_attempts - 1:
                        await asyncio.sleep(1.0 * (attempt + 1))
                        continue
                    latency_ms = (time.monotonic() - started) * 1000.0
                    observe_ms("rm_llm_call", float(latency_ms), labels={"agent": self._name, "model": model_label})
                    inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": e.code})
                    logger.warning(f"Agent {self._name} LLM error: {e}")
                    raise
            if last_error is not None:
                latency_ms = (time.monotonic() - started) * 1000.0
                observe_ms("rm_llm_call", float(latency_ms), labels={"agent": self._name, "model": model_label})
                inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": last_error.code})
                logger.warning(f"Agent {self._name} LLM error: {last_error}")
                raise last_error
        except LLMError:
            raise
        except Exception:
            latency_ms = (time.monotonic() - started) * 1000.0
            observe_ms("rm_llm_call", float(latency_ms), labels={"agent": self._name, "model": model_label})
            inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": "UNKNOWN"})
            raise
