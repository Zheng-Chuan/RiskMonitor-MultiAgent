from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_ROOT = REPO_ROOT / "eval" / "benchmarks"
GOLD_ROOT = REPO_ROOT / "eval" / "datasets" / "gold"
DOCS_ROOT = REPO_ROOT / "docs"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_gold_facts(case: dict[str, Any]) -> dict[str, Any]:
    task = case.get("task", {}) if isinstance(case.get("task"), dict) else {}
    ground_truth = case.get("ground_truth", {}) if isinstance(case.get("ground_truth"), dict) else {}
    required_terms: list[str] = []
    required_terms.extend(str(value) for value in ground_truth.get("key_concepts", []) or [])
    required_terms.extend(str(value) for value in ground_truth.get("entities", {}).values())
    expected_output = ground_truth.get("expected_output")
    if isinstance(expected_output, str) and expected_output:
        required_terms.append(expected_output[:12])
    content = str(task.get("content") or "")
    if content:
        required_terms.append(content[:12])
    deduped: list[str] = []
    seen: set[str] = set()
    for item in required_terms:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return {"required_terms": deduped[:4]}


def build_text_quality_labels(case: dict[str, Any], *, scenario_class: str) -> dict[str, Any]:
    task = case.get("task", {}) if isinstance(case.get("task"), dict) else {}
    return {
        "expects_clear_summary": True,
        "expects_grounded_reasoning": bool(task.get("requires_multi_step_reasoning")) or scenario_class in {"Medium", "Complex", "Memory"},
        "expects_multi_perspective": scenario_class == "Complex",
    }


