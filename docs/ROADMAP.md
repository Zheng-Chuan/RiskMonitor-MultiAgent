# ROADMAP (RiskMonitor-MultiAgent)

本项目是一个面向金融风控演示的 Multi-Agent 系统, 目标是用可治理的方式把“意图识别 → 多步规划 → 工具执行 → 证据链输出 → 可回放与成本治理”落到工程代码里.

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

- Phase 0: MVP 风控链路与服务化 (Week 01-05)
- Phase 1: 知识与记忆 (Week 08, 19)
- Phase 2: 权限与副作用闭环 (Week 11-13, 12)
- Phase 3: 编排与治理平台 (Week 14, 18, 20-21)
- Phase 4: 契约与质量闸门(最小版) (Week 15)
- Phase 5: 量化评测与CLI回归 (Week 22-23)

说明: Week 编号保留历史顺序, 但只保留“仓库中确实存在的能力与验收”.

---

## Phase 0: MVP 风控链路与服务化

### Week 01: 监控链路 MVP (vertical slice)

**目标**
- 形成一个端到端可复现的“查询头寸 → 聚合敞口 → 违规判断 → 生成告警记录(不落库)”链路.

**输入**
- MCP 工具调用参数: `desk`, `as_of`, `market_snapshot_url` 或 `market_snapshot`, `abs_delta_limit`
- 数据依赖: MySQL `positions` 表

**输出**
- `monitor_desk_exposure` 结构化结果: `exposure`, `breaches`, `alerts`, `request_id`, `latency_ms`

**交付 Checklist**
- [x] MCP Server 基本可用并注册核心工具
- [x] 头寸查询与风险聚合计算可运行
- [x] 结构化输出包含 request_id 与关键字段
- [x] 端到端 smoke test 覆盖主链路

**验收 Checklist**
- [x] MCP client 可通过 stdio 调用至少 2 个工具
- [x] smoke test 可复现并通过

---

### Week 02: 数据访问与工程化底座

**目标**
- 将数据库访问工程化: 连接池/超时/错误封装, 避免业务层直接依赖裸连接.

**输入**
- MySQL 连接配置: `MYSQL_*` 环境变量

**输出**
- 可复用的数据访问模块与健康检查

**交付 Checklist**
- [x] SQLAlchemy Engine 封装与连接池配置
- [x] MySQL 健康检查
- [x] 配置集中管理与 `.env` 加载

**验收 Checklist**
- [x] 集成测试可连接 MySQL 并查询 positions

---

### Week 03: 服务化形态与 DX

**目标**
- 固化可运行的服务端形态, 提供 health/ready/metrics, 支持本地与容器运行.

**输入**
- HTTP Header 鉴权 Token

**输出**
- `/health`, `/ready`, `/metrics` 端点

**交付 Checklist**
- [x] health 与 readiness
- [x] Prometheus metrics 输出
- [x] 优雅退出(ready 先切 not_ready)

**验收 Checklist**
- [x] 未授权访问 `/metrics` 与 `/ready` 会被拒绝

---

### Week 04: 告警规则(最小闭环)

**目标**
- 在不引入复杂事件总线的前提下, 形成“规则评估 → 生成告警记录 →(可选)写库”的闭环.

**输入**
- 风险计算结果(例如 abs_delta 与阈值)

**输出**
- 告警结构: severity/desk/message/created_at 等

**交付 Checklist**
- [x] 告警规则引擎(最小集合)
- [x] 告警输出格式化

**验收 Checklist**
- [x] `monitor_desk_exposure` 输出的 alerts 结构稳定

---

### Week 05: MCP Foundation (无状态 + AI 友好)

**目标**
- MCP Server 无状态, 工具语义清晰, 读写边界明确.

**输入**
- MCP tool params, HTTP headers

**输出**
- 读工具与写工具边界清晰, 鉴权/错误结构统一

**交付 Checklist**
- [x] 读写边界: `monitor_desk_exposure` 无副作用, 写库由 `submit_alerts` 承担
- [x] Token 鉴权
- [x] Resources/Prompts 注册

**验收 Checklist**
- [x] 未授权调用在服务端返回结构化错误

---

## Phase 1: 知识与记忆

### Week 08: Knowledge Base (Chroma)

**目标**
- 支持把历史告警/知识写入向量库并检索相似告警.

**输入**
- Chroma 配置: `CHROMA_PERSIST_DIR` 或 `CHROMA_HOST/CHROMA_PORT`

**输出**
- `ChromaVectorStore` 的 upsert/query 能力

**交付 Checklist**
- [x] Chroma store 封装, 支持 persistent 与 http client
- [x] 相似告警检索工具路径可用

