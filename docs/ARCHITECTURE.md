# 系统架构和技术特点

## 项目概述

RiskMonitor-MCP 是一个基于 Model Context Protocol (MCP) 的金融衍生品风险监控服务, 为 AI Agent 提供实时风险计算和监控能力. 项目采用分层架构设计, 实现了从数据访问到业务逻辑的完整闭环.

## 架构总览

```text
┌─────────────────┐        ┌────────────────────────────────────────────┐
│ AI Clients      │ -----> │ FastMCP Server                             │
│ - Claude等      │        │ - MCP tools: positions query, exposure     │
│ - HTTP 客户端    │        │   monitor, total delta, tasks, metrics     │
└─────────────────┘        │ - Custom routes: /health /ready /metrics   │
                           │ - Structured logging with request_id       │
                           └───────────────┬────────────────────────────┘
                                           │
                               ┌───────────▼───────────┐
                               │ MySQL (positions,     │
                               │ alerts, limits)       │
                               └───────────┬───────────┘
                                           │
                               ┌───────────▼───────────┐
                               │ Market Snapshot       │
                               │ Service (HTTP)        │
                               └───────────────────────┘
```

## CDC 与告警推送架构

- Debezium 订阅 MySQL binlog, 输出 positions_cdc topic.
- positions_cdc 的 Kafka message key 保持 Debezium 默认主键(position_id).
- CDC consumer 拉取 positions_cdc, 维护 position 最新状态并按 desk 级聚合 delta, 触发 breach 判断, 写入 alerts 表与 risk_alerts topic.
- 方案B desk 迁移语义: update 时若 desk 发生变化 则对 before.desk 扣减 对 after.desk 增加.
- webhook notifier 订阅 risk_alerts topic, 将告警推送到外部 webhook, 支持签名校验, 幂等, 重试.
- 监控: consumer lag 与 delivery latency 暴露在 /metrics.

```text
MySQL binlog --Debezium--> Kafka topics (positions_cdc, risk_alerts)
                                     │
                                     ▼
                          CDC Consumer + Risk Engine
                          - desk delta 聚合与阈值判断
                          - 写 alerts 表 + risk_alerts topic
                                     │
                                     ▼
                            Webhook Notifier
                          - 签名 + 幂等 + 重试
```

## 当前能力清单

- MCP 工具: query_all_positions, query_positions_by_trader, query_positions_by_desk, calculate_total_delta, monitor_desk_exposure, start_calculate_total_delta_task, get_task_status, cancel_task, get_service_metrics.
- 计算与规则: compute_exposure, build_abs_delta_breaches, alert_rules_service 生成规则, alerting_service 写入 alerts 表.
- 数据访问: positions_repository, alerts_repository, market_snapshot_client 提供数据读取并结合错误映射.
- 可观测性: 结构化日志带 request_id, Prometheus 指标在 /metrics, health 与 ready 路由可用于探针.
- 持久化: MySQL 存储 positions, alerts, risk_limits 等核心表, migration 已包含 alerts 表.
- 运行形态: 支持 stdio 与 streamable-http, Makefile 提供 setup-mcp 与 test-all 入口.

## 技术亮点

### 1. MCP Streamable HTTP 作为生产传输

**技术点**:

- 支持 `streamable-http` transport, 适配生产环境的 HTTP 访问模式
- 支持 `stdio` transport, 适配本地 Claude Desktop 等客户端

**落地位置**:

- 启动时通过环境变量 `MCP_TRANSPORT=streamable-http` 切换
- server 层基于 FastMCP 提供工具注册和 HTTP 路由

### 2. HTTP 端点治理: health ready metrics

**技术点**:

- `/health` 用于 liveness
- `/ready` 用于 readiness, 支持关闭中返回 not ready
- `/metrics` 暴露 Prometheus text format

**落地位置**:

- `src/riskmonitor_mcp/server.py` 使用 `@mcp.custom_route` 挂载端点

### 3. Prometheus 指标暴露

**技术点**:

- Prometheus exposition format
- 采集请求计数, 平均延迟, 错误计数, 错误率, 进程运行时间

**落地位置**:

- `src/riskmonitor_mcp/services/prometheus_metrics_service.py`
- `/metrics` 端点返回 `text/plain; version=0.0.4`

### 4. 告警闭环: 规则评估 + 持久化

**技术点**:

- desk abs delta breach 规则
- INFO WARNING CRITICAL 三级告警
- 告警写入 MySQL alerts 表, 支持按 request_id 追踪

**落地位置**:

- migration: `db/migrations/003_create_alerts_table.sql`
- rules: `src/riskmonitor_mcp/services/alert_rules_service.py`
- persistence: `src/riskmonitor_mcp/data_access/alerts_repository.py`
- tool integration: `src/riskmonitor_mcp/tools/mcp_tools.py` 的 `monitor_desk_exposure`

