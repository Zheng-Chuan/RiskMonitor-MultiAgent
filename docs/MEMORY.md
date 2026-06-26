# MEMORY

`RiskMonitor-MultiAgent` 的记忆模块不是一个单独的向量库服务.
它本质上是一个统一门面 + Redis 持久层 + 进程内语义索引 的混合架构.

核心目标如下.

- 给 planning 阶段提供历史上下文
- 给 execution 阶段持续记录 working memory
- 给 finalize 阶段沉淀 run summary 和 lesson
- 给 resume 阶段恢复 task graph 和 memory state
- 给多角色协作提供 shared memory 和 private memory

## 1. 总体架构

```text
RiskMonitor-MultiAgent Memory Architecture

[Workflow / Agents]
    |
    v
[MemoryStore]
    |
    +-- append / list_recent / retrieve_for_planning
    +-- save_run_context / build_resume_payload
    +-- persist_run_artifacts / persist_approval_memory
    |
    +-- RedisBackend
    |     |
    |     +-- shared memory list
    |     +-- agent private memory list
    |     +-- run context hash
    |     +-- run summary hash
    |
    +-- SemanticIndexer
          |
          +-- 对重要记忆做轻量语义索引
          +-- 供 planning 时做经验召回
```

统一门面是 `MemoryStore`.
它对上承接 workflow 和 agent.
对下同时管理 Redis 持久化和语义检索.

## 1.1 Redis 数据形态

这一层里实际有 4 种核心数据.
前 2 种更像协作记忆流.
后 2 种更像运行态快照和恢复执行基础设施.

### A. shared memory list

作用

- 保存所有角色都能看到的共享记忆流
- 典型条目包括 `plan` `working_memory` `final` `lesson` `approval` `semantic_case`
- planning 阶段会从这里取 recent hits 和 shared board

Redis key

```text
shared:memory
```

Redis type

```text
List
```

value 格式

- list 中的每一个元素都是一个 JSON string
- 每个 JSON string 都符合 `memory_entry.v1` 结构

单条 value 完整字段

```json
{
  "schema_version": "memory_entry.v1",
  "entry_id": "mem_xxx",
  "ts_ms": 1710000000000,
  "agent_id": "system_engineer",
  "scope": "shared",
  "kind": "working_memory",
  "memory_type": "episodic",
  "session_id": "sess_monitor_001",
  "run_id": "run_proactive_001",
  "source": "task_graph_execution",
  "created_by": "system_engineer",
  "agent_role": "system_engineer",
  "agent_perspective": "system_reliability",
  "task_phase": "execution",
  "confidence": 0.93,
  "trace_ref": {
    "run_id": "run_proactive_001",
    "step_id": "step_fetch_metrics",
    "command_id": "cmd_fetch_metrics_001"
  },
  "content": {
    "text": "step step_fetch_metrics kind=tool_call status=completed agent=system_engineer tool=get_service_metrics task=监控交易台敞口和系统状态",
    "task_id": "task_monitor_001",
    "payload": {
      "content": "监控交易台敞口和系统状态",
      "desk": "delta_one"
    },
    "trace_entry": {
      "step_id": "step_fetch_metrics",
      "kind": "tool_call",
      "status": "completed",
      "tool_name": "get_service_metrics",
      "target_agent": "system_engineer",
      "command_id": "cmd_fetch_metrics_001"
    },
    "node_result": {
      "output": {
        "summary": "service healthy",
        "confidence": 0.93
      }
    }
  },
  "tags": [
    "tool_call",
    "completed",
    "execution"
  ]
}
```

### B. agent private memory list

作用

- 保存某个 agent 的私有任务快照
- 主要用于角色隔离和局部状态延续
- planning 阶段会把默认角色的 private memory state 一起读回来

Redis key

```text
agent:{agent_id}:memory
```

例子

```text
agent:system_engineer:memory
agent:risk_analyst:memory
agent:critic:memory
```

Redis type

```text
List
```

value 格式

- list 中的每一个元素也是一个 JSON string
- 顶层还是 `memory_entry.v1`
- 但 `content` 会是 `build_private_task_snapshot()` 产出的私有快照结构

单条 value 完整字段

