# PRD

## 1. 文档目标

本文档面向 `RiskMonitor-MultiAgent` 的下一阶段增强.

目标只有一个:

- 让 `RESUME.md` 中关于 Multi-Agent 项目的关键表述, 都能在真实代码, 真实运行链路, 真实评测结果中被验证

本文档先说明项目现状, 再给出增强方案, 最后给出分阶段验收标准.

---

## 2. 当前项目情况

### 2.1 当前已经具备的能力

- 已有 MCP Server 和一组可运行的风险工具
- 已有 `Intent -> Plan -> Critic -> Execute -> Finalize` 主流程
- 已有 RBAC 和 side effect policy 等治理骨架
- 已有短期记忆, 长期总结, 部分语义记忆接口
- 已有基础可观测性, 结果落盘, 评测 CLI 和质量门禁
- 已有多角色 Agent 框架, 包括 Intent, Orchestrator, Critic, SystemEngineer, RiskAnalyst

### 2.2 当前最核心的问题

- 复杂任务规划还不是真正的动态任务图调度, 更像固定阶段工作流
- `plan_steps` 没有稳定驱动真实工具执行和执行后重规划
- 记忆存储层有了, 但记忆没有真正驱动规划, 执行和恢复
- 多 Agent 协作仍以固定角色串联为主, 事件驱动和消息驱动还不够真实
- 评测体系可以做内部回归, 但还不足以严格证明工具调用, 审批, 重规划, 错误恢复的真实性
- `RESUME.md` 中部分表述比当前真实落地程度更超前

### 2.3 当前项目阶段判断

当前项目更准确的定位是:

- 一个已经具备工程骨架的金融风控 Multi-Agent 平台原型
- 治理框架和角色建模已经成型
- 真正的规划执行闭环, 记忆闭环, 评测真实性闭环仍需补强

---

## 3. 产品背景

### 3.1 背景

金融风控任务不是单轮问答问题.

一个可用的风控 Agent 系统至少要解决 5 件事:

- 先理解用户意图和风险上下文
- 把复杂任务拆成可执行步骤
- 调用工具拿到真实观测结果
- 在执行中根据观测结果重规划
- 对副作用动作做审批, 留下完整证据链和回放能力

如果这 5 件事没有形成闭环, 那么系统更像一个会写分析报告的 LLM 工作流, 而不是一个真正可治理的 Multi-Agent 系统.

### 3.2 立项原因

`RESUME.md` 已经把项目定位为:

- Proactive Multi-Agent 风控智能体
- LangGraph 多角色协作与 HITL 审批流
- ReAct + CoT + BDI 混合推理
- Unified Memory Architecture
- 零信任工具治理
- 全链路可观测与回放
- 42 条基准用例与完整评测体系

因此当前增强工作的目标不是再加新故事, 而是把这 7 条承诺全部做实.

---

## 4. 产品目标

### 4.1 总目标

把 `RiskMonitor-MultiAgent` 从"有骨架的多 Agent 工作流原型"升级为"简历表述和代码实现严格一致的可验证系统".

### 4.2 成功标准

项目完成后, 需要同时满足以下标准:

- 简历中的每个关键能力都有对应代码模块, 测试, 文档, 评测样例
- 主流程必须形成 `plan -> execute -> observe -> replan -> finalize` 真实闭环
- 工具调用必须产出真实 receipt, 并被后续 Agent 消费
- 记忆必须在任务前检索, 任务中更新, 任务后沉淀, 并支持恢复执行
- 副作用动作必须在真实审批链上通过或被拒绝, 不能只写兼容字段
- 评测体系必须以真实执行行为为基础, 不能主要依赖默认值和启发式补分

### 4.3 非目标

本期不追求:

- 做成通用办公 Agent
- 引入过重的分布式中间件
- 先做非常复杂的前端界面
- 追求海量工具数量

本期只做一件事:

- 让金融风控场景下的 Multi-Agent 闭环真实可运行, 可评测, 可解释, 可复盘

