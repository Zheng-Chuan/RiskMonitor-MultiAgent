# 演练和故障排查手册

本文档提供 RiskMonitor-MultiAgent 系统的演练指南和常见问题的故障排查方法。

## 目录

- [演练指南](#演练指南)
- [常见问题](#常见问题)
- [故障排查](#故障排查)
- [监控和告警](#监控和告警)

---

## 演练指南

### 演练 1: 基础风险监控任务

**目标**: 验证基础风险监控功能正常工作

**步骤**:

1. **启动服务**

```bash
docker compose up -d mysql
make run
```

2. **验证数据库连接**

```bash
make test-db
```

预期结果: `DB health check passed`

3. **执行基础任务**

创建一个测试脚本 `test_basic.py`:

```python
import asyncio
from main import run_risk_monitor_task

async def test():
    result = await run_risk_monitor_task({
        "payload": {
            "content": "检查 Equities desk 的风险暴露"
        }
    })
    print(f"Status: {result['status']}")
    assert result['status'] == 'completed'

asyncio.run(test())
```

运行:
```bash
python test_basic.py
```

**验收标准**:
- [ ] 服务正常启动
- [ ] 数据库连接正常
- [ ] 任务执行成功，status 为 'completed'
- [ ] 有 intent、engineer、analyst 输出

---

### 演练 2: 消息总线和动态协作

**目标**: 验证消息总线和动态协作功能

**步骤**:

1. **使用多 Agent 工作流**

创建测试脚本 `test_message_bus.py`:

```python
import asyncio
from riskmonitor_multiagent.orchestration.multiagent_workflow import get_multi_agent_workflow

async def test():
    workflow = get_multi_agent_workflow()
    result = await workflow.run({
        "payload": {
            "content": "检查 Equities desk 的风险暴露"
        }
    })
    print(f"Message History: {len(result['message_history'])}")
    assert len(result['message_history']) > 0

asyncio.run(test())
```

2. **使用动态协作工作流**

创建测试脚本 `test_dynamic.py`:

```python
import asyncio
from riskmonitor_multiagent.orchestration.dynamic_workflow import get_dynamic_workflow

async def test():
    workflow = get_dynamic_workflow()
    result = await workflow.run({
        "payload": {
            "content": "检查 Equities desk 的风险暴露"
        }
    })
    print(f"Mode: {result['mode']}")
    assert result['mode'] == 'dynamic'

asyncio.run(test())
```

**验收标准**:
- [ ] 消息总线有消息历史
- [ ] 动态协作模式为 'dynamic'
- [ ] 有 completed_agents 记录

---

### 演练 3: ReAct + CoT 循环

**目标**: 验证 ReAct + CoT 推理功能

**步骤**:

创建测试脚本 `test_react.py`:

```python
import asyncio
from riskmonitor_multiagent.orchestration.react_loop import (
    CoTEnhancedReActLoop,
    format_react_trace,
)

async def test():
    def thought_generator(task, history):
        return f"思考步骤 {len(history) + 1}"
    
    def reasoning_generator(task, history, thought):
        return f"理由: {thought} 是必要的"
    
    def evidence_generator(task, history, thought):
        return {"step": len(history) + 1}
    
    def action_decider(task, history, thought):
        if len(history) < 3:
            return ("mock_action", {"step": len(history) + 1})
        return ("finalize", {})
    
    def action_executor(action_type, action):
        return {"result": "done"}
    
    def termination_checker(task, history):
        return len(history) >= 3
    
    loop = CoTEnhancedReActLoop(
        max_steps=5,
        thought_generator=thought_generator,
        reasoning_generator=reasoning_generator,
        evidence_generator=evidence_generator,
        action_decider=action_decider,
        action_executor=action_executor,
        termination_checker=termination_checker,
    )
    
    result = await loop.run(task={"test": "data"})
    
    print(format_react_trace(result))
    assert result.success is True
    assert len(result.steps) == 3

asyncio.run(test())
```

**验收标准**:
- [ ] ReAct 循环成功执行
- [ ] 有 3 个步骤
- [ ] 每个步骤都有 reasoning 和 evidence
- [ ] trace 可以正常格式化

---

### 演练 4: BDI 模型和迭代优化

**目标**: 验证 BDI 模型和迭代优化功能

**步骤**:

创建测试脚本 `test_bdi.py`:

```python
from riskmonitor_multiagent.agents.bdi import BDIAgentMixin

class TestAgent(BDIAgentMixin):
    def __init__(self):
        super().__init__()

agent = TestAgent()

# 添加信念
agent.add_belief(
    content="市场波动很大",
    source="observation",
    confidence=0.9,
)

# 添加愿望
agent.add_desire(
    description="降低风险暴露",
    priority=100,
)

# 添加意图
agent.add_intention(
    description="查询当前头寸",
    tool_name="query_positions_by_desk",
    tool_params={"desk": "Equities"},
)

# 验证
beliefs = agent.get_beliefs()
desires = agent.get_active_desires()
intentions = agent.get_pending_intentions()

print(f"Beliefs: {len(beliefs)}")
print(f"Desires: {len(desires)}")
print(f"Intentions: {len(intentions)}")

assert len(beliefs) == 1
assert len(desires) == 1
assert len(intentions) == 1
```

**验收标准**:
- [ ] 信念可以添加和获取
- [ ] 愿望可以添加和获取
- [ ] 意图可以添加和获取

---

## 常见问题

### 问题 1: 数据库连接失败

**症状**: `Access denied for user 'admin'@'...'`

**原因**: MySQL 容器是用旧版 `.env` 初始化的，密码不一致

**解决方案**:

```bash
# 停止并删除 MySQL 容器
docker compose stop mysql
docker compose rm -f mysql

# 删除数据卷（会清空库内数据）
docker volume rm riskmonitor-multiagent_mysql_data 2>/dev/null || true

# 重新启动 MySQL
docker compose up -d mysql

# 等待约 10 秒后测试连接
make test-db
```

---

### 问题 2: 服务启动失败

**症状**: `make run` 报错

**排查步骤**:

1. 检查环境变量
```bash
cat .env
```

2. 检查端口占用
```bash
lsof -i :8000
```

3. 查看详细日志
```bash
python main.py
```

---

### 问题 3: LLM 调用失败

**症状**: Agent 返回错误或超时

**排查步骤**:

1. 检查 LLM 配置
```bash
echo $LLM_API_KEY
echo $LLM_BASE_URL
```

2. 检查网络连接
```bash
ping $LLM_BASE_URL
```

3. 检查成本控制
- 查看 `MAX_LLM_COST_PER_TASK` 配置
- 查看 Prometheus 指标 `llm_cost_total_usd`

---

### 问题 4: 测试失败

**症状**: `make test-unit` 部分测试失败

**解决方案**:

1. 确保 MySQL 正在运行
```bash
docker compose ps
```

2. 重置并重新运行
```bash
make test-unit
```

3. 查看详细错误
```bash
python -m pytest tests/unit/test_xxx.py -v -xvs
```

---

## 故障排查

### 检查清单

当系统出现问题时，按以下顺序检查:

1. **基础设施**
   - [ ] MySQL 是否运行? `docker compose ps`
   - [ ] 数据库连接是否正常? `make test-db`
   - [ ] 端口 8000 是否被占用? `lsof -i :8000`

2. **配置**
   - [ ] `.env` 文件是否存在?
   - [ ] 环境变量是否正确?
   - [ ] LLM API Key 是否配置?

3. **日志**
   - [ ] 查看应用日志
   - [ ] 查看错误堆栈
   - [ ] 查看 Trace ID

4. **指标**
   - [ ] 访问 `http://localhost:8000/metrics`
   - [ ] 查看错误率
   - [ ] 查看延迟

---

### 日志查看

**应用日志**:

```bash
# 直接运行看日志
python main.py
```

**审计日志**:

查看 `audit.log` 文件（如果配置了）。

**Trace 日志**:

如果启用了 tracing，可以通过 Trace ID 追踪请求:

```python
from riskmonitor_multiagent.observability.tracing import get_trace_summary

trace = get_trace_summary("your-trace-id")
print(trace)
```

---

### 指标监控

**Prometheus 指标**:

访问 `http://localhost:8000/metrics`

关键指标:

| 指标 | 说明 |
|------|------|
| `orchestrator_runs_total` | 编排运行次数 |
| `orchestrator_latency_ms` | 编排延迟（毫秒） |
| `intent_recognitions_total` | 意图识别次数 |
| `llm_calls_total` | LLM 调用次数 |
| `llm_cost_total_usd` | LLM 总成本（美元） |

**告警规则示例**:

- 错误率 > 5%: 告警
- P95 延迟 > 15 秒: 告警
- LLM 成本每日超预算: 告警

---

## 监控和告警

### 健康检查

**数据库健康检查**:

```bash
make test-db
```

**服务健康检查**:

访问 `http://localhost:8000/health`（如果有）

### 告警建议

| 告警类型 | 触发条件 | 严重程度 |
|----------|----------|----------|
| 数据库连接失败 | 连续 3 次连接失败 | P0 |
| LLM 调用失败率 | 失败率 > 10% | P1 |
| 高延迟 | P95 > 30 秒 | P1 |
| 高成本 | 日成本 > $100 | P2 |

---

## 更多文档

- [API 文档](./API.md)
- [使用指南](./USAGE_GUIDE.md)
- [系统架构](./ARCHITECTURE.md)
- [快速开始](./QUICKSTART.md)
- [路线图](./ROADMAP.md)
