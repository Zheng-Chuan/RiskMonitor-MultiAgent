# 数据字典

本文件记录当前项目已落地的 MySQL schema 与 Kafka topic 设计
同时记录事件驱动告警链路需要的增量设计, 用于后续实现与评审

说明

- "已落地"部分以当前仓库 `scripts/init_db.sql` 与 tools/data_access 实现为准
- "增量设计"用于记录后续演进方向 例如更多 topics DLQ retry audit tables

## MySQL schema

### positions

来源

- scripts/init_db.sql

字段

- position_id: VARCHAR(50) primary key
- trader_id: VARCHAR(50) not null
- desk: VARCHAR(100) not null
- security_id: VARCHAR(100) not null
- quantity: DECIMAL(18, 4) not null
- delta: DECIMAL(18, 4) nullable
- entry_date: DATE not null
- currency: VARCHAR(3) not null default USD
- created_at: TIMESTAMP default current_timestamp
- updated_at: TIMESTAMP default current_timestamp on update current_timestamp

索引

- idx_positions_trader on trader_id
- idx_positions_desk on desk
- idx_positions_security on security_id
- idx_positions_date on entry_date

### alerts

来源

- scripts/init_db.sql

字段

- alert_id: VARCHAR(36) primary key
- request_id: VARCHAR(36) not null
- alert_type: VARCHAR(50) not null
- severity: VARCHAR(20) not null
- desk: VARCHAR(100) not null
- trader_id: VARCHAR(50) nullable
- metric_name: VARCHAR(50) not null
- metric_value: DECIMAL(20, 2) not null
- threshold_value: DECIMAL(20, 2) not null
- breach_amount: DECIMAL(20, 2) not null
- message: TEXT not null
- created_at: TIMESTAMP default current_timestamp
- acknowledged: BOOLEAN default false
- acknowledged_at: TIMESTAMP nullable
- acknowledged_by: VARCHAR(50) nullable

增量设计

- 事件驱动告警链路需要引入状态字段, 以支持 pending 到 consumed 的工单式语义
- LLM 分析结果需要落库, 以支持重试, 可观测, 以及 webhook payload 可追踪

建议新增字段

- status: VARCHAR(32) not null
 - pending_analysis
 - pending_delivery
 - delivered
 - consumed
- analysis_json: JSON nullable, 结构化分析结论
- analysis_text: TEXT nullable, 面向 risk manager 的自然语言总结
- delivery_id: VARCHAR(64) nullable, webhook 幂等键
- delivery_attempts: INT not null default 0
- delivered_at: TIMESTAMP nullable
- consumed_at: TIMESTAMP nullable

索引

- idx_request_id on request_id
- idx_alert_type on alert_type
- idx_desk on desk
- idx_created_at on created_at
- idx_severity on severity

## Kafka topics

本项目在 Week 6 引入了 Kafka + Debezium Connect, 并打通了 positions 表的 CDC 输出.
本项目在 Week 7 增加了 Sentinel consumer, 可以直接消费 CDC 事件并触发多智能体流水线.
本项目在 Week 8 增加向量数据库 Chroma, 用于存储历史告警的向量化表示并提供相似度检索.

## 向量数据库

### Chroma

用途

- 存储 alerts 的向量化表示, 支持相似度检索
- MCP tool search_similar_alerts 与 CLI 都会查询这里

当前落地

- docker compose profile: kb
- service: chroma (端口 8001)
- collection: 默认 riskmonitor-alerts 可用 CHROMA_COLLECTION 覆盖

### positions_cdc

用途

- Debezium 从 MySQL binlog 捕获 positions 表变更
- CDC consumer 消费后触发 desk 级风险计算与 breach 判断

当前落地

- topic: `risk.positions.cdc`
- payload: Debezium 事件经 ExtractNewRecordState 展开后的行级变更, 当前为 Kafka Connect JSON 格式(schema + payload)
- JSON Schema: `schemas/cdc/positions_cdc_v1.schema.json` (可注册到 Schema Registry)
- connector 配置: `scripts/debezium/positions-connector.json`

消费侧说明