---

## 5. 用户与场景

### 5.1 核心用户

- Risk Manager
- Desk Head
- 风控运营人员
- 平台研发和模型研发人员

### 5.2 核心场景

- 查询某 desk 当前头寸并分析 breach 原因
- 针对多 desk 异常同时排查, 自动拆分子任务并合并结论
- 对副作用动作如写告警和提交告警执行审批
- 根据历史类似案例和长期记忆给出更稳健的行动建议
- 在执行失败后基于上下文和回执恢复运行

---

## 6. 简历承诺与落地映射

| 简历承诺 | 当前状态 | 本期要求 | 验收标准 |
| :--- | :--- | :--- | :--- |
| 多角色 Agent 推理有向图 | 部分具备 | 改成真实状态机和任务图驱动 | 同一任务可出现分支, 并行, 回退, 重规划 |
| LangGraph 多角色协作与 HITL 审批流 | 部分具备 | 审批点进入真实中断和恢复流程 | 评测样例能验证 `pending_approval -> approved -> resume` |
| ReAct + CoT + BDI 混合推理 | 骨架具备 | 推理状态必须驱动动作而不是仅记录痕迹 | 每个动作都能追溯到 thought, reason, evidence, observation |
| Unified Memory Architecture | 部分具备 | 记忆检索接入计划生成和恢复执行 | 有 memory hit, memory write, memory replay 三类指标 |
| 零信任工具治理 | 较强 | 把 registry, policy, approval, receipt 打通 | 每个副作用动作都可审计, 可拒绝, 可回放 |
| 全链路可观测与回放 | 部分具备 | 补齐 trace schema 和回放工具 | 单 run 可回放 plan, tool, approval, memory, final |
| 42 条基准用例和评测门禁 | 已有基础 | 变成真实行为评测而非兼容打分 | 所有核心指标基于真实行为事件计算 |

---

## 7. 核心增强方案

### 7.1 方向一. 真实任务图规划系统

#### 目标

把当前固定五段式流程升级为真正的任务图执行系统.

#### Checklist

- [ ] Checkpoint 7.1.1 `TaskGraph` 契约落地
  - 实现项: 新增 `task_graph.py` 或等价契约文件. 定义 `TaskNode` `TaskEdge` `TaskGraph` `TaskExecutionState` 结构. 节点至少支持 `tool_call` `delegate` `ask_human` `analyze` `finalize` `stop` `replan`.
  - 验收方法: 运行 TaskGraph 契约单测和负例单测.
  - 验收证据: 单测报告. 契约样例 JSON. 非法节点类型和非法依赖被拒绝的错误输出.
  - 通过标准: 契约单测全部通过. 非法输入全部被拒绝. 图结构可稳定序列化和反序列化.
- [ ] Checkpoint 7.1.2 计划输出改为显式任务图
  - 实现项: `Orchestrator` 不再只输出线性 `plan_steps`. 必须输出带节点 ID 和依赖边的任务图. 每个节点都包含 `step_id` `parent_id` `status` `reason` `evidence`.
  - 验收方法: 运行 3 个规划类 benchmark case 和 1 组负例 case.
  - 验收证据: `results/` 中的任务图产物. trace 中的节点和边. 负例中的 schema error.
  - 通过标准: 3 个 benchmark case 全部生成合法任务图. 每个节点字段完整率为 100%.
- [ ] Checkpoint 7.1.3 任务图调度器替代固定五段式执行
  - 实现项: 保留当前工作流入口, 但内部执行器切换为任务图调度器. 调度器支持就绪节点选择, 条件分支, 并行 fan out 和收敛.
  - 验收方法: 运行 `make test` 中新增的调度器集成测试. 再运行 2 个 medium case 和 2 个 complex case.
  - 验收证据: trace 中的节点状态流转. 并行节点时间线. 调度器日志.
  - 通过标准: fixed workflow 逻辑不再承担主执行职责. 4 个 case 均由任务图调度器驱动完成.
