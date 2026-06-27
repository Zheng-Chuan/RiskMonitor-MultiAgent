from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from riskmonitor_multiagent.llm import prompts as prompts_module
from riskmonitor_multiagent.llm.output_repair import (
    OutputRepairError,
    build_repair_prompt,
    extract_json_from_text,
    fix_common_json_issues,
    parse_with_retry,
)
from riskmonitor_multiagent.llm.prompts import PromptLoader, get_prompt_loader
from riskmonitor_multiagent.orchestration.observation_tools import (
    observe_chroma_health,
    observe_kafka_lag_estimate,
    observe_mysql_health,
    observe_service_metrics,
)
from riskmonitor_multiagent.resources.mcp_resources import register_resources
from riskmonitor_multiagent.services import auth_service
from riskmonitor_multiagent.utils.json import safe_json_dumps, safe_json_loads
from riskmonitor_multiagent.utils.text import clean_llm_output, truncate_context, truncate_text
from riskmonitor_multiagent.utils.time import Timer, elapsed_ms, measure_time, now_ms


class _OutputModel(BaseModel):
    answer: str
    score: int


def test_extract_json_and_fix_common_issues() -> None:
    assert extract_json_from_text('{"answer":"ok","score":1}') == '{"answer":"ok","score":1}'
    assert extract_json_from_text("```json\n{\"answer\":\"ok\",\"score\":1}\n```") == '{"answer":"ok","score":1}'
    assert extract_json_from_text("before {\"answer\":\"ok\",\"score\":1} after") == '{"answer":"ok","score":1}'
    assert extract_json_from_text("") is None

    fixed = fix_common_json_issues(
        """
        {
          // comment
          "answer": "ok",
          "score": 1,
        }
        """
    )
    assert json.loads(fixed) == {"answer": "ok", "score": 1}


def test_parse_with_retry_and_repair_prompt() -> None:
    repaired = parse_with_retry(
        '{"answer":"done","score":3}',
        _OutputModel,
        max_fix_attempts=2,
    )
    assert repaired.answer == "done"
    assert repaired.score == 3

    with pytest.raises(OutputRepairError):
        parse_with_retry('{"answer":"done","score":3,}', _OutputModel, max_fix_attempts=1)

    messages = build_repair_prompt(
        original_prompt=[{"role": "system", "content": "return json"}],
        error=ValueError("bad output"),
        model_class=_OutputModel,
    )
    assert messages[0]["role"] == "system"
    assert "bad output" in messages[-1]["content"]
    assert "answer" in messages[-1]["content"]


def test_prompt_loader_supports_multiple_formats_and_singleton(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "alpha.txt").write_text("text prompt", encoding="utf-8")
    (tmp_path / "beta.md").write_text("# markdown", encoding="utf-8")
    (tmp_path / "gamma.json").write_text('{"kind":"json"}', encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not-json}", encoding="utf-8")

    loader = PromptLoader(str(tmp_path))
    assert loader.load("alpha") == "text prompt"
    assert loader.load("beta") == "# markdown"
    assert loader.load_json("gamma") == {"kind": "json"}
    assert loader.load_json("broken") is None
    assert loader.load("missing") is None

    monkeypatch.setattr(prompts_module, "_prompt_loader", None)
    monkeypatch.setattr(prompts_module.Path, "resolve", lambda self: tmp_path / "fake.py")
    singleton_a = get_prompt_loader()
    singleton_b = get_prompt_loader()
    assert singleton_a is singleton_b


def test_auth_service_authorization_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RISKMONITOR_API_TOKEN", raising=False)
    assert auth_service.is_authorized({}) is True

    monkeypatch.setenv("RISKMONITOR_API_TOKEN", " secret-token ")
    assert auth_service._extract_bearer(None) is None
    assert auth_service._extract_bearer("") is None
    assert auth_service._extract_bearer("Basic abc") is None
    assert auth_service._extract_bearer("Bearer secret-token") == "secret-token"
    assert auth_service.is_authorized({"authorization": "Bearer secret-token"}) is True
    assert auth_service.is_authorized({"Authorization": "Bearer secret-token"}) is True
    assert auth_service.is_authorized({"authorization": "Bearer wrong"}) is False


def test_auth_service_get_headers_from_ctx_handles_multiple_shapes() -> None:
    ctx = SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(headers={"authorization": "Bearer token"})
        )
    )
    assert auth_service.get_headers_from_ctx(ctx) == {"authorization": "Bearer token"}

    ctx = SimpleNamespace(request_context=SimpleNamespace(headers={"x-id": "1"}))
    assert auth_service.get_headers_from_ctx(ctx) == {"x-id": "1"}

    bad_headers = SimpleNamespace(__iter__=None)
    ctx = SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=bad_headers)))
    assert auth_service.get_headers_from_ctx(ctx) == {}
    assert auth_service.get_headers_from_ctx(SimpleNamespace()) == {}


