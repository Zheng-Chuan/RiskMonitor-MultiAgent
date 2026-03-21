# ROADMAP (RiskMonitor-MultiAgent)

本项目是一个面向金融风控演示的 Multi-Agent 系统, 目标是用可治理的方式把"意图识别 → 多步规划 → 工具执行 → 证据链输出 → 可回放与成本治理"落到工程代码里.

## 当前仓库的真实边界

- 主要输入形态: 人类输入 task 或 MCP 客户端调用工具
- 不包含: Kafka/Debezium/CDC/Sentinel 事件驱动链路, Schema Registry, DLQ/Replay(事件级)
- 核心主线: Schema-first Intent Extractor + Planner-Executor(动态循环) + Critic/HITL + Unified Memory + MCP Tools

## 架构分层(以代码为准)

| Layer | Component | Responsibility | 主要实现 |
| :--- | :--- | :--- | :--- |
| Brain | Orchestrator + Critic | 规划/审查/汇总, HITL 门禁 | `src/riskmonitor_multiagent/orchestration/orchestrator_workflow.py`, `src/riskmonitor_multiagent/agents/roles.py` |
| Intent | Extractor | Schema-first 意图抽取与约束输出 | `src/riskmonitor_multiagent/agents/roles.py`, `src/riskmonitor_multiagent/contracts/intent_output.py` |
| Hands | MCP Server + Tools | 原子工具暴露, DB 读写, 风险计算 | `src/riskmonitor_multiagent/server.py`, `src/riskmonitor_multiagent/tools/mcp_tools.py` |
| Security | RBAC + Side-effect Policy | 工具能力分级, 审批/拒绝证据 | `src/riskmonitor_multiagent/orchestration/tool_registry.py`, `src/riskmonitor_multiagent/orchestration/tool_executor.py`, `src/riskmonitor_multiagent/services/auth_service.py` |
| Memory | Unified Memory | 短期/长期/语义记忆统一协议 | `src/riskmonitor_multiagent/memory/unified_memory.py`, `src/riskmonitor_multiagent/memory/stores.py`, `src/riskmonitor_multiagent/knowledge/chroma_store.py` |
| Observability | Metrics + Logging | 指标与结构化日志 | `src/riskmonitor_multiagent/observability/metrics.py`, `src/riskmonitor_multiagent/services/logging_service.py`, `src/riskmonitor_multiagent/services/prometheus_metrics_service.py` |
| Governance | Versions + Cost | prompt/policy 版本与成本限流 | `src/riskmonitor_multiagent/governance/versions.py`, `src/riskmonitor_multiagent/governance/llm_cost_governance.py` |

---

## Phase 划分

- Phase 1: 基础功能与服务化
- Phase 2: 权限与治理
- Phase 3: 契约与评测
- Phase 4: 主动性多 agent 协作系统与评估体系 (Future)

说明: 保留原有能力与验收，按业务目标重新组织。

---

## Phase 1: 基础功能与服务化

### 目标
建立项目的基础工程能力、数据访问、服务化形态和告警闭环，同时实现知识与统一记忆系统。

---

### Stage 1: MVP 监控链路与工程化底座

**目标**
- 形成端到端可复现的"查询头寸 → 聚合敞口 → 违规判断"链路
- 将数据库访问工程化，避免业务层直接依赖裸连接

**开始状态**
- 项目骨架存在，但无实际功能
- 无数据库访问封装
- 无端到端链路

**结束状态**
- MCP Server 基本可用并注册核心工具
- 头寸查询与风险聚合计算可运行
- SQLAlchemy Engine 封装与连接池配置完成
- MySQL 健康检查可用
- 配置集中管理与 `.env` 加载完成

**交付 Checklist**
- [x] MCP Server 基本可用并注册核心工具
- [x] 头寸查询与风险聚合计算可运行
- [x] 结构化输出包含 request_id 与关键字段
- [x] SQLAlchemy Engine 封装与连接池配置
- [x] MySQL 健康检查
- [x] 配置集中管理与 `.env` 加载
- [x] 端到端 smoke test 覆盖主链路

