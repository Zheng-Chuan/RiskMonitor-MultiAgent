# 快速开始

## 环境要求

- Python 3.13+
- Docker & Docker Compose
- Git

## 安装步骤

### Step 1: 克隆项目

```bash
git clone https://github.com/Zheng-Chuan/RiskMonitor-MCP.git
cd RiskMonitor-MCP
```

### Step 2: 配置环境变量

```bash
cp .env.example .env
```

### Step 3: 启动MySQL容器

```bash
docker-compose up -d
```

等待约10秒让MySQL完全启动。

### Step 4: 创建Python虚拟环境

```bash
# 使用 conda 环境 MCP
conda activate MCP
```

### Step 5: 安装Python依赖

```bash
pip install -r requirements.txt
```

### Step 6: 测试数据库连接

```bash
python tests/diagnostics/db_connection_check.py
```

如果看到 `✓ All tests passed!`，说明环境搭建成功！

## 验证安装

### 检查容器状态

```bash
docker-compose ps
```

应该看到:
- `riskmonitor-mysql` - Up (healthy)

### 检查数据库

```bash
# 方式1: 使用测试脚本
python tests/diagnostics/db_connection_check.py

# 方式2: 直接连接数据库
docker-compose exec mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"'

# 在MySQL中执行
SHOW TABLES;                  # 查看所有表
SELECT * FROM positions;      # 查看数据
EXIT;                         # 退出
```

## 使用指南

### 启动服务

#### 使用Makefile(推荐)

```bash
make help        # 查看所有命令
make up          # 启动容器
make down        # 停止容器
make restart     # 重启容器
make logs        # 查看日志
make test-db     # 测试数据库连接
make shell-db    # 进入MySQL命令行
make clean       # 清理所有容器和数据卷
```

#### 直接使用Docker Compose

```bash
# 启动
docker-compose up -d

# 停止
docker-compose down

# 查看日志
docker-compose logs -f mysql

# 重启单个服务
docker-compose restart mysql

# 进入MySQL容器
docker-compose exec mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" "$${MYSQL_DATABASE}"'
```

### 配置Claude Desktop

编辑 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "riskmonitor": {
      "command": "python",
      "args": ["/path/to/RiskMonitor-MCP/main.py"]
    }
  }
}
```

Windows路径: `%APPDATA%\Claude\claude_desktop_config.json`

### 常用命令

#### 数据库操作

```bash
# 测试连接
make test-db

# 进入MySQL命令行
make shell-db

# 查看表结构
docker-compose exec mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" -e "DESCRIBE $${MYSQL_DATABASE}.positions;"'

# 查看数据
docker-compose exec mysql sh -lc 'mysql -u "$${MYSQL_USER}" -p"$${MYSQL_PASSWORD}" -e "SELECT * FROM $${MYSQL_DATABASE}.positions LIMIT 5;"'
```

#### 容器管理

```bash
# 查看容器状态
docker-compose ps

# 查看容器日志
docker-compose logs -f

# 重启容器
docker-compose restart

# 完全清理(删除数据)
docker-compose down -v
```

#### 可选: 启动phpMyAdmin管理界面

```bash
docker-compose --profile tools up -d
```

访问 http://localhost:8080
- 服务器: mysql
- 用户名: admin
