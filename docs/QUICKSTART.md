# 快速开始

## 目标

在本地最短路径启动 RiskMonitor-MCP, 并让 MCP 客户端能调用工具.

## 前置要求

- Python 3.13+
- Docker

## 方式 1: Docker + stdio(推荐本地开发)

1. 启动数据库

```bash
docker-compose up -d mysql
```

2. 安装依赖

```bash
pip install -r requirements.txt
```

3. 启动 MCP server

```bash
python main.py
```

4. 配置 MCP 客户端

以 Windsurf 为例, 配置 `~/.codeium/windsurf/mcp_config.json`.

```json
{
  "mcpServers": {
    "riskMonitor": {
      "command": "python",
      "args": ["/path/to/RiskMonitor-MCP/main.py"]
    }
  }
}
```

## 方式 2: Docker + streamable-http(推荐生产)

说明: 生产部署建议使用 streamable-http, 便于网络访问与水平扩展.

```bash
APP_ENV=production MCP_TRANSPORT=streamable-http FASTMCP_HOST=0.0.0.0 FASTMCP_PORT=8000 python main.py
```

默认 MCP endpoint 通常为:
`http://<host>:<port>/mcp`

## 更多文档

- 文档中心: [ROOT.md](ROOT.md)
- 系统架构: [ARCHITECTURE.md](ARCHITECTURE.md)
- 路线图: [ROADMAP.md](ROADMAP.md)
