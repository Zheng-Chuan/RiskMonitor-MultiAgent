# 开发计划 (Advanced Real-time Multi-Agent)

本项目旨在构建一个**金融级、实时、知识增强的 Multi-Agent 风控系统**。
对标 Datadog/PagerDuty 的高级智能监控架构，集成 CDC、流计算、RAG 和多智能体编排。

## 技术架构亮点与必须落地清单 (工程作品集标准)

说明

- 这些是必须落地的技术点, 用 checklist 方式确保可衡量 可测试 可验证
- Week 内容只是实现路径, 但无论如何这些能力最终都要落地

### A. 事件驱动架构 (必须实现)

- [x] CDC 数据动脉: MySQL -> Debezium -> Kafka topic
- [ ] 标准事件 Envelope (企业对齐)
  - [ ] schema_version + event_id + correlation_id + causation_id + occurred_at + producer
  - [ ] Schema Registry 与兼容策略 (breaking change 流程)
- [ ] 事件分级与性质分类
  - [ ] severity (INFO/WARNING/CRITICAL) 与 category (system/business)
  - [ ] actionability (是否可执行) 与 confidence (置信度)
  - [ ] 每类事件的默认处理策略 (拦截/降级/升级/人工审批)
- [ ] 幂等与去重
  - [ ] 基于 event_id 或 partition+offset 的去重表
  - [ ] 同一事件重放不重复写库/不重复推送
- [ ] 重试与 DLQ
  - [ ] 可配置重试次数与退避
  - [ ] 不可恢复错误进入 DLQ 并可追溯
- [ ] 可回放 Replay
  - [ ] 选定 event_id 可重放并产出一致的结构化输出 (允许文本不同)

### B. Multi-Agent 协作 (必须实现)

- [x] 三角色拆分
  - [x] System Engineer Agent: 专注 IT 报错与抖动分析
  - [x] Risk Analyst Agent: 专注业务风险分析与事实报告
  - [x] Manager Agent: 汇总信息, 向人类汇报, 下发可执行指令并等待结果
- [ ] Manager 指令协议 (可执行且可验证)
  - [ ] 指令 schema: target_agent + action + params + timeout + expected_output_schema
  - [ ] 执行回执 schema: ok + evidence + artifacts + latency_ms + error
- [ ] 状态机编排 (LangGraph)
  - [ ] Quality Gate + RewriteLoop + Human-in-the-loop
  - [ ] 可回放与幂等内置在编排层

### C. Agent 上下文共享机制 (必须实现)

- [x] RAG 知识库 (Chroma)
- [ ] Context Store (共享上下文)
  - [ ] 黑板模型: event snapshot + tool results + rag hits + decisions + approvals
  - [ ] 结构化引用 evidence (每条结论必须能追溯到 tool/rag/事件字段)
- [ ] 预算与策略
  - [ ] token 预算与截断策略
  - [ ] 缓存策略 (相同事件/相同检索 query 的缓存与失效)
  - [ ] Prompt/Policy 版本化 (可回放)
    - [ ] 每次 Agent run 记录 prompt_version, model, temperature, tool_versions

### D. 工程化质量门禁 (必须实现)

- [ ] Contract Tests (结构化输出质量)
  - [ ] JSON 可解析率, 字段齐全率, 类型正确率
  - [ ] evidence 非空率 (关键结论必须有来源)
- [ ] 离线评测与回归集
  - [ ] 固定回归集 events + 期望结构化输出 (base vs new 版本一键对比)
  - [ ] LLM-as-judge 或规则评分作为质量闸门
  - [ ] 防幻觉与引用治理
    - [ ] 关键结论必须引用 tool 或 rag evidence, 否则降级或拒答

### E. 安全与权限治理 (必须实现)

- [ ] Role-based 工具权限
  - [ ] System Engineer 只允许读取与诊断类工具
  - [ ] Risk Analyst 允许读取业务数据与检索
  - [ ] Manager 才能发起写库/推送, 且 CRITICAL 必须 HITL
