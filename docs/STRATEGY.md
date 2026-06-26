# RiskMonitor-MultiAgent 产品战略

## Press Release

### 标题

RiskMonitor-MultiAgent：金融风控的自学习多智能体系统

### 副标题

为金融风控团队赋予 AI 驱动的主动感知、精密执行和持续改进能力

### 概述

2026 年 6 月 — RiskMonitor-MultiAgent 是一个面向金融风控团队的 Proactive Multi-Agent 系统。它将传统风控工作中的意图理解、任务规划、工具执行、审批治理和经验沉淀整合为一个完整闭环，让风控团队从被动响应告警转变为主动感知风险、精密执行处置、持续积累组织智慧。

与传统规则引擎或单一 LLM 方案不同，RiskMonitor-MultiAgent 采用多角色专业化 Agent 协作架构——每个 Agent 承担明确职责（意图识别、规划调度、风险分析、系统排查、评审治理），通过消息驱动和事件触发实现动态协作。系统支持任务图级并行执行、自动重规划、step 级审批恢复、语义记忆驱动的 few-shot 经验复用，以及全链路可追溯回放。

本系统专为金融风控场景设计，服务于 Risk Manager、Desk Head、风控运营人员和平台研发团队。

### 用户价值

- **Risk Manager**：从被动监控告警到主动感知风险。系统持续订阅市场信号和仓位变化，在 breach 发生前主动触发排查，自动拆解复杂风险场景为可追溯的分析链路，提供带完整证据链的行动建议，而非简单阈值告警。

- **Desk Head**：从人工查证到智能根因分析。面对头寸异常或限额突破，系统自动调度 SystemEngineer 和 RiskAnalyst 并行排查系统状态和业务逻辑，汇总多维度诊断结果，定位根因并附带每一步的工具回执和数据引用，决策有据可依。

- **风控运营**：从告警洪流到智能聚合处理。ModeratorAgent 自动对同类事件做冲突仲裁和优先级排序，将多源告警聚合为结构化任务，副作用操作（如写告警、提交处置）自动进入审批流，已处理经验沉淀为 Skill 供后续复用，告警疲劳显著降低。

- **研发人员**：从一次性工具到可复用 Skill 库。系统在成功完成任务后自动提炼可复用模式为结构化 Skill，Skill 具备语义检索、置信度衰减、版本迭代能力。新增风控场景只需注册工具和描述意图，无需重写执行逻辑。

### 差异化

与市面现有方案相比，RiskMonitor-MultiAgent 具备 5 个核心差异：

1. **真实闭环，非演示流水线**：`plan → execute → observe → replan → finalize` 每一步都有真实工具回执、真实数据观测和真实重规划决策，不是预设脚本式的工作流编排。

2. **多 Agent 专业协作，非单 LLM 万能回答**：IntentAgent、OrchestratorAgent、CriticAgent、SystemEngineerAgent、RiskAnalystAgent、ModeratorAgent 各司其职，通过 TaskGraph 并行委托和 MessageBus 消息驱动实现动态协作，而非单模型承担所有推理。

3. **零信任治理体系，非黑箱自动化**：所有副作用工具强制经过 RBAC + 侧效应审批 + receipt 绑定，每个动作可审计、可拒绝、可回放。`dangerous_action_block_rate = 100%` 是系统硬约束。

4. **自学习持续改进，非固定规则库**：从 Unified Memory 到 Skill 自创，系统通过高置信经验沉淀、few-shot 复用和 Skill 置信度动态更新实现越用越好，而非依赖人工维护规则库。

5. **完整可追溯，非结果汇报**：`run_trace.v2` 覆盖 task、plan、step、command、receipt、approval、memory、final 全链路。单条命令即可回放任意一次运行的完整决策链。

### Getting Started

```bash
# 环境准备
cp .env.example .env  # 配置 LLM Provider 和基础设施

# 启动依赖服务
make docker-up

# 初始化知识库
make kb-init

# 运行系统
make run

# 执行评测
make eval-quick

# 回放历史运行
make replay RUN_ID=<run_id>
```

---

## External FAQ（面向客户/用户）

### Q: RiskMonitor-MultiAgent 与传统风控工具有什么不同？

A: 传统风控工具主要有三类方案，各自存在明显局限：

| 方案类型 | 局限性 | RiskMonitor-MultiAgent 的优势 |
|---------|--------|------|
| 规则引擎 | 只能处理预定义场景，无法应对复杂、动态的风险组合 | 任务图级规划支持动态分支、并行、重规划，适应非预设场景 |
| 单一 LLM 方案 | 缺乏执行闭环，生成建议但无法驱动行动和验证 | 真实工具调用 + receipt 回灌 + 多步观测，形成行动闭环 |
| 人工流程 | 响应慢、难追溯、经验难以沉淀 | 全链路 trace + 经验自动沉淀 + Skill 复用，组织智慧持续积累 |

核心差异在于：本系统不是"给出建议"，而是"理解意图 → 规划行动 → 执行工具 → 验证结果 → 恢复异常 → 沉淀经验"的完整闭环。

