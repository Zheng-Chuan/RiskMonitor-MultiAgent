"""
Agent 执行模板.

减少 5 个 Agent 角色类的重复代码，提供统一的执行框架.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from riskmonitor_multiagent.agents.base import AgentResult, BaseAgent
from riskmonitor_multiagent.utils import truncate_context


class AgentExecutor:
    """
    Agent 执行模板，减少重复代码.

    提供统一的 Agent 执行框架，包含：
    - 上下文截断
    - LLM 调用
    - 输出归一化
    - 输出验证
    - 结果封装
    """

    @staticmethod
    async def execute(
        agent: BaseAgent,
        *,
        user_prompt: str,
        fallback: dict[str, Any],
        normalize_fn: Callable[[Any], dict[str, Any]],
        validate_fn: Callable[[Any], tuple[bool, Any]],
        context: Optional[dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        governance: Optional[dict[str, Any]] = None,
        max_context_chars: int = 1200,
    ) -> AgentResult:
        """
        执行 Agent 任务.

        Args:
            agent: BaseAgent 实例
            user_prompt: 用户提示词
            fallback: 失败时的默认返回值
            normalize_fn: 输出归一化函数
            validate_fn: 输出验证函数
            context: 上下文数据
            max_tokens: 最大 Token 数
            governance: 治理参数
            max_context_chars: 上下文最大字符数

        Returns:
            AgentResult 包含输出数据和元信息
        """
        ctx_truncated = truncate_context(context, max_chars=max_context_chars) if context else None
        
        # 如果上下文不为空，添加到提示词中
        if ctx_truncated:
            user_prompt = f"{user_prompt}\n\nContext:\n{ctx_truncated}"
        
        result = await agent.ask_json(
            user_prompt=user_prompt,
            fallback=fallback,
            max_tokens=max_tokens or 512,
            governance=governance,
        )
        
        out = normalize_fn(result.output if isinstance(result.output, dict) else {})
        ok_out, _ = validate_fn(out)
        
        return AgentResult(ok=ok_out, output=out, usage=result.usage, meta=result.meta)
