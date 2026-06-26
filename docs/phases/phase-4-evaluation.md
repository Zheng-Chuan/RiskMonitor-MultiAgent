# Phase 4: 评测与门禁生产化

## 状态

已完成 ✓

## 核心目标

让评测体系对外也能站得住, 把当前结果文件升级成真正的全链路 trace 系统, 让评测系统真正证明系统能力, 而不是只证明工作流没报错.

## 时间盒与资源

- 时间：2-3 周
- 优先级：高

## 工作范围

### In Scope
- 可观测性与回放 (方向六 §7.6)
- 评测体系重构 (方向七 §7.7)
- run_trace.v2 契约
- step 级时间线和失败定位
- 回放 CLI
- 版本快照
- trace 作为评测输入源
- 核心指标改为真实事件计算
- 指标口径和阈值固化
- 金标准人工标注集
- LLM Judge 角色收缩
- 数据集扩展和 baseline 体系
- gate 只阻断真实行为问题

### Out of Scope（本期不做）
- 前端可视化界面
- 自动化 CI/CD 集成
- 外部对接标准评测平台

## 详细 Checkpoint

### 方向六. 可观测性与回放 (§7.6)

#### 目标

把当前结果文件升级成真正的全链路 trace 系统.

- [x] Checkpoint 7.6.1 `run_trace.v2` 契约
  - 实现项: 定义统一 trace schema. 至少包含 task, plan, step, message, command, receipt, approval, memory, final, version_snapshot.
  - 验收方法: 运行 trace schema 单测和负例单测.
  - 验收证据: trace schema 样例. 非法 trace 报错.
  - 通过标准: trace 结构校验通过率 100%. 非法 trace 全部被拒绝.

- [x] Checkpoint 7.6.2 step 级时间线和失败定位
  - 实现项: 为每个 step 记录开始时间, 结束时间, 前驱, 后继, 失败原因, 相关 receipt 和相关 memory.
  - 验收方法: 运行 2 个失败注入 case.
  - 验收证据: step timeline. failure summary.
  - 通过标准: 任意一次失败都能在 1 条时间线上定位到具体 step 和失败原因.

- [x] Checkpoint 7.6.3 回放 CLI
  - 实现项: 提供单 run 回放 CLI. 输出任务摘要, 关键事件, 失败点, receipt 证据和最终结论.
  - 验收方法: 对 2 个历史 run 执行 replay 命令.
  - 验收证据: CLI 输出文件和终端输出样例.
  - 通过标准: 单命令可以生成可读回放报告. 无需人工拼接多份文件.

- [x] Checkpoint 7.6.4 版本快照
  - 实现项: trace 中固定记录 prompt 版本, policy 版本, model, toolset, benchmark config.
  - 验收方法: 在同一 benchmark 上跑两组不同配置.
  - 验收证据: 两份 run trace 中的 version snapshot 差异.
  - 通过标准: 任意两次运行都能用 trace 直接对比版本差异.

- [x] Checkpoint 7.6.5 trace 作为评测输入源
  - 实现项: 评测器直接消费 `run_trace.v2` 而不是依赖兼容拼装字段.
  - 验收方法: 用同一批 trace 运行评测 CLI 和 gate CLI.
  - 验收证据: 评测输入日志. trace 到 summary 的映射结果.
  - 通过标准: 评测主链路只依赖 trace. 兼容层不再承担主评测职责.

### 方向七. 评测体系重构 (§7.7)

#### 目标

让评测系统真正证明系统能力, 而不是只证明工作流没报错.

- [x] Checkpoint 7.7.1 核心指标改为真实事件计算
  - 实现项: 所有核心指标直接从 `run_trace.v2` 聚合. 明确区分 `workflow_success` `task_success` `tool_success` `approval_correctness` `replan_quality`.
  - 验收方法: 运行指标单测和 trace 聚合对照测试.
  - 验收证据: 指标计算脚本输出. trace 到 metric 的映射表.
  - 通过标准: `tool_call_count` `approval_count` `replan_count` `memory_hit_count` 均来自 trace 真实计数. 默认值占比为 0.