- [ ] Checkpoint 7.1.4 真实 replan 闭环
  - 实现项: 在 `TOOL_FAILED` `NEW_EVIDENCE` `CRITIC_REJECTED` 事件后支持局部重规划. 新增节点必须带 `replan_from_step_id`.
  - 验收方法: 运行 3 个 complex replan benchmark case.
  - 验收证据: trace 中 `replan_count >= 1`. 新增 step 与旧 step 的父子关系. Critic 审查记录.
  - 通过标准: 3 个 case 全部出现真实 replan. 最终输出引用 replan 后新增 receipt.
- [ ] Checkpoint 7.1.5 失败恢复和 step 级重试
  - 实现项: 支持 step 级 retry 和从失败节点恢复. 不允许整任务默认重跑.
  - 验收方法: 运行 2 个故障注入 case. 一个是工具超时. 一个是参数错误修复后恢复.
  - 验收证据: trace 中的 retry 记录和 resume 记录. 上游成功节点未重复执行的日志.
  - 通过标准: 2 个 case 均从失败 step 继续. 已成功上游 step 的重复执行次数为 0.
- [ ] Checkpoint 7.1.6 并行子任务真实落地
  - 实现项: 至少支持 `SystemEngineer` 和 `RiskAnalyst` 的并行 delegation. 最终由 `Moderator` 或 `Orchestrator` 汇总.
  - 验收方法: 运行 2 个并行协作 benchmark case.
  - 验收证据: trace 中同时进行的子任务时间线. 汇总节点的输入来源字段.
  - 通过标准: 2 个 case 均存在并行节点. 汇总结果同时引用两个子分支产物.

### 7.2 方向二. 工具调用闭环增强

#### 目标

把"会规划工具"升级为"会稳定执行工具并消费结果".

#### Checklist

- [ ] Checkpoint 7.2.1 统一 `Command -> Executor -> Receipt` 闭环
  - 实现项: 删除隐式工具调用路径. 所有工具调用只能通过 `tool_registry.py` 和 `tool_executor.py`.
  - 验收方法: 对现有工具调用路径做 grep 检查并运行工具执行相关单测.
  - 验收证据: 搜索结果中不存在绕过 `tool_executor.py` 的主路径. 单测报告.
  - 通过标准: 所有生产路径仅保留 1 个工具执行入口.
- [ ] Checkpoint 7.2.2 标准化 receipt 契约
  - 实现项: receipt 固定包含 `command_id` `tool_name` `inputs` `outputs` `status` `error` `latency_ms` `side_effect` `approval_state`.
  - 验收方法: 运行 receipt 契约单测和 1 个真实工具调用集成测试.
  - 验收证据: receipt JSON 样例. 缺字段负例的契约报错.
  - 通过标准: 所有成功和失败 receipt 的字段完整率为 100%.
- [ ] Checkpoint 7.2.3 receipt 回灌规划和审查链路
  - 实现项: `Orchestrator` `Critic` 和执行 Agent 都能读取前序 receipt. 最终结论必须引用至少 1 个 receipt.
  - 验收方法: 运行 3 个多步工具 benchmark case.
  - 验收证据: trace 中 agent 输入含 receipt 引用. final 输出中的 `receipt_command_ids`.
  - 通过标准: 3 个 case 的最终输出 receipt 绑定率达到 100%.
- [ ] Checkpoint 7.2.4 工具预算和失败治理
  - 实现项: 增加工具超时, 最大重试次数, 预算上限, 失败分类 `permission` `validation` `runtime` `dependency`.
  - 验收方法: 运行 4 个故障注入 case.
  - 验收证据: 失败分类统计. timeout 日志. retry 计数.
  - 通过标准: 4 类故障都能被正确分类. 超时和重试策略生效.
