from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from riskmonitor_multiagent import config
from riskmonitor_multiagent.llm.openrouter_client import OpenRouterClient
from riskmonitor_multiagent.llm.openrouter_client import OpenRouterError
from riskmonitor_multiagent.llm.openrouter_client import extract_first_text
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms

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
        client: OpenRouterClient | None = None,
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
        temperature: float = 0.2,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        started = time.monotonic()
        model_label = (self._model or "").strip() or "default"
        try:
            if os.getenv("DISABLE_LLM", "0").strip() not in {"0", "false", "False"} or config.get_openrouter_api_key().strip() == "":
                inc_counter("rm_llm_skipped_total", labels={"agent": self._name, "model": model_label})
                return AgentResult(
                    ok=False,
                    output=fallback,
                    usage=None,
                    meta={"agent": self._name, "model": model_label, "temperature": float(temperature), "max_tokens": int(max_tokens) if isinstance(max_tokens, int) else None, "prompt_version": self._prompt_version, "policy_version": self._policy_version},
                )
            client = self._client or OpenRouterClient()
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
            usage = resp.get("usage") if isinstance(resp, dict) else None
            meta = {
                "agent": self._name,
                "model": model_label,
                "temperature": float(temperature),
                "max_tokens": int(max_tokens) if isinstance(max_tokens, int) else None,
                "prompt_version": self._prompt_version,
                "policy_version": self._policy_version,
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
            text = extract_first_text(resp).strip()
            data = json.loads(text)
            if isinstance(data, dict):
                return AgentResult(ok=True, output=data, usage=usage if isinstance(usage, dict) else None, meta=meta)
            return AgentResult(ok=False, output=fallback, usage=usage if isinstance(usage, dict) else None, meta=meta)
        except OpenRouterError as e:
            latency_ms = (time.monotonic() - started) * 1000.0
            observe_ms("rm_llm_call", float(latency_ms), labels={"agent": self._name, "model": model_label})
            inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": e.code})
            logger.warning(f"Agent {self._name} OpenRouter error: {e}")
            return AgentResult(
                ok=False,
                output=fallback,
                usage=None,
                meta={"agent": self._name, "model": model_label, "temperature": float(temperature), "max_tokens": int(max_tokens) if isinstance(max_tokens, int) else None, "prompt_version": self._prompt_version, "policy_version": self._policy_version},
            )
        except Exception:
            latency_ms = (time.monotonic() - started) * 1000.0
            observe_ms("rm_llm_call", float(latency_ms), labels={"agent": self._name, "model": model_label})
            inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": "UNKNOWN"})
            return AgentResult(
                ok=False,
                output=fallback,
                usage=None,
                meta={"agent": self._name, "model": model_label, "temperature": float(temperature), "max_tokens": int(max_tokens) if isinstance(max_tokens, int) else None, "prompt_version": self._prompt_version, "policy_version": self._policy_version},
            )
