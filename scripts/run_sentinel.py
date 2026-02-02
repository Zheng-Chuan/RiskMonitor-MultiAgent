#!/usr/bin/env python3
"""启动 Sentinel 服务的脚本."""

import sys
from pathlib import Path

# 将 src 加入 PYTHONPATH
repo_root = Path(__file__).resolve().parents[1]
sys.path.append(str(repo_root / "src"))

import asyncio
from riskmonitor_multiagent.sentinel.service import run_sentinel

if __name__ == "__main__":
    try:
        asyncio.run(run_sentinel())
    except KeyboardInterrupt:
        pass