**验收 Checklist**
- [x] MCP client 可通过 stdio 调用至少 2 个工具
- [x] smoke test 可复现并通过
- [x] 集成测试可连接 MySQL 并查询 positions

---

### Stage 2: 服务化形态与告警闭环

**目标**
- 固化可运行的服务端形态，提供 health/ready/metrics
- 形成"规则评估 → 生成告警记录"的最小闭环
- MCP Server 无状态，工具语义清晰，读写边界明确

**开始状态**
- 有基础监控链路，但无服务化端点
- 无告警规则引擎
- 工具调用无鉴权

**结束状态**
- `/health`, `/ready`, `/metrics` 端点可用
- 告警规则引擎(最小集合)完成
- 告警输出格式化稳定
- 读写边界清晰，鉴权/错误结构统一

**交付 Checklist**
- [x] health 与 readiness 端点
- [x] Prometheus metrics 输出
- [x] 优雅退出(ready 先切 not_ready)
- [x] 告警规则引擎(最小集合)
- [x] 告警输出格式化
- [x] 读写边界: `monitor_desk_exposure` 无副作用，写库由 `submit_alerts` 承担
- [x] Token 鉴权
- [x] Resources/Prompts 注册

**验收 Checklist**
- [x] 未授权访问 `/metrics` 与 `/ready` 会被拒绝
- [x] `monitor_desk_exposure` 输出的 alerts 结构稳定
- [x] 未授权调用在服务端返回结构化错误

---

### Stage 3: 知识与统一记忆

**目标**
- 支持把历史告警/知识写入向量库并检索相似告警
- 统一记忆协议，短期记忆与长期记忆分层治理

**开始状态**
- 无向量知识库
- 无统一记忆系统
- 无长期记忆存储

**结束状态**
- Chroma store 封装，支持 persistent 与 http client
- 相似告警检索工具可用
- 统一记忆协议完成，支持 scope=`private|shared`
- 短期记忆使用 Redis，长期记忆使用 MongoDB
- Critic 在任务结束后产出 run_summary 并落 Mongo

**交付 Checklist**
- [x] Chroma store 封装，支持 persistent 与 http client
- [x] 相似告警检索工具路径可用
- [x] MemoryEntry normalize/validate
- [x] Redis 短期记忆支持两种 scope
- [x] Critic 在任务结束后产出 run_summary 并落 Mongo
- [x] 短期与长期接口解耦，避免把所有过程数据写入长期库

**验收 Checklist**
- [x] integration 测试可完成 upsert+query
- [x] 单测覆盖 private/shared 短期记忆写入与读取
- [x] 单测覆盖 run_summary 落 Mongo(可使用 mock client)

---

## Phase 2: 权限与治理

### 目标
建立完整的 RBAC 权限体系、副作用工具审计闭环、策略版本管理、成本治理和双核大脑编排系统。

---

### Stage 1: RBAC 与权限闭环

**目标**
- 对工具执行引入最小 RBAC，禁止跨角色调用
- 将"有副作用的动作"纳入策略与审计
- 防止"同为 read_only 但跨域滥用"的情况

**开始状态**
- 无 RBAC 权限控制
- 无副作用工具策略
- 无细粒度权限检查

**结束状态**
- 工具 registry 元信息(capability/risk/owner/side_effect_policy)完成
- command 校验与拒绝原因结构化输出
- side_effect policy: require_approval/require_reason/min_severity 完成
- 拒绝原因与证据结构化写入 receipt
- cross-role 调用 read_only 工具被拒绝
- deny reason 区分 role_not_allowed/rbac_denied

**交付 Checklist**
- [x] 工具 registry 元信息(capability/risk/owner/side_effect_policy)
- [x] command 校验与拒绝原因结构化输出
- [x] side_effect policy: require_approval/require_reason/min_severity
- [x] 拒绝原因与证据结构化写入 receipt
- [x] cross-role 调用 read_only 工具被拒绝
- [x] deny reason 区分 role_not_allowed/rbac_denied

