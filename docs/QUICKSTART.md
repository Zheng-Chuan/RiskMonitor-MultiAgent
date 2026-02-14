# 快速开始

## 目标

在本地最短路径启动 RiskMonitor-MultiAgent 并让 MCP 客户端能调用工具

交付与验收原则

- 以 tests 作为唯一硬标准
- 本地开发与测试依赖组件统一使用 Docker

## 前置要求

- Python 3.13+
- Docker

说明

- 本仓库通过 docker compose 提供 MySQL 容器
- 如果你已经有独立的 MySQL 容器 也可以复用 只需要确保环境变量正确

本地依赖组件

- MySQL 在 Docker
- Kafka Debezium Schema Registry 等 CDC 组件在 Docker(Week 6)

你需要准备以下环境变量

- MYSQL_ROOT_PASSWORD
- MYSQL_DATABASE
- MYSQL_USER
- MYSQL_PASSWORD

如果你需要在服务端直接调用 LLM(通过 OpenRouter)

- OPENROUTER_API_KEY
- OPENROUTER_MODEL (可选, 默认值见 src/riskmonitor_multiagent/config.py)
- OPENROUTER_BASE_URL (可选, 默认 https://openrouter.ai/api/v1)
- OPENROUTER_HTTP_REFERER (可选, 用于 OpenRouter 统计)
- OPENROUTER_APP_TITLE (可选, 用于 OpenRouter 统计)

如果你需要自定义知识库向量库连接(Week 8)

- CHROMA_HOST (可选, 默认 localhost)
- CHROMA_PORT (可选, 默认 8001)
- CHROMA_COLLECTION (可选, 默认 riskmonitor-alerts)

说明

- 当前仓库仅提供 OpenRouter 客户端封装模块, 供服务端/worker 在业务流程内直接调用
- 暂未将 LLM 调用注册为 MCP tool, 以避免把上游调用策略耦合到工具层

建议你先验证连通性

- 方式 A 使用 make test-db
- 方式 B 在 python 进程启动后访问 ready endpoint
  - <http://127.0.0.1:8000/ready>

建议方式

- 在 shell 里 export 这些变量
- 或者使用你本地的方式注入到 docker compose

## 方式 1 推荐 本地运行 MCP 服务 依赖用 Docker

### 1 启动 MySQL

```bash
docker compose up -d mysql
```

MySQL 端口映射默认是 3307 -> 3306

如果你准备做 Week 6 的 CDC 链路(可选)

```bash
make up-infra
```

服务端口

- Kafka UI: <http://127.0.0.1:8081>
- Debezium Connect: <http://127.0.0.1:8083>
- Schema Registry: <http://127.0.0.1:8085>

注册 Debezium positions connector(输出到 topic `risk.positions.cdc`)

```bash
make register-cdc
```

注册 positions CDC JSON Schema(可选)

```bash
./scripts/schema_registry/register_positions_cdc_schema.sh
```

### 2 安装依赖

```bash
pip install -r requirements.txt
```

### 3 启动 MCP server

```bash
python main.py
```

### 4 运行 tests 作为验收

```bash
make test
```

如果你希望把数据库变化推送到 Sentinel 并触发多智能体流水线(Week 7)

```bash
make run-sentinel
```

说明

- Kafka 对宿主机暴露的端口是 29092
- Sentinel 默认连接 localhost:29092 并订阅 risk.positions.cdc
- 如果 OpenRouter 模型不可用或返回 404 系统会自动走 fallback 保证链路可跑通 你可以在 .env 里覆盖 OPENROUTER_MODEL
- 如果你希望启用状态机编排 设置 ENABLE_LANGGRAPH=1
- 如果你希望本地默认自动审批 设置 HITL_AUTO_APPROVE=1
- Week11 增加工具治理 side_effect 写库动作必须审批 Manager 才能执行

如果你希望让 Agent 具备知识库检索能力(Week 8)

先启动向量数据库

```bash
make up-kb
```

再把最近的 alerts 写入向量库

```bash
make ingest-knowledge
```

然后你可以用 CLI 验证检索

```bash
make kb-query QUERY="desk Equity Derivatives breach" TOP_K=5
```

再在 MCP 客户端里调用 tool

- search_similar_alerts query="desk Equity Derivatives breach" top_k=5

如果你希望跑覆盖率

```bash
make test-cov
```

如果你希望在 Docker 里跑 tests 也可以

```bash
docker compose --profile dev run --rm test-runner
```

### 5 配置 MCP 客户端

以 Windsurf 为例 配置 `~/.codeium/windsurf/mcp_config.json`

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

如果你希望 MCP 客户端侧显示的 server 名字更明确

- 设置环境变量 MCP_SERVER_NAME=RiskMonitor MultiAgent
- 或者在 `.env` 里配置 MCP_SERVER_NAME

如果你希望用 streamable http 连接 MCP

- MCP endpoint: <http://127.0.0.1:8000/mcp>

## 方式 2: docker compose 运行 MCP server

如果你希望本地也使用和 k8s 更接近的形态 可以直接起容器

```bash
docker compose up -d mcp-server
```

默认端口

- MCP server: <http://127.0.0.1:8000>
- MCP endpoint: <http://127.0.0.1:8000/mcp>
- health: <http://127.0.0.1:8000/health>
- ready: <http://127.0.0.1:8000/ready>
- metrics: <http://127.0.0.1:8000/metrics>

如果你想看数据库界面

```bash
docker compose --profile tools up -d
```

## 方式 3 复用你已有的 MySQL 容器

如果你已经有一个 docker 里的 MySQL 供这个项目使用 你可以不启动本仓库的 mysql 服务

你需要确保以下环境变量指向正确的 MySQL 地址

- MYSQL_HOST
- MYSQL_PORT
- MYSQL_DATABASE
- MYSQL_USER
- MYSQL_PASSWORD

然后本地直接运行

```bash
python main.py
```

## 更多文档

- 项目总入口: [../README.md](../README.md)
- 系统架构: [ARCHITECTURE.md](ARCHITECTURE.md)
- 路线图: [ROADMAP.md](ROADMAP.md)
