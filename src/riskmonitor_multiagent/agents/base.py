"""
Agent 基类定义.

提供统一的 LLM 交互能力,包括:
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
from riskmonitor_multiagent.llm.output_repair import extract_json_from_text, fix_common_json_issues
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
        meta: 元数据(模型、温度等)
    """
    ok: bool
    output: dict[str, Any]
    usage: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None


class BaseAgent:
    """Agent 基类,封装 LLM 调用能力."""

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
            name: Agent 名称(用于指标和日志)
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
        use_json_mode: bool = True,
    ) -> AgentResult:
        """
        向 LLM 发起请求并解析 JSON 响应.

        流程:
        1. 检查 API Key 和禁用标志
        2. 治理检查(配额、优先级)
        3. 调用 LLM(启用 JSON Mode)
        4. 解析 JSON
        5. 记录指标

        Args:
            user_prompt: 用户提示词
            fallback: 失败时的默认返回值
            governance: 治理参数(user_id, priority)
            temperature: 采样温度
            max_tokens: 最大 Token 数
            use_json_mode: 是否启用 JSON Mode(默认 True,强制模型输出 JSON)

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

            # 执行 LLM 调用(带重试)
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
                use_json_mode=use_json_mode,
            )

        except LLMError as e:
            if self._should_use_fallback(e):
                logger.warning(
                    "Agent %s falling back to default JSON output due to LLM error: %s",
                    self._name,
                    e.code,
                )
                return AgentResult(
                    ok=True,
                    output=dict(fallback),
                    usage=None,
                    meta={
                        "agent": self._name,
                        "model": model_label,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "prompt_version": self._prompt_version,
                        "policy_version": self._policy_version,
                        "fallback_used": True,
                        "fallback_reason": e.code,
                    },
                )
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
        use_json_mode: bool = True,
    ) -> AgentResult:
        """带重试机制的 LLM 调用(支持智能修复).
        
        重试策略:
        - 第 1 次:正常请求
        - 第 2-N 次:将错误信息反馈给 LLM,让它修复上次的输出
        - 最多重试 max_attempts 次
        
        Args:
            client: LLM 客户端
            user_prompt: 用户提示词
            temperature: 采样温度
            max_tokens: 最大 Token 数
            model_label: 模型标签
            user_id: 用户 ID
            priority: 优先级
            gov_meta: 治理元数据
            started: 开始时间
            max_attempts: 最大尝试次数
            use_json_mode: 是否启用 JSON Mode
        
        Returns:
            AgentResult 包含输出数据和元信息
        
        Raises:
            LLMError: 当所有尝试都失败时
        """
        last_error: LLMError | None = None
        last_raw_output: str | None = None  # 保存上次的原始输出
        last_error_message: str | None = None  # 保存上次的错误信息
        
        for attempt in range(max_attempts):
            try:
                # 使用 JSON Mode 强制模型输出严格 JSON
                response_format = {"type": "json_object"} if use_json_mode else None
                
                # 构建请求消息
                messages = [
                    {"role": "system", "content": self._system_prompt},
                ]
                
                # 如果是重试,添加修复提示
                if attempt == 0:
                    # 第 1 次:正常请求
                    messages.append({"role": "user", "content": user_prompt})
                else:
                    # 第 2-N 次:请求 LLM 修复上次的输出
                    repair_prompt = self._build_repair_prompt(
                        original_prompt=user_prompt,
                        last_output=last_raw_output,
                        error_message=last_error_message,
                        attempt=attempt + 1,
                        max_attempts=max_attempts,
                    )
                    messages.append({"role": "user", "content": repair_prompt})
                
                try:
                    resp = await client.chat_completions(
                        messages=messages,
                        model=self._model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=response_format,
                    )
                except TypeError as exc:
                    if "response_format" not in str(exc):
                        raise
                    # 兼容旧测试里的 fake client 签名
                    resp = await client.chat_completions(
                        messages=messages,
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
                
                # 解析响应(不捕获异常,让外层处理)
                return self._parse_response(resp, model_label, user_id, priority, gov_meta)
                
            except LLMError as e:
                if use_json_mode and self._is_json_mode_unsupported(e):
                    logger.info(
                        "Agent %s detected unsupported json mode. Retrying without response_format.",
                        self._name,
                    )
                    use_json_mode = False
                    last_error = e
                    last_error_message = str(e.message)[:500]
                    continue
                last_error = e
                
                # 保存错误信息用于下次重试
                if attempt < max_attempts - 1:
                    # 提取原始输出(如果是解析错误)
                    if e.code == "BAD_LLM_OUTPUT":
                        # 从错误信息中提取 raw output
                        import re
                        match = re.search(r'raw=(.+?)(?:\nTraceback|$)', str(e.message), re.DOTALL)
                        if match:
                            last_raw_output = match.group(1).strip()[:2000]  # 限制长度
                        last_error_message = str(e.message)[:500]
                    
                    # 等待后重试
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                
                # 最后一次尝试失败,记录错误并抛出
                self._record_error(model_label, e.code, started)
                raise
        
        # 不应该到这里,但以防万一
        if last_error:
            self._record_error(model_label, last_error.code, started)
            raise last_error
        
        raise LLMError(code="UNKNOWN", message="Unexpected error in retry loop")

    @staticmethod
    def _is_json_mode_unsupported(error: LLMError) -> bool:
        """判断上游是否不支持 JSON Mode."""
        if error.code != "UPSTREAM_BAD_STATUS":
            return False
        message = str(error.message or "").lower()
        return (
            "response_format" in message
            or "json_object" in message
            or "not supported by this model" in message
        )

    @staticmethod
    def _should_use_fallback(error: LLMError) -> bool:
        """判断是否应返回调用方提供的 fallback."""
        return error.code in {
            "BAD_LLM_OUTPUT",
            "UPSTREAM_BAD_STATUS",
            "UPSTREAM_BAD_RESPONSE",
            "UPSTREAM_TIMEOUT",
            "UPSTREAM_UNAVAILABLE",
        }
    
    def _build_repair_prompt(
        self,
        *,
        original_prompt: str,
        last_output: str | None,
        error_message: str | None,
        attempt: int,
        max_attempts: int,
    ) -> str:
        """构建修复专用的提示词.
        
        Args:
            original_prompt: 原始的用户提示词
            last_output: 上次的输出(可能格式错误)
            error_message: 错误信息
            attempt: 当前尝试次数
            max_attempts: 最大尝试次数
        
        Returns:
            修复专用的提示词
        """
        remaining = max_attempts - attempt + 1
        
        prompt = f"""你是一个专业的 JSON 修复助手.你的任务是修复上次输出中的格式错误.

