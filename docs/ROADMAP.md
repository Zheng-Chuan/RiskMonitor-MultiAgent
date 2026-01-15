# 开发计划

采用最小可运行 demo -> 逐步扩充的策略, 从简单到复杂逐步构建系统.

## 功能
1. 根据用户提问 计算不同纬度的风险数据 如果超出给定阈值 则报警
2. 采用事件驱动模式 数据库每一笔交易 触发风险计算和检测 如果超出给定阈值 则报警
3. 高可用的服务
4. 用户身份安全等级区分 不同的用户有不同的数据访问权限


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

### Week 5(Phase 3+): 事件驱动基础与告警语义

- 交付

  - [ ] CDC 事件口径与 topics 定义
    - [ ] 定义 trade position 变更事件 schema
    - [ ] 定义 topics 规划
      - [ ] positions_cdc topic
        - [ ] Kafka message key 保持 Debezium 默认主键
        - [ ] consumer 侧按 desk 做聚合与 breach 判断
      - [ ] risk_alerts topic
        - [ ] 可选扩展 topic, 用于对外 fan out 或未来拆分独立 notifier
        - [ ] partition key 固定为 alert_id
    - [ ] 将 topic 规划落地到配置
      - [ ] positions_cdc key 使用 position_id
      - [ ] risk_alerts key 使用 alert_id
  - [ ] Debezium MySQL binlog to Kafka PoC
    - [ ] 本地可跑通 MySQL binlog 订阅
    - [ ] 事件可进入 Kafka topic 并可被 consumer 消费
  - [ ] desk level breach 语义与告警生命周期
    - [ ] desk 迁移语义(方案B)
      - [ ] update 时 desk 发生变化: 对 before.desk 扣减 对 after.desk 增加
    - [ ] 明确告警状态
      - [ ] pending_analysis
      - [ ] pending_delivery
      - [ ] delivered
      - [ ] consumed
    - [ ] 定义告警解除规则
      - [ ] 强制接收方 webhook ack 才能消费
      - [ ] 未 ack 时不消费, 告警保持可重试投递
  - [ ] server 内部事件触发(2A)
    - [ ] analysis_queue, delivery_queue 使用进程内 asyncio.Queue
    - [ ] 启动补偿: 扫描 pending_analysis 与 pending_delivery 并重新 enqueue
    - [ ] 约束: 主链路事件驱动, 扫描仅用于补偿恢复
  - [ ] 告警落库字段增量
    - [ ] alerts 表新增 status, analysis_json, analysis_text, delivery_id 等字段
    - [ ] 新增 processed_cdc_events 与 desk_risk_state 表
  - [ ] 质量口径
    - [ ] 覆盖率可度量
      - [x] make test-cov 生成 html 和 xml 覆盖率
      - [ ] 核心链路覆盖率目标 80 percent plus
    - [ ] lint 统一
      - [x] 只使用 pylint 作为静态检查入口

- 验收

  - [ ] CDC 事件 schema 和 topic 规划有文档并落地到配置
  - [ ] 本地环境可稳定把 MySQL 变更写入 Kafka 并消费
  - [ ] server 重启后可通过启动补偿继续处理未完成告警
  - [ ] pytest 全量通过
  - [ ] 覆盖率报告可生成并达到目标

### Week 6+(Phase 3+): 告警推送闭环与 10s 延迟目标

- 交付

  - [ ] CDC consumer and risk engine
    - [ ] 消费 positions_cdc topic
    - [ ] 以 desk level 口径触发风险计算与 breach 判断
    - [ ] 单 desk 超限只生成一次告警, 基于 desk_risk_state 做状态判断
    - [ ] 将 alerts 写入 alerts 表, 初始状态 pending_analysis
    - [ ] 可选: 同步发布 risk_alerts topic 用于对外扩展
  - [ ] LLM analyzer worker(server side)
    - [ ] 从 analysis_queue 取 alert_id, 组装上下文并调用 LLM
    - [ ] 写回 analysis_json 与 analysis_text
    - [ ] 更新告警状态为 pending_delivery, 并 enqueue 到 delivery_queue
  - [ ] webhook notifier worker
    - [ ] 从 delivery_queue 取 alert_id 并推送到 webhook endpoint
    - [ ] 签名校验与幂等, delivery_id 作为幂等键
    - [ ] 重试与死信
    - [ ] 接收方 ack API
      - [ ] 接收方必须 ack 才能把 alert 标记为 consumed
  - [ ] 10s 延迟目标
    - [ ] 定义从 DB commit 到 webhook delivered 的端到端延迟口径, 默认包含 LLM 分析与投递
    - [ ] 在 /metrics 暴露分段指标
      - [ ] consumer lag
      - [ ] analysis latency
      - [ ] delivery latency

- 验收

  - [ ] 从单笔交易写入到告警推送 delivered 的 p95 延迟小于 10s
  - [ ] 未 ack 的告警不会被消费 且会按策略重试
  - [ ] ack 后告警状态可追踪并变更为 consumed
  - [ ] /metrics 可观测 consumer lag analysis latency delivery latency 和 webhook 成功率

### Week 7+(Phase 3 扩展): k8s 生产化与 CI CD

- 交付

  - [ ] k8s 部署形态
    - [ ] 组件拆分
      - [ ] mcp server
        - [ ] 内置 analyzer worker 和 notifier worker
      - [ ] web ui
      - [ ] cdc consumer
      - [ ] webhook notifier
        - [ ] 可选, 若从 mcp server 中拆出独立部署
      - [ ] llm analyzer
        - [ ] 可选, 若从 mcp server 中拆出独立部署
    - [ ] 探针
      - [ ] /health
      - [ ] /ready
    - [ ] 配置与 secrets
    - [ ] HPA 与资源口径
  - [ ] CI CD
    - [ ] GitHub Actions: pylint tests coverage

- 验收

  - [ ] k8s 可部署并可水平扩展
  - [ ] CI 可稳定运行并阻断不合格变更

## Phase 映射(参考)

说明:

- 本文以 week 为权威计划.
- phase 仅用于描述能力成熟度, 用于后续复盘与叙事.

phase 定义:

- Phase 0: 安全与工程化底线, 可复现, 可观测, tests 可信.
- Phase 1: MCP 可用与 DX, demo 脚本固化, 结构清晰.
- Phase 2: 专业业务用例与口径, 更强的风险计算与 explainability.
- Phase 3: 高可用 web 服务, 性能与 SLO 可量化验收.

## 时间规划

| Phase | 预计时间 | 关键里程碑 |
| ------- | -------- | ---------- |
| Phase 0 | 1 周 | MCP 最佳实践与可维护性增强 |
| Phase 1 | 1 周 | MCP 最小可运行与端到端演示 |
| Phase 2 | 3-6 周 | 业务场景驱动的数据建模与风险计算展示 |
| Phase 3 | 1-2 周 | 生产化与指标验收 |

**总计**: 6-10 周

## 开发建议

1. **每完成一个Phase就提交Git** - 保持代码可回溯
2. **边开发边写测试** - 避免后期bug堆积
3. **定期Demo** - 录制演示视频用于展示
4. **代码质量** - 使用类型提示 添加 docstring 遵循 PEP 8