- [x] Checkpoint 7.7.2 指标口径和阈值固化
  - 实现项: 明确定义 `task_success_rate` `tool_selection_accuracy` `receipt_binding_rate` `replan_success_rate` `approval_correctness` `memory_hit_rate` `memory_usefulness` `resume_success_rate` `dangerous_action_block_rate` `message_trace_completeness` `factuality_score` `evidence_coverage` 的公式和阈值.
  - 验收方法: 运行指标公式单测和阈值配置加载测试.
  - 验收证据: 指标定义表. gate 阈值配置文件.
  - 通过标准: 每个指标都有公式, 数据源, 聚合口径, 目标阈值, gate 规则.

- [x] Checkpoint 7.7.3 金标准人工标注集
  - 实现项: 建立最小人工标注集. 至少覆盖 `Simple` `Medium` `Complex` `Recovery` `Approval` `Memory` `Safety`.
  - 验收方法: 随机抽样校验标注一致性.
  - 验收证据: 标注文件. 标注指南. 一致性统计结果.
  - 通过标准: 每个类别至少 3 个 case. 双人标注一致率不低于 0.85.

- [x] Checkpoint 7.7.4 LLM Judge 角色收缩
  - 实现项: LLM Judge 只评估开放文本质量, 不参与行为事实判定. 行为事实全部由 trace 和标注决定.
  - 验收方法: 运行 1 组 judge on 和 judge off 对照实验.
  - 验收证据: 两组评测结果对比. 行为指标保持不变的证明.
  - 通过标准: 关闭 LLM Judge 后, 行为类指标数值不发生变化.

- [x] Checkpoint 7.7.5 数据集扩展和 baseline 体系
  - 实现项: 评测集扩展为 `Simple` `Medium` `Complex` `Recovery` `Approval` `Memory` `Safety`. 增加单 Agent baseline 和无记忆 baseline.
  - 验收方法: 运行完整 benchmark 和 baseline compare CLI.
  - 验收证据: benchmark 清单. baseline 对比报告.
  - 通过标准: 至少 42 个 case 重构完成. 每个类别至少 4 个 case. baseline 对比可稳定复现.

- [x] Checkpoint 7.7.6 gate 只阻断真实行为问题
  - 实现项: gate 仅依据真实行为指标和事实指标阻断. 启发式占位指标只能告警不能硬阻断.
  - 验收方法: 运行 2 组 gate 对照 case. 一组真实失败. 一组仅启发式异常.
  - 验收证据: gate decision log. 被阻断原因列表.
  - 通过标准: 真实失败 case 被阻断. 仅启发式异常 case 不被硬阻断.

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|----------|
| 评测指标定义过多拖慢迭代速度 | 中 | 中 | 区分核心指标和观察指标, 核心指标数量控制在 12 个以内 |
| trace schema 变更导致历史数据不兼容 | 低 | 高 | trace 中固定 version 字段, 支持多版本并存 |
| 人工标注集规模不足导致结论不稳定 | 中 | 中 | 先建最小标注集, 后续渐进扩展 |
| LLM Judge 收缩后评测覆盖不全 | 低 | 中 | LLM Judge 仅收缩行为判定, 保留文本质量评估 |

## 成功标准 (Exit Criteria)

- 重构 benchmark
- 建立人工标注校准集
- 让评测基于 trace 驱动
- 实现更严格的 quality gate
- 42 个 case 在新评测口径下重新跑通
- 结果可复现, 可解释, 可对比

## 交付物清单

- [x] 代码：run_trace.v2 schema, 回放 CLI, 指标计算器, gate 引擎
- [x] 测试：trace schema 单测, 指标公式单测, gate 对照测试
- [x] 文档：指标定义表, 标注指南, 评测体系说明
- [x] 评测：42+ benchmark case, 人工标注集, baseline 对比报告

## 相关文档

- PRD：[docs/PRD.md](../PRD.md)
- 架构：[docs/ARCHITECTURE.md](../ARCHITECTURE.md)
- 评测结果：[eval/reports/](../../eval/reports/)
- 标注集：[eval/datasets/gold/](../../eval/datasets/gold/)
