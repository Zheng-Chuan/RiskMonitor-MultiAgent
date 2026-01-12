# RiskMonitor-MCP 面试题库

本文档收录项目中的关键技术决策与架构设计, 作为面试准备材料.

---

## MCP Transport 机制

### Q1: 为什么 MCP 需要 streamable-http transport? 它解决了什么问题?

**背景**

MCP (Model Context Protocol) 是一个标准化协议, 用于连接 AI 系统与外部工具和数据源. 协议本身是传输无关的, 但需要具体的 transport 层来承载通信.

**streamable-http 存在的核心原因**

1. **生产环境部署需求**
   - stdio 只适合本地进程间通信, 无法跨网络部署
   - 生产环境需要独立部署的服务, 支持多客户端并发访问
   - 需要标准化的 HTTP 协议栈(负载均衡, 反向代理, TLS, 认证)

2. **云原生与容器化**
   - Kubernetes 等编排系统基于 HTTP 健康检查和就绪探针
   - 需要 `/health` `/ready` 等标准端点
   - 需要优雅关闭(graceful shutdown)支持滚动更新

3. **可观测性与运维**
   - HTTP 有成熟的监控工具链(Prometheus, Grafana, APM)
   - 可以用标准 HTTP 中间件做日志, 链路追踪, 限流
   - 便于集成企业级网关和 API 管理平台

4. **安全与合规**
   - 支持标准 OAuth2/OIDC 认证授权
   - 可以在网络层做 mTLS, IP 白名单, WAF
   - 审计日志可以统一到 HTTP access log

5. **开发体验**
   - 可以用 curl, Postman 等工具直接调试
   - 支持 OpenAPI/Swagger 文档生成
   - 便于编写集成测试和端到端测试

**为什么叫 streamable-http 而不是普通 HTTP?**

- **streamable** 表示支持长连接和流式响应
- MCP 协议需要支持服务端推送(server-sent events)和双向通信
- 相比传统 request-response, streamable-http 可以在一个连接内持续推送更新
- 底层基于 HTTP/1.1 chunked transfer 或 HTTP/2 stream

---

## MCP 三种 Transport 对比

### stdio (Standard Input/Output)

**适用场景**
- 本地开发和调试
- IDE 插件与本地 MCP 服务通信
- 单用户, 单进程, 短生命周期

**特点**
- **通信方式**: 父子进程通过 stdin/stdout 传递 JSON-RPC 消息
- **生命周期**: 客户端启动时 fork MCP 服务进程, 退出时终止
- **并发**: 一个客户端对应一个服务进程, 无法共享
- **网络**: 仅限本机, 无法跨网络
- **状态**: 进程级隔离, 每个客户端独立状态

**优点**
- 零配置, 启动快
- 适合 IDE 集成(如 VSCode, Cursor)
- 调试简单, 日志直接输出到 stderr

**缺点**
- 无法多客户端共享
- 无法独立部署和扩展
- 无法做负载均衡和高可用

---

### streamable-http (HTTP with Streaming)

**适用场景**
- 生产环境部署
- 多客户端并发访问
- 云原生和容器化部署
- 需要认证授权和可观测性

**特点**
- **通信方式**: HTTP POST 请求, 支持 chunked transfer 和流式响应
- **生命周期**: 独立服务进程, 长期运行
- **并发**: 单实例支持多客户端, 可水平扩展
- **网络**: 支持跨网络, 标准 HTTP 协议栈
- **状态**: 可选 stateful(会话保持)或 stateless(每次请求独立)

**优点**
- 生产级部署能力
- 标准 HTTP 生态(负载均衡, 监控, 认证)
- 支持健康检查和优雅关闭
- 可以集成企业级安全策略

**缺点**
- 需要额外的网络和端口配置
- 相比 stdio 有网络开销
- 需要处理会话管理和并发控制

---

### SSE (Server-Sent Events)

**适用场景**
- 需要服务端主动推送的场景
- 实时通知和事件流
- 浏览器客户端(Web UI)

**特点**
- **通信方式**: HTTP GET 建立长连接, 服务端持续推送事件
- **生命周期**: 类似 streamable-http, 独立服务
- **并发**: 支持多客户端
- **网络**: 基于 HTTP, 单向推送(服务端到客户端)
- **状态**: 通常是 stateful, 维护长连接

**优点**
- 浏览器原生支持(EventSource API)
- 自动重连机制
- 适合实时通知和进度更新

**缺点**
- 单向通信, 客户端请求需要额外 HTTP 调用
- 连接数受限(浏览器对同域名有并发限制)
- 不如 WebSocket 灵活

---

## MCP 服务器会话状态管理

### Q2: MCP 服务器会维持会话状态吗? 为什么?

**答案: 取决于 transport 和配置**

### stdio 模式: 天然 stateful

