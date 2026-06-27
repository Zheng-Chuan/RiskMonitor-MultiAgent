# RiskMonitor-MultiAgent Architecture

# 系统统一主流程
```text
[输入]
    |
    +-> [user_task]
    |       | 用户显式任务
    |       v
    |   [run_proactive_workflow]
    |
    +-> [system_event]
    |       | 特殊的系统输入
    |       | normalize_event
    |       | validate_event
    |       | publish 到 MessageBus
    |       | proactive budget 判断
    |       | ModeratorAgent route decision
    |       | 转成 unified task
    |       v
    |   [run_proactive_workflow]
    |
    +-> [resume request]
            | 输入 run_id approval_decision resume_from_step_id
            | build_resume_payload
            | 读取 task_graph execution_state memory_state run_summary
            | _apply_resume_context
            v
        [run_proactive_workflow]
    
    |
    v
[ProactiveMultiAgentWorkflow.run]
    | 检查 memory_enabled baseline_mode benchmark_config
    | 组装 task_with_context
    | 生成统一 run_id 和 run_context
    v
[Step 1] intent
    | IntentAgent 识别 primary_intent_type
    | 输出 intent evidence permission_requirements
    | 写入 intent trace
    v
[Step 2] retrieve planning memory
    | Redis recent shared memory
    | built-in semantic experience retrieval
    | 如果是 resume 则合并 memory_state 和 run_summary
    | 形成 orchestrator context.memory
    v
[Step 3] orchestrator_plan
    | OrchestratorAgent 输出 orchestrator_output.v1
    | normalize_orchestrator_output
    | plan_steps -> task_graph
    | task_graph 包含 nodes edges schema_version = task_graph.v1
    v
[Step 4] critic_plan
    | CriticAgent 审查计划
    | 输出 issues suggested_fixes require_human_approval
    | 决定是否 replan
    v
[Step 5] task_graph execution
    | TaskGraphExecutor 按依赖调度节点
    | 支持 delegate / tool_call / finalize / ask_human / replan / stop
    |
    +-> [delegate]
    |       | engineer / analyst 执行子任务
    |       | 输出 delegate_result
    |
    +-> [tool_call]
    |       | 构造标准 command
    |       | 注入 timeout_ms retry_budget
    |       v
    |   [ToolExecutor]
    |       | 检查 tool registry
    |       | 检查 RBAC
    |       | 检查 budget
    |       | 判断是否 require approval
    |       |
    |       +-> [approval required]
    |       |       | 生成 approval_request
    |       |       | approval state = pending approved rejected expired resumed
    |       |       | 写入 approval_trace approval_memory
    |       |       | 若 pending 则 blocked 并等待 resume
    |       |
    |       +-> [handler execution]
    |               | 执行具体工具
    |               | 捕获 timeout runtime dependency validation
    |               v
    |           [receipt]
    |               | ok error approval_state
    |               | failure_classification retry_count timeout_ms
    |               | 写入 task_graph_execution.trace
    |
    +-> [working memory]
            | step 完成后 record_working_memory
            | 写入 shared episodic memory
    v
[Step 6] receipts approvals replan
    | 汇总 receipts approval_trace retry_records
    | failure or critic rejection -> replan
    | replan 后新子图重新进入 TaskGraphExecutor
    | blocked_step_id 或 failed_step_id 进入 resume 路径
    | resume 时只清失败节点和下游输出
    v
[Step 7] finalize output
    | 汇总 engineer analyst receipts approvals
    | 生成 final_output quality approval summary
    | critic 写 final 和 lesson
    v
[Step 8] persist and trace
    | build_run_trace_snapshot -> run_trace.v2
    | category 包括 task plan step command receipt approval memory final
    | RunTraceStore 内存缓存 + 持久化到 results/run_traces
    | Redis 保存 run context 和 resume state
    | eval/results 消费 trace 做 replay evaluator gate benchmark
    | 返回统一结果
    v
[输出]
    | user_task 返回给用户
    | system_event 产出统一 run_trace 和 follow-up result
    | resume 返回继续执行后的结果
```

# 文档保留范围
```text
README.md
docs/ARCHITECTURE.md
docs/PRD.md
```
