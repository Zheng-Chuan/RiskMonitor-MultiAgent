# P3: Agent 主动提问功能实现报告

## 概述

成功实现了完整的 Agent 主动提问功能，使 Agent 能够真正向用户提问并等待回答。

**完成时间**: 2026-03-21  
**优先级**: P3 (低优先级)  
**状态**: ✅ 已完成

---

## 交付内容

### 1. 问题管理器模块

**文件**: `src/riskmonitor_multiagent/proactive_agents/question_manager.py`

**核心类**:

#### PendingQuestion
- 问题数据结构
- 包含问题 ID、内容、上下文、回答、状态等字段
- 支持序列化为字典

#### QuestionManager
- `ask_user()` - 向用户提问并等待回答
- `submit_answer()` - 提交用户回答
- `get_pending_questions()` - 获取待回答问题
- `get_all_questions()` - 获取所有问题历史
- `cancel_question()` - 取消问题
- `register_callback()` - 注册问题回调

**便捷函数**:
- `ask_user_question()` - 快速提问
- `answer_user_question()` - 快速回答

---

### 2. 集成到 ReAct 循环

**修改文件**: `src/riskmonitor_multiagent/proactive_agents/base.py`

#### 2.1 修改 `_execute_action()`

```python
elif action_type == "ask_human":
    # 真正的 ask_human 实现 - 等待用户回答
    question = action.get("question", "需要您的帮助")
    context = action.get("context", {})
    timeout = action.get("timeout", 300)  # 默认 5 分钟
    
    manager = get_question_manager()
    answer = await manager.ask_user(
        agent_name=self._name,
        question=question,
        context=context,
        timeout_seconds=timeout,
    )
    
    return {
        "status": "human_answered",
        "question": question,
        "answer": answer,
        "timeout": answer.startswith("[超时]"),
    }
```

#### 2.2 修改 `_should_terminate()`

```python
async def _should_terminate(self, task, history):
    # 如果是 finalize，终止
    if last_step.action_type == "finalize":
        return True
    
    # 如果是 ask_human 但已超时，终止
    if last_step.action_type == "ask_human":
        observation = last_step.observation
        if observation and observation.get("timeout"):
            return True  # 超时后终止
    
    return False
```

**关键改进**:
- ask_human 后不立即终止
- 等待用户回答后继续执行
- 超时后才终止

---

### 3. 模块导出

**修改文件**: `src/riskmonitor_multiagent/proactive_agents/__init__.py`

新增导出:
```python
__all__ = [
    # ... 原有导出
    "QuestionManager",
    "PendingQuestion",
    "get_question_manager",
    "ask_user_question",
    "answer_user_question",
]
```

---

## 核心功能

### 1. 提问流程

```
Agent 决定 ask_human
    ↓
创建 PendingQuestion
    ↓
触发回调 (通知用户)
    ↓
打印问题到控制台
    ↓
等待用户回答 (异步)
    ↓
用户提交回答
    ↓
触发事件，唤醒 Agent
    ↓
Agent 继续执行
```

### 2. 超时处理

- 默认超时时间：300 秒 (5 分钟)
- 超时后返回：`[超时] 用户未在 X 秒内回答`
- 超时后终止 ReAct 循环

### 3. 回调机制

```python
def on_new_question(question: PendingQuestion):
    print(f"新问题：{question.question}")

manager.register_callback(on_new_question)
```

### 4. 问题管理

```python
# 获取待回答问题
pending = manager.get_pending_questions()

# 获取问题历史
all_questions = manager.get_all_questions()

# 取消问题
manager.cancel_question(question_id)

# 清理旧问题
manager.clear_answered_questions(max_age_seconds=3600)
```

---

## 测试结果

### 测试 1: 正常提问

```
============================================================
测试 1: 正常提问 (等待用户输入)
============================================================

📢 新问题通知:
   ID: 9d074def-c984-4921-a241-6aae47bda8dd
   Agent: test_agent
   问题：请问 1+1 等于几？

============================================================
[test_agent] 提问：请问 1+1 等于几？
问题 ID: 9d074def-c984-4921-a241-6aae47bda8dd
超时时间：30 秒
============================================================

模拟用户输入...

✅ Agent 收到回答：等于 2
```

### 测试 2: 超时处理