### 5. 异步任务: 启动 查询 取消

**技术点**:

- 后台任务启动, 轮询查询状态
- 支持任务取消

**落地位置**:

- `start_calculate_total_delta_task`
- `get_task_status`
- `cancel_task`
- `src/riskmonitor_mcp/services/task_registry.py`

### 6. Cache 抽象预留点

**技术点**:

- Cache Protocol + Noop 默认实现
- 为后续 Redis 等实现预留替换点

**落地位置**:

- `src/riskmonitor_mcp/data_access/cache.py`

## 业务痛点和技术解决方案

### 痛点 1: 金融风险数据复杂, AI Agent 难以直接访问

**业务场景**:

- 交易台每天产生数万笔交易, 涉及股票、期权、互换等多种金融工具
- 风险数据分散在多个系统(交易系统、风控系统、市场数据系统)
- AI Agent 需要实时查询风险敞口, 但缺少统一的接口

**技术解决方案**:

- **MCP 协议**: 为 AI Agent 提供标准化的工具调用接口
- **工具抽象**: 将复杂的风险计算封装为简单的工具(如 `monitor_desk_exposure`)
- **结构化输出**: 返回 JSON 格式的结构化数据, AI Agent 易于理解和处理

**代码示例**:

```python
@mcp.tool()
async def monitor_desk_exposure(
    desk: str,
    as_of: Optional[str] = None,
    abs_delta_limit: float = 1000000.0
) -> dict:
    """监控交易台风险敞口, 返回 delta、breach 和 alerts"""
    # 1. 查询头寸数据
    positions = fetch_positions_by_desk(desk)
    
    # 2. 计算风险敞口
    exposure = calculate_exposure(positions)
    
    # 3. 检查限额
    breaches = check_limits(exposure, abs_delta_limit)
    
    # 4. 生成告警
    alerts = generate_alerts(breaches)
    
    return {
        "exposure": exposure,
        "breaches": breaches,
        "alerts": alerts
    }
```

**业务价值**:
- AI Agent 可以通过自然语言查询风险数据(例如: "帮我查看股票衍生品交易台的风险敞口")
- 风险经理可以快速获取实时风险报告, 无需手动查询多个系统
- 支持自动化风险监控和告警

### 痛点 2: 风险计算耗时长, 影响用户体验

**业务场景**:

- 计算全市场的 delta 需要聚合数万笔头寸, 耗时可能超过 10 秒
- 用户在等待过程中无法获取进度反馈, 体验差
- 如果计算失败, 用户需要重新发起请求, 浪费时间

**技术解决方案**:

- **异步任务**: 将长时间计算任务放到后台执行
- **任务状态查询**: 提供 `get_task_status` 工具, 用户可以查询任务进度
- **任务取消**: 提供 `cancel_task` 工具, 用户可以取消不需要的任务

**代码示例**:
```python
# 1. 启动异步任务
@mcp.tool()
async def start_calculate_total_delta_task() -> dict:
    task_id = uuid.uuid4().hex
    task_registry.register_task(task_id, "calculate_total_delta")
    asyncio.create_task(_run_calculate_total_delta(task_id))
    return {"task_id": task_id, "status": "running"}

# 2. 查询任务状态
@mcp.tool()
async def get_task_status(task_id: str) -> dict:
    task = task_registry.get_task(task_id)
    return {
        "task_id": task_id,
        "status": task.status,  # running, completed, failed
        "result": task.result if task.status == "completed" else None
    }

# 3. 取消任务
@mcp.tool()
async def cancel_task(task_id: str) -> dict:
    task_registry.cancel_task(task_id)
    return {"task_id": task_id, "status": "cancelled"}
```

**业务价值**:
- 用户可以立即获得任务 ID, 无需等待计算完成
- 用户可以查询任务进度, 了解计算状态
- 用户可以取消不需要的任务, 节省计算资源

### 痛点 3: 风险超限难以及时发现, 缺少主动告警

**业务场景**:

- 交易台的 delta 超过限额时, 风险经理需要手动查询才能发现
- 缺少主动告警机制, 可能导致风险累积
- 告警信息分散, 难以追踪和管理

**技术解决方案**:

- **告警规则引擎**: 自动评估风险指标是否超限
- **多级告警**: 支持 INFO/WARNING/CRITICAL 三级告警, 根据超限程度自动分级
- **告警持久化**: 将告警写入数据库, 支持查询和追踪
- **告警追踪**: 每个告警都有唯一的 `alert_id` 和 `request_id`, 便于关联和追踪

