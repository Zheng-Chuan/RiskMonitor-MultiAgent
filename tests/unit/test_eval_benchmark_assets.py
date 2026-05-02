import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from eval.cli import load_all_cases
from eval.scripts.compute_iaa import compute_simple_agreement


def test_primary_benchmark_taxonomy_has_42_cases() -> None:
    cases = load_all_cases(str(project_root / "eval" / "benchmarks"))
    assert len(cases) == 42

    category_counts: dict[str, int] = {}
    for case in cases:
        category_counts[case.category] = category_counts.get(case.category, 0) + 1

    expected_categories = {"simple", "medium", "complex", "recovery", "approval", "memory", "safety"}
    assert set(category_counts) == expected_categories
    for category in expected_categories:
        assert category_counts[category] >= 4


def test_gold_annotation_assets_cover_all_scenarios() -> None:
    gold_dir = project_root / "eval" / "datasets" / "gold"
    cases_path = gold_dir / "cases.jsonl"
    with cases_path.open("r", encoding="utf-8") as file:
        rows = [json.loads(line) for line in file if line.strip()]

    counts: dict[str, int] = {}
    for row in rows:
        scenario = row["scenario_class"]
        counts[scenario] = counts.get(scenario, 0) + 1

    expected = {"Simple", "Medium", "Complex", "Recovery", "Approval", "Memory", "Safety"}
    assert set(counts) == expected
    for scenario in expected:
        assert counts[scenario] >= 3


def test_annotation_agreement_is_above_threshold() -> None:
    gold_dir = project_root / "eval" / "datasets" / "gold"
    result = compute_simple_agreement(
        gold_dir / "labels.annotator_a.jsonl",
        gold_dir / "labels.annotator_b.jsonl",
    )
    assert result["sample_count"] == 21.0
    assert result["agreement"] >= 0.85
