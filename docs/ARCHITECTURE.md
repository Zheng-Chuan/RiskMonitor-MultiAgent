# 系统架构和技术特点

## 项目概述

RiskMonitor-MCP 是一个基于 Model Context Protocol (MCP) 的金融衍生品风险监控服务, 为 AI Agent 提供实时风险计算和监控能力. 项目采用分层架构设计, 实现了从数据访问到业务逻辑的完整闭环.

---

## 技术亮点

### 1. 清晰的分层架构设计 ⭐⭐⭐⭐⭐

**亮点**: 采用经典的四层架构, 职责清晰, 易于维护和扩展

```
┌─────────────────────────────────────┐
│  MCP Tools Layer (tools/)           │  ← 对外接口层: MCP 工具注册和调用
├─────────────────────────────────────┤
│  Business Services (services/)      │  ← 业务逻辑层: 风险计算、告警规则
├─────────────────────────────────────┤
│  Data Access Layer (data_access/)   │  ← 数据访问层: 数据库、外部 API
├─────────────────────────────────────┤
│  Infrastructure (MySQL, HTTP)       │  ← 基础设施层: 数据库、消息队列
└─────────────────────────────────────┘
```

**技术价值**:
- 依赖方向正确(上层依赖下层), 避免循环依赖
- 每层职责单一, 易于单元测试和集成测试
- 支持水平扩展和模块替换

### 2. 统一的错误处理和分类机制 ⭐⭐⭐⭐⭐

**亮点**: 实现了 `DataAccessError` 统一错误模型, 支持错误码、可重试标记和原因链

```python
@dataclass(frozen=True)
class DataAccessError(RuntimeError):
    code: str              # 稳定的错误码, 用于上层映射
    retriable: bool        # 是否可重试, 支持自动重试策略
    message: str           # 人类可读的错误信息
    cause: Optional[BaseException] = None  # 原始异常, 保留完整堆栈
```

**技术价值**:
- 错误码稳定, 上层可以基于错误码做精确处理
- `retriable` 标记支持自动重试策略, 提升系统可用性
- 保留原始异常, 便于问题排查和根因分析

**错误分类**:
- `DB_TIMEOUT`: 数据库超时, 可重试
- `DB_UNAVAILABLE`: 数据库不可用, 可重试
- `DB_QUERY_FAILED`: SQL 语法错误, 不可重试
- `UPSTREAM_TIMEOUT`: 上游服务超时, 可重试
- `UPSTREAM_BAD_STATUS`: 上游返回错误状态码, 根据状态码判断是否可重试

### 3. 完善的可观测性体系 ⭐⭐⭐⭐⭐

**亮点**: 实现了日志、指标、告警三位一体的可观测性体系

**3.1 结构化日志**:
```python
# 每个请求都有唯一的 request_id, 便于日志关联和问题追踪
log_info(f"monitor_desk_exposure start desk={desk}", request_id)
log_error(f"query failed error={err}", request_id)
```

**3.2 Prometheus 指标**:
```python
# 暴露 /metrics 端点, 支持 Prometheus 采集
- mcp_requests_total: 请求总数(按工具名称分组)
- mcp_request_latency_ms_avg: 平均延迟(按工具名称分组)
- mcp_errors_total: 错误总数(按工具名称和错误码分组)
- mcp_error_rate: 错误率
- process_uptime_seconds: 进程运行时间
```

**3.3 告警系统**:
```python
# 告警规则引擎, 支持多级告警(INFO/WARNING/CRITICAL)
# 告警持久化到数据库, 支持按 request_id/alert_id/severity 查询
# 告警可追踪, 支持告警确认和关闭
```

**技术价值**:
- 日志提供详细的执行轨迹, 便于问题排查
- 指标提供系统健康度量, 支持容量规划和性能优化
- 告警提供主动通知, 支持快速响应和故障恢复

### 4. 工业级数据库连接池管理 ⭐⭐⭐⭐⭐

**亮点**: 使用 SQLAlchemy 连接池, 配置了完善的超时和健康检查