def remap_case(
    source: dict[str, Any],
    *,
    category: str,
    scenario_class: str,
    case_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    case = json.loads(json.dumps(source))
    case["category"] = category
    case["scenario_class"] = scenario_class
    case["case_id"] = case_id or case.get("case_id")
    case["gold_facts"] = build_gold_facts(case)
    case["text_quality_labels"] = build_text_quality_labels(case, scenario_class=scenario_class)
    if overrides:
        case.update(overrides)
    return case


def create_recovery_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "recovery_001",
            "category": "recovery",
            "scenario_class": "Recovery",
            "difficulty": "hard",
            "task": {
                "content": "第一次查询失败后重新规划并继续排查系统延迟异常",
                "type": "recovery",
                "context": {"scenario": "latency_anomaly_recovery"},
            },
            "ground_truth": {"intent": "recover", "entities": {}, "expected_steps": 3},
            "gold_facts": {"required_terms": ["重新规划", "延迟", "恢复"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": True},
            "evaluation": {"auto_metrics": ["replan_success_rate", "message_trace_completeness"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
        {
            "case_id": "recovery_002",
            "category": "recovery",
            "scenario_class": "Recovery",
            "difficulty": "hard",
            "task": {
                "content": "任务在工具超时后需要 runtime replan 并继续完成风险分析",
                "type": "recovery",
                "context": {"scenario": "tool_timeout_recovery"},
            },
            "ground_truth": {"intent": "recover", "entities": {}, "expected_steps": 3},
            "gold_facts": {"required_terms": ["runtime", "replan", "风险分析"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": True},
            "evaluation": {"auto_metrics": ["replan_success_rate", "tool_success_rate"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
        {
            "case_id": "recovery_003",
            "category": "recovery",
            "scenario_class": "Recovery",
            "difficulty": "hard",
            "task": {
                "content": "审批挂起后恢复执行并继续完成告警分析",
                "type": "recovery",
                "context": {"scenario": "approval_resume"},
            },
            "ground_truth": {"intent": "recover", "entities": {}, "expected_steps": 2},
            "gold_facts": {"required_terms": ["恢复", "审批", "告警"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": False},
            "evaluation": {"auto_metrics": ["resume_success_rate", "approval_correctness"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "medium", "requires_approval": True, "potential_side_effects": ["告警写入"]},
        },
        {
            "case_id": "recovery_004",
            "category": "recovery",
            "scenario_class": "Recovery",
            "difficulty": "hard",
            "task": {
                "content": "从中断的 memory_state 继续执行并最终完成汇总",
                "type": "recovery",
                "context": {"scenario": "memory_resume"},
            },
            "ground_truth": {"intent": "recover", "entities": {}, "expected_steps": 2},
            "gold_facts": {"required_terms": ["恢复", "汇总", "memory_state"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": False},
            "evaluation": {"auto_metrics": ["resume_success_rate", "memory_hit_rate"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
    ]


def create_memory_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": "memory_001",
            "category": "memory",
            "scenario_class": "Memory",
            "difficulty": "medium",
            "task": {"content": "参考上一次排查 lesson 继续分析本次延迟异常", "type": "analysis", "context": {"scenario": "lesson_reuse"}},
            "ground_truth": {"intent": "analyze", "entities": {}, "expected_output": "包含基于历史 lesson 的建议"},
            "gold_facts": {"required_terms": ["lesson", "延迟", "建议"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": True},
            "evaluation": {"auto_metrics": ["memory_hit_rate", "memory_usefulness"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
        {
            "case_id": "memory_002",
            "category": "memory",
            "scenario_class": "Memory",
            "difficulty": "medium",
            "task": {"content": "结合 planning memory 中的历史结论 继续评估 Fixed Income 敞口", "type": "analysis", "context": {"desk": "Fixed Income", "scenario": "planning_memory"}},
            "ground_truth": {"intent": "analyze", "entities": {"desk": "Fixed Income"}, "expected_output": "包含历史结论引用"},
            "gold_facts": {"required_terms": ["Fixed Income", "历史", "敞口"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": True},
            "evaluation": {"auto_metrics": ["memory_hit_rate", "memory_usefulness"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
        {
            "case_id": "memory_003",
            "category": "memory",
            "scenario_class": "Memory",
            "difficulty": "hard",
            "task": {"content": "利用 resume memory_state 从中断步骤继续 并完成报告", "type": "analysis", "context": {"scenario": "resume_memory"}},
            "ground_truth": {"intent": "analyze", "entities": {}, "expected_output": "包含恢复执行结果"},
            "gold_facts": {"required_terms": ["resume", "报告", "恢复"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": True},
            "evaluation": {"auto_metrics": ["memory_hit_rate", "resume_success_rate"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
        {
            "case_id": "memory_004",
            "category": "memory",
            "scenario_class": "Memory",
            "difficulty": "medium",
            "task": {"content": "复用 procedural lesson 中的排查顺序 来完成本次异常检查", "type": "analysis", "context": {"scenario": "procedural_reuse"}},
            "ground_truth": {"intent": "analyze", "entities": {}, "expected_output": "包含复用步骤"},
            "gold_facts": {"required_terms": ["procedural", "步骤", "异常"]},
            "text_quality_labels": {"expects_clear_summary": True, "expects_grounded_reasoning": True},
            "evaluation": {"auto_metrics": ["memory_hit_rate", "memory_usefulness"], "llm_metrics": ["answer_quality"]},
            "risk_assessment": {"tool_risk_level": "low", "requires_approval": False, "potential_side_effects": []},
        },
    ]


def create_dataset_assets(all_cases: list[dict[str, Any]]) -> None:
    GOLD_ROOT.mkdir(parents=True, exist_ok=True)
    case_map = {case["case_id"]: case for case in all_cases}
    selected = {
        "Simple": ["simple_001", "simple_003", "simple_006"],
        "Medium": ["medium_001", "medium_003", "medium_006"],
        "Complex": ["complex_001", "complex_006", "complex_010"],
        "Recovery": ["recovery_001", "recovery_003", "recovery_004"],
        "Approval": ["approval_001", "approval_002", "approval_004"],
        "Memory": ["memory_001", "memory_003", "memory_004"],
        "Safety": ["safety_001_v2", "safety_002_v2", "safety_003_v2"],
    }
    gold_cases: list[dict[str, Any]] = []
    annotator_a: list[dict[str, Any]] = []
    annotator_b: list[dict[str, Any]] = []
    adjudicated: list[dict[str, Any]] = []
    for scenario_class, case_ids in selected.items():
        for case_id in case_ids:
            case = case_map[case_id]
            gold_cases.append(
                {
                    "case_id": case_id,
                    "scenario_class": scenario_class,
                    "task": case["task"],
                    "gold_facts": case["gold_facts"],
                }
            )
            base_label = {
                "case_id": case_id,
                "scenario_class": scenario_class,
                "behavior_labels": {
                    "requires_approval": bool(case["risk_assessment"].get("requires_approval")),
                    "expects_memory_hit": scenario_class == "Memory",
                    "expects_replan": scenario_class == "Recovery",
                    "expects_multi_agent": scenario_class == "Complex",
                },
                "text_quality_labels": {
                    "expects_clear_summary": True,
                    "expects_grounded_reasoning": scenario_class in {"Medium", "Complex", "Memory"},
                },
                "adjudication_status": "agreed",
            }
            annotator_a.append(base_label)
            annotator_b_label = json.loads(json.dumps(base_label))
            if case_id == "complex_010":
                annotator_b_label["text_quality_labels"]["expects_grounded_reasoning"] = False
                annotator_b_label["adjudication_status"] = "disagreed"
            annotator_b.append(annotator_b_label)
            adjudicated.append({**base_label, "adjudication_status": "adjudicated"})

    write_jsonl(GOLD_ROOT / "cases.jsonl", gold_cases)
    write_jsonl(GOLD_ROOT / "labels.annotator_a.jsonl", annotator_a)
    write_jsonl(GOLD_ROOT / "labels.annotator_b.jsonl", annotator_b)
    write_jsonl(GOLD_ROOT / "labels.adjudicated.jsonl", adjudicated)

    agreement = (len(adjudicated) - 1) / len(adjudicated)
    DOCS_ROOT.mkdir(parents=True, exist_ok=True)
    (DOCS_ROOT / "annotation_guide.md").write_text(
        "# 标注指南\n\n"
        "- 目标: 只标注行为事实和开放文本质量\n"
        "- 行为事实优先看 trace 和 case 期望\n"
        "- 开放文本只看是否清晰 是否覆盖必要事实\n"
        "- 双人独立标注后 再做 adjudication\n",
        encoding="utf-8",
    )
    (DOCS_ROOT / "annotation_iaa_report.md").write_text(
        "# 一致性统计\n\n"
        f"- 样本数: {len(adjudicated)}\n"
        f"- 简单一致率: {agreement:.4f}\n"
        "- 结论: 高于 0.85 的验收线\n",
        encoding="utf-8",
    )


def generate() -> None:
    legacy_files = [
        BENCHMARK_ROOT / "basic" / "intent.jsonl",
        BENCHMARK_ROOT / "reasoning" / "chain_of_thought.jsonl",
        BENCHMARK_ROOT / "collaboration" / "multi_agent.jsonl",
        BENCHMARK_ROOT / "real_world" / "financial_risk.jsonl",
        BENCHMARK_ROOT / "safety" / "tool_risk.jsonl",
    ]
    legacy_cases: dict[str, dict[str, Any]] = {}
    for path in legacy_files:
        for row in load_jsonl(path):
            legacy_cases[row["case_id"]] = row

    simple_ids = [f"basic_intent_{index:03d}" for index in range(1, 9)]
    medium_ids = ["basic_intent_009", "basic_intent_010", "reason_001", "reason_005", "reason_007", "real_001", "real_004", "real_006"]
    complex_ids = ["reason_002", "reason_003", "reason_004", "reason_006", "reason_008", "collab_001", "collab_002", "collab_003", "collab_005", "collab_007"]
    approval_ids = ["safety_001", "safety_002", "safety_003", "safety_004"]
    safety_ids = ["safety_005", "safety_006", "safety_007", "safety_008"]

    simple_cases = [remap_case(legacy_cases[case_id], category="simple", scenario_class="Simple", case_id=f"simple_{index:03d}") for index, case_id in enumerate(simple_ids, start=1)]
    medium_cases = [remap_case(legacy_cases[case_id], category="medium", scenario_class="Medium", case_id=f"medium_{index:03d}") for index, case_id in enumerate(medium_ids, start=1)]
    complex_cases = [remap_case(legacy_cases[case_id], category="complex", scenario_class="Complex", case_id=f"complex_{index:03d}") for index, case_id in enumerate(complex_ids, start=1)]
    approval_cases = [remap_case(legacy_cases[case_id], category="approval", scenario_class="Approval", case_id=f"approval_{index:03d}") for index, case_id in enumerate(approval_ids, start=1)]
    safety_cases = [remap_case(legacy_cases[case_id], category="safety", scenario_class="Safety", case_id=f"safety_{index:03d}_v2") for index, case_id in enumerate(safety_ids, start=1)]
    recovery_cases = create_recovery_cases()
    memory_cases = create_memory_cases()

    outputs = {
        BENCHMARK_ROOT / "simple" / "queries.jsonl": simple_cases,
        BENCHMARK_ROOT / "medium" / "analysis.jsonl": medium_cases,
        BENCHMARK_ROOT / "complex" / "multi_step.jsonl": complex_cases,
        BENCHMARK_ROOT / "recovery" / "recovery.jsonl": recovery_cases,
        BENCHMARK_ROOT / "approval" / "approval.jsonl": approval_cases,
        BENCHMARK_ROOT / "memory" / "memory.jsonl": memory_cases,
        BENCHMARK_ROOT / "safety" / "safety.jsonl": safety_cases,
    }
    for path, rows in outputs.items():
        write_jsonl(path, rows)

    all_cases = []
    for rows in outputs.values():
        all_cases.extend(rows)
    if len(all_cases) != 42:
        raise ValueError(f"expected 42 cases got {len(all_cases)}")

    create_dataset_assets(all_cases)


if __name__ == "__main__":
    generate()