- [ ] Checkpoint 7.2.5 副作用工具审批化
  - 实现项: `write_alert` 和 `submit_alerts` 必须进入审批状态机. registry 中所有 `side_effect=true` 工具都自动受控.
  - 验收方法: 运行安全 benchmark 和副作用集成测试.
  - 验收证据: approval trace. 未审批拒绝记录. 已审批成功记录.
  - 通过标准: 未审批副作用调用全部被阻断. 已审批后才能执行成功.
- [ ] Checkpoint 7.2.6 工具执行指标真实化
  - 实现项: 评测报告中输出真实 `tool_call_count` `tool_success_rate` `tool_timeout_rate` `tool_retry_rate`.
  - 验收方法: 运行完整评测 CLI.
  - 验收证据: results summary 和 trace 计数对齐报告.
  - 通过标准: 以上指标全部来自真实 receipt 聚合. 默认值占比为 0.

### 7.3 方向三. Unified Memory 真正落地

#### 目标

把当前存储型 memory 改造成真正参与决策的 memory system.

#### Checklist

- [ ] Checkpoint 7.3.1 三层记忆契约
  - 实现项: 定义 `episodic` `semantic` `procedural` 三类记忆的 schema 和存储边界. 每条记忆都包含 `source` `confidence` `created_by` `scope` `trace_ref`.
  - 验收方法: 运行 memory schema 单测和迁移脚本测试.
  - 验收证据: schema 样例. 存储映射文档. 非法记忆条目报错.
  - 通过标准: 三类记忆可独立写入和读取. 字段校验覆盖率 100%.
- [ ] Checkpoint 7.3.2 plan 前强制记忆检索
  - 实现项: 在 `Orchestrator` 生成任务图前执行记忆检索. 检索结果进入 planning context.
  - 验收方法: 运行 3 个 memory retrieval benchmark case.
  - 验收证据: trace 中的 `memory_hits`. 规划输入中的记忆摘要. 关闭 memory 开关后的对照结果.
  - 通过标准: 3 个 case 全部出现 memory hit. 无记忆模式下不出现该字段.
- [ ] Checkpoint 7.3.3 working memory 和经验沉淀
  - 实现项: 执行过程中写 working memory. 任务结束后由 `Critic` 写入 run summary 和 procedural lesson.
  - 验收方法: 运行 2 个多步任务 case.
  - 验收证据: run 过程中新增的 working memory 条目. 任务结束后的 summary 和 lesson 记录.
  - 通过标准: 每个多步任务至少写入 1 条 working memory 和 1 条长期总结.
- [ ] Checkpoint 7.3.4 语义记忆真实接入
  - 实现项: `search_semantic()` 接入真实向量索引. 不允许返回空实现.
  - 验收方法: 运行 upsert query 集成测试和 1 个 few-shot memory case.
  - 验收证据: 向量库查询结果. 相似案例命中日志. few-shot prompt 片段.
  - 通过标准: 语义检索路径可稳定返回非空命中. few-shot 样例中至少引用 1 条历史案例.
- [ ] Checkpoint 7.3.5 resume from run 和 resume from step
  - 实现项: 支持从 `run_id` 和 `step_id` 恢复. 恢复时要复用 receipt 和 memory state.
  - 验收方法: 运行 2 个中断恢复 case.
  - 验收证据: 恢复前后 trace 对比. 已完成 step 未重复执行的记录.
  - 通过标准: 2 个恢复 case 全通过. 已完成 step 重复执行次数为 0.
- [ ] Checkpoint 7.3.6 memory 价值评测
  - 实现项: 新增 `memory_hit_rate` `memory_usefulness` `resume_success_rate`. `memory_usefulness` 定义为开启 memory 与关闭 memory 的任务成功率差值和 evidence 完整率差值的加权分.
  - 验收方法: 在同一 benchmark 上跑 `memory_on` 和 `memory_off` 两组对照实验.
  - 验收证据: A/B 报告. 指标计算脚本输出.
  - 通过标准: 至少 1 类任务在 `memory_on` 下的 `task_success_rate` 或 `evidence_coverage` 提升不低于 10%.

