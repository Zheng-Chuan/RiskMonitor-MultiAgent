# Phase 1: 真实执行闭环

## 状态

已完成 ✓

## 核心目标

先打通 `plan -> command -> receipt -> final`, 把当前固定五段式流程升级为真正的任务图执行系统, 并把"会规划工具"升级为"会稳定执行工具并消费结果".

## 时间盒与资源

- 时间：2-3 周
- 优先级：高

## 工作范围

### In Scope
- 真实任务图规划系统 (方向一 §7.1)
- 工具调用闭环增强 (方向二 §7.2)
- TaskGraph 契约落地
- 统一 Command -> Executor -> Receipt 闭环
- 任务图调度器替代固定五段式执行
- 真实 replan 闭环
- 失败恢复和 step 级重试
- 并行子任务
- 副作用工具审批化

### Out of Scope（本期不做）
- 统一记忆架构完整实现
- 事件驱动协作
- 评测体系重构
- HITL 审批完整状态机

## 详细 Checkpoint

### 方向一. 真实任务图规划系统 (§7.1)

#### 目标

把当前固定五段式流程升级为真正的任务图执行系统.

- [x] Checkpoint 7.1.1 `TaskGraph` 契约落地
  - 实现项: 新增 `task_graph.py` 或等价契约文件. 定义 `TaskNode` `TaskEdge` `TaskGraph` `TaskExecutionState` 结构. 节点至少支持 `tool_call` `delegate` `ask_human` `analyze` `finalize` `stop` `replan`.
  - 验收方法: 运行 TaskGraph 契约单测和负例单测.
  - 验收证据: 单测报告. 契约样例 JSON. 非法节点类型和非法依赖被拒绝的错误输出.
  - 通过标准: 契约单测全部通过. 非法输入全部被拒绝. 图结构可稳定序列化和反序列化.

- [x] Checkpoint 7.1.2 计划输出改为显式任务图
  - 实现项: `Orchestrator` 不再只输出线性 `plan_steps`. 必须输出带节点 ID 和依赖边的任务图. 每个节点都包含 `step_id` `parent_id` `status` `reason` `evidence`.
  - 验收方法: 运行 3 个规划类 benchmark case 和 1 组负例 case.
  - 验收证据: `results/` 中的任务图产物. trace 中的节点和边. 负例中的 schema error.
  - 通过标准: 3 个 benchmark case 全部生成合法任务图. 每个节点字段完整率为 100%.

- [x] Checkpoint 7.1.3 任务图调度器替代固定五段式执行
  - 实现项: 保留当前工作流入口, 但内部执行器切换为任务图调度器. 调度器支持就绪节点选择, 条件分支, 并行 fan out 和收敛.
  - 验收方法: 运行 `make test` 中新增的调度器集成测试. 再运行 2 个 medium case 和 2 个 complex case.
  - 验收证据: trace 中的节点状态流转. 并行节点时间线. 调度器日志.
  - 通过标准: fixed workflow 逻辑不再承担主执行职责. 4 个 case 均由任务图调度器驱动完成.

- [x] Checkpoint 7.1.4 真实 replan 闭环
  - 实现项: 在 `TOOL_FAILED` `NEW_EVIDENCE` `CRITIC_REJECTED` 事件后支持局部重规划. 新增节点必须带 `replan_from_step_id`.
  - 验收方法: 运行 3 个 complex replan benchmark case.
  - 验收证据: trace 中 `replan_count >= 1`. 新增 step 与旧 step 的父子关系. Critic 审查记录.
  - 通过标准: 3 个 case 全部出现真实 replan. 最终输出引用 replan 后新增 receipt.

- [x] Checkpoint 7.1.5 失败恢复和 step 级重试
  - 实现项: 支持 step 级 retry 和从失败节点恢复. 不允许整任务默认重跑.
  - 验收方法: 运行 2 个故障注入 case. 一个是工具超时. 一个是参数错误修复后恢复.
  - 验收证据: trace 中的 retry 记录和 resume 记录. 上游成功节点未重复执行的日志.
  - 通过标准: 2 个 case 均从失败 step 继续. 已成功上游 step 的重复执行次数为 0.

- [x] Checkpoint 7.1.6 并行子任务真实落地
  - 实现项: 至少支持 `SystemEngineer` 和 `RiskAnalyst` 的并行 delegation. 最终由 `Moderator` 或 `Orchestrator` 汇总.
  - 验收方法: 运行 2 个并行协作 benchmark case.
  - 验收证据: trace 中同时进行的子任务时间线. 汇总节点的输入来源字段.
  - 通过标准: 2 个 case 均存在并行节点. 汇总结果同时引用两个子分支产物.

