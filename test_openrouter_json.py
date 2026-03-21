#!/usr/bin/env python3
"""测试 OpenRouter 的 JSON Mode 是否正常工作."""

import asyncio
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from riskmonitor_multiagent.llm.llm_client import LlmClient


async def test_json_mode():
    """测试 JSON Mode."""
    print("=" * 60)
    print("测试 OpenRouter JSON Mode")
    print("=" * 60)
    
    client = LlmClient()
    
    # 测试 1: 不使用 JSON Mode
    print("\n[测试 1] 不使用 JSON Mode（普通模式）")
    print("-" * 60)
    try:
        response = await client.chat_completions(
            messages=[
                {"role": "system", "content": "你是一个助手。"},
                {"role": "user", "content": "用一句话介绍你自己。"},
            ],
            model="deepseek/deepseek-chat",
            temperature=0.2,
            max_tokens=100,
        )
        
        from riskmonitor_multiagent.llm.llm_client import extract_first_text
        text = extract_first_text(response)
        print(f"✅ 成功（普通文本）: {text[:100]}")
    except Exception as e:
        print(f"❌ 失败：{e}")
    
    # 测试 2: 使用 JSON Mode
    print("\n[测试 2] 使用 JSON Mode（强制 JSON 输出）")
    print("-" * 60)
    text = None
    try:
        response = await client.chat_completions(
            messages=[
                {"role": "system", "content": "你必须输出严格的 JSON 格式。"},
                {"role": "user", "content": '返回一个包含 name, age, city 三个字段的 JSON 对象，name="张三", age=25, city="北京"'},
            ],
            model="deepseek/deepseek-chat",
            temperature=0.0,
            max_tokens=200,
            response_format={"type": "json_object"},
        )
        
        from riskmonitor_multiagent.llm.llm_client import extract_first_text
        import json
        
        text = extract_first_text(response)
        print(f"原始输出：{text}")
        
        # 尝试解析 JSON
        data = json.loads(text)
        print(f"✅ 成功解析 JSON: {data}")
        
        # 验证字段
        assert "name" in data, "缺少 name 字段"
        assert "age" in data, "缺少 age 字段"
        assert "city" in data, "缺少 city 字段"
        print(f"✅ 所有必需字段都存在")
        
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析失败：{e}")
        print(f"   原始输出：{text}")
    except Exception as e:
        print(f"❌ 失败：{e}")
    
    # 测试 3: 使用 JSON Schema（结构化输出）
    print("\n[测试 3] 使用 JSON Schema（最严格的格式控制）")
    print("-" * 60)
    text = None
    try:
        json_schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
                "city": {"type": "string"}
            },
            "required": ["name", "age", "city"],
            "additionalProperties": False
        }
        
        response = await client.chat_completions(
            messages=[
                {"role": "system", "content": "你必须输出符合 JSON Schema 的严格格式。"},
                {"role": "user", "content": '创建一个人物，name="李四", age=30, city="上海"'},
            ],
            model="deepseek/deepseek-chat",
            temperature=0.0,
            max_tokens=200,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "person",
                    "schema": json_schema
                }
            },
        )
        
        text = extract_first_text(response)
        print(f"原始输出：{text}")
        
        data = json.loads(text)
        print(f"✅ 成功解析 JSON Schema 输出：{data}")
        
        # 验证字段类型
        assert isinstance(data["name"], str), "name 应该是字符串"
        assert isinstance(data["age"], int), "age 应该是整数"
        assert isinstance(data["city"], str), "city 应该是字符串"
        print(f"✅ 所有字段类型都正确")
        
    except Exception as e:
        print(f"❌ 失败：{e}")
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_json_mode())