### 7.4 方向四. 主动性与事件驱动协作

#### 目标

把"被调用才工作"升级为"可持续感知, 主动协作, 事件触发".

#### Checklist

- [ ] Checkpoint 7.4.1 事件协议和 Message Bus 主流程化
  - 实现项: 定义统一事件 schema. 至少包括 `TASK_CREATED` `TOOL_FINISHED` `RISK_BREACH_DETECTED` `APPROVAL_REQUIRED` `HUMAN_FEEDBACK_RECEIVED`.
  - 验收方法: 运行消息契约单测和 2 个事件流集成测试.
  - 验收证据: 事件样例 JSON. Bus 中的消息历史. 非法事件拒绝记录.
  - 通过标准: 主流程中的关键状态转移全部由事件驱动. 非法事件全部被拒绝.
- [ ] Checkpoint 7.4.2 `ModeratorAgent` 落地
  - 实现项: 增加 `ModeratorAgent` 决定下一位发言或执行的 Agent. 它必须消费事件而不是直接依赖固定顺序.
  - 验收方法: 运行 2 个多 Agent 协作 case.
  - 验收证据: trace 中的 moderator decision 记录. 下一跳 agent 选择日志.
  - 通过标准: 2 个 case 均出现至少 3 次由 `ModeratorAgent` 做出的显式调度决策.
- [ ] Checkpoint 7.4.3 主动订阅和主动发起协作
  - 实现项: Agent 支持订阅事件并在满足触发条件时主动发起分析任务. 主动任务必须带触发原因和证据.
  - 验收方法: 运行 1 个后台主动发现 breach 的 benchmark case 和 1 个人工触发对照 case.
  - 验收证据: 无用户输入下创建的任务记录. 触发证据字段. 对照实验日志.
  - 通过标准: 至少 1 个 case 在没有新用户输入时由 Agent 主动创建任务.
- [ ] Checkpoint 7.4.4 冲突仲裁和优先级规则
  - 实现项: 定义冲突检测规则和仲裁策略. 至少覆盖结论冲突, 工具选择冲突, 审批优先级冲突.
  - 验收方法: 运行 3 个 conflict benchmark case.
  - 验收证据: conflict trace. arbitration result. 被放弃路径的原因说明.
  - 通过标准: 3 个冲突 case 全部产生明确仲裁结果. 不允许静默覆盖冲突.
- [ ] Checkpoint 7.4.5 主动性预算和熔断
  - 实现项: 为主动协作增加频控, token budget, 最大并发数和熔断规则.
  - 验收方法: 运行压测脚本和异常风暴模拟 case.
  - 验收证据: budget 统计. throttling 日志. circuit breaker 日志.
  - 通过标准: 异常风暴下主动任务数不超过预算上限. 熔断触发后不再继续扩散任务.
- [ ] Checkpoint 7.4.6 协作链路可回放
  - 实现项: 所有消息都进入 trace. 必须能回放谁在什么事件后做了什么决策.
  - 验收方法: 运行 2 个复杂协作 case 并执行 replay CLI.
  - 验收证据: replay 输出. message trace 时间线.
  - 通过标准: 2 个 case 的消息链完整率达到 100%.

### 7.5 方向五. HITL 审批和恢复执行

#### 目标

把审批从兼容字段升级为真实产品能力.

#### Checklist

- [ ] Checkpoint 7.5.1 审批状态机落地
  - 实现项: 定义 `pending` `approved` `rejected` `expired` `resumed` 状态机和合法转换.
  - 验收方法: 运行审批状态机单测和负例单测.
  - 验收证据: 状态转换图. 非法转换报错.
  - 通过标准: 合法转换全部通过. 非法转换全部阻断.
- [ ] Checkpoint 7.5.2 step 和 command 两级审批
  - 实现项: 同时支持 step 级审批和 command 级审批. 审批请求必须带理由, 风险等级, 影响范围, 建议动作.
  - 验收方法: 运行 3 个审批 benchmark case.
  - 验收证据: step 级审批记录. command 级审批记录. 请求详情字段.
  - 通过标准: 3 个 case 覆盖通过, 驳回, 超时三种结果.