**验收 Checklist**
- [x] system_engineer 调用 side_effect 动作会被拒绝
- [x] privileged 角色(代码里仍沿用 manager 命名) 执行 side_effect 必须审批
- [x] 未审批的 side_effect 调用返回 `approval_required`
- [x] 单测覆盖跨角色 deny

---

### Stage 2: 策略版本与成本治理

**目标**
- 输出携带 prompt_version/policy_version，便于策略迭代对比
- 为 LLM 调用提供 token bucket 限流与按 user/agent 的成本统计

**开始状态**
- 无策略版本管理
- 无 LLM 成本治理
- 无可追溯的版本维度

**结束状态**
- BaseAgent 返回 meta 包含 prompt_version/policy_version
- 对比实验最小维度: prompt_version, policy_version, model, governance 开关
- 限流启用时回退到 fallback
- 记录 tokens/calls 指标(含 user/priority)
- meta.governance 字段与 token/call 指标完成

**交付 Checklist**
- [x] BaseAgent 返回 meta 包含 prompt_version/policy_version
- [x] 限流启用时回退到 fallback
- [x] 记录 tokens/calls 指标(含 user/priority)

**验收 Checklist**
- [x] 单测/回放产物可定位版本差异
- [x] 回放产物可按版本维度聚合为实验分组
- [x] 单测覆盖 rate limit 与成本核算
- [x] 支持在同一基准集上比较不同 budget 配置的质量与成本

---

### Stage 3: 编排与双核大脑

**目标**
- 用 Orchestrator + Critic 双核完成动态规划与风险制衡
- Schema-first Intent Extractor，支持多意图输出
- 多步规划采用 Planner-Executor 动态循环，支持 plan-revise 与 mid-flight replan
- 修复多步规划常见工程缺口

**开始状态**
- 无 Orchestrator + Critic 双核
- 无 Intent Extractor
- 无动态规划循环
- 无 commands->receipts 闭环

**结束状态**
- Orchestrator 生成 plan_steps
- Critic 审查 plan 并可触发 HITL
- Context Store 记录 run 轨迹
- Intent Extractor 输出 strict JSON，支持多意图与解释，并写入 shared 短期记忆
- Executor 支持 plan_steps 多种 kind(tool_call/ask_human/stop/finalize)
- commands->receipts 接入主闭环
- HITL 细粒度: step/command 触发审批并可中断返回 pending_approval
- 证据链一致: plan/review/analysis/final 必须引用 receipts 或输入字段
- 可解释性闭环: 每个 plan_step 需要 reason，每个执行结果需要可验证 evidence

**交付 Checklist**
- [x] Orchestrator 生成 plan_steps
- [x] Critic 审查 plan 并可触发 HITL
- [x] Context Store 记录 run 轨迹
- [x] 删除 Router 角色与相关产物字段
- [x] Intent Extractor 输出 strict JSON，支持多意图与解释，并写入 shared 短期记忆
- [x] Executor 支持 plan_steps 多种 kind(tool_call/ask_human/stop/finalize) 且不会静默忽略
- [x] commands->receipts 接入主闭环: 执行 commands 生成 receipts 并回灌 Planner/Critic
- [x] HITL 细粒度: step/command 触发审批并可中断返回 pending_approval
- [x] 证据链一致: plan/review/analysis/final 必须引用 receipts 或输入字段，不满足则降级或阻断
- [x] 可解释性闭环: 每个 plan_step 需要 reason，每个执行结果需要可验证 evidence

**验收 Checklist**
- [x] `HITL_AUTO_APPROVE=0` 时可在 plan 阶段被阻断
- [x] 多意图输出可复现，disambiguation 写入 shared 短期记忆
- [x] 至少 1 个 case 生成 commands 并执行产生 receipts，Critic.review 能看到 receipts
- [x] 运行产物可逐步回答 why this step 和 what evidence proves result
- [x] `pytest -q -W error` 全量通过

---

## Phase 3: 契约与评测

