# Phase 2: 记忆闭环

## 状态

已完成 ✓

## 核心目标

把当前以 shared memory 为主的基础版实现, 升级为和 `RESUME.md` 对齐的 Unified Memory Architecture, 让 memory 成为真正的系统能力.

## 时间盒与资源

- 时间：2-3 周
- 优先级：高

## 工作范围

### In Scope
- Unified Memory Architecture 目标版 (方向三 §7.3)
- 单 Agent 私有任务记忆模板
- 多 Agent 公共记忆看板
- 规划/执行/恢复强制消费记忆
- 高置信长期经验沉淀
- few-shot 经验迁移链路
- 角色漂移和记忆混杂治理
- Unified Memory A/B 价值评测

### Out of Scope（本期不做）
- 记忆永久化存储层 (Phase 6)
- 上下文压缩 (Phase 6)
- 技能自创 (Phase 5)
- 事件驱动协作

## 详细 Checkpoint

### 方向三. Unified Memory Architecture 目标版 (§7.3)

#### 目标

把当前以 shared memory 为主的基础版实现, 升级为和 `RESUME.md` 对齐的 Unified Memory Architecture.

目标态必须同时满足 4 个要求:

- 单 Agent 在单任务内拥有仅本角色可读可写的 private task memory
- 多 Agent 拥有带角色和视角标识的 shared memory board
- `Critic Agent` 只把高置信决策沉淀为结构化长期经验
- 记忆不只用于存取, 还必须真实驱动 planning execution resume 和 few-shot reuse

#### 当前状态

当前版本已经形成统一的 7.3 主链.

- `private task memory` 已落地到主链执行路径, 并形成稳定模板
- `shared memory board` 已从流水式条目升级为显式 board 视图
- `Critic Agent` 已按 `confidence policy` 沉淀高置信长期经验, 同时保留 rejected 记录
- `planning execution resume` 三条链路都已显式消费记忆, `few-shot reuse` 也已返回可复用结构化片段
- `role_drift_rate` `memory_cross_talk_rate` 已进入指标与 trace
- 轻量 A/B 验收已经跑通, `memory_on` 在 memory benchmark 上能稳定命中历史经验并产生 few-shot reuse

7.3 已全部收口完成.

- A/B 脚本与三组 baseline 入口已经补齐
- 最新轻量报告位于 `eval/results/memory_ab/20260515_195830_summary.json` 和 `eval/results/memory_ab/20260515_195830_summary.md`

#### Checkpoint 详细内容

- [x] Checkpoint 7.3.1 单 Agent 私有任务记忆模板
  - 实现项: 为每个 agent 增加 `private task memory` 模板, 至少包含 `role` `task_goal` `current_progress` `open_questions` `recent_observations` `next_intended_action`. private memory 默认只能由对应 agent 读写.
  - 验收方法: 运行 2 个多角色任务 case, 检查 engineer 和 analyst 的 private memory 是否隔离.
  - 验收证据: private memory 样例. agent 级查询结果. 非所属 agent 读取被拒绝或返回空结果.
  - 通过标准: 同一 run 中两个 agent 都有独立 private task memory, 且互不串读.

- [x] Checkpoint 7.3.2 多 Agent 公共记忆看板
  - 实现项: 在 shared memory 之上增加显式 `shared memory board` 视图. 每条公共记忆必须带 `agent_role` `agent_perspective` `task_phase` `confidence` `trace_ref`.
  - 验收方法: 运行 2 个并行协作 case 和 1 个冲突 case.
  - 验收证据: shared board 快照. 不同 agent 写入的视角字段. conflict case 中的 board 变化记录.
  - 通过标准: 并行协作过程中公共记忆能清楚区分角色和视角, 不出现无来源的混杂条目.

- [x] Checkpoint 7.3.3 规划 执行 恢复都强制消费记忆
  - 实现项: `Orchestrator` 规划前必须读 shared board 和相关 private memory 摘要. `TaskGraphExecutor` 在关键 step 执行前后更新 working memory. `resume` 必须复用 private memory shared board receipt state 和 run summary.
  - 验收方法: 运行 3 个 case, 分别覆盖 planning execution resume.
  - 验收证据: trace 中的 `memory_hits` `memory_writes` `resume_memory_state`. prompt 或上下文字段中的 memory 摘要.
  - 通过标准: 三条链路都能看到显式记忆消费和更新记录, 不是只在任务结束后写 memory.

