# RiskMonitor MultiAgent 监控配置

## 快速启动

### 启动监控栈

```bash
# 只启动 Prometheus 和 Grafana
docker-compose --profile monitoring up -d prometheus grafana

# 或者启动所有服务 (包括监控)
docker-compose --profile monitoring up -d
```

### 访问服务

- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000 (admin/admin)

### 停止监控

```bash
docker-compose --profile monitoring stop prometheus grafana
```

## 资源限制

所有监控服务都已配置内存限制:

| 服务 | 内存限制 | 磁盘限制 |
|------|----------|----------|
| Prometheus | 512MB | 2GB (7 天数据) |
| Grafana | 512MB | 动态 |

## 配置说明

### Prometheus 配置

配置文件位于：`monitoring/prometheus.yml`

主要配置项:
- `scrape_interval`: 抓取间隔 (默认 15s)
- `retention.time`: 数据保留时间 (7 天)
- `retention.size`: 数据保留大小 (2GB)

### Grafana 配置

- 数据源自动配置：`monitoring/grafana/provisioning/datasources/prometheus.yml`
- 默认用户名/密码：`admin/admin`

## 监控指标

### 应用指标暴露

在代码中使用 metrics:

```python
from riskmonitor_multiagent.observability.metrics import inc_counter, observe_ms

# 计数器
inc_counter("proactive_agent_runs_total")

# 直方图 (延迟)
observe_ms("proactive_agent_latency_ms", latency_ms)

# 仪表板 (当前值)
set_gauge("agent_active_count", active_count)
```

### 关键指标

1. **Agent 性能指标**
   - `proactive_agent_runs_total` - Agent 运行次数
   - `proactive_agent_latency_ms` - Agent 响应延迟
   - `react_steps_count` - ReAct 步骤数量

2. **BDI 状态指标**
   - `agent_beliefs_count` - 信念数量
   - `agent_desires_count` - 愿望数量
   - `agent_intentions_count` - 意图数量

3. **LLM 成本指标**
   - `llm_tokens_total` - Token 使用总量
   - `llm_cost_total` - LLM 总成本
   - `llm_cache_hit_rate` - 缓存命中率

## 常用查询

### Prometheus 查询示例

```promql
# Agent 运行成功率
rate(proactive_agent_runs_success_total[5m]) / rate(proactive_agent_runs_total[5m])

# P95 延迟
histogram_quantile(0.95, rate(proactive_agent_latency_ms_bucket[5m]))

# Token 使用趋势
rate(llm_tokens_total[5m])
```

### Grafana 面板

导入现成的 Dashboard:
1. 访问 Grafana → Dashboards → Import
2. 输入 Dashboard ID:
   - 10280 (Prometheus 自身监控)
   - 763 (Redis 监控)
   - 7362 (MySQL 监控)

## 故障排查

### Prometheus 无法抓取应用指标

```bash
# 检查应用是否暴露 metrics 端点
curl http://localhost:8000/metrics

# 检查 Prometheus 配置
docker-compose exec prometheus cat /etc/prometheus/prometheus.yml

# 重新加载 Prometheus 配置
curl -X POST http://localhost:9090/-/reload
```

### Grafana 无法连接 Prometheus

```bash
# 检查 Prometheus 是否运行
docker-compose ps prometheus

# 检查网络连接
docker-compose exec grafana ping prometheus
```

## 环境变量

可以通过 `.env` 文件配置:

```bash
# 修改默认密码
GF_SECURITY_ADMIN_USER=your_user
GF_SECURITY_ADMIN_PASSWORD=your_password

# 修改 Prometheus 保留策略
PROMETHEUS_RETENTION_DAYS=14
PROMETHEUS_RETENTION_SIZE=4GB
```

## 生产环境建议

1. **增加内存限制**: 生产环境建议 Prometheus 至少 1GB
2. **延长保留时间**: 根据需求调整 `retention.time`
3. **启用 HTTPS**: 使用反向代理 (Nginx) 启用 HTTPS
4. **配置告警**: 添加 alerting 规则
5. **备份数据**: 定期备份 `prometheus_data` 和 `grafana_data` 卷

## 参考资源

- [Prometheus 官方文档](https://prometheus.io/docs/)
- [Grafana 官方文档](https://grafana.com/docs/)
- [Prometheus 查询语言](https://prometheus.io/docs/prometheus/latest/querying/basics/)
