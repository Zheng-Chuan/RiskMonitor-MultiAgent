"""
问题管理器 - Agent 主动提问功能.

管理 Agent 与用户之间的问答交互,支持:
1. Agent 主动向用户提问
2. 等待用户回答 (支持超时)
3. 问题队列管理
4. 异步通知机制
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
import uuid

logger = logging.getLogger(__name__)


@dataclass
class PendingQuestion:
    """待回答的问题."""
    
    question_id: str
    agent_name: str
    question: str
    context: dict[str, Any]
    created_at: float
    answer: Optional[str] = None
    answered_at: Optional[float] = None
    status: str = "pending"  # pending, answered, timeout, cancelled
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典."""
        return {
            "question_id": self.question_id,
            "agent_name": self.agent_name,
            "question": self.question,
            "context": self.context,
            "created_at": self.created_at,
            "answer": self.answer,
            "answered_at": self.answered_at,
            "status": self.status,
        }


class QuestionManager:
    """
    问题管理器.
    
    核心功能:
    1. 向用户提问并等待回答
    2. 管理问题队列
    3. 支持超时处理
    4. 异步通知机制
    """
    
    def __init__(self) -> None:
        self._questions: dict[str, PendingQuestion] = {}
        self._answer_events: dict[str, asyncio.Event] = {}
        self._callbacks: list[Callable[[PendingQuestion], Any]] = []
    
    def register_callback(self, callback: Callable[[PendingQuestion], Any]) -> None:
        """
        注册问题回调.
        
        当有新问题时,会调用所有注册的回调函数.
        
        Args:
            callback: 回调函数,接收 PendingQuestion 参数
        """
        self._callbacks.append(callback)
        logger.debug(f"Registered question callback: {callback.__name__}")
    
    async def ask_user(
        self,
        agent_name: str,
        question: str,
        context: Optional[dict[str, Any]] = None,
        timeout_seconds: float = 300,
    ) -> str:
        """
        向用户提问并等待回答.
        
        Args:
            agent_name: 提问的 Agent 名称
            question: 问题内容
            context: 问题上下文
            timeout_seconds: 超时时间 (秒), 默认 5 分钟
            
        Returns:
            用户的回答,如果超时返回超时消息
        """
        question_id = str(uuid.uuid4())
        
        # 创建问题
        pending_question = PendingQuestion(
            question_id=question_id,
            agent_name=agent_name,
            question=question,
            context=context or {},
            created_at=time.time(),
        )
        
        self._questions[question_id] = pending_question
        
        # 创建事件用于等待回答
        event = asyncio.Event()
        self._answer_events[question_id] = event
        
        # 通知所有回调 (展示问题给用户)
        await self._notify_callbacks(pending_question)
        
        # 打印问题到控制台 (简单的 CLI 交互)
        print(f"\n{'='*60}")
        print(f"[{agent_name}] 提问:{question}")
        print(f"问题 ID: {question_id}")
        print(f"超时时间:{timeout_seconds}秒")
        print(f"{'='*60}\n")
        
        # 等待回答
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            pending_question.status = "timeout"
            logger.warning(f"Question {question_id} timeout after {timeout_seconds}s")
            return f"[超时] 用户未在 {timeout_seconds}秒内回答"
        
        # 获取回答
        answer = self._questions[question_id].answer
        if answer is None:
            return "[错误] 未获取到有效回答"
        
        logger.info(f"Question {question_id} answered: {answer[:50]}...")
        return answer
    
    async def submit_answer(self, question_id: str, answer: str) -> bool:
        """
        提交用户回答.
        
        Args:
            question_id: 问题 ID
            answer: 用户回答
            
        Returns:
            是否提交成功
        """
        if question_id not in self._questions:
            logger.error(f"Question not found: {question_id}")
            return False
        
        question = self._questions[question_id]
        question.answer = answer
        question.answered_at = time.time()
        question.status = "answered"
        
        # 触发事件,唤醒等待的 Agent
        if question_id in self._answer_events:
            self._answer_events[question_id].set()
        
        logger.info(f"Answer submitted for question {question_id}")
        return True
    
    def get_pending_questions(self) -> list[PendingQuestion]:
        """获取所有待回答的问题."""
        return [q for q in self._questions.values() if q.status == "pending"]
    
    def get_question(self, question_id: str) -> Optional[PendingQuestion]:
        """根据 ID 获取问题."""
        return self._questions.get(question_id)
    
    def get_all_questions(self) -> list[PendingQuestion]:
        """获取所有问题."""
        return list(self._questions.values())
    
    def cancel_question(self, question_id: str) -> bool:
        """
        取消问题.
        
        Args:
            question_id: 问题 ID
            
        Returns:
            是否取消成功
        """
        if question_id not in self._questions:
            return False
        
        question = self._questions[question_id]
        if question.status == "pending":
            question.status = "cancelled"
            
            # 触发事件,唤醒等待的 Agent
            if question_id in self._answer_events:
                self._answer_events[question_id].set()
            
            logger.info(f"Question {question_id} cancelled")
            return True
        
        return False
    
    async def _notify_callbacks(self, question: PendingQuestion) -> None:
        """通知所有回调."""
        for callback in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(question)
                else:
                    callback(question)
            except Exception as e:
                logger.error(f"Question callback error: {e}")
    
    def clear_answered_questions(self, max_age_seconds: float = 3600) -> int:
        """
        清理已回答的问题.
        
        Args:
            max_age_seconds: 最大保留时间 (秒)
            
        Returns:
            清理的问题数量
        """
        current_time = time.time()
        to_remove = []
        
        for qid, question in self._questions.items():
            if question.status in ["answered", "timeout", "cancelled"]:
                if question.answered_at and (current_time - question.answered_at) > max_age_seconds:
                    to_remove.append(qid)
        
        for qid in to_remove:
            del self._questions[qid]
            if qid in self._answer_events:
                del self._answer_events[qid]
        
        if to_remove:
            logger.info(f"Cleared {len(to_remove)} answered questions")
        
        return len(to_remove)


# 全局问题管理器实例
_question_manager: Optional[QuestionManager] = None


def get_question_manager() -> QuestionManager:
    """获取全局问题管理器实例."""
    global _question_manager
    if _question_manager is None:
        _question_manager = QuestionManager()
    return _question_manager


def reset_question_manager() -> None:
    """重置问题管理器 (用于测试)."""
    global _question_manager
    _question_manager = None


async def ask_user_question(
    agent_name: str,
    question: str,
    context: Optional[dict[str, Any]] = None,
    timeout_seconds: float = 300,
) -> str:
    """
    便捷函数:向用户提问.
    
    Args:
        agent_name: Agent 名称
        question: 问题内容
        context: 上下文
        timeout_seconds: 超时时间
        
    Returns:
        用户回答
    """
    manager = get_question_manager()
    return await manager.ask_user(
        agent_name=agent_name,
        question=question,
        context=context,
        timeout_seconds=timeout_seconds,
    )


async def answer_user_question(question_id: str, answer: str) -> bool:
    """
    便捷函数:提交用户回答.
    
    Args:
        question_id: 问题 ID
        answer: 用户回答
        
    Returns:
        是否提交成功
    """
    manager = get_question_manager()
    return await manager.submit_answer(question_id, answer)


__all__ = [
    "PendingQuestion",
    "QuestionManager",
    "get_question_manager",
    "reset_question_manager",
    "ask_user_question",
    "answer_user_question",
]
