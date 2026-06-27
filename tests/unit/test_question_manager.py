from __future__ import annotations

import asyncio

import pytest

from riskmonitor_multiagent.proactive_agents.question_manager import (
    QuestionManager,
    answer_user_question,
    ask_user_question,
    get_question_manager,
    reset_question_manager,
)


@pytest.mark.asyncio
async def test_question_manager_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = QuestionManager()
    seen: list[str] = []

    async def async_callback(question) -> None:
        seen.append(question.question)

    def sync_callback(question) -> None:
        seen.append(question.agent_name)

    manager.register_callback(async_callback)
    manager.register_callback(sync_callback)
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    task = asyncio.create_task(
        manager.ask_user(
            agent_name="risk_analyst",
            question="是否继续?",
            context={"desk": "EQD"},
            timeout_seconds=1.0,
        )
    )
    await asyncio.sleep(0)
    pending = manager.get_pending_questions()
    assert len(pending) == 1
    qid = pending[0].question_id
    assert await manager.submit_answer(qid, "继续") is True

    answer = await task
    question = manager.get_question(qid)
    assert answer == "继续"
    assert question is not None and question.status == "answered"
    assert question.to_dict()["context"] == {"desk": "EQD"}
    assert seen == ["是否继续?", "risk_analyst"]


@pytest.mark.asyncio
async def test_question_manager_timeout_cancel_and_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = QuestionManager()
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    timed_out = await manager.ask_user(
        agent_name="system_engineer",
        question="超时测试",
        timeout_seconds=0.01,
    )
    assert "[超时]" in timed_out
    timeout_question = manager.get_all_questions()[0]
    assert timeout_question.status == "timeout"
    assert manager.clear_answered_questions(max_age_seconds=0) == 0

    wait_task = asyncio.create_task(
        manager.ask_user(
            agent_name="manager",
            question="取消测试",
            timeout_seconds=1.0,
        )
    )
    await asyncio.sleep(0)
    pending = manager.get_pending_questions()
    assert len(pending) == 1
    qid = pending[0].question_id
    assert manager.cancel_question(qid) is True
    cancelled_answer = await wait_task
    assert cancelled_answer == "[错误] 未获取到有效回答"
    assert manager.cancel_question("missing") is False
    assert manager.submit_answer("missing", "x") is not None
    assert await manager.submit_answer("missing", "x") is False

    cancelled_question = manager.get_question(qid)
    assert cancelled_question is not None
    cancelled_question.answered_at = cancelled_question.created_at - 10
    timeout_question.answered_at = timeout_question.created_at - 10
    cleared = manager.clear_answered_questions(max_age_seconds=0)
    assert cleared == 2
    assert manager.get_all_questions() == []


@pytest.mark.asyncio
async def test_question_manager_callback_error_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = QuestionManager()
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)

    def failing_callback(question) -> None:
        raise RuntimeError(f"boom:{question.question_id}")

    manager.register_callback(failing_callback)

    task = asyncio.create_task(
        manager.ask_user(agent_name="moderator", question="问题", timeout_seconds=1.0)
    )
    await asyncio.sleep(0)
    qid = manager.get_pending_questions()[0].question_id
    assert await manager.submit_answer(qid, "收到") is True
    assert await task == "收到"


@pytest.mark.asyncio
async def test_question_manager_global_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_question_manager()
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: None)
    manager = get_question_manager()
    assert manager is get_question_manager()

    task = asyncio.create_task(
        ask_user_question(
            agent_name="intent_agent",
            question="全局 helper 是否工作?",
            timeout_seconds=1.0,
        )
    )
    await asyncio.sleep(0)
    qid = manager.get_pending_questions()[0].question_id
    assert await answer_user_question(qid, "工作正常") is True
    assert await task == "工作正常"
    reset_question_manager()
