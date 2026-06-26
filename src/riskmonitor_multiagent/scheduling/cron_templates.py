"""金融场景 Cron 模板.

预置常用金融风控定时任务模板, 可直接用于 CronManager.create_task.
"""

from __future__ import annotations

from typing import Any, TypedDict


class CronTemplate(TypedDict):
    """Cron 任务模板定义."""

    name: str
    natural_language: str
    cron_expression: str
    task_template: dict[str, Any]
    trigger_config: dict[str, Any]


FINANCIAL_CRON_TEMPLATES: list[CronTemplate] = [
    {
        "name": "每日盘后风险汇总",
        "natural_language": "每个工作日收盘后",
        "cron_expression": "0 18 * * 1-5",
        "task_template": {
            "intent": "daily_post_market_risk_summary",
            "content": {"category": "risk_summary", "scope": "all_desks"},
        },
        "trigger_config": {"entry_type": "system_event", "priority": "normal"},
    },
    {
        "name": "定时阈值巡检",
        "natural_language": "每小时",
        "cron_expression": "0 * * * *",
        "task_template": {
            "intent": "threshold_patrol_check",
            "content": {"category": "threshold_check", "check_all": True},
        },
        "trigger_config": {"entry_type": "system_event", "priority": "high"},
    },
    {
        "name": "周度合规报告",
        "natural_language": "每周",
        "cron_expression": "0 9 * * 1",
        "task_template": {
            "intent": "weekly_compliance_report",
            "content": {"category": "compliance", "report_type": "weekly"},
        },
        "trigger_config": {"entry_type": "system_event", "priority": "normal"},
    },
]


__all__ = [
    "CronTemplate",
    "FINANCIAL_CRON_TEMPLATES",
]