```json
{
  "schema_version": "memory_entry.v1",
  "entry_id": "mem_private_xxx",
  "ts_ms": 1710000000100,
  "agent_id": "system_engineer",
  "scope": "private",
  "kind": "private_task_state",
  "memory_type": "episodic",
  "session_id": "sess_monitor_001",
  "run_id": "run_proactive_001",
  "source": "task_graph_execution",
  "created_by": "system_engineer",
  "agent_role": "system_engineer",
  "agent_perspective": "system_reliability",
  "task_phase": "execution",
  "confidence": 0.93,
  "trace_ref": {
    "run_id": "run_proactive_001",
    "step_id": "step_fetch_metrics",
    "command_id": "cmd_fetch_metrics_001"
  },
  "content": {
    "role": "system_engineer",
    "task_goal": "监控交易台敞口和系统状态",
    "current_progress": "completed",
    "open_questions": [],
    "recent_observations": [
      "service healthy"
    ],
    "next_intended_action": "handoff_to_next_step",
    "snapshot_text": "role=system_engineer goal=监控交易台敞口和系统状态 progress=completed observation=service healthy next=handoff_to_next_step"
  },
  "tags": [
    "private_task_memory",
    "completed"
  ]
}
```

### C. run context hash

作用

- 保存某一次 run 的完整运行上下文快照
- 这是 `resume` 能成立的关键基础设施
- 主要给恢复执行 回放 审计 调试使用

Redis key

```text
context:{run_id}
```

例子

```text
context:run_proactive_001
```

Redis type

```text
Hash
```

field 格式

```text
payload
```

field 对应的 value

- 是一个 JSON string
- 顶层结构由 `save_run_context()` 写入

完整 example

```json
{
  "run_id": "run_proactive_001",
  "event_id": "task_monitor_001",
  "created_at_ms": 1710000001000,
  "data": {
    "status": "completed",
    "entry_type": "user_task",
    "run_context": {
      "run_id": "run_proactive_001",
      "entry_type": "user_task",
      "task_id": "task_monitor_001"
    },
    "task": {
      "task_id": "task_monitor_001",
      "session_id": "sess_monitor_001",
      "payload": {
        "content": "监控交易台敞口和系统状态"
      }
    },
    "source_event": {},
    "route_decision": {},
    "intent": {
      "primary_intent_type": "check_system"
    },
    "task_graph": {
      "schema_version": "task_graph.v1",
      "nodes": [],
      "edges": []
    },
    "task_graph_execution": {
      "status": "completed",
      "blocked_step_id": null,
      "failed_step_id": null,
      "trace": []
    },
    "receipts": [],
    "approval_trace": [],
    "memory_hits": [],
    "planning_memory": {
      "hit_count": 2,
      "texts": [
        "[episodic/plan] previous plan",
        "[procedural/lesson] lesson use receipts"
      ]
    },
    "shared_memory_board": [],
    "private_memory_state": {
      "system_engineer": [],
      "risk_analyst": [],
      "critic": [],
      "orchestrator": []
    },
    "run_summary": {
      "text": "desk exposure and service metrics checked",
      "key_points": [
        "exposure within limit",
        "service healthy"
      ],
      "receipt_command_ids": [],
      "task_id": "task_monitor_001",
      "session_id": "sess_monitor_001"
    },
    "procedural_lesson": {
      "text": "lesson use receipts before final answer"
    },
    "long_term_experience": {
      "kind": "semantic_case"
    },
    "rejected_experience": {},
    "memory_policy": {
      "accepted": true,
      "confidence": 0.92,
      "threshold": 0.85,
      "reasons": [
        "accepted"
      ],
      "evidence_refs": [
        "run_trace:run_proactive_001"
      ]
    },
    "final_output": {
      "summary": "desk exposure and service metrics checked"
    }
  }
}
```

### D. run summary hash

作用

- 保存某次 run 的轻量总结
- 用于快速展示和 resume 时补充 run summary
- 它比 `run context hash` 小很多 更像摘要页

Redis key

```text
summary:{run_id}
```

例子

```text
summary:run_proactive_001
```

Redis type

```text
Hash
```

field 格式

```text
payload
updated_at
```

field 对应的 value

- `payload` 是 JSON string
- `updated_at` 是 Unix 时间戳整数

完整 example

```json
{
  "payload": "{\"text\":\"desk exposure and service metrics checked\",\"key_points\":[\"exposure within limit\",\"service healthy\"],\"receipt_command_ids\":[],\"task_id\":\"task_monitor_001\",\"session_id\":\"sess_monitor_001\"}",
  "updated_at": 1710000001
}
```

如果按应用层解析 `payload` 之后 它的结构是