- **每个客户端独立进程**: 一个客户端 fork 一个 MCP 服务进程
- **进程内存即状态**: 可以在内存中维护任意状态(缓存, 连接池, 上下文)
- **生命周期绑定**: 客户端退出, 服务进程终止, 状态自动清理
- **无需会话管理**: 不存在多客户端共享问题

**示例**
```python
# stdio 模式下可以安全地在全局变量维护状态
_cache = {}  # 只服务于当前客户端, 进程退出自动清理
```

---

### streamable-http 模式: 可选 stateful 或 stateless

**FastMCP 提供两种模式**

#### 1. Stateful 模式(默认)

- **会话保持**: 服务器为每个客户端维护独立会话(session)
- **session_id**: 客户端首次连接时分配, 后续请求携带 session_id
- **状态存储**: 会话状态存储在服务端内存(或 Redis 等外部存储)
- **适用场景**: 需要上下文连续性(如对话历史, 临时缓存)

**实现机制**
```python
# FastMCP 内部维护 session manager
class StreamableHTTPSessionManager:
    def __init__(self):
        self._sessions = {}  # session_id -> session_state
    
    def get_or_create_session(self, session_id):
        if session_id not in self._sessions:
            self._sessions[session_id] = Session()
        return self._sessions[session_id]
```

**优点**
- 支持有状态的工具调用(如多轮对话, 事务)
- 减少重复初始化开销

**缺点**
- 内存占用随会话数增长
- 水平扩展需要会话共享(sticky session 或外部存储)
- 需要会话过期和清理机制

---

#### 2. Stateless 模式

- **无会话保持**: 每次请求独立处理, 不维护客户端状态
- **幂等性**: 相同请求多次调用结果一致
- **适用场景**: 无状态工具(如查询, 计算), 需要水平扩展

**配置方式**
```python
mcp = FastMCP("RiskMonitor")
mcp.settings.stateless_http = True  # 启用 stateless 模式
```

**优点**
- 易于水平扩展, 任意实例可处理任意请求
- 无内存泄漏风险
- 适合云原生和 serverless 部署

**缺点**
- 无法维护上下文(每次请求需要重新初始化)
- 不适合有状态的业务逻辑

---

### RiskMonitor-MCP 的选择

**当前实现: Stateful(默认)**

原因:
1. **数据库连接池**: 需要在进程生命周期内复用连接, 避免每次请求重建
2. **指标聚合**: `metrics_service` 在内存中累积请求计数和延迟, 用于 `/metrics` 端点
3. **后台任务**: `task_registry` 维护异步任务状态, 需要跨请求访问

**但我们的状态是进程级, 不是会话级**

```python
# 我们的状态是全局共享的, 不依赖 session_id
_mysql_engine = None  # 所有请求共享连接池
_metrics = {"request_count": 0}  # 所有请求共享指标
_tasks = {}  # 所有请求共享任务注册表
```

**这意味着**
- 多个客户端访问同一个服务实例, 共享连接池和指标
- 但每个工具调用是独立的, 不依赖前序请求
- 适合无状态的查询和计算工具

**未来优化方向**
- 如果需要水平扩展, 可以:
  - 将 `task_registry` 迁移到 Redis
  - 将 `metrics` 推送到 Prometheus
  - 启用 `stateless_http = True`

---

## 总结对比表

| 维度 | stdio | streamable-http (stateful) | streamable-http (stateless) | SSE |
|------|-------|---------------------------|----------------------------|-----|
| **部署** | 本地进程 | 独立服务 | 独立服务 | 独立服务 |
| **并发** | 单客户端 | 多客户端 | 多客户端 | 多客户端 |
| **网络** | 本机 | 跨网络 | 跨网络 | 跨网络 |
| **状态** | 进程级 stateful | 会话级 stateful | 无状态 | 会话级 stateful |
| **扩展性** | 不可扩展 | 需要 sticky session | 易扩展 | 需要 sticky session |
| **通信** | 双向(stdin/stdout) | 双向(HTTP) | 双向(HTTP) | 单向(服务端推送) |
| **适用场景** | IDE 插件 | 生产环境 | 无状态 API | 实时通知 |

---

## 延伸思考

### Q3: 如果要做多租户隔离, 应该选择哪种模式?

**答案: stateless + 外部状态存储**

- 每个租户的状态存储在外部(Redis, DB)
- 请求携带 tenant_id, 服务端根据 tenant_id 加载状态
- 任意实例可处理任意租户请求, 易于扩展

### Q4: 如果要做实时协作(多用户同时编辑), 应该选择哪种 transport?

**答案: SSE 或 WebSocket**

- 需要服务端主动推送其他用户的变更
- SSE 适合单向推送(服务端 -> 客户端)
- WebSocket 适合双向实时通信

### Q5: RiskMonitor-MCP 未来如果要支持流式返回(如逐步计算风险), 需要改造吗?

