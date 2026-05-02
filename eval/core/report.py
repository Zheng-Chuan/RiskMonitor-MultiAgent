"""
评估报告生成器.

生成多种格式的评估报告:
- JSON 报告
- Markdown 报告
- HTML 报告
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from eval.core.evaluator import EvaluationResult

logger = logging.getLogger(__name__)


class ReportGenerator:
    """评估报告生成器."""
    
    def __init__(self) -> None:
        """初始化报告生成器."""
        pass
    
    def generate_json_report(
        self,
        result: EvaluationResult,
        output_path: str | Path | None = None,
    ) -> str:
        """
        生成 JSON 报告.
        
        Args:
            result: 评估结果
            output_path: 输出路径
            
        Returns:
            JSON 字符串
        """
        report = result.to_dict()
        report_json = json.dumps(report, ensure_ascii=False, indent=2)
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_json)
            logger.info(f"JSON report saved to {output_path}")
        
        return report_json
    
    def generate_markdown_report(
        self,
        result: EvaluationResult,
        output_path: str | Path | None = None,
    ) -> str:
        """
        生成 Markdown 报告.
        
        Args:
            result: 评估结果
            output_path: 输出路径
            
        Returns:
            Markdown 字符串
        """
        lines = []
        
        lines.append("# Multi-Agent System Evaluation Report")
        lines.append("")
        lines.append(f"**Run ID**: {result.run_id}")
        lines.append(f"**Timestamp**: {result.timestamp}")
        lines.append("")
        
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Cases**: {result.total_cases}")
        lines.append(f"- **Passed**: {result.passed_cases}")
        lines.append(f"- **Failed**: {result.failed_cases}")
        lines.append(f"- **Pass Rate**: {result.pass_rate:.2%}")
        lines.append(f"- **Overall Score**: {result.overall_metrics.overall_score:.2%}")
        lines.append("")
        
        lines.append("## Metrics Overview")
        lines.append("")
        
        metrics = result.overall_metrics
        
        lines.append("### Task Accuracy")
        lines.append("")
        lines.append(f"- Intent Match: {metrics.task_accuracy.intent_match_score:.2%}")
        lines.append(f"- Plan Correctness: {metrics.task_accuracy.plan_correctness:.2%}")
        lines.append(f"- Execution Success: {metrics.task_accuracy.execution_success_rate:.2%}")
        lines.append(f"- Answer Quality: {metrics.task_accuracy.answer_quality:.2%}")
        lines.append(f"- **Overall**: {metrics.task_accuracy.overall_accuracy:.2%}")
        lines.append("")
        
        lines.append("### Comprehension")
        lines.append("")
        lines.append(f"- Intent Recognition F1: {metrics.comprehension.intent_recognition_f1:.2%}")
        lines.append(f"- Entity Extraction F1: {metrics.comprehension.entity_extraction_f1:.2%}")
        lines.append(f"- Ambiguity Resolution: {metrics.comprehension.ambiguity_resolution:.2%}")
        lines.append(f"- Context Understanding: {metrics.comprehension.context_understanding:.2%}")
        lines.append(f"- **Overall**: {metrics.comprehension.overall_comprehension:.2%}")
        lines.append("")
        
        lines.append("### Collaboration")
        lines.append("")
        lines.append(f"- Agent Participation: {metrics.collaboration.agent_participation_rate:.2%}")
        lines.append(f"- Information Diversity: {metrics.collaboration.information_diversity:.2%}")
        lines.append(f"- Message Exchange Depth: {metrics.collaboration.message_exchange_depth:.2%}")
        lines.append(f"- Role Specialization: {metrics.collaboration.role_specialization:.2%}")
        lines.append(f"- Conflict Resolution: {metrics.collaboration.conflict_resolution_rate:.2%}")
        lines.append(f"- **Overall**: {metrics.collaboration.overall_collaboration:.2%}")
        lines.append("")
        
        lines.append("### Efficiency")
        lines.append("")
        lines.append(f"- Latency: {metrics.efficiency.latency_ms}ms")
        lines.append(f"- Latency per Step: {metrics.efficiency.latency_per_step_ms}ms")
        lines.append(f"- Token Count: {metrics.efficiency.token_count}")
        lines.append(f"- Token Efficiency: {metrics.efficiency.token_efficiency:.2%}")
        lines.append(f"- Tool Call Count: {metrics.efficiency.tool_call_count}")
        lines.append(f"- Tool Call Efficiency: {metrics.efficiency.tool_call_efficiency:.2%}")
        lines.append(f"- Tool Success Rate: {metrics.efficiency.tool_success_rate:.2%}")
        lines.append(f"- Tool Timeout Rate: {metrics.efficiency.tool_timeout_rate:.2%}")
        lines.append(f"- Tool Retry Rate: {metrics.efficiency.tool_retry_rate:.2%}")
        lines.append(f"- Iteration Count: {metrics.efficiency.iteration_count}")
        lines.append(f"- **Overall**: {metrics.efficiency.overall_efficiency:.2%}")
        lines.append("")
        
        lines.append("### Reasoning")
        lines.append("")
        lines.append(f"- Thought Relevance: {metrics.reasoning.thought_relevance:.2%}")
        lines.append(f"- Reasoning Validity: {metrics.reasoning.reasoning_validity:.2%}")
        lines.append(f"- Evidence Support: {metrics.reasoning.evidence_support:.2%}")
        lines.append(f"- Logical Consistency: {metrics.reasoning.logical_consistency:.2%}")
        lines.append(f"- Reasoning Depth: {metrics.reasoning.reasoning_depth:.2%}")
        lines.append(f"- **Overall**: {metrics.reasoning.overall_reasoning:.2%}")
        lines.append("")
        
        lines.append("### Tool Risk")
        lines.append("")
        lines.append(f"- Side Effect Detection: {metrics.tool_risk.side_effect_detection:.2%}")
        lines.append(f"- Permission Compliance: {metrics.tool_risk.permission_compliance:.2%}")
        lines.append(f"- Risk Assessment Accuracy: {metrics.tool_risk.risk_assessment_accuracy:.2%}")
        lines.append(f"- Approval Flow Compliance: {metrics.tool_risk.approval_flow_compliance:.2%}")
        lines.append(f"- Dangerous Action Blocked: {metrics.tool_risk.dangerous_action_blocked:.2%}")
        lines.append(f"- **Overall Safety**: {metrics.tool_risk.overall_safety:.2%}")
        lines.append("")

        lines.append("### Memory")
        lines.append("")
        lines.append(f"- Memory Hit Rate: {metrics.memory.memory_hit_rate:.2%}")
        lines.append(f"- Memory Usefulness: {metrics.memory.memory_usefulness:.2%}")
        lines.append(f"- Resume Success Rate: {metrics.memory.resume_success_rate:.2%}")
        lines.append(f"- **Overall Memory**: {metrics.memory.overall_memory:.2%}")
        lines.append("")
        
        if result.comparison:
            lines.append("## Comparison")
            lines.append("")
            
            if "vs_history" in result.comparison:
                vs_history = result.comparison["vs_history"]
                lines.append("### vs History")
                lines.append("")
                for key, value in vs_history.items():
                    if isinstance(value, (int, float)):
                        sign = "+" if value >= 0 else ""
                        lines.append(f"- {key}: {sign}{value:.4f}")
                    else:
                        lines.append(f"- {key}: {value}")
                lines.append("")
            
            if "vs_benchmark" in result.comparison:
                vs_benchmark = result.comparison["vs_benchmark"]
                lines.append("### vs Benchmark")
                lines.append("")
                for key, value in vs_benchmark.items():
                    lines.append(f"- {key}: {value}")
                lines.append("")
        
        lines.append("## Case Results")
        lines.append("")
        lines.append("| Case ID | Category | Difficulty | Success | Overall Score |")
        lines.append("|---------|----------|------------|---------|---------------|")
        
        for case in result.case_results[:20]:
            success_mark = "✅" if case.success else "❌"
            lines.append(
                f"| {case.case_id} | {case.category} | {case.difficulty} | "
                f"{success_mark} | {case.metrics.overall_score:.2%} |"
            )
        
        if len(result.case_results) > 20:
            lines.append(f"| ... | ... | ... | ... | ... |")
            lines.append(f"_Showing 20 of {len(result.case_results)} cases_")
        
        lines.append("")
        lines.append("---")
        lines.append(f"Generated at {datetime.now().isoformat()}")
        
        report_md = "\n".join(lines)
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report_md)
            logger.info(f"Markdown report saved to {output_path}")
        
        return report_md
    
    def generate_html_report(
        self,
        result: EvaluationResult,
        output_path: str | Path | None = None,
    ) -> str:
        """
        生成 HTML 报告.
        
        Args:
            result: 评估结果
            output_path: 输出路径
            
        Returns:
            HTML 字符串
        """
        metrics = result.overall_metrics
        
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Agent Evaluation Report - {result.run_id}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        .summary-cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
        }}
        .card {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .card h3 {{
            margin: 0 0 10px 0;
            color: #666;
            font-size: 14px;
        }}
        .card .value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }}
        .metrics-section {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metrics-section h2 {{
            margin-top: 0;
            color: #333;
        }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #eee;
        }}
        .metric-row:last-child {{
            border-bottom: none;
        }}
        .metric-name {{
            color: #666;
        }}
        .metric-value {{
            font-weight: bold;
        }}
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: #e0e0e0;
            border-radius: 4px;
            overflow: hidden;
            margin-top: 5px;
        }}
        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, #667eea, #764ba2);
            border-radius: 4px;
        }}
        .good {{ color: #4caf50; }}
        .warning {{ color: #ff9800; }}
        .bad {{ color: #f44336; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Multi-Agent System Evaluation Report</h1>
        <p>Run ID: {result.run_id} | Timestamp: {result.timestamp}</p>
    </div>
    
    <div class="summary-cards">
        <div class="card">
            <h3>Total Cases</h3>
            <div class="value">{result.total_cases}</div>
        </div>
        <div class="card">
            <h3>Pass Rate</h3>
            <div class="value {'good' if result.pass_rate >= 0.8 else 'warning' if result.pass_rate >= 0.6 else 'bad'}">{result.pass_rate:.1%}</div>
        </div>
        <div class="card">
            <h3>Overall Score</h3>
            <div class="value {'good' if result.overall_metrics.overall_score >= 0.7 else 'warning' if result.overall_metrics.overall_score >= 0.5 else 'bad'}">{result.overall_metrics.overall_score:.1%}</div>
        </div>
        <div class="card">
            <h3>Avg Latency</h3>
            <div class="value">{metrics.efficiency.latency_ms}ms</div>
        </div>
    </div>
    
    <div class="metrics-section">
        <h2>Task Accuracy</h2>
        <div class="metric-row">
            <span class="metric-name">Intent Match</span>
            <span class="metric-value">{metrics.task_accuracy.intent_match_score:.1%}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: {metrics.task_accuracy.intent_match_score * 100}%"></div></div>
        
        <div class="metric-row">
            <span class="metric-name">Plan Correctness</span>
            <span class="metric-value">{metrics.task_accuracy.plan_correctness:.1%}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: {metrics.task_accuracy.plan_correctness * 100}%"></div></div>
        
        <div class="metric-row">
            <span class="metric-name">Execution Success</span>
            <span class="metric-value">{metrics.task_accuracy.execution_success_rate:.1%}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: {metrics.task_accuracy.execution_success_rate * 100}%"></div></div>
        
        <div class="metric-row">
            <span class="metric-name">Answer Quality</span>
            <span class="metric-value">{metrics.task_accuracy.answer_quality:.1%}</span>
        </div>
        <div class="progress-bar"><div class="progress-fill" style="width: {metrics.task_accuracy.answer_quality * 100}%"></div></div>
    </div>
    
    <div class="metrics-section">
        <h2>Collaboration</h2>
        <div class="metric-row">
            <span class="metric-name">Agent Participation</span>
            <span class="metric-value">{metrics.collaboration.agent_participation_rate:.1%}</span>
        </div>
        <div class="metric-row">
            <span class="metric-name">Information Diversity</span>
            <span class="metric-value">{metrics.collaboration.information_diversity:.1%}</span>
        </div>
        <div class="metric-row">
            <span class="metric-name">Role Specialization</span>
            <span class="metric-value">{metrics.collaboration.role_specialization:.1%}</span>
        </div>
    </div>
    
    <div class="metrics-section">
        <h2>Reasoning Quality</h2>
        <div class="metric-row">
            <span class="metric-name">Thought Relevance</span>
            <span class="metric-value">{metrics.reasoning.thought_relevance:.1%}</span>
        </div>
        <div class="metric-row">
            <span class="metric-name">Reasoning Validity</span>
            <span class="metric-value">{metrics.reasoning.reasoning_validity:.1%}</span>
        </div>
        <div class="metric-row">
            <span class="metric-name">Evidence Support</span>
            <span class="metric-value">{metrics.reasoning.evidence_support:.1%}</span>
        </div>
    </div>
    
    <div class="metrics-section">
        <h2>Tool Risk</h2>
        <div class="metric-row">
            <span class="metric-name">Side Effect Detection</span>
            <span class="metric-value">{metrics.tool_risk.side_effect_detection:.1%}</span>
        </div>
        <div class="metric-row">
            <span class="metric-name">Permission Compliance</span>
            <span class="metric-value">{metrics.tool_risk.permission_compliance:.1%}</span>
        </div>
        <div class="metric-row">
            <span class="metric-name">Dangerous Action Blocked</span>
            <span class="metric-value">{metrics.tool_risk.dangerous_action_blocked:.1%}</span>
        </div>
    </div>
</body>
</html>"""
        
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)
            logger.info(f"HTML report saved to {output_path}")
        
        return html


__all__ = ["ReportGenerator"]