- [ ] Checkpoint 7.5.3 审批结果写入 trace 和 memory
  - 实现项: 审批结果必须同步写入 trace 和 memory, 供后续决策使用.
  - 验收方法: 运行 1 个审批后重规划 case.
  - 验收证据: trace 中的 approval event. memory 中的审批摘要.
  - 通过标准: 审批结果在 trace 和 memory 中都可查询到, 且字段一致.
- [ ] Checkpoint 7.5.4 从阻断点恢复执行
  - 实现项: `pending_approval` 不再只是最终状态. 批准后从阻断 step 继续, 不重新执行已成功上游 step.
  - 验收方法: 运行 2 个 pending resume case.
  - 验收证据: resume trace. 上游 step 执行次数统计.
  - 通过标准: 2 个 case 全部从阻断点继续. 上游成功 step 重复执行次数为 0.

### 7.6 方向六. 可观测性与回放

#### 目标

把当前结果文件升级成真正的全链路 trace 系统.

#### Checklist

- [ ] Checkpoint 7.6.1 `run_trace.v2` 契约
  - 实现项: 定义统一 trace schema. 至少包含 task, plan, step, message, command, receipt, approval, memory, final, version_snapshot.
  - 验收方法: 运行 trace schema 单测和负例单测.
  - 验收证据: trace schema 样例. 非法 trace 报错.
  - 通过标准: trace 结构校验通过率 100%. 非法 trace 全部被拒绝.
- [ ] Checkpoint 7.6.2 step 级时间线和失败定位
  - 实现项: 为每个 step 记录开始时间, 结束时间, 前驱, 后继, 失败原因, 相关 receipt 和相关 memory.
  - 验收方法: 运行 2 个失败注入 case.
  - 验收证据: step timeline. failure summary.
  - 通过标准: 任意一次失败都能在 1 条时间线上定位到具体 step 和失败原因.
- [ ] Checkpoint 7.6.3 回放 CLI
  - 实现项: 提供单 run 回放 CLI. 输出任务摘要, 关键事件, 失败点, receipt 证据和最终结论.
  - 验收方法: 对 2 个历史 run 执行 replay 命令.
  - 验收证据: CLI 输出文件和终端输出样例.
  - 通过标准: 单命令可以生成可读回放报告. 无需人工拼接多份文件.
- [ ] Checkpoint 7.6.4 版本快照
  - 实现项: trace 中固定记录 prompt 版本, policy 版本, model, toolset, benchmark config.
  - 验收方法: 在同一 benchmark 上跑两组不同配置.
  - 验收证据: 两份 run trace 中的 version snapshot 差异.
  - 通过标准: 任意两次运行都能用 trace 直接对比版本差异.
- [ ] Checkpoint 7.6.5 trace 作为评测输入源
  - 实现项: 评测器直接消费 `run_trace.v2` 而不是依赖兼容拼装字段.
  - 验收方法: 用同一批 trace 运行评测 CLI 和 gate CLI.
  - 验收证据: 评测输入日志. trace 到 summary 的映射结果.
  - 通过标准: 评测主链路只依赖 trace. 兼容层不再承担主评测职责.

### 7.7 方向七. 评测体系重构

#### 目标

让评测系统真正证明系统能力, 而不是只证明工作流没报错.

#### Checklist

- [ ] Checkpoint 7.7.1 核心指标改为真实事件计算
  - 实现项: 所有核心指标直接从 `run_trace.v2` 聚合. 明确区分 `workflow_success` `task_success` `tool_success` `approval_correctness` `replan_quality`.
  - 验收方法: 运行指标单测和 trace 聚合对照测试.
  - 验收证据: 指标计算脚本输出. trace 到 metric 的映射表.
  - 通过标准: `tool_call_count` `approval_count` `replan_count` `memory_hit_count` 均来自 trace 真实计数. 默认值占比为 0.
