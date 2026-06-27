"""Cron 定时任务管理器.

提供 CronTask 定义和 CronManager 管理器,
支持自然语言转 cron 表达式、任务 CRUD、触发检测和递归防护.

设计约束:
- 使用内存存储 (不需要 Redis)
- cron 表达式使用简单解析 (不需要 croniter 库)
- Cron 任务通过统一执行内核执行, 不允许绕过治理体系.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_CRON_SEGMENT_COUNT = 5  # minute hour day month weekday

# 自然语言 → cron 表达式映射 (顺序很重要: 先匹配更具体的关键词)
_NATURAL_LANGUAGE_MAP: list[tuple[str, str]] = [
    # 金融场景
    ("每个工作日收盘后", "0 18 * * 1-5"),
    ("每天收盘后", "0 18 * * 1-5"),
    ("收盘后", "0 18 * * 1-5"),
    ("每个工作日开盘前", "30 9 * * 1-5"),
    ("每天开盘前", "30 9 * * 1-5"),
    ("开盘前", "30 9 * * 1-5"),
    # 工作日
    ("工作日", "0 0 * * 1-5"),
    ("每个工作日", "0 0 * * 1-5"),
    # 时间段
    ("每天午夜", "0 0 * * *"),
    ("午夜", "0 0 * * *"),
    ("每天中午", "0 12 * * *"),
    ("中午", "0 12 * * *"),
    # 基本周期
    ("每天", "0 0 * * *"),
    ("每日", "0 0 * * *"),
    # 具体星期 (必须在 "每周" 之前, 否则 "每周一" 会先匹配 "每周")
    ("每周一", "0 0 * * 1"),
    ("每周二", "0 0 * * 2"),
    ("每周三", "0 0 * * 3"),
    ("每周四", "0 0 * * 4"),
    ("每周五", "0 0 * * 5"),
    ("每周六", "0 0 * * 6"),
    ("每周日", "0 0 * * 0"),
    ("每周天", "0 0 * * 0"),
    ("每周", "0 0 * * 0"),
    ("每半小时", "*/30 * * * *"),
    ("半小时", "*/30 * * * *"),
    ("每小时", "0 * * * *"),
]

# 正则模式列表 (用于动态解析, 按优先级排列)
_NL_REGEX_PATTERNS: list[tuple[str, str]] = [
    # "每隔N分钟" / "每N分钟" → "*/N * * * *"
    (r"每(?:隔)?\s*(\d+)\s*分钟", "*/{0} * * * *"),
    # "每隔N小时" / "每N小时" → "0 */N * * *"
    (r"每(?:隔)?\s*(\d+)\s*小时", "0 */{0} * * *"),
    # "每天X点Y分" → "M X * * *"
    (r"每?天\s*(?:上午|下午)?(\d{1,2})\s*[点时:]\s*(\d{1,2})\s*分?", "{1} {0} * * *"),
    # "每天X点" → "0 X * * *"
    (r"每?天\s*(?:上午|下午)?(\d{1,2})\s*[点时:]", "0 {0} * * *"),
    # "下午X点" → "0 X+12 * * *" (下午自动 +12)
    (r"下午\s*(\d{1,2})\s*[点时:]", "0 {_pm_hour} * * *"),
    # "上午X点" → "0 X * * *"
    (r"上午\s*(\d{1,2})\s*[点时:]", "0 {0} * * *"),
    # "每个工作日X点" → "0 X * * 1-5"
    (r"每?个?工作日\s*(?:上午|下午)?(\d{1,2})\s*[点时:]", "0 {0} * * 1-5"),
    # "每N天" → "0 0 */N * *"
    (r"每(?:隔)?\s*(\d+)\s*天", "0 0 */{0} * *"),
    # "周X" → "0 0 * * N" (周几)
    (r"周([一二三四五六日天])", "0 0 * * {_weekday}"),
]

# 中文星期映射
_WEEKDAY_MAP: dict[str, str] = {
    "一": "1", "二": "2", "三": "3", "四": "4",
    "五": "5", "六": "6", "日": "0", "天": "0",
}

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
    可选启用 asyncio 后台调度循环, 自动触发到期任务.
    """

    def __init__(
        self,
        *,
        max_concurrent_crons: int = 5,
        schedule_interval_seconds: float = 30.0,
    ) -> None:
        self._tasks: dict[str, CronTask] = {}
        self._recursion_depths: dict[str, int] = {}
        self._max_concurrent_crons = max_concurrent_crons
        self._schedule_interval = schedule_interval_seconds
        self._background_task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._trigger_callback: Optional[
            Callable[[CronTask], Awaitable[None]]
        ] = None

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

        解析策略 (按优先级):
        1. 关键词精确匹配 (_NATURAL_LANGUAGE_MAP)
        2. 正则模式动态解析 (_NL_REGEX_PATTERNS)
        3. 兜底返回 "0 0 * * *" (每天)

        支持的关键词:
        - "每天" / "每日" → "0 0 * * *"
        - "每个工作日" / "工作日" → "0 0 * * 1-5"
        - "每周" → "0 0 * * 0"
        - "每周一" ~ "每周日" → 对应星期几
        - "每小时" → "0 * * * *"
        - "每半小时" → "*/30 * * * *"
        - "收盘后" / "每天收盘后" → "0 18 * * 1-5"
        - "开盘前" / "每天开盘前" → "30 9 * * 1-5"
        - "中午" → "0 12 * * *"
        - "午夜" → "0 0 * * *"

        支持的正则模式:
        - "每隔N分钟" → "*/N * * * *"
        - "每隔N小时" → "0 */N * * *"
        - "每天X点" → "0 X * * *"
        - "每天X点Y分" → "M X * * *"
        - "下午X点" → "0 X+12 * * *"
        - "每个工作日X点" → "0 X * * 1-5"
        - "每N天" → "0 0 */N * *"
        - "周X" → "0 0 * * N"

        兜底: 返回 "0 0 * * *" (每天)
        """
        if not description:
            return _DEFAULT_CRON
        desc = description.strip()

        # 1. 如果包含数字 (具体时间), 优先尝试正则模式
        if re.search(r"\d", desc):
            result = self._parse_with_regex(desc)
            if result is not None:
                return result

        # 2. 关键词匹配
        for keyword, cron_expr in _NATURAL_LANGUAGE_MAP:
            if keyword in desc:
                return cron_expr

        # 3. 正则模式匹配 (非数字场景, 如 "周X")
        result = self._parse_with_regex(desc)
        if result is not None:
            return result

        # 4. 兜底
        return _DEFAULT_CRON

    def _parse_with_regex(self, desc: str) -> str | None:
        """使用正则模式动态解析自然语言.

        Args:
            desc: 自然语言描述文本.

        Returns:
            解析成功的 cron 表达式, 失败返回 None.
        """
        for pattern, template in _NL_REGEX_PATTERNS:
            match = re.search(pattern, desc)
            if not match:
                continue

            groups = match.groups()

            # 特殊处理: 下午时间 (+12)
            if "{_pm_hour}" in template:
                hour = int(groups[0])
                if hour < 12:
                    hour += 12
                return template.replace("{_pm_hour}", str(hour))

            # 特殊处理: 中文星期
            if "{_weekday}" in template:
                weekday_char = groups[0]
                weekday_num = _WEEKDAY_MAP.get(weekday_char, "0")
                return template.replace("{_weekday}", weekday_num)

            # 通用格式化
            try:
                return template.format(*groups)
            except (IndexError, KeyError):
                continue

        return None

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

    # ------------------------------------------------------------------
    # 后台调度循环
    # ------------------------------------------------------------------

    def set_trigger_callback(
        self,
        callback: Callable[[CronTask], Awaitable[None]] | None,
    ) -> None:
        """设置任务触发时的回调函数.

        回调在每个调度周期内对到期任务逐一调用.
        若未设置回调, 到期任务仅更新 last_triggered / trigger_count.

        Args:
            callback: 异步回调函数, 接收 CronTask 参数.
        """
        self._trigger_callback = callback

    async def start(self) -> None:
        """启动后台调度循环.

        创建 asyncio 后台任务, 每隔 schedule_interval_seconds
        检查到期任务并触发. 重复调用幂等.
        """
        if self._running:
            logger.debug("CronManager scheduler already running")
            return
        self._running = True
        self._background_task = asyncio.create_task(
            self._schedule_loop(),
            name="cron_manager_schedule_loop",
        )
        logger.info(
            "CronManager scheduler started (interval=%.1fs)",
            self._schedule_interval,
        )

    async def stop(self) -> None:
        """停止后台调度循环.

        取消后台任务并等待其退出. 幂等调用.
        """
        if not self._running:
            return
        self._running = False
        if self._background_task is not None:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
            self._background_task = None
        logger.info("CronManager scheduler stopped")

    @property
    def is_running(self) -> bool:
        """后台调度循环是否正在运行."""
        return self._running

    async def _schedule_loop(self) -> None:
        """后台调度循环主逻辑.

        每隔 schedule_interval_seconds 检测到期任务,
        调用 mark_triggered 并执行回调.
        """
        logger.info("Schedule loop entered")
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Error in cron schedule tick")
            try:
                await asyncio.sleep(self._schedule_interval)
            except asyncio.CancelledError:
                raise

    async def _tick(self) -> None:
        """单次调度周期: 检测到期任务并触发."""
        due_tasks = await self.get_due_tasks()
        if not due_tasks:
            return

        sem = asyncio.Semaphore(self._max_concurrent_crons)

        async def _process(task: CronTask) -> None:
            async with sem:
                await self.mark_triggered(task.task_id)
                if self._trigger_callback is not None:
                    try:
                        await self._trigger_callback(task)
                    except Exception:
                        logger.exception(
                            "Cron trigger callback failed for task %s",
                            task.task_id,
                        )

        await asyncio.gather(*[_process(t) for t in due_tasks])
        logger.debug("Schedule tick: processed %d due tasks", len(due_tasks))


__all__ = [
    "CronManager",
    "CronTask",
]
