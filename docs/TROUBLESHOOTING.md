# 故障排除

## 容器无法启动

```bash
# 查看详细日志
docker-compose logs mysql

# 检查端口占用
lsof -i :3307  # MySQL

# 完全清理后重新启动
docker-compose down -v
docker-compose up -d
```

## 数据库连接失败

1. 确认容器正在运行: `docker-compose ps`
2. 检查 `.env` 文件是否存在且配置正确
3. 等待10秒让MySQL完全启动
4. 查看数据库日志: `docker-compose logs mysql`

## 权限问题

```bash
# 给脚本添加执行权限
chmod +x scripts/test_db_connection.py
```

## 常见错误

### 错误: `Can't connect to MySQL server on 'localhost'`
**解决**: 确保Docker容器正在运行，等待MySQL完全启动

### 错误: `Access denied for user 'admin'`
**解决**: 检查`.env`文件中的密码是否正确

### 错误: `Unknown database 'riskmonitor'`
**解决**: 数据库未正确初始化，重新启动容器

### 错误: `Port 3307 is already in use`
**解决**: 
```bash
# 查找占用端口的进程
lsof -i :3307

# 停止占用端口的进程或修改docker-compose.yml中的端口映射
```

## 测试相关问题

### 错误: `ModuleNotFoundError: No module named 'mcp'`
**解决**: 
```bash
# 确保在正确的虚拟环境中
conda activate MCP
# 或
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 错误: 测试无法连接数据库
**解决**:
```bash
# 检查环境变量
cat .env

# 确保MySQL容器正在运行
docker-compose ps

# 测试数据库连接
python scripts/test_db_connection.py
```

## Docker相关问题

### 容器频繁重启
```bash
# 查看容器日志
docker-compose logs -f mysql

# 检查容器健康状态
docker inspect riskmonitor-mysql | grep -A 10 Health
```

### 磁盘空间不足
```bash
# 清理未使用的Docker资源
docker system prune -a

# 查看Docker磁盘使用
docker system df
```

## 性能问题

### 查询速度慢
```sql
-- 检查是否有缺失的索引
SHOW INDEX FROM positions;

-- 分析查询性能
EXPLAIN SELECT * FROM positions WHERE trader_id = 'TRADER-001';

-- 优化表
OPTIMIZE TABLE positions;
```

### 内存不足
```bash
# 增加Docker内存限制
# 编辑 docker-compose.yml
services:
  mysql:
    mem_limit: 2g
    memswap_limit: 2g
```

## 获取帮助

如果以上方法都无法解决问题:

1. 查看完整日志: `docker-compose logs --tail=100 mysql`
2. 检查系统资源: `docker stats`
3. 提交Issue到GitHub仓库，附上错误日志和环境信息
