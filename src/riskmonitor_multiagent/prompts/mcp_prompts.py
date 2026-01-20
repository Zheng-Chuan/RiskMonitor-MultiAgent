"""MCP 提示词注册."""

from __future__ import annotations

from mcp.server import FastMCP


def register_prompts(mcp: FastMCP) -> None:
    """注册 MCP 提示词."""
    @mcp.prompt(
        name="analyze-risk-breach",
        title="Analyze Risk Breach",
        description="风控告警分析模板(根因、影响、处置建议、下一步动作)",
    )
    def analyze_risk_breach(
        desk: str,
        as_of: str,
        abs_delta: float,
        abs_delta_limit: float,
    ) -> str:
        return f"""你是资深衍生品风控分析师。

输入:
- desk: {desk}
- as_of: {as_of}
- abs_delta: {abs_delta}
- abs_delta_limit: {abs_delta_limit}

请输出一个结构化报告(使用 Markdown):
1) 结论(是否超限, 严重程度)
2) 根因假设(至少 3 条, 按可能性排序)
3) 风险影响(对 PV、流动性、Greeks 的潜在影响)
4) 处置建议(立即动作/短期/中期)
5) 需要补充的数据(最少化列表)

约束:
- 不要编造未提供的数据。
- 如果信息不足, 明确说明并给出最小可行的下一步查询动作。
"""
