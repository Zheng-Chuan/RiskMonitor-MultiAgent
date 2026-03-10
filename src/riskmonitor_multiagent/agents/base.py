"""
Agent 基类定义.

提供统一的 LLM 交互能力，包括:
- JSON 输出解析
- 错误重试机制
- Token 用量追踪
- 治理合规检查
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from riskmonitor_multiagent import config
from riskmonitor_multiagent.governance.llm_cost_governance import get_llm_cost_governor
from riskmonitor_multiagent.llm import LLMError, LlmClient, extract_first_text
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms
from riskmonitor_multiagent.utils import clean_llm_output

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentResult:
    """Agent 执行结果.

    Attributes:
        ok: 是否成功
        output: 输出的字典数据
        usage: Token 用量信息
        meta: 元数据（模型、温度等）
    """
    ok: bool
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class BaseAgent:
    """Agent 基类，封装 LLM 调用能力."""

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
        """
        初始化 Agent.

        Args:
            name: Agent 名称（用于指标和日志）
            system_prompt: 系统提示词
            client: 可选的 LLM 客户端实例
            model: 可选的模型名称
            prompt_version: 提示词版本
            policy_version: 策略版本
        """
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
        """
        向 LLM 发起请求并解析 JSON 响应.

        流程:
        1. 检查 API Key 和禁用标志
        2. 治理检查（配额、优先级）
        3. 调用 LLM
        4. 解析 JSON
        5. 记录指标

        Args:
            user_prompt: 用户提示词
            fallback: 失败时的默认返回值
            governance: 治理参数（user_id, priority）
            temperature: 采样温度
            max_tokens: 最大 Token 数

        Returns:
            AgentResult 包含输出数据和元信息

        Raises:
            LLMError: 当调用失败且无法恢复时
        """
        started = time.monotonic()
        model_label = (self._model or "").strip() or "default"

        try:
            # 检查 API Key
            try:
                api_key = config.get_llm_api_key().strip()
            except Exception as e:
                raise LLMError(code="MISSING_API_KEY", message=str(e)) from e

            if not api_key:
                raise LLMError(code="MISSING_API_KEY", message="LLM_API_KEY is empty")

            # 检查禁用标志
            if os.getenv("DISABLE_LLM", "0").strip() not in {"0", "false", "False"}:
                raise LLMError(code="LLM_DISABLED", message="DISABLE_LLM is set")

            # 治理检查
            gov = dict(governance) if isinstance(governance, dict) else {}
            user_id = str(gov.get("user_id") or os.getenv("RM_USER_ID", "") or "unknown")
            priority = str(gov.get("priority") or "default")
            est_tokens = int(max_tokens) if isinstance(max_tokens, int) else 512

            governor = get_llm_cost_governor()
            allowed, gov_meta = governor.allow(
                agent=self._name,
                user_id=user_id,
                priority=priority,
                estimated_tokens=est_tokens,
            )

            if not allowed:
                inc_counter(
                    "rm_llm_circuit_break_total",
                    labels={"agent": self._name, "model": model_label, "priority": priority},
                )
                raise LLMError(code="GOVERNANCE_BLOCKED", message=str(gov_meta))

            # 执行 LLM 调用（带重试）
            client = self._client or LlmClient()
            return await self._call_with_retry(
                client=client,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                model_label=model_label,
                user_id=user_id,
                priority=priority,
                gov_meta=gov_meta,
                started=started,
            )

        except LLMError:
            raise
        except Exception:
            # 记录未知错误指标
            observe_ms("rm_llm_call", self._elapsed_ms(started), labels={"agent": self._name, "model": model_label})
            inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": "UNKNOWN"})
            raise

    async def _call_with_retry(
        self,
        *,
        client: LlmClient,
        user_prompt: str,
        temperature: float,
        max_tokens: int | None,
        model_label: str,
        user_id: str,
        priority: str,
        gov_meta: dict,
        started: float,
        max_attempts: int = 3,
    ) -> AgentResult:
        """带重试机制的 LLM 调用."""
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

                # 记录成功指标
                latency = self._elapsed_ms(started)
                observe_ms("rm_llm_call", latency, labels={"agent": self._name, "model": model_label})
                inc_counter("rm_llm_calls_total", labels={"agent": self._name, "model": model_label})
                if self._prompt_version:
                    inc_counter("rm_llm_calls_by_user_total", labels={
                        "agent": self._name, "model": model_label,
                        "user": user_id, "priority": priority,
                    })

                # 解析响应
                return self._parse_response(resp, model_label, user_id, priority, gov_meta)

            except LLMError as e:
                last_error = e
                if e.code == "BAD_LLM_OUTPUT" and attempt < max_attempts - 1:
                    # JSON 解析错误时重试
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue

                # 记录错误指标并抛出
                self._record_error(model_label, e.code, started)
                raise

        if last_error:
            self._record_error(model_label, last_error.code, started)
            raise last_error

        raise LLMError(code="UNKNOWN", message="Unexpected error in retry loop")

    def _parse_response(
        self,
        resp: dict,
        model_label: str,
        user_id: str,
        priority: str,
        gov_meta: dict,
    ) -> AgentResult:
        """解析 LLM 响应为 AgentResult."""
        usage = resp.get("usage") if isinstance(resp, dict) else None

        # 记录 Token 用量
        if isinstance(usage, dict):
            for key, metric in [
                ("prompt_tokens", "prompt"),
                ("completion_tokens", "completion"),
                ("total_tokens", "total"),
            ]:
                v = usage.get(key)
                if isinstance(v, int) and v > 0:
                    inc_counter("rm_llm_tokens_total", labels={
                        "agent": self._name, "model": model_label, "type": metric,
                    }, value=v)
                    inc_counter("rm_llm_tokens_by_user_total", labels={
                        "agent": self._name, "model": model_label,
                        "type": metric, "user": user_id, "priority": priority,
                    }, value=v)

        # 提取文本并解析 JSON
        raw_text = extract_first_text(resp).strip()
        clean_text = clean_llm_output(raw_text)

        try:
            data = json.loads(clean_text)
        except json.JSONDecodeError as e:
            raise LLMError(
                code="BAD_LLM_OUTPUT",
                message=f"response is not valid JSON: raw={raw_text[:200]}",
                cause=e,
            ) from e

        if not isinstance(data, dict):
            raise LLMError(code="BAD_LLM_OUTPUT", message="response JSON is not an object")

        # 构建元数据
        meta = {
            "agent": self._name,
            "model": model_label,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "prompt_version": self._prompt_version,
            "policy_version": self._policy_version,
            "governance": {
                "blocked": False,
                "user": user_id,
                "priority": priority,
                "detail": gov_meta,
            },
        }

        return AgentResult(
            ok=True,
            output=data,
            usage=usage if isinstance(usage, dict) else None,
            meta=meta,
        )

    def _record_error(self, model_label: str, code: str, started: float) -> None:
        """记录错误指标."""
        observe_ms("rm_llm_call", self._elapsed_ms(started), labels={"agent": self._name, "model": model_label})
        inc_counter("rm_llm_errors_total", labels={"agent": self._name, "model": model_label, "code": code})
        logger.warning(f"Agent {self._name} LLM error: {code}")

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        """计算已耗时间（毫秒）."""
        return (time.monotonic() - started) * 1000.0

    @property
    def _temperature(self) -> float:
        """默认温度参数."""
        return 0.2

    @property
    def _max_tokens(self) -> int | None:
        """默认最大 Token 数."""
        return 512