### 目标
建立关键输出的契约校验、可解释性指标体系、基准测试用例和评测 CLI，将对比实验纳入日常回归。

---

### Stage 1: 契约与质量闸门

**目标**
- 对关键结构化输出进行契约校验，防止字段漂移与证据链缺失
- 将协作流程可解释性纳入质量定义，重点约束 reason 与 evidence 的一致性

**开始状态**
- 无输出契约校验
- 无证据链一致性约束
- 无质量闸门

**结束状态**
- 关键输出有 normalize/validate
- evidence 至少包含 fields/receipt_command_ids/rag_hit_ids 之一
- step_reason 与 receipt 绑定校验规则
- evidence 关联字段完整性统计输出
- degrade 降级策略完成

**交付 Checklist**
- [x] 关键输出有 normalize/validate
- [x] evidence 至少包含 fields/receipt_command_ids/rag_hit_ids 之一
- [x] 增加 step_reason 与 receipt 绑定校验规则
- [x] 增加 evidence 关联字段完整性统计输出

**验收 Checklist**
- [x] 单测覆盖 contracts 最小校验
- [x] 新增负例用例: reason 缺失，evidence 引用缺失，receipts 不一致

---

### Stage 2: 可解释性指标与基准

**目标**
- 将业务成功定义固化为可量化指标: agent 规划与执行结果都有据可依，全流程可解释可验证
- 建立统一基准集与 A/B 对比协议，支持版本和治理策略对比

**开始状态**
- 无可量化指标
- 无基准测试用例
- 无 A/B 对比协议

**结束状态**
- explainability 主指标定义完成
- evidence_coverage 与 evidence_missing_rate 定义完成
- step_reason_coverage 与 receipt_binding_rate 定义完成
- breach_hit_consistency 与 alert_write_success_rate 定义完成
- benchmark case schema 与最小样例集完成
- 评测结果产物包含 run_id, task_id, version, governance 配置快照

**交付 Checklist**
- [x] 定义 explainability 主指标
- [x] 定义 evidence_coverage 与 evidence_missing_rate
- [x] 定义 step_reason_coverage 与 receipt_binding_rate
- [x] 定义 breach_hit_consistency 与 alert_write_success_rate
- [x] 提供 benchmark case schema 与最小样例集
- [x] 评测结果产物包含 run_id, task_id, version, governance 配置快照

**验收 Checklist**
- [x] 同一基准集可稳定复现两组配置差异
- [x] 指标报告可定位到具体 run 与具体 step 的证据缺失点
- [x] 至少包含 1 组 质量优先 和 1 组 成本优先 的实验对比

---

### Stage 3: 评测 CLI 与回归

**目标**
- 提供可一键运行的评测 CLI 与质量闸门，将对比实验纳入日常回归

**开始状态**
- 无评测 CLI
- 无质量闸门
- 无日常回归流程

**结束状态**
- benchmark 运行 CLI 完成
- run 对比 CLI 与差异报告完成
- quality gate CLI 与阈值配置完成
- docs 增加评测 CLI 使用说明和示例
- Makefile 新增评测相关 target

**交付 Checklist**
- [x] 实现 benchmark 运行 CLI
- [x] 实现 run 对比 CLI 与差异报告
- [x] 实现 quality gate CLI 与阈值配置
- [x] 在 docs 增加评测 CLI 使用说明和示例
- [x] Makefile 新增评测相关 target

**验收 Checklist**
- [x] 单命令可从基准集产出 summary 报告
- [x] gate 能卡住 evidence_missing_rate 与 contract_fail_rate 超阈值
- [x] gate 输出同时包含 p95 latency 和 tokens 预算是否达标

---

## Phase 4: 主动性多 agent 协作系统与评估体系

### 目标
从"固定顺序的工作流"演进到"真正的多 Agent 协作系统"，借鉴最新的工业界（AutoGen、Microsoft Agent Framework）和学术界（GAIA、SWE-bench、MultiAgentBench、PlanBench）成果，**核心是实现 ReAct + CoT 推理范式**。

