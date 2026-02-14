# RiskMonitor-MultiAgent

## 项目概述

在花旗金融衍生品交易组 传统的风险计算逻辑分散在多个脚本和系统中 业务人员需要懂SQL和编程才能查询分析 本项目将所有风险计算逻辑封装为标准化的MCP工具 Risk Manager通过自然语言即可调用复杂计算 AI Agent自动编排多个工具完成分析任务

### 核心特性

- **MCP 工具集(已落地)**: 头寸查询 交易台敞口监控 组合 Delta 汇总 告警写入与查询 运行指标查询
- **服务化形态(已落地)**: stdio 与 streamable-http 两种传输方式 提供 health/ready/metrics 端点
- **告警闭环最小版(已落地)**: desk delta breach 规则评估 告警持久化与查询
- **LLM Provider 适配(已落地)**: OpenRouter 客户端封装模块 供后续分析/worker 调用
- **容器化部署**: Docker + MySQL 8.0 支持本地开发与类生产形态
- **完整测试框架**: 单元测试 + 集成测试 + smoke test 作为唯一验收标准

---

## 文档目录

- [docs/QUICKSTART.md](docs/QUICKSTART.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/STATE_MACHINE.md](docs/STATE_MACHINE.md)
- [docs/DATA.md](docs/DATA.md)
- [docs/ROADMAP.md](docs/ROADMAP.md)
- [docs/INTERVIEW.md](docs/INTERVIEW.md) - MCP 完整面试指南(含 70 个硬核面试题)

---
