# ADR-005: run_trace.v2 全链路追踪设计

**状态**：Decided, Implemented
**日期**：2026-06-26
**作者**：RiskMonitor-MultiAgent 项目组

## Context / 问题背景

金融风控 Agent 系统对可审计性和可回放性有极高要求：

1. **审计需求**：监管机构可能要求回溯"某次风控决策是怎么产生的"，需要完整证据链
2. **故障定位**：复杂任务可能涉及 10+ 个步骤，失败定位需要 step 级时间线
3. **评测需求**：评测体系需要基于真实行为事件计算指标，不能依赖默认值
4. **回放需求**：支持单 run 的完整回放，重现决策过程
5. **对比需求**：不同配置或不同模型的运行结果需要可对比

早期系统的结果文件缺乏统一 schema，评测主要通过兼容拼装字段实现。这导致：
- 指标计算依赖默认值和启发式补分
- 无法精确定位失败步骤
- 回放需要人工拼接多份文件
- 不同运行间无法直接对比版本差异

## Decision / 决策

**采用统一的 run_trace.v2 schema，覆盖从任务创建到最终输出的全部关键事件。**

### Trace Entry 分类

| Category | 说明 | 典型内容 |
|----------|------|---------|
| `task` | 任务创建和元信息 | run_id, entry_type, user_input, trigger |
| `plan` | 规划产物 | task_graph, nodes, edges, orchestrator_output |
| `step` | 步骤执行 | step_id, status, start_time, end_time, inputs, outputs |
| `message` | Agent 间消息 | sender, receiver, content, message_type |
| `command` | 工具调用指令 | command_id, tool_name, inputs, timeout_ms |
| `receipt` | 工具执行回执 | receipt_id, status, outputs, latency_ms, failure_class |
| `approval` | 审批事件 | approval_id, state, reason, approver, decision |
| `memory` | 记忆读写 | memory_type, operation, content, agent_role |
| `final` | 最终输出 | summary, quality_score, receipt_refs, evidence |
| `version_snapshot` | 版本快照 | prompt_version, policy_version, model, toolset |

### 统一 Trace Entry 结构

```
TraceEntry {
  run_id: str           # 全局唯一运行 ID
  entry_id: str         # 条目 ID
  category: str         # 上述 10 类之一
  timestamp: datetime   # 精确时间戳
  agent_role: str       # 产出 Agent 角色
  phase: str            # 当前阶段
  payload: dict         # 类型化负载
  parent_entry_id: str | null  # 父条目（用于层次关系）
}
```

### 设计要点

#### 1. 每个 trace entry 带 run_id

所有事件、决策、执行、记忆写入都通过 `run_id` 关联到同一次运行。双入口（`user_task` 和 `system_event`）共享统一 `run_id` 生成机制。

#### 2. Step 级时间线

每个 TaskGraph 节点的执行都记录：
- `start_time`：开始时间
- `end_time`：结束时间
- `predecessors`：前驱节点
- `successors`：后继节点
- `failure_reason`：失败原因（如有）
- `related_receipts`：关联回执
- `related_memory`：关联记忆操作

任意一次失败都能在一条时间线上定位到具体 step 和失败原因。

#### 3. 版本快照

每次运行的 trace 中固定记录：
- `prompt_version`：提示词版本
- `policy_version`：治理策略版本
- `model`：使用的 LLM 模型
- `toolset`：可用工具集
- `benchmark_config`：评测配置

任意两次运行都能用 trace 直接对比版本差异。

#### 4. 支持 Replay CLI 回放

```bash
python -m riskmonitor_multiagent.cli.replay --run-id <run_id>
```

输出：
- 任务摘要
- 关键事件时间线
- 失败点和恢复点
- Receipt 证据链
- 最终结论和置信度

#### 5. 持久化策略

- 运行时：内存缓存（RunTraceStore）
- 持久化：落盘到 `results/run_traces/`
- Redis：保存 run context 和 resume state
- 评测消费：`eval/` 直接读取 trace 做 replay、evaluator、gate、benchmark

### 与评测体系的关系

评测器直接消费 `run_trace.v2` 而不是依赖兼容拼装字段：

- `tool_call_count`：从 `command` + `receipt` 类 trace 聚合
- `approval_count`：从 `approval` 类 trace 聚合
- `replan_count`：从 `plan` 类 trace 中 replan 标记聚合
- `memory_hit_count`：从 `memory` 类 trace 中 read 操作聚合

所有核心指标基于真实事件计数，默认值占比为 0。

## Rationale / 理由

### 金融审计合规

监管要求 Agent 决策可追溯。run_trace.v2 提供从输入到输出的完整证据链，每个步骤都有时间戳、产出者和证据引用。

### 故障快速定位

step 级时间线让运维人员不需要通读全部日志，直接在 trace 上定位失败节点和失败原因，以及受影响的下游。

### 评测真实性

评测指标直接从 trace 聚合，消除了"默认值补分"和"启发式推断"。gate 只阻断真实行为问题。

### 可对比性

版本快照让不同运行之间的差异可量化。Prompt 改了哪里、模型换了什么、工具集变了什么，都在 trace 中有明确记录。

## Consequences / 后果

| 后果 | 程度 | 说明 |
|------|------|------|
| 存储开销增加 | 中 | 每次 run 产出完整 trace JSON，典型大小 50KB-500KB |
| 可审计性极大提升 | 高 | 单命令可生成完整回放报告 |
| 评测可信度提升 | 高 | 指标来自真实事件，无默认值 |
| 调试效率提升 | 高 | step 级时间线 + 失败定位 |
| 写入性能影响 | 低 | 异步写入，不阻塞主链执行 |
| Schema 维护成本 | 中 | 新增 trace 类型需要更新 schema 和验证 |

## Considered Options / 考虑的其他方案

### 方案A: 结构化日志（Structured Logging）

**Pros**:
- 接入成本低
- 现有工具链丰富

**Cons**:
- 缺乏全局视图（散落在多个日志文件中）
- 难以做 run 级回放
- 无法直接作为评测输入

**为什么没选**：日志是面向调试的，不是面向审计和评测的。金融场景需要的是"单 run 完整证据链"，不是"搜索关键字定位问题"。

### 方案B: OpenTelemetry Spans

**Pros**:
- 业界标准
- 丰富的可视化工具

**Cons**:
- Span 模型不适合表达 DAG 节点间的依赖关系
- 缺乏金融审计特定的语义（approval、receipt）
- 评测体系需要额外适配

**为什么没选**：OpenTelemetry 适合性能监控，但 run_trace.v2 面向的是"业务决策审计"和"评测输入"。两者可共存（observability 层用 OTEL，审计层用 run_trace.v2）。

## Update Log

- 2026-06-26: 创建本 ADR，确立 run_trace.v2 全链路追踪设计
