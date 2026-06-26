# Phase 3: 事件驱动与主动协作

## 状态

已完成 ✓

## 核心目标

让多 Agent 协作从固定串联升级为消息和事件驱动, 把当前系统升级为"双入口, 单执行内核"的协作系统, 并把审批从兼容字段升级为真实产品能力.

## 时间盒与资源

- 时间：3-4 周
- 优先级：高

## 工作范围

### In Scope
- 主动性与事件驱动协作 (方向四 §7.4)
- HITL 审批和恢复执行 (方向五 §7.5)
- 双入口运行模型和事件协议
- ModeratorAgent 落地
- 主动订阅和主动发起协作
- 冲突仲裁和优先级规则
- 主动性预算和熔断
- 协作链路可回放
- 审批状态机落地
- step 和 command 两级审批
- 从阻断点恢复执行

### Out of Scope（本期不做）
- 评测体系重构
- 内置调度系统 (Phase 7)
- 多平台网关 (Phase 7)
- 技能自创 (Phase 5)

## 详细 Checkpoint

### 方向四. 主动性与事件驱动协作 (§7.4)

#### 目标

把当前系统升级为"双入口, 单执行内核"的协作系统.

- 用户显式任务入口: 继续支持 `user_task -> intent -> orchestrator plan -> task_graph -> finished`.
- 系统感知事件入口: 支持 `system_event -> moderator -> intent 或 orchestrator -> task_graph -> finished`.
- 共性约束: 两种入口最终都必须汇合到同一套 `TaskGraphExecutor` `receipt` `memory` `trace`.
- 路由规则: 所有 `system_event` 默认必须先经过 `ModeratorAgent`, 再决定是否进入 `intent`, 是否直接进入 `orchestrator`, 或是否走局部处理链路.
- 禁止事项: 不允许形成"用户任务一套执行链路, 系统事件另一套执行链路"的双轨实现.

#### 总 Checkpoint

- [x] Checkpoint 7.4.1 双入口运行模型和事件协议
  - 实现项: 定义统一 `system_event` schema 和 `run trigger` 结构. 明确区分 `user_task` 与 `system_event` 两类入口, 但两者都映射到统一 run 上下文. 事件类型至少包括 `TASK_CREATED` `TOOL_FINISHED` `RISK_BREACH_DETECTED` `APPROVAL_REQUIRED` `HUMAN_FEEDBACK_RECEIVED`.
  - 验收方法: 运行契约单测和 2 个双入口集成测试, 其中一个从用户任务启动, 一个从系统事件启动.
  - 验收证据: 入口样例 JSON. run context 样例. Bus 中的事件历史. 非法事件拒绝记录.
  - 通过标准: `user_task` 和 `system_event` 都能创建合法 run. 非法事件全部被拒绝. 两类 run 都带统一 `run_id`.

- [x] Checkpoint 7.4.2 `ModeratorAgent` 落地
  - 实现项: 增加 `ModeratorAgent` 作为所有 `system_event` 的默认首站. 它基于规则优先决定下一跳是否进入 `intent`, `orchestrator`, `critic`, `human`, 或局部处理链路. 只有规则不能唯一决定时才允许 LLM 做 tie breaker.
  - 验收方法: 运行 2 个系统事件 case 和 1 个规则冲突 case.
  - 验收证据: trace 中的 moderator decision 记录. 规则命中日志. tie breaker 触发日志.
  - 通过标准: 3 个 case 均出现显式 moderator 决策. 规则可决定时 tie breaker 调用次数为 0. 规则不可决定时 tie breaker 调用次数大于 0.

- [x] Checkpoint 7.4.3 主动订阅和主动发起协作
  - 实现项: Agent 支持订阅 `system_event` 并在满足条件时主动创建任务或主动请求协作. 主动任务必须携带 `trigger_event_id` `trigger_reason` `trigger_evidence`. 由事件触发的新任务必须继续走统一 `intent` 或 `orchestrator` 主链.
  - 验收方法: 运行 1 个后台主动发现 breach 的 benchmark case 和 1 个用户显式任务对照 case.
  - 验收证据: 无用户输入下创建的任务记录. 触发证据字段. 统一 run trace. 对照实验日志.
  - 通过标准: 至少 1 个 case 在没有新用户输入时由 Agent 主动创建任务. 该任务最终进入统一 `TaskGraphExecutor`.

