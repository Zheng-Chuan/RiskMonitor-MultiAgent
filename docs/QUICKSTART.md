# 快速开始

## 目标

在本地最短路径启动服务并完成功能验收

## 前置要求

- Python 3.13+
- Docker

## 必要环境变量

- MYSQL_HOST
- MYSQL_PORT
- MYSQL_DATABASE
- MYSQL_USER
- MYSQL_PASSWORD

可选环境变量

- OPENROUTER_API_KEY
- OPENROUTER_MODEL
- OPENROUTER_BASE_URL
- DISABLE_LLM
- MCP_SERVER_NAME
- MCP_TRANSPORT

## 推荐启动方式 本地运行服务 Docker承载依赖

### 1 启动 MySQL

```bash
docker compose up -d mysql
```

### 2 安装依赖

```bash
pip install -r requirements.txt
```

### 3 启动 MCP 服务

```bash
python main.py
```

### 4 运行验收测试

```bash
make test-all
pytest tests/smoke/ -v --tb=short
```

## 常用开发命令

```bash
make test-db
make test-unit
make test-integration
make test-cov
```

## 知识库能力 可选

```bash
make up-kb
make ingest-knowledge
make kb-query QUERY="desk Equity Derivatives breach" TOP_K=5
```

## 评测与质量闸门

```bash
make eval-run RUN_TAG=baseline
make eval-gate RUN_TAG=baseline
make eval-compare BASE=baseline CAND=candidate
```

更详细指标说明见 [../EVALUATION.md](../EVALUATION.md)

## MCP 客户端配置示例

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

## 相关文档

- 项目总入口: [../README.md](../README.md)
- 系统架构: [ARCHITECTURE.md](./ARCHITECTURE.md)
- 路线图: [ROADMAP.md](./ROADMAP.md)
- 评测手册: [../EVALUATION.md](../EVALUATION.md)