- Sentinel 会从 payload 中提取 desk 与 delta 字段, 并把 delta 作为 exposure 口径进行阈值判断
- delta 为 DECIMAL 类型时可能以 base64 形式出现, Sentinel 已做兼容解码

建议配置

- partitions: 3 起步
- replication_factor: 本地 1 生产按集群策略
- key 建议: position_id
- 语义: at least once

事件 schema

- schema_version: string, v1
- event_id: string, 用于幂等去重
- op: string, c u d
- ts_ms: number
- key:
 - position_id: string
- before: object or null
- after: object or null
- source:
 - db: string
 - table: string
 - binlog_file: string
 - binlog_pos: number

字段映射说明

- before after 的业务字段建议与 positions 表列保持一致
- consumer 侧按 after 或 before 中的 desk 做 desk 级聚合
- 方案B desk 迁移语义: update 时若 before.desk 不等于 after.desk 则对 old desk 做扣减 对 new desk 做增加

幂等与去重

- CDC consumer 需要对 event_id 去重
- 推荐新建 processed_cdc_events 表用于存储已处理 event_id
- event_id 可以优先使用 Debezium 自带 source 元数据, 或使用 topic partition offset 组合

### 标准事件 Envelope (RiskEvent)

用途

- 用统一的事件结构承载 module2 的所有输入输出
- 让编排层可回放 可幂等 可审计

当前落地

- schema_version: `risk_event.v1`
- JSON Schema: `schemas/events/risk_event_v1.schema.json`
- Sentinel 消费 `risk.positions.cdc` 后会先 normalize 成 RiskEvent (producer=debezium)
- 当 breach 触发时 Sentinel 会生成派生事件 RiskEvent (producer=sentinel, causation_id=source_event_id)

核心字段

- schema_version: string, 固定 risk_event.v1
- event_id: string, 默认使用 topic:partition:offset 组合, 可用于幂等去重与回放定位
- correlation_id: string, 默认等于 event_id, 用于端到端串联
- causation_id: string or null, 派生事件指向上游事件 id
- occurred_at: string, ISO8601
- producer: string, 例如 debezium 或 sentinel
- severity: INFO WARNING CRITICAL
- category: system 或 business
- actionability: boolean
- confidence: number 0到1
- payload: object, 业务载荷与证据引用

默认处理策略

- category=system 或 system_issue 时优先拦截并输出可观测证据
- category=business 且 actionability=true 且 severity=CRITICAL 时默认进入人工审批后再执行有副作用动作

### Agent 输出契约

用途

- 固化三个 Agent 的结构化输出
- 让质量门禁可测试可回归

当前落地

- System Engineer 输出 schema: `schemas/agents/system_engineer_output_v1.schema.json`
- Risk Analyst 输出 schema: `schemas/agents/risk_analyst_output_v1.schema.json`
- Manager 输出 schema: `schemas/agents/manager_output_v1.schema.json`

兼容策略

- schema_version 固定为 v1
- 新增字段只允许向后兼容 consumer 必须忽略未知字段

### Agent 协作对话格式

用途

- Manager 向其他 Agent 下发指令并等待回执
- 让协作闭环可测试可回放可审计

当前落地

- 指令 schema: `schemas/agents/agent_command_v1.schema.json`
- 回执 schema: `schemas/agents/agent_receipt_v1.schema.json`

字段约定

- run_id: 串联一次完整状态机运行
- command_id: 串联一次指令与回执
- target_agent: system_engineer risk_analyst manager
- action: 约定动作名 例如 collect_metrics query_positions_by_desk search_similar_alerts write_alert
- params: 动作参数对象
  - side_effect action 需要包含 approval 字段 由状态机注入
  - side_effect action 会包含 _event 字段 由状态机注入 用于 per-action policy 判断
- timeout_ms: 超时时间
- expected_output_schema: 期望的 output 结构标识, 用于质量门禁与兼容治理

approval 字段

- required: boolean
- approved: boolean
- reason: string or null
- note: string or null

回执约定

- ok: 是否执行成功
- evidence: 证据引用, 必须可追溯到 tool 或事件字段
- artifacts: 附件列表, 例如 metrics snapshot, query results, links
- latency_ms: 端到端执行耗时
- error: 失败时的结构化错误摘要
- output: 结构化输出, 由 expected_output_schema 约束