**验收 Checklist**
- [x] integration 测试可完成 upsert+query

---

### Week 19: Unified Memory System (统一记忆)

**目标**
- 统一记忆协议, 短期记忆与长期记忆分层治理.
- 短期记忆拆分为单 Agent 独有与多 Agent 共享, 全部使用 Redis.
- 长期记忆使用 MongoDB, 仅存储“任务完成后的 run 总结”, 由 Critic 产出并以 run_id 为键.

**输入**
- Redis: `REDIS_URL`, `WORKING_MEMORY_TTL_S`, `WORKING_MEMORY_MAX_LEN`
- MongoDB: `MONGO_URL`, `MONGO_DB`, `MONGO_RUN_SUMMARY_COLLECTION`
- Chroma: `CHROMA_PERSIST_DIR`

**输出**
- 短期: `MemoryEntry` 协议, 支持 scope=`private|shared`
- 长期: `run_summary` 文档(以 run_id 为键), 存储 Critic 的总结与证据引用

**交付 Checklist**
- [x] MemoryEntry normalize/validate
- [x] Redis 短期记忆支持两种 scope
- [x] Critic 在任务结束后产出 run_summary 并落 Mongo
- [x] 短期与长期接口解耦, 避免把所有过程数据写入长期库

**验收 Checklist**
- [x] 单测覆盖 private/shared 短期记忆写入与读取
- [x] 单测覆盖 run_summary 落 Mongo(可使用 mock client)

---

## Phase 2: 权限与副作用闭环

### Week 11: RBAC (基础版)

**目标**
- 对工具执行引入最小 RBAC, 禁止跨角色调用, side_effect 必须审批.

**输入**
- AgentCommand: `target_agent`, `action`, `params`, `approval`

**输出**
- AgentReceipt: ok/error/evidence

**交付 Checklist**
- [x] 工具 registry 元信息(capability/risk/owner/side_effect_policy)
- [x] command 校验与拒绝原因结构化输出

**验收 Checklist**
- [x] system_engineer 调用 side_effect 动作会被拒绝
- [x] privileged 角色(代码里仍沿用 manager 命名) 执行 side_effect 必须审批

---

### Week 12: Side-effect 工具与审计闭环

**目标**
- 将“有副作用的动作”纳入策略与审计, 默认要求审批并可追责.

**输入**
- side_effect 工具调用参数 + approval

**输出**
- 写库动作的可控执行与审计落点

**交付 Checklist**
- [x] side_effect policy: require_approval/require_reason/min_severity
- [x] 拒绝原因与证据结构化写入 receipt

**验收 Checklist**
- [x] 未审批的 side_effect 调用返回 `approval_required`

---

### Week 13: RBAC (治理增强)

**目标**
- 防止“同为 read_only 但跨域滥用”的情况, 把 allowed_targets/owner 作为约束.

**输入**
- AgentCommand

**输出**
- 更细粒度的 deny reason

**交付 Checklist**
- [x] cross-role 调用 read_only 工具被拒绝
- [x] deny reason 区分 role_not_allowed/rbac_denied

**验收 Checklist**
- [x] 单测覆盖跨角色 deny

---

## Phase 3: 编排与治理平台

### Week 14: Policy/Prompt 版本化与可回放(最小版)

**目标**
- 输出携带 prompt_version/policy_version, 便于策略迭代对比.
- 为后续 A/B 评测建立可追溯的版本维度, 支持按 run 对齐指标与证据链.

**输入**
- `POLICY_VERSION` 与各 agent prompt version 常量

**输出**
- AgentResult.meta 中包含版本字段, 可追溯
- 对比实验最小维度: prompt_version, policy_version, model, governance 开关

**交付 Checklist**
- [x] BaseAgent 返回 meta 包含 prompt_version/policy_version

**验收 Checklist**
- [x] 单测/回放产物可定位版本差异
- [x] 回放产物可按版本维度聚合为实验分组

---

### Week 18: Orchestrator & Critic (The New Brain)

**目标**
- 用 Orchestrator + Critic 双核完成动态规划与风险制衡.

**输入**
- task: `task_id/session_id/source/payload.content`

**输出**
- `orchestrator_run.v1`: plan/review/approval/specialists/final

**交付 Checklist**
- [x] Orchestrator 生成 plan_steps
- [x] Critic 审查 plan 并可触发 HITL
- [x] Context Store 记录 run 轨迹

**验收 Checklist**
- [x] `HITL_AUTO_APPROVE=0` 时可在 plan 阶段被阻断

---

### Week 20: LLM Cost Governance

**目标**
- 为 LLM 调用提供 token bucket 限流与按 user/agent 的成本统计.

**输入**
- `LLM_RATE_LIMIT_*` 环境变量, `RM_USER_ID`