**答案: 不需要, streamable-http 天然支持**

```python
@mcp.tool()
async def stream_risk_calculation(desk: str) -> AsyncIterator[dict]:
    """流式返回风险计算进度"""
    for step in ["loading_positions", "fetching_market", "computing_delta"]:
        yield {"step": step, "progress": 0.33}
        await asyncio.sleep(0.1)
    yield {"step": "done", "result": {...}}
```

FastMCP 的 streamable-http 会自动将 AsyncIterator 转换为 chunked HTTP 响应.

---

## MCP 硬核面试题库 (P6/2-1 级别)

以下 50 个 MCP 技术面试题 + 20 个项目拷打问题, 难度对标阿里 P6 或字节 2-1.

---

### 模块 1: MCP 协议与架构 (10 题)

#### Q1: MCP 协议的核心设计理念是什么? 为什么不直接用 gRPC 或 GraphQL?

**考点**: 协议设计权衡

**参考答案**:

- MCP 是 JSON-RPC 2.0 的扩展, 强调简单性和可扩展性
- gRPC 需要 protobuf 定义和代码生成, MCP 用 JSON Schema 更灵活
- GraphQL 是查询语言, MCP 是 RPC 协议, 语义不同
- MCP 设计目标是 AI-tool 通信, 不是通用 API 网关

#### Q2: MCP 的 capabilities negotiation 机制是如何工作的? 为什么需要它?

**考点**: 协议握手与版本兼容

**参考答案**:

- 客户端和服务端在 initialize 阶段交换 capabilities
- 客户端声明支持的协议版本和特性(如 sampling, roots)
- 服务端返回自己支持的 capabilities
- 避免客户端调用服务端不支持的功能, 实现向后兼容

#### Q3: MCP 的 tool 和 resource 有什么区别? 各自适用什么场景?

**考点**: 概念区分

**参考答案**:

- **tool**: 可执行的函数, 有副作用, 用于操作(如查询数据库, 发送邮件)
- **resource**: 只读的数据源, 无副作用, 用于提供上下文(如文件内容, API 文档)
- tool 适合动作, resource 适合知识检索

#### Q4: MCP 的 prompt 机制是做什么的? 和 tool 有什么关系?

**考点**: 协议扩展能力

**参考答案**:

- prompt 是服务端提供的预定义提示词模板
- 客户端可以列出可用 prompt, 并用参数实例化
- 用于标准化常见任务的提示词(如"分析这段代码")
- 和 tool 配合使用, prompt 生成任务描述, tool 执行任务

#### Q5: MCP 的 sampling 机制是什么? 为什么需要它?

**考点**: 高级特性

**参考答案**:

- sampling 允许服务端请求客户端的 LLM 生成内容
- 用于服务端需要 AI 能力的场景(如代码生成, 文本总结)
- 实现"服务端调用客户端"的反向 RPC
- 避免服务端自己部署 LLM

#### Q6: MCP 的 roots 机制是做什么的? 和文件系统有什么关系?

**考点**: 安全与权限

**参考答案**:

- roots 定义服务端可以访问的文件系统路径
- 客户端在 initialize 时声明 roots
- 服务端只能访问 roots 内的文件, 实现沙箱隔离
- 防止服务端任意读写客户端文件系统

#### Q7: MCP 的 progress notification 是如何实现的? 和普通 RPC 有什么不同?

**考点**: 异步与流式

**参考答案**:

- 服务端在处理长时间任务时, 可以发送 progress notification
- 客户端通过 notification 更新进度条或日志
- 不同于普通 RPC 的 request-response, progress 是单向推送
- 基于 JSON-RPC 的 notification 机制(无 id, 无需响应)

#### Q8: MCP 的错误处理机制是什么? 如何区分可重试和不可重试错误?

**考点**: 错误设计

**参考答案**:

- 使用 JSON-RPC 2.0 的 error 对象(code, message, data)
- 自定义 error code 区分错误类型
- 在 data 字段添加 retriable 标志
- 客户端根据 retriable 决定是否重试

#### Q9: MCP 协议如何支持流式响应? 和 HTTP chunked transfer 有什么关系?

**考点**: 流式传输

**参考答案**:

- MCP 本身是消息协议, 流式由 transport 层实现
- streamable-http 使用 HTTP chunked transfer encoding
- 服务端逐块发送 JSON-RPC 消息
- 客户端逐块解析, 实现流式处理

#### Q10: 如果要设计一个 MCP 的认证授权机制, 你会怎么做?

**考点**: 安全架构

**参考答案**:

- 在 HTTP transport 层做 OAuth2/OIDC
- 客户端在 Authorization header 携带 token
- 服务端验证 token, 提取 user_id 和 scope
- 在 tool 层做细粒度权限控制(RBAC 或 ABAC)
- 敏感操作记录审计日志

