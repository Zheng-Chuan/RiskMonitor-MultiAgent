#!/usr/bin/env python3
"""修复测试文件中的 UnifiedMemory 引用."""

import re

# 读取文件
with open('/Users/zhengchuan/Documents/TECH/Repo/RiskMonitor-MultiAgent/tests/unit/test_orchestrator_workflow.py', 'r') as f:
    content = f.read()

# 替换所有 UnifiedMemory 引用
content = content.replace(
    'from riskmonitor_multiagent.memory.unified_memory import UnifiedMemory',
    'from riskmonitor_multiagent.memory import get_memory_store'
)

# 替换所有 mem = UnifiedMemory()
content = content.replace(
    'mem = UnifiedMemory()',
    'mem = get_memory_store()'
)

# 写回文件
with open('/Users/zhengchuan/Documents/TECH/Repo/RiskMonitor-MultiAgent/tests/unit/test_orchestrator_workflow.py', 'w') as f:
    f.write(content)

print("Fixed test file!")