- [x] Checkpoint 7.3.4 高置信长期经验沉淀
  - 实现项: 由 `Critic Agent` 基于 `confidence policy` 只沉淀高置信结论. 长期经验条目至少包含 `agent_perspective` `decision_pattern` `applicable_conditions` `failure_boundary` `evidence_refs`.
  - 验收方法: 运行 2 个成功 case 和 2 个低置信 case.
  - 验收证据: long term experience 样例. 被拒绝沉淀的低置信记录. confidence policy 日志.
  - 通过标准: 只有满足置信门槛的经验被沉淀. 低置信 summary 不进入长期经验库.

- [x] Checkpoint 7.3.5 few-shot 经验迁移链路
  - 实现项: `search_semantic()` 不只返回相似文本, 还要返回可复用的结构化经验片段. 规划时必须能显式引用历史案例中的 `decision_pattern` 或 `failure_boundary`.
  - 验收方法: 运行 1 个相似案例复用 case 和 1 个 memory_off 对照 case.
  - 验收证据: few-shot prompt 片段. 经验命中日志. 最终计划中的历史经验引用.
  - 通过标准: 至少 1 个 case 中能明确看到历史经验参与当前计划生成, 且 memory_off 下该引用消失.

- [x] Checkpoint 7.3.6 角色漂移和记忆混杂治理
  - 实现项: 增加 `role_drift_rate` `memory_cross_talk_rate` 两类指标. 对 private/shared memory 增加角色边界检查和污染检测.
  - 验收方法: 运行 2 个长任务 case 和 1 个故意注入错误记忆 case.
  - 验收证据: 角色漂移指标. cross talk 检测日志. 错误记忆被隔离或降权的记录.
  - 通过标准: 长任务中角色边界保持稳定, 错误来源的公共记忆不会静默污染所有 agent.

- [x] Checkpoint 7.3.7 Unified Memory A/B 价值评测
  - 实现项: 新增 `memory_hit_rate` `memory_usefulness` `resume_success_rate` `few_shot_reuse_rate` `role_drift_rate` `memory_cross_talk_rate`. `memory_usefulness` 继续采用 memory_on 和 memory_off 对照.
  - 验收方法: 在同一 benchmark 上跑 `memory_on` `memory_off` `private_disabled` 三组实验.
  - 验收证据: `eval/results/memory_ab/20260515_195830_summary.json` `eval/results/memory_ab/20260515_195830_summary.md` 和对应三组结果文件. 其中 `memory_on` 对比 `memory_off` 的 `memory_hit_rate` 从 `0.0` 提升到 `1.0`, `memory_usefulness` 从 `0.0` 提升到 `0.6`, `few_shot_reuse_rate` 从 `0.0` 提升到 `1.0`.
  - 通过标准: 已满足. 当前最小 memory benchmark 中 `memory_on` 相比 `memory_off` 的 `evidence_coverage` 提升 `20%`, 且 `few_shot_reuse_rate > 0`. `private_disabled` 在该共享经验复用 case 上与 `memory_on` 基本持平, 说明这个 case 主要验证 shared memory 与 semantic few-shot 价值, 不是私有记忆主导场景.

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|----------|
| 记忆做错导致错误迁移和错误强化 | 中 | 高 | Critic 基于 confidence policy 只沉淀高置信结论 |
| 记忆混杂导致角色漂移 | 中 | 中 | 增加角色边界检查和 cross talk 污染检测 |
| few-shot 注入错误历史案例 | 低 | 高 | 设置置信门槛, 低置信经验不参与规划注入 |
| A/B 实验设计偏差 | 低 | 中 | 三组对照 (memory_on / memory_off / private_disabled) 交叉验证 |

## 成功标准 (Exit Criteria)

- 实现三层记忆模型
- 接入 semantic retrieval
- 实现 run resume 和 step resume
- 增加 memory 质量评测
- 有记忆版本优于无记忆 baseline
- 中断后恢复成功率大于 80%

## 交付物清单

- [x] 代码：private task memory, shared memory board, confidence policy, few-shot retrieval, role drift detection
- [x] 测试：记忆隔离单测, A/B 对照脚本, resume 集成测试
- [x] 文档：Unified Memory Architecture 设计说明
- [x] 评测：memory benchmark, A/B 对照结果报告

## 相关文档

- PRD：[docs/PRD.md](../PRD.md)
- 架构：[docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- A/B 结果：[eval/results/memory_ab/](../../eval/results/memory_ab/)