---

### 模块 2: Transport 与网络 (10 题)

#### Q11: stdio transport 的进程生命周期是怎样的? 如何处理进程崩溃?

**考点**: 进程管理

**参考答案**:

- 客户端 fork 子进程, 通过 stdin/stdout 通信
- 子进程继承父进程的环境变量和工作目录
- 进程崩溃时, 客户端检测到 EOF 或 exit code
- 客户端可以重启子进程, 但状态丢失

#### Q12: streamable-http 的连接复用是如何实现的? 和 HTTP/1.1 keep-alive 有什么关系?

**考点**: HTTP 优化

**参考答案**:

- 使用 HTTP/1.1 的 Connection: keep-alive
- 客户端和服务端复用 TCP 连接, 避免重复握手
- 需要设置合理的 timeout, 避免连接泄漏
- HTTP/2 可以进一步优化(多路复用, header 压缩)

#### Q13: 如何在 streamable-http 模式下实现请求超时控制?

**考点**: 超时设计

**参考答案**:

- 客户端设置 HTTP client timeout(connect + read)
- 服务端设置 request timeout, 超时返回 504
- 长时间任务用异步模式(返回 task_id, 客户端轮询)
- 使用 context.Context 或 asyncio.timeout 传递超时

#### Q14: SSE 的自动重连机制是如何工作的? 如何处理重连时的消息丢失?

**考点**: 可靠性设计

**参考答案**:

- 浏览器 EventSource 自动重连, 默认 3 秒间隔
- 服务端可以发送 retry 字段自定义间隔
- 使用 Last-Event-ID 实现断点续传
- 服务端缓存最近的事件, 重连时补发

#### Q15: 如果要在 MCP 上实现双向流式通信, 应该用哪种 transport?

**考点**: 技术选型

**参考答案**:

- WebSocket 是最佳选择(全双工, 低延迟)
- streamable-http 可以模拟(客户端轮询 + 服务端推送)
- gRPC bidirectional streaming(如果用 protobuf)
- 不推荐 SSE(单向)

#### Q16: 如何在 streamable-http 模式下实现限流和熔断?

**考点**: 稳定性保障

**参考答案**:

- 限流: 用 token bucket 或 leaky bucket 算法
- 在中间件层统计 QPS, 超过阈值返回 429
- 熔断: 统计错误率, 超过阈值快速失败
- 可以用 Redis 做分布式限流

#### Q17: 如何设计 MCP 的健康检查机制? /health 和 /ready 有什么区别?

**考点**: 云原生实践

**参考答案**:

- **/health**: liveness probe, 检查进程是否存活
  - 返回 200 即可, 不做复杂检查
  - 失败时 K8s 重启 pod
- **/ready**: readiness probe, 检查是否可以接收流量
  - 检查依赖(DB, Redis, 下游服务)
  - 失败时 K8s 摘除流量, 不重启
- 优雅关闭时先将 /ready 置为 503

#### Q18: 如何实现 MCP 服务的优雅关闭? 需要处理哪些资源?

**考点**: 生产级实践

**参考答案**:

1. 捕获 SIGTERM 信号
2. 停止接收新请求(将 /ready 置为 503)
3. 等待现有请求完成(设置超时, 如 30s)
4. 关闭数据库连接池
5. 关闭后台任务
6. 退出进程

#### Q19: 如果 MCP 服务需要支持跨域(CORS), 应该如何配置?

**考点**: Web 安全

**参考答案**:

- 在 HTTP 响应添加 CORS headers
  - Access-Control-Allow-Origin
  - Access-Control-Allow-Methods
  - Access-Control-Allow-Headers
- 处理 OPTIONS preflight 请求
- 生产环境限制 origin 白名单
- 敏感操作不允许跨域

#### Q20: 如何在 MCP 上实现 mTLS(双向 TLS 认证)?

**考点**: 安全加固

**参考答案**:

- 服务端和客户端都配置证书
- 服务端验证客户端证书(verify_mode=CERT_REQUIRED)
- 从客户端证书提取 CN 或 SAN 作为身份
- 用于高安全场景(如金融, 医疗)

---

### 模块 3: 数据访问与状态管理 (10 题)

#### Q21: 为什么要用连接池? 如何设计连接池的大小?

**考点**: 资源管理

**参考答案**:

- 避免每次请求建立连接的开销(TCP 握手, 认证)
- 连接池大小 = (核心线程数 * 2) + 有效磁盘数
- 考虑数据库的 max_connections 限制
- 监控连接池使用率, 动态调整

#### Q22: SQLAlchemy 的 Engine 和 Session 有什么区别? 在 MCP 中应该如何使用?

**考点**: ORM 理解

**参考答案**:

