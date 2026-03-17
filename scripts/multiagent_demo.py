#!/usr/bin/env python3
"""
多 Agent 协作示例脚本.

演示如何使用 Message Bus、Moderator 和多 Agent 协作工作流.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SRC_ROOT = _PROJECT_ROOT / "src"
for p in (_PROJECT_ROOT, _SRC_ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from riskmonitor_multiagent.orchestration.multiagent_workflow import (
    MultiAgentCollaborationWorkflow,
    get_multi_agent_workflow,
    reset_multi_agent_workflow,
)
from riskmonitor_multiagent.orchestration.message_bus import (
    MessageBus,
    get_message_bus,
    reset_message_bus,
)
from riskmonitor_multiagent.services.logging_service import configure_logging, new_request_id


async def demo_simple_task(workflow: MultiAgentCollaborationWorkflow) -> None:
    """演示简单任务."""
    print(f"\n{'=' * 80}")
    print("演示 1: 简单任务")
    print(f"{'=' * 80}")

    task = {
        "task_id": new_request_id(),
        "session_id": "demo_session",
        "source": "human",
        "payload": {
            "content": "查询 desk 'Equities' 当前头寸"
        }
    }

    print(f"\n任务: {task['payload']['content']}")
    print(f"Task ID: {task['task_id']}")
    print(f"\n开始协作...")

    try:
        result = await workflow.run(task)
        print(f"\n协作完成!")
        print(f"结果状态: {result.get('status')}")
        print(f"消息历史长度: {len(result.get('conversation_history', []))}")
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)


async def demo_medium_task(workflow: MultiAgentCollaborationWorkflow) -> None:
    """演示中等复杂度任务."""
    print(f"\n{'=' * 80}")
    print("演示 2: 中等复杂度任务")
    print(f"{'=' * 80}")

    task = {
        "task_id": new_request_id(),
        "session_id": "demo_session",
        "source": "human",
        "payload": {
            "content": "desk 'Equities' 的 delta 疑似 breach，请分析并生成报告"
        }
    }

    print(f"\n任务: {task['payload']['content']}")
    print(f"Task ID: {task['task_id']}")
    print(f"\n开始协作...")

    try:
        result = await workflow.run(task)
        print(f"\n协作完成!")
        print(f"结果状态: {result.get('status')}")
        print(f"消息历史长度: {len(result.get('conversation_history', []))}")
    except Exception as e:
        print(f"\n错误: {e}", file=sys.stderr)


async def main() -> None:
    """主函数."""
    configure_logging()

    parser = argparse.ArgumentParser(prog="multiagent_demo", description="多 Agent 协作演示")
    parser.add_argument("--demo", type=str, default="all", choices=["simple", "medium", "all"], help="选择演示类型")
    args = parser.parse_args()

    print(f"{'=' * 80}")
    print("RiskMonitor MultiAgent - 多 Agent 协作演示")
    print(f"{'=' * 80}")

    # 重置状态
    reset_message_bus()
    reset_multi_agent_workflow()

    # 获取工作流
    workflow = get_multi_agent_workflow()

    print(f"\nMessage Bus: 已初始化")
    print(f"Moderator Agent: 已初始化")
    print(f"MultiAgent Workflow: 已初始化")

    # 运行演示
    if args.demo in ["simple", "all"]:
        await demo_simple_task(workflow)

    if args.demo in ["medium", "all"]:
        await demo_medium_task(workflow)

    print(f"\n{'=' * 80}")
    print("演示完成!")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    asyncio.run(main())
