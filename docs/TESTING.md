# 测试指南

## 📋 测试结构

```
tests/
├── unit/                      # 单元测试（不需要Docker）
│   └── test_data_validation.py
├── integration/               # 集成测试（需要Docker）
│   ├── test_database.py
│   └── test_mcp_tools.py
└── __init__.py
```

## 🚀 快速开始

### 1. 运行所有测试

```bash
make test
```

### 2. 分别运行不同类型的测试

```bash
# 测试数据库连接
make test-db

# 运行单元测试（快速，不需要Docker）
make test-unit

# 运行集成测试（需要Docker运行）
make test-integration
```

---

## 📝 测试类型说明

### 单元测试 (Unit Tests)

**特点**：
- ✅ 快速执行
- ✅ 不需要外部依赖
- ✅ 测试纯逻辑

**测试内容**：
- 数据格式验证
- 计算逻辑
- 输入验证

**运行方式**：
```bash
pytest tests/unit/ -v
```

---

### 集成测试 (Integration Tests)

**特点**：
- 🐳 需要Docker容器运行
- 🔗 测试真实数据库交互
- 📊 测试MCP工具端到端

**测试内容**：
- 数据库连接
- SQL查询
- MCP工具函数

**运行方式**：
```bash
# 确保Docker容器运行
docker-compose up -d

# 运行集成测试
pytest tests/integration/ -v
```

---

## 🔍 详细测试命令

### 运行特定测试文件

```bash
# 测试数据验证
pytest tests/unit/test_data_validation.py -v

# 测试数据库操作
pytest tests/integration/test_database.py -v

# 测试MCP工具
pytest tests/integration/test_mcp_tools.py -v
```

### 运行特定测试函数

```bash
# 只测试Delta计算
pytest tests/unit/test_data_validation.py::test_delta_calculation -v

# 只测试数据库连接
pytest tests/integration/test_database.py::test_database_connection -v
```

### 显示详细输出

```bash
# 显示print输出
pytest tests/ -v -s

# 显示更详细的错误信息
pytest tests/ -v --tb=long

# 失败时立即停止
pytest tests/ -v -x
```

---

## 🐛 测试失败排查

### 问题1：数据库连接失败

```
Error: Can't connect to MySQL server
```

**解决方案**：
```bash
# 1. 检查容器是否运行
docker-compose ps

# 2. 启动容器
docker-compose up -d

# 3. 等待MySQL就绪
sleep 10

# 4. 测试连接
python scripts/test_db_connection.py
```

### 问题2：找不到模块

```
ModuleNotFoundError: No module named 'pytest'
```

**解决方案**：
```bash
# 安装测试依赖
pip install -r requirements.txt
```

### 问题3：环境变量未设置

```
Error: MYSQL_HOST not found
```

**解决方案**：
```bash
# 确保.env文件存在
cp .env.example .env

# 或者手动设置环境变量
export MYSQL_HOST=localhost
export MYSQL_PORT=3306
```

---

## 📊 测试覆盖率

### 生成覆盖率报告

```bash
# 安装coverage
pip install pytest-cov

# 运行测试并生成覆盖率报告
pytest tests/ --cov=. --cov-report=html

# 查看报告
open htmlcov/index.html
```

---

## 🔄 CI/CD集成

### GitHub Actions示例

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      mysql:
        image: mysql:8.0
        env:
          MYSQL_ROOT_PASSWORD: riskmonitor2024
          MYSQL_DATABASE: riskmonitor
          MYSQL_USER: admin
          MYSQL_PASSWORD: riskmonitor2024
        ports:
          - 3306:3306
        options: >-
          --health-cmd="mysqladmin ping"
          --health-interval=10s
          --health-timeout=5s
          --health-retries=5
    
    steps:
    - uses: actions/checkout@v2
    
    - name: Set up Python
      uses: actions/setup-python@v2
      with:
        python-version: '3.13'
    
    - name: Install dependencies
      run: |
        pip install -r requirements.txt
    
    - name: Run tests
      env:
        MYSQL_HOST: 127.0.0.1
        MYSQL_PORT: 3306
        MYSQL_DATABASE: riskmonitor
        MYSQL_USER: admin
        MYSQL_PASSWORD: riskmonitor2024
      run: |
        pytest tests/ -v
```

---

## 💡 最佳实践

### 1. 测试前准备

```bash
# 完整的测试流程
make clean          # 清理旧环境
make up             # 启动容器
sleep 10            # 等待MySQL就绪
make test           # 运行所有测试
```

### 2. 开发时快速测试

```bash
# 只运行单元测试（快速反馈）
make test-unit

# 修改代码后测试特定功能
pytest tests/integration/test_mcp_tools.py::test_query_all_positions -v
```

### 3. 提交前完整测试

```bash
# 运行所有测试
make test-all

# 检查代码风格
black . --check
flake8 .
```

---

## 📚 扩展测试

### 添加新的测试

1. **单元测试**：在`tests/unit/`创建新文件
2. **集成测试**：在`tests/integration/`创建新文件
3. **命名规范**：文件名以`test_`开头
4. **函数命名**：测试函数以`test_`开头

### 示例：添加新测试

```python
# tests/unit/test_new_feature.py
def test_new_calculation():
    """测试新的计算功能"""
    result = my_new_function(10, 20)
    assert result == 30
```

---

## 🎯 测试目标

- ✅ 单元测试覆盖率 > 80%
- ✅ 集成测试覆盖所有MCP工具
- ✅ 所有测试通过
- ✅ 无警告和错误

---

## 📞 获取帮助

遇到问题？

1. 查看测试输出的详细错误信息
2. 检查Docker容器日志：`docker-compose logs mysql`
3. 验证数据库连接：`make test-db`
4. 查看README.md的故障排除部分
