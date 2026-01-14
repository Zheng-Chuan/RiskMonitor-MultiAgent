# 快速开始

## 目标

在本地最短路径启动 RiskMonitor-MCP 并让 MCP 客户端能调用工具

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
- Kafka Debezium 等事件驱动组件在 Docker

后续 Week5 Week6 会引入 Kafka 和 binlog CDC 相关组件 并同样放在 Docker

你需要准备以下环境变量

- MYSQL_ROOT_PASSWORD
- MYSQL_DATABASE
- MYSQL_USER
- MYSQL_PASSWORD

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
docker-compose up -d mysql
```

MySQL 端口映射默认是 3307 -> 3306

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

如果你希望跑覆盖率

```bash
make test-cov
```

如果你希望在 Docker 里跑 tests 也可以

```bash
docker-compose --profile dev run --rm test-runner
```

### 5 运行 pylint 作为交付前检查

```bash
make lint
```

如果你希望在 Docker 里跑 pylint 也可以

```bash
docker-compose --profile dev run --rm lint-runner
```

### 6 配置 MCP 客户端

以 Windsurf 为例 配置 `~/.codeium/windsurf/mcp_config.json`

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

如果你希望用 streamable http 连接 MCP

- MCP endpoint: <http://127.0.0.1:8000/mcp>

## 方式 2: docker compose 运行 MCP server

如果你希望本地也使用和 k8s 更接近的形态 可以直接起容器

```bash
docker-compose up -d mcp-server
```

默认端口

- MCP server: <http://127.0.0.1:8000>
- MCP endpoint: <http://127.0.0.1:8000/mcp>
- health: <http://127.0.0.1:8000/health>
- ready: <http://127.0.0.1:8000/ready>
- metrics: <http://127.0.0.1:8000/metrics>

如果你想看数据库界面

```bash
docker-compose --profile tools up -d
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

## Web 前端选型 python only

目标

- 只写 python
- 布局灵活 风格多样 页面要漂亮
- 需要支持登录与权限认证

选型建议

- 服务端: FastAPI
- 模板: Jinja2
- 交互: HTMX
- 样式: Tailwind CSS CDN 或 Bootstrap CDN

推荐的美观策略

- Tailwind 适合做布局灵活的页面
- Bootstrap 适合快速做出稳定统一的页面
- 你可以按页面模块选择不同风格 但保持组件边界清晰

理由

- 无需引入前端构建链 跟 python 项目集成成本低
- HTMX 可以实现丰富交互 但你不用写 JavaScript
- Tailwind 可以快速做出不同风格的页面布局

落地位置

- Web 门户会在 ROADMAP 的 Week 7 plus 交付
- 该 Web 服务也将承接 webhook 接收 与 MCP tools 调用编排

## 更多文档

- 文档中心: [ROOT.md](ROOT.md)
- 系统架构: [ARCHITECTURE.md](ARCHITECTURE.md)
- 路线图: [ROADMAP.md](ROADMAP.md)