def test_json_text_and_time_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert safe_json_loads('{"a":1}') == {"a": 1}
    assert safe_json_loads("", default={}) == {}
    assert safe_json_loads("{bad}", default=[]) == []
    assert safe_json_dumps({"中文": 1}, ensure_ascii=False).startswith("{")
    assert safe_json_dumps(None, default="null") == "null"

    cleaned = clean_llm_output("```json\nbefore {\"ok\": true}\nafter\n```")
    assert cleaned == '{"ok": true}'
    assert truncate_text("abcdef", max_chars=5) == "ab..."
    assert truncate_text("abc", max_chars=5) == "abc"
    assert truncate_context(None) is None
    assert truncate_context({"plan": "x" * 800, "keep": "v"}, max_chars=30)["plan"].endswith("[truncated]")

    with Timer() as timer:
        time.sleep(0.001)
    assert timer.elapsed_ms >= 0

    calls: list[str] = []

    @measure_time
    def wrapped(value: str) -> str:
        calls.append(value)
        return value.upper()

    assert wrapped("ok") == "OK"
    assert calls == ["ok"]

    monkeypatch.setattr("riskmonitor_multiagent.utils.time.time.time", lambda: 1.234)
    monkeypatch.setattr("riskmonitor_multiagent.utils.time.time.monotonic", lambda: 10.5)
    assert now_ms() == 1234
    assert elapsed_ms(10.0) == 500.0


def test_observation_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monotonic_values = iter([1.0, 1.01, 2.0, 2.02, 3.0, 3.03, 4.0, 4.05, 5.0, 5.06])
    monkeypatch.setattr("riskmonitor_multiagent.orchestration.observation_tools.time.monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.observation_tools.get_metrics_summary",
        lambda: {"requests": 3},
    )
    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.observation_tools.check_mysql_ready",
        lambda: (False, "mysql_down", SimpleNamespace(code="MYSQL_UNAVAILABLE")),
    )
    monkeypatch.setattr(
        "riskmonitor_multiagent.orchestration.observation_tools.time.time",
        lambda: 10.0,
    )

    class _GoodStore:
        def query_alerts(self, query_text: str, top_k: int) -> list[dict[str, str]]:
            assert query_text == "health_check"
            assert top_k == 1
            return [{"id": "ok"}]

    sys.modules["riskmonitor_multiagent.knowledge.chroma_store"] = SimpleNamespace(
        ChromaVectorStore=_GoodStore
    )
    try:
        metrics = observe_service_metrics()
        mysql = observe_mysql_health()
        chroma = observe_chroma_health()
        kafka_bad = observe_kafka_lag_estimate(message_ts_ms=None)
        kafka_good = observe_kafka_lag_estimate(message_ts_ms=9000)
    finally:
        sys.modules.pop("riskmonitor_multiagent.knowledge.chroma_store", None)

    assert metrics["ok"] is True and metrics["summary"] == {"requests": 3}
    assert mysql["ok"] is False and mysql["error_code"] == "MYSQL_UNAVAILABLE"
    assert chroma["ok"] is True and chroma["message"] == "ok"
    assert kafka_bad["ok"] is False and kafka_bad["lag_ms"] is None
    assert kafka_good["ok"] is True and kafka_good["lag_ms"] == 1000


def test_observe_chroma_health_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("riskmonitor_multiagent.orchestration.observation_tools.time.monotonic", lambda: 1.0)
    sys.modules["riskmonitor_multiagent.knowledge.chroma_store"] = SimpleNamespace(
        ChromaVectorStore=lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    try:
        result = observe_chroma_health()
    finally:
        sys.modules.pop("riskmonitor_multiagent.knowledge.chroma_store", None)
    assert result["ok"] is False
    assert result["message"] == "chroma_unavailable"
    assert "boom" in str(result["error"])


def test_register_resources_registers_three_payloads() -> None:
    registered: dict[str, object] = {}

    class _FakeMCP:
        def resource(self, uri: str, **kwargs: object):
            def decorator(func):
                registered[uri] = (kwargs, func)
                return func

            return decorator

    register_resources(_FakeMCP())

    assert sorted(registered.keys()) == [
        "market://snapshot/latest",
        "risk://limits/global",
        "risk://metadata/desks",
    ]
    desks_payload = json.loads(registered["risk://metadata/desks"][1]())
    limits_payload = json.loads(registered["risk://limits/global"][1]())
    snapshot_payload = json.loads(registered["market://snapshot/latest"][1]())
    assert desks_payload["desks"][0]["desk"] == "Equity Derivatives"
    assert limits_payload["abs_delta_limit"] == 1000000.0
    assert snapshot_payload["fx_rates"]["USD"] == 1.0
