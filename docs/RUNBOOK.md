# Runbook

这份 Runbook 面向本地开发与类生产排障  
目标是让你能在 10 分钟内复现风暴压测, 看见 metrics, 并能定位常见故障  

## 启动顺序

1. 启动基础设施(MySQL, Kafka, Debezium, Kafka UI)
- 使用项目提供的 docker compose profile infra

2. 启动 MCP Server
- 提供 /health /ready /metrics

3. 启动 Sentinel
- 消费 `risk.positions.cdc`
- 触发状态机编排并写入 Context Store

4. 启动 Chroma(可选)
- 如果要验证同步记忆与相似检索, 需要启动 Chroma

## 风暴压测(Storm)

目标: 短时间内大量 positions update, 触发多个 desk breach  

### 注入脚本

脚本: [storm_positions.py](../scripts/stress/storm_positions.py)

示例:
- 注入 1000 条更新, 每 0ms 一条

```bash
python3 scripts/stress/storm_positions.py --n 1000 --sleep-ms 0 --breach-delta 120000
```

观测点:
- Kafka UI 里 topic `risk.positions.cdc` 的写入速率
- Sentinel 日志是否持续输出 breach
- Context Store 是否持续写入 run_*.json
- /metrics 是否出现 pipeline 节点延迟与 LLM 指标

## 指标查看

### /metrics
- MCP Server 暴露的 Prometheus 指标端点
- 指标清单见 [OBSERVABILITY.md](OBSERVABILITY.md)

重点指标:
- rm_kafka_lag_ms: CDC lag(估算)
- rm_kafka_consumer_lag{topic,partition}: consumer lag(基于 end_offset - current_offset)
- rm_sentinel_messages_total, rm_sentinel_breaches_total
- rm_pipeline_total_ms_p95, rm_pipeline_node_ms_p95{node}
- rm_llm_errors_total{code}, rm_llm_tokens_total{type}
- rm_chroma_query_ms_p95{collection}, rm_chroma_hits_total{collection}

## 故障演练

### LLM 不可用
预期: 仍能产出结构化决策  
原因: Agent ask_json 在 OpenRouter 异常时会 fallback  

排查:
- /metrics 查看 rm_llm_errors_total 是否上升
- Context Store 里 analyst/manager 输出是否为 fallback 的最小结构

### Chroma 不可用
预期: 仍可运行, 但 output 标注 memory 不可用  

排查:
- 状态机 RetrieveContext 会记录 memory_query_error
- Execute 会记录 memory_write_ok=false 与 memory_write_error

## 常见问题

### /ready 返回 not_ready
- 检查 MYSQL_PASSWORD 是否配置
- MySQL 容器是否启动

### Sentinel 没有消费到消息
- 检查 KAFKA_BOOTSTRAP_SERVERS
- Kafka topic 是否存在 risk.positions.cdc
- Debezium connector 是否正常

