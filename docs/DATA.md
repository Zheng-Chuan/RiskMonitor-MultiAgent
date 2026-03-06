# 数据与契约

本文档聚焦“当前代码实际使用”的数据结构与协议。

## MySQL 核心表

建表来源：[init_db.sql](../scripts/init_db.sql)

### positions

用途：头寸基础数据，供查询与风险计算使用。

关键字段：

- `position_id` 主键
- `trader_id`、`desk`、`security_id`
- `quantity`、`delta`、`currency`
- `entry_date`、`created_at`、`updated_at`

### alerts

用途：风险告警持久化与检索。

关键字段：

- `alert_id` 主键
- `request_id`、`alert_type`、`severity`
- `desk`、`trader_id`
- `metric_name`、`metric_value`、`threshold_value`、`breach_amount`
- `message`、`acknowledged`、`acknowledged_at`、`acknowledged_by`

## 编排产物契约

### orchestrator_run.v1

主产物由 [orchestrator_workflow.py](../src/riskmonitor_multiagent/orchestration/orchestrator_workflow.py) 构建。

重点字段：

- `run_id`、`task_id`
- `intent`
- `orchestrator_plan`、`critic_plan`
- `artifacts`、`receipts`
- `approval`、`status`
- `step_trace`
- `quality`

### Agent 输出契约

定义与校验在 [agent_outputs.py](../src/riskmonitor_multiagent/contracts/agent_outputs.py)：

- `orchestrator_output.v1`
- `critic_review.v1`
- `system_engineer_output.v1`
- `risk_analyst_output.v1`

### 意图契约

定义与校验在 [intent_output.py](../src/riskmonitor_multiagent/contracts/intent_output.py)：

- `intent_output.v2`
- 支持 `intents` 多意图
- 支持 `disambiguation` 解释
- 支持 evidence 引用字段约束

### 命令与回执契约

定义与校验在 [agent_messages.py](../src/riskmonitor_multiagent/contracts/agent_messages.py)：

- `agent_command.v1`
- `agent_receipt.v1`

## 记忆与存储

### MemoryEntry

定义在 [memory_entry.py](../src/riskmonitor_multiagent/contracts/memory_entry.py)：

- `scope` 仅允许 `private|shared`
- `kind` 表示记忆类型
- `session_id`、`run_id` 作为检索维度

### 运行总结 run_summary

存储在 [mongo_run_summary_store.py](../src/riskmonitor_multiagent/memory/mongo_run_summary_store.py)：

- 以 `run_id` 为主键 upsert
- 默认 schema `run_summary.v1`
- 关键字段 `text`、`key_points`、`receipt_command_ids`

## 向量检索

实现见 [chroma_store.py](../src/riskmonitor_multiagent/knowledge/chroma_store.py)：

- 告警相似检索 `query_alerts`
- 可选语义记忆写入（由开关控制）
