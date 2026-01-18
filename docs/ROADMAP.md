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
  - [x] tests 全部通过(27 个测试, 包含 5 个告警测试)

---

## 演进计划 (Week 5-10)

### Week 5: MCP Foundation (坚实底座)
**目标**: 清洗现有架构，确保 MCP Server 无状态、安全且 AI 友好。

- **交付**
  - [ ] **架构清洗 (Stateless & Secure)**
    - [ ] **删除** `task_registry.py`: 移除内存任务队列，回归无状态。
    - [ ] **重构** `monitor_desk_exposure`: 拆分为 `calculate` (读) 和 `submit` (写)。
    - [ ] **Auth**: 实现基于 Token 的 HTTP Header 鉴权桩。
  - [ ] **Resources & Prompts**
    - [ ] 实现 `risk://metadata/desks` 和 `risk://limits/global` Resources。
    - [ ] 内置 `analyze-risk-breach` Prompt 模版。

### Week 6: Infrastructure & CDC (数据动脉)
**目标**: 搭建 Kafka 生态，打通从 DB 到流的实时通道。

- **交付**
  - [ ] **容器化基础设施**
    - [ ] `docker-compose.yml`: 添加 Zookeeper, Kafka, Kafka UI, Debezium Connect。
  - [ ] **CDC Pipeline**
    - [ ] 配置 Debezium Connector 监听 MySQL `positions` 表。
    - [ ] 验证 Binlog 变更能实时进入 Kafka Topic `risk.positions.cdc`。
  - [ ] **Schema Registry**
    - [ ] 定义并固化 CDC 事件的 JSON Schema，确保下游 Consumer 类型安全。

### Week 7: Stream Processing (实时聚合 - 脊髓)
**目标**: 构建“脊髓”反射层，处理高频数据，生成聚合信号。

- **交付**
  - [ ] **Faust Streaming Application**
    - [ ] 搭建 `risk-stream-processor` 服务 (Python Faust)。
    - [ ] 定义 `Table` (KV Store) 用于存储窗口内的聚合状态 (如 Desk Delta)。
  - [ ] **Sliding Window Aggregation**
    - [ ] 实现 "1分钟滑动窗口"，实时计算 `Desk Delta` 的变化率 (Velocity)。
    - [ ] 实现 "Breach Detector": 当聚合值超过阈值，立即向下游 Topic `risk.signals.breach` 发送信号。
- **验收**
  - [ ] 模拟每秒 100 笔交易注入，系统能实时输出聚合后的 Risk Metrics，而不是单笔流水。

### Week 8: RAG & Knowledge Base (知识记忆 - 海马体)
**目标**: 让 Agent 拥有记忆，能参考历史案例。

- **交付**
  - [ ] **Vector DB 部署**
    - [ ] 部署 **Milvus** (或 Chroma) 向量数据库。
  - [ ] **Knowledge Ingestion**
    - [ ] 编写脚本，将历史 `alerts` 表数据向量化存入 Milvus。
    - [ ] (可选) 导入一份 Mock 的 "Risk Management Handbook" 文档。
  - [ ] **Context Retrieval Tool**
    - [ ] 新增 MCP Tool `search_similar_alerts(embedding)`: 给定当前情况，查找最相似的历史告警及处理结果。

### Week 9: Multi-Agent Orchestration (多智能体编排 - 大脑)
**目标**: 使用 LangGraph 组装 Sentinel, Analyst, Manager 三大角色。

- **交付**
  - [ ] **Agent 角色定义**
    - [ ] **Sentinel (哨兵)**: 监听 `risk.signals.breach` Topic，组装初始上下文，唤醒 Analyst。
    - [ ] **Analyst (分析师)**: 
        - 调用 `search_similar_alerts` (RAG) 获取历史参考。
        - 调用 `calculate_exposure` (MCP) 复核数据。
        - 生成分析报告 (Root Cause Analysis)。
    - [ ] **Risk Manager (决策者)**: 
        - 评估报告，给出操作建议 (Call Margin / Liquidate)。
        - **Human-in-the-loop**: 对于高风险操作，挂起工作流等待 API 确认。
  - [ ] **LangGraph Workflow**
    - [ ] 实现 `Sentinel -> Analyst -> Risk Manager -> (Human) -> Tool Execution` 的状态机。

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

---

## 架构层次总结

| Layer | Component | Technology | Responsibility |
| :--- | :--- | :--- | :--- |
| **Brain** | **Multi-Agent System** | **LangGraph**, LLM | 复杂决策, 根因分析, 人机协作 |
| **Memory**| **Knowledge Base** | **Milvus**, RAG | 历史经验检索, 规则文档查询 |
| **Reflex**| **Stream Processor** | **Faust/Flink** | 实时聚合, 降噪, 信号触发 |
| **Nerves**| **Event Bus** | **Kafka**, Debezium | 实时数据捕获与传输 |
| **Hands** | **MCP Server** | **FastMCP** | 数据库读写, 原子工具暴露 |
