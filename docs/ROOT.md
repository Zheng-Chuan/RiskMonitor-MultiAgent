# 文档中心

## 快速开始

- **[快速配置](SETUP.md)** - Docker部署和MCP配置 ⭐
- **[本地开发](QUICKSTART.md)** - 本地开发环境

## 核心文档

- **[系统架构](ARCHITECTURE.md)** - 系统设计
- **[功能说明](FEATURES.md)** - MCP工具
- **[数据库](DATABASE.md)** - 数据库设计
- **[路线图](ROADMAP.md)** - 开发计划
- **[本地开发](QUICKSTART.md)** - 本地开发与验证
- **[快速配置](SETUP.md)** - Docker部署和MCP配置

## 配置示例

```bash
make setup-mcp
```

编辑配置文件 `~/.codeium/windsurf/mcp_config.json`:

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

## 常用命令

```bash
make setup-mcp      # 设置
make mcp-logs       # 日志
make up             # 启动
make down           # 停止
```
