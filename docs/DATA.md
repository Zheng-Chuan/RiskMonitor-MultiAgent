# 数据字典

本文件记录当前项目已落地的 MySQL schema 与 Kafka topic 设计

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

- db/migrations/003_create_alerts_table.sql

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

索引

- idx_request_id on request_id
- idx_alert_type on alert_type
- idx_desk on desk
- idx_created_at on created_at
- idx_severity on severity

## Kafka topics

本项目当前仅保留 2 个 topic

### positions_cdc

用途

- Debezium 从 MySQL binlog 捕获 positions 表变更
- CDC consumer 消费后触发 desk 级风险计算与 breach 判断

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

### risk_alerts

用途

- risk engine 产生 breach 事件后发布
- webhook notifier 或其他下游消费并推送

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

## 设计约束

- topic schema 必须版本化, 新增字段只允许向后兼容
- consumer 以 event_id 做幂等, 避免重复告警
- positions_cdc key 为 position_id 但聚合口径以 desk 为第一维度, consumer 需维护 position 最新状态并支持 desk 迁移
