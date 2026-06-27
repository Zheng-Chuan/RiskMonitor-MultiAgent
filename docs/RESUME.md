# RESUME

## 目标

本文档定义 `run_id` 级恢复语义, 作为 Unified Memory Architecture 的恢复侧锚点.

## 恢复入口

- 用户恢复请求通过 `resume.run_id` 或 `resume.task_graph` 进入统一 workflow
- 当只提供 `run_id` 时, 系统会从 MemoryStore 加载运行上下文和恢复 payload
- 当同时提供 `approval_decision` 时, 系统会先把审批结果回写到目标 step, 再从对应 step 继续执行

## 恢复载荷

恢复请求应至少包含下面这些字段中的一部分

- `run_id`
- `task_graph`
- `execution_state`
- `resume_from_step_id`
- `memory_state`
- `shared_memory_board`
- `private_memory_state`
- `run_summary`
- `approval_decision`

## 恢复原则

- 不默认整任务重跑
- 上游已成功 step 不重复执行
- 恢复上下文会显式注入 orchestrator 和 delegate 执行链
- planning memory 会合并 resume memory state, shared board, private memory, run summary

## 当前实现锚点

- 载荷构造: `src/riskmonitor_multiagent/memory/memory_store.py`
- 恢复注入: `src/riskmonitor_multiagent/orchestration/workflow_resume.py`
- step 级恢复执行: `src/riskmonitor_multiagent/orchestration/task_graph_executor.py`
- 主流程恢复入口: `src/riskmonitor_multiagent/orchestration/proactive_workflow.py`

## 与其他文档关系

- 架构总览见 `docs/ARCHITECTURE.md`
- 统一记忆决策见 `docs/decisions/ADR-003-unified-memory-design.md`
- Phase 2 记忆闭环计划见 `docs/phases/phase-2-memory-closure.md`
