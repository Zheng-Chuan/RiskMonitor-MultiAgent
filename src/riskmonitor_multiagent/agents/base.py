from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from riskmonitor_multiagent.llm.openrouter_client import OpenRouterClient
from riskmonitor_multiagent.llm.openrouter_client import OpenRouterError
from riskmonitor_multiagent.llm.openrouter_client import extract_first_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResult:
    ok: bool
    output: dict[str, Any]


class BaseAgent:
    def __init__(
        self,
        *,
        name: str,
        system_prompt: str,
        client: OpenRouterClient | None = None,
        model: str | None = None,
    ) -> None:
        self._name = name
        self._system_prompt = system_prompt
        self._client = client
        self._model = model

    async def ask_json(
        self,
        *,
        user_prompt: str,
        fallback: dict[str, Any],
        temperature: float = 0.2,
        max_tokens: int | None = 512,
    ) -> AgentResult:
        try:
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
            text = extract_first_text(resp).strip()
            data = json.loads(text)
            if isinstance(data, dict):
                return AgentResult(ok=True, output=data)
            return AgentResult(ok=False, output=fallback)
        except OpenRouterError as e:
            logger.warning(f"Agent {self._name} OpenRouter error: {e}")
            return AgentResult(ok=False, output=fallback)
        except Exception:
            return AgentResult(ok=False, output=fallback)

