# 快速配置指南

## 启动服务

```bash
make setup-mcp
```

## 本地开发环境

本项目本地开发与测试默认使用 conda 环境 `MCP`.
如果你在其他解释器里直接运行 `pytest` 或 `python main.py`, 可能会出现 `ModuleNotFoundError: mcp` 之类的报错.

最小自检命令:

```bash
python -c "import sys; print(sys.executable); import mcp; print('mcp_ok')"
```

如果自检失败:

- **优先检查** 当前终端是否已激活 conda 环境 `MCP`
- **其次检查** `pip install -r requirements.txt` 是否是在该环境内执行

## 配置MCP客户端

### 配置文件位置

- **Windsurf**: `~/.codeium/windsurf/mcp_config.json`
- **Claude Desktop (macOS)**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

### 配置内容

```json
{
  "mcpServers": {
    "riskMonitor": {
      "command": "docker",
      "args": [
        "exec",
        "-i",
        "riskmonitor-mcp",
        "python",
        "main.py"
      ],
      "env": {}
    }
  }
}
```

### 重启客户端

完全退出并重启 Windsurf 或 Claude Desktop

## 验证

```bash
# 检查容器
docker ps | grep riskmonitor

# 查看日志
docker logs -f riskmonitor-mcp
```

测试: `请查询所有头寸数据`

## 常用命令

```bash
make mcp-logs       # 查看日志
make mcp-shell      # 进入容器
make up             # 启动
make down           # 停止
make restart        # 重启
make clean          # 清理
```

## 故障排除

```bash
# 检查容器状态
docker ps -a | grep riskmonitor

# 重启服务
docker-compose restart

# 查看日志
docker logs riskmonitor-mcp
```

## MCP工具

- `query_all_positions` - 查询所有头寸
- `query_positions_by_trader` - 按交易员查询
- `query_positions_by_desk` - 按交易台查询
- `calculate_total_delta` - 计算总Delta
