#!/usr/bin/env python3
"""验证 LLM 连接与配置.

用法:
  python scripts/check_llm_connection.py

要求:
  - 项目根目录 .env 中设置 LLM_API_KEY=你的密钥
  - 本项目默认使用兼容 OpenAI Chat Completions 的 LLM 提供方
  - 切勿将 API Key 提交到 git 或粘贴到聊天
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = _REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# 确保加载 .env
from riskmonitor_multiagent import config  # noqa: E402
from riskmonitor_multiagent.llm.llm_client import LlmClient  # noqa: E402
from riskmonitor_multiagent.llm.llm_client import extract_first_text  # noqa: E402


async def main() -> int:
    try:
        api_key = config.get_llm_api_key()
    except ValueError:
        print("错误: 未配置 LLM_API_KEY", file=sys.stderr)
        print("请在项目根目录创建 .env 文件并添加: LLM_API_KEY=你的密钥", file=sys.stderr)
        print("可复制 .env.example 为 .env 后填写.切勿将密钥提交到 git 或粘贴到聊天.", file=sys.stderr)
        return 1

    if not api_key or len(api_key) < 10:
        print("错误: LLM_API_KEY 过短或为空", file=sys.stderr)
        return 1

    model = config.get_llm_model()
    base_url = config.get_llm_base_url()
    print(f"Base URL: {base_url}")
    print(f"Model:   {model}")
    print("正在发送一条测试请求...")

    client = LlmClient()
    try:
        resp = await client.chat_completions(
            messages=[
                {"role": "user", "content": "Reply with exactly: {\"ok\": true}"},
            ],
            model=model,
            temperature=0,
            max_tokens=64,
        )
    except Exception as e:
        print(f"请求失败: {e}", file=sys.stderr)
        return 1

    usage = resp.get("usage") if isinstance(resp, dict) else None
    text = extract_first_text(resp)
    print("响应内容:", text[:200] + ("..." if len(text) > 200 else ""))
    if isinstance(usage, dict):
        print("Token 使用:", json.dumps(usage, ensure_ascii=False))
    print("OK: 当前 LLM 提供方连接正常, 可以运行 make eval-run 等进行带真实调用的评测.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
