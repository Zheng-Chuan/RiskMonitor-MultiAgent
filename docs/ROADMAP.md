# 开发计划

采用最小可运行 demo -> 逐步扩充的策略, 从简单到复杂逐步构建系统.

## 2026-01 1 个月范围(优先级 P1)

说明:

- 该项目在 2026-01 的优先级低于 `RiskAgent-MultiAgent` 与 `RiskKnowGraph-GraphRAG`.
- 2026-01 只做最小可展示版本, 重点是可复现, 可演示, 可维护.

主线定位:

- 用例 A: Intraday desk exposure monitoring(near real time)
  - 输入: positions(交易系统落库) + market snapshot(上游 API 或 mock) + risk limits
  - 输出: desk 级别 exposure(PV, Delta, Vega 的简化版) + breaches + alert payload
  - 目标: 让工程师能通过工具与文档理解风控口径, 让 risk manager 能实时查询与订阅告警

硬性验收口径:

- 本地可运行: MCP server 可稳定启动, 数据库可运行.
- 端到端演示: MCP 客户端可调用至少 2 个工具, 且有 1 条 demo 脚本.
- 工程化底线: 无明文 secrets, 错误分层与结构化日志可定位, tests 可运行且通过.

验收原则:

- 以 tests 全部通过为硬标准.
- demo 作为辅助验证, 用于面试叙事与可复现展示.

周计划与 phase 映射:

- Week 1-2 对应 Phase 0: 工程化底线与可复现闭环.
- Week 3 对应 Phase 1: DX 与服务化形态稳定.
- Week 4 对应 Phase 3(最小版): 可观测与告警闭环, 指标化验收.

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

  - [ ] 模块化重构
    - [ ] 拆分 main.py 为模块(接口层, service 层, 计算层, 数据访问层, 配置层)
    - [ ] 统一输入输出 schema 与错误结构

  - [ ] 数据访问层工业化
    - [ ] 连接池, 超时, 重试
    - [ ] 读写分离预留点或 cache 抽象(先不实现也可)

  - [ ] 性能与容量口径
    - [ ] 固化压测用例(固定请求集)
    - [ ] 定义并输出 p50, p95 latency 的目标与测量方法

- 验收

  - [ ] p95 latency 在固定用例下达到目标(先给出保守目标, 例如 500ms 以内)
  - [ ] 关键模块可单测, 用例级逻辑可集成测试

### Week 3(Phase 1): 服务化形态与 DX 固化

- 交付

  - [ ] streamable-http 部署形态固化
    - [ ] streamable-http 作为推荐部署方式
    - [ ] health check, readiness, graceful shutdown
  - [ ] DX 固化
    - [ ] 统一启动与测试入口
    - [x] 明确目录职责(例如 src, scripts, tests)

- 验收

  - [ ] 在 streamable-http 模式下可稳定运行并可被客户端连接
  - [ ] tests 全部通过

### Week 4(Phase 3 最小版): 可观测与告警闭环

- 交付

  - [ ] 告警闭环
    - [ ] 告警规则最小集合(例如 desk delta breach)
    - [ ] 告警路由(例如 webhook 或写入 alerts 表)
  - [ ] 可观测与容量口径
    - [ ] 指标可观测: p50, p95 latency, error rate
    - [ ] 固化压测用例与报告输出

- 验收

  - [ ] 告警可端到端触发并可追踪(request_id, alert_id)
  - [ ] 固定压测用例下 error rate 与 p95 latency 可观测
  - [ ] tests 全部通过

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
4. **代码质量** - 使用类型提示、添加docstring、遵循PEP 8
