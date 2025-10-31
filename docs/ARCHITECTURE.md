# 系统架构

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

## 技术栈

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
