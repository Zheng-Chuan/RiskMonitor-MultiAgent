"""MCP 提示词."""

from __future__ import annotations

from riskmonitor_multiagent.prompts.cost_report import (
    CostBaseline,
    CostComparisonResult,
    CostReportGenerator,
)
from riskmonitor_multiagent.prompts.prompt_cache import PromptCacheManager
from riskmonitor_multiagent.prompts.tiered_prompt_builder import (
    PromptTier,
    TieredPromptBuilder,
)
from riskmonitor_multiagent.prompts.trend_tracker import (
    TREND_DOWN,
    TREND_STABLE,
    TREND_UP,
    TrendAnalysis,
    TrendSnapshot,
    TrendTracker,
)

__all__: list[str] = [
    "CostBaseline",
    "CostComparisonResult",
    "CostReportGenerator",
    "PromptTier",
    "PromptCacheManager",
    "TieredPromptBuilder",
    "TREND_DOWN",
    "TREND_STABLE",
    "TREND_UP",
    "TrendAnalysis",
    "TrendSnapshot",
    "TrendTracker",
]
