# API 文档

本文档描述 RiskMonitor-MultiAgent 的主要 API 接口。

## 目录

- [服务入口](#服务入口)
- [核心 API](#核心-api)
- [Agent API](#agent-api)
- [编排 API](#编排-api)
- [可观测性 API](#可观测性-api)

---

## 服务入口

### MCP Server 启动

```python
from riskmonitor_multiagent.server import app
import uvicorn

uvicorn.run(app, host="0.0.0.0", port=8000)
```

或使用 Makefile：

```bash
make run
```

---

## 核心 API

### 1. 风险监控任务执行

**函数**: `run_risk_monitor_task()`

**位置**: `main.py`

**描述**: 执行完整的风险监控任务流程

**参数**:
- `task: dict[str, Any]` - 任务定义
  - `task_id: str` - 任务 ID（可选）
  - `payload: dict` - 任务载荷
    - `content: str` - 用户查询内容

**返回**: `dict[str, Any]` - 完整的执行结果

**示例**:

```python
from main import run_risk_monitor_task

result = await run_risk_monitor_task({
    "payload": {
        "content": "检查 Equities desk 的风险暴露"
    }
})
```

---

## Agent API

### 1. Intent Agent

**类**: `IntentAgent`

**位置**: `src/riskmonitor_multiagent/agents/roles.py`

**方法**: `recognize(task: dict[str, Any])`

**描述**: 识别用户查询意图

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `AgentOutput` - 包含意图识别结果

**示例**:

```python
from riskmonitor_multiagent.agents.roles import IntentAgent

agent = IntentAgent()
result = await agent.recognize(task={
    "payload": {"content": "检查 Equities desk 的风险暴露"}
})
```

### 2. Orchestrator Agent

**类**: `OrchestratorAgent`

**位置**: `src/riskmonitor_multiagent/agents/roles.py`

**方法**: `orchestrate(task: dict[str, Any])`

**描述**: 制定执行计划

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `AgentOutput` - 包含执行计划

### 3. Critic Agent

**类**: `CriticAgent`

**位置**: `src/riskmonitor_multiagent/agents/roles.py`

**方法**: `review(task: dict[str, Any], orchestrator: dict[str, Any])`

**描述**: 评审执行计划

**参数**:
- `task: dict[str, Any]` - 任务定义
- `orchestrator: dict[str, Any]` - Orchestrator 的输出

**返回**: `AgentOutput` - 包含评审结果

### 4. System Engineer Agent

**类**: `SystemEngineerAgent`

**位置**: `src/riskmonitor_multiagent/agents/roles.py`

**方法**: `analyze_task(task: dict[str, Any])`

**描述**: 从系统工程角度分析任务

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `AgentOutput` - 包含分析结果

### 5. Risk Analyst Agent

**类**: `RiskAnalystAgent`

**位置**: `src/riskmonitor_multiagent/agents/roles.py`

**方法**: `analyze_task(task: dict[str, Any])`

**描述**: 从风险分析角度分析任务

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `AgentOutput` - 包含分析结果

---

## 编排 API

### 1. Orchestrator Workflow（兼容层）

**类**: `OrchestratorWorkflow`

**位置**: `src/riskmonitor_multiagent/orchestration/orchestrator_workflow.py`

**方法**: `run(task: dict[str, Any])`

**描述**: 运行兼容层的编排工作流

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `dict[str, Any]` - 执行结果

### 2. Multi-Agent Workflow（消息总线）

**类**: `MultiAgentCollaborationWorkflow`

**位置**: `src/riskmonitor_multiagent/orchestration/multiagent_workflow.py`

**方法**: `run(task: dict[str, Any])`

**描述**: 运行使用消息总线的多 Agent 工作流

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `dict[str, Any]` - 执行结果，包含 `message_history`

### 3. Dynamic Workflow（动态协作）

**类**: `DynamicCollaborationWorkflow`

**位置**: `src/riskmonitor_multiagent/orchestration/dynamic_workflow.py`

**方法**: `run(task: dict[str, Any], max_iterations: int = 10)`

**描述**: 运行真正的动态协作工作流（状态机驱动）

**参数**:
- `task: dict[str, Any]` - 任务定义
- `max_iterations: int` - 最大迭代次数（默认 10）

**返回**: `dict[str, Any]` - 执行结果，包含 `mode: "dynamic"`

---

## ReAct + CoT API

### 1. ReAct Loop

**类**: `ReActLoop`

**位置**: `src/riskmonitor_multiagent/orchestration/react_loop.py`

**方法**: `run(task: dict[str, Any])`

**描述**: 运行 ReAct 循环

**参数**:
- `task: dict[str, Any]` - 任务定义

**返回**: `ReActResult` - ReAct 循环结果

### 2. CoT-Enhanced ReAct Loop

**类**: `CoTEnhancedReActLoop`

**位置**: `src/riskmonitor_multiagent/orchestration/react_loop.py`

**描述**: 带有 CoT 思维链增强的 ReAct 循环

### 3. ReAct Agent Mixin

**类**: `ReActAgentMixin`

**位置**: `src/riskmonitor_multiagent/agents/react_agent.py`

**描述**: 为 Agent 添加 ReAct + CoT 能力

**方法**:
- `run_react(task: dict[str, Any])` - 运行 ReAct 循环
- `get_last_react_trace()` - 获取 ReAct 追踪
- `add_task_belief(task: dict)` - 添加任务信念
- `add_observation_belief(observation: Any)` - 添加观察信念
- `add_goal_desire(description: str)` - 添加目标愿望
- `add_action_intention(description: str)` - 添加行动意图

---

## BDI API

### 1. BDI Agent Mixin

**类**: `BDIAgentMixin`

**位置**: `src/riskmonitor_multiagent/agents/bdi.py`

**描述**: 为 Agent 添加信念、愿望、意图能力

**方法**:
- `add_belief(content: Any, source: str)` - 添加信念
- `get_beliefs(source: Optional[str])` - 获取信念
- `add_desire(description: str, priority: int)` - 添加愿望
- `get_active_desires()` - 获取活跃愿望
- `add_intention(description: str)` - 添加意图
- `get_pending_intentions()` - 获取待处理意图
- `update_intention_status(intention_id: str, status: str)` - 更新意图状态

---

## 迭代优化 API

### 1. Iterative Refinement Engine

**类**: `IterativeRefinementEngine`

**位置**: `src/riskmonitor_multiagent/orchestration/iterative_refinement.py`

**描述**: 迭代优化引擎

**方法**:
- `run_iterative_refinement()` - 运行迭代优化
- `run_review_and_revise()` - 运行评审-修订
- `record_conflict(agent_a, agent_b, description)` - 记录冲突
- `resolve_conflict(conflict_id, resolution)` - 解决冲突
- `get_unresolved_conflicts()` - 获取未解决的冲突

---

## 层次协作 API

### 1. Hierarchical Coordinator

**类**: `HierarchicalCoordinator`

**位置**: `src/riskmonitor_multiagent/orchestration/hierarchical.py`

**描述**: 层次协作协调器

**方法**:
- `add_level(level_id, level_name, agents, responsibility)` - 添加层次
- `assign_task(task, from_agent, to_agent)` - 分配任务
- `execute_assignment(assignment_id, executor_fn)` - 执行任务分配
- `start_monitor(check_interval_ms, on_assignment_pending)` - 启动后台监控
- `stop_monitor()` - 停止后台监控

---

## 可观测性 API

### 1. Metrics

**模块**: `riskmonitor_multiagent.observability.metrics`

**函数**:
- `inc_counter(name: str, labels: Optional[dict])` - 增加计数器
- `set_gauge(name: str, value: float, labels: Optional[dict])` - 设置仪表盘
- `observe_ms(name: str, value_ms: float, labels: Optional[dict])` - 观察毫秒值
- `render_metrics()` - 渲染 Prometheus 格式的指标

### 2. Tracing

**模块**: `riskmonitor_multiagent.observability.tracing`

**函数**:
- `@trace(name: str, trace_id: Optional[str])` - 追踪上下文管理器
- `get_current_trace_id()` - 获取当前 Trace ID
- `get_current_span_id()` - 获取当前 Span ID
- `add_trace_attributes(attributes: dict)` - 添加 Trace 属性
- `get_trace_summary(trace_id: str)` - 获取 Trace 摘要

### 3. Logging

**模块**: `riskmonitor_multiagent.services.logging_service`

**函数**:
- `new_request_id()` - 生成新的请求 ID
- `get_request_id()` - 获取当前请求 ID
- `get_audit_logger()` - 获取审计日志记录器

---

## 消息总线 API

### 1. Message Bus

**类**: `MessageBus`

**位置**: `src/riskmonitor_multiagent/orchestration/message_bus.py`

**方法**:
- `send_request(from_agent, to_agent, content)` - 发送请求
- `send_response(from_agent, to_agent, content, in_reply_to)` - 发送响应
- `broadcast(from_agent, content)` - 广播消息
- `subscribe(agent_id, callback)` - 订阅消息
- `get_message_history()` - 获取消息历史
- `get_messages_for_agent(agent_id)` - 获取特定 Agent 的消息

---

## 工具 API

### 1. Tool Registry

**类**: `ToolRegistry`

**位置**: `src/riskmonitor_multiagent/orchestration/tool_registry.py`

**方法**:
- `register_tool(tool_name: str, tool_fn: Callable)` - 注册工具
- `get_tool(tool_name: str)` - 获取工具
- `list_tools()` - 列出所有工具

### 2. Tool Executor

**类**: `ToolExecutor`

**位置**: `src/riskmonitor_multiagent/orchestration/tool_executor.py`

**方法**:
- `execute_tool(tool_name: str, params: dict[str, Any])` - 执行工具

---

## 数据访问 API

### 1. Positions DAO

**类**: `PositionsDAO`

**位置**: `src/riskmonitor_multiagent/data_access/positions_dao.py`

**方法**:
- `query_all_positions()` - 查询所有头寸
- `query_positions_by_trader(trader_id: str)` - 按交易员查询
- `query_positions_by_desk(desk: str)` - 按 Desk 查询

### 2. Risk DAO

**类**: `RiskDAO`

**位置**: `src/riskmonitor_multiagent/data_access/risk_dao.py`

**方法**:
- `calculate_total_delta()` - 计算总 Delta
- `monitor_desk_exposure(desk: str, limit: float)` - 监控 Desk 风险暴露

---

## 配置 API

**模块**: `riskmonitor_multiagent.config`

**配置项**:
- `LLM_API_KEY` - LLM API 密钥
- `LLM_BASE_URL` - LLM 基础 URL
- `LLM_MODEL` - LLM 模型名称
- `MYSQL_HOST` - MySQL 主机
- `MYSQL_PORT` - MySQL 端口
- `MYSQL_DATABASE` - MySQL 数据库
- `MYSQL_USER` - MySQL 用户名
- `MYSQL_PASSWORD` - MySQL 密码
- `ENABLE_TRACING` - 是否启用追踪
- `MAX_LLM_COST_PER_TASK` - 每任务最大 LLM 成本

---

## 快速示例

### 完整流程示例

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

### 使用动态协作

```python
from riskmonitor_multiagent.orchestration.dynamic_workflow import get_dynamic_workflow

workflow = get_dynamic_workflow()
result = await workflow.run({
    "payload": {
        "content": "检查 Equities desk 的风险暴露"
    }
})

print(f"Mode: {result['mode']}")  # 应该是 "dynamic"
print(f"Completed Agents: {result['completed_agents']}")
```

---

## 更多文档

- [系统架构](./ARCHITECTURE.md)
- [快速开始](./QUICKSTART.md)
- [路线图](./ROADMAP.md)
