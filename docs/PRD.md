# RiskMonitor-MultiAgent PRD

## 1. 文档目标

本文档是 RiskMonitor-MultiAgent 项目的产品需求总纲. 详细的分阶段规划, 技术决策和产品战略分别存放在独立文档中.

- **产品战略与客户价值**: [docs/STRATEGY.md](./STRATEGY.md)
- **技术决策记录**: [docs/decisions/](./decisions/)
- **分阶段详细规划**: [docs/phases/](./phases/)
- **架构设计**: [docs/ARCHITECTURE.md](./ARCHITECTURE.md)

---

## 2. 项目定位

把 RiskMonitor-MultiAgent 从"有骨架的多 Agent 工作流原型"升级为"简历表述和代码实现严格一致的可验证系统", 并在此基础上进一步升级为"自我改进的智能风控平台".

### 2.1 成功标准

- 简历中的每个关键能力都有对应代码模块, 测试, 文档, 评测样例
- 主流程必须形成 `plan -> execute -> observe -> replan -> finalize` 真实闭环
- 工具调用必须产出真实 receipt, 并被后续 Agent 消费
- 记忆必须在任务前检索, 任务中更新, 任务后沉淀, 并支持恢复执行
- 副作用动作必须在真实审批链上通过或被拒绝
- 评测体系必须以真实执行行为为基础, 不依赖默认值和启发式补分

### 2.2 非目标

- 做成通用办公 Agent
- 引入过重的分布式中间件
- 先做非常复杂的前端界面
- 追求海量工具数量

本期只做一件事: 让金融风控场景下的 Multi-Agent 闭环真实可运行, 可评测, 可解释, 可复盘.

---

## 3. 用户与场景

### 3.1 核心用户

- Risk Manager
- Desk Head
- 风控运营人员
- 平台研发和模型研发人员

### 3.2 核心场景

- 查询某 desk 当前头寸并分析 breach 原因
- 针对多 desk 异常同时排查, 自动拆分子任务并合并结论
- 对副作用动作 (写告警, 提交告警) 执行审批
- 根据历史类似案例和长期记忆给出更稳健的行动建议
- 在执行失败后基于上下文和回执恢复运行

---

## 4. 架构约束（绝对不变）

系统始终保持 Multi-Agent 架构, 绝不退化为单 Agent 系统.

- 多角色 Agent 体系不变 (IntentAgent, OrchestratorAgent, CriticAgent, SystemEngineerAgent, RiskAnalystAgent, ModeratorAgent)
- Hermes 能力增强每个 Agent, 不是替代多 Agent 协作
- 统一执行内核不变: `intent -> orchestrator plan -> task_graph -> parallel delegation -> critic review -> finalize`
- 角色隔离不变: 独立 private memory, 独立推理链, 独立 RBAC

> 详见: [ADR-001: 多Agent架构](./decisions/ADR-001-multi-agent-architecture.md)

---

## 5. 核心里程碑

| 阶段 | 目标 | 状态 | 详情 |
| :--- | :--- | :--- | :--- |
| Phase 0 | 对齐与止血 | ✓ 完成 | [phase-0-alignment.md](./phases/phase-0-alignment.md) |
| Phase 1 | 真实执行闭环 | ✓ 完成 | [phase-1-execution-loop.md](./phases/phase-1-execution-loop.md) |
| Phase 2 | 记忆闭环和恢复执行 | ✓ 完成 | [phase-2-memory-closure.md](./phases/phase-2-memory-closure.md) |
| Phase 3 | 事件驱动和主动协作 | ✓ 完成 | [phase-3-event-driven.md](./phases/phase-3-event-driven.md) |
| Phase 4 | 评测和门禁生产化 | ✓ 完成 | [phase-4-evaluation.md](./phases/phase-4-evaluation.md) |
| Phase 5 | 技能自创闭环 | ☐ 待开始 | [phase-5-skill-creation.md](./phases/phase-5-skill-creation.md) |
| Phase 6 | 记忆永久化与上下文压缩 | ☐ 待开始 | [phase-6-memory-persistence.md](./phases/phase-6-memory-persistence.md) |
| Phase 7 | 调度与多平台 | ☐ 待开始 | [phase-7-scheduling-gateway.md](./phases/phase-7-scheduling-gateway.md) |
| Phase 8 | 提示词优化与自我改进闭环 | ☐ 待开始 | [phase-8-prompt-optimization.md](./phases/phase-8-prompt-optimization.md) |

