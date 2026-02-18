import json
from pathlib import Path


def test_week15_quality_gate_report_ok():
    from riskmonitor_multiagent.governance.week15_quality_gate import QualityGateConfig, run_week15_quality_gate

    root = Path(__file__).resolve().parents[2]
    cases_file = root / "tests" / "fixtures" / "week15_cases.json"
    baseline_file = root / "tests" / "fixtures" / "week15_baseline.json"

    report = run_week15_quality_gate(
        config=QualityGateConfig(
            cases_file=str(cases_file),
            baseline_file=str(baseline_file),
            write_baseline=False,
            disable_llm=True,
        )
    )
    assert report.get("ok") is True
    results = report.get("results")
    assert isinstance(results, list)
    assert all(isinstance(r, dict) and r.get("ok") is True for r in results)


def test_week15_key_decision_only_from_manager(monkeypatch):
    from riskmonitor_multiagent.orchestration.state_machine import run_state_machine

    root = Path(__file__).resolve().parents[2]
    cases_file = root / "tests" / "fixtures" / "week15_cases.json"
    cases = json.loads(cases_file.read_text(encoding="utf-8")).get("cases")
    assert isinstance(cases, list) and cases

    import asyncio
    monkeypatch.setenv("ENABLE_LANGGRAPH", "1")
    monkeypatch.setenv("HITL_AUTO_APPROVE", "1")
    monkeypatch.setenv("DISABLE_LLM", "1")

    event = dict(cases[0]["event"])
    out = asyncio.run(run_state_machine(event=event))
    assert out.get("ok") is True
    final_output = out.get("result")
    assert isinstance(final_output, dict)

    engineer = final_output.get("engineer")
    analyst = final_output.get("analyst")
    manager = final_output.get("manager")
    assert isinstance(engineer, dict)
    assert isinstance(analyst, dict)
    assert isinstance(manager, dict)

    assert "decision" not in engineer
    assert "decision" not in analyst
    assert "commands" not in engineer
    assert "commands" not in analyst
    assert "decision" in manager
    assert "commands" in manager
