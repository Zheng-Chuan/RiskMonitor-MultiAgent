"""CronManager 后台调度循环和增强自然语言解析测试."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from riskmonitor_multiagent.scheduling.cron_manager import CronManager, CronTask


# ---------------------------------------------------------------------------
# 后台调度循环测试
# ---------------------------------------------------------------------------


class TestCronManagerBackgroundLoop:
    """CronManager 后台调度循环测试."""

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        """start/stop 正常启停."""
        manager = CronManager(schedule_interval_seconds=0.05)
        assert manager.is_running is False

        await manager.start()
        assert manager.is_running is True

        await manager.stop()
        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_start_idempotent(self) -> None:
        """重复 start 幂等."""
        manager = CronManager(schedule_interval_seconds=0.05)
        await manager.start()
        await manager.start()  # 不应报错
        assert manager.is_running is True
        await manager.stop()

    @pytest.mark.asyncio
    async def test_stop_idempotent(self) -> None:
        """重复 stop 幂等."""
        manager = CronManager(schedule_interval_seconds=0.05)
        await manager.stop()  # 未启动时 stop 不报错
        assert manager.is_running is False

    @pytest.mark.asyncio
    async def test_background_loop_triggers_due_tasks(self) -> None:
        """后台循环自动触发到期任务."""
        manager = CronManager(schedule_interval_seconds=0.05)
        task = await manager.create_task({
            "name": "自动触发测试",
            "cron_expression": "0 0 * * *",
            "task_template": {"intent": "test"},
            "trigger_config": {},
        })

        callback = AsyncMock()
        manager.set_trigger_callback(callback)

        await manager.start()
        # 等待至少一个调度周期
        await asyncio.sleep(0.2)
        await manager.stop()

        assert task.trigger_count >= 1
        callback.assert_awaited()
        # 回调接收 CronTask 参数
        called_task = callback.await_args.args[0]
        assert called_task.task_id == task.task_id

    @pytest.mark.asyncio
    async def test_background_loop_without_callback(self) -> None:
        """未设置回调时, 到期任务仍会更新 trigger_count."""
        manager = CronManager(schedule_interval_seconds=0.05)
        task = await manager.create_task({
            "name": "无回调测试",
            "cron_expression": "0 0 * * *",
            "task_template": {},
            "trigger_config": {},
        })

        await manager.start()
        await asyncio.sleep(0.2)
        await manager.stop()

        assert task.trigger_count >= 1
        assert task.last_triggered is not None

    @pytest.mark.asyncio
    async def test_callback_exception_does_not_crash_loop(self) -> None:
        """回调异常不影响调度循环继续运行."""
        manager = CronManager(schedule_interval_seconds=0.05)
        await manager.create_task({
            "name": "异常回调测试",
            "cron_expression": "0 0 * * *",
            "task_template": {},
            "trigger_config": {},
        })

        async def _failing_callback(task: CronTask) -> None:
            raise RuntimeError("intentional test error")

        manager.set_trigger_callback(_failing_callback)

        await manager.start()
        await asyncio.sleep(0.2)
        # 循环应该仍在运行
        assert manager.is_running is True
        await manager.stop()

    @pytest.mark.asyncio
    async def test_set_trigger_callback_none(self) -> None:
        """设置 None 回调清除回调."""
        manager = CronManager()
        manager.set_trigger_callback(AsyncMock())
        assert manager._trigger_callback is not None
        manager.set_trigger_callback(None)
        assert manager._trigger_callback is None


# ---------------------------------------------------------------------------
# 增强自然语言解析测试
# ---------------------------------------------------------------------------


class TestEnhancedNaturalLanguageParsing:
    """增强自然语言 cron 解析测试."""

    def setup_method(self) -> None:
        self.manager = CronManager()

    # -- 关键词匹配 (扩展部分) --

    def test_parse_opening_time(self) -> None:
        """开盘前 → 工作日 9:30."""
        assert self.manager.parse_natural_language("开盘前") == "30 9 * * 1-5"
        assert self.manager.parse_natural_language("每天开盘前") == "30 9 * * 1-5"

    def test_parse_closing_time(self) -> None:
        """收盘后 → 工作日 18:00."""
        assert self.manager.parse_natural_language("收盘后") == "0 18 * * 1-5"

    def test_parse_noon(self) -> None:
        """中午 → 12:00."""
        assert self.manager.parse_natural_language("中午") == "0 12 * * *"
        assert self.manager.parse_natural_language("每天中午") == "0 12 * * *"

    def test_parse_midnight(self) -> None:
        """午夜 → 0:00."""
        assert self.manager.parse_natural_language("午夜") == "0 0 * * *"

    def test_parse_daily_alias(self) -> None:
        """每日 → 每天."""
        assert self.manager.parse_natural_language("每日") == "0 0 * * *"

    def test_parse_half_hour(self) -> None:
        """每半小时 → */30."""
        assert self.manager.parse_natural_language("每半小时") == "*/30 * * * *"
        assert self.manager.parse_natural_language("半小时") == "*/30 * * * *"

    def test_parse_specific_weekday(self) -> None:
        """每周一 ~ 每周日."""
        assert self.manager.parse_natural_language("每周一") == "0 0 * * 1"
        assert self.manager.parse_natural_language("每周三") == "0 0 * * 3"
        assert self.manager.parse_natural_language("每周五") == "0 0 * * 5"
        assert self.manager.parse_natural_language("每周日") == "0 0 * * 0"

    # -- 正则模式匹配 --

    def test_parse_every_n_minutes(self) -> None:
        """每隔N分钟."""
        assert self.manager.parse_natural_language("每隔5分钟") == "*/5 * * * *"
        assert self.manager.parse_natural_language("每10分钟") == "*/10 * * * *"
        assert self.manager.parse_natural_language("每 15 分钟") == "*/15 * * * *"

    def test_parse_every_n_hours(self) -> None:
        """每隔N小时."""
        assert self.manager.parse_natural_language("每隔2小时") == "0 */2 * * *"
        assert self.manager.parse_natural_language("每6小时") == "0 */6 * * *"

    def test_parse_daily_specific_time(self) -> None:
        """每天X点."""
        assert self.manager.parse_natural_language("每天9点") == "0 9 * * *"
        assert self.manager.parse_natural_language("每天18点") == "0 18 * * *"

    def test_parse_daily_specific_time_and_minute(self) -> None:
        """每天X点Y分."""
        assert self.manager.parse_natural_language("每天9点30分") == "30 9 * * *"
        assert self.manager.parse_natural_language("每天14点15分") == "15 14 * * *"

    def test_parse_afternoon_time(self) -> None:
        """下午X点 → 自动 +12."""
        assert self.manager.parse_natural_language("下午3点") == "0 15 * * *"
        assert self.manager.parse_natural_language("下午6点") == "0 18 * * *"

    def test_parse_morning_time(self) -> None:
        """上午X点."""
        assert self.manager.parse_natural_language("上午9点") == "0 9 * * *"
        assert self.manager.parse_natural_language("上午10点") == "0 10 * * *"

    def test_parse_weekday_specific_time(self) -> None:
        """每个工作日X点."""
        assert self.manager.parse_natural_language("每个工作日9点") == "0 9 * * 1-5"
        assert self.manager.parse_natural_language("工作日18点") == "0 18 * * 1-5"

    def test_parse_every_n_days(self) -> None:
        """每N天."""
        assert self.manager.parse_natural_language("每3天") == "0 0 */3 * *"
        assert self.manager.parse_natural_language("每7天") == "0 0 */7 * *"

    def test_parse_weekday_chinese(self) -> None:
        """周X → 对应星期."""
        assert self.manager.parse_natural_language("周一") == "0 0 * * 1"
        assert self.manager.parse_natural_language("周三") == "0 0 * * 3"
        assert self.manager.parse_natural_language("周五") == "0 0 * * 5"
        assert self.manager.parse_natural_language("周日") == "0 0 * * 0"
        assert self.manager.parse_natural_language("周天") == "0 0 * * 0"

    def test_parse_unknown_fallback(self) -> None:
        """无法识别的文本兜底为每天."""
        assert self.manager.parse_natural_language("随机描述无法识别") == "0 0 * * *"
        assert self.manager.parse_natural_language("") == "0 0 * * *"

    # -- 向后兼容: 原有测试用例仍需通过 --

    def test_original_keywords_still_work(self) -> None:
        """原有自然语言关键词仍然有效."""
        cases = [
            ("每天", "0 0 * * *"),
            ("每个工作日", "0 0 * * 1-5"),
            ("工作日", "0 0 * * 1-5"),
            ("每周", "0 0 * * 0"),
            ("每小时", "0 * * * *"),
            ("每天收盘后", "0 18 * * 1-5"),
            ("每个工作日收盘后", "0 18 * * 1-5"),
            ("不认识的关键词", "0 0 * * *"),
        ]
        for desc, expected in cases:
            result = self.manager.parse_natural_language(desc)
            assert result == expected, f"parse_natural_language({desc!r}) = {result!r}, expected {expected!r}"