- **Engine**: 连接池管理, 全局单例, 线程安全
- **Session**: 事务管理, 请求级别, 非线程安全
- MCP 中 Engine 在启动时创建, Session 在每次请求创建
- 使用 context manager 确保 Session 正确关闭

#### Q23: 如何在 MCP 中实现数据库查询的超时控制?

**考点**: 超时设计

**参考答案**:

- 在连接池配置 connect_timeout 和 pool_timeout
- 在 SQL 执行时设置 statement_timeout
- 使用 asyncio.wait_for 或 signal.alarm 包装查询
- 超时后抛出 DataAccessError(retriable=True)

#### Q24: 如何设计 MCP 的缓存策略? 什么时候用本地缓存, 什么时候用 Redis?

**考点**: 缓存架构

**参考答案**:

- **本地缓存**: 进程内, 适合只读配置, 小数据集
  - 用 LRU cache, 设置 TTL
  - 单实例有效, 多实例不一致
- **Redis**: 分布式, 适合共享状态, 大数据集
  - 支持多实例共享
  - 需要处理网络延迟和故障

#### Q25: 如何在 MCP 中实现分布式事务?

**考点**: 分布式系统

**参考答案**:

- **两阶段提交(2PC)**: 强一致, 性能差, 不推荐
- **Saga 模式**: 最终一致, 每步可补偿
- **TCC(Try-Confirm-Cancel)**: 业务侵入大
- **本地消息表 + 定时任务**: 简单可靠
- MCP 场景推荐 Saga 或本地消息表

#### Q26: 如何处理数据库连接泄漏?

**考点**: 资源泄漏

**参考答案**:

- 使用 context manager 确保连接归还
- 设置连接池的 pool_recycle(如 1800s)
- 监控连接池的 checked_out 数量
- 定期检查慢查询和长事务

#### Q27: 如何在 MCP 中实现读写分离?

**考点**: 数据库架构

**参考答案**:

- 配置主库和从库的连接池
- 查询操作路由到从库, 写操作路由到主库
- 处理主从延迟(如强制读主库)
- 使用中间件(如 ProxySQL)简化路由

#### Q28: 如何设计 MCP 的异常映射机制? 为什么需要统一的 DataAccessError?

**考点**: 错误抽象

**参考答案**:

- 数据库异常(pymysql, psycopg2)映射为 DataAccessError
- 统一 error code(如 DB_CONNECTION_ERROR, DB_TIMEOUT)
- 标记 retriable 字段, 指导重试策略
- 上层不感知底层数据库类型, 易于切换

#### Q29: 如何在 MCP 中实现乐观锁和悲观锁?

**考点**: 并发控制

**参考答案**:

- **乐观锁**: 用 version 字段, UPDATE 时检查版本号
  - 适合冲突少的场景
  - 失败时返回 409 Conflict
- **悲观锁**: 用 SELECT FOR UPDATE
  - 适合冲突多的场景
  - 需要事务支持

#### Q30: 如何设计 MCP 的数据访问层重试策略?

**考点**: 可靠性设计

**参考答案**:

- 只重试 retriable 错误(网络, 超时, 死锁)
- 不重试 non-retriable 错误(语法错误, 权限)
- 使用指数退避(exponential backoff)
- 设置最大重试次数(如 3 次)
- 记录重试日志, 便于排查

---

### 模块 4: 性能与可观测性 (10 题)

#### Q31: 如何设计 MCP 的性能基准测试? 需要测哪些指标?

**考点**: 性能工程

**参考答案**:

- **延迟**: p50, p95, p99(ms)
- **吞吐**: QPS, TPS
- **错误率**: 4xx, 5xx 占比
- **资源**: CPU, 内存, 连接数
- 固化测试用例, 自动化执行, 趋势监控

#### Q32: 为什么要关注 p95 而不是平均值? p99 和 p95 有什么区别?

**考点**: 性能指标理解

**参考答案**:

- 平均值会被极值拉偏, 不反映用户体验
- p95 表示 95% 的请求延迟, 更接近真实体验
- p99 更严格, 但可能被偶发抖动影响
- SLA 通常用 p95 或 p99 作为目标

#### Q33: 如何在 MCP 中实现分布式链路追踪?

**考点**: 可观测性

**参考答案**:

- 使用 OpenTelemetry 或 Jaeger
- 在请求入口生成 trace_id 和 span_id
- 在跨服务调用时传递 trace context
- 在日志中记录 trace_id, 关联日志和链路
- 可视化调用链, 定位性能瓶颈

#### Q34: 如何设计 MCP 的日志规范? 需要记录哪些字段?

**考点**: 日志工程

**参考答案**:

- **必选**: timestamp, level, request_id, message
- **可选**: user_id, tool_name, latency_ms, error_code
- 使用结构化日志(JSON), 便于检索
- 敏感信息脱敏(如密码, token)
- 日志分级(DEBUG, INFO, WARN, ERROR)