```
============================================================
测试 2: 超时处理 (5 秒超时)
============================================================

📢 新问题通知:
   ID: aa07a327-c3c3-4b05-bfcb-caaaf0b6a31f
   Agent: test_agent
   问题：这是一个超时测试问题

⏰ 超时结果：[超时] 用户未在 5 秒内回答
```

### 测试 3: 问题历史

```
============================================================
测试 3: 查看所有问题历史
============================================================

总问题数：2

问题 9d074def...:
  Agent: test_agent
  问题：请问 1+1 等于几？
  状态：answered
  回答：等于 2

问题 aa07a327...:
  Agent: test_agent
  问题：这是一个超时测试问题
  状态：timeout
  回答：无
```

---

## 使用示例

### 基础使用

```python
from riskmonitor_multiagent.proactive_agents import ask_user_question

# Agent 主动提问
answer = await ask_user_question(
    agent_name="risk_analyst",
    question="请确认这个风险操作是否继续？",
    context={"operation": "sell_stock", "amount": 10000},
    timeout_seconds=120,
)

if answer.startswith("[超时]"):
    print("用户未确认，操作取消")
else:
    print(f"用户确认：{answer}")
```

### 注册回调

```python
from riskmonitor_multiagent.proactive_agents import get_question_manager

manager = get_question_manager()

# 注册 Webhook 回调
async def send_to_frontend(question):
    # 发送到前端
    await websocket.send({
        "type": "question",
        "data": question.to_dict()
    })

manager.register_callback(send_to_frontend)
```

### 提交回答

```python
from riskmonitor_multiagent.proactive_agents import answer_user_question

# 用户通过 API 提交回答
@app.post("/api/answer")
async def submit_answer(question_id: str, answer: str):
    success = await answer_user_question(question_id, answer)
    return {"success": success}
```

---

## 代码统计

| 文件 | 新增行数 | 说明 |
|------|----------|------|
| question_manager.py | ~250 | 问题管理器核心 |
| base.py (修改) | ~25 | 集成 ask_human |
| __init__.py (修改) | ~10 | 导出新增模块 |
| test_ask_human.py | ~100 | 测试脚本 |
| **总计** | **~385** | |

---

## 技术亮点

1. **异步等待机制**
   - 使用 `asyncio.Event` 实现异步等待
   - 不阻塞其他 Agent 的执行
   - 支持并发多个提问

2. **超时处理**
   - 可配置的超时时间
   - 超时后自动返回
   - 不影响系统稳定性

3. **回调系统**
   - 支持多个回调函数
   - 可用于集成到 UI
   - 灵活的通知机制

4. **问题历史**
   - 完整的问题记录
   - 支持查询和清理
   - 便于调试和审计

---

## 集成方案

### 1. CLI 集成
当前实现已支持 CLI 交互，问题会打印到控制台。

### 2. Web 前端集成
```python
# FastAPI 示例
@app.websocket("/ws/questions")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    manager = get_question_manager()
    
    def on_new_question(question):
        asyncio.create_task(
            websocket.send_json(question.to_dict())
        )
    
    manager.register_callback(on_new_question)
    
    while True:
        data = await websocket.receive_json()
        await answer_user_question(
            data["question_id"],
            data["answer"]
        )
```

### 3. API 集成
```python
# REST API
@app.post("/api/questions/{question_id}/answer")
async def submit_answer_api(question_id: str, answer: str):
    success = await answer_user_question(question_id, answer)
    return {"success": success}
```

---

## 后续优化建议

1. **持久化存储**
   - 使用数据库存储问题历史
   - 支持系统重启后恢复

2. **多用户支持**
   - 问题路由到不同用户
   - 用户权限管理

3. **优先级队列**
   - 高优先级问题优先处理
   - 问题分类和标签

4. **通知渠道**
   - 邮件通知
   - 短信通知
   - Slack/钉钉集成

---

## 总结

P3 任务**完全完成**，实现了:

✅ 问题管理器 (QuestionManager)  
✅ 提问和回答功能  
✅ 异步等待机制  
✅ 超时处理  
✅ 回调通知系统  
✅ 问题历史管理  
✅ 集成到 ReAct 循环  
✅ 完整的测试用例  

**Phase 4 完成度：100%** 🎉

所有核心功能已实现:
- ✅ 质量门禁系统 (P0)
- ✅ Agent 主动性 (P1)
- ✅ ROADMAP 修正 (P2)
- ✅ Agent 主动提问 (P3)
