# RFC-001: Hermes Engineering 五柱升级提案

**状态**：Draft
**日期**：2026-06-26
**作者**：RiskMonitor-MultiAgent 项目组

## Motivation / 动机

当前系统已完成 Phase 0-4 全部增强，形成了具备以下能力的 Multi-Agent 金融风控平台：

- 真实执行闭环（TaskGraph DAG 调度 + Command/Receipt）
- 统一记忆架构（Private + Shared + Long-term Experience）
- 事件驱动协作（双入口 + ModeratorAgent + MessageBus）
- HITL 审批与恢复（审批状态机 + step 级恢复）
- 全链路追踪与评测（run_trace.v2 + Replay CLI + 42 条基准用例）

下一阶段目标是将系统从**"精密执行引擎"升级为"自我改进的智能风控平台"**。

参考 Hermes Engineering (Nous Research) 的五柱架构思想，系统需要获得：
1. 从经验中自动创建和改进可复用技能
2. 关键记忆跨会话永久保存
3. 自主定时执行风控任务
4. 多通道告警推送和交互查询
5. LLM 调用成本可控下降

**架构不变量**：本升级始终保持多 Agent 架构（参见 [ADR-001](./ADR-001-multi-agent-architecture.md)），Hermes 能力增强每个 Agent，不替代多 Agent 协作。

## Proposal / 提案概述

### 支柱一：技能自创闭环（方向八）

将 Critic 的 lesson 沉淀机制升级为完整的 Skill 系统：
- Skill 定义为结构化文档（Markdown + YAML frontmatter）
- SkillStore 基于语义向量检索
- 规划阶段自动注入匹配 Skill 作为 few-shot
- 执行反馈驱动 Skill 置信度衰减/增长
- 低质量 Skill 自动归档，防止噪音

### 支柱二：永久化记忆与上下文压缩（方向九）

将 Redis TTL 临时存储升级为永久化存储层：
- MySQL/SQLite 作为落盘后端，关键数据永久保存
- 四级 TTL 分级策略（ephemeral/short_term/long_term/permanent）
- 上下文压缩器（保护头尾 + 中间摘要 + checkpoint 分段）
- 长任务自动分段与链接恢复

### 支柱三：内置调度系统（方向十）

为系统增加原生定时任务能力：
- CronManager 支持 Cron 表达式和自然语言双模式
- 调度任务接入统一执行内核（system_event → ModeratorAgent → TaskGraphExecutor）
- 复用 ProactiveBudgetManager 做预算隔离
- 预置金融风控场景模板（盘后汇总、阈值巡检、合规报告）

### 支柱四：多平台网关（方向十一）

从 MCP 单入口扩展为多通道统一适配：
- GatewayAdapter 抽象基类，新平台只需实现适配器（核心契约保留）
- ~~企业微信、Slack 等平台适配器~~ (已回退 2026-06-27)
- 统一 GatewayMessage 格式 + 路由层

### 支柱五：提示词缓存分层（方向十二）

将 LLM prompt 构建升级为三层分离策略：
- `stable_tier`：Agent 角色定义、工具索引、行为规则（极少变化，命中提供商端缓存）
- `context_tier`：当前 Skills、项目规则（日级刷新）
- `volatile_tier`：记忆快照、当前事件（每次刷新）
- 版本管理 + 缓存失效控制
- token 成本追踪与优化报告

## Detailed Design / 详细设计

### 技能自创闭环

**核心数据结构**：
```
Skill {
  skill_id: str
  name: str
  tags: str[]
  applicable_conditions: str
  steps: str[]
  failure_boundary: str
  confidence: float
  write_origin: str  # agent_role + run_id
  created_at: datetime
  updated_at: datetime
  usage_count: int
  success_rate: float
  revision_history: Revision[]
}
```

**创建链路**：`CriticAgent.final_review()` → SkillProposer（quality_score >= threshold）→ 语义去重检查 → 创建/更新 Skill

**注入链路**：`OrchestratorAgent.orchestrate()` 前 → `retrieve_applicable_skills()` → 以 few-shot 注入规划 prompt

**置信度更新**：成功执行 `+delta`，失败执行 `-delta`，连续失败自动降权或 deprecated

**治理参数**：`max_skills_per_category`、`min_confidence_for_injection`、`max_skill_age_days`

### 永久化记忆与上下文压缩

**持久化架构**：
```
Runtime Layer:  Redis (高性能读写, 工作态数据)
                    ↓ 周期性落盘
Persistent Layer: MySQL/SQLite (永久保存, 高价值数据)
```

**四级 TTL 策略**：
| 级别 | TTL | 适用数据 |
|------|-----|---------|
| ephemeral | 24h | 工作态中间状态 |
| short_term | 7d | 单任务记忆 |
| long_term | 永久 | 高置信经验 |
| permanent | 永久 | Skills、配置、用户偏好 |

**上下文压缩策略**：
1. 估算当前 token 数，判断是否超限
2. 保护头尾消息（system prompt + 最近交互）
3. 中间历史 LLM 摘要压缩
4. 任务链分段 checkpoint

### 内置调度系统

**CronManager 核心能力**：
- 创建/查询/暂停/删除定时任务
- Cron 表达式 + 自然语言描述双模式
- 每个 Cron 关联 `task_template` + `trigger_config`

