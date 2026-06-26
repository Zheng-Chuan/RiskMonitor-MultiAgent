# Phase 5: 技能自创闭环

## 状态

待开始 ☐

## 核心目标

让系统具备从经验中自动创建和改进可复用技能的能力, 将当前的 lesson 沉淀机制升级为完整的 Skill 系统, 实现从经验到可复用技能的自动化闭环.

## 时间盒与资源

- 时间：3-4 周
- 优先级：高

## 工作范围

### In Scope
- 技能自创与自我改进闭环 (方向八 §14.4)
- Skill 契约与存储层
- Skill 自动创建链路
- Skill 注入规划链路
- Skill 置信度动态更新
- Skill 改进闭环
- Skill 治理与噪音控制

### Out of Scope（本期不做）
- 记忆永久化存储层 (Phase 6)
- 上下文压缩 (Phase 6)
- 内置调度系统 (Phase 7)
- 多平台网关 (Phase 7)
- 提示词缓存分层 (Phase 8)

## 详细 Checkpoint

### 方向八. 技能自创与自我改进闭环 (§14.4)

#### 目标

将当前的 lesson 沉淀机制升级为完整的 Skill 系统, 实现从经验到可复用技能的自动化闭环.

#### 设计要点

- Skill 定义为 Markdown + YAML frontmatter, 包含 `name` `tags` `applicable_conditions` `steps` `failure_boundary` `confidence` `write_origin`
- SkillStore 基于现有 SemanticIndexer 做向量化检索
- OrchestratorAgent 规划阶段自动注入匹配 Skill 作为 few-shot
- Critic 评审后若 quality_score >= threshold 则自动提议创建或更新 Skill
- 执行反馈驱动 Skill 置信度衰减或增长

#### Checkpoint 详细内容

- [ ] Checkpoint 14.3.1 Skill 契约与存储层
  - 实现项: 新增 `src/riskmonitor_multiagent/skills/` 模块. 定义 `Skill` 契约, 包含 `skill_id` `name` `tags` `applicable_conditions` `steps` `failure_boundary` `confidence` `write_origin` `created_at` `updated_at` `usage_count` `success_rate`. 实现 `SkillStore` 支持 CRUD 和语义检索.
  - 验收方法: 运行 Skill 契约单测和存储层集成测试.
  - 验收证据: Skill JSON 样例. 语义检索命中记录. 非法 Skill 拒绝记录.
  - 通过标准: 契约单测全部通过. 语义检索能命中相关 Skill. 非法输入全部被拒绝.

- [ ] Checkpoint 14.3.2 Skill 自动创建链路
  - 实现项: 在 `CriticAgent.final_review()` 之后新增 `SkillProposer`. 当 quality_score >= confidence_threshold 时, 自动从 run_trace 提取可复用模式, 生成 Skill 提案. 检查语义去重后决定是创建新 Skill 还是更新已有 Skill.
  - 验收方法: 运行 3 个高质量完成的 benchmark case, 检查是否产生 Skill 提案.
  - 验收证据: Skill 提案记录. 去重检查日志. 新建或更新的 Skill 快照.
  - 通过标准: 3 个 case 中至少 2 个产生 Skill 提案. 重复模式不会创建新 Skill 而是更新已有 Skill.

- [ ] Checkpoint 14.3.3 Skill 注入规划链路
  - 实现项: 在 `OrchestratorAgent.orchestrate()` 之前, 新增 `retrieve_applicable_skills()`. 基于当前 intent 和上下文检索匹配的 Skill, 以结构化 few-shot 形式注入规划 prompt. 支持 skill_on / skill_off 对照.
  - 验收方法: 运行 2 个有历史 Skill 可复用的 case 和 1 个 skill_off 对照 case.
  - 验收证据: 规划 prompt 中的 Skill 注入片段. 最终计划中的 Skill 引用. skill_off 下无 Skill 引用.
  - 通过标准: 至少 1 个 case 中 Skill 明确参与规划生成. skill_off 下该引用消失.

- [ ] Checkpoint 14.3.4 Skill 置信度动态更新
  - 实现项: 每次 Skill 被使用后, 根据执行结果更新置信度. 成功执行 +delta, 失败执行 -delta. 低置信度 Skill 自动降权或标记为 deprecated. 支持手动确认和人工审核.
  - 验收方法: 运行 2 个 Skill 成功复用 case 和 2 个 Skill 失败 case.
  - 验收证据: 置信度变化记录. 降权或 deprecated 标记. usage_count 和 success_rate 统计.
  - 通过标准: 成功使用后置信度上升. 失败使用后置信度下降. 连续失败的 Skill 被自动降权.

- [ ] Checkpoint 14.3.5 Skill 改进闭环
  - 实现项: 当 Skill 被使用但产生次优结果时, Critic 可提议 Skill 修订. 修订内容追加到 Skill 的 `revision_history`. 支持 A/B 对比修订前后的效果.
  - 验收方法: 运行 1 个 Skill 修订场景 case 和 1 个修订前后 A/B 对照.
  - 验收证据: Skill revision_history 记录. A/B 对照结果. 修订后效果提升的证据.
  - 通过标准: 修订链路完整. 修订后的 Skill 在相同场景中表现不劣于修订前.

- [ ] Checkpoint 14.3.6 Skill 治理与噪音控制
  - 实现项: 增加 `max_skills_per_category` `min_confidence_for_injection` `max_skill_age_days` 治理参数. 低质量 Skill 自动归档. Skill 注入数量限制防止 prompt 膨胀.
  - 验收方法: 运行 1 个大量 Skill 积累后的规划 case 和 1 个低质量 Skill 清理 case.
  - 验收证据: Skill 注入限制日志. 归档记录. prompt token 统计不超预算.
  - 通过标准: Skill 注入不超过限额. 低置信度 Skill 不参与规划注入. prompt 长度可控.

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|----------|
| 低质量 Skill 污染规划, 导致决策退化 | 高 | 高 | 置信度门槛 + 自动降权 + 归档机制 |
| Skill 注入过多导致 prompt 膨胀超限 | 中 | 高 | max_skills_per_category 限制 + prompt token 预算 |
| Skill 去重失败导致冗余积累 | 中 | 中 | 语义去重检查 + 相似 Skill 合并策略 |
| Skill 修订引入回归 | 低 | 中 | A/B 对比验证修订效果, 保留 revision_history 可回滚 |

## 成功标准 (Exit Criteria)

- 实现 Skill 契约和 SkillStore
- 打通 Critic -> SkillProposer -> SkillStore 创建链路
- 实现 Skill 语义检索和规划注入
- 实现 Skill 置信度动态更新
- Skill 改进闭环跑通
- skill_on vs skill_off 对照实验显示收益

## 交付物清单

- [ ] 代码：`src/riskmonitor_multiagent/skills/` 模块, SkillStore, SkillProposer, 置信度更新器
- [ ] 测试：Skill 契约单测, 创建链路集成测试, 注入对照测试, 置信度更新测试
- [ ] 文档：Skill 系统设计说明, 治理参数配置指南
- [ ] 评测：skill_on vs skill_off A/B 对照实验报告

## 相关文档

- PRD：[docs/PRD.md](../PRD.md)
- 架构：[docs/ARCHITECTURE.md](../ARCHITECTURE.md)