### Q: 系统如何保证风控决策的准确性和可信度？

A: 系统通过四重机制保证决策可信：

1. **多 Agent 制衡**：OrchestratorAgent 规划、CriticAgent 审查、ModeratorAgent 仲裁，每个决策至少经过两个 Agent 校验，避免单点幻觉。
2. **证据绑定**：所有最终结论必须引用至少 1 个工具回执（receipt），`receipt_binding_rate > 95%`，结论可追溯到原始数据。
3. **人工审批（HITL）**：所有副作用动作进入 `pending → approved → resumed` 审批状态机，高风险操作人工确认后才执行。
4. **完整审计**：`run_trace.v2` 记录每一步的 thought、reason、evidence、observation，任意决策可回放复盘。

### Q: 如果 AI 做出错误决策怎么办？

A: 系统在设计层面预防并处理错误决策：

- **零信任工具治理**：所有副作用工具（写告警、提交处置等）标记 `side_effect=true`，自动触发审批，未经批准不可执行。`dangerous_action_block_rate` 硬性要求 100%。
- **HITL 审批流**：step 级和 command 级双层审批，审批请求携带风险等级、影响范围和建议动作，审批人可充分评估后决定。
- **可回滚设计**：审批被拒绝后系统不会执行该动作，任务可从阻断点恢复走替代路径，已成功的上游步骤不重复执行。
- **完整 trace**：每个决策的推理链（BDI + ReAct + CoT）完整记录，事后可精确定位错误环节和原因。

### Q: 能否支持自定义风控规则和策略？

A: 支持，通过三层扩展机制：

1. **工具注册**：新增风控工具只需在 `tool_registry` 中声明名称、参数、副作用属性和 RBAC 权限，自动纳入统一执行链路。
2. **Skill 系统**：将常用风控策略编码为结构化 Skill（Markdown + YAML frontmatter），包含适用条件、执行步骤、失败边界和置信度，系统规划时自动匹配注入。
3. **策略版本化**：通过 `version_snapshot` 机制，prompt 版本、policy 版本、toolset 配置全部纳入 trace，任意两次运行可对比策略差异。支持 A/B 实验验证策略效果。

### Q: 系统的数据安全性如何保证？

A: 数据安全通过五层防护：

1. **RBAC 权限控制**：每个 Agent 按角色分配工具访问权限，RiskAnalyst 只能调用分析类工具，不能执行写操作。
2. **侧效应审批**：所有 `side_effect=true` 操作强制审批，禁止静默执行。
3. **审计日志**：所有工具调用产出标准化 receipt（含 command_id、inputs、outputs、approval_state），全部可审计。
4. **隔离执行**：多 Agent 私有记忆互不串读，`memory_cross_talk_rate` 作为治理指标持续监控。
5. **预算熔断**：主动任务受 ProactiveBudgetManager 约束，异常风暴下自动熔断，防止资源滥用。

---

## Internal FAQ（面向团队/技术决策者）

### Q: 为什么选择多 Agent 架构而不是单 Agent？

A: 多 Agent 架构在金融风控场景中具备不可替代的优势：

- **可解释性**：每个 Agent 产出独立推理链和结构化输出，审计时可逐角色回溯，单 Agent 的混合推理链难以拆解归因。
- **容错性**：单个 Agent 推理失败不影响全局，TaskGraph 支持局部重规划和 step 级重试，单 Agent 失败即全局失败。
- **专业分工**：IntentAgent 专注意图识别，CriticAgent 专注质量评审，ModeratorAgent 专注冲突仲裁——每个角色可独立优化 prompt 和选择最适合的模型。
- **成本优化**：按角色选择不同规格的 LLM（简单路由用轻量模型，复杂推理用强模型），比单一大模型全量推理成本更低。
- **金融合规**：监管要求决策可追溯、可审计、可解释。多 Agent 的角色分离天然满足"谁做了什么决策、基于什么依据"的合规要求。

### Q: Hermes 升级的 ROI 是什么？

A: Hermes 五柱升级（Phase 5-8）的预期回报：

| 升级维度 | 预期收益 |
|---------|---------|
| Skill 自创 | 相似任务不再重复推理，直接复用历史 Skill，预计减少 30%+ 的重复规划开销 |
| 提示词缓存分层 | stable_tier 前缀复用命中提供商缓存，token 成本预计下降 20%+ |
| 记忆永久化 | 关键经验跨会话保持，系统重启不丢失组织智慧，新团队成员可即时受益 |
| 上下文压缩 | 超长任务（20+ 步）不再因 context window 超限而失败，任务成功率提升 |
| 自我改进闭环 | 系统随使用时间自动积累高质量 Skill 和经验，整体表现呈上升趋势 |

核心逻辑：让系统的边际成本随使用时间递减，边际价值随使用时间递增。

### Q: 系统的主要技术风险是什么？

A: 四类核心风险及缓解措施：

