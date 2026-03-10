# 项目结构说明

本文档描述优化后的项目架构.

## 目录结构

```
项目根目录/
├── src/riskmonitor_multiagent/    # 主代码
│   ├── agents/                    # Agent 角色定义
│   │   ├── base.py               # Agent 基类
│   │   └── roles.py              # 5 种 Agent 角色
│   ├── contracts/                 # 契约定义（数据验证）
│   │   ├── agent_outputs.py      # Agent 输出验证
│   │   ├── agent_messages.py     # Agent 消息验证
│   │   ├── intent_output.py      # 意图输出验证
│   │   └── memory_entry.py       # 记忆条目验证
│   ├── orchestration/             # 编排逻辑（LangGraph）
│   │   └── orchestrator_workflow.py  # 主工作流
│   ├── utils/                     # 公共工具函数 ⭐
│   │   ├── __init__.py
│   │   ├── ids.py                # ID 生成
│   │   ├── json.py               # JSON 处理
│   │   ├── text.py               # 文本处理
│   │   ├── time.py               # 时间工具
│   │   └── validation.py         # 验证工具
│   └── ...                        # 其他模块
├── tests/                         # 测试
│   ├── unit/                      # 单元测试
│   └── integration/               # 集成测试
├── eval/                          # 评估流水线
└── docs/                          # 文档
```

## 核心架构

### 1. Utils 包（公共工具）

新创建的 `utils` 包集中管理公共函数:

| 模块 | 功能 |
|------|------|
| `utils.text` | `clean_llm_output()`, `truncate_context()` |
| `utils.validation` | `is_non_empty_str()`, `has_evidence_refs()` |
| `utils.json` | `safe_json_loads()`, `safe_json_dumps()` |
| `utils.ids` | `new_run_id()`, `new_command_id()` |
| `utils.time` | `now_ms()`, `elapsed_ms()` |

使用方式:
```python
from riskmonitor_multiagent.utils import clean_llm_output, truncate_context
```

### 2. Contracts 包（契约验证）

数据格式验证和归一化:

```python
from riskmonitor_multiagent.contracts import (
    validate_orchestrator_output,
    normalize_orchestrator_output,
)

# 验证输出
ok, errors = validate_orchestrator_output(output)

# 归一化输出（补充缺失字段）
normalized = normalize_orchestrator_output(output)
```

### 3. Agents 包（Agent 定义）

5 种 Agent 角色:

| Agent | 职责 |
|-------|------|
| `IntentAgent` | 意图识别 |
| `OrchestratorAgent` | 编排计划 |
| `CriticAgent` | 计划评审 |
| `SystemEngineerAgent` | 系统工程师分析 |
| `RiskAnalystAgent` | 风险分析师评估 |

### 4. Orchestration 包（编排逻辑）

使用 LangGraph 实现的工作流:

```
Intent Node → Plan Node → Execute Node → Finalize Node
```

## 代码规范

### 注释规范

- 文件头部: 模块说明文档字符串
- 类/函数: docstring 说明用途、参数、返回值
- 关键逻辑: 行内注释解释原因

示例:
```python
def validate_orchestrator_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    验证编排器 Agent 输出.

    检查项:
    - schema_version 有效性
    - plan_steps 格式与完整性
    - evidence 引用有效性

    Args:
        output: Agent 输出字典

    Returns:
        (是否通过, 错误列表)
    """
```

### 导入规范

```python
# 1. 标准库
from __future__ import annotations
import json
from typing import Any

# 2. 第三方库
from langgraph.graph import StateGraph

# 3. 本项目模块
from riskmonitor_multiagent.utils import is_non_empty_str
from riskmonitor_multiagent.contracts import validate_orchestrator_output
```

## 测试

运行所有单元测试:
```bash
pytest tests/unit/ -v
```

运行集成测试:
```bash
pytest tests/integration/ -v
```

## 评估流水线

独立运行的评估模块 (`eval/`):

```bash
make eval-run RUN_TAG=experiment-1
make eval-gate RUN_TAG=experiment-1
```

## 优化记录

| 日期 | 优化内容 |
|------|---------|
| 2025-03-10 | 创建 utils 包，集中管理公共函数 |
| 2025-03-10 | 重构 contracts，添加中文注释和文档字符串 |
| 2025-03-10 | 重构 agents，使用新的 utils 包 |
