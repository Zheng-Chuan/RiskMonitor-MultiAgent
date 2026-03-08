import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))


def test_intent_heuristics_side_effect_detection():
    from riskmonitor_multiagent.orchestration.intent_heuristics import guess_risk_level, guess_side_effects

    text = "请删除数据库里的异常记录并重启服务"
    side = guess_side_effects(text=text)
    risk = guess_risk_level(text=text, side_effects=side)
    assert side is True
    assert risk == "HIGH"


def test_intent_output_contract_normalize_and_validate():
    from riskmonitor_multiagent.contracts.intent_output import normalize_intent_output, validate_intent_output

    out = normalize_intent_output(
        {
            "schema_version": "intent_output.v2",
            "primary_intent_type": "query_positions",
            "intents": [{"intent_type": "query_positions", "slots": {"desk": "Equity Derivatives"}, "confidence": 0.8}],
            "disambiguation": {"has_multiple": False, "explanation": "", "notes": []},
            "risk_level": "LOW",
            "permission_requirements": {"side_effects": False, "requires_human_approval": False, "allowed_tools": None},
            "evidence": {"fields": ["task.payload.content"]},
            "degraded": False,
        }
    )
    ok, errors = validate_intent_output(out)
    assert ok, errors


def test_intent_output_multi_intent_is_sorted_and_explained():
    from riskmonitor_multiagent.contracts.intent_output import normalize_intent_output

    out = normalize_intent_output(
        {
            "schema_version": "intent_output.v2",
            "primary_intent_type": "",
            "intents": [
                {"intent_type": "write_alert", "slots": {}, "confidence": 0.4},
                {"intent_type": "query_positions", "slots": {}, "confidence": 0.9},
            ],
            "disambiguation": {"has_multiple": False, "explanation": "", "notes": None},
            "risk_level": "MEDIUM",
            "permission_requirements": {"side_effects": True, "requires_human_approval": True, "allowed_tools": None},
            "evidence": {"fields": ["task.payload.content"]},
            "degraded": False,
        }
    )
    intents = out.get("intents")
    assert isinstance(intents, list) and len(intents) == 2
    assert intents[0].get("intent_type") == "query_positions"
    assert out.get("primary_intent_type") == "query_positions"
    dis = out.get("disambiguation")
    assert isinstance(dis, dict)
    assert dis.get("has_multiple") is True
    assert isinstance(dis.get("explanation"), str) and dis.get("explanation")


@pytest.mark.asyncio
async def test_intent_agent_raises_when_llm_disabled(monkeypatch):
    monkeypatch.setenv("DISABLE_LLM", "1")
    monkeypatch.setenv("LLM_API_KEY", "test")
    from riskmonitor_multiagent.agents.roles import IntentAgent

    task = {"task_id": "t1", "session_id": "s1", "source": "human", "payload": {"content": "请查询 TRADER-001 的头寸"}}
    agent = IntentAgent()
    with pytest.raises(Exception):
        await agent.recognize(task=task, metadata={"source": "test"})
