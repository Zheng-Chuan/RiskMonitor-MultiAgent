# 开发计划

采用最小可运行 demo -> 逐步扩充的策略, 从简单到复杂逐步构建系统.

## Phase 0: 基础强化与MCP最佳实践

**目标**: 在现有功能基础上优先完成安全, 稳定, 可扩展, 可维护方面的增强, 为后续各 Phase 打好生产级基础.

- [x] 移除 mcp_config.json 中的明文 secrets, 改为读取环境变量, 未使用的第三方 server 默认 disabled
- [x] 为高风险工具补充用途说明与前置授权提示, 确保用户同意与最小权限
- [x] 为至少 2 个工具完成 JSON Schema 化输入输出, 输出改为结构化 JSON
- [x] 为查询类工具增加分页与日期范围过滤参数
- [x] 统一错误分层与结构化日志, 引入 correlation id 便于排障
- [x] 为耗时操作提供 progress 与 cancellation 钩子
- [x] 引入 tasks 以支持长耗时操作的轮询与延迟结果获取
- [x] 评估启用 Streamable HTTP 与 SSE 流, 为无状态与水平扩展做准备
- [ ] 数据访问层强化: 连接池, 超时, 重试, 明确事务边界与资源释放
- [ ] 模块化重构: 拆分 main.py 为模块(工具层, 数据访问层, 配置层)
- [ ] 扩充单元与集成测试覆盖新增路径

**验收标准**:
- mcp_config.json 无明文 secrets, 未用 server 处于禁用状态
- 至少 2 个工具完成 JSON Schema 化并返回结构化 JSON
- 查询类工具支持分页或日期范围过滤
- 关键路径具备结构化日志与错误分层, 并提供 progress/cancellation 钩子
- 新增或调整的测试通过

## Phase 1: MCP 最小可运行与开发体验

**目标**: 保证 MCP server 可在本地稳定运行, 并能被 MCP 客户端调用, 形成端到端演示闭环.

- [x] 项目初始化
- [x] Docker 环境配置
- [x] MySQL 数据库初始化
- [x] MCP Server 基础框架
- [x] 基础查询与聚合工具可用
- [x] Claude Desktop 或 Windsurf 可调用工具

**验收标准**:
- 数据库正常运行
- MCP Server 能启动
- MCP 客户端能调用至少 2 个工具
- 至少 1 个端到端流程跑通

## Phase 2: 金融衍生品业务场景与风险计算展示

**目标**: 用更专业的金融衍生品业务场景驱动实现, 重点展示业务理解, 数据建模能力, 与风险计算能力.

### 2.1 业务问题与用例设计

- [ ] 选定 2 到 3 条真实感用例, 并明确计算口径与输出形式.
  - 主线 A: FRTB SA sensitivities 流程演示.
    - 输入: position, instrument, market snapshot, risk factor mapping.
    - 输出: Delta, Vega, Curvature sensitivities, 以及按 risk class 的聚合结果.
    - 可选: 应用相关性矩阵后得到资本占用的示意结果.
  - 辅线 C: CVA 简化链路演示.
    - 输入: counterparty, rating or PD, LGD, expected exposure.
    - 输出: counterparty 级别 CVA 与变化解释.
  - 业务增强: 多币种 Dollarization 与 desk 级别聚合, 作为口径统一的一部分.
- [ ] 定义输入输出口径, 例如: desk, trader, portfolio, instrument, currency, valuation_time, risk_factor

### 2.2 数据模型与数据字典

- [ ] 基于业务用例设计数据模型, 明确实体与关系, 覆盖以下最小集合:
  - instruments: component, compound, underlying, strike, expiry, option_type
  - positions: component_position, compound_position, quantity, desk, trader, book
  - market_data: spot, fx_rates, curves, vol_surface, credit_spreads
  - risk_measures: pv, delta, gamma, vega, theta, dv01, cva
  - counterparties: rating, pd, lgd, netting_set, collateral
- [ ] 为关键字段提供数据字典, 明确单位与口径, 例如:
  - delta per share vs per contract, dv01 definition, fx conversion convention
  - valuation_time cut, eod vs intraday snapshot