---

## 6. 关键技术决策

| 决策 | 状态 | 文档 |
| :--- | :--- | :--- |
| 多Agent架构作为绝对约束 | Decided | [ADR-001](./decisions/ADR-001-multi-agent-architecture.md) |
| TaskGraph DAG 调度设计 | Implemented | [ADR-002](./decisions/ADR-002-task-graph-design.md) |
| 统一记忆架构 | Implemented | [ADR-003](./decisions/ADR-003-unified-memory-design.md) |
| 零信任工具治理 | Implemented | [ADR-004](./decisions/ADR-004-tool-governance.md) |
| run_trace.v2 全链路追踪 | Implemented | [ADR-005](./decisions/ADR-005-run-trace-v2.md) |
| Hermes 五柱升级提案 | Draft | [RFC-001](./decisions/RFC-001-hermes-upgrade.md) |

---

## 7. 功能需求清单

| 编号 | 需求 | 关联阶段 |
| :--- | :--- | :--- |
| FR-1 | 系统必须支持任务图级规划和执行 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-2 | 系统必须支持真实工具调用回执 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-3 | 系统必须支持 step 级审批和恢复 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-4 | 系统必须支持消息驱动协作 | [Phase 3](./phases/phase-3-event-driven.md) |
| FR-5 | 系统必须支持语义记忆检索和经验沉淀 | [Phase 2](./phases/phase-2-memory-closure.md) |
| FR-6 | 系统必须支持任务失败后的恢复执行 | [Phase 2](./phases/phase-2-memory-closure.md) |
| FR-7 | 系统必须支持 trace 回放 | [Phase 1](./phases/phase-1-execution-loop.md) |
| FR-8 | 系统必须支持基于真实行为事件的评测 | [Phase 4](./phases/phase-4-evaluation.md) |

---

## 8. 非功能需求

- NFR-1: 所有关键状态都必须可持久化
- NFR-2: 所有副作用动作都必须可审计
- NFR-3: 所有最终结论都必须可追溯到输入, receipt 或 memory
- NFR-4: 评测结果必须可复现
- NFR-5: 每个阶段都要有单测, 集成测试, benchmark 样例

---

## 9. 风险与取舍

### 主要风险

- 引入任务图和事件驱动后, 系统复杂度会显著上升
- 记忆系统一旦做错, 会带来错误迁移和错误强化
- 过度主动性会造成噪声事件和成本失控
- 技能噪音: 低质量 Skill 污染规划, 导致决策退化
- 持久化迁移: Redis -> DB 迁移期间的数据一致性风险

### 设计取舍

- 优先把真实执行闭环做通, 再扩充 Agent 数量
- 优先做金融风控高价值场景, 不追求通用性
- 优先保证 trace 和评测可信, 再追求漂亮指标
- 优先做可恢复和可审批, 再追求极致自治
- 优先做技能自创闭环, 这是 Hermes 最核心的差异化能力

---

## 10. 发布准入标准

以下条件同时满足, 才允许对外按照简历口径讲完整能力:

- `plan -> execute -> observe -> replan` 闭环已在代码和 benchmark 中成立
- 真实工具调用, 审批, 回执, 恢复都有 case 证明
- 记忆检索已经真实参与规划和恢复
- 评测结果中关键计数项全部来自真实事件
- README, ARCHITECTURE, PRD 的能力口径保持一致

---

## 11. Hermes 升级成功标准

项目完成 Phase 5-8 后, 需要同时满足以下标准:

- 系统具备从执行经验中自动创建和改进 Skill 的能力
- 关键记忆跨会话永久保存, 不因 Redis 重启而丢失
- 支持自然语言定义的定时风控任务
- 支持至少 2 个企业通讯平台的告警推送和交互查询
- LLM token 成本较当前下降 20% 以上
- 系统整体表现随使用时间呈上升趋势 (自我改进闭环成立)
- 所有新增能力都接入统一执行内核, 不形成旁路

---

## 12. 相关文档

- [产品战略 (PR/FAQ)](./STRATEGY.md)
- [架构设计](./ARCHITECTURE.md)
- [技术决策](./decisions/)
- [分阶段规划](./phases/)
- [README](../README.md)
