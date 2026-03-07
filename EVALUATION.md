# 评测与优化手册

## 目标

本手册用于统一回答三个问题

- 指标代表什么
- 如何做对比实验和提升实验
- 如何解读仓库已有实验数据

## 评测入口

```bash
make eval-run RUN_TAG=baseline
make eval-gate RUN_TAG=baseline
make eval-compare BASE=baseline CAND=candidate
```

产物目录

- `eval/results/<run_tag>.jsonl` 单case记录
- `eval/results/<run_tag>.summary.json` 聚合指标
- `eval/results/<run_tag>.gate.json` 质量闸门结果
- `eval/results/<cand>.diff.json` 与 base 的差异分析

## 指标含义

### 可解释性与契约质量

- `step_reason_coverage` 计划步骤中包含 reason 的覆盖率 越高越好
- `evidence_missing_rate` 输出中缺少 evidence 引用的比例 越低越好
- `receipt_binding_rate` evidence 引用 command_id 与实际 receipts 一致率 越高越好
- `contract_fail_rate` 输出契约校验失败比例 越低越好
- `explainability_score` 由上述 4 项组合而成的总体解释性分数 越高越好

### 性能与稳定性

- `latency_ms_avg` 平均时延 越低越好
- `latency_ms_p95` P95 时延 越低越好
- `stability_ok_rate` 同一 case 多次重复执行结果稳定率 越高越好

### 治理与成本

- `approval_required_rate` 触发审批比例 反映风险动作门禁强度
- `governance_blocked_avg` 平均治理阻断次数 越低越好
- `degraded_avg` 平均降级次数 越低越好
- `tokens_total` 总 token 消耗 越低越好

### 业务一致性

- `breach_hit_consistency` breach 与 alerts 对齐一致性 越高越好
- `alert_write_success_rate` side_effect 写入成功率 越高越好

## 质量闸门默认阈值

- `min_step_reason_coverage = 0.95`
- `max_evidence_missing_rate = 0.05`
- `min_receipt_binding_rate = 0.95`
- `max_contract_fail_rate = 0.02`
- `max_latency_ms_p95 = 8000`
- `max_tokens_total = 50000`
- `min_stability_ok_rate = 1.0`

当任一约束不满足时 gate 直接 fail

## 对比实验方案

### 方案 A 成本策略对比

目的

- 对比 strict 与 balanced 预算策略下的质量与时延变化

执行

```bash
make eval-run RUN_TAG=cost_strict BUDGET_PROFILE=strict REPEATS=2
make eval-run RUN_TAG=cost_balanced BUDGET_PROFILE=balanced REPEATS=2
make eval-compare BASE=cost_strict CAND=cost_balanced
make eval-gate RUN_TAG=cost_balanced
```

观察重点

- 先看 `pass_rate` 是否下降
- 再看 `latency_ms_p95` 是否改善
- 最后看 `evidence_missing_rate` 与 `contract_fail_rate` 是否保持不恶化

### 方案 B 审批策略对比

目的

- 比较 `HITL_AUTO_APPROVE=1` 与 `HITL_AUTO_APPROVE=0` 对解释性和时延的影响

执行

```bash
make eval-run RUN_TAG=smoke_eval HITL=1
make eval-run RUN_TAG=smoke_eval_hitl0 HITL=0
make eval-compare BASE=smoke_eval CAND=smoke_eval_hitl0
```

观察重点

- `evidence_missing_rate` 是否上升
- `explainability_score` 是否下降
- `latency_ms_p95` 是否上升

## 提升实验方案

### 方案 1 解释性优先

- 动作 增加 plan_step reason 完整性检查与 evidence 回填
- 目标 `evidence_missing_rate <= 0.05` 且 `explainability_score >= 0.95`
- 风险 时延可能上升

### 方案 2 性能优先

- 动作 减少不必要 replan 轮次 控制 `ORCH_MAX_EXEC_ROUNDS`
- 目标 降低 `latency_ms_p95`
- 风险 过度收敛可能影响覆盖率

### 方案 3 治理优先

- 动作 强化 side_effect 审批和最小严重级别策略
- 目标 将高风险动作稳定留在审批门内
- 风险 人工确认比例上升

## 仓库已有实验数据小结

### 成本策略对比

来自 `cost_strict.summary.json` 与 `cost_balanced.summary.json`

- 两组 `pass_rate` 都是 `1.0`
- `cost_balanced` 的 `latency_ms_avg` 从 `320.683549` 降到 `296.922701`
- `cost_balanced` 的 `latency_ms_p95` 从 `721.938792` 降到 `339.858`
- 解释性核心指标保持不变 `step_reason_coverage=1.0` `evidence_missing_rate=0.0` `contract_fail_rate=0.0`

结论

- 在当前基准集上 balanced 相比 strict 取得了更低时延且未损伤解释性质量

### 审批策略对比

来自 `smoke_eval.summary.json` 与 `smoke_eval_hitl0.summary.json`

- 两组 `pass_rate` 都是 `1.0`
- `HITL=0` 时 `evidence_missing_rate` 从 `0.0` 上升到 `0.571429`
- `HITL=0` 时 `explainability_score` 从 `1.0` 下降到 `0.857143`
- `HITL=0` 时 `latency_ms_p95` 从 `523.439125` 升到 `782.11`

结论

- 在当前样本下关闭自动审批并未降低通过率 但解释性与时延表现变差

## 推荐验收顺序

```bash
make test-all
pytest tests/smoke/ -v --tb=short
make eval-run RUN_TAG=baseline
make eval-gate RUN_TAG=baseline
```

通过标准

- 测试全绿
- gate 通过
- 对比实验中无关键质量指标退化
