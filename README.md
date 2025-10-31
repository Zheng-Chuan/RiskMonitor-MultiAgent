# RiskMonitor-MCP

> **Model Context Protocol (MCP) Server for Financial Derivatives Risk Management**
> 
> 将花旗金融衍生品风险计算业务逻辑封装为MCP工具，实现AI驱动的智能风险分析和报表生成

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MySQL 8.0](https://img.shields.io/badge/mysql-8.0-orange.svg)](https://www.mysql.com/)
[![MCP](https://img.shields.io/badge/MCP-1.12.4+-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 📑 目录

- [项目概述](#项目概述)
  - [业务背景](#业务背景)
  - [MCP解决方案](#mcp解决方案)
- [系统架构](#系统架构)
  - [整体数据流](#整体数据流)
  - [技术栈](#技术栈)
- [核心功能](#核心功能)
  - [数据模拟层](#数据模拟层)
  - [MCP工具集](#mcp工具集)
  - [典型工作流](#典型工作流)
- [快速开始](#快速开始)
  - [环境要求](#环境要求)
  - [安装步骤](#安装步骤)
  - [验证安装](#验证安装)
- [使用指南](#使用指南)
  - [启动服务](#启动服务)
  - [配置Claude Desktop](#配置claude-desktop)
  - [常用命令](#常用命令)
- [数据库设计](#数据库设计)
- [开发计划](#开发计划)
- [故障排除](#故障排除)
- [项目价值](#项目价值)
- [贡献指南](#贡献指南)
- [许可证](#许可证)
- [作者](#作者)

---

## 项目概述

### 业务背景

在花旗金融衍生品交易组，业务流程如下：

```
交易员交易 → 量化组计算风险 → 风险数据入库 → 风险分析计算 → 生成报表 → Risk Manager + 数据湖
```

**传统方式的痛点**：
- 风险计算逻辑分散在多个脚本和系统中
- 业务人员需要懂SQL和编程才能查询分析
- 报表生成流程固化，难以灵活调整
- 新需求开发周期长，响应慢

### MCP解决方案

- 将所有风险计算逻辑封装为标准化的MCP工具
- Risk Manager通过自然语言即可调用复杂计算
- AI Agent自动编排多个工具完成分析任务
- 灵活生成各类定制化报表

---

## 系统架构

### 整体数据流

```
┌─────────────────┐
│  Trading Desk   │  交易员执行交易（股票、期权、互换等）
└────────┬────────┘
         │ Trade Data
         ↓
┌─────────────────┐
│  Quant Team     │  计算风险指标（Delta, Gamma, Vega, CVA等）
└────────┬────────┘
         │ Risk Metrics
         ↓
┌─────────────────────────────────────────────────────────┐
│              MySQL Database (Port 3306)                 │
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

### 技术栈

**后端**:
- Python 3.13+
- FastMCP - MCP Server框架
- SQLAlchemy - 数据库ORM
- PyMySQL - MySQL数据库驱动

**数据库**:
- MySQL 8.0 - 关系数据库
- Docker - 容器化部署

**数据处理**:
- NumPy/Pandas - 数值计算和数据处理
- QuantLib (可选) - 金融衍生品定价库

**报表生成**:
- OpenPyXL - Excel报表
- ReportLab (可选) - PDF报表
- Plotly (可选) - 可视化图表

---

## 核心功能

### 数据模拟层

**目的**：模拟真实的交易头寸数据流入关系数据库

#### 模拟数据结构

**Positions 表**：
```python
{
    "position_id": "POS-2024-001",
    "trader_id": "TRADER-001",
    "desk": "Equity Derivatives",
    "security_id": "AAPL-CALL-150-20251231",
    "quantity": 1000,
    "delta": 600.0,
    "entry_date": "2024-10-01",
    "currency": "USD"
}
```

#### 模拟场景

1. **单一期权头寸** - 买入AAPL看涨期权，计算Greeks和CVA
2. **复合策略头寸** - 跨式期权(Straddle)、价差策略(Spread)
3. **多币种头寸** - EUR、JPY、GBP期权，需要Dollarization
4. **对手方风险** - 不同交易对手，CVA计算

### MCP工具集

#### 1. 头寸查询工具
- `query_positions_by_trader` - 查询特定交易员的所有头寸
- `query_positions_by_desk` - 查询整个交易台的头寸
- `query_positions_by_security` - 查询特定证券的所有头寸

#### 2. Greeks计算工具
- `calculate_portfolio_greeks` - Portfolio级别风险度量
- `calculate_greeks_by_underlying` - 按标的资产分组的Greeks
- `calculate_delta_hedge_requirement` - 对冲策略建议

#### 3. CVA计算工具
- `calculate_cva_by_counterparty` - 对手方信用风险评估
- `calculate_cva_change` - CVA风险归因分析
- `simulate_cva_stress` - 压力测试

#### 4. 风险聚合工具
- `aggregate_risk_by_desk` - 管理层风险报告
- `aggregate_risk_by_asset_class` - 资产配置分析
- `dollarize_multi_currency_positions` - 跨币种风险统一度量

#### 5. 限额检查工具
- `check_greeks_limits` - 实时风险监控
- `check_concentration_limits` - 防止过度集中
- `generate_limit_breach_alert` - 自动告警

#### 6. 报表生成工具
- `generate_daily_risk_report` - 每日风险报告
- `generate_pnl_attribution_report` - 绩效分析
- `generate_regulatory_report` - 合规报送

#### 7. 压力测试工具
- `run_market_stress_test` - 极端情景分析
- `run_historical_scenario` - 历史情景回测

#### 8. 场景分析工具
- `analyze_what_if_scenario` - 假设分析
- `optimize_portfolio_for_target_greeks` - Portfolio优化

### 典型工作流

#### 场景1：Risk Manager早晨风险检查

**自然语言请求**：
> "给我看看昨天股票衍生品交易台的整体风险情况，特别关注Delta和Vega暴露，以及是否有超限的情况"

**MCP工具调用链**：
```
1. query_positions_by_desk(desk="Equity Derivatives", date="2024-10-30")
2. calculate_portfolio_greeks(desk="Equity Derivatives")
3. check_greeks_limits(desk="Equity Derivatives")
4. generate_daily_risk_report(date="2024-10-30", scope="desk")
```

**输出**：Excel报表，包含所有头寸、Greeks汇总、限额使用情况

#### 场景2：CVA团队对手方风险分析

**自然语言请求**：
> "分析一下对手方XYZ Bank的信用风险，计算我们的CVA暴露，并模拟如果他们的信用评级从A降到BBB会怎样"

**MCP工具调用链**：
```
1. query_positions_by_counterparty(counterparty="XYZ Bank")
2. calculate_cva_by_counterparty(counterparty="XYZ Bank")
3. simulate_cva_stress(counterparty="XYZ Bank", rating_change="A_to_BBB")
4. generate_cva_report(counterparty="XYZ Bank")
```

**输出**：
- 当前CVA：$6,000
- 评级下降后CVA：$30,000
- CVA增加：$24,000
- 建议：考虑买入CDS对冲

---

## 快速开始

### 环境要求

- Python 3.13+
- Docker & Docker Compose
- Git

### 安装步骤

#### Step 1: 克隆项目

```bash
git clone https://github.com/yourusername/RiskMonitor-MCP.git
cd RiskMonitor-MCP
```

#### Step 2: 配置环境变量

```bash
cp .env.example .env
```

#### Step 3: 启动MySQL容器

```bash
docker-compose up -d
```

等待约10秒让MySQL完全启动。

#### Step 4: 创建Python虚拟环境

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
source .venv/bin/activate  # macOS/Linux
# 或
.venv\Scripts\activate  # Windows
```

#### Step 5: 安装Python依赖

```bash
pip install -r requirements.txt
```

#### Step 6: 测试数据库连接

```bash
python scripts/test_db_connection.py
```

如果看到 `✓ All tests passed!`，说明环境搭建成功！

### 验证安装

#### 检查容器状态

```bash
docker-compose ps
```

应该看到：
- `riskmonitor-mysql` - Up (healthy)

#### 检查数据库

```bash
# 方式1: 使用测试脚本
python scripts/test_db_connection.py

# 方式2: 直接连接数据库
docker-compose exec mysql mysql -u admin -priskmonitor2024 riskmonitor

# 在MySQL中执行
SHOW TABLES;                  # 查看所有表
SELECT * FROM positions;      # 查看数据
EXIT;                         # 退出
```

---

## 使用指南

### 启动服务

#### 使用Makefile（推荐）

```bash
make help        # 查看所有命令
make up          # 启动容器
make down        # 停止容器
make restart     # 重启容器
make logs        # 查看日志
make test-db     # 测试数据库连接
make shell-db    # 进入MySQL命令行
make clean       # 清理所有容器和数据卷
```

#### 直接使用Docker Compose

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 查看日志
docker-compose logs -f mysql

# 重启单个服务
docker-compose restart mysql

# 进入MySQL容器
docker-compose exec mysql mysql -u admin -priskmonitor2024 riskmonitor
```

### 配置Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "riskmonitor": {
      "command": "python",
      "args": ["/path/to/RiskMonitor-MCP/main.py"]
    }
  }
}
```

Windows路径：`%APPDATA%\Claude\claude_desktop_config.json`

### 常用命令

#### 数据库操作

```bash
# 测试连接
make test-db

# 进入MySQL命令行
make shell-db

# 查看表结构
docker-compose exec mysql mysql -u admin -priskmonitor2024 -e "DESCRIBE riskmonitor.positions;"

# 查看数据
docker-compose exec mysql mysql -u admin -priskmonitor2024 -e "SELECT * FROM riskmonitor.positions LIMIT 5;"
```

#### 容器管理

```bash
# 查看容器状态
docker-compose ps

# 查看容器日志
docker-compose logs -f

# 重启容器
docker-compose restart

# 完全清理（删除数据）
docker-compose down -v
```

#### 可选：启动phpMyAdmin管理界面

```bash
docker-compose --profile tools up -d
```

访问 http://localhost:8080
- 服务器：mysql
- 用户名：admin
- 密码：riskmonitor2024

---

## 数据库设计

### 核心表结构

#### Positions 表

```sql
CREATE TABLE positions (
    position_id VARCHAR(50) PRIMARY KEY,
    trader_id VARCHAR(50) NOT NULL,
    desk VARCHAR(100) NOT NULL,
    security_id VARCHAR(100) NOT NULL,
    quantity DECIMAL(18, 4) NOT NULL,
    delta DECIMAL(18, 4),
    entry_date DATE NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### Securities 表

```sql
CREATE TABLE securities (
    security_id VARCHAR(100) PRIMARY KEY,
    security_type VARCHAR(50) NOT NULL,  -- Stock, Option, Swap, Bond
    underlying VARCHAR(20),
    option_type VARCHAR(10),  -- Call / Put
    strike DECIMAL(18, 4),
    expiry_date DATE,
    currency VARCHAR(3) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### Risk_Metrics 表

```sql
CREATE TABLE risk_metrics (
    metric_id INT AUTO_INCREMENT PRIMARY KEY,
    position_id VARCHAR(50) NOT NULL,
    calculation_date DATE NOT NULL,
    delta DECIMAL(18, 4),
    gamma DECIMAL(18, 4),
    vega DECIMAL(18, 4),
    theta DECIMAL(18, 4),
    rho DECIMAL(18, 4),
    cva DECIMAL(18, 2),
    usd_equivalent DECIMAL(18, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (position_id) REFERENCES positions(position_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

#### Risk_Limits 表

```sql
CREATE TABLE risk_limits (
    limit_id INT AUTO_INCREMENT PRIMARY KEY,
    scope VARCHAR(50) NOT NULL,  -- Trader / Desk / Firm
    scope_id VARCHAR(100) NOT NULL,
    limit_type VARCHAR(50) NOT NULL,  -- Delta / Gamma / Vega / CVA
    limit_value DECIMAL(18, 2) NOT NULL,
    effective_date DATE NOT NULL,
    expiry_date DATE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 开发计划

采用**最小可运行demo → 逐步扩充**的策略，从简单到复杂逐步构建系统。

### Phase 1: 最小可运行Demo

**目标**：实现一个端到端的简单功能，验证技术可行性

- [x] 项目初始化
- [x] Docker环境配置
- [x] MySQL数据库初始化
- [ ] MCP Server基础框架
- [ ] 实现第一个工具：`query_all_positions`
- [ ] 实现第二个工具：`calculate_total_delta`
- [ ] Claude Desktop集成测试

**验收标准**：
- 数据库正常运行
- MCP Server能启动
- Claude Desktop能调用至少2个工具
- 端到端流程跑通

### Phase 2: 完善数据模型

**目标**：建立完整的数据库表结构和模拟数据

- [ ] 创建完整的4张表
- [ ] 编写数据生成脚本
- [ ] 生成50-100条模拟数据
- [ ] 实现3个查询工具
- [ ] 添加日期范围过滤

**验收标准**：
- 4张核心表全部创建
- 有足够的模拟数据支持测试
- 3个查询工具都能正常工作

### Phase 3: Greeks计算引擎

**目标**：实现Greeks计算和风险聚合功能

- [ ] Portfolio Greeks聚合计算
- [ ] 按标的分组Greeks
- [ ] Delta对冲建议
- [ ] 按交易台聚合
- [ ] 多币种转换(Dollarization)
- [ ] 限额检查
- [ ] 单元测试

**验收标准**：
- Greeks计算准确
- 支持多维度聚合
- 限额检查功能正常

### Phase 4: CVA和高级功能

**目标**：实现CVA计算和压力测试

- [ ] 对手方数据和CVA计算
- [ ] CVA变化分析
- [ ] 信用利差压力测试
- [ ] 市场压力测试
- [ ] 历史情景回测
- [ ] 假设分析
- [ ] 集成测试

**验收标准**：
- CVA计算逻辑正确
- 压力测试能运行
- 所有核心功能集成测试通过

### Phase 5: 报表生成和系统优化

**目标**：实现专业报表生成和系统优化

- [ ] Excel日度风险报告
- [ ] 盈亏归因报告
- [ ] 监管报送报告
- [ ] 图表可视化
- [ ] 数据库查询优化
- [ ] 日志和监控
- [ ] 错误处理
- [ ] 文档完善

**验收标准**：
- 能生成专业Excel/PDF报表
- 查询响应时间 < 1秒
- 代码质量达到生产级别

---

## 故障排除

### 容器无法启动

```bash
# 查看详细日志
docker-compose logs mysql

# 检查端口占用
lsof -i :3306  # MySQL

# 完全清理后重新启动
docker-compose down -v
docker-compose up -d
```

### 数据库连接失败

1. 确认容器正在运行: `docker-compose ps`
2. 检查 `.env` 文件是否存在且配置正确
3. 等待10秒让MySQL完全启动
4. 查看数据库日志: `docker-compose logs mysql`

### 权限问题

```bash
# 给脚本添加执行权限
chmod +x scripts/test_db_connection.py
```

### 常见错误

**错误**: `Can't connect to MySQL server on 'localhost'`
- **解决**: 确保Docker容器正在运行，等待MySQL完全启动

**错误**: `Access denied for user 'admin'`
- **解决**: 检查`.env`文件中的密码是否正确

**错误**: `Unknown database 'riskmonitor'`
- **解决**: 数据库未正确初始化，重新启动容器

---

## 项目价值

### 对团队的价值

1. **效率提升**
   - Risk Manager无需编写SQL，自然语言即可查询
   - 报表生成从数小时缩短到数分钟
   - 减少90%的重复性手工工作

2. **风险管理增强**
   - 实时风险监控和告警
   - 灵活的压力测试和场景分析
   - 更快的风险响应速度

3. **合规性改善**
   - 标准化的监管报送流程
   - 完整的审计追踪
   - 降低合规风险

4. **知识沉淀**
   - 业务逻辑代码化、标准化
   - 新人培训成本降低
   - 知识不再依赖个人

### 对个人简历的价值

1. **技术亮点**
   - MCP协议实战应用（前沿技术）
   - AI Agent与金融业务深度结合
   - 分布式系统和大规模数据处理

2. **业务深度**
   - FRTB、CVA等复杂金融概念
   - 真实的银行风险管理流程
   - 监管合规经验

3. **影响力**
   - 提升团队效率的实际案例
   - 可量化的业务价值
   - 创新性解决方案

---

## 贡献指南

欢迎贡献！请遵循以下步骤：

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

### 开发建议

1. **每完成一个Phase就提交Git** - 保持代码可回溯
2. **边开发边写测试** - 避免后期bug堆积
3. **保持README更新** - 记录问题和解决方案
4. **定期Demo** - 录制演示视频用于展示
5. **代码质量** - 使用类型提示、添加docstring、遵循PEP 8

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 作者

**郑川**
- 哥伦比亚大学硕士 | 兰州大学本科
- 花旗金融信息服务有限公司 - 衍生品风险管理
- 目标：AI Agent开发工程师
- GitHub: [@your-github](https://github.com/your-github)

---

## 致谢

- [Model Context Protocol](https://modelcontextprotocol.io/) - MCP协议规范
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP Server框架
- [QuantLib](https://www.quantlib.org/) - 金融衍生品定价库
- 花旗金融衍生品团队 - 业务知识支持

---

**⭐ 如果这个项目对你有帮助，请给个Star！**