- [ ] 审计与追责
  - [ ] 每次写库/推送都有 correlation_id 且可追溯到 event_id 与审批记录

### F. 可观测性与生产化 (必须实现)

- [ ] 端到端指标: CDC lag, consumer lag, pipeline latency (分节点), LLM error rate, Chroma latency
- [ ] 可视化运维界面 (后期)
  - [ ] 事件流 + Agent runs 全链路轨迹
  - [ ] Human-in-the-loop 审批与审计
  - [ ] Replay 重放入口

## 核心架构愿景 (The Advanced Stack)

1. **Level 1: The Nerves (感知层)**
   - **Event Ingestion**: Debezium + Kafka 实时捕获变更
   - **Contracts**: 事件 envelope + schema registry + 兼容策略
2. **Level 2: The Reflexes (快速反射层)**
   - **Sentinel**: 轻量过滤与阈值检测, 把噪音挡在 LLM 外
   - **Deterministic Guardrails**: 技术故障拦截, 幂等, 降级, 重试
3. **Level 3: The Brain (大脑层)**
   - **Memory (RAG)**: Chroma 存储历史告警与知识
   - **Orchestration**: LangGraph 编排多智能体协作与人机协作
   - **Action**: MCP Server 提供原子化操作工具 (读写分离, HITL 约束)

---

## 历史里程碑 (已完成)

### Week 1(Phase 0): 监控链路 MVP(vertical slice)

- 交付
  - [x] 业务用例固化
    - [x] 定义口径与 contract
      - [x] positions schema, market snapshot schema, risk limits schema
      - [x] output schema: exposure, breaches, alerts, citations(如果有)
    - [x] 实现 1 个用例级入口(可被 MCP 与 HTTP 复用)
      - [x] 示例: monitor_desk_exposure(desk, as_of, horizon, limit_profile)
  - [x] 实时性与可观测性底座(最小版)
    - [x] 数据访问层: 超时, 重试, 资源释放, 明确事务边界
    - [x] 结构化日志: request_id, tool name, latency_ms, error.code
    - [x] 指标: 至少输出 2 个核心指标(例如 qps, p95 latency)的最小实现方式
  - [x] demo 与回归入口
    - [x] 1 条 demo 脚本: 从查询头寸 -> 聚合 exposure -> 限额判断 -> 输出告警 payload
    - [x] 1 条端到端 smoke test 覆盖该链路

- 验收
  - [x] 端到端 demo 可复现
    - [x] 本地一键启动数据库与 server
    - [x] MCP 客户端可调用至少 2 个工具
    - [x] demo 脚本输出包含:
      - [x] exposure(按 desk 聚合)
      - [x] breaches(超限判断)
      - [x] request_id 与可定位日志
  - [x] 工程化底线满足
    - [x] 无明文 secrets
    - [x] 核心链路具备超时与结构化错误返回
    - [x] tests 可运行且通过

### Week 2(Phase 0): 工程化强化与性能

- 交付
  - [x] 模块化重构
    - [x] 拆分 main.py 为模块(接口层, service 层, 计算层, 数据访问层, 配置层)
    - [x] 统一输入输出 schema 与错误结构
  - [x] 数据访问层工业化
    - [x] SQLAlchemy Engine 连接池与超时
    - [x] 重试策略(下沉到 data_access)
    - [x] 错误映射
    - [x] 读写分离预留点或 cache 抽象(先不实现也可)
  - [x] 性能与容量口径
    - [x] 固化压测用例(固定请求集)
    - [x] 定义并输出 p50, p95 latency 的目标与测量方法

- 验收
  - [x] p95 latency 在固定用例下达到目标(目标: 500ms 以内, 方法: scripts/benchmarks/bench_monitor_desk_exposure.py --p95-target-ms 500)
  - [x] 关键模块可单测, 用例级逻辑可集成测试

### Week 3(Phase 1): 服务化形态与 DX 固化

- 交付
  - [x] streamable-http 部署形态固化
    - [x] streamable-http 作为推荐部署方式
    - [x] health check, readiness, graceful shutdown
  - [x] DX 固化
    - [x] 统一启动与测试入口(Makefile 提供 make setup-mcp, make test-all)
    - [x] 明确目录职责(例如 src, scripts, tests)

