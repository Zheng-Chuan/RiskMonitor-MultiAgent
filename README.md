# RiskMonitor-MultiAgent

## 项目概述

这是一个面向金融风控场景的 Proactive Multi-Agent 系统  
它把用户任务和系统事件统一收敛到同一套执行内核中  
主链路已经具备下面这些真实能力

- 任务先经过 `intent -> plan -> execute -> final`
- 系统事件先经过 `ModeratorAgent` 再进入同一套 workflow
- 所有工具执行都走统一 `command -> receipt` 主链
- step 级审批 恢复执行 运行时 replan 已接到真实执行链路
- 记忆检索会真实参与规划 恢复和 lesson 沉淀
- `run_trace.v2` 会记录 task plan step command receipt approval memory final
- replay 和评测会直接消费统一 trace
- benchmark v2 已收敛为 `Simple Medium Complex Recovery Approval Memory Safety` 七类

## 当前口径

这个仓库现在只对外讲已经被真实代码 真实 trace 和真实 benchmark 证明过的能力  
不再保留任何和当前实现不一致的宣传性文档

## 代码入口

- 编排入口: `src/riskmonitor_multiagent/orchestration/proactive_workflow.py`
- 主工作流: `src/riskmonitor_multiagent/orchestration/proactive_workflow.py`
- 任务图执行: `src/riskmonitor_multiagent/orchestration/task_graph_executor.py`
- 工具治理: `src/riskmonitor_multiagent/orchestration/tool_executor.py`
- 统一记忆: `src/riskmonitor_multiagent/memory/memory_store.py`
- 统一 trace: `src/riskmonitor_multiagent/observability/run_trace.py`
- 评测入口: `eval/cli.py`

## 文档

- [docs/ARCHETECTURE.md](docs/ARCHETECTURE.md)
- [docs/PRD.md](docs/PRD.md)

## 测试入口

- `tests/unit`: 纯逻辑和 contract 测试
- `tests/integration`: 真实 adapter 和基础设施对接测试
- `tests/workflows`: 面向主工作流的回归测试 当前先收敛 monitoring 和 unified memory 两条稳定主链
- `tests/acceptance`: 发布前验收测试
- 推荐执行: `pytest tests/unit`
- 基础设施接线: `pytest tests/integration`
- 主工作流回归: `pytest tests/workflows`
- 发布前验收: `pytest tests/acceptance`