**代码示例**:
```python
# 1. 告警规则评估
def evaluate_desk_delta_breach(
    desk: str,
    abs_delta: float,
    threshold: float,
    request_id: str
) -> list[dict]:
    """评估 delta 是否超限, 返回告警列表"""
    if abs_delta <= threshold:
        return []
    
    breach_amount = abs_delta - threshold
    breach_pct = breach_amount / threshold
    
    # 根据超限程度确定告警级别
    if breach_pct < 0.2:
        severity = "INFO"
    elif breach_pct < 0.5:
        severity = "WARNING"
    else:
        severity = "CRITICAL"
    
    return [{
        "alert_id": uuid.uuid4().hex,
        "request_id": request_id,
        "alert_type": "desk_delta_breach",
        "severity": severity,
        "desk": desk,
        "metric_value": abs_delta,
        "threshold_value": threshold,
        "breach_amount": breach_amount,
        "message": f"Desk {desk} delta breach: {abs_delta:.2f} > {threshold:.2f}"
    }]

# 2. 告警持久化
async def save_alerts(alerts: list[dict]):
    """将告警保存到数据库"""
    await alerts_repository.save_alerts_batch(alerts)

# 3. 告警查询
async def get_recent_alerts(severity: str = None, desk: str = None):
    """查询最近的告警"""
    return await alerts_repository.get_recent_alerts(
        severity=severity,
        desk=desk,
        limit=100
    )
```

**业务价值**:
- 风险超限时自动生成告警, 无需人工监控
- 告警分级, 风险经理可以优先处理高优先级告警
- 告警可追踪, 支持告警确认和关闭流程
- 告警历史可查询, 支持风险分析和合规审计

### 痛点 4: 系统可用性难以保证, 缺少监控和告警

**业务场景**:

- 数据库连接断开、上游服务超时等问题难以及时发现
- 缺少性能指标, 无法进行容量规划和性能优化
- 故障发生时难以快速定位问题

**技术解决方案**:

- **健康检查**: 提供 `/health` 和 `/ready` 端点, 支持 Kubernetes 健康检查
- **Prometheus 指标**: 暴露 `/metrics` 端点, 支持 Prometheus 采集和告警
- **结构化日志**: 每个请求都有 `request_id`, 便于日志关联和问题追踪
- **错误分类**: 统一的错误码和可重试标记, 支持自动重试和降级

**代码示例**:
```python
# 1. 健康检查
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> Response:
    return JSONResponse({"status": "ok"})

# 2. 就绪检查
@mcp.custom_route("/ready", methods=["GET"])
async def readiness_check(request: Request) -> Response:
    # 检查数据库连接
    ok, message, err = check_mysql_ready()
    if ok:
        return JSONResponse({"status": "ready", "checks": {"mysql": "ok"}})
    return JSONResponse(
        {"status": "not_ready", "checks": {"mysql": {"status": "not_ready"}}},
        status_code=503
    )

# 3. Prometheus 指标
@mcp.custom_route("/metrics", methods=["GET"])
async def metrics_endpoint(request: Request) -> Response:
    metrics_text = generate_prometheus_metrics()
    return Response(content=metrics_text, media_type="text/plain")
```

**业务价值**:
- 支持 Kubernetes 滚动更新, 避免服务中断
- Prometheus 告警规则可以主动通知运维人员
- 性能指标支持容量规划和性能优化
- 结构化日志支持快速定位问题

### 痛点 5: 数据库连接不稳定, 影响系统可用性

**业务场景**:

- MySQL 连接可能因为网络抖动、超时等原因断开
- 连接池中的连接可能已经失效(stale connection)
- 长时间运行的连接可能被 MySQL 回收(wait_timeout)

**技术解决方案**:

- **连接池**: 使用 SQLAlchemy 连接池, 复用连接, 避免频繁创建连接
- **连接健康检查**: `pool_pre_ping=True`, 使用前先 ping, 避免使用失效连接
- **连接回收**: `pool_recycle=1800`, 定期回收连接, 避免超过 MySQL wait_timeout
- **超时配置**: 配置连接超时、读超时、写超时, 避免长时间阻塞

**代码示例**:
```python
create_engine(
    _build_mysql_url(),
    pool_pre_ping=True,              # 使用前先 ping
    pool_recycle=1800,               # 30 分钟回收连接
    pool_size=5,                     # 核心连接数
    max_overflow=10,                 # 最大溢出连接数
    connect_args={
        "connect_timeout": 3,        # 连接超时 3 秒
        "read_timeout": 5,           # 读超时 5 秒
        "write_timeout": 5,          # 写超时 5 秒
    }
)
```

**业务价值**:
- 避免因为连接失效导致的请求失败
- 提升系统可用性和稳定性
- 减少数据库连接开销, 提升性能

### 痛点 6: 错误信息不明确, 难以定位问题