### Context Store

用途

- 保存一次 run 的共享上下文与同步记忆
- 用于 replay 与审计

当前落地

- 文件落盘形式, 每个 run_id 一个 json 文件
- 路径由 CONTEXT_STORE_DIR 控制 默认 data/context_store
- 写入内容包含 event_snapshot run_meta budget receipts rag hits agent outputs approval audit_records audit_db llm_meta_* final_output

### Audit records

用途

- 对 side_effect commands 生成审计记录
- 用于追责与回放

当前落地

- 状态机 Execute 节点生成 audit_records
- 同时写入 Context Store 顶层字段与 final_output.audit_records

字段

- audit_id: string
- ts_ms: number
- event_id: string
- correlation_id: string or null
- run_id: string
- command_id: string
- target_agent: string
- action: string
- actor: string
- approved: boolean
- approved_by: string or null
- approval_reason: string or null
- ok: boolean
- error: string or null

### Governance metrics

用途

- 观测 RBAC 审批 side_effect 的运行状态

指标

- rm_rbac_denied_total{target_agent,action,capability}
- rm_approval_required_total{target_agent,action}
- rm_side_effect_executed_total{target_agent,action,ok}
- rm_budget_exceeded_total{type,node}
- rm_budget_remaining{type}

### Run meta

用途

- 记录一次 run 的 policy prompt tool versions
- 支持回放对比

字段

- policy_version
- tool_registry_version
- rbac_policy_version
- prompt_versions

### Budget

用途

- token tool time 预算与熔断
- 预算超限时写入 exceeded_type exceeded_reason 并触发降级输出

字段

- token_budget token_used
- tool_budget tool_used
- time_budget_ms elapsed_ms
- exceeded exceeded_type exceeded_node exceeded_reason

同步记忆落地

- 状态机会把 final_output 摘要写入 Chroma
- 默认 collection riskmonitor-memory 可用 CHROMA_MEMORY_COLLECTION 覆盖

### risk_alerts

用途

- risk engine 产生 breach 事件后发布
- webhook notifier 或其他下游消费并推送

说明

- 若采用 2A 方案, server 内部的 analyzer 与 notifier 使用进程内队列触发, 不依赖 risk_alerts
- risk_alerts 可以作为对外 fan out 的扩展能力, 便于后续拆分独立 notifier 服务

建议配置

- partitions: 3 起步
- key 建议: alert_id
- 语义: at least once

事件 schema

- schema_version: string, v1
- alert_id: string
- trace_id: string, 建议复用 request_id 或独立生成
- upstream_event_id: string, 对应 positions_cdc event_id
- desk: string
- severity: string, INFO WARNING CRITICAL
- alert_type: string, desk_delta_breach
- metric:
 - name: string, abs_delta
 - value: number
 - threshold: number
- as_of: string, ISO8601
- status: string, open
- message: string

## 事件驱动告警链路增量表

### processed_cdc_events

用途

- CDC consumer 的幂等去重表, 保证重放不会重复更新 desk 聚合或重复生成告警

建议字段

- event_id: VARCHAR(128) primary key
- processed_at: TIMESTAMP default current_timestamp
- topic: VARCHAR(128) nullable
- partition_id: INT nullable
- offset: BIGINT nullable

### desk_risk_state

用途

- desk 维度风险状态表, 用于实现 单 desk 超限只生成一次告警 的语义
- 该表记录当前 desk 是否处于 breach 状态, 以及关联的 active alert

建议字段

- desk: VARCHAR(100) primary key
- is_breached: BOOLEAN not null
- active_alert_id: VARCHAR(36) nullable
- last_metric_value: DECIMAL(20, 4) nullable
- last_threshold_value: DECIMAL(20, 4) nullable
- updated_at: TIMESTAMP default current_timestamp on update current_timestamp

## 设计约束

- topic schema 必须版本化, 新增字段只允许向后兼容
- consumer 以 event_id 做幂等, 避免重复告警
- positions_cdc key 为 position_id 但聚合口径以 desk 为第一维度, consumer 需维护 position 最新状态并支持 desk 迁移
