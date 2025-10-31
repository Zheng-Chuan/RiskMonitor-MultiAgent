# MCP面试题精选

## 基础概念 (5题)

### 1. 什么是Model Context Protocol (MCP)?

MCP是一个开放协议，用于在AI应用和外部数据源/工具之间建立标准化连接。基于JSON-RPC 2.0，支持stdio、HTTP SSE等传输方式。

**核心能力**: Resources(上下文数据)、Prompts(提示模板)、Tools(可执行函数)

### 2. MCP服务器的生命周期有哪些阶段?

1. **初始化**: 客户端发送initialize请求，协商协议版本
2. **就绪**: 服务器响应capabilities
3. **运行**: 处理工具调用请求
4. **关闭**: 清理资源

### 3. MCP中stdio传输方式的优缺点?

**优点**: 简单、安全、适合本地工具、支持容器通信  
**缺点**: 不支持远程、调试困难、无法并发多客户端

### 4. 如何在MCP中实现错误处理?

```python
from mcp.types import ErrorData, McpError

@mcp.tool()
async def query_data(query: str):
    try:
        return await execute_query(query)
    except ValueError as e:
        raise McpError(ErrorData(code=-32602, message=f"Invalid: {e}"))
```

### 5. MCP工具支持哪些参数类型?

支持JSON Schema定义的所有类型: string, number, boolean, object, array, null

## 架构设计 (5题)

### 6. 如何设计支持多数据源的MCP服务器?

使用策略模式和工厂模式:

```python
class DataSource(ABC):
    @abstractmethod
    async def query(self, params: Dict) -> list:
        pass

class DataSourceFactory:
    _sources: Dict[str, DataSource] = {}
    
    @classmethod
    def get(cls, name: str) -> DataSource:
        return cls._sources.get(name)
```

### 7. MCP服务器如何实现认证?

**方案1: 环境变量**
```python
api_key = os.getenv("MCP_API_KEY")
if not api_key:
    raise McpError("Authentication required")
```

**方案2: RBAC权限控制**
```python
def require_permission(action: str):
    def decorator(func):
        if not check_permission(action):
            raise McpError("Permission denied")
        return func
    return decorator
```

### 8. 如何优化MCP服务器性能?

1. **连接池**: 使用aiomysql.create_pool管理数据库连接
2. **缓存**: 实现LRU缓存减少重复查询
3. **批量处理**: asyncio.gather并发执行
4. **流式响应**: 使用async generator处理大数据

### 9. 如何实现MCP服务器的可观测性?

```python
from prometheus_client import Counter, Histogram

tool_calls = Counter('mcp_tool_calls', ['tool', 'status'])
tool_duration = Histogram('mcp_tool_duration', ['tool'])

def observe_tool(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = await func(*args, **kwargs)
            tool_calls.labels(tool=func.__name__, status='ok').inc()
            return result
        finally:
            duration = time.time() - start
            tool_duration.labels(tool=func.__name__).observe(duration)
    return wrapper
```

### 10. 如何设计插件化的MCP服务器?

```python
class MCPPlugin(Protocol):
    name: str
    async def register_tools(self, server: Server) -> None:
        pass

class PluginManager:
    def discover_plugins(self, package: str):
        # 自动发现并加载插件
        for module in pkgutil.iter_modules([package]):
            plugin = importlib.import_module(f"{package}.{module.name}")
            self.plugins.append(plugin.Plugin())
```

## 实战应用 (5题)

### 11. 如何实现支持事务的MCP工具?

```python
@asynccontextmanager
async def transaction():
    conn = await get_connection()
    try:
        await conn.begin()
        yield conn
        await conn.commit()
    except:
        await conn.rollback()
        raise

@mcp.tool()
async def transfer_funds(from_acc: str, to_acc: str, amount: float):
    async with transaction() as conn:
        await conn.execute("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amount, from_acc)
        await conn.execute("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amount, to_acc)
```

### 12. 如何实现流式数据处理?

```python
@mcp.tool()
async def stream_large_dataset(query: str):
    async with db_pool.acquire() as conn:
        cursor = await conn.cursor()
        await cursor.execute(query)
        batch = []
        async for row in cursor:
            batch.append(dict(row))
            if len(batch) >= 100:
                yield {"batch": batch}
                batch = []
        if batch:
            yield {"batch": batch}
```

