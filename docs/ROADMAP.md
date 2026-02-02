# 开发计划 (Advanced Real-time Multi-Agent)

本项目旨在构建一个**金融级、实时、知识增强的 Multi-Agent 风控系统**。
对标 Datadog/PagerDuty 的高级智能监控架构，集成 CDC、流计算、RAG 和多智能体编排。

## 核心架构愿景 (The Advanced Stack)

1.  **Level 1: The Nerves (感知层)**
    *   **CDC**: Debezium + Kafka，实时捕获每一笔交易。
    *   **Resource**: MCP Server 暴露静态元数据 (Limits, Desks)。
2.  **Level 2: The Reflexes (脊髓层 - 实时聚合)**
    *   **Stream Processing**: 使用 **Faust** (Python Streaming) 进行时间窗口聚合 (Time-Window Aggregation)。
    *   **Signal Detection**: 过滤 99% 的噪音，只将“高价值信号” (High-Value Signals) 传递给 Agent。
3.  **Level 3: The Brain (大脑层 - 决策分发)**
    *   **Memory (RAG)**: **Milvus** (Vector DB) 存储历史案例、操作手册、市场新闻。
    *   **Orchestration**: **LangGraph** 编排多智能体协作 (Sentinel -> Analyst -> Manager)。
    *   **Action**: MCP Server 提供原子化操作工具 (Submit Alert, Update Limit)。

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
    - [x] **System Engineer Agent (IT 运维)**: 第一道防线，检查数据延迟与事件字段完整性，过滤明显技术故障。
    - [x] **Junior Analyst Agent (初级分析师)**: 第二道防线，基于事件生成事实报告，后续可补充调用 `monitor_desk_exposure` 拉取详情。
    - [x] **Risk Manager Agent (风险经理)**: 最终决策者，基于分析报告给出处置建议 (Watch/Critical)。
  - [x] **Sequential Pipeline (线性编排)**
    - [x] 在 Sentinel 中串联 `Engineer -> Analyst -> Manager` 的调用链。
  - [x] **Verification**
    - [x] 修改数据库 `positions` 表 -> Kafka 产出事件 -> Sentinel 捕获 -> 触发 Agent -> 输出决策日志。

### Week 8: RAG & Knowledge Base (知识记忆 - 海马体)
**目标**: 让 Agent 拥有记忆，能参考历史案例。

- **交付**
  - [x] **Vector Store 部署**
    - [x] 使用本地 SQLite 文件实现轻量向量存储 默认路径 data/knowledge.sqlite
  - [x] **Knowledge Ingestion**
    - [x] 提供脚本 将最近 `alerts` 表数据向量化存入知识库
    - [ ] (可选) 导入一份 Mock 的 Risk Management Handbook 文档
  - [x] **Context Retrieval Tool**
    - [x] 新增 MCP Tool `search_similar_alerts` 给定查询文本 返回相似历史告警
 - **验收**
   - [x] 一键复现
     - [x] 本地启动 MySQL 与 infra 后 运行 ingest 脚本能生成知识库文件
   - [x] 检索可用
     - [x] MCP tool `search_similar_alerts` 可返回 top_k 结果 每条包含 similarity 与 alert_id
   - [x] 回归覆盖
     - [x] tests 覆盖 ingest 与检索核心逻辑 且 pytest 全量通过

### Week 9: Multi-Agent Orchestration (Advanced)
**目标**: 将线性流程升级为 LangGraph 状态机，处理更复杂的交互（如 Manager 驳回分析报告）。

- **交付**
  - [ ] **LangGraph Workflow**
    - [ ] 迁移 Pipeline 逻辑到 LangGraph Graph。
    - [ ] 增加 "Human-in-the-loop" 节点。
    - [ ] 增加 "Rewrite" 回路（当分析报告质量不达标时）。
 - **验收**
   - [ ] 工作流可运行
     - [ ] 提供 demo 脚本 输入一个 breach event 能跑完整状态机并输出最终决策
   - [ ] 人工介入
     - [ ] 高风险动作必须进入 human in loop 节点 未确认不得执行写库动作
   - [ ] 回路生效
     - [ ] 当分析报告缺字段时触发 rewrite 回路 至少重写一次后再进入 manager
   - [ ] 测试覆盖
     - [ ] tests 覆盖状态机关键分支 且 pytest 全量通过

### Week 10: Production Readiness (生产化)
**目标**: 全链路压测与可观测性。

- **交付**
  - [ ] **End-to-End Stress Test**
    - [ ] 制造“风暴场景”：短时间内大量交易触发多个 Desk 违规。
    - [ ] 验证 Kafka Backpressure 和 Agent 响应延迟。
  - [ ] **Observability Dashboard**
    - [ ] 监控：CDC 延迟, Flink/Faust 吞吐, Agent Token 消耗, RAG 检索命中率。
  - [ ] **Documentation**
    - [ ] 完整的架构图与操作手册。
 - **验收**
   - [ ] 压测可复现
     - [ ] 提供脚本能在本地注入 N 条 positions 变更并触发 Sentinel 与 Agent
   - [ ] 指标可观测
     - [ ] /metrics 至少新增 CDC lag 与 pipeline latency 指标
   - [ ] 稳定性
     - [ ] 连续运行 30 分钟 无崩溃 无明显内存泄漏 关键错误有结构化日志

---

## 架构层次总结

| Layer | Component | Technology | Responsibility |
| :--- | :--- | :--- | :--- |
| **Brain** | **Multi-Agent Pipeline** | LLM, Pipeline | 三角色协作, 生成报告与决策 |
| **Memory**| **Knowledge Base** | **Milvus**, RAG | 历史经验检索, 规则文档查询 |
| **Reflex**| **Sentinel** | Python, Kafka Consumer | 轻量过滤与阈值检测, 触发智能体 |
| **Nerves**| **Event Bus** | **Kafka**, Debezium | 实时数据捕获与传输 |
| **Hands** | **MCP Server** | **FastMCP** | 数据库读写, 原子工具暴露 |
