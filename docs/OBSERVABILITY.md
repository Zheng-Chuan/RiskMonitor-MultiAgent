# Observability

本项目对外暴露 Prometheus 指标, 用于排障与性能监控  
指标实现与业务代码隔离在 `riskmonitor_multiagent.observability` 模块  
`/metrics` 端点会聚合原有 MCP 指标与新增的系统指标  

入口

- 指标模块: [metrics.py](../src/riskmonitor_multiagent/observability/metrics.py)
- /metrics 端点: [server.py](../src/riskmonitor_multiagent/server.py)

## 指标覆盖范围

### CDC 延迟
- rm_kafka_lag_ms gauge
  - 通过 message_ts_ms 估算 lag, 在状态机 RetrieveContext 写入

### Kafka consumer lag
- rm_kafka_consumer_lag gauge labels: topic, partition
  - Sentinel 使用 end_offset - current_offset 估算

### Sentinel 吞吐
- rm_sentinel_messages_total counter
- rm_sentinel_breaches_total counter
- rm_sentinel_process_message_ms_avg p95
- rm_sentinel_trigger_alert_ms_avg p95

### pipeline latency(分节点)
- rm_pipeline_total_ms_avg p95
- rm_pipeline_node_ms_avg p95 labels: node

### LLM 调用成功率与 token 消耗
- rm_llm_calls_total counter labels: agent, model
- rm_llm_errors_total counter labels: agent, model, code
- rm_llm_call_ms_avg p95 labels: agent, model
- rm_llm_tokens_total counter labels: agent, model, type

### Chroma query p95 与命中率
- rm_chroma_query_ms_avg p95 labels: collection
- rm_chroma_queries_total counter labels: collection
- rm_chroma_hits_total counter labels: collection

## 约定

- counter 只增不减, 用于统计成功率与总量
- gauge 用于记录瞬时值, 例如 rm_kafka_lag_ms
- ms 指标以 avg p95 count 三元组输出, 便于快速定位慢点
