# 模块职责边界说明

本文档明确区分项目中 **Test（测试）** 和 **Evaluation（评估）** 两大模块的职责边界。

## 核心区别

| 维度 | Test (测试) | Evaluation (评估) |
|------|-------------|-------------------|
| **目的** | 检测项目功能是否正常工作 | 针对给定指标评估项目效果 |
| **触发时机** | 开发/CI 阶段自动运行 | 发布/优化阶段手动触发 |
| **判断标准** | 通过/失败 (Pass/Fail) | 指标数值与阈值对比 |
| **输出** | 测试报告、覆盖率 | 指标汇总、质量门禁 |

---

## 1. Test 模块 (`/tests/`)

### 职责
验证代码功能正确性，确保各组件按预期工作。

### 目录结构

```
tests/
├── unit/                          # 单元测试
│   ├── test_orchestrator_workflow.py   # 编排工作流功能测试
│   ├── test_llm_client.py              # LLM 客户端测试
│   ├── test_eval_gate.py               # 对 eval/gate.py 的测试 ✅
│   ├── test_eval_metrics.py            # 对 eval/metrics.py 的测试 ✅
│   └── ...
├── integration/                   # 集成测试
│   ├── test_alerts.py
│   ├── test_database.py
│   └── ...
├── smoke/                         # 冒烟测试
└── scenarios/                     # 场景测试
```

### 测试对象
- `tests/unit/test_eval_*.py` 测试的是 `/eval/` 目录下的评估模块功能
- 确保评估模块本身能正确工作（不是评估项目效果）

### 运行方式
```bash
make test              # 运行所有测试
pytest tests/unit/     # 运行单元测试
```

---

## 2. Evaluation 模块 (`/eval/`)

### 职责
与业务解耦的独立评估流水线，通过运行多组测试用例并收集指标来评估项目效果。

### 目录结构

```
eval/
├── case_schema.py        # 测试用例格式定义 (BenchmarkCase)
├── runner.py             # 评估执行器（调度用例、调用工作流、收集记录）
├── metrics.py            # 指标汇总（计算平均值、百分比等）
├── gate.py               # 质量门禁（对比指标与阈值）
├── gates/
│   └── default.json      # 门禁阈值配置
├── benchmarks/           # 测试语料（多组测试用例）
│   └── explainability_cases.jsonl
└── results/              # 评估结果
    ├── final.jsonl
    └── final.summary.json
```

### 与业务模块的交互

```
┌─────────────────────────────────────────────────────────────┐
│                     Evaluation Pipeline                      │
│                      (eval/ 目录)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │ case_schema  │→ │   runner     │→ │   metrics    │       │
│  │  (定义用例)   │  │ (调度执行)    │  │  (汇总指标)   │       │
│  └──────────────┘  └──────┬───────┘  └──────┬───────┘       │
│                           │                  │              │
│                           ▼                  ▼              │
│                  ┌──────────────────┐  ┌──────────┐         │
│                  │   Business API   │  │  gate    │         │
│                  │ (run_orchestrator │  │ (门禁)   │         │
│                  │  _workflow)       │  │          │         │
│                  └──────────────────┘  └──────────┘         │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                     Business Module                          │
│              (src/riskmonitor_multiagent/)                   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         orchestration/eval_adapter.py               │   │
│  │   (将工作流输出转换为评估记录格式，唯一交互点)         │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 评估指标体系

#### 传统指标 (Task Quality)
| 指标 | 说明 | 阈值 |
|------|------|------|
| `pass_rate` | 任务通过率 | > 0.9 |
| `step_reason_coverage` | 步骤理由覆盖率 | > 0.95 |
| `evidence_missing_rate` | 证据缺失率 | < 0.05 |
| `contract_fail_rate` | 契约失败率 | < 0.02 |
| `latency_ms_p95` | P95 延迟 | < 8000ms |
| `tokens_total` | Token 消耗 | < 50000 |

#### 协作/过程指标 (Collaboration & Process)
| 指标 | 全称 | 说明 | 阈值 |
|------|------|------|------|
| **IDS** | Information Diversity Score | 信息多样性 | > 0.3 |
| **UPR** | Unnecessary Path Ratio | 冗余路径比 | < 0.5 |
| **Milestone** | Milestone Achievement Rate | 里程碑达成率 | > 0.75 |

### 运行方式
```bash
make eval-run RUN_TAG=experiment-1        # 运行评估
make eval-gate RUN_TAG=experiment-1       # 质量门禁检查
make eval-compare BASE=run1 CAND=run2       # 对比两次运行
```

---

## 3. Scripts 模块 (`/scripts/`)

### 职责
提供便捷的命令行脚本，封装常用操作。

### 结构
```
scripts/
├── eval/                     # 评估相关脚本
│   ├── run_benchmark.py      # 运行基准测试
│   ├── quality_gate.py      # 质量门禁检查
│   └── compare_runs.py       # 对比运行结果
├── health_check.py           # 健康检查
└── run_mcp_stdio.py          # MCP 服务启动
```

---

## 4. 关键边界原则

### 原则 1: 测试模块不评估效果
- `tests/` 只验证功能正确性
- 不计算 IDS、UPR 等效果指标
- 不对指标做阈值判断

### 原则 2: 评估模块不测试功能
- `eval/` 假设业务功能已正常工作
- 不验证单个函数的正确性
- 只收集和汇总运行指标

### 原则 3: 单向依赖
```
tests/ ────────┐
              ├──→ src/
eval/ ─────────┘
         ↑
         │ (通过 eval_adapter.py 接口)
```

### 原则 4: 业务模块仅暴露一个评估接口
```python
# src/riskmonitor_multiagent/orchestration/eval_adapter.py
# 这是业务侧唯一与评估相关的模块

def workflow_output_to_eval_record(
    out: dict,
    case_id: str,
    tags: list[str],
    config: dict,
) -> dict:
    """将工作流输出转换为评估记录格式."""
    ...
```

---

## 5. 常见问题

### Q: `tests/unit/test_eval_*.py` 为什么测试 eval 模块？
**A**: 这些测试验证评估模块的功能是否正确（例如 `gate.py` 是否能正确判断阈值），不是评估项目效果。

### Q: 如何添加新的效果评估指标？
**A**:
1. 在 `eval_adapter.py` 中计算指标（业务侧）
2. 在 `eval/metrics.py` 中汇总（评估侧）
3. 在 `eval/gate.py` 中设置阈值（评估侧）
4. 在 `eval/gates/default.json` 中配置（评估侧）

### Q: 如何添加新的功能测试？
**A**:
1. 在 `tests/unit/` 或 `tests/integration/` 添加测试文件
2. 使用 pytest 编写断言
3. 运行 `pytest tests/unit/test_xxx.py` 验证

---

## 6. 修改历史

| 日期 | 修改内容 |
|------|---------|
| 2025-03-10 | 删除空的 `src/riskmonitor_multiagent/eval/` 目录，明确模块边界 |