**业务场景**:
- 数据库查询失败时, 只有一个通用的错误信息, 无法判断是超时、连接失败还是 SQL 语法错误
- 上游服务调用失败时, 无法判断是否可以重试
- 缺少错误追踪, 难以定位问题根因

**技术解决方案**:

- **统一错误模型**: `DataAccessError` 包含错误码、可重试标记、错误信息和原始异常
- **错误映射**: 将底层异常(pymysql, httpx)映射为统一的错误模型
- **错误码稳定**: 上层可以基于错误码做精确处理, 不依赖错误信息字符串
- **原因链**: 保留原始异常, 便于问题排查

**代码示例**:
```python
def map_mysql_error(err: pymysql.MySQLError, operation: str) -> DataAccessError:
    if _is_timeout_error(err):
        return DataAccessError(
            code="DB_TIMEOUT",
            retriable=True,
            message=f"mysql timeout op={operation}",
            cause=err
        )
    
    if isinstance(err, pymysql.err.OperationalError):
        return DataAccessError(
            code="DB_UNAVAILABLE",
            retriable=True,
            message=f"mysql unavailable op={operation}",
            cause=err
        )
    
    # ... 其他错误类型
```

**业务价值**:
- 错误信息明确, 便于快速定位问题
- 可重试标记支持自动重试, 提升系统可用性
- 错误码稳定, 上层可以做精确处理和降级

---

## 整体数据流

```text
┌─────────────────┐
│  Trading Desk   │  交易员执行交易(股票、期权、互换等)
└────────┬────────┘
         │ Trade Data
         ↓
┌─────────────────┐
│  Quant Team     │  计算风险指标(Delta, Gamma, Vega, CVA等)
└────────┬────────┘
         │ Risk Metrics
         ↓
┌─────────────────────────────────────────────────────────┐
│              MySQL Database (Port 3307)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Positions   │  │  Securities  │  │  Risk Data   │  │
│  │              │  │              │  │              │  │
│  │ - Component  │  │ - Component  │  │ - Greeks     │  │
│  │ - Compound   │  │ - Compound   │  │ - CVA        │  │
│  │              │  │              │  │ - Exposure   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│                  RiskMonitor-MCP Server                 │
│  ┌────────────────────────────────────────────────────┐ │
│  │              MCP Function Calls                    │ │
│  │                                                    │ │
│  │  • 头寸查询工具 (Position Query)                    │ │
│  │  • Greeks计算工具 (Greeks Calculation)             │ │
│  │  • CVA计算工具 (CVA Calculation)                   │ │
│  │  • 风险聚合工具 (Risk Aggregation)                 │ │
│  │  • 限额检查工具 (Limit Check)                      │ │
│  │  • 报表生成工具 (Report Generation)                │ │
│  │  • 压力测试工具 (Stress Testing)                   │ │
│  │  • 场景分析工具 (Scenario Analysis)                │ │
│  └────────────────────────────────────────────────────┘ │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│                    AI Agent / Client                    │
│  • Claude Desktop                                       │
│  • Custom AI Applications                               │
│  • Risk Manager自然语言查询                              │
└────────┬────────────────────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────────────────────┐
│                   Output & Delivery                     │
│  • Excel/PDF 报表                                        │
│  • 实时风险仪表盘                                         │
│  • 下游数据湖                                            │
│  • 监管报送系统                                          │
└─────────────────────────────────────────────────────────┘
```

## MCP特性

### 已使用

- [x] Tools: 通过 FastMCP `@mcp.tool` 暴露工具, 支持头寸查询与简单聚合
- [x] 本地进程集成: 使用 stdio 方式与 MCP 客户端对接
- [x] 环境变量配置: 通过 env 注入数据库连接参数, 支持本地与容器切换

### Phase 0 计划增强

- [x] 移除配置中的明文 secrets, 改为读取环境变量, 未使用的第三方 server 默认 disabled
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

### Phase 2 业务主线

- 主线 A: FRTB SA sensitivities, risk factor mapping -> sensitivities -> aggregation -> correlation
- 辅线 C: CVA 简化链路, exposure -> PD -> LGD -> CVA

### Phase 3 生产化与高可用

- 使用 streamable-http 作为生产 transport
- 使用成熟组件完成部署与治理, 并用 QPS, p95 latency, SLO 验收

## 基础技术栈

### 后端
- Python 3.13+
- FastMCP - MCP Server框架
- SQLAlchemy - 数据库ORM
- PyMySQL - MySQL数据库驱动

### 数据库
- MySQL 8.0 - 关系数据库
- Docker - 容器化部署

### 数据处理
- NumPy/Pandas - 数值计算和数据处理
- QuantLib (可选) - 金融衍生品定价库

### 报表生成
- OpenPyXL - Excel报表
- ReportLab (可选) - PDF报表
- Plotly (可选) - 可视化图表