## 原始任务
{original_prompt}

## 上次的输出(有格式错误)
```json
{last_output or "N/A"}
```

## 错误信息
{error_message or "JSON 解析失败"}

## 你的任务
请仔细检查上面的输出,找出 JSON 格式错误并修复它.常见问题包括:
1. 缺少逗号(,)分隔字段
2. 缺少引号(")包裹字符串
3. 多余的逗号或括号
4. 缩进不正确

## 要求
1. **只输出修复后的 JSON**,不要添加任何解释
2. 确保 JSON 格式完全正确,可以被 json.loads() 直接解析
3. 保持原始输出的内容和结构,不要修改业务逻辑
4. 这是第 {attempt} 次尝试,还剩 {remaining} 次机会

请现在输出修复后的 JSON:"""
        
        return prompt

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

        # 提取文本并解析 JSON(带自动修复)
        raw_text = extract_first_text(resp).strip()
        clean_text = clean_llm_output(raw_text)

        try:
            # 1. 尝试直接解析
            data = json.loads(clean_text)
        except json.JSONDecodeError:
            # 2. 尝试从文本中提取 JSON
            json_str = extract_json_from_text(clean_text)
            if json_str is None:
                raise LLMError(
                    code="BAD_LLM_OUTPUT",
                    message=f"response is not valid JSON and no JSON found: raw={raw_text[:200]}",
                )
            try:
                data = json.loads(json_str)
            except json.JSONDecodeError:
                # 3. 尝试修复常见问题
                fixed_json = fix_common_json_issues(json_str)
                try:
                    data = json.loads(fixed_json)
                except json.JSONDecodeError as e:
                    raise LLMError(
                        code="BAD_LLM_OUTPUT",
                        message=f"response is not valid JSON even after repair: raw={raw_text[:200]}",
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
        """计算已耗时间(毫秒)."""
        return (time.monotonic() - started) * 1000.0

    @property
    def _temperature(self) -> float:
        """默认温度参数."""
        return 0.2

    @property
    def _max_tokens(self) -> int | None:
        """默认最大 Token 数."""
        return 512