#### Q35: 如何在 MCP 中实现指标采集? Prometheus 和 StatsD 有什么区别?

**考点**: 监控架构

**参考答案**:

- **Prometheus**: pull 模式, 服务端暴露 /metrics
  - 适合云原生, K8s 原生支持
  - 支持多维度标签
- **StatsD**: push 模式, 客户端推送指标
  - 适合传统架构
  - 简单轻量
- MCP 推荐 Prometheus

#### Q36: 如何设计 MCP 的告警规则? 什么时候应该告警?

**考点**: 告警策略

**参考答案**:

- **错误率**: 5xx > 1% 持续 5 分钟
- **延迟**: p95 > SLA 阈值持续 5 分钟
- **可用性**: /ready 失败持续 3 次
- **资源**: CPU > 80%, 内存 > 90%
- 避免告警风暴, 设置抑制规则

#### Q37: 如何在 MCP 中实现慢查询监控?

**考点**: 性能优化

**参考答案**:

- 在数据库层开启 slow query log
- 在应用层记录查询耗时, 超过阈值(如 1s)告警
- 定期分析慢查询, 优化索引
- 使用 EXPLAIN 分析执行计划

#### Q38: 如何设计 MCP 的容量规划? 如何预估需要多少实例?

**考点**: 容量工程

**参考答案**:

- 测量单实例的 QPS 上限(压测)
- 预估业务峰值 QPS
- 实例数 = 峰值 QPS / 单实例 QPS / 0.7(留 30% buffer)
- 考虑高可用(至少 2 个实例)
- 监控实际负载, 动态扩缩容

#### Q39: 如何在 MCP 中实现请求采样? 为什么需要采样?

**考点**: 可观测性优化

**参考答案**:

- 高 QPS 场景下, 全量日志和链路成本高
- 按比例采样(如 1%), 或按规则采样(错误请求全采)
- 使用 trace_id 的哈希值决定是否采样
- 保证采样的随机性和代表性

#### Q40: 如何在 MCP 中实现 SLO 监控? SLO 和 SLA 有什么区别?

**考点**: 服务质量管理

**参考答案**:

- **SLO**(Service Level Objective): 内部目标, 如 p95 < 500ms
- **SLA**(Service Level Agreement): 对外承诺, 如可用性 99.9%
- SLO 应该比 SLA 更严格, 留 buffer
- 监控 SLO 达成率, 未达成时触发改进

---

### 模块 5: 安全与合规 (10 题)

#### Q41: 如何在 MCP 中防止 SQL 注入?

**考点**: 安全基础

**参考答案**:

- 使用参数化查询(prepared statement)
- 不要拼接 SQL 字符串
- 使用 ORM(如 SQLAlchemy)自动转义
- 输入验证, 拒绝特殊字符

#### Q42: 如何在 MCP 中实现 API 限流? 如何防止 DDoS?

**考点**: 安全防护

**参考答案**:

- 限流: token bucket, 按 IP 或 user_id 限流
- 返回 429 Too Many Requests, 带 Retry-After header
- DDoS 防护: 在网关层做(如 Cloudflare, AWS WAF)
- 应用层做业务逻辑限流(如单用户每分钟 10 次)

#### Q43: 如何在 MCP 中实现敏感数据脱敏?

**考点**: 数据安全

**参考答案**:

- 日志中脱敏(密码, token, 身份证)
- 数据库中加密存储(AES-256)
- 传输中用 HTTPS
- 返回给客户端时部分隐藏(如手机号 138****1234)

#### Q44: 如何在 MCP 中实现审计日志? 需要记录哪些操作?

**考点**: 合规要求

**参考答案**:

- 记录敏感操作(创建, 修改, 删除)
- 字段: timestamp, user_id, action, resource, result
- 审计日志不可篡改(写入专用存储或区块链)
- 定期归档, 保留时间符合合规要求(如 7 年)

#### Q45: 如何在 MCP 中实现 RBAC(基于角色的访问控制)?

**考点**: 权限设计

**参考答案**:

- 定义角色(admin, operator, viewer)
- 定义权限(read, write, delete)
- 用户关联角色, 角色关联权限
- 在 tool 层检查权限, 无权限返回 403

#### Q46: 如何在 MCP 中防止 CSRF 攻击?

**考点**: Web 安全

**参考答案**:

- 使用 CSRF token, 在表单中嵌入
- 验证 Referer 或 Origin header
- 敏感操作用 POST, 不用 GET
- SameSite Cookie 属性

#### Q47: 如何在 MCP 中实现 API Key 管理?

**考点**: 认证机制

**参考答案**:

- 生成随机 API Key(如 UUID)
- 存储时哈希(bcrypt 或 SHA-256)
- 客户端在 Authorization header 携带
- 支持 API Key 的创建, 撤销, 过期

