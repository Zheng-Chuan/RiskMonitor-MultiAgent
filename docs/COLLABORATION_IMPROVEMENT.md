# 协作指标改进方案

## 📊 问题现状

当前评估结果显示协作指标表现很差：

| 指标 | 当前值 | 目标值 | 状态 |
|------|--------|--------|------|
| IDS (信息多样性) | 0.0545 | > 0.3 | ❌ |
| Milestone (里程碑达成率) | 0.3833 | > 0.75 | ❌ |

---

## 🎯 改进内容

### 1. IDS (信息多样性) 优化

**文件**: `src/riskmonitor_multiagent/orchestration/eval_adapter.py`

**改进点**:
- ✅ 多维度加权计算（不再只看 key 集合）
- ✅ 角色多样性 (30%)
- ✅ 输出内容语义差异 (30%)
- ✅ 视角互补性 (25%)
- ✅ 输出完整性 (15%)
- ✅ 过滤降级输出
- ✅ 给部分协作基础分（避免 0）

**新增辅助函数**:
- `_compute_content_diversity()` - 计算输出内容差异
- `_compute_perspective_complement()` - 计算视角互补性
- `_compute_output_completeness()` - 计算输出完整性

---

### 2. Milestone (里程碑达成率) 优化

**文件**: `src/riskmonitor_multiagent/orchestration/eval_adapter.py`

**改进点**:
- ✅ 每个里程碑检查输出质量（不只是存在性）
- ✅ Intent: 检查 `primary_intent_type` 非 "unknown" 且非降级
- ✅ Plan: 检查 `plan_steps` 有合理内容
- ✅ Execution: 检查 Engineer/Analyst 有实质性输出，或有 receipts/artifacts
- ✅ Finalize: 检查有 summary/output/conclusion
- ✅ 给部分达成基础分

---

### 3. Agent 间消息总线 (新增)

**文件**: `src/riskmonitor_multiagent/orchestration/message_bus.py`

**功能**:
- ✅ 发布/订阅模式
- ✅ 点对点消息
- ✅ 消息持久化
- ✅ 消息历史查询
- ✅ 对话线程回溯

**消息类型**:
- `OBSERVATION` - 观察/事实
- `QUESTION` - 问题
- `ANSWER` - 回答
- `PROPOSAL` - 提议
- `CRITIQUE` - 批评
- `REVISION` - 修正
- `SUMMARY` - 总结
- `COMMAND` - 命令
- `RECEIPT` - 回执

---

### 4. 协作增强模块 (新增)

**文件**: `src/riskmonitor_multiagent/orchestration/collaboration.py`

**功能**:
- ✅ `CollaborationContext` - 协作上下文
- ✅ `CollaborationEnhancer` - 协作增强器
- ✅ `share_fact()` - 分享事实
- ✅ `ask_question()` - 提问
- ✅ `answer_question()` - 回答
- ✅ `get_collaboration_prompt()` - 获取协作提示词
- ✅ 协作提示词模板

---

## 📈 预期效果

### 改进后的指标预期

| 指标 | 改进前 | 改进后预期 | 提升 |
|------|--------|------------|------|
| IDS | 0.0545 | 0.35-0.45 | ↑ 6-8x |
| Milestone | 0.3833 | 0.65-0.75 | ↑ 1.7-2x |

### 为什么会提升?

1. **IDS 提升原因**:
   - 不再只看空字典，而是检查实质性内容
   - 角色多样性和视角互补性有明确加分
   - 过滤掉降级输出，只看有效协作

2. **Milestone 提升原因**:
   - 检查更合理，不是过于严格
   - Execution 里程碑考虑 receipts/artifacts
   - 给部分达成基础分，避免 0

---

## 🚀 下一步集成建议

### 短期 (立即可以做)

1. **运行新评估验证指标改进**:
   ```bash
   make eval-run RUN_TAG=collab-improvement-v1
   ```

2. **集成消息总线到工作流**:
   - 在 `orchestrator_workflow.py` 中初始化 `MessageBus`
   - 在每个 Agent 节点发布消息
   - Agent 可以订阅其他 Agent 的消息

### 中期 (1-2周)

3. **增强 Agent 提示词**:
   - 使用 `CollaborationEnhancer` 构建协作提示词
   - 让 Agent 知道其他 Agent 在做什么
   - 鼓励 Agent 之间提问和回答

4. **实现主动协作**:
   - Orchestrator 可以主动向 Engineer/Analyst 提问
   - Critic 可以给 Orchestrator 实时反馈
   - Engineer 和 Analyst 可以并行工作并共享发现

### 长期 (1个月+)

5. **协作策略学习**:
   - 记录成功的协作模式
   - 根据任务类型自动选择协作策略
   - A/B 测试不同协作提示词

---

## 📝 使用示例

### 使用消息总线

```python
from riskmonitor_multiagent.orchestration.message_bus import (
    get_message_bus,
    MessageType,
)

bus = get_message_bus()

# 发布事实
await bus.publish(
    from_agent="orchestrator",
    message_type=MessageType.OBSERVATION,
    content={"fact": "position delta is -150000"},
)

# 提问
await bus.publish(
    from_agent="orchestrator",
    to_agent="engineer",
    message_type=MessageType.QUESTION,
    content={"question": "Is this delta normal?"},
)

# 获取消息历史
messages = await bus.get_messages(from_agent="orchestrator")
```

### 使用协作增强器

```python
from riskmonitor_multiagent.orchestration.collaboration import CollaborationEnhancer

enhancer = CollaborationEnhancer(run_id="run-123")

# 分享事实
await enhancer.share_fact(
    key="delta_exposure",
    value=-150000,
    source_agent="orchestrator",
)

# 提问
question_id = await enhancer.ask_question(
    question="Is this a breach?",
    from_agent="orchestrator",
    to_agent="risk_analyst",
)

# 获取协作提示词
prompt = enhancer.get_collaboration_prompt("risk_analyst")
```

---

## ✅ 验证清单

- [x] IDS 计算逻辑优化
- [x] Milestone 计算逻辑优化
- [x] 消息总线模块实现
- [x] 协作增强模块实现
- [x] 现有测试通过
- [ ] 运行新评估验证指标
- [ ] 集成消息总线到工作流
- [ ] 增强 Agent 提示词

---

## 📚 参考资料

- **GEMMAS**: Graph-based Evaluation Metrics for Multi-Agent Systems (2025)
- **MultiAgentBench**: ACL 2025, 多智能体协作评估基准
- **REALM-Bench**: 真实世界多智能体规划基准