- [ ] Checkpoint 7.7.2 指标口径和阈值固化
  - 实现项: 明确定义 `task_success_rate` `tool_selection_accuracy` `receipt_binding_rate` `replan_success_rate` `approval_correctness` `memory_hit_rate` `memory_usefulness` `resume_success_rate` `dangerous_action_block_rate` `message_trace_completeness` `factuality_score` `evidence_coverage` 的公式和阈值.
  - 验收方法: 运行指标公式单测和阈值配置加载测试.
  - 验收证据: 指标定义表. gate 阈值配置文件.
  - 通过标准: 每个指标都有公式, 数据源, 聚合口径, 目标阈值, gate 规则.
- [ ] Checkpoint 7.7.3 金标准人工标注集
  - 实现项: 建立最小人工标注集. 至少覆盖 `Simple` `Medium` `Complex` `Recovery` `Approval` `Memory` `Safety`.
  - 验收方法: 随机抽样校验标注一致性.
  - 验收证据: 标注文件. 标注指南. 一致性统计结果.
  - 通过标准: 每个类别至少 3 个 case. 双人标注一致率不低于 0.85.
- [ ] Checkpoint 7.7.4 LLM Judge 角色收缩
  - 实现项: LLM Judge 只评估开放文本质量, 不参与行为事实判定. 行为事实全部由 trace 和标注决定.
  - 验收方法: 运行 1 组 judge on 和 judge off 对照实验.
  - 验收证据: 两组评测结果对比. 行为指标保持不变的证明.
  - 通过标准: 关闭 LLM Judge 后, 行为类指标数值不发生变化.
- [ ] Checkpoint 7.7.5 数据集扩展和 baseline 体系
  - 实现项: 评测集扩展为 `Simple` `Medium` `Complex` `Recovery` `Approval` `Memory` `Safety`. 增加单 Agent baseline 和无记忆 baseline.
  - 验收方法: 运行完整 benchmark 和 baseline compare CLI.
  - 验收证据: benchmark 清单. baseline 对比报告.
  - 通过标准: 至少 42 个 case 重构完成. 每个类别至少 4 个 case. baseline 对比可稳定复现.
- [ ] Checkpoint 7.7.6 gate 只阻断真实行为问题
  - 实现项: gate 仅依据真实行为指标和事实指标阻断. 启发式占位指标只能告警不能硬阻断.
  - 验收方法: 运行 2 组 gate 对照 case. 一组真实失败. 一组仅启发式异常.
  - 验收证据: gate decision log. 被阻断原因列表.
  - 通过标准: 真实失败 case 被阻断. 仅启发式异常 case 不被硬阻断.

---

## 8. 分阶段实施计划

### Phase 0. 对齐与止血

#### 目标

先解决文档叙事和真实代码不一致的问题, 并补最关键的执行缺口.

#### Checklist

- [ ] 修正 README, ARCHITECTURE, ROADMAP 中已完成状态的口径
- [ ] 梳理唯一主流程和唯一工具执行入口
- [ ] 补齐 `write_alert` 等危险工具的评测覆盖
- [ ] 让评测结果中真实记录工具调用数
- [ ] 文档中不再把未完成能力标成已完成
- [ ] 最新评测结果可看到真实 receipt

### Phase 1. 真实执行闭环

#### 目标

先打通 `plan -> command -> receipt -> final`.

#### Checklist

- [ ] 实现任务图模型
- [ ] 打通统一 command receipt 闭环
- [ ] 增加 step 级 trace
- [ ] 实现基础 replan
- [ ] Medium 和 Complex case 中真实工具调用稳定发生
- [ ] 最终输出引用 receipt 的比例大于 95%

### Phase 2. 记忆闭环和恢复执行

#### 目标

让 memory 成为真正的系统能力.

#### Checklist

