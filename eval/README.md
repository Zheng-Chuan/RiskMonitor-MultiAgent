# 评估流水线（与业务解耦）

本目录为**评估流水线**，与业务模块（`src/riskmonitor_multiagent`）相互独立。

## 边界

- **业务侧**：只提供两样东西供评估使用：
  1. `run_orchestrator_workflow(task)`：执行一次工作流
  2. `workflow_output_to_eval_record(out, case_id=..., tags=..., config=...)`：将工作流返回转为评估记录（定义在 `src/.../orchestration/eval_adapter.py`）
- **评估侧**：本目录下的 `runner`、`metrics`、`gate`、`case_schema` 只依赖上述接口，不感知工作流内部结构（intent、artifacts、receipts 等由 adapter 在业务侧解析）。

## 目录结构

- `case_schema.py`：用例格式与加载（BenchmarkCase、load_benchmark_cases）
- `metrics.py`：汇总指标（summarize_benchmark_records）
- `gate.py`：质量门禁（evaluate_quality_gate、default_gate_thresholds）
- `runner.py`：调度 case、调工作流、组 record、汇总
- `benchmarks/`：语料（如 explainability_cases.jsonl）
- `results/`：运行结果（*.jsonl、*.summary.json）
- `gates/`：门禁阈值配置（如 default.json）

## 运行

从项目根目录执行（会同时把项目根和 `src` 加入 path）：

```bash
make eval-run RUN_TAG=my-run
make eval-gate RUN_TAG=my-run
make eval-compare BASE=run1 CAND=run2
```

## 评估指标体系 (Industry Best Practice)

本评估流水线参照 **GEMMAS**、**MultiAgentBench**、**REALM-Bench** 等行业基准，建立两大维度：

### 1. 传统指标 (Task Quality)

| 指标 | 说明 | 理想值 |
|------|------|--------|
| `pass_rate` | 任务通过率 | > 0.9 |
| `step_reason_coverage` | 步骤理由覆盖率 | > 0.95 |
| `evidence_missing_rate` | 证据缺失率 | < 0.05 |
| `receipt_binding_rate` | 回执绑定率 | > 0.95 |
| `contract_fail_rate` | 契约失败率 | < 0.02 |
| `latency_ms_p95` | P95 延迟 | < 8000ms |
| `tokens_total` | 总 Token 消耗 | < 50000 |
| `stability_ok_rate` | 稳定性（多轮一致性）| 1.0 |

### 2. 协作/过程指标 (Collaboration & Process Metrics)

参照 **GEMMAS** (Graph-based Evaluation Metrics for Multi-Agent Systems) 和 **MultiAgentBench**:

| 指标 | 全称 | 说明 | 计算方式 | 理想值 |
|------|------|------|----------|--------|
| **IDS** | Information Diversity Score | 信息多样性：步骤间输出的语义差异度。高 IDS 表示各 Agent 贡献的信息互补而非重复。 | 基于各 step output 的 key 集合计算 1 - 平均 Jaccard 相似度 | > 0.3 (越高越好) |
| **UPR** | Unnecessary Path Ratio | 冗余路径比：反映执行路径的精简程度。低 UPR 表示没有多余的降级/重试步骤。 | degraded 步骤数 / 总步骤数 | < 0.5 (越低越好) |
| **Milestone** | Milestone Achievement Rate | 里程碑达成率：关键节点（Intent → Plan → Execution → Finalize）的完成比例。 | 4 个里程碑中达成的比例 | > 0.75 (越高越好) |

### 指标来源

- **GEMMAS**: Graph-based Evaluation Metrics for Multi-Agent Systems (2025)
- **MultiAgentBench**: ACL 2025, 多智能体协作评估基准
- **REALM-Bench**: 真实世界多智能体规划基准

## 扩展方式

在保持「评估流水线只消费业务输出」的前提下：

1. **业务侧**: 在 `src/.../orchestration/eval_adapter.py` 的 `workflow_output_to_eval_record` 中，从工作流内部状态计算新指标（如步骤间消息多样性、冗余路径比、里程碑达成），写入 `quality` 字段。
2. **评估侧**: 在 `eval/metrics.py` 中对新指标做汇总（加入 `summarize_benchmark_records`），在 `eval/gate.py` 中增加对应门禁阈值，在 `eval/gates/default.json` 中配置阈值。

这样协作/过程类指标仍由业务侧按契约提供，评估侧只做汇总与门禁，不混入业务逻辑。
