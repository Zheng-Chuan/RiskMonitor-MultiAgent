# ADR-001: 多Agent架构作为系统的绝对约束

**状态**：Decided
**日期**：2026-06-26
**作者**：RiskMonitor-MultiAgent 项目组

## Context / 问题背景

金融风控任务本质上不是单轮问答问题，而是需要多维度专业分工的复杂决策过程。一个可治理的风控 Agent 系统至少要解决以下五件事：

1. **意图理解**：先理解用户意图和风险上下文
2. **任务规划**：把复杂任务拆成可执行步骤，形成有向无环任务图
3. **工具执行**：调用工具拿到真实观测结果，产出标准化回执
4. **动态重规划**：在执行中根据观测结果、失败反馈和 Critic 审查进行重规划
5. **治理与审批**：对副作用动作做审批，留下完整证据链和回放能力

这五项能力分别需要不同的推理模式、不同的上下文窗口、不同的工具权限和不同的安全边界。在 Hermes Engineering 五柱升级背景下，系统将获得技能自创、永久化记忆、内置调度、网关抽象层等新能力。必须明确这些新能力是增强每个 Agent，还是替代多 Agent 为单 Agent。

## Decision / 决策

**系统必须始终保持多Agent架构，绝不退化为单Agent系统。**

具体约束如下：

### 1. 多角色 Agent 体系不变

以下 6 个专业化角色全部保留，各司其职：

| 角色 | 职责 |
|------|------|
| `IntentAgent` | 意图识别、上下文提取、权限需求分析 |
| `OrchestratorAgent` | 任务分解、TaskGraph DAG 规划、重规划 |
| `CriticAgent` | 计划审查、质量评审、经验沉淀 |
| `SystemEngineerAgent` | 系统层面工具执行、技术分析 |
| `RiskAnalystAgent` | 风险分析、阈值判断、合规建议 |
| `ModeratorAgent` | 事件路由、冲突仲裁、优先级裁决 |

### 2. Hermes 能力增强每个 Agent，不是替代

技能自创、记忆永久化、上下文压缩、提示词缓存等能力是赋予每个 Agent 的基础能力升级。本质是"让每个士兵都更强"，而不是"用一个超级士兵替代整支军队"。

### 3. 协作拓扑不变

- `TaskGraph` 并行委托（DAG 节点 + 依赖边）
- `MessageBus` 消息驱动（事件发布/订阅）
- `ModeratorAgent` 仲裁（冲突检测 + 路由决策）
- `CriticAgent` 评审（计划审查 + 质量门控 + 经验沉淀）

### 4. 统一执行内核不变

所有任务仍通过以下多 Agent 协作主链完成：

```
intent -> orchestrator plan -> task_graph -> parallel delegation -> critic review -> finalize
```

双入口（`user_task` 和 `system_event`）最终都汇入同一套 `TaskGraphExecutor`、`receipt`、`memory`、`trace`。

### 5. 角色隔离不变

- 每个 Agent 保持独立的 **private task memory**（仅本角色可读可写）
- 每个 Agent 保持独立的 **推理链**（BDI + ReAct + CoT）
- 每个 Agent 保持独立的 **工具集权限**（RBAC 策略隔离）

### 6. 禁止事项

- **禁止合并 Agent**：不允许把多个专业 Agent 的职责合并到单个 Agent
- **禁止单 Agent + Skills 替代**：不允许用单 Agent + Skills/Plugins 模式替代多 Agent 协作
- **禁止移除角色**：不允许移除任何现有 Agent 角色

## Rationale / 理由

### 可解释性

每个决策都可追溯到具体 Agent 的推理链。IntentAgent 负责"为什么做"，OrchestratorAgent 负责"做什么"，执行 Agent 负责"怎么做"，CriticAgent 负责"做得对不对"。链路清晰，审计友好。

### 容错性

单个 Agent 失败不会导致全系统崩溃。TaskGraph 支持节点级重试、局部重规划、从失败步骤恢复。Agent 间通过 MessageBus 解耦，局部故障可隔离。

### 专业分工

金融风控场景中，系统分析和风险判断是两种完全不同的专业能力。SystemEngineerAgent 和 RiskAnalystAgent 的并行委托支持多视角分析，ModeratorAgent 汇总仲裁。

### 可治理性

RBAC 按角色分配工具权限。副作用工具只有特定角色可以触发。审批链路可以针对不同角色设置不同策略。角色漂移和记忆污染可检测可度量。

### 成本优化

不同 Agent 可以使用不同的模型。IntentAgent 可用快速小模型，OrchestratorAgent 用推理强的大模型，CriticAgent 用判断准确的模型。避免所有任务都消耗最昂贵模型的 token。

## Consequences / 后果

| 后果 | 程度 | 说明 |
|------|------|------|
| 系统复杂度增加 | 中 | 多 Agent 间通信、状态同步、冲突仲裁需要额外基础设施 |
| 调试难度增加 | 中 | 需要全链路 trace（run_trace.v2）和 replay CLI 支撑 |
| 可理解性提升 | 高 | 每个 Agent 职责明确，决策可追溯到具体角色 |
| 故障隔离提升 | 高 | 单 Agent 失败可局部重试，不需要整任务重跑 |
| 灵活扩展性 | 高 | 新增领域只需新增专业 Agent，无需修改已有角色 |
| 安全治理提升 | 高 | RBAC 按角色隔离，审批按角色策略，记忆按角色边界 |
| 延迟增加 | 低 | 并行委托和 TaskGraph DAG 调度可缓解串行延迟 |

## Considered Options / 考虑的其他方案

### 方案A: 单Agent + Plugins

**描述**：用一个强大的 Agent 配合多个工具插件完成所有任务。

**Pros**:
- 实现简单，无需 Agent 间通信
- 上下文集中，无信息分散问题
- 开发和维护成本低

**Cons**:
- 上下文窗口容易超限
- 无法按职责隔离权限
- 单点故障影响全系统
- 推理过程不可解释，无法区分"意图理解"和"执行决策"
- 无法针对不同能力使用不同模型

**为什么没选**：金融风控场景要求可审计、可解释、可治理。单 Agent 无法提供角色级 RBAC、独立审计链和故障隔离。

### 方案B: 轻型编排（<3 Agent）

**描述**：只保留 Planner + Executor + Reviewer 三个角色。

**Pros**:
- 复杂度适中
- 基本具备规划-执行-审查能力
- 通信开销小

**Cons**:
- 无法区分系统分析和风险分析两种专业能力
- 无法支持事件路由和冲突仲裁
- 扩展新领域需要修改已有 Agent
- 审批和主动性协作难以干净实现

**为什么没选**：金融风控的多维度分析需求（系统 + 风险 + 合规）无法由单一 Executor 覆盖。事件驱动和主动协作需要独立的 ModeratorAgent 做路由和仲裁。

## Update Log

- 2026-06-26: 创建本 ADR，确立多 Agent 架构不可退化约束