```python
create_engine(
    _build_mysql_url(),
    pool_pre_ping=True,              # 连接前 ping, 避免 stale connection
    pool_recycle=1800,               # 连接回收时间, 避免 MySQL wait_timeout
    pool_size=5,                     # 核心连接数
    max_overflow=10,                 # 最大溢出连接数
    connect_args={
        "connect_timeout": 3,        # 连接超时
        "read_timeout": 5,           # 读超时
        "write_timeout": 5,          # 写超时
    }
)
```

**技术价值**:
- `pool_pre_ping` 避免使用已断开的连接, 提升可用性
- 合理的连接池大小, 平衡资源占用和并发能力
- 完善的超时配置, 避免长时间阻塞

### 5. 参数化查询防 SQL 注入 ⭐⭐⭐⭐⭐

**亮点**: 所有 SQL 查询都使用参数化, 没有字符串拼接

```python
# ✅ 正确: 使用参数化查询
sql = text("""
    SELECT * FROM positions 
    WHERE trader_id = :trader_id AND desk = :desk
""")
conn.execute(sql, {"trader_id": trader_id, "desk": desk})

# ❌ 错误: 字符串拼接(本项目中不存在)
sql = f"SELECT * FROM positions WHERE trader_id = '{trader_id}'"
```

**技术价值**:
- 完全防止 SQL 注入攻击
- 数据库可以缓存执行计划, 提升性能

### 6. 异步处理和任务管理 ⭐⭐⭐⭐

**亮点**: 支持长时间任务的异步执行和状态查询

```python
# 启动异步任务
task_id = start_calculate_total_delta_task()

# 查询任务状态
status = get_task_status(task_id)  # running, completed, failed

# 取消任务
cancel_task(task_id)
```

**技术价值**:
- 避免长时间阻塞客户端
- 支持任务取消, 节省资源
- 支持任务状态查询, 提升用户体验

### 7. Graceful Shutdown 和 Readiness 探针 ⭐⭐⭐⭐

**亮点**: 实现了优雅关闭和健康检查机制

```python
# /health 端点: 服务是否存活
GET /health -> {"status": "ok"}

# /ready 端点: 服务是否就绪(数据库连接是否正常)
GET /ready -> {"status": "ready", "checks": {"mysql": "ok"}}

# 收到 SIGTERM 信号时, 先标记为 not ready, 然后等待请求处理完成
```

**技术价值**:
- 支持 Kubernetes 健康检查和滚动更新
- 避免在关闭过程中接收新请求
- 保证请求不丢失

### 8. 配置管理和环境隔离 ⭐⭐⭐⭐

**亮点**: 集中的配置管理, 支持环境变量和默认值

```python
# config.py 集中管理所有配置
def get_mysql_host() -> str:
    return os.getenv("MYSQL_HOST", "localhost")

def get_mysql_password() -> str:
    password = os.getenv("MYSQL_PASSWORD")
    if not password:
        raise ValueError("MYSQL_PASSWORD is required")
    return password
```

**技术价值**:
- 配置集中管理, 易于维护
- 支持环境变量注入, 适配不同环境(开发、测试、生产)
- 敏感信息不硬编码, 提升安全性

### 9. 完善的测试体系 ⭐⭐⭐⭐

**亮点**: 27 个测试用例, 覆盖单元测试、集成测试、端到端测试

```
tests/
├── unit/              # 单元测试: 数据验证、计算逻辑
├── integration/       # 集成测试: 数据库、HTTP、MCP 工具
└── smoke/             # 冒烟测试: 端到端验证
```

**技术价值**:
- 单元测试保证核心逻辑正确性
- 集成测试保证模块间协作正确性
- 端到端测试保证完整链路可用性

### 10. 工程化 DX 固化 ⭐⭐⭐⭐

**亮点**: 统一的启动、测试和代码质量检查入口

```makefile
# 一键启动数据库和服务
make up

# 一键运行测试
make test

# 一键代码质量检查
make lint

# 一键清理
make clean
```

**技术价值**:
- 降低新人上手成本
- 统一开发流程, 减少人为错误
- 支持 CI/CD 集成

---

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

```
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