- [x] Checkpoint 7.4.4 冲突仲裁和优先级规则
  - 实现项: 定义冲突检测规则和仲裁策略. 至少覆盖结论冲突, 工具选择冲突, 审批优先级冲突. 仲裁结果必须由 `ModeratorAgent` 或其调用的 tie breaker 显式产出, 并写入统一 trace.
  - 验收方法: 运行 3 个 conflict benchmark case.
  - 验收证据: conflict trace. arbitration result. moderator decision. 被放弃路径的原因说明.
  - 通过标准: 3 个冲突 case 全部产生明确仲裁结果. 不允许静默覆盖冲突. 仲裁后的链路仍汇合到统一执行内核.

- [x] Checkpoint 7.4.5 主动性预算和熔断
  - 实现项: 为 `system_event` 触发的主动协作增加频控, token budget, 最大并发数和熔断规则. 用户显式任务链路不受主动性预算误伤, 但仍共享统一 trace 和资源统计.
  - 验收方法: 运行压测脚本, 异常风暴模拟 case, 以及 1 个并发用户任务对照 case.
  - 验收证据: budget 统计. throttling 日志. circuit breaker 日志. 用户任务未被误熔断的对照日志.
  - 通过标准: 异常风暴下主动任务数不超过预算上限. 熔断触发后不再继续扩散任务. 用户显式任务仍可正常完成主链.

- [x] Checkpoint 7.4.6 协作链路可回放
  - 实现项: 所有事件, moderator 决策, task graph 执行, receipt, memory 写入都进入同一套 trace. 必须能回放谁在什么事件或什么用户任务后做了什么决策.
  - 验收方法: 运行 1 个用户显式任务 case 和 1 个系统事件触发 case, 然后执行 replay CLI.
  - 验收证据: replay 输出. 双入口 trace 时间线. receipt 证据链. memory 引用链.
  - 通过标准: 2 个 case 的链路完整率达到 100%. 回放输出能明确显示入口类型, moderator 决策, `TaskGraphExecutor` 执行结果和最终 finished 状态.

#### 实施 Checkpoints

- [x] Checkpoint 7.4.A 双入口统一运行模型
  - 目标: 让 `user_task` 和 `system_event` 共享统一 `run_id` `run_context` `entry_type` `trace_ref`.
  - 主要文件: `src/riskmonitor_multiagent/orchestration/proactive_workflow.py` `src/riskmonitor_multiagent/contracts/event.py` 新增 `src/riskmonitor_multiagent/contracts/run_context.py`
  - 关键实现: 定义 `RunTrigger` 和 `RunContext`; 明确 `entry_type in {user_task, system_event}`; 所有 run 在入口阶段就生成统一 `run_id`; `user_task` 保持 `intent -> orchestrator -> task_graph` 主链; `system_event` 先不直接执行, 统一交给 `ModeratorAgent`
  - 对应总 checkpoint: `7.4.1` 以及 `7.4.2` 的入口约束部分
  - 测试: 新增 `tests/unit/test_run_context.py`; 新增 `tests/integration/test_dual_entry_runs.py`
  - 验收证据: 同一套返回结构中都出现 `run_id` `entry_type` `task_graph_execution`; 用户任务 case 和系统事件 case 都能创建合法 run

- [x] Checkpoint 7.4.B Event Facade 和 Moderator 汇流层
  - 目标: 把 `system_event -> moderator -> next hop -> unified execution` 变成真实主链, 不再停留在兼容壳子.
  - 主要文件: `src/riskmonitor_multiagent/orchestration/multiagent_workflow.py` `src/riskmonitor_multiagent/proactive_agents/moderator.py` `src/riskmonitor_multiagent/orchestration/message_bus.py` `src/riskmonitor_multiagent/orchestration/proactive_workflow.py`
  - 关键实现: 将 `multiagent_workflow` 从兼容骨架升级为 facade; 所有 `system_event` 默认都先过 `ModeratorAgent`; moderator 输出结构化路由决策, 决定进入 `intent` `orchestrator` `critic` `human` 或局部处理; facade 最终调用统一执行函数, 不允许旁路 `TaskGraphExecutor`
  - 对应总 checkpoint: `7.4.1` `7.4.2` 以及 `7.4.4` 的仲裁入口部分
  - 测试: 扩展 `tests/unit/test_multiagent.py`; 新增 `tests/integration/test_event_routing.py`
  - 验收证据: `system_event` 进入后 trace 中先出现 moderator decision; 规则可决定时 tie breaker 调用次数为 0; routed case 最终进入 `TaskGraphExecutor`

