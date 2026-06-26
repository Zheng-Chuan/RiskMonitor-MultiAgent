"""CronManager 单元测试."""

from __future__ import annotations

import time

import pytest

from riskmonitor_multiagent.scheduling.cron_manager import CronManager, CronTask
from riskmonitor_multiagent.scheduling.cron_templates import FINANCIAL_CRON_TEMPLATES


@pytest.mark.asyncio
async def test_create_and_get_task() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "每日风控巡检",
        "cron_expression": "0 18 * * 1-5",
        "natural_language": "每个工作日收盘后",
        "task_template": {"intent": "daily_check", "content": {"scope": "all"}},
        "trigger_config": {"entry_type": "system_event", "priority": "normal"},
    })

    assert task.task_id.startswith("cron_")
    assert task.name == "每日风控巡检"
    assert task.cron_expression == "0 18 * * 1-5"
    assert task.natural_language == "每个工作日收盘后"
    assert task.task_template["intent"] == "daily_check"
    assert task.trigger_config["priority"] == "normal"
    assert task.enabled is True
    assert task.created_at > 0
    assert task.last_triggered is None
    assert task.trigger_count == 0
    assert task.max_recursion_depth == 3

    fetched = await manager.get_task(task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id
    assert fetched.name == task.name


@pytest.mark.asyncio
async def test_create_task_with_natural_language_only() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "每小时巡检",
        "natural_language": "每小时",
        "task_template": {"intent": "hourly_check"},
        "trigger_config": {},
    })
    assert task.cron_expression == "0 * * * *"


@pytest.mark.asyncio
async def test_create_task_invalid_cron_raises() -> None:
    manager = CronManager()
    with pytest.raises(ValueError, match="invalid cron expression"):
        await manager.create_task({
            "name": "bad",
            "cron_expression": "99 99 99 99 99",
            "task_template": {},
            "trigger_config": {},
        })


@pytest.mark.asyncio
async def test_create_task_missing_name_raises() -> None:
    manager = CronManager()
    with pytest.raises(ValueError, match="task name is required"):
        await manager.create_task({
            "cron_expression": "0 0 * * *",
            "task_template": {},
            "trigger_config": {},
        })


@pytest.mark.asyncio
async def test_pause_resume_and_due_tasks() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "测试暂停",
        "cron_expression": "0 * * * *",
        "task_template": {"intent": "test"},
        "trigger_config": {},
    })

    paused = await manager.pause_task(task.task_id)
    assert paused is True
    assert task.enabled is False

    due = await manager.get_due_tasks()
    assert all(t.task_id != task.task_id for t in due)

    resumed = await manager.resume_task(task.task_id)
    assert resumed is True
    assert task.enabled is True

    due = await manager.get_due_tasks()
    assert any(t.task_id == task.task_id for t in due)


@pytest.mark.asyncio
async def test_pause_nonexistent_returns_false() -> None:
    manager = CronManager()
    assert await manager.pause_task("cron_nonexistent") is False
    assert await manager.resume_task("cron_nonexistent") is False


@pytest.mark.asyncio
async def test_delete_task() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "待删除",
        "cron_expression": "0 0 * * *",
        "task_template": {},
        "trigger_config": {},
    })

    deleted = await manager.delete_task(task.task_id)
    assert deleted is True

    fetched = await manager.get_task(task.task_id)
    assert fetched is None

    deleted_again = await manager.delete_task(task.task_id)
    assert deleted_again is False


@pytest.mark.asyncio
async def test_list_tasks_filter() -> None:
    manager = CronManager()
    t1 = await manager.create_task({
        "name": "任务1",
        "cron_expression": "0 0 * * *",
        "task_template": {},
        "trigger_config": {},
    })
    t2 = await manager.create_task({
        "name": "任务2",
        "cron_expression": "0 12 * * *",
        "task_template": {},
        "trigger_config": {},
    })
    await manager.pause_task(t2.task_id)

    all_tasks = await manager.list_tasks()
    assert len(all_tasks) == 2

    enabled_tasks = await manager.list_tasks(enabled=True)
    assert len(enabled_tasks) == 1
    assert enabled_tasks[0].task_id == t1.task_id

    disabled_tasks = await manager.list_tasks(enabled=False)
    assert len(disabled_tasks) == 1
    assert disabled_tasks[0].task_id == t2.task_id


def test_parse_natural_language_various_keywords() -> None:
    manager = CronManager()
    cases = [
        ("每天", "0 0 * * *"),
        ("每个工作日", "0 0 * * 1-5"),
        ("工作日", "0 0 * * 1-5"),
        ("每周", "0 0 * * 0"),
        ("每小时", "0 * * * *"),
        ("每天收盘后", "0 18 * * 1-5"),
        ("每个工作日收盘后", "0 18 * * 1-5"),
        ("不认识的关键词", "0 0 * * *"),
        ("", "0 0 * * *"),
    ]
    for desc, expected in cases:
        result = manager.parse_natural_language(desc)
        assert result == expected, f"parse_natural_language({desc!r}) = {result!r}, expected {expected!r}"


