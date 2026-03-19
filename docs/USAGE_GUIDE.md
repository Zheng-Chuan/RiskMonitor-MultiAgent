# 使用指南

本文档详细描述如何使用 RiskMonitor-MultiAgent 系统。

## 目录

- [快速开始](#快速开始)
- [基本使用](#基本使用)
- [高级使用](#高级使用)
- [配置说明](#配置说明)

---

## 快速开始

### 前置要求

- Python 3.13+
- Docker
- MySQL（可选，可以用 Docker 运行）

### 1. 克隆项目

```bash
git clone <repository-url>
cd RiskMonitor-MultiAgent
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 启动 MySQL

```bash
docker compose up -d mysql
```

### 4. 配置环境变量

复制 `.env.example` 为 `.env` 并填入你的配置：

```bash
cp .env.example .env
```

必须配置项：
- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_DATABASE`
- `MYSQL_USER`
- `MYSQL_PASSWORD`

可选配置项：
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

### 5. 测试数据库连接

```bash
make test-db
```

### 6. 启动服务

```bash
make run
```

服务将在 `http://localhost:8000` 启动。

### 7. 运行测试

```bash
make test-unit
make test-integration
make test-smoke
```

---

## 基本使用

### 1. 执行风险监控任务

使用 `main.py` 中的 `run_risk_monitor_task` 函数：

```python
from main import run_risk_monitor_task

result = await run_risk_monitor_task({
    "payload": {
        "content": "检查 Equities desk 的风险暴露"
    }
})

print(f"Status: {result['status']}")
print(f"Intent: {result['intent']}")
print(f"Engineer: {result['engineer']}")
print(f"Analyst: {result['analyst']}")
```

### 2. 使用 MCP 工具

通过 MCP Server 调用工具：

```python
from riskmonitor_multiagent.tools.mcp_tools import get_all_tools

tools = get_all_tools()

# 查询头寸
positions = await tools["query_all_positions"]({})

# 计算风险
delta = await tools["calculate_total_delta"]({})
```

### 3. 直接使用 Agent

单独使用某个 Agent：

```python
from riskmonitor_multiagent.agents.roles import (
    IntentAgent,
    OrchestratorAgent,
    CriticAgent,
)

# 意图识别
intent_agent = IntentAgent()
intent_result = await intent_agent.recognize(task={
    "payload": {"content": "检查 Equities desk 的风险暴露"}
})

# 制定计划
orchestrator_agent = OrchestratorAgent()
plan_result = await orchestrator_agent.orchestrate(task={
    "payload": {"content": "检查 Equities desk 的风险暴露"}
})

# 评审计划
critic_agent = CriticAgent()
review_result = await critic_agent.review(
    task={
        "payload": {"content": "检查 Equities desk 的风险暴露"}
    },
    orchestrator=plan_result.output,
)
```

---

## 高级使用

### 1. 使用动态协作工作流

```python
from riskmonitor_multiagent.orchestration.dynamic_workflow import get_dynamic_workflow

workflow = get_dynamic_workflow()
result = await workflow.run({
    "payload": {
        "content": "检查 Equities desk 的风险暴露"
    }
})

print(f"Mode: {result['mode']}")  # "dynamic"
print(f"Completed Agents: {result['completed_agents']}")
print(f"Final State: {result['final_state']}")
```

### 2. 使用消息总线工作流

```python
from riskmonitor_multiagent.orchestration.multiagent_workflow import get_multi_agent_workflow

workflow = get_multi_agent_workflow()
result = await workflow.run({
    "payload": {
        "content": "检查 Equities desk 的风险暴露"
    }
})

print(f"Message History: {len(result['message_history'])} messages")
```

### 3. 使用 ReAct + CoT

```python
from riskmonitor_multiagent.orchestration.react_loop import (
    CoTEnhancedReActLoop,
)

def thought_generator(task, history):
    return "思考中..."

def reasoning_generator(task, history, thought):
    return "理由..."

def evidence_generator(task, history, thought):
    return {"source": "test"}

def action_decider(task, history, thought):
    return ("mock_action", {"step": len(history) + 1})

def action_executor(action_type, action):
    return {"result": "done"}

def termination_checker(task, history):
    return len(history) >= 3

loop = CoTEnhancedReActLoop(
    max_steps=5,
    thought_generator=thought_generator,
    reasoning_generator=reasoning_generator,
    evidence_generator=evidence_generator,
    action_decider=action_decider,
    action_executor=action_executor,
    termination_checker=termination_checker,
)

result = await loop.run(task={"test": "data"})
print(f"Success: {result.success}")
print(f"Steps: {len(result.steps)}")
```

### 4. 使用 BDI 模型

```python
from riskmonitor_multiagent.agents.bdi import BDIAgentMixin

class MyAgent(BDIAgentMixin):
    def __init__(self):
        super().__init__()

agent = MyAgent()

# 添加信念
agent.add_belief(
    content="市场波动很大",
    source="observation",
    confidence=0.9,
)

# 添加愿望
agent.add_desire(
    description="降低风险暴露",
    priority=100,
)

# 添加意图
agent.add_intention(
    description="查询当前头寸",
    tool_name="query_positions_by_desk",
    tool_params={"desk": "Equities"},
)

# 获取活跃愿望
active_desires = agent.get_active_desires()
print(f"Active Desires: {len(active_desires)}")
```

### 5. 使用迭代优化

```python
from riskmonitor_multiagent.orchestration.iterative_refinement import get_refinement_engine

engine = get_refinement_engine()

def agent_fn(input_data):
    return {"output": input_data, "quality": "good"}

def critic_fn(output):
    return (True, "Looks good", [])

final_output, steps = await engine.run_iterative_refinement(
    initial_input={"task": "test"},
    agent_fn=agent_fn,
    critic_fn=critic_fn,
    max_iterations=3,
)
```

### 6. 使用层次协作

```python
from riskmonitor_multiagent.orchestration.hierarchical import get_hierarchical_coordinator

coordinator = get_hierarchical_coordinator()

# 添加层次
coordinator.add_level(
    level_id="level_1",
    level_name="管理层",
    agents=["moderator"],
    responsibility="协调和决策",
)

coordinator.add_level(
    level_id="level_2",
    level_name="执行层",
    agents=["engineer", "analyst"],
    responsibility="执行任务",
    parent_level="level_1",
)

# 分配任务
assignment = coordinator.assign_task(
    task={"payload": {"content": "分析风险"}},
    from_agent="moderator",
    to_agent="engineer",
)

print(f"Assignment ID: {assignment.assignment_id}")
```

### 7. 启用追踪

```python
from riskmonitor_multiagent.observability.tracing import (
    trace,
    get_trace_summary,
)

@trace("my_operation")
async def my_function():
    # 你的代码
    pass

# 调用并获取追踪
await my_function()

# 获取 Trace 摘要
trace_id = get_trace_summary(...)
```

---

## 配置说明

### 环境变量

| 变量 | 必须 | 默认值 | 说明 |
|------|------|--------|------|
| `MYSQL_HOST` | 是 | - | MySQL 主机 |
| `MYSQL_PORT` | 是 | - | MySQL 端口 |
| `MYSQL_DATABASE` | 是 | - | MySQL 数据库名 |
| `MYSQL_USER` | 是 | - | MySQL 用户名 |
| `MYSQL_PASSWORD` | 是 | - | MySQL 密码 |
| `LLM_API_KEY` | 否 | - | LLM API 密钥 |
| `LLM_BASE_URL` | 否 | - | LLM 基础 URL |
| `LLM_MODEL` | 否 | - | LLM 模型名称 |
| `ENABLE_TRACING` | 否 | `true` | 是否启用追踪 |
| `MAX_LLM_COST_PER_TASK` | 否 | `1.0` | 每任务最大 LLM 成本（美元） |

### Makefile 命令

| 命令 | 说明 |
|------|------|
| `make init` | 初始化项目 |
| `make run` | 启动服务 |
| `make test-unit` | 运行单元测试 |
| `make test-integration` | 运行集成测试 |
| `make test-smoke` | 运行冒烟测试 |
| `make test-db` | 测试数据库连接 |
| `make eval-local` | 本地评估 |
| `make eval-benchmark` | 基准测试评估 |
| `make metrics` | 查看指标 |
| `make docker-up` | 启动 Docker 服务 |
| `make docker-down` | 停止 Docker 服务 |

### Prometheus 指标

访问 `http://localhost:8000/metrics` 查看 Prometheus 格式的指标。

主要指标：
- `orchestrator_runs_total` - 编排运行次数
- `orchestrator_latency_ms` - 编排延迟（毫秒）
- `intent_recognitions_total` - 意图识别次数
- `llm_calls_total` - LLM 调用次数
- `llm_cost_total_usd` - LLM 总成本（美元）

---

## 更多文档

- [API 文档](./API.md)
- [系统架构](./ARCHITECTURE.md)
- [快速开始](./QUICKSTART.md)
- [路线图](./ROADMAP.md)
