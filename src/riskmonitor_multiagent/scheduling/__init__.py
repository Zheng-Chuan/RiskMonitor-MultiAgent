"""内置调度系统模块.

提供 Cron 任务管理、自然语言解析和金融场景模板.
Cron 任务通过统一执行内核 (system_event → ModeratorAgent → TaskGraphExecutor) 执行,
不允许绕过多 Agent 治理体系.
"""

from riskmonitor_multiagent.scheduling.cron_manager import CronManager, CronTask
from riskmonitor_multiagent.scheduling.cron_templates import FINANCIAL_CRON_TEMPLATES, CronTemplate

__all__ = [
    "CronManager",
    "CronTask",
    "CronTemplate",
    "FINANCIAL_CRON_TEMPLATES",
]