- 验收
  - [x] 在 streamable-http 模式下可稳定运行并可被客户端连接
  - [x] tests 全部通过

### Week 4(Phase 3 最小版): 可观测与告警闭环

- 交付
  - [x] 告警闭环
    - [x] 告警规则最小集合(desk delta breach, 支持 INFO/WARNING/CRITICAL 三级)
    - [x] 告警路由(写入 alerts 表, 支持按 request_id/alert_id/desk/severity 查询)
  - [x] 可观测与容量口径
    - [x] 指标可观测: /metrics 端点暴露 Prometheus 格式指标(request_count, avg_latency, error_rate)
    - [x] 已有压测脚本(scripts/benchmarks/bench_monitor_desk_exposure.py)

- 验收
  - [x] 告警可端到端触发并可追踪(request_id, alert_id)
  - [x] /metrics 端点可正常访问, 暴露关键指标
  - [x] tests 全部通过(截至目前 36 个测试)

---

## 演进计划 (Week 5-10)

### Week 5: MCP Foundation (坚实底座)
**目标**: 清洗现有架构，确保 MCP Server 无状态、安全且 AI 友好。

- **交付**
  - [x] **架构清洗 (Stateless & Secure)**
    - [x] **删除** `task_registry.py`: 移除内存任务队列，回归无状态。
    - [x] **拆分读写边界**: `monitor_desk_exposure` 保持无副作用, 写入动作由 `submit_alerts` 承担。
    - [x] **Auth**: 实现基于 Token 的 HTTP Header 鉴权桩。
  - [x] **Resources & Prompts**
    - [x] 实现 `risk://metadata/desks` 和 `risk://limits/global` Resources。
    - [x] 内置 `analyze-risk-breach` Prompt 模版。
  - [x] **LLM Provider 适配 (OpenRouter)**
    - [x] 新增独立模块 `riskmonitor_multiagent.llm.openrouter_client` 统一封装 OpenRouter 调用。
    - [x] 从仓库根目录 `.env` 自动读取 `OPENROUTER_API_KEY` 等配置, 默认使用免费模型。
    - [x] 不注册为 MCP 工具, 供后续 server/worker 在业务流程内直接调用。

### Week 6: Infrastructure & CDC (数据动脉)
**目标**: 搭建 Kafka 生态，打通从 DB 到流的实时通道。

- **交付**
  - [x] **容器化基础设施**
    - [x] `docker-compose.yml`: 添加 Zookeeper, Kafka, Kafka UI, Debezium Connect, Schema Registry。
  - [x] **CDC Pipeline**
    - [x] 配置 Debezium Connector 监听 MySQL `positions` 表。
    - [x] 验证 Binlog 变更能实时进入 Kafka Topic `risk.positions.cdc`。
  - [x] **Schema Registry**
    - [x] 定义 CDC 事件 JSON Schema 并提供注册脚本, 供下游 Consumer 类型对齐与演进。

### Week 7: Sentinel & Agent Pipeline (哨兵与智能体流水线)
**目标**: 放弃复杂的流计算框架，使用轻量级 Sentinel 脚本直接连接 Kafka 与 Multi-Agent 系统，实现 "Event -> Agent" 的快速闭环。

- **交付**
  - [x] **Sentinel Service (轻量级哨兵)**
    - [x] 编写 `riskmonitor_multiagent.sentinel.service`，使用 `aiokafka` 监听 `risk.positions.cdc`。
    - [x] 实现基础过滤逻辑：解析 CDC 事件，发现 Exposure > Limit 即触发后续流程。
  - [x] **Agent Roles Implementation (三大角色)**
    - [x] **System Engineer Agent (IT 运维)**: 专门分析 IT 系统报错与抖动，检查数据延迟、字段完整性与依赖可用性，过滤技术故障。
    - [x] **Risk Analyst Agent (风险分析师)**: 专门分析业务风险，基于事件与上下文生成客观事实报告与风险点列表。
    - [x] **Manager Agent (管理者/指挥官)**: 汇总前两者信息进行分析与处理，向人类汇报，并向其他两个 Agent 下发可执行指令并等待执行结果。
  - [x] **Sequential Pipeline (线性编排)**
    - [x] 在 Sentinel 中串联 `SystemEngineer -> RiskAnalyst -> Manager` 的调用链。
  - [x] **Verification**
    - [x] 修改数据库 `positions` 表 -> Kafka 产出事件 -> Sentinel 捕获 -> 触发 Agent -> 输出决策日志。