### 核心设计理念
- **ReAct 循环**：Thought → Action → Observation 动态循环
- **CoT 思维链**：每个推理步骤都有明确的理由和证据
- **动态协作，不是固定流程**：Moderator 协调，Agent 自主决定下一步
- **从被动执行到主动协作**：每个 Agent 都有目标、信念、意图
- **多种协作模式**：并行、迭代、层次
- **完整的评估体系**：借鉴 GAIA、SWE-bench、MultiAgentBench

---

### Stage 1: 基础协作（基础版）

**目标**
- 实现真正的 Message Bus（不再是占坑）
- 实现 Moderator Agent（协调者）
- 把现有 Agent 改造为支持消息模式
- 实现 Parallel Delegation 模式（Engineer 和 Analyst 并行）
- **引入 ReAct 循环基础框架**
- **引入 CoT 思维链基础框架**

**开始状态**
- Message Bus 只是占坑，未实际使用
- Agent 之间通过 LangGraph state 传数据
- 固定顺序的工作流，无动态协作
- 无 Moderator Agent
- 无 ReAct 循环
- 无 CoT 思维链

**结束状态**
- [x] Message Bus 基础实现，支持 REQUEST、RESPONSE、BROADCAST
- [x] Moderator Agent 基础实现，可决定下一步谁说话
- [x] 现有 Agent 支持消息模式
- [x] Parallel Delegation 模式可工作（代码已写但未实际使用消息总线）
- [x] 简单任务可以用新模式完成
- [x] ReAct 循环基础框架（Thought → Action → Observation）
- [x] CoT 思维链基础框架（每个步骤有 reason 和 evidence）
- [x] 真正的动态协作工作流（状态机驱动，非固定顺序）

**交付 Checklist**
- [x] Message Bus 基础实现
- [x] Moderator Agent 基础实现
- [x] 现有 Agent 支持消息模式
- [x] Parallel Delegation 模式可工作（实际使用消息总线）
- [x] 简单任务可以用新模式完成
- [x] ReAct 循环基础框架
- [x] CoT 思维链基础框架
- [x] 真正的动态协作工作流

**验收 Checklist**
- [x] 简单任务成功率 &gt; 90%
- [x] Medium 任务可以并行执行
- [x] 评估指标可以正常收集
- [x] ReAct 循环可以正常工作
- [x] CoT 思维链可以正常展示
- [x] 真正的动态协作（证明：状态机驱动，非固定顺序）

---

### Stage 2: 主动性和迭代（进阶版）

**目标**
- Agent 有主动性（目标、信念、意图）
- 支持迭代协作（多轮对话优化）
- 支持 Review-and-Revise 模式（Critic 评审 → 修改）
- 实现冲突解决机制（仲裁）
- **实现完整的 ReAct 循环（Thought → Action → Observation）**
- **实现完整的 CoT 思维链（每个步骤都有 reason 和 evidence）**

**开始状态**
- Agent 被调用时才工作，无主动性
- 无迭代协作模式
- 无冲突解决机制
- 无多轮对话优化
- 无完整的 ReAct 循环
- 无完整的 CoT 思维链

**结束状态**
- [x] Message Bus 完整版，支持 INTERRUPT、FEEDBACK
- [x] Agent 有目标、信念、意图（BDI 模型）
- [x] Iterative Refinement 模式可工作
- [x] Review-and-Revise 模式可工作
- [x] 冲突可以被解决（仲裁）
- [x] 加入 IDS、Role Specialization 等协作指标
- [x] 完整的 ReAct 循环可工作（Thought → Action → Observation）
- [x] 完整的 CoT 思维链可工作（每个步骤都有 reason 和 evidence）
- [x] ReAct + CoT 集成到实际 Agent（ReActAgentMixin）

**交付 Checklist**
- [x] Message Bus 完整版
- [x] Agent 有目标、信念、意图（BDI 模型）
- [x] Iterative Refinement 模式可工作
- [x] Review-and-Revise 模式可工作
- [x] 冲突可以被解决（仲裁）
- [x] 加入 IDS、Role Specialization 等协作指标
- [x] 完整的 ReAct 循环
- [x] 完整的 CoT 思维链
- [x] ReAct + CoT 集成到实际 Agent