**输出**
- meta.governance 字段与 token/call 指标
- 成本与可用性对比的基础指标: rate_limited, degraded, blocked

**交付 Checklist**
- [x] 限流启用时回退到 fallback
- [x] 记录 tokens/calls 指标(含 user/priority)

**验收 Checklist**
- [x] 单测覆盖 rate limit 与成本核算
- [x] 支持在同一基准集上比较不同 budget 配置的质量与成本

---

### Week 21: Intent Router & Flexible Planning

**目标**
- 意图识别仅保留 Schema-first Intent Extractor, 输入为用户输入 + 基础元数据.
- Intent Extractor 支持多意图输出, 并包含多意图之间的解释与取舍建议, 写入共享短期记忆.
- 多步规划采用 Planner-Executor 动态循环, 支持 plan-revise 与 mid-flight replan.
- 修复多步规划常见工程缺口: 执行器只跑 delegate, commands->receipts 未闭环, HITL 只在 plan 阶段, 证据链不一致.

**输入**
- task.payload.content

**输出**
- `intent_output.v2`(支持 intents + disambiguation) + `orchestrator_run.v1` 扩展字段: `intent`, `artifacts`, `receipts`

**交付 Checklist**
- [x] 删除 Router 角色与相关产物字段
- [x] Intent Extractor 输出 strict JSON, 支持多意图与解释, 并写入 shared 短期记忆
- [x] Executor 支持 plan_steps 多种 kind(tool_call/ask_human/stop/finalize) 且不会静默忽略
- [x] commands->receipts 接入主闭环: 执行 commands 生成 receipts 并回灌 Planner/Critic
- [x] HITL 细粒度: step/command 触发审批并可中断返回 pending_approval
- [x] 证据链一致: plan/review/analysis/final 必须引用 receipts 或输入字段, 不满足则降级或阻断
- [x] 可解释性闭环: 每个 plan_step 需要 reason, 每个执行结果需要可验证 evidence

**验收 Checklist**
- [x] 多意图输出可复现, disambiguation 写入 shared 短期记忆
- [x] 至少 1 个 case 生成 commands 并执行产生 receipts, Critic.review 能看到 receipts
- [x] 运行产物可逐步回答 why this step 和 what evidence proves result
- [x] `pytest -q -W error` 全量通过

---

## Phase 5: 量化评测与CLI回归

### Week 22: Explainability Metrics & Benchmark

**目标**
- 将业务成功定义固化为可量化指标: agent 规划与执行结果都有据可依, 全流程可解释可验证.
- 建立统一基准集与 A/B 对比协议, 支持版本和治理策略对比.

**输入**
- 基准任务集: `eval/benchmarks/explainability_cases.jsonl`
- 运行配置: prompt_version, policy_version, model, `HITL_AUTO_APPROVE`, `LLM_RATE_LIMIT_*`

**输出**
- 每次评测输出 `eval/results/<run_tag>.jsonl` 和汇总 `eval/results/<run_tag>.summary.json`
- 指标分层: latency, cost, governance, explainability, business_consistency

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

### Week 23: Evaluation CLI & Quality Gate

**目标**
- 提供可一键运行的评测 CLI 与质量闸门, 将对比实验纳入日常回归.

**输入**
- `eval/benchmarks/*.jsonl`
- CLI 参数: `--model`, `--policy-version`, `--prompt-version`, `--hitl`, `--budget-profile`, `--run-tag`

**输出**
- CLI 命令:
  - `python -m scripts.eval.run_benchmark`
  - `python -m scripts.eval.compare_runs --base <tag> --cand <tag>`
  - `python -m scripts.eval.quality_gate --run <tag>`
- 质量闸门结果: pass/fail 和失败原因列表

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

## Phase 4: 契约与质量闸门(最小版)

### Week 15: Contracts & Quality Gate (Minimal)

**目标**
- 对关键结构化输出进行契约校验, 防止字段漂移与证据链缺失.
- 将协作流程可解释性纳入质量定义, 重点约束 reason 与 evidence 的一致性.

**输入**
- Agent 输出: orchestrator_output/critic_review/system_engineer_output/risk_analyst_output

**输出**
- validate errors 列表, 以及 degraded 降级策略

**交付 Checklist**
- [x] 关键输出有 normalize/validate
- [x] evidence 至少包含 fields/receipt_command_ids/rag_hit_ids 之一
- [x] 增加 step_reason 与 receipt 绑定校验规则
- [x] 增加 evidence 关联字段完整性统计输出

**验收 Checklist**
- [x] 单测覆盖 contracts 最小校验
- [x] 新增负例用例: reason 缺失, evidence 引用缺失, receipts 不一致
