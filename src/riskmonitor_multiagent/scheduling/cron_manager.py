"""Cron 定时任务管理器.

提供 CronTask 定义和 CronManager 管理器,
支持自然语言转 cron 表达式、任务 CRUD、触发检测和递归防护.

设计约束:
- 使用内存存储 (不需要 Redis)
- cron 表达式使用简单解析 (不需要 croniter 库)
- Cron 任务通过统一执行内核执行, 不允许绕过治理体系.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_CRON_SEGMENT_COUNT = 5  # minute hour day month weekday

# 自然语言 → cron 表达式映射 (顺序很重要: 先匹配更具体的关键词)
_NATURAL_LANGUAGE_MAP: list[tuple[str, str]] = [
    ("每个工作日收盘后", "0 18 * * 1-5"),
    ("每天收盘后", "0 18 * * 1-5"),
    ("工作日", "0 0 * * 1-5"),
    ("每个工作日", "0 0 * * 1-5"),
    ("每天", "0 0 * * *"),
    ("每周", "0 0 * * 0"),
    ("每小时", "0 * * * *"),
]

_DEFAULT_CRON = "0 0 * * *"

# 各字段的有效范围
_FIELD_RANGES = [
    (0, 59),   # minute
    (0, 23),   # hour
    (1, 31),   # day of month
    (1, 12),   # month
    (0, 7),    # day of week (0 and 7 both represent Sunday)
]


# ---------------------------------------------------------------------------
# CronTask 数据类
# ---------------------------------------------------------------------------

@dataclass
class CronTask:
    """定时任务定义."""

    task_id: str
    name: str
    cron_expression: str
    natural_language: str
    task_template: dict[str, Any]
    trigger_config: dict[str, Any]
    enabled: bool = True
    created_at: int = 0
    last_triggered: int | None = None
    trigger_count: int = 0
    max_recursion_depth: int = 3


# ---------------------------------------------------------------------------
# CronManager 管理器
# ---------------------------------------------------------------------------

class CronManager:
    """定时任务管理器.

    使用内存存储管理 CronTask 生命周期,
    支持自然语言解析和递归深度防护.
    """

    def __init__(self, *, max_concurrent_crons: int = 5) -> None:
        self._tasks: dict[str, CronTask] = {}
        self._recursion_depths: dict[str, int] = {}
        self._max_concurrent_crons = max_concurrent_crons

    # ------------------------------------------------------------------
    # 任务 CRUD
    # ------------------------------------------------------------------

    async def create_task(self, task: dict[str, Any]) -> CronTask:
        """创建定时任务. 验证 cron 表达式.

        Args:
            task: 包含 name, cron_expression/natural_language, task_template, trigger_config 的字典.

        Returns:
            创建的 CronTask 实例.

        Raises:
            ValueError: 如果 cron 表达式无效或缺少必填字段.
        """
        name = str(task.get("name") or "").strip()
        if not name:
            raise ValueError("task name is required")

        natural_language = str(task.get("natural_language") or "").strip()
        cron_expression = str(task.get("cron_expression") or "").strip()

        # 如果提供了自然语言但没提供 cron 表达式, 则自动解析
        if not cron_expression and natural_language:
            cron_expression = self.parse_natural_language(natural_language)

        # 如果都没有, 使用默认
        if not cron_expression:
            cron_expression = _DEFAULT_CRON

        if not self.validate_cron_expression(cron_expression):
            raise ValueError(f"invalid cron expression: {cron_expression}")

        task_template = task.get("task_template") if isinstance(task.get("task_template"), dict) else {}
        trigger_config = task.get("trigger_config") if isinstance(task.get("trigger_config"), dict) else {}
        max_recursion_depth = int(task.get("max_recursion_depth", 3))

        task_id = f"cron_{uuid.uuid4().hex[:12]}"
        created_at = int(time.time() * 1000)

        cron_task = CronTask(
            task_id=task_id,
            name=name,
            cron_expression=cron_expression,
            natural_language=natural_language,
            task_template=task_template,
            trigger_config=trigger_config,
            enabled=True,
            created_at=created_at,
            last_triggered=None,
            trigger_count=0,
            max_recursion_depth=max_recursion_depth,
        )
        self._tasks[task_id] = cron_task
        self._recursion_depths[task_id] = 0
        logger.info("Cron task created: %s (%s) expr=%s", task_id, name, cron_expression)
        return cron_task

    async def get_task(self, task_id: str) -> CronTask | None:
        """获取定时任务."""
        return self._tasks.get(task_id)

    async def list_tasks(self, *, enabled: bool | None = None) -> list[CronTask]:
        """列出定时任务, 可按 enabled 过滤."""
        tasks = list(self._tasks.values())
        if enabled is not None:
            tasks = [t for t in tasks if t.enabled == enabled]
        return tasks

    async def pause_task(self, task_id: str) -> bool:
        """暂停定时任务."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.enabled = False
        logger.info("Cron task paused: %s", task_id)
        return True

    async def resume_task(self, task_id: str) -> bool:
        """恢复定时任务."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        task.enabled = True
        logger.info("Cron task resumed: %s", task_id)
        return True

    async def delete_task(self, task_id: str) -> bool:
        """删除定时任务."""
        existed = self._tasks.pop(task_id, None) is not None
        self._recursion_depths.pop(task_id, None)
        if existed:
            logger.info("Cron task deleted: %s", task_id)
        return existed

    # ------------------------------------------------------------------
    # 触发管理
    # ------------------------------------------------------------------

    async def get_due_tasks(self, *, now_ms: int | None = None) -> list[CronTask]:
        """获取当前应该触发的任务.

        简单实现: 检查 last_triggered + interval.
        如果任务从未触发过, 则认为应当触发.
        """
        if now_ms is None:
            now_ms = int(time.time() * 1000)

        due: list[CronTask] = []
        for task in self._tasks.values():
            if not task.enabled:
                continue
            interval_ms = self._estimate_interval_ms(task.cron_expression)
            if task.last_triggered is None:
                # 从未触发过, 检查是否到了应该触发的时间
                # 简单策略: 如果创建时间距今超过 interval, 则应触发
                if now_ms - task.created_at >= interval_ms:
                    due.append(task)
                else:
                    # 如果创建时间很近, 也允许立即触发一次 (首次触发)
                    due.append(task)
            elif now_ms - task.last_triggered >= interval_ms:
                due.append(task)
        return due

    async def mark_triggered(self, task_id: str) -> None:
        """标记任务已触发, 更新 last_triggered 和 trigger_count."""
        task = self._tasks.get(task_id)
        if task is None:
            return
        task.last_triggered = int(time.time() * 1000)
        task.trigger_count += 1
        logger.info(
            "Cron task triggered: %s (count=%d)",
            task_id,
            task.trigger_count,
        )

    # ------------------------------------------------------------------
    # 递归防护
    # ------------------------------------------------------------------

    def check_recursion(self, task_id: str, current_depth: int) -> bool:
        """检查递归深度是否超限. 超过 max_recursion_depth 返回 False."""
        task = self._tasks.get(task_id)
        if task is None:
            return False
        if current_depth > task.max_recursion_depth:
            logger.warning(
                "Cron task recursion limit exceeded: %s (depth=%d, max=%d)",
                task_id,
                current_depth,
                task.max_recursion_depth,
            )
            return False
        self._recursion_depths[task_id] = current_depth
        return True

    def get_recursion_depth(self, task_id: str) -> int:
        """获取当前递归深度."""
        return self._recursion_depths.get(task_id, 0)

    def reset_recursion(self, task_id: str) -> None:
        """重置递归深度计数."""
        self._recursion_depths[task_id] = 0

    # ------------------------------------------------------------------
    # 自然语言解析
    # ------------------------------------------------------------------

    def parse_natural_language(self, description: str) -> str:
        """将自然语言描述转为 cron 表达式.

        支持的关键词:
        - "每天" → "0 0 * * *"
        - "每个工作日" / "工作日" → "0 0 * * 1-5"
        - "每周" → "0 0 * * 0"
        - "每小时" → "0 * * * *"
        - "每天收盘后" / "每个工作日收盘后" → "0 18 * * 1-5"

        兜底: 返回 "0 0 * * *" (每天)
        """
        if not description:
            return _DEFAULT_CRON
        desc = description.strip()
        for keyword, cron_expr in _NATURAL_LANGUAGE_MAP:
            if keyword in desc:
                return cron_expr
        return _DEFAULT_CRON

    # ------------------------------------------------------------------
    # Cron 表达式验证
    # ------------------------------------------------------------------

    def validate_cron_expression(self, expr: str) -> bool:
        """验证 cron 表达式格式. 5 段格式: minute hour day month weekday.

        每段支持: *, 数字, 逗号列表, 范围 (1-5), 步长 (*/2).
        """
        if not expr or not isinstance(expr, str):
            return False
        parts = expr.strip().split()
        if len(parts) != _CRON_SEGMENT_COUNT:
            return False
        for idx, part in enumerate(parts):
            if not self._validate_cron_field(part, idx):
                return False
        return True

    # ------------------------------------------------------------------
    # 内部辅助方法
    # ------------------------------------------------------------------

    def _validate_cron_field(self, field_str: str, field_idx: int) -> bool:
        """验证单个 cron 字段."""
        min_val, max_val = _FIELD_RANGES[field_idx]
        # 星号
        if field_str == "*":
            return True
        # 步长: */N
        if field_str.startswith("*/"):
            step_str = field_str[2:]
            if not step_str.isdigit():
                return False
            step = int(step_str)
            if step < 1 or step > max_val:
                return False
            return True
        # 逗号分隔的列表
        if "," in field_str:
            for item in field_str.split(","):
                if not self._validate_single_value(item.strip(), min_val, max_val):
                    return False
            return True
        # 单个值或范围
        return self._validate_single_value(field_str, min_val, max_val)

    def _validate_single_value(self, value: str, min_val: int, max_val: int) -> bool:
        """验证单个 cron 值 (数字或范围)."""
        if not value:
            return False
        # 范围: N-M
        if "-" in value and not value.startswith("-"):
            parts = value.split("-")
            if len(parts) != 2:
                return False
            for part in parts:
                if not part.isdigit():
                    return False
                num = int(part)
                if num < min_val or num > max_val:
                    # weekday: 7 代表 Sunday
                    if max_val == 7 and num == 7:
                        continue
                    return False
            return True
        # 纯数字
        if value.isdigit():
            num = int(value)
            if num < min_val or num > max_val:
                # weekday: 7 代表 Sunday
                if max_val == 7 and num == 7:
                    return True
                return False
            return True
        return False

    def _estimate_interval_ms(self, cron_expression: str) -> int:
        """从 cron 表达式估算触发间隔 (毫秒).

        简单策略:
        - 如果 hour 字段是 *, 间隔为 1 小时
        - 如果 weekday 字段不是 *, 间隔为 7 天
        - 否则间隔为 1 天
        """
        parts = cron_expression.strip().split()
        if len(parts) != _CRON_SEGMENT_COUNT:
            return 86400 * 1000  # 默认 1 天

        minute_field, hour_field, day_field, month_field, weekday_field = parts

        # 每小时
        if hour_field == "*":
            return 3600 * 1000

        # 每周 (指定了 weekday)
        if weekday_field != "*":
            return 7 * 86400 * 1000

        # 默认每天
        return 86400 * 1000


__all__ = [
    "CronManager",
    "CronTask",
]