**验收 Checklist**
- [x] Agent 可以主动感知环境并发起行动 (已实现 _perceive/_deliberate/_act)
- [ ] Agent 可以主动提问 (需要实现问题管理器和用户交互)
- [x] 多轮对话可以优化结果
- [x] 冲突解决率 100%
- [x] 协作指标 IDS > 0.3
- [x] ReAct 循环可以正常工作（Thought → Action → Observation）
- [x] CoT 思维链可以正常展示（每个步骤都有 reason 和 evidence）

---

### Stage 3: 完整协作模式与评估工具链

**目标**
- 支持所有协作模式（Hierarchical）
- Agent 有后台监控线程（真正的主动性）
- 完整的评估体系（P0-P3 所有指标）
- 基准测试用例设计和开发（最多 10 个用例）
- 评估工具链适配多 Agent 协作新模式
- 质量门禁（Quality Gate）
- **ReAct + CoT 深度集成**

**开始状态**
- 只有基础协作模式
- Agent 无后台监控线程
- 评估体系不完整
- 基准测试用例不足
- 评估工具链只支持现有固定工作流模式
- 无质量门禁
- ReAct + CoT 未深度集成

**结束状态**
- [x] Hierarchical 模式（层次协作）可工作
- [x] Agent 有后台监控线程
- [x] P0-P3 所有指标实现
- [x] 10 个基准测试用例完成（Simple: 4, Medium: 4, Complex: 2）
- [ ] 评估工具链适配多 Agent 协作新模式
- [ ] 质量门禁可工作
- [x] ReAct + CoT 深度集成，所有 Agent 都使用 ReAct + CoT

**交付 Checklist**
- [x] Hierarchical 模式可工作
- [x] Agent 有后台监控线程 (已启动并实现核心方法)
- [x] P0-P3 所有指标实现
- [x] 设计并开发 10 个基准测试用例（Simple: 4, Medium: 4, Complex: 2）
- [x] 评估工具链适配多 Agent 协作新模式：
  - [x] 通过 orchestrator_workflow.py 间接适配消息总线和动态协作
  - [x] 新增协作过程指标收集（IDS、Role Specialization 等）
  - [x] 新增评估 CLI 支持多 Agent 模式
  - [x] 质量门禁已实现 (eval/gate.py)
- [x] 质量门禁可工作 (eval/gate.py + CLI 集成)
- [x] ReAct + CoT 深度集成

**验收 Checklist**
- [x] 所有协作模式都可以工作
- [x] 评估体系完整运行 (6 维度指标 + LLM 辅助 + 质量门禁)
- [x] Complex 任务成功率 &gt; 80%
- [x] 质量门禁可以卡住低质量运行 (eval/gate.py 已实现)
- [x] 评估工具链可以正确收集多 Agent 协作指标
- [x] 所有 Agent 都使用 ReAct + CoT

---

### Stage 4: 生产就绪（生产版）

**目标**
- 可观测性（分布式追踪、日志聚合）
- 性能优化（缓存、并行）
- 成本控制（LLM 预算）
- 完整的文档（架构、API、使用指南）
- 演练和故障排查手册
- **ReAct + CoT 生产化优化**

**开始状态**
- 无分布式追踪
- 无完整的日志聚合
- 无性能优化
- 无成本控制
- 文档不完善
- ReAct + CoT 未生产化优化

**结束状态**
- [x] 分布式追踪（Trace）可用
- [x] 完整的日志聚合可用
- [x] 性能优化（缓存、并行）完成
- [x] 成本控制（LLM 预算）完成
- [x] 完整的文档（架构、API、使用指南）
- [x] 演练和故障排查手册完成
- [x] ReAct + CoT 生产化优化完成

**交付 Checklist**
- [x] 分布式追踪（Trace）
- [x] 完整的日志聚合
- [x] 性能优化（缓存、并行）
- [x] 成本控制（LLM 预算）
- [x] 核心文档（架构、ROADMAP、快速开始）
- [x] ReAct + CoT 生产化优化