- [x] Checkpoint 7.4.C 主动任务创建协议
  - 目标: 让 agent 真正基于事件主动创建任务, 而不是只记录事件.
  - 主要文件: `src/riskmonitor_multiagent/proactive_agents/base.py` `src/riskmonitor_multiagent/orchestration/proactive_workflow.py` `src/riskmonitor_multiagent/contracts/event.py` `src/riskmonitor_multiagent/memory/memory_store.py`
  - 关键实现: 主动创建的任务必须带 `trigger_event_id` `trigger_reason` `trigger_evidence`; `RISK_BREACH_DETECTED` 和 `TOOL_FINISHED` 等事件可以生成 follow-up task; follow-up task 不单独走新执行器, 继续复用统一主链; 任务创建时写入 memory 和 trace 关联字段
  - 对应总 checkpoint: `7.4.3` 以及 `7.4.6` 的证据链基础
  - 测试: 新增 `tests/integration/test_proactive_task_creation.py`; 扩展 `tests/unit/test_memory.py`
  - 验收证据: 无用户输入的主动建任务记录; run trace 中能看到 trigger 字段; follow-up task 最终进入统一 `TaskGraphExecutor`

- [x] Checkpoint 7.4.D 冲突仲裁并入统一执行内核
  - 目标: 把当前冲突检测和仲裁骨架从局部能力升级为系统级能力.
  - 主要文件: `src/riskmonitor_multiagent/orchestration/iterative_refinement.py` `src/riskmonitor_multiagent/proactive_agents/moderator.py` `src/riskmonitor_multiagent/orchestration/proactive_workflow.py` `src/riskmonitor_multiagent/orchestration/message_bus.py`
  - 关键实现: 冲突检测输出结构化 `conflict trace`; 仲裁输出结构化 `arbitration result`; 记录被放弃路径和原因; 仲裁结果要能回流为 task graph patch 或下一跳 agent 决策
  - 对应总 checkpoint: `7.4.4` 以及 `7.4.6` 的回放要素
  - 测试: 扩展 `tests/unit/test_iterative_refinement.py`; 新增 `tests/integration/test_conflict_arbitration_flow.py`
  - 验收证据: 结论冲突 工具选择冲突 审批优先级冲突各有完整 trace; 不存在静默覆盖冲突; 仲裁后链路继续进入统一执行内核

- [x] Checkpoint 7.4.E 统一 Trace 和 Replay 底座
  - 目标: 把 event trace moderator decision task graph trace receipt memory 全部挂到同一套 run 视角上.
  - 主要文件: `src/riskmonitor_multiagent/orchestration/message_bus.py` `src/riskmonitor_multiagent/orchestration/proactive_workflow.py` `src/riskmonitor_multiagent/memory/memory_store.py` 新增 `src/riskmonitor_multiagent/observability/run_trace.py` 新增 `src/riskmonitor_multiagent/cli/replay.py`
  - 关键实现: 统一 trace entry schema; 所有 event moderator node receipt memory 写入都带 `run_id`; replay 直接按 `run_id` 输出双入口时间线
  - 对应总 checkpoint: `7.4.6` 并为 `7.5` `7.6` 做底座
  - 测试: 新增 `tests/unit/test_run_trace.py`; 新增 `tests/integration/test_replay_cli.py`
  - 验收证据: 用户任务 case 和系统事件 case 的 replay 输出; trace 时间线中能同时看到入口 事件 决策 执行 receipt memory

- [x] Checkpoint 7.4.F 主动性预算和熔断
  - 目标: 为 `system_event` 触发的主动协作加治理, 同时不误伤用户显式任务.
  - 主要文件: `src/riskmonitor_multiagent/orchestration/proactive_workflow.py` `src/riskmonitor_multiagent/orchestration/message_bus.py` `src/riskmonitor_multiagent/orchestration/tool_executor.py` 新增 `src/riskmonitor_multiagent/governance/proactive_budget.py`
  - 关键实现: `event burst limit`; `max concurrent proactive runs`; `token budget`; `circuit breaker`; 用户显式任务走独立豁免规则
  - 对应总 checkpoint: `7.4.5`
  - 测试: 新增 `tests/unit/test_proactive_budget.py`; 新增 `tests/integration/test_event_storm_guardrail.py`
  - 验收证据: 异常风暴下主动任务受限; circuit breaker 触发日志; 用户显式任务在对照 case 中未被误熔断

#### 推荐开发顺序