### Week 8: RAG & Knowledge Base (知识记忆 - 海马体)
**目标**: 让 Agent 拥有记忆，能参考历史案例。

- **交付**
  - [x] **Vector DB 部署**
    - [x] 在 docker compose 中增加 **Chroma** 服务并提供持久化 volume
  - [x] **Knowledge Ingestion**
    - [x] 提供 CLI 将最近 `alerts` 表数据向量化写入 Chroma
    - [ ] (可选) 导入一份 Mock 的 Risk Management Handbook 文档
  - [x] **Context Retrieval Tool**
    - [x] 新增 MCP Tool `search_similar_alerts` 读取 Chroma 并返回相似历史告警
  - [x] **CLI 工具**
    - [x] 提供 `kb ingest-alerts` 与 `kb query` 两个子命令 用于本地验证与排障
 - **验收**
   - [x] 一键复现
     - [x] `docker compose --profile kb up -d` 可启动 Chroma 且重启后数据仍在
     - [x] `make ingest-knowledge` 成功写入向量库 并输出写入条数
   - [x] 检索可用
     - [x] CLI query 能返回 top_k 结果 每条包含 similarity 与 alert_id
     - [x] MCP tool `search_similar_alerts` 返回结构与 CLI 一致
   - [x] 回归覆盖
     - [x] tests 覆盖 ingest 与检索核心逻辑 且 pytest 全量通过

### Week 9: Multi-Agent Orchestration (Advanced)
**目标**: 将线性流程升级为可治理的状态机，支持质量门禁、重写回路、人机协作与可回放。

- **交付**
  - [ ] **Contracts (输入输出契约)**
    - [ ] 定义并固化 `RiskEvent` 事件结构与版本号（event_id, correlation_id, causation_id, occurred_at, producer, schema_version）。
    - [ ] 定义事件分级与性质分类（severity, category/system_or_business, actionability, confidence），并明确每类事件的默认处理策略。
    - [ ] 定义并固化三个 Agent 的结构化输出 schema，并提供校验与兼容策略。
  - [ ] **State Machine (LangGraph)**
    - [ ] 节点建议: NormalizeEvent -> EngineerCheck -> RetrieveContext(tools + Chroma) -> RiskAnalyst -> QualityGate -> RewriteLoop -> Manager -> HumanApproval -> Execute.
    - [ ] Manager 节点支持向 System Engineer 与 Risk Analyst 下发可执行指令并等待执行结果。
  - [ ] **Quality Gate**
    - [ ] 当报告缺字段或置信度过低时触发 rewrite 回路，并限制最大重试次数。
    - [ ] 当 LLM 不可用时自动降级到规则化输出，保证闭环不中断。
  - [ ] **Human-in-the-loop**
    - [ ] 对 CRITICAL 级别动作必须人工确认后才能执行有副作用操作（至少写库/推送）。
 - **验收**
   - [ ] 工作流可运行
     - [ ] 提供 demo 脚本 输入一个 breach event 能跑完整状态机并输出最终决策（结构化 JSON）。
   - [ ] 可回放与幂等
     - [ ] 同一 event_id 重放不会重复写入/重复推送，并且输出结构保持一致。
   - [ ] 回路生效
     - [ ] 当 Risk Analyst 输出缺字段时触发 rewrite 回路，至少重写一次后再进入 Manager。
   - [ ] 人工介入
     - [ ] CRITICAL 动作必须进入 human approval，未确认不得执行写库动作。
   - [ ] 测试覆盖
     - [ ] tests 覆盖 system_issue、rewrite、human approval、fallback 等关键分支，pytest 全量通过。