**验收 Checklist**
- [x] 生产环境可部署
- [x] 有完整的监控和告警
- [x] 文档完善
- [x] P95 延迟 &lt; 15s
- [x] 每任务成本 &lt; $0.5
- [x] ReAct + CoT 在生产环境稳定运行

---

### 评估体系（借鉴最新基准）

#### P0 指标（核心业务指标）

| 指标 | 来源 | 说明 | 目标阈值 |
|------|------|------|----------|
| Task Success Rate | GAIA | 任务最终成功率 | &gt; 85% |
| Pass@1 | SWE-bench | 一次尝试通过率 | &gt; 70% |
| Tool Selection Accuracy | GAIA | 选择正确工具的比例 | &gt; 90% |
| Plan-Execution Alignment | PlanBench | 计划和执行的一致性 | &gt; 80% |

#### P1 指标（协作质量指标）

| 指标 | 来源 | 说明 | 目标阈值 |
|------|------|------|----------|
| Collaboration Efficiency | MultiAgentBench | 协作效率（交互次数少=好） | &lt; 10 轮 |
| Information Diversity Score (IDS) | MultiAgentBench | 信息多样性 | &gt; 0.4 |
| Role Specialization | Industry | 角色专业化程度 | &gt; 0.8 |
| Conflict Resolution Rate | Industry | 冲突解决率 | 100% |

#### P2 指标（系统性能指标）

| 指标 | 来源 | 说明 | 目标阈值 |
|------|------|------|----------|
| Latency P95 | Industry | P95 延迟 | &lt; 15s |
| Cost per Task | Industry | 每任务成本 | &lt; $0.5 |
| Tool Call Success Rate | Industry | 工具调用成功率 | &gt; 98% |
| Error Recovery Rate | Industry | 错误恢复率 | &gt; 90% |

#### P3 指标（可解释性指标）

| 指标 | 来源 | 说明 | 目标阈值 |
|------|------|------|----------|
| Evidence Coverage | 项目现有 | 证据覆盖率 | &gt; 95% |
| Step Reason Coverage | 项目现有 | 步骤理由覆盖率 | &gt; 95% |
| Hallucination Score | Industry | 幻觉检测分 | &gt; 0.8 |
| Factuality Score | GAIA | 事实准确性 | &gt; 0.9 |

---

### 基准测试用例设计

借鉴 GAIA 和 SWE-bench，设计 3 类测试用例，总共 10 个：

| 类别 | 难度 | 数量 | 说明 |
|------|------|------|------|
| Simple Tasks | 简单 | 4 | 单工具、单 Agent 可以完成 |
| Medium Tasks | 中等 | 4 | 需要多个工具、多个 Agent 协作 |
| Complex Tasks | 复杂 | 2 | 需要多轮对话、冲突解决、动态调整 |

#### Simple Tasks（4 个）
1. 查询 desk 'Equities' 当前头寸
2. 计算 desk 'Rates' 的 delta 敞口
3. 查询最近 7 天的告警历史
4. 检索与当前 desk 相关的历史知识

#### Medium Tasks（4 个）
1. desk 'Equities' 的 delta 疑似 breach，请分析并生成报告
2. 对比 desk 'Equities' 和 'Credit' 的风险敞口
3. 发现异常告警，请查询历史数据并给出建议
4. 需要同时查询头寸和市场数据来评估风险

#### Complex Tasks（2 个）
1. desk 'Equities' 的 delta 持续 breach，需要深度分析原因，Agent 之间需要多轮对话和迭代优化
2. 发现多个 desk 都有异常，需要 Agent 之间协作排查系统问题，可能需要中断和重新规划

---

### 预期收益

- 任务成功率：从 70% → 85%+（借鉴 GAIA 的成果）
- 协作效率：IDS 从 0.05 → 0.4+
- 可扩展性：新 Agent 可以快速加入
- 可维护性：架构清晰，职责分离
