# ADR-002: 选择 TaskGraph DAG 调度而非固定状态机

**状态**：Decided, Implemented
**日期**：2026-06-26
**作者**：RiskMonitor-MultiAgent 项目组

## Context / 问题背景

系统最初采用固定五段式流程（Intent → Plan → Critic → Execute → Finalize），本质上是一个线性状态机。随着业务复杂度增长，这种模式暴露出以下问题：

1. **无法表达并行**：多 desk 异常同时排查需要并行子任务，线性流程只能串行
2. **分支难以表达**：条件执行（如审批通过走路径 A，拒绝走路径 B）在状态机中需要大量额外状态
3. **回退代价高**：重规划时需要回退到特定步骤，线性流程只能从头重跑或手动跳转
4. **依赖关系不显式**：步骤间的数据依赖只能通过顺序隐含，无法支持"只要前置依赖完成就可执行"
5. **恢复执行困难**：从失败步骤恢复需要知道哪些上游已完成，线性流程无法表达

系统需要一种调度模型，能同时支持并行执行、条件分支、局部回退、重规划和从断点恢复。

## Decision / 决策

**使用 TaskGraph（DAG 节点 + 依赖边）替代固定五段式流程作为核心调度模型。**

### 核心数据结构

```
TaskGraph {
  schema_version: "task_graph.v1"
  nodes: TaskNode[]
  edges: TaskEdge[]
  execution_state: TaskExecutionState
}

TaskNode {
  step_id: str
  parent_id: str | null
  node_type: enum
  status: pending | running | completed | failed | skipped | blocked
  reason: str
  evidence: str[]
  inputs: dict
  outputs: dict
  retry_count: int
  replan_from_step_id: str | null
}

TaskEdge {
  from_step_id: str
  to_step_id: str
  edge_type: dependency | conditional | replan
  condition: str | null
}
```

### 支持的节点类型

| 节点类型 | 说明 |
|---------|------|
| `tool_call` | 调用注册工具，产出 receipt |
| `delegate` | 委托给专业 Agent（engineer/analyst）执行子任务 |
| `ask_human` | 触发人工审批或人工输入，阻塞等待 |
| `analyze` | Agent 内部分析推理，不产生副作用 |
| `finalize` | 汇总所有分支结果，生成最终输出 |
| `stop` | 终止执行（异常或满足停止条件） |
| `replan` | 触发局部重规划，生成新子图 |

### 调度规则

1. **就绪节点选择**：所有前置依赖已完成的节点进入就绪队列
2. **并行 Fan-out**：就绪队列中的独立节点可并行执行
3. **收敛 Fan-in**：finalize 节点等待所有输入分支完成
4. **条件分支**：conditional 边根据前置节点输出决定是否激活
5. **重规划注入**：replan 后生成的新子图插入原图，新节点带 `replan_from_step_id`
6. **失败恢复**：只清理失败节点和下游输出，已成功上游不重复执行

### 与原有流程的关系

原有五段式流程被保留为「语义阶段」，但不再承担执行调度职责：

```
[Intent] → [Orchestrator] → [TaskGraph DAG 调度] → [Critic Review] → [Finalize]
                                    ↑
                          真正的执行调度在这里
```

OrchestratorAgent 的输出从线性 `plan_steps` 改为显式 TaskGraph，每个节点包含 `step_id`、`parent_id`、`status`、`reason`、`evidence`。

## Rationale / 理由

### DAG 天然支持并行

SystemEngineerAgent 和 RiskAnalystAgent 可以同时执行独立子任务。TaskGraph 用依赖边显式表达"什么时候可以并行"，调度器自动发现并行机会。

### 条件分支表达自然

审批通过/拒绝、工具成功/失败、阈值突破/正常，都可以用 conditional 边优雅表达，不需要额外的状态定义。

### 重规划是子图插入

`TOOL_FAILED`、`NEW_EVIDENCE`、`CRITIC_REJECTED` 事件后，Orchestrator 生成新子图插入原图。新节点通过 `replan_from_step_id` 链接到触发点，保持全局可追溯。

### 恢复执行有明确语义

从失败步骤恢复时，调度器只需要：
1. 找到失败节点
2. 清理其输出和下游状态
3. 重新将其加入就绪队列

已完成的上游节点不受影响，重复执行次数为 0。

### 状态机的局限性

状态机适合表达固定流程，但金融风控任务的复杂度表现在：同一个任务可能需要 3-15 个步骤，步骤数在运行时才能确定，步骤间依赖关系是动态的。状态机无法优雅表达这种动态结构。

## Consequences / 后果

| 后果 | 程度 | 说明 |
|------|------|------|
| 调度器复杂度增加 | 高 | 需要实现拓扑排序、就绪检测、并行调度、状态流转 |
| 可恢复性提升 | 高 | 任意节点失败可局部恢复，无需整任务重跑 |
| 灵活性提升 | 高 | 支持运行时动态调整任务图 |
| 可观测性提升 | 高 | 每个节点有独立状态和时间线，trace 粒度到 step 级 |
| 测试复杂度增加 | 中 | 需要覆盖并行、条件分支、重规划、恢复等多种场景 |
| LLM 输出要求提升 | 中 | OrchestratorAgent 需要生成合法 DAG 而非线性列表 |

## Considered Options / 考虑的其他方案

### 方案A: 保持固定五段式状态机

**Pros**:
- 实现简单，调试直观
- LLM 只需输出线性步骤列表

**Cons**:
- 无法并行执行
- 无法局部回退和恢复
- 重规划只能整任务重跑

**为什么没选**：金融风控的复杂任务（多 desk 同时排查、并行分析后汇总）无法在线性流程中高效完成。

### 方案B: Petri Net

**Pros**:
- 数学基础完备
- 天然支持并发和同步

**Cons**:
- 过于学术化，团队维护成本高
- LLM 难以直接生成 Petri Net 结构
- 缺乏生态支持

**为什么没选**：DAG 在表达能力和工程可维护性之间取得了最佳平衡。

### 方案C: Actor Model（纯消息驱动）

**Pros**:
- 天然并行和解耦
- 容错性好

**Cons**:
- 缺乏全局任务视图
- 难以实现"等所有分支完成后汇总"的 Fan-in 语义
- 调试困难

**为什么没选**：MessageBus 已用于 Agent 间通信，但任务调度需要全局视图来做依赖分析和恢复判断。

## Update Log

- 2026-06-26: 创建本 ADR，确立 TaskGraph DAG 调度为核心执行模型