def test_validate_cron_expression_valid() -> None:
    manager = CronManager()
    valid_exprs = [
        "0 0 * * *",
        "0 18 * * 1-5",
        "0 * * * *",
        "0 9 * * 1",
        "30 14 * * *",
        "*/5 * * * *",
        "0 0 1 * *",
        "0 0 1 1 *",
        "0,30 * * * *",
        "0 0 * * 0-6",
        "0 0 * * 7",
        "15 9 1,15 * *",
    ]
    for expr in valid_exprs:
        assert manager.validate_cron_expression(expr), f"Expected valid: {expr}"


def test_validate_cron_expression_invalid() -> None:
    manager = CronManager()
    invalid_exprs = [
        "",
        "0 0",
        "0 0 * * * *",
        "60 0 * * *",
        "0 25 * * *",
        "0 0 32 * *",
        "0 0 * 13 *",
        "0 0 * * 8",
        "abc 0 * * *",
        "0 0 - * *",
    ]
    for expr in invalid_exprs:
        assert not manager.validate_cron_expression(expr), f"Expected invalid: {expr}"


@pytest.mark.asyncio
async def test_check_recursion_within_limit() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "递归测试",
        "cron_expression": "0 0 * * *",
        "task_template": {},
        "trigger_config": {},
        "max_recursion_depth": 3,
    })

    assert manager.check_recursion(task.task_id, 0) is True
    assert manager.check_recursion(task.task_id, 1) is True
    assert manager.check_recursion(task.task_id, 2) is True
    assert manager.check_recursion(task.task_id, 3) is True
    assert manager.check_recursion(task.task_id, 4) is False
    assert manager.check_recursion(task.task_id, 5) is False


def test_check_recursion_nonexistent_task() -> None:
    manager = CronManager()
    assert manager.check_recursion("cron_nonexistent", 0) is False


@pytest.mark.asyncio
async def test_get_and_reset_recursion_depth() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "递归深度",
        "cron_expression": "0 0 * * *",
        "task_template": {},
        "trigger_config": {},
    })

    manager.check_recursion(task.task_id, 2)
    assert manager.get_recursion_depth(task.task_id) == 2

    manager.reset_recursion(task.task_id)
    assert manager.get_recursion_depth(task.task_id) == 0


@pytest.mark.asyncio
async def test_mark_triggered_increments_count() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "触发计数",
        "cron_expression": "0 * * * *",
        "task_template": {},
        "trigger_config": {},
    })

    assert task.trigger_count == 0
    assert task.last_triggered is None

    await manager.mark_triggered(task.task_id)
    assert task.trigger_count == 1
    assert task.last_triggered is not None
    first_triggered = task.last_triggered

    time.sleep(0.01)

    await manager.mark_triggered(task.task_id)
    assert task.trigger_count == 2
    assert task.last_triggered is not None
    assert task.last_triggered > first_triggered


@pytest.mark.asyncio
async def test_mark_triggered_nonexistent_no_error() -> None:
    manager = CronManager()
    await manager.mark_triggered("cron_nonexistent")


@pytest.mark.asyncio
async def test_get_due_tasks_never_triggered() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "首次触发",
        "cron_expression": "0 0 * * *",
        "task_template": {},
        "trigger_config": {},
    })

    due = await manager.get_due_tasks()
    assert any(t.task_id == task.task_id for t in due)


@pytest.mark.asyncio
async def test_get_due_tasks_recently_triggered_excluded() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "刚触发",
        "cron_expression": "0 0 * * *",
        "task_template": {},
        "trigger_config": {},
    })

    await manager.mark_triggered(task.task_id)

    due = await manager.get_due_tasks()
    assert all(t.task_id != task.task_id for t in due)


@pytest.mark.asyncio
async def test_get_due_tasks_with_custom_now_ms() -> None:
    manager = CronManager()
    task = await manager.create_task({
        "name": "自定义时间",
        "cron_expression": "0 * * * *",
        "task_template": {},
        "trigger_config": {},
    })

    await manager.mark_triggered(task.task_id)
    last = task.last_triggered
    assert last is not None

    due = await manager.get_due_tasks(now_ms=last + 30 * 60 * 1000)
    assert all(t.task_id != task.task_id for t in due)

    due = await manager.get_due_tasks(now_ms=last + 61 * 60 * 1000)
    assert any(t.task_id == task.task_id for t in due)


def test_financial_cron_templates_structure() -> None:
    assert len(FINANCIAL_CRON_TEMPLATES) == 3
    for template in FINANCIAL_CRON_TEMPLATES:
        assert "name" in template
        assert "natural_language" in template
        assert "cron_expression" in template
        assert "task_template" in template
        assert "trigger_config" in template
        assert isinstance(template["task_template"], dict)
        assert isinstance(template["trigger_config"], dict)

        manager = CronManager()
        assert manager.validate_cron_expression(template["cron_expression"])


@pytest.mark.asyncio
async def test_financial_templates_can_create_tasks() -> None:
    manager = CronManager()
    for template in FINANCIAL_CRON_TEMPLATES:
        task = await manager.create_task(dict(template))
        assert task.name == template["name"]
        assert task.cron_expression == template["cron_expression"]
        assert task.task_template == template["task_template"]
