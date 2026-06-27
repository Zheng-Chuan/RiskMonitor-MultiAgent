# INTERVIEW - 面试问答集

本文件整理了针对 RiskMonitor-MultiAgent 项目的高压面试问题与参考答案.

关联架构文档: [ARCHITECTURE.md](file:///Users/zhengchuan/Documents/TECH/Repo/RiskMonitor-MultiAgent/docs/ARCHITECTURE.md)

这不是八股文.
这是从资深面试官视角出发, 专门拷打你是否真的做过这个项目, 是否真的理解 `TaskGraph` `ToolExecutor` `Memory` `Approval` `Trace` `Benchmark` 的一份问答手册.

如果你对其中一半问题都答不上来, 那说明你对项目的理解还停留在功能介绍层, 没有进入系统设计层.

---

## 目录

- [项目定位与 Why MultiAgent](#project)
- [核心 Workflow 与执行内核](#workflow)
- [TaskGraph 与调度系统](#taskgraph)
- [工具调用与安全治理](#tooling)
- [Memory 与 Resume](#memory)
- [事件驱动与主动协作](#event)
- [审批 恢复与安全边界](#approval)
- [Trace Replay 与评测体系](#trace)
- [架构 Trade-off 与局限](#tradeoff)

---

<a id="project"></a>
## 项目定位与 Why MultiAgent

### 面试官: 项目定位拷问

---

### 一. 为什么不是单 Agent

#### Q1: "你为什么要做 MultiAgent. 单个强模型加工具调用不行吗. 你这个系统是不是过度设计了"

**参考答案**:

"这是这个项目最应该先回答的问题.

我不是为了追热点才做 MultiAgent, 而是因为这个项目要解决的是金融风控里的长链路任务, 它天然有 4 个困难:

1. 任务长链路:
   - 不是一次回答就结束
   - 要先识别意图, 再规划, 再执行, 再审查, 再恢复

2. 角色分工不同:
   - `IntentAgent` 负责把输入归类
   - `OrchestratorAgent` 负责产出任务图
   - `CriticAgent` 负责挑错和 replan
   - `SystemEngineer` 和 `RiskAnalyst` 负责并行执行子任务
   - `ModeratorAgent` 负责系统事件入口仲裁

3. 风险控制要求高:
   - 工具调用不能只看功能通不通
   - 还要做 RBAC, 审批, budget, receipt, trace

4. 需要可恢复:
   - 单 prompt 很难做 step 级恢复
   - 但任务图和 execution_state 可以天然支持 resume

所以我不是简单把一个任务拆给多个模型聊天, 而是把系统拆成多个有明确输入 输出 失败模式和治理边界的角色.

如果任务只是一次性 FAQ, 我不会上 MultiAgent.
但这个项目是风控执行系统, 不是聊天机器人, 所以需要 programmatic controller 加角色化协作."

---

#### Q2: "你说是多智能体, 那它到底是 supervisor 架构, 还是 peer to peer 架构"

**参考答案**:

"它本质上是 supervisor 型架构, 不是 peer to peer.

核心原因是这个项目重视的是可控性, 可审计性, 和统一执行内核.

具体来说:

1. `ProactiveWorkflow` 是统一控制层
2. `OrchestratorAgent` 决定计划结构
3. `TaskGraphExecutor` 决定执行顺序
4. `ToolExecutor` 决定工具是否真的能执行
5. `CriticAgent` 有审查权, 但没有直接旁路执行权

也就是说, agent 之间不是自由协商和投票, 而是在统一控制流下做分工.

这样做的好处是:

- 更容易 replay
- 更容易做 benchmark
- 更容易查谁造成了错误
- 更容易加审批和预算

代价是:

- 创造性和自治程度不如 peer to peer
- 中心控制层可能成为瓶颈

但对金融风控来说, 这个 trade-off 是合理的."

---

#### Q3: "那你这个项目最像什么. 是 agent framework 还是 workflow engine"

**参考答案**:

"更准确地说, 它是 agentic workflow engine.

原因是:

1. 它不是裸 agent 对话
   - 它有显式 `TaskGraph`
   - 有显式 `TaskGraphExecutor`
   - 有显式 `run_trace.v2`

2. 它不是纯 workflow engine
   - 计划不是人工静态编排
   - 而是 `OrchestratorAgent` 动态生成
   - `CriticAgent` 可以触发 replan

3. 它是 programmatic controller 和 LLM planner 的混合
   - LLM 决定做什么
   - 程序决定是否允许这么做

这也是我认为它比很多 demo 式 agent 项目更接近生产系统的原因."

---

<a id="workflow"></a>
## 核心 Workflow 与执行内核

### 面试官: 主链路拷问

---

### 二. 主链是不是讲得清楚

#### Q4: "别讲概念. 你把这个项目一次 user_task 的真实主链按顺序说出来"

**参考答案**:

"主链是固定的, 不是 agent 随机聊天.

顺序是:

1. `run_proactive_workflow`
   - 生成 `run_id`
   - 初始化 `run_context`

2. `IntentAgent`
   - 做意图识别
   - 输出 `primary_intent_type` 和证据

3. `planning memory`
   - 查 recent memory
   - 查 semantic memory
   - 如果是 resume, 再合并 `memory_state` 和 `run_summary`

4. `OrchestratorAgent`
   - 产出 `orchestrator_output.v1`
   - 经过 normalize 变成显式 `task_graph`

5. `CriticAgent`
   - 审查任务图
   - 如果发现有问题, 触发 replan

6. `TaskGraphExecutor`
   - 按依赖调度各节点
   - 节点类型包括 `delegate` `tool_call` `finalize` `ask_human` `replan` `stop`

7. `ToolExecutor`
   - 对 `tool_call` 节点做 registry RBAC budget approval receipt

8. `final_output`
   - 汇总执行结果

9. persist
   - 写 memory
   - 写 `run_trace.v2`

所以这个系统不是 agent 自由发挥, 而是统一主链加显式状态机."

---

#### Q5: "你说只有一个执行内核. 那 `system_event` 和 `user_task` 到底哪里统一了"

**参考答案**:

"统一点不在入口, 而在 run model 和 execution kernel.

1. `user_task`
   - 直接进入 `run_proactive_workflow`

2. `system_event`
   - 先经过 `validate_event`
   - 再经过 `ModeratorAgent`
   - 再转成 unified task

3. 两者最终统一到:
   - 同一个 `run_id`
   - 同一个 `RunContext`
   - 同一个 `ProactiveWorkflow`
   - 同一个 `TaskGraphExecutor`
   - 同一个 `receipt`
   - 同一个 `run_trace`

这件事很重要.
因为如果 `system_event` 和 `user_task` 分别跑两套主链, 后面 replay 和评测都会裂开."

---

#### Q6: "如果我把 `ModeratorAgent` 去掉, 会发生什么"

**参考答案**:

"系统不会立刻不能跑, 但主动协作会失控.

因为 `ModeratorAgent` 的价值不是多一个角色, 而是把 `system_event` 的入口收口.

去掉之后会有 3 个问题:

1. 事件没有统一首站
   - 不同 agent 可能直接吃事件
   - 路由逻辑分散

2. 冲突仲裁失去中心
   - 结论冲突
   - 工具选择冲突
   - 审批优先级冲突
   - 都没有统一仲裁点

3. trace 不好看
   - replay 时不知道是谁决定了下一跳

所以 `ModeratorAgent` 不是为了好看, 而是为了让 `system_event` 入口具备可治理性."

---

<a id="taskgraph"></a>
## TaskGraph 与调度系统

### 面试官: TaskGraph 拷问

---

### 三. 任务图到底是不是核心能力

#### Q7: "你为什么非要搞 `TaskGraph`. 一个 `plan_steps` 数组不够吗"

**参考答案**:

"`plan_steps` 只适合线性流程, 但这个项目需要的是:

- 并行 fan out
- 收敛 finalize
- step 级 retry
- step 级 resume
- replan 后接子图
- 审批阻断后继续

如果还是线性数组, 这些能力都会变成一堆 if else patch.

而 `TaskGraph` 提供了:

1. 节点类型约束
2. 依赖边约束
3. 循环依赖检测
4. 调度依据
5. trace 单位
6. resume 最小颗粒

所以 `TaskGraph` 不是数据结构炫技, 而是后续所有执行能力的基础."

---

#### Q8: "任务图每次都可能不一样. 你怎么保证不会生成一堆不可执行的垃圾图"

**参考答案**:

"我没有把可靠性押宝在 LLM 一次生成对.

而是做了两层保护:

1. 上游契约层
   - `validate_orchestrator_output`
   - `validate_task_graph`
   - 检查节点字段 节点类型 依赖关系 特殊字段

2. normalize 层
   - 自动补 `step_id`
   - 自动补 `reason`
   - 自动补 `evidence`
   - 把 `plan_steps` 规整成合法图

也就是说, LLM 负责提出图, 程序负责把它收敛成可执行图.

这是典型的 agent 系统工程化思路.
不能信模型一次就完美, 必须用 schema 和 normalize 做收口."

---

#### Q9: "你的 replan 是真 replan 还是只是打个标记说我重规划了"

**参考答案**:

"是真 replan, 不是布尔标记.

主要有两种触发:

1. `CriticAgent` 拒绝当前计划
2. 运行期失败触发 runtime replan

真实落地表现为:

- 会生成新的计划
- 会形成新的 `task_graph` 或新子图
- 新节点带 `replan_from_step_id`
- 新图重新进入执行器
- 最终输出要引用 replan 后新增的 receipt

如果只是写一个 `replan=True`, 那不叫 replan, 只能叫日志.
这个项目做的是结构性重规划."

---

#### Q10: "step 级恢复到底有什么价值. 为什么不整任务重跑, 简单得多"

**参考答案**:

"整任务重跑最简单, 但对真实执行系统最糟糕.

坏处有 4 个:

1. 浪费成本
   - 已成功的工具调用又跑一遍

2. 污染外部世界
   - 有副作用的步骤可能重复执行

3. 审计不可信
   - 你分不清这次结果来自第一次还是第二次

4. 用户体验差
   - 失败一点点, 却全部重来

所以我做的是:

- 记录 `failed_step_id` 和 `blocked_step_id`
- resume 时只清失败节点和其下游
- 已成功上游节点不重跑

这个设计本质上是在把 agent workflow 从 demo 升级成可恢复系统."

---

<a id="tooling"></a>
## 工具调用与安全治理

### 面试官: Tool 调用拷问

---

### 四. 工具调用是不是只是 function call 套壳

#### Q11: "你这个工具调用和 OpenAI function calling 有什么本质区别"

**参考答案**:

"OpenAI function calling 解决的是模型按 schema 产出参数.

我这个项目解决的是生产级工具治理闭环.

真正多出来的部分是:

1. `tool_registry`
   - 工具先注册
   - 定义 capability owner risk_level timeout allowed_targets

2. `ToolExecutor`
   - 所有工具统一经由一个执行入口

3. RBAC
   - 不同 target_agent 只能调被允许的工具

4. approval
   - side effect 工具必须进审批状态机

5. budget
   - 控制总调用数和副作用调用数

6. receipt
   - 每次调用都产出标准回执

所以我做的不是 function calling 壳子, 而是 command -> executor -> receipt 的治理闭环."

---

#### Q12: "你说工具调用安全. 那到底安全在哪里. 不要泛泛而谈"

**参考答案**:

"安全性主要靠 5 层.

1. catalog safety
   - agent 不能发明工具
   - 必须从 registry 里选

2. role safety
   - `system_engineer` 和 `risk_analyst` 只能做 read_only 类动作
   - `manager` 才能做 side_effect

3. policy safety
   - 副作用工具要求 `approval`
   - 某些工具要求 `reason`

4. budget safety
   - 防止工具风暴
   - 防止 side effect 连续执行

5. receipt safety
   - 执行结果要过契约校验
   - 非法回执直接判失败

也就是说, 安全不是只靠 prompt 告诫模型别乱调工具, 而是代码层强约束."

---

#### Q13: "如果工具返回的是错的, 但 schema 是对的, 你怎么处理"

**参考答案**:

"这是个真实难点.

当前系统解决的是 3 件事:

1. 至少保证结构可信
   - `receipt` 字段完整
   - 失败分类清楚

2. 让错误可审计
   - inputs outputs error latency 都进 trace

3. 让后续 agent 可读
   - `Orchestrator` `Critic` 和最终输出都能引用 receipt

但我要实话实说:

当前系统对 `schema 正确但语义错误` 的处理还不够强.
现在更多依赖:

- `CriticAgent` 的审查
- downstream 结果矛盾时触发 replan
- benchmark 暴露系统性误差

如果下一步继续做, 我会补两件事:

1. tool specific post validator
2. receipt-level semantic checker

这也是当前系统从工程可控走向更强语义可靠性的下一步."

---

<a id="memory"></a>
## Memory 与 Resume

### 面试官: 记忆机制拷问

---

### 五. 记忆是不是只是 Redis 缓存

#### Q14: "你说自己有 memory system. 结果我一看不就是存 Redis 吗. 这也叫记忆"

**参考答案**:

"如果只是把内容塞进 Redis, 那当然不叫 memory system.

这个项目之所以还能叫 memory system, 是因为它至少做了 4 件事:

1. 有显式类型体系
   - `episodic`
   - `semantic`
   - `procedural`

2. 有使用时机
   - planning 前强制检索
   - 不是结束后随便存一下

3. 有运行中写入
   - step 完成写 `working_memory`
   - run 完成写 `summary` 和 `lesson`

4. 有恢复路径
   - `resume` 时回灌 `memory_state` 和 `run_summary`

所以它不是一个智能脑, 但它是一个真正参与决策和恢复的 memory pipeline."

---

#### Q15: "既然是多智能体, 为什么不是每个 agent 都有独立长期记忆"

**参考答案**:

"这是一个很好的拷打点.

底层是支持 `private` 和 `shared` 两种 scope 的.
但当前主链实际更偏中心化 memory.

也就是说:

- 架构上支持 agent 私有记忆
- 但生产主链主要写和读的是 shared memory

原因是这个项目当前优先级是:

1. 保证统一 trace
2. 保证统一 replay
3. 保证统一 resume
4. 保证 benchmark 可计算

如果每个 agent 都搞一套私有长期记忆, 当前评测和审计复杂度会陡增.

所以现在的 trade-off 是:

- 优先统一共享记忆
- 私有记忆能力预留在 schema 和 store
- 但不在主链大规模启用

这不是最强智能体设计, 但对当前项目阶段是合理的工程选择."

---

#### Q16: "resume 真正复用了什么. 还是只是从某个 step 重新开始"

**参考答案**:

"resume 复用的不只是 step_id.

它至少复用 4 类状态:

1. `task_graph`
2. `execution_state`
3. `memory_state`
4. `run_summary`

所以 resume 的本质不是 goto 某一行代码.
而是恢复一个中间态 run.

如果只有 step_id, 那上游为什么不重跑, 当前为什么能继续, 都说不清楚.
真正让恢复成立的, 是显式的 execution_state 和 memory_state."

---

<a id="event"></a>
## 事件驱动与主动协作

### 面试官: 主动性拷问

---

### 六. 主动协作是不是 PPT 能力

#### Q17: "你怎么证明它真的有事件驱动和主动协作, 不是用户每次都手动触发"

**参考答案**:

"证明点在于系统允许 `system_event` 在没有新用户输入的前提下创建 follow-up task.

关键不是能收事件, 而是:

1. 事件有统一 schema
2. 事件先过 `ModeratorAgent`
3. agent 可以基于事件主动创建任务
4. 新任务仍然走统一主链
5. 整条链有 `run_trace`

所以主动性不是后台打印一条日志, 而是:

`system_event -> moderator -> proactive task creation -> unified task_graph execution`

如果没有最后一步统一进入执行内核, 那就不叫真正主动协作."

---

#### Q18: "事件驱动系统最容易炸的地方是什么. 你这个项目怎么防"

**参考答案**:

"最容易炸的是事件风暴和主动任务扩散.

典型问题是:

1. 一个异常触发多个事件
2. 多个事件又触发多个 follow-up task
3. follow-up task 再产生更多事件
4. 最后系统自己把自己打爆

这个项目的防法是:

1. proactive budget
   - 限制主动任务数量

2. token budget
   - 限制主动协作消耗

3. max concurrent proactive runs
   - 控并发

4. circuit breaker
   - 异常风暴时直接熔断

而且用户显式任务有豁免规则, 不会被主动链路误伤.

这说明主动性不是越强越好, 一定要有治理."

---

<a id="approval"></a>
## 审批 恢复与安全边界

### 面试官: 审批和恢复拷问

---

### 七. 安全能力是不是只是字段摆设

#### Q19: "审批状态机如果只是写在 trace 里, 没有拦截真实执行, 那其实没意义. 你这里是真阻断吗"

**参考答案**:

"是真阻断, 不是 trace decoration.

判断依据是:

1. side effect 工具先生成 `approval_request`
2. 没有审批通过时, 当前 command 不会执行成功
3. 状态会进入 `pending` 或 `blocked`
4. `execution_state` 会记录 `blocked_step_id`
5. 后续必须靠 `resume` 才继续

所以审批不是结果字段, 而是控制流的一部分.
这也是为什么我说这个项目做的是 HITL capability, 不是 HITL annotation."

---

#### Q20: "为什么要做 step 级审批和 command 级审批两层. 一层不够吗"

**参考答案**:

"两层审批解决的是不同粒度的问题.

1. command 级审批
   - 解决具体工具调用是否允许
   - 适合 side effect 工具

2. step 级审批
   - 解决当前整个任务步骤是否需要人工确认
   - 适合高风险决策节点

如果只有 command 级:
   - 你能控制单个写操作
   - 但控制不了更高层的业务动作

如果只有 step 级:
   - 你能控制大动作
   - 但工具层细粒度风控会变粗

所以两层并存是为了同时覆盖业务风险和执行风险."

---

<a id="trace"></a>
## Trace Replay 与评测体系

### 面试官: 可观测性和评测拷问

---

### 八. 你怎么证明系统不是靠演示骗我

#### Q21: "为什么你一定要做 `run_trace.v2`. 普通日志不行吗"

**参考答案**:

"普通日志适合排错, 但不适合 agent system 评测.

`run_trace.v2` 的价值在于它是统一证据面.

它把这些东西放到同一个 run 视角下:

- task
- plan
- step
- command
- receipt
- approval
- memory
- final

这样才可能支持:

1. replay
2. evaluator
3. gate

如果只是普通日志, 这些信息散在不同模块里, 根本无法稳定做行为级 benchmark."

---

#### Q22: "你的评测为什么强调 trace first 而不是只看 final answer"

**参考答案**:

"因为多智能体系统最容易伪装.

只看 final answer, 你会看不到:

- 是否真的走了任务图
- 是否真的发生了审批阻断
- 是否真的用了 memory
- 是否真的成功 resume
- 是否真的发生了 replan
- 工具成功率和超时率到底是多少

所以这个项目把很多指标定义成 trace 聚合, 比如:

- `tool_call_count`
- `tool_success_rate`
- `memory_hit_rate`
- `resume_success_rate`
- `approval_count`
- `replan_count`

这是为了避免项目看起来很智能, 但其实底层都是写死默认值."

---

#### Q23: "你怎么证明 benchmark 不是自己骗自己"

**参考答案**:

"我做了几层约束来降低自欺风险.

1. 指标尽量来自真实 trace 和 receipt 聚合
   - 不是手填 summary

2. 有 baseline compare
   - 比如 `memory_on` 对 `memory_off`
   - 比如当前版本对 baseline

3. gate 只阻断真实行为问题
   - 不是所有 warning 都拦

4. replay 可复查
   - 如果 benchmark 分高, trace 却很空, 一眼就能看出来

当然我要承认, 当前系统离最严格评测还有距离.
比如 tool 语义正确性验证还不够强.
但在 agent 工程项目里, 能把 trace receipt replay gate benchmark 打通, 已经比只看 demo 成熟很多."

---

<a id="tradeoff"></a>
## 架构 Trade-off 与局限

### 面试官: 追杀式 trade-off 拷问

---

### 九. 你知道自己系统哪里还不够好吗

#### Q24: "说三个你这个项目现在最明显的架构短板. 不要说还可以优化这种废话"

**参考答案**:

"我会直接说 3 个真实短板.

1. memory 还是偏中心化
   - schema 支持 private
   - 但主链主要还是 shared memory
   - agent 私有长期记忆还没真正形成体系

2. tool semantic validation 还不够强
   - receipt 契约很强
   - 但工具返回语义是否正确, 当前更多靠 critic 和下游暴露

3. 控制层偏强中心化
   - `ProactiveWorkflow` 和 `TaskGraphExecutor` 很强
   - 这让系统可控
   - 但也限制了更自治的协商式协作

这 3 个问题都不是 bug, 而是明确的架构 trade-off.
我知道自己牺牲了什么, 这比盲目追求全都要强更重要."

---

#### Q25: "如果让你做 2.0 版本, 你最优先改什么"

**参考答案**:

"我会优先做 3 件事.

1. 强化工具结果语义校验
   - 给关键工具补 post validator
   - 减少 schema 正确但语义错误的情况

2. 真正做 agent scoped memory
   - 让 engineer analyst 不只是输出结果
   - 而是拥有可控的私有经验层

3. 做更硬的在线治理
   - 把 budget approval gate 和 online policy 做得更细
   - 让系统更接近 production service

也就是说, 2.0 我不会优先追求更多 agent.
我会优先追求更强的 correctness 和 governance."

---

#### Q26: "最后一个问题. 你怎么用一句话定义这个项目的价值"

**参考答案**:

"一句话说, 这个项目的价值不是证明 LLM 会调用工具, 而是证明多智能体风控系统可以在统一执行内核下, 以任务图为骨架, 以审批 记忆 恢复 和 trace 为治理底座, 把长链路任务做成可执行 可恢复 可审计 可评测的系统."

---

## 使用建议

- 面试前先把每个 section 的前 2 个问题背熟
- 不要只背结论, 要能把 `为什么这样设计` 和 `为什么不那么设计` 说清楚
- 对每个答案都至少准备 1 个失败案例 或 trade-off
- 如果面试官继续深挖, 优先落到 `TaskGraphExecutor` `ToolExecutor` `memory_store` `run_trace.v2` 这四个核心点

---

## 最后提醒

真正的高级面试不是问你这个项目做了多少功能.
而是问你:

- 你为什么这样拆
- 你怎么证明它真的工作
- 它哪里会失效
- 失败后怎么恢复
- 为什么这套设计值得付出复杂度

如果你能把这几个问题讲透, 这个项目就不是 demo, 而是作品.
