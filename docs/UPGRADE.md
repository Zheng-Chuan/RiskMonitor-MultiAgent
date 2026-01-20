# 升级指南

## 从 RiskMonitor-MCP 升级到 RiskMonitor-MultiAgent

### 变更点

- GitHub 仓库名从 RiskMonitor-MCP 改为 RiskMonitor-MultiAgent
- Python 包名从 riskmonitor_mcp 改为 riskmonitor_multiagent
- docker compose 命令统一使用 docker compose
- MCP server 展示名支持通过 MCP_SERVER_NAME 配置 默认 RiskMonitor MultiAgent

### 你需要做什么

#### 1 更新 git remote

```bash
git remote set-url origin git@github.com:Zheng-Chuan/RiskMonitor-MultiAgent.git
git fetch --all --prune
```

#### 2 更新 import

把代码里所有

- riskmonitor_mcp

替换为

- riskmonitor_multiagent

#### 3 更新本地 MCP 客户端配置

把 MCP 客户端配置里的 main.py 路径指向新的仓库目录

示例

```json
{
  "mcpServers": {
    "riskMonitor": {
      "command": "python",
      "args": ["/path/to/RiskMonitor-MultiAgent/main.py"]
    }
  }
}
```

#### 4 可选 设置 MCP server 展示名

```bash
export MCP_SERVER_NAME="RiskMonitor MultiAgent"
```