- [ ] 为查询路径设计索引策略, 以演示工程思维即可, 不追求自研高可用

### 2.3 公开数据与资料引用

- [ ] 收集可公开引用的数据或资料, 用于支撑口径与示例数据:
  - 利率曲线节点样例, 波动率样例, CDS spread 样例, FX spot 样例
  - Greeks 定义与聚合口径资料, FRTB SA sensitivities 资料
  - CVA 与 XVA 的概念资料
- [ ] 在 docs 中记录来源链接与口径假设, 并说明简化点

### 2.4 风险计算实现

- [ ] 定义统一的 risk measure 输出结构, 例如: pv, delta, gamma, vega, theta, dv01, cva
- [ ] 实现至少 2 条计算链路, 并可被 MCP tools 编排.
  - FRTB SA 主链路: risk factor mapping -> sensitivities -> bucket aggregation -> correlation aggregation.
  - CVA 副链路: exposure -> PD term structure or simplified PD -> LGD -> CVA.
- [ ] 增加结果校验与 sanity check:
  - 数值范围, 符号, 单位一致性
  - 聚合前后守恒检查, 例如 sum(component) == portfolio

### 2.5 MCP 交互层设计

- [ ] 以 MCP 为中心设计工具集合, 让 agent 易于编排, 并体现业务语言:
  - list_desks, list_traders, query_positions, get_market_snapshot
  - frtb_map_risk_factors, frtb_calc_sensitivities, frtb_aggregate_sa
  - frtb_apply_correlation, frtb_capital_charge_summary
  - dollarize_positions, run_shock_scenario
  - calc_cva_summary
- [ ] 增加 Resources 与 Prompts 模板, 让业务背景与口径能被 agent 复用

### 2.6 测试与演示

- [ ] 单元测试覆盖关键计算
- [ ] 集成测试覆盖典型用例
- [ ] 输出 1 份 demo 脚本或对话示例, 展示从查询到风险分析的完整链路

**验收标准**:
- 有清晰的业务用例与数据口径说明
- 数据模型与字段口径合理且可解释
- 至少 2 条风险计算链路可运行并有测试
- MCP 工具设计可被 agent 自然编排
- 有可复现实验与演示材料

## Phase 3: 生产化与高可用 Web 服务

**目标**: 将 MCP server 以 streamable-http 方式部署为可复用的服务, 使用成熟框架与基础设施能力, 用指标验收高可用与性能.

### 3.1 部署方式与运行形态

- [ ] 基于成熟组件完成服务化部署, 不自研:
  - uvicorn, docker, reverse proxy, k8s 或托管平台
- [ ] 支持水平扩展与无状态化:
  - streamable-http transport
  - tasks 结果存储方案演进, 例如 redis

### 3.2 可观测性与容量指标

- [ ] 定义指标与验收口径:
  - QPS, p50, p95 latency, error rate
  - availability SLO, 例如 99.9%
- [ ] 集成成熟观测方案:
  - structured logging
  - metrics, traces, dashboards

### 3.3 安全与治理

- [ ] 采用成熟方案实现:
  - TLS, authn/authz, rate limit
  - network policy, secrets management

**验收标准**:
- 在 streamable-http 模式下可稳定运行并可被客户端连接
- 在固定压测用例下达到目标 QPS 与 p95 延迟
- 异常与取消路径可观测, 且错误率可控

## 时间规划

| Phase | 预计时间 | 关键里程碑 |
|-------|---------|-----------|
| Phase 0 | 1 周 | MCP 最佳实践与可维护性增强 |
| Phase 1 | 1 周 | MCP 最小可运行与端到端演示 |
| Phase 2 | 3-6 周 | 业务场景驱动的数据建模与风险计算展示 |
| Phase 3 | 1-2 周 | 生产化与指标验收 |

**总计**: 6-10 周

## 开发建议

1. **每完成一个Phase就提交Git** - 保持代码可回溯
2. **边开发边写测试** - 避免后期bug堆积
3. **保持README更新** - 记录问题和解决方案
4. **定期Demo** - 录制演示视频用于展示
5. **代码质量** - 使用类型提示、添加docstring、遵循PEP 8
