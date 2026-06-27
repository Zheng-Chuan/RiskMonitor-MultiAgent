"""三层 prompt 分离构建器.

将 prompt 拆分为三个层级, 实现 prefix-cache 友好的构建策略:

1. stable_tier (稳定层): Agent 角色定义, 工具索引, 行为规则
   - 版本管理 (stable_version), 尽量前缀稳定
   - cacheable: True

2. context_tier (上下文层): 当前 Skills, 项目规则, 日级刷新
   - 按日期戳管理 (context_date)
   - cacheable: True

3. volatile_tier (易变层): 记忆快照, 当前事件, 每次刷新
   - 版本号: 时间戳 (精确到毫秒)
   - cacheable: False

设计约束:
1. 三层分离是可选增强, 不破坏现有 prompt 构建逻辑
2. token 估算使用简单启发式: 中文 1.5 字/token, 英文 4 字符/token
3. 不修改现有 prompt 文件内容
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Any

# tiktoken 可选导入: 用于精确 token 计算
try:
    import tiktoken as _tiktoken
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _tiktoken = None  # type: ignore[assignment]
    _TIKTOKEN_AVAILABLE = False

# 中文字符的 Unicode 范围正则 (与 context_compressor 保持一致)
_CJK_PATTERN = re.compile(
    r"[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"
    r"\U00020000-\U0002a6df\U0002a700-\U0002b73f"
    r"\U0002b740-\U0002b81f\U0002b820-\U0002ceaf]"
)

# 每条消息的元数据开销 (估算 role 等结构开销, 与 context_compressor 保持一致)
_PER_MESSAGE_OVERHEAD = 4


@dataclass
class PromptTier:
    """prompt 层级.

    Attributes:
        tier_name: 层级名称 ("stable" | "context" | "volatile")
        content: 文本内容
        version: 版本标识
        token_estimate: 估算 token 数
        cacheable: 是否可缓存
    """

    tier_name: str
    content: str
    version: str
    token_estimate: int
    cacheable: bool


class TieredPromptBuilder:
    """三层 prompt 构建器.

    - stable_tier: Agent 角色定义, 工具索引, 行为规则 (版本管理, 尽量前缀稳定)
    - context_tier: 当前 Skills, 项目规则, 日级刷新 (按日期戳管理)
    - volatile_tier: 记忆快照, 当前事件, 每次刷新 (不缓存)
    """

    def __init__(
        self,
        *,
        stable_version: str = "v1",
        context_date: str | None = None,
    ) -> None:
        """初始化三层 prompt 构建器.

        Args:
            stable_version: stable tier 的版本号
            context_date: context tier 的日期戳 (YYYY-MM-DD), 默认当天
        """
        self._stable_version = stable_version
        if context_date is not None:
            self._context_date = context_date
        else:
            self._context_date = date.today().isoformat()

    @property
    def stable_version(self) -> str:
        """stable tier 的版本号."""
        return self._stable_version

    @property
    def context_date(self) -> str:
        """context tier 的日期戳."""
        return self._context_date

    # ------------------------------------------------------------------ #
    # 三层构建
    # ------------------------------------------------------------------ #
    def build_stable_tier(
        self,
        *,
        agent_role: str,
        tools_index: list[dict],
        behavior_rules: list[str],
    ) -> PromptTier:
        """构建稳定层.

        包含 Agent 角色定义、工具索引、行为规则.
        版本号: stable_version, 可缓存.

        Args:
            agent_role: Agent 角色定义文本
            tools_index: 工具索引列表
            behavior_rules: 行为规则列表

        Returns:
            PromptTier (stable, cacheable=True)
        """
        lines: list[str] = []

        # Agent 角色定义 (放在最前面, 保证前缀稳定)
        lines.append(f"[Agent Role]\n{agent_role}")

        # 工具索引
        lines.append(f"\n[Tools Index]\n{json.dumps(tools_index, ensure_ascii=False, indent=2)}")

        # 行为规则
        rules_text = "\n".join(f"- {rule}" for rule in behavior_rules)
        lines.append(f"\n[Behavior Rules]\n{rules_text}")

        content = "\n".join(lines)
        token_estimate = self.estimate_tier_tokens_text(content)

        return PromptTier(
            tier_name="stable",
            content=content,
            version=self._stable_version,
            token_estimate=token_estimate,
            cacheable=True,
        )

    def build_context_tier(
        self,
        *,
        skills: list[dict],
        project_rules: list[str],
        memory_summary: dict[str, Any] | None = None,
    ) -> PromptTier:
        """构建上下文层.

        包含当前 Skills、项目规则、记忆摘要.
        版本号: context_date (日期戳), 可缓存.

        Args:
            skills: 当前可用的 Skill 列表
            project_rules: 项目规则
            memory_summary: 记忆摘要 (可选)

        Returns:
            PromptTier (context, cacheable=True)
        """
        lines: list[str] = []

        # Skills
        lines.append(f"[Skills]\n{json.dumps(skills, ensure_ascii=False, indent=2)}")

        # 项目规则
        rules_text = "\n".join(f"- {rule}" for rule in project_rules)
        lines.append(f"\n[Project Rules]\n{rules_text}")

        # 记忆摘要 (可选)
        if memory_summary is not None:
            lines.append(
                f"\n[Memory Summary]\n{json.dumps(memory_summary, ensure_ascii=False, indent=2)}"
            )

        content = "\n".join(lines)
        token_estimate = self.estimate_tier_tokens_text(content)

        return PromptTier(
            tier_name="context",
            content=content,
            version=self._context_date,
            token_estimate=token_estimate,
            cacheable=True,
        )

    def build_volatile_tier(
        self,
        *,
        current_event: dict[str, Any] | None,
        task: dict[str, Any],
        react_history: list[dict[str, Any]] | None = None,
    ) -> PromptTier:
        """构建易变层.

        包含当前事件、当前任务、ReAct 历史.
        版本号: 时间戳 (精确到毫秒), 不可缓存.

        Args:
            current_event: 当前事件
            task: 当前任务
            react_history: ReAct 历史

        Returns:
            PromptTier (volatile, cacheable=False)
        """
        lines: list[str] = []

        # 当前事件 (可选)
        if current_event is not None:
            lines.append(
                f"[Current Event]\n{json.dumps(current_event, ensure_ascii=False, indent=2)}"
            )
        else:
            lines.append("[Current Event]\nNone")

        # 当前任务
        lines.append(f"\n[Task]\n{json.dumps(task, ensure_ascii=False, indent=2)}")

        # ReAct 历史 (可选)
        if react_history is not None:
            lines.append(
                f"\n[ReAct History]\n{json.dumps(react_history, ensure_ascii=False, indent=2)}"
            )
        else:
            lines.append("\n[ReAct History]\n[]")

        content = "\n".join(lines)
        token_estimate = self.estimate_tier_tokens_text(content)

        # 版本号: 毫秒级时间戳
        version = str(time.time_ns() // 1_000_000)

        return PromptTier(
            tier_name="volatile",
            content=content,
            version=version,
            token_estimate=token_estimate,
            cacheable=False,
        )

    # ------------------------------------------------------------------ #
    # 组装与缓存
    # ------------------------------------------------------------------ #
    def assemble_messages(
        self,
        stable: PromptTier,
        context: PromptTier,
        volatile: PromptTier,
    ) -> list[dict[str, str]]:
        """组装三层为 messages 列表.

        顺序: stable → context → volatile.
        每层构建为一条 system message.

        Args:
            stable: 稳定层
            context: 上下文层
            volatile: 易变层

        Returns:
            messages 列表 (每条包含 role 和 content)
        """
        return [
            {"role": "system", "content": stable.content},
            {"role": "system", "content": context.content},
            {"role": "system", "content": volatile.content},
        ]

    def get_cache_key(self, stable: PromptTier, context: PromptTier) -> str:
        """生成缓存键.

        缓存键 = stable_version + context_date.
        volatile_tier 不参与缓存键.

        Args:
            stable: 稳定层
            context: 上下文层

        Returns:
            缓存键字符串
        """
        return f"{stable.version}:{context.version}"

    # ------------------------------------------------------------------ #
    # Token 估算
    # ------------------------------------------------------------------ #
    def estimate_tier_tokens(self, tier: PromptTier) -> int:
        """估算层级 token 数.

        中文 1.5 字/token, 英文 4 字符/token.
        加上每条消息的结构开销.

        Args:
            tier: prompt 层级

        Returns:
            估算的 token 数
        """
        return self.estimate_tier_tokens_text(tier.content)

    @staticmethod
    def estimate_tier_tokens_text(text: str) -> int:
        """估算文本的 token 数.

        使用简单启发式:
        - 中文字符按 1.5 字/token
        - 英文字符按 4 字符/token
        - 加上每条消息的结构开销

        Args:
            text: 文本内容

        Returns:
            估算的 token 数
        """
        if not text:
            return _PER_MESSAGE_OVERHEAD

        # 统计中文字符数
        cjk_chars = len(_CJK_PATTERN.findall(text))
        # 非中文字符数
        non_cjk_chars = len(text) - cjk_chars
        # 中文按 1.5 字/token, 英文按 4 字符/token
        cjk_tokens = cjk_chars / 1.5
        en_tokens = non_cjk_chars / 4.0
        return int(cjk_tokens + en_tokens) + _PER_MESSAGE_OVERHEAD

    @staticmethod
    def count_tokens_precise(text: str, *, model: str = "gpt-4") -> int:
        """精确计算文本的 token 数 (使用 tiktoken).

        当 tiktoken 可用时, 使用 cl100k_base 编码精确计算.
        当 tiktoken 不可用时, 回退到启发式估算.

        Args:
            text: 文本内容
            model: 模型名称 (目前统一使用 cl100k_base)

        Returns:
            精确的 token 数
        """
        if not text:
            return 0
        if _TIKTOKEN_AVAILABLE:
            try:
                enc = _tiktoken.get_encoding("cl100k_base")
                return len(enc.encode(text))
            except Exception:
                # tiktoken 编码失败时回退到启发式
                pass
        return TieredPromptBuilder.estimate_tier_tokens_text(text)

    def count_tier_tokens_precise(self, tier: PromptTier, *, model: str = "gpt-4") -> int:
        """精确计算层级的 token 数.

        Args:
            tier: prompt 层级
            model: 模型名称

        Returns:
            精确的 token 数
        """
        return self.count_tokens_precise(tier.content, model=model)


__all__ = [
    "PromptTier",
    "TieredPromptBuilder",
]
