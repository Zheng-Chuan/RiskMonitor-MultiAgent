# RiskMonitor-MCP

> **Model Context Protocol (MCP) Server for Financial Derivatives Risk Management**
>
> 将金融衍生品风险计算业务逻辑封装为MCP工具，实现AI驱动的智能风险分析和报表生成

[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![MySQL 8.0](https://img.shields.io/badge/mysql-8.0-orange.svg)](https://www.mysql.com/)
[![MCP](https://img.shields.io/badge/MCP-1.12.4+-green.svg)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 项目概述

在花旗金融衍生品交易组，传统的风险计算逻辑分散在多个脚本和系统中，业务人员需要懂SQL和编程才能查询分析。本项目将所有风险计算逻辑封装为标准化的MCP工具，Risk Manager通过自然语言即可调用复杂计算，AI Agent自动编排多个工具完成分析任务。

### 核心特性

- **8大MCP工具集**: 头寸查询、Greeks计算、CVA计算、风险聚合、限额检查、报表生成、压力测试、场景分析
- **模拟真实数据**: 15条多资产类别头寸数据(股票、期权、债券、商品、信用衍生品)
- **容器化部署**: Docker + MySQL 8.0，支持本地开发和Kubernetes生产部署
- **完整测试框架**: 单元测试 + 集成测试，确保代码质量

---

## 快速开始

### 方式1: Docker部署 (推荐)

```bash
# 1. 克隆项目
git clone https://github.com/Zheng-Chuan/RiskMonitor-MCP.git
cd RiskMonitor-MCP

# 2. 一键启动
make setup-mcp

# 3. 配置MCP客户端
# 编辑 ~/.codeium/windsurf/mcp_config.json 或
# ~/Library/Application Support/Claude/claude_desktop_config.json
# 添加以下配置:
```

```json
{
  "mcpServers": {
    "riskMonitor": {
      "command": "docker",
      "args": ["exec", "-i", "riskmonitor-mcp", "python", "main.py"]
    }
  }
}
```

### 方式2: 本地开发

```bash
# 1. 启动MySQL容器
docker-compose up -d mysql

# 2. 安装Python依赖
pip install -r requirements.txt

# 3. 测试数据库连接
python scripts/test_db_connection.py

# 4. 运行MCP服务器
python main.py
```

### 方式3: 生产部署 Streamable HTTP

说明:
本地开发与测试建议使用 stdio
生产部署建议使用 streamable-http, 便于网络访问, 无状态部署与水平扩展

启动方式示例:
```bash
MCP_TRANSPORT=streamable-http FASTMCP_HOST=0.0.0.0 FASTMCP_PORT=8000 python main.py
```

默认 MCP endpoint 通常为:
`http://<host>:<port>/mcp`

详细文档: [docs/ROOT.md](docs/ROOT.md)
