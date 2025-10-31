# RiskMonitor-MCP

> **Model Context Protocol (MCP) Server for Financial Derivatives Risk Management**
>
> 将花旗金融衍生品风险计算业务逻辑封装为MCP工具，实现AI驱动的智能风险分析和报表生成

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

详细文档: [docs/README.md](docs/README.md)

---

## 📚 文档

- [快速配置](docs/SETUP.md) - Docker部署和MCP配置
- [本地开发](docs/QUICKSTART.md) - 本地开发环境
- [系统架构](docs/ARCHITECTURE.md) - 系统设计
- [功能说明](docs/FEATURES.md) - MCP工具
- [数据库](docs/DATABASE.md) - 数据库设计
- [测试](docs/TESTING.md) - 测试指南
- [故障排除](docs/TROUBLESHOOTING.md) - 常见问题

### 常用命令

```bash
# MCP服务器
make setup-mcp   # 一键设置MCP服务器
make mcp-logs    # 查看MCP日志
make mcp-shell   # 进入MCP容器

# 容器管理
make build       # 构建Docker镜像
make up          # 启动容器
make down        # 停止容器
make logs        # 查看日志
make clean       # 清理所有容器和数据

# 数据库操作
make test-db     # 测试数据库连接
make shell-db    # 进入MySQL命令行

# 测试
make test-unit   # 运行单元测试
make test-integration  # 运行集成测试
make test-all    # 运行所有测试
```

---

## 项目结构

```
RiskMonitor-MCP/
├── docs/                      # 📚 文档目录
│   ├── QUICKSTART.md         # 快速开始指南
│   ├── ARCHITECTURE.md       # 系统架构
│   ├── FEATURES.md           # 核心功能
│   ├── DATABASE.md           # 数据库设计
│   ├── TESTING.md            # 测试指南
│   ├── ROADMAP.md            # 开发计划
│   └── TROUBLESHOOTING.md    # 故障排除
├── main.py                   # MCP Server主程序
├── docker-compose.yml        # Docker配置
├── requirements.txt          # Python依赖
├── scripts/                  # 工具脚本
│   ├── init_db.sql          # 数据库初始化
│   └── test_db_connection.py # 数据库连接测试
├── tests/                    # 测试用例
│   ├── unit/                # 单元测试
│   └── integration/         # 集成测试
└── Makefile                 # 常用命令
```

---

## 技术栈

- **后端**: Python 3.13+, FastMCP, SQLAlchemy, PyMySQL
- **数据库**: MySQL 8.0
- **容器**: Docker, Docker Compose
- **测试**: pytest, pytest-asyncio
- **数据处理**: NumPy, Pandas

---

## 开发状态

### Phase 1: 最小可运行Demo ✅

- [x] 项目初始化
- [x] Docker环境配置
- [x] MySQL数据库初始化
- [x] 实现4个基础MCP工具
- [x] 测试框架搭建

### Phase 2-5: 进行中 🚧

查看完整开发计划: [开发路线图](docs/ROADMAP.md)

---

## 贡献指南

欢迎贡献！请遵循以下步骤:

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

## 作者

**郑川**

- 哥伦比亚大学硕士 | 兰州大学本科
- 花旗金融信息服务有限公司 - 衍生品风险管理
- 目标: AI Agent开发工程师
- GitHub: [@Zheng-Chuan](https://github.com/Zheng-Chuan)

---

## 致谢

- [Model Context Protocol](https://modelcontextprotocol.io/) - MCP协议规范
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP Server框架
- [QuantLib](https://www.quantlib.org/) - 金融衍生品定价库
- 花旗金融衍生品团队 - 业务知识支持

---

**⭐ 如果这个项目对你有帮助，请给个Star！**
