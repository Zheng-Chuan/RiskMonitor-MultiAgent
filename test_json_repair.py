#!/usr/bin/env python3
"""测试智能修复重试机制."""

import asyncio
import json
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from riskmonitor_multiagent.agents.base import BaseAgent
from riskmonitor_multiagent.llm.llm_client import LlmClient


async def test_json_repair():
    """测试 JSON 修复机制."""
    print("=" * 60)
    print("测试智能修复重试机制")
    print("=" * 60)
    
    # 创建一个测试 Agent
    agent = BaseAgent(
        name="test_repair",
        system_prompt="你是一个 JSON 生成助手。你必须输出严格的 JSON 格式。",
        client=LlmClient(),
        model="deepseek/deepseek-chat",
    )
    
    # 测试用例 1：正常请求（应该成功）
    print("\n[测试 1] 正常请求（预期成功）")
    print("-" * 60)
    try:
        result = await agent.ask_json(
            user_prompt='返回一个包含 name, age, city 的 JSON，name="张三", age=25, city="北京"',
            fallback={"error": "failed"},
            temperature=0.2,
            max_tokens=200,
        )
        print(f"✅ 成功：{result.output}")
    except Exception as e:
        print(f"❌ 失败：{e}")
    
    # 测试用例 2：模拟格式错误（测试修复机制）
    print("\n[测试 2] 模拟格式错误（测试修复）")
    print("-" * 60)
    print("这个测试会故意生成一个有格式错误的 JSON，然后让 LLM 修复它")
    print("观察日志中的修复过程...")
    
    # 创建一个会生成错误 JSON 的 prompt
    result = await agent.ask_json(
        user_prompt="""请生成一个复杂的 JSON 对象，包含以下字段:
- name: 字符串
- age: 整数
- city: 字符串
- hobbies: 数组
- address: 对象（包含 street, zip）

注意：这个 JSON 会比较复杂，请确保格式完全正确。""",
        fallback={"error": "failed"},
        temperature=0.7,  # 高温度更容易出错
        max_tokens=500,
    )
    print(f"✅ 成功：{json.dumps(result.output, indent=2, ensure_ascii=False)}")
    
    # 测试用例 3：连续多次请求（测试稳定性）
    print("\n[测试 3] 连续 5 次请求（测试稳定性）")
    print("-" * 60)
    success_count = 0
    fail_count = 0
    
    for i in range(5):
        try:
            result = await agent.ask_json(
                user_prompt=f'生成第{i+1}个 JSON，包含 id={i+1} 和 value="test{i+1}"',
                fallback={"error": "failed"},
                temperature=0.2,
                max_tokens=100,
            )
            success_count += 1
            print(f"  第{i+1}次：✅ 成功")
        except Exception as e:
            fail_count += 1
            print(f"  第{i+1}次：❌ 失败 - {e}")
    
    print(f"\n成功率：{success_count}/5 = {success_count * 20}%")
    if fail_count > 0:
        print(f"失败率：{fail_count}/5 = {fail_count * 20}%")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_json_repair())