### Week 10: Production Readiness (生产化)
**目标**: 全链路压测与可观测性。

- **交付**
  - [ ] **End-to-End Stress Test**
    - [ ] 制造“风暴场景”：短时间内大量交易触发多个 Desk 违规。
    - [ ] 验证 Kafka Backpressure 和 Agent 响应延迟。
  - [ ] **Observability Dashboard**
    - [ ] 监控：CDC 延迟, Kafka consumer lag, Sentinel 吞吐, pipeline latency(分节点), LLM 调用成功率与 token 消耗, Chroma query p95 与命中率。
  - [ ] **Documentation**
    - [ ] 完整的架构图、操作手册与故障排查 Runbook。
 - **验收**
   - [ ] 压测可复现
     - [ ] 提供脚本能在本地注入 N 条 positions 变更并触发 Sentinel 与 Agent
     - [ ] 证明在风暴场景下无重复告警（同一 event_id/alert_id 幂等）。
   - [ ] 指标可观测
     - [ ] /metrics 至少新增 CDC lag, consumer lag, pipeline latency, LLM error rate, Chroma latency 指标
   - [ ] 稳定性
     - [ ] 连续运行 30 分钟 无崩溃 无明显内存泄漏 关键错误有结构化日志
   - [ ] 故障演练
     - [ ] LLM 不可用时自动降级仍能产出结构化决策
     - [ ] Chroma 不可用时仍可运行但明确标注 memory 不可用

### Week 11: Enterprise Event-Driven & Ops UI (Backlog)
**目标**: 将模块二升级为主流企业风格的事件驱动架构，并为多智能体提供可视化运维界面。

- **交付**
  - [ ] **Event-Driven Hardening (主流企业方案对齐)**
    - [ ] 标准化事件 envelope（schema_version, event_id, correlation_id, causation_id, producer, occurred_at）。
    - [ ] Topic 规划与命名规范（raw/normalized/alerts/agent_runs 等），并记录到 docs/DATA.md。
    - [ ] 幂等与去重（基于 event_id 或 partition+offset 的持久化去重表），避免重复告警与重复执行。
    - [ ] 重试与死信（DLQ）策略：可配置重试次数与退避，对不可恢复错误落盘/落库。
    - [ ] Schema 演进策略：兼容旧版本 consumer，明确 breaking change 流程。
  - [ ] **Multi-Agent 可视化界面 (Operations Console)**
    - [ ] 展示事件流与处理状态（最新事件、延迟、成功/失败/被拦截原因）。
    - [ ] 展示每次 Agent run 的完整轨迹（输入、检索命中、输出、质量门禁、HITL 状态）。
    - [ ] 支持 Human-in-the-loop 审批（approve/reject）与审计记录。
    - [ ] 支持重放与回滚演练（选定 event_id 进行回放，保证幂等）。
- **验收**
  - [ ] 事件驱动一致性
    - [ ] 端到端链路全部基于事件驱动执行，核心状态可在事件与数据库中回溯。
  - [ ] 控制台可用
    - [ ] 本地启动后可看见近 1 小时的事件与 Agent runs，并可执行一次审批与一次重放。

---

## 架构层次总结

| Layer | Component | Technology | Responsibility |
| :--- | :--- | :--- | :--- |
| **Brain** | **Manager Orchestrator** | LLM, State Machine | 汇总信息, 下发指令, 等待执行, 向人类汇报 |
| **Memory**| **Knowledge Base** | **Chroma**, RAG | 历史经验检索, 规则文档查询 |
| **Reflex**| **Sentinel** | Python, Kafka Consumer | 轻量过滤与阈值检测, 触发智能体 |
| **Nerves**| **Event Bus** | **Kafka**, Debezium | 实时数据捕获与传输 |
| **Hands** | **MCP Server** | **FastMCP** | 数据库读写, 原子工具暴露 |