**接入统一执行内核**：
```
Cron 触发 → system_event(type=SCHEDULED_TASK)
         → ModeratorAgent route
         → TaskGraphExecutor
         → 受预算和审批约束
```

**预置场景**：
- 每日盘后风险汇总
- 定时阈值巡检（每小时）
- 周度合规报告

### 多平台网关

**适配器抽象**：
```python
class GatewayAdapter(ABC):
    async def receive_message() -> GatewayMessage
    async def send_response(response, platform_hints)
    async def send_alert(alert, platform_hints)
    def platform_hints() -> dict
```

**消息路由**：
```
平台消息 → GatewayAdapter.receive_message()
         → 归一化为 GatewayMessage
         → 路由层判断 user_task / system_event
         → 进入统一执行入口
```

### 提示词缓存分层

**三层分离**：
```
┌─────────────────────────────────────┐
│ stable_tier (版本号管理, 极少变化)    │  ← 命中提供商端 prefix cache
├─────────────────────────────────────┤
│ context_tier (日期戳/哈希, 日级刷新) │  ← 日内共享
├─────────────────────────────────────┤
│ volatile_tier (每次刷新, 不参与缓存) │  ← 当前记忆 + 事件
└─────────────────────────────────────┘
```

**预期收益**：token 总消耗下降 20%+（stable_tier 完全命中缓存 + context_tier 日内复用）

## Drawbacks / 缺点

### 技能噪音

低质量 Skill 可能污染规划。如果 SkillProposer 的质量门槛设得不够高，或者 Skill 置信度衰减不够快，噪音 Skill 会干扰 OrchestratorAgent 的规划质量。

**缓解**：`min_confidence_for_injection` + `max_skills_per_category` + 定期归档

### 持久化迁移风险

从 Redis-only 迁移到 Redis + DB 的过渡期可能出现数据不一致。特别是在 Redis 故障恢复期间，可能出现内存数据和持久化数据版本冲突。

**缓解**：write-through 策略 + 一致性校验 + 分批迁移

### Prompt 膨胀

Skill 注入 + 记忆上下文 + 多层 prompt 可能导致 token 用量反增。如果不严格控制 volatile_tier 大小，三层分离的优化效果会被新增内容抵消。

**缓解**：注入数量上限 + 上下文压缩器 + token 实时监控

### 调度过载

Cron 任务如果定义过密或出现递归创建，可能消耗大量系统资源，影响用户显式任务的执行。

**缓解**：复用 ProactiveBudgetManager + 递归防护 + 用户任务豁免

### 平台适配复杂性

各企业通讯平台 API 变更频繁，消息格式差异大，维护多个适配器的长期成本可能较高。

**缓解**：抽象层隔离变化 + 只适配核心消息模式 + 按需扩展

> 注: 2026-06-27 Slack 和 WeChat Work 适配器已从代码库移除, 核心 GatewayAdapter 抽象层保留.

## Alternatives / 替代方案

### 方案A: 不升级（保持现状）

**描述**：系统已满足 Phase 0-4 目标，维持当前能力不变。

**Pros**：
- 无迁移风险
- 无新增复杂度
- 维护成本低

**Cons**：
- 系统无学习能力，不会随使用改进
- 记忆会过期丢失，无知识积累
- 无定时任务能力，依赖外部触发
- 单通道交互，覆盖面有限

**评估**：适合短期维护期，但不适合作为长期产品形态。

### 方案B: 只做部分升级

**描述**：只做技能自创 + 记忆永久化，暂缓调度和多平台。

**Pros**：
- 降低实施风险
- 聚焦核心价值（学习 + 记忆）
- 迭代周期短

**Cons**：
- 调度能力缺失限制自主巡检场景
- 单通道限制风控告警的触达面
- 成本优化推迟

**评估**：可作为降级方案。如果资源有限，优先实施 Phase 5（技能自创）和 Phase 6（记忆永久化），Phase 7 和 Phase 8 后续追加。

## Unresolved Questions / 待解决问题

### 1. Skill 质量控制策略

- `quality_score` 的阈值如何确定？过高会导致极少 Skill 被创建，过低会导致噪音
- 需要 A/B 实验确定最优 `confidence_threshold`
- 是否需要人工审核环节？还是完全自动化？

### 2. 多平台优先级

- ~~企业微信 vs Slack vs Telegram，优先适配哪个？~~ (已回退 2026-06-27, 具体平台适配器已移除)
- 核心 GatewayAdapter 抽象层保留, 后续可按需实现新平台适配器

### 3. 上下文压缩的质量损失

- LLM 摘要压缩会丢失信息，丢失的信息是否影响后续决策？
- 压缩后的任务完成质量下限是多少？
- 是否需要"重要信息标记"机制防止关键信息被压缩？

### 4. Cron 任务与主动性的边界

- Cron 定时任务和现有 system_event 驱动的主动任务如何协调？
- 同一个风控检查，Cron 定时触发和事件主动触发是否应该去重？
- 预算如何在 Cron 和事件之间分配？

### 5. 技能迁移和版本管理

- 模型升级后，旧模型下创建的 Skill 是否仍然适用？
- Skill 的 `applicable_conditions` 如何跨模型版本迁移？
- 是否需要 Skill 版本化，支持回滚？

## Update Log

- 2026-06-26: 创建本 RFC，提出 Hermes 五柱升级提案