#### Q48: 如何在 MCP 中防止重放攻击?

**考点**: 安全加固

**参考答案**:

- 使用 nonce(一次性随机数)
- 请求中携带 timestamp, 拒绝过期请求
- 服务端缓存已使用的 nonce, 拒绝重复
- 使用 HTTPS 防止中间人攻击

#### Q49: 如何在 MCP 中实现数据备份与恢复?

**考点**: 灾难恢复

**参考答案**:

- 定期全量备份(如每天)
- 增量备份(如每小时)
- 备份存储在异地(如 S3)
- 定期演练恢复流程, 测试 RTO 和 RPO

#### Q50: 如何在 MCP 中实现零信任架构?

**考点**: 安全架构

**参考答案**:

- 不信任任何网络, 所有请求都认证授权
- 使用 mTLS 验证服务身份
- 最小权限原则, 按需授权
- 持续验证, 动态调整权限

---

### 项目拷打: RiskMonitor-MCP 专项 (20 题)

#### 拷打 1: 为什么你的 server.py 要做成薄入口? 如果业务逻辑都在 server.py 会有什么问题?

**考点**: 架构分层

**参考答案**:

- 违反单一职责原则, server.py 职责过重
- 难以测试, 无法 mock 数据库和外部依赖
- 难以复用, 业务逻辑和框架耦合
- 难以扩展, 新增功能需要修改 server.py

#### 拷打 2: 你的 data_access 层为什么要用 SQLAlchemy Engine 而不是直接用 pymysql?

**考点**: 技术选型

**参考答案**:

- Engine 提供连接池, pymysql 每次建连开销大
- Engine 支持连接回收, 避免连接泄漏
- Engine 提供统一的异常处理
- 未来可以无缝切换到 PostgreSQL 或其他数据库

#### 拷打 3: 你的错误映射为什么要用 DataAccessError 而不是直接抛 pymysql.Error?

**考点**: 抽象设计

**参考答案**:

- 上层不应该感知底层数据库类型
- 统一 error code, 便于客户端处理
- 标记 retriable, 指导重试策略
- 便于切换数据库实现

#### 拷打 4: 你的 benchmark 脚本为什么要固化请求集? 如果每次随机生成会有什么问题?

**考点**: 性能测试方法论

**参考答案**:

- 随机生成无法复现, 无法对比不同版本
- 无法排除数据差异的影响
- 固化请求集可以测试缓存效果
- 便于定位性能回归

#### 拷打 5: 你的 p95 目标为什么是 500ms? 如果是 100ms 或 2000ms 会怎样?

**考点**: SLO 设定

**参考答案**:

- 100ms 过于严格, 需要大量优化, 成本高
- 2000ms 过于宽松, 用户体验差
- 500ms 是金融场景的常见目标, 平衡性能和成本
- 需要根据业务场景和用户反馈调整

#### 拷打 6: 你的 readiness check 为什么要检查 MySQL? 如果 MySQL 慢查询会怎样?

**考点**: 健康检查设计

**参考答案**:

- MySQL 是核心依赖, 不可用时服务无法工作
- 慢查询会导致 readiness check 超时, 服务被摘除
- 需要设置 readiness check 的超时(如 3s)
- 慢查询应该在应用层优化, 不应该影响健康检查

#### 拷打 7: 你的 graceful shutdown 为什么要先将 /ready 置为 503? 如果直接关闭会怎样?

**考点**: 优雅关闭

**参考答案**:

- 直接关闭会导致正在处理的请求失败
- 先置为 503, K8s 会摘除流量, 不再转发新请求
- 等待现有请求完成(如 30s), 再关闭
- 避免用户看到 502 Bad Gateway

#### 拷打 8: 你的 monitor_desk_exposure 为什么要异步调用 fetch_market_snapshot? 如果同步会怎样?

**考点**: 异步编程

**参考答案**:

- 同步会阻塞事件循环, 影响其他请求
- 异步可以并发处理多个请求, 提高吞吐
- 网络 IO 是异步的天然场景
- FastMCP 是异步框架, 必须用 async/await

#### 拷打 9: 你的 task_registry 为什么要用内存存储? 如果服务重启会怎样?

**考点**: 状态管理

**参考答案**:

- 内存存储简单, 适合 demo 和单实例
- 服务重启会丢失任务状态, 客户端需要重新提交
- 生产环境应该用 Redis 或数据库持久化
- 需要权衡一致性和性能

#### 拷打 10: 你的 metrics_service 为什么要用进程内存? 如果多实例会怎样?

**考点**: 指标聚合

**参考答案**:

- 进程内存简单, 适合单实例
- 多实例时每个实例的指标独立, 需要在 Prometheus 聚合
- 或者推送到中心化存储(如 Redis, InfluxDB)
- 需要权衡实时性和一致性

