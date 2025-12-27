# 系统架构和技术特点

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
