# RiskMonitor-MCP

## 项目概述

在花旗金融衍生品交易组，传统的风险计算逻辑分散在多个脚本和系统中，业务人员需要懂SQL和编程才能查询分析。本项目将所有风险计算逻辑封装为标准化的MCP工具，Risk Manager通过自然语言即可调用复杂计算，AI Agent自动编排多个工具完成分析任务。

### 核心特性

- **8大MCP工具集**: 头寸查询、Greeks计算、CVA计算、风险聚合、限额检查、报表生成、压力测试、场景分析
- **模拟真实数据**: 15条多资产类别头寸数据(股票、期权、债券、商品、信用衍生品)
- **容器化部署**: Docker + MySQL 8.0，支持本地开发和Kubernetes生产部署
- **完整测试框架**: 单元测试 + 集成测试，确保代码质量

---

## 文档目录

- [docs/ROOT.md](docs/ROOT.md)
- [docs/QUICKSTART.md](docs/QUICKSTART.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DATA.md](docs/DATA.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [docs/INTERVIEW.md](docs/INTERVIEW.md) - MCP 完整面试指南(含 70 个硬核面试题)

---