#### 拷打 11: 你的 exposure_service 为什么要单独一层? 为什么不直接在 tool 里计算?

**考点**: 分层设计

**参考答案**:

- 业务逻辑和 IO 分离, 便于测试
- exposure 计算可能被多个 tool 复用
- 便于优化(如缓存, 并行计算)
- 符合单一职责原则

#### 拷打 12: 你的 breach_service 为什么要返回 list 而不是 bool? 如果只返回是否超限会有什么问题?

**考点**: API 设计

**参考答案**:

- 客户端需要知道哪些指标超限, 不只是是否超限
- list 可以包含多个 breach, 每个 breach 有详细信息
- 便于生成告警和报告
- 扩展性更好

#### 拷打 13: 你的 alerting_service 为什么要和 breach_service 分开? 为什么不合并?

**考点**: 职责划分

**参考答案**:

- breach 是业务规则判断, alert 是通知机制
- breach 可能有多种告警方式(webhook, 邮件, 短信)
- 分开便于测试和扩展
- 符合开闭原则

#### 拷打 14: 你的 logging_service 为什么要用 request_id? 如果不用会有什么问题?

**考点**: 可观测性

**参考答案**:

- 无法关联同一个请求的多条日志
- 无法追踪请求的完整生命周期
- 无法定位问题(如哪个请求慢, 哪个请求失败)
- request_id 是分布式系统的标准实践

#### 拷打 15: 你的 cache 为什么要用 Protocol 而不是 ABC? 为什么要预留 NoopCache?

**考点**: 接口设计

**参考答案**:

- Protocol 是 duck typing, 不需要继承
- 更灵活, 第三方库可以直接实现
- NoopCache 用于测试和 demo, 避免引入 Redis 依赖
- 符合依赖倒置原则

#### 拷打 16: 你的 benchmark 为什么要支持 --p95-target-ms 参数? 为什么不硬编码?

**考点**: 工程实践

**参考答案**:

- 不同环境的目标不同(本地, 测试, 生产)
- 便于 CI/CD 集成, 自动化验收
- 便于调试, 快速验证优化效果
- 符合配置外部化原则

#### 拷打 17: 你的 test_http_endpoints 为什么要用 TestClient 而不是真实的 HTTP 请求?

**考点**: 测试策略

**参考答案**:

- TestClient 不需要启动真实服务, 测试更快
- 可以 mock 依赖(如数据库, 外部 API)
- 便于 CI/CD 集成, 不需要额外环境
- 真实 HTTP 请求适合端到端测试, 不适合单元测试

#### 拷打 18: 你的 ROADMAP 为什么要分 Week 而不是 Phase? Week 和 Phase 有什么区别?

**考点**: 项目管理

**参考答案**:

- Week 是时间维度, Phase 是能力维度
- Week 便于跟踪进度, Phase 便于描述成熟度
- Week 是执行计划, Phase 是交付目标
- 两者结合, 既有时间约束又有质量标准

#### 拷打 19: 你的项目为什么要用 pylint 而不是 flake8 或 black? 为什么只用一个工具?

**考点**: 工具选型

**参考答案**:

- pylint 功能最全, 可以替代 flake8
- black 是格式化工具, pylint 是静态分析工具, 职责不同
- 只用一个工具避免规则冲突
- Google Python Style Guide 推荐 pylint

#### 拷打 20: 如果让你重新设计 RiskMonitor-MCP, 你会做哪些不同的选择? 为什么?

**考点**: 架构反思

**参考答案**:

- **缓存**: 引入 Redis, 支持多实例
- **任务队列**: 用 Celery 替代内存 task_registry
- **指标**: 推送到 Prometheus, 支持多实例聚合
- **认证**: 引入 OAuth2, 支持多租户
- **测试**: 增加压测和混沌工程
- **文档**: 增加 API 文档和架构图

---

## 面试题总结

这 70 个问题覆盖了:

- **协议与架构**: MCP 核心概念, 设计理念
- **网络与传输**: transport 选型, 性能优化
- **数据访问**: 连接池, 事务, 缓存
- **性能与监控**: 指标, 日志, 链路追踪
- **安全与合规**: 认证, 授权, 审计
- **项目实践**: RiskMonitor-MCP 的设计决策

难度对标阿里 P6/字节 2-1, 需要:

- 深入理解协议和框架
- 有生产环境实践经验
- 能权衡技术方案的 trade-off
- 能从业务场景反推技术选型

---

## 参考资料

- [MCP Specification](https://spec.modelcontextprotocol.io/)
- [FastMCP Documentation](https://github.com/jlowin/fastmcp)
- [HTTP Chunked Transfer Encoding (RFC 7230)](https://tools.ietf.org/html/rfc7230#section-4.1)
- [Server-Sent Events (W3C)](https://html.spec.whatwg.org/multipage/server-sent-events.html)