- [ ] 实现三层记忆模型
- [ ] 接入 semantic retrieval
- [ ] 实现 run resume 和 step resume
- [ ] 增加 memory 质量评测
- [ ] 有记忆版本优于无记忆 baseline
- [ ] 中断后恢复成功率大于 80%

### Phase 3. 事件驱动和主动协作

#### 目标

让多 Agent 协作从固定串联升级为消息和事件驱动.

#### Checklist

- [ ] 增加 `ModeratorAgent`
- [ ] 定义标准事件协议
- [ ] 让 Message Bus 成为主流程一部分
- [ ] 实现主动感知和冲突仲裁
- [ ] 至少 2 类复杂任务依赖事件触发和动态协作
- [ ] 协作指标基于真实消息而非默认值

### Phase 4. 评测和门禁生产化

#### 目标

让评测体系对外也能站得住.

#### Checklist

- [ ] 重构 benchmark
- [ ] 建立人工标注校准集
- [ ] 让评测基于 trace 驱动
- [ ] 实现更严格的 quality gate
- [ ] 42 个 case 在新评测口径下重新跑通
- [ ] 结果可复现, 可解释, 可对比

---

## 9. 详细需求清单

### 9.1 功能需求

- [ ] FR-1: 系统必须支持任务图级规划和执行
- [ ] FR-2: 系统必须支持真实工具调用回执
- [ ] FR-3: 系统必须支持 step 级审批和恢复
- [ ] FR-4: 系统必须支持消息驱动协作
- [ ] FR-5: 系统必须支持语义记忆检索和经验沉淀
- [ ] FR-6: 系统必须支持任务失败后的恢复执行
- [ ] FR-7: 系统必须支持 trace 回放
- [ ] FR-8: 系统必须支持基于真实行为事件的评测

### 9.2 非功能需求

- [ ] NFR-1: 所有关键状态都必须可持久化
- [ ] NFR-2: 所有副作用动作都必须可审计
- [ ] NFR-3: 所有最终结论都必须可追溯到输入, receipt 或 memory
- [ ] NFR-4: 评测结果必须可复现
- [ ] NFR-5: 每个阶段都要有单测, 集成测试, benchmark 样例

---

## 10. 风险与取舍

### 10.1 主要风险

- 引入任务图和事件驱动后, 系统复杂度会显著上升
- 记忆系统一旦做错, 会带来错误迁移和错误强化
- 过度主动性会造成噪声事件和成本失控
- 评测指标如果定义过多, 会拖慢迭代速度

### 10.2 设计取舍

- 优先把真实执行闭环做通, 再扩充 Agent 数量
- 优先做金融风控高价值场景, 不追求通用性
- 优先保证 trace 和评测可信, 再追求漂亮指标
- 优先做可恢复和可审批, 再追求极致自治

---

## 11. 发布准入标准

以下条件同时满足, 才允许对外按照简历口径讲完整能力:

- `plan -> execute -> observe -> replan` 闭环已在代码和 benchmark 中成立
- 真实工具调用, 审批, 回执, 恢复都有 case 证明
- 记忆检索已经真实参与规划和恢复
- 评测结果中关键计数项全部来自真实事件
- 文档, README, ROADMAP, PRD, RESUME 的能力口径保持一致

---

## 12. 对 `RESUME.md` 的落地结论

当本 PRD 的 Phase 0 到 Phase 4 全部完成后, 可以有把握地保留并强化以下表述:

- Proactive Multi-Agent 系统
- LangGraph 多角色协作与 HITL 审批流
- ReAct + CoT + BDI 混合推理
- Unified Memory Architecture
- 零信任工具治理体系
- 全链路可观测与回放
- 42 条基准用例和质量门禁

在此之前, 对外表述需要坚持一个原则:

- 只讲已经被真实代码, 真实 trace, 真实 benchmark 证明过的能力

---

## 13. 相关文档

- [README.md](../README.md)
- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [ROADMAP.md](./ROADMAP.md)