### 方向二. 工具调用闭环增强 (§7.2)

#### 目标

把"会规划工具"升级为"会稳定执行工具并消费结果".

- [x] Checkpoint 7.2.1 统一 `Command -> Executor -> Receipt` 闭环
  - 实现项: 删除隐式工具调用路径. 所有工具调用只能通过 `tool_registry.py` 和 `tool_executor.py`.
  - 验收方法: 对现有工具调用路径做 grep 检查并运行工具执行相关单测.
  - 验收证据: 搜索结果中不存在绕过 `tool_executor.py` 的主路径. 单测报告.
  - 通过标准: 所有生产路径仅保留 1 个工具执行入口.

- [x] Checkpoint 7.2.2 标准化 receipt 契约
  - 实现项: receipt 固定包含 `command_id` `tool_name` `inputs` `outputs` `status` `error` `latency_ms` `side_effect` `approval_state`.
  - 验收方法: 运行 receipt 契约单测和 1 个真实工具调用集成测试.
  - 验收证据: receipt JSON 样例. 缺字段负例的契约报错.
  - 通过标准: 所有成功和失败 receipt 的字段完整率为 100%.

- [x] Checkpoint 7.2.3 receipt 回灌规划和审查链路
  - 实现项: `Orchestrator` `Critic` 和执行 Agent 都能读取前序 receipt. 最终结论必须引用至少 1 个 receipt.
  - 验收方法: 运行 3 个多步工具 benchmark case.
  - 验收证据: trace 中 agent 输入含 receipt 引用. final 输出中的 `receipt_command_ids`.
  - 通过标准: 3 个 case 的最终输出 receipt 绑定率达到 100%.

- [x] Checkpoint 7.2.4 工具预算和失败治理
  - 实现项: 增加工具超时, 最大重试次数, 预算上限, 失败分类 `permission` `validation` `runtime` `dependency`.
  - 验收方法: 运行 4 个故障注入 case.
  - 验收证据: 失败分类统计. timeout 日志. retry 计数.
  - 通过标准: 4 类故障都能被正确分类. 超时和重试策略生效.

- [x] Checkpoint 7.2.5 副作用工具审批化
  - 实现项: `write_alert` 和 `submit_alerts` 必须进入审批状态机. registry 中所有 `side_effect=true` 工具都自动受控.
  - 验收方法: 运行安全 benchmark 和副作用集成测试.
  - 验收证据: approval trace. 未审批拒绝记录. 已审批成功记录.
  - 通过标准: 未审批副作用调用全部被阻断. 已审批后才能执行成功.

- [x] Checkpoint 7.2.6 工具执行指标真实化
  - 实现项: 评测报告中输出真实 `tool_call_count` `tool_success_rate` `tool_timeout_rate` `tool_retry_rate`.
  - 验收方法: 运行完整评测 CLI.
  - 验收证据: results summary 和 trace 计数对齐报告.
  - 通过标准: 以上指标全部来自真实 receipt 聚合. 默认值占比为 0.

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|----------|
| 任务图引入后系统复杂度显著上升 | 高 | 高 | 保留当前工作流入口作为兼容层, 内部切换为任务图调度器 |
| 工具执行路径重构影响已有功能 | 中 | 高 | 统一入口后保留完整单测覆盖, 逐步迁移 |
| replan 导致无限循环 | 低 | 高 | 增加 replan 次数上限和预算治理 |
| 并行子任务引入竞态条件 | 中 | 中 | 收敛节点明确等待所有并行分支完成 |

## 成功标准 (Exit Criteria)

- 实现任务图模型
- 打通统一 command receipt 闭环
- 增加 step 级 trace
- 实现基础 replan
- Medium 和 Complex case 中真实工具调用稳定发生
- 最终输出引用 receipt 的比例大于 95%

## 交付物清单

- [x] 代码：TaskGraph 契约, 任务图调度器, 统一工具执行入口, receipt 契约, replan 机制
- [x] 测试：TaskGraph 单测, 调度器集成测试, receipt 契约单测, replan case, 故障注入 case
- [x] 文档：任务图设计文档, 工具调用链路说明
- [x] 评测：Medium/Complex/Recovery benchmark case 全部基于真实任务图执行

## 相关文档

- PRD：[docs/PRD.md](../PRD.md)
- 架构：[docs/ARCHITECTURE.md](../ARCHITECTURE.md)