1. **LLM 依赖风险**：多角色调用放大了 LLM 不稳定性。缓解：receipt 绑定强制验证事实性、Critic 审查过滤幻觉、step 级重试和 replan 容错。
2. **记忆噪音风险**：低质量经验污染规划。缓解：confidence policy 只沉淀高置信结论、Skill 置信度动态衰减、`memory_cross_talk_rate` 监控隔离。
3. **成本控制风险**：多 Agent 调用和主动协作可能失控。缓解：ProactiveBudgetManager 频控/token budget/熔断、按角色选模型降本、提示词缓存分层。
4. **评测对齐风险**：指标体系不能真实反映系统能力。缓解：所有指标基于 `run_trace.v2` 真实事件聚合、LLM Judge 只评文本质量不判行为事实、金标准人工标注集校准。

### Q: 如何衡量系统成功？

A: 通过两层指标体系量化衡量：

**核心行为指标**（基于 trace 真实事件计算）：
- `task_success_rate`：任务端到端成功率 > 85%
- `tool_selection_accuracy`：工具选择准确率 > 90%
- `receipt_binding_rate`：结论引用 receipt 比例 > 95%
- `dangerous_action_block_rate`：危险动作阻断率 = 100%
- `replan_success_rate`：重规划后任务恢复成功率
- `resume_success_rate`：中断恢复成功率 > 80%

**记忆与协作指标**：
- `memory_hit_rate`：记忆命中率 > 60%
- `memory_usefulness`：memory_on vs memory_off 对照收益
- `few_shot_reuse_rate`：Skill/经验复用率
- `role_drift_rate`：角色漂移率（越低越好）
- `memory_cross_talk_rate`：记忆串读率（越低越好）
- `message_trace_completeness`：消息追踪完整率

### Q: 系统的扩展路径是什么？

A: 从当前 Phase 4（已完成）到未来 Phase 8 的渐进路径：

```
Phase 0-4 [已完成] → 真实执行闭环 + 统一记忆 + 事件驱动 + HITL审批 + 评测体系
    |
Phase 5 → 技能自创闭环（Skill 从经验中自动创建、复用和改进）
    |
Phase 6 → 记忆永久化 + 上下文压缩（关键记忆永不丢失 + 超长任务支持）
    |
Phase 7 → 内置调度 + 多平台网关（定时巡检 + 企业微信/Slack 交互）
    |
Phase 8 → 提示词优化 + 自我改进闭环（token 成本降 20%+ + 系统越用越好）
```

扩展原则：所有新增能力接入统一执行内核（`ModeratorAgent → TaskGraphExecutor`），不形成旁路；始终保持多 Agent 架构，不退化为单 Agent。

### Q: 与竞品（如单一 LLM Agent、规则引擎）的成本对比？

A: 多 Agent 架构在实际运营中具备成本优势：

| 对比维度 | 单一 LLM Agent | 规则引擎 | RiskMonitor-MultiAgent |
|---------|--------------|---------|----------------------|
| 推理成本 | 全量任务使用大模型，高 | 无 LLM 成本，低 | 按角色选模型，中等 |
| 开发维护 | 单 prompt 膨胀难以维护 | 规则爆炸式增长 | 角色独立演进，可控 |
| 适应新场景 | 需重写 prompt + 全量测试 | 需新增大量规则 | 注册工具 + Skill 自动积累 |
| 错误恢复 | 失败即重跑全流程 | 需人工干预 | step 级重试 + 局部 replan |
| 长期趋势 | 成本随复杂度线性增长 | 维护成本指数增长 | Skill 复用减少重复推理，成本递减 |

关键优势：Skill 复用减少 30%+ 重复推理；提示词缓存分层降低 20%+ token 消耗；按角色选模型（简单路由用 4o-mini，复杂推理用 GPT-4 / Claude）综合成本更优。

---

## 附录

### 核心指标体系

| 指标 | 定义 | 目标 |
|-----|------|------|
| task_success_rate | 任务端到端成功率（plan → execute → finalize 完整完成） | > 85% |
| tool_selection_accuracy | 工具选择与场景匹配的准确率 | > 90% |
| receipt_binding_rate | 最终结论引用至少 1 个 receipt 的比例 | > 95% |
| dangerous_action_block_rate | 未审批副作用动作被阻断的比例 | 100% |
| replan_success_rate | 触发重规划后任务最终成功的比例 | > 75% |
| resume_success_rate | 从中断点恢复后任务成功完成的比例 | > 80% |
| memory_hit_rate | 规划和执行阶段命中相关记忆的比例 | > 60% |
| few_shot_reuse_rate | 历史 Skill/经验被规划显式引用的比例 | > 30% |
| role_drift_rate | Agent 输出偏离角色职责的比例 | < 5% |
| memory_cross_talk_rate | 私有记忆被非所属 Agent 读取的比例 | 0% |
| message_trace_completeness | run trace 覆盖所有关键事件的完整率 | 100% |
| factuality_score | 结论与工具回执数据一致性评分 | > 0.85 |
| evidence_coverage | 结论中每个关键声明都有证据支撑的比例 | > 90% |

### 相关文档

- [PRD](./PRD.md)
- [架构设计](./ARCHITECTURE.md)