```json
{
  "text": "desk exposure and service metrics checked",
  "key_points": [
    "exposure within limit",
    "service healthy"
  ],
  "receipt_command_ids": [],
  "task_id": "task_monitor_001",
  "session_id": "sess_monitor_001"
}
```

## 2. 记忆分层

### 2.1 短期共享记忆

- 所有 agent 都可见
- 主要存 plan step working_memory approval memory
- 底层是 Redis List
- 典型 key 类似 `shared:memory`

### 2.2 短期私有记忆

- 只给单个 agent 自己看
- 主要存每个角色的 task state snapshot
- 底层也是 Redis List
- 典型 key 类似 `agent:{agent_id}:memory`

### 2.3 长期经验记忆

- 运行结束后沉淀 summary lesson semantic_case
- 当前不是外部向量库
- 当前实现是进程内 `SemanticIndexer`
- 作用是在后续 planning 时做 few-shot 和经验召回

## 3. 主调用链

### 3.1 planning 链

workflow 启动后先拿 `MemoryStore`.
然后统一读取 shared board private memory recent memory 和 semantic hits.
这些内容会被合并成 planning memory.
最后交给 orchestrator 产出 plan.
产出后的 plan 会再次写回 shared memory.

主链大致如下.

```text
proactive_workflow
  -> memory_store.retrieve_for_planning()
  -> orchestrator 使用 memory summary 生成 plan
  -> persist_plan_memory()
```

### 3.2 execution 链

`TaskGraphExecutor` 每执行完一个 node 就会回调一次记忆写入.
共享 working memory 一定会写.
如果启用了 private memory 还会给对应 agent 写 private task state.

主链大致如下.

```text
TaskGraphExecutor.execute()
  -> on_node_completed
  -> memory_store.record_working_memory()
```

### 3.3 finalize 链

执行完成后系统会生成 final output.
critic 会做 final review.
然后把 run summary lesson 和可能的 semantic_case 一起沉淀下来.

主链大致如下.

```text
proactive_workflow
  -> memory_store.persist_run_artifacts()
```

### 3.4 approval 链

执行过程里产生的 approval record 不只是 trace.
它们在 run 结束后会被转成 approval memory 写入 shared memory.
这样后续回放和审计就可以直接从记忆层读取.

### 3.5 resume 链

如果某次 workflow 需要 resume.
系统会先按 `run_id` 读回 run context.
然后恢复 task graph 和 execution state.
再把 memory state shared board private state 和 run summary 合回 planning memory.
最后从 blocked step 继续执行.

## 4. 关键文件

统一门面

- `src/riskmonitor_multiagent/memory/memory_store.py`

写入编排

- `src/riskmonitor_multiagent/memory/memory_operations.py`

Redis 后端

- `src/riskmonitor_multiagent/memory/redis_backend.py`

语义索引

- `src/riskmonitor_multiagent/memory/semantic_indexer.py`

记忆 schema

- `src/riskmonitor_multiagent/contracts/memory_entry.py`

workflow 接入点

- `src/riskmonitor_multiagent/orchestration/proactive_workflow.py`

plan 和 result 落记忆

- `src/riskmonitor_multiagent/orchestration/workflow_memory.py`

resume 接入

- `src/riskmonitor_multiagent/orchestration/workflow_resume.py`

## 5. 设计重点

### 5.1 shared memory 是主链核心

shared memory 是整个系统的主协作面.
private memory 只是辅助角色隔离和局部状态保存.

### 5.2 记忆层和 workflow 强绑定

这里的记忆模块不是单纯的 CRUD 存储.
它直接服务 planning execution finalize resume 四条主链.

### 5.3 resume 能成立是因为上下文和记忆一起存

如果只存 task graph 不存 memory state.
恢复执行时就会丢掉之前的上下文.
当前实现把 run context 和 memory state 一起保存.
所以 resume 不是重新跑一遍.
而是真正从中断位置继续.

### 5.4 长期经验后端当前不是 Chroma

仓库里虽然有 Chroma.
但它属于 knowledge 子系统.
记忆主链当前真正使用的是 Redis + 进程内 `SemanticIndexer`.

## 6. 一句话总结

这个项目的记忆模块本质上是.

`以 MemoryStore 为统一入口, 用 Redis 保存短期和运行态记忆, 用轻量语义索引保存可复用经验, 并把 planning execution finalize resume 四条主链全部接到同一套记忆读写协议上.`
