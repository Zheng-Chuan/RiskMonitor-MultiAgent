# RiskMonitor-MultiAgent Architecture

## Overview

系统现在有两种输入 但只有一个执行内核

- `user_task`
- `system_event`

两者最终都会汇入同一套 `RunContext + ProactiveWorkflow + TaskGraphExecutor + receipt + memory + run_trace`

## Topology

```text
                           +----------------------+
                           |      user_task       |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           |  run_orchestrator    |
                           |     _workflow        |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           |   ProactiveWorkflow  |
                           +----------+-----------+
                                      ^
                                      |
                   +------------------+------------------+
                   |                                     |
                   |                                     |
       +-----------+-----------+             +-----------+-----------+
       |      system_event     |             |      resume request   |
       +-----------+-----------+             +-----------+-----------+
                   |                                     |
                   v                                     |
       +------------------------+                        |
       |    validate_event      |                        |
       +-----------+------------+                        |
                   |                                     |
                   v                                     |
       +------------------------+                        |
       |    ModeratorAgent      |                        |
       +-----------+------------+                        |
                   |                                     |
                   +------------------+------------------+
                                      |
                                      v
                           +----------------------+
                           |    build intent      |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           |   planning memory    |
                           |   + orchestrator     |
                           |   + critic review    |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           |      task_graph      |
                           +----------+-----------+
                                      |
                                      v
                           +----------------------+
                           | TaskGraphExecutor    |
                           +----------+-----------+
                                      |
                    +-----------------+-----------------+
                    |                 |                 |
                    v                 v                 v
          +----------------+ +----------------+ +----------------+
          |  delegate step | |  tool_call     | |  finalize step |
          +----------------+ |  via executor  | +----------------+
                             +--------+-------+
                                      |
                                      v
                           +----------------------+
                           |   ToolExecutor       |
                           | command -> receipt   |
                           +----------+-----------+
                                      |
                                      v
                    +-----------------+-----------------+
                    |                 |                 |
                    v                 v                 v
            +---------------+ +---------------+ +---------------+
            | approval flow | | memory store  | | run_trace v2  |
            +---------------+ +---------------+ +---------------+
                                      |
                                      v
                           +----------------------+
                           |     final output     |
                           +----------------------+
```

## Main Flow

```text
user_task
  -> intent
  -> retrieve planning memory
  -> orchestrator_plan
  -> critic_plan
  -> task_graph
  -> execute steps
  -> receipts / approvals / replan
  -> final_output
  -> persist memory
  -> persist run_trace
```

## Event Flow

```text
system_event
  -> validate_event
  -> MessageBus publish
  -> ModeratorAgent route decision
  -> convert to unified task
  -> same workflow as user_task
```

## Approval And Resume

```text
tool_call or step
  -> approval required
  -> blocked / pending_approval
  -> approval_record
  -> approval_memory
  -> resume request
  -> resume_from_step_id
  -> continue TaskGraphExecutor
```

## Memory Layers

```text
planning memory
  - recent shared memory
  - semantic retrieval

working memory
  - run time hits
  - private and shared context

long term memory
  - run summary
  - procedural lesson
  - approval memory
  - resume state
```

## Trace Model

`run_trace.v2` 是统一证据面  
核心 category 如下

```text
task
plan
step
message
command
receipt
approval
memory
final
version_snapshot
```

trace 会同时服务三类用途

- replay
- evaluator
- gate

## Storage

```text
Redis
  - short term working memory
  - run context

PageIndex / Chroma
  - semantic retrieval

results/run_traces
  - persisted run_trace snapshots

eval/results
  - evaluation result files
```

## Module Map

```text
src/riskmonitor_multiagent/contracts
  - event approval run_context task_graph run_trace

src/riskmonitor_multiagent/orchestration
  - orchestrator_workflow
  - proactive_workflow
  - task_graph_executor
  - tool_executor
  - message_bus

src/riskmonitor_multiagent/memory
  - memory_store

src/riskmonitor_multiagent/observability
  - run_trace

eval
  - cli
  - evaluator
  - gate
  - benchmarks
```

## Release Standard

只有下面三份文档保留为当前项目文档面

- `README.md`
- `docs/ARCHETECTURE.md`
- `docs/PRD.md`
