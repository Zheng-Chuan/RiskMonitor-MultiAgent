#!/usr/bin/env python3
"""
测试 Agent 主动提问功能.

演示如何通过 CLI 与 Agent 进行问答交互.
"""

import asyncio
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))
sys.path.insert(0, str(project_root))

from riskmonitor_multiagent.proactive_agents import (
    get_question_manager,
    ask_user_question,
    answer_user_question,
)


async def test_ask_user():
    """测试主动提问功能."""
    print("=" * 60)
    print("测试 Agent 主动提问功能")
    print("=" * 60)
    
    # 获取问题管理器
    manager = get_question_manager()
    
    # 注册回调 (用于展示问题)
    def on_new_question(question):
        print(f"\n📢 新问题通知:")
        print(f"   ID: {question.question_id}")
        print(f"   Agent: {question.agent_name}")
        print(f"   问题:{question.question}")
    
    manager.register_callback(on_new_question)
    
    # 测试 1: 正常提问
    print("\n" + "=" * 60)
    print("测试 1: 正常提问 (等待用户输入)")
    print("=" * 60)
    
    question_task = asyncio.create_task(
        ask_user_question(
            agent_name="test_agent",
            question="请问 1+1 等于几?",
            context={"task_id": "test_001"},
            timeout_seconds=30,
        )
    )
    
    # 等待 2 秒后模拟用户输入
    await asyncio.sleep(2)
    
    # 获取问题列表
    pending = manager.get_pending_questions()
    if pending:
        question_id = pending[0].question_id
        print(f"\n模拟用户输入...")
        await answer_user_question(question_id, "等于 2")
    
    # 等待回答
    answer = await question_task
    print(f"\n✅ Agent 收到回答:{answer}")
    
    # 测试 2: 超时处理
    print("\n" + "=" * 60)
    print("测试 2: 超时处理 (5 秒超时)")
    print("=" * 60)
    
    question_task2 = asyncio.create_task(
        ask_user_question(
            agent_name="test_agent",
            question="这是一个超时测试问题",
            context={"task_id": "test_002"},
            timeout_seconds=5,
        )
    )
    
    # 不输入答案,等待超时
    answer2 = await question_task2
    print(f"\n⏰ 超时结果:{answer2}")
    
    # 测试 3: 查看历史记录
    print("\n" + "=" * 60)
    print("测试 3: 查看所有问题历史")
    print("=" * 60)
    
    all_questions = manager.get_all_questions()
    print(f"\n总问题数:{len(all_questions)}")
    for q in all_questions:
        print(f"\n问题 {q.question_id[:8]}...:")
        print(f"  Agent: {q.agent_name}")
        print(f"  问题:{q.question}")
        print(f"  状态:{q.status}")
        print(f"  回答:{q.answer or '无'}")
    
    print("\n" + "=" * 60)
    print("✅ 所有测试完成!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = asyncio.run(test_ask_user())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试中断")
        sys.exit(1)