### 13. 如何实现参数验证?

```python
from pydantic import BaseModel, Field, validator

class QueryParams(BaseModel):
    trader_id: str = Field(..., pattern=r'^TRADER-\d{3}$')
    limit: int = Field(100, ge=1, le=1000)
    
    @validator('trader_id')
    def validate_trader(cls, v):
        if not trader_exists(v):
            raise ValueError(f'Trader {v} not found')
        return v

@mcp.tool()
async def query_positions(trader_id: str, limit: int = 100):
    params = QueryParams(trader_id=trader_id, limit=limit)
    return await execute_query(params)
```

### 14. 如何实现热重载?

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class MCPReloader(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.py'):
            importlib.reload(sys.modules[module_name])
            register_tools(server)

observer = Observer()
observer.schedule(MCPReloader(), path='./tools', recursive=True)
observer.start()
```

### 15. 如何实现工具版本管理?

```python
class VersionedToolRegistry:
    def __init__(self):
        self.tools: Dict[str, Dict[str, Callable]] = {}
    
    def register(self, name: str, version: str):
        def decorator(func):
            if name not in self.tools:
                self.tools[name] = {}
            self.tools[name][version] = func
            return func
        return decorator
    
    def get_handler(self, name: str, version: str = None):
        versions = self.tools[name]
        if version is None:
            version = max(versions.keys())
        return versions[version]

registry = VersionedToolRegistry()

@registry.register("query", "1.0")
async def query_v1(params: str):
    pass

@registry.register("query", "2.0")
async def query_v2(params: str, include_history: bool = False):
    pass
```

## 高级主题 (5题)

### 16. 如何实现分布式MCP服务器?

**架构**: Load Balancer → Multiple MCP Servers → Shared Cache (Redis) → Database

**关键点**:
- 使用HAProxy/Nginx负载均衡
- Redis共享缓存和会话
- 数据库连接池
- 分布式追踪(OpenTelemetry)

### 17. 如何实现A/B测试?

```python
class ABTestManager:
    def get_variant(self, user_id: str) -> str:
        hash_val = int(hashlib.md5(f"{user_id}".encode()).hexdigest(), 16)
        return "treatment" if (hash_val % 100) < 50 else "control"

@mcp.tool()
async def query_with_ab_test(user_id: str, query: str):
    variant = ab_test.get_variant(user_id)
    if variant == "treatment":
        return await new_algorithm(query)
    return await old_algorithm(query)
```

### 18. 如何实现灰度发布?

```python
class CanaryDeployment:
    def __init__(self):
        self.canary_users: Set[str] = set()
        self.canary_percentage: float = 0.0
    
    def is_canary_user(self, user_id: str) -> bool:
        if user_id in self.canary_users:
            return True
        hash_val = int(hashlib.md5(user_id.encode()).hexdigest(), 16)
        return (hash_val % 100) < self.canary_percentage

# 灰度流程: 5% → 20% → 50% → 100%
canary.set_canary_percentage(5)
```

### 19. 如何实现请求限流?

```python
from aiolimiter import AsyncLimiter

rate_limiter = AsyncLimiter(max_rate=100, time_period=60)

@mcp.tool()
async def rate_limited_query(query: str):
    async with rate_limiter:
        return await execute_query(query)
```

### 20. 如何实现MCP服务器的健康检查?

```python
@mcp.tool()
async def health_check():
    checks = {
        "database": await check_database(),
        "cache": await check_cache(),
        "disk_space": await check_disk_space()
    }
    
    all_healthy = all(checks.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": checks,
        "timestamp": datetime.now().isoformat()
    }

async def check_database():
    try:
        async with db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except:
        return False
```

## 总结

这20道面试题涵盖了MCP的核心概念、架构设计、实战应用和高级主题，从基础到进阶全面考察候选人对MCP协议的理解和实践能力。

**重点掌握**:
- MCP协议基础和生命周期
- 错误处理和参数验证
- 性能优化(连接池、缓存、并发)
- 可观测性(日志、指标、追踪)
- 高级特性(分布式、灰度发布、A/B测试)