1. 先做工作包 A 和 B. 这是 7.4 的主梁. 不先立住双入口汇流层, 后面 replay 和 budget 都会返工.
2. 再做工作包 C. 让主动任务真正进入统一执行链.
3. 然后做工作包 D. 把冲突仲裁升级成系统级能力.
4. 再做工作包 E. 统一 trace 并落 replay.
5. 最后做工作包 F. 用统一 run 和 trace 做预算与熔断.

#### 明确不做的路径

- 不新建第二套 `event_executor`
- 不让 `system_event` 绕过 `TaskGraphExecutor`
- 不把 `multiagent_workflow.py` 继续堆成与 `proactive_workflow.py` 平行的第二套主流程
- 不先做 replay CLI 再补统一 trace
- 不先做 budget 再补双入口 run model

#### 里程碑验收

- M1: 用户显式任务和系统事件都能生成统一 run, 并共享 `run_id`
- M2: 所有 `system_event` 默认先过 `ModeratorAgent`, 并最终汇入统一执行函数
- M3: 至少 1 个主动事件在无用户输入时生成 follow-up task, 且该任务进入 `TaskGraphExecutor`
- M4: 3 类冲突都有显式仲裁结果和放弃路径原因
- M5: replay CLI 能完整回放一个 `user_task` run 和一个 `system_event` run
- M6: 异常风暴下主动协作受控, 用户显式任务不被误伤

### 方向五. HITL 审批和恢复执行 (§7.5)

#### 目标

把审批从兼容字段升级为真实产品能力.

- [x] Checkpoint 7.5.1 审批状态机落地
  - 实现项: 定义 `pending` `approved` `rejected` `expired` `resumed` 状态机和合法转换.
  - 验收方法: 运行审批状态机单测和负例单测.
  - 验收证据: 状态转换图. 非法转换报错.
  - 通过标准: 合法转换全部通过. 非法转换全部阻断.

- [x] Checkpoint 7.5.2 step 和 command 两级审批
  - 实现项: 同时支持 step 级审批和 command 级审批. 审批请求必须带理由, 风险等级, 影响范围, 建议动作.
  - 验收方法: 运行 3 个审批 benchmark case.
  - 验收证据: step 级审批记录. command 级审批记录. 请求详情字段.
  - 通过标准: 3 个 case 覆盖通过, 驳回, 超时三种结果.

- [x] Checkpoint 7.5.3 审批结果写入 trace 和 memory
  - 实现项: 审批结果必须同步写入 trace 和 memory, 供后续决策使用.
  - 验收方法: 运行 1 个审批后重规划 case.
  - 验收证据: trace 中的 approval event. memory 中的审批摘要.
  - 通过标准: 审批结果在 trace 和 memory 中都可查询到, 且字段一致.

- [x] Checkpoint 7.5.4 从阻断点恢复执行
  - 实现项: `pending_approval` 不再只是最终状态. 批准后从阻断 step 继续, 不重新执行已成功上游 step.
  - 验收方法: 运行 2 个 pending resume case.
  - 验收证据: resume trace. 上游 step 执行次数统计.
  - 通过标准: 2 个 case 全部从阻断点继续. 上游成功 step 重复执行次数为 0.

## 风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|-----|------|------|----------|
| 双入口引入的系统复杂度 | 高 | 高 | 坚持"双入口, 单执行内核"原则, 不允许形成双轨 |
| 过度主动性造成噪声事件和成本失控 | 中 | 高 | 主动性预算和熔断机制, 用户任务链路豁免 |
| 冲突仲裁逻辑难以覆盖所有场景 | 中 | 中 | 先覆盖结论/工具/审批三类核心冲突, 后续渐进扩展 |
| 审批恢复链路引入状态不一致 | 低 | 高 | 审批状态机严格约束合法转换, resume 前校验上游 step 状态 |

## 成功标准 (Exit Criteria)

- 增加 `ModeratorAgent`
- 定义标准事件协议
- 让 Message Bus 成为主流程一部分
- 实现主动感知和冲突仲裁
- 至少 2 类复杂任务依赖事件触发和动态协作
- 协作指标基于真实消息而非默认值

## 交付物清单

- [x] 代码：双入口运行模型, ModeratorAgent, 冲突仲裁, 主动性预算, 审批状态机, replay CLI
- [x] 测试：双入口集成测试, 事件路由测试, 冲突仲裁测试, 审批恢复测试, 风暴模拟测试
- [x] 文档：事件驱动协作设计, 审批流程说明
- [x] 评测：协作 benchmark case, 审批 benchmark case

## 相关文档

- PRD：[docs/PRD.md](../PRD.md)
- 架构：[docs/ARCHITECTURE.md](../ARCHITECTURE.md)
