from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pymysql
import pytest

import riskmonitor_multiagent.orchestration as orchestration
from riskmonitor_multiagent import config
from riskmonitor_multiagent.contracts.approval import (
    build_approval_summary_text,
    ensure_approval_transition,
    normalize_approval_record,
    normalize_approval_request,
    validate_approval_record,
    validate_approval_request,
    validate_approval_transition,
)
from riskmonitor_multiagent.contracts.event import (
    EVENT_SCHEMA_VERSION,
    EventType,
    new_event,
    normalize_event,
    validate_event,
)
from riskmonitor_multiagent.contracts.message import (
    MESSAGE_SCHEMA_VERSION,
    MessageType,
    normalize_message,
    validate_message,
)
from riskmonitor_multiagent.contracts.run_context import (
    RUN_CONTEXT_SCHEMA_VERSION,
    new_run_context,
    normalize_run_context,
    validate_run_context,
)
from riskmonitor_multiagent.contracts.task_graph import (
    append_replan_subgraph,
    build_task_graph_from_plan_steps,
    normalize_task_graph,
    validate_task_graph,
)
from riskmonitor_multiagent.data_access.errors import map_http_error, map_mysql_error
from riskmonitor_multiagent.data_access.health_checks import check_mysql_ready
from riskmonitor_multiagent.data_access import mysql_engine
from riskmonitor_multiagent.orchestration.intent_heuristics import (
    build_intent_metadata,
    guess_risk_level,
    guess_side_effects,
)
from riskmonitor_multiagent.services import logging_service
from riskmonitor_multiagent.services.prometheus_metrics_service import (
    generate_prometheus_metrics,
    get_metrics_summary,
    record_request,
    reset_metrics,
)
from riskmonitor_multiagent.tools.errors import error_payload
from riskmonitor_multiagent.tools import mcp_tools
from riskmonitor_multiagent.utils.validation import has_evidence_refs, is_non_empty_str, is_valid_list


def test_approval_contract_quick_paths() -> None:
    request = normalize_approval_request(
        {
            "level": "COMMAND",
            "command_id": " cmd-1 ",
            "impact_scope": " desk:eq ",
            "risk_level": "bad",
            "recommended_action": " ",
            "reason": " ",
        }
    )
    record = normalize_approval_record(
        {
            "request": request,
            "state": "not_required",
            "actor": " alice ",
            "note": " ok ",
            "error": " none ",
        }
    )

    assert request["approval_id"] == "command:cmd-1"
    assert request["level"] == "command"
    assert request["impact_scope"] == ["desk:eq"]
    assert request["risk_level"] == "HIGH"
    assert request["recommended_action"] == "review_and_confirm"
    assert request["reason"] == "approval_required"
    assert record["required"] is False
    assert record["actor"] == "alice"
    assert record["note"] == "ok"
    assert record["error"] == "none"
    assert validate_approval_request(request) == (True, [])
    assert validate_approval_record(record) == (True, [])
    assert "command:cmd-1" not in build_approval_summary_text(record)
    assert "target=cmd-1" in build_approval_summary_text(record)
    assert ensure_approval_transition("approved", "approved_but_failed") == "approved_but_failed"


def test_approval_contract_errors_and_transitions() -> None:
    assert validate_approval_transition("", "approved") == (False, "bad_current_approval_state")
    assert validate_approval_transition("pending", "bad") == (False, "bad_next_approval_state")
    assert validate_approval_transition("pending", "pending") == (True, None)

    ok, errors = validate_approval_request(
        {
            "schema_version": "bad",
            "approval_id": "",
            "level": "bad",
            "reason": "",
            "risk_level": "bad",
            "impact_scope": [" ", None],
            "recommended_action": "",
        }
    )
    assert ok is False
    assert {
        "bad_approval_request_schema_version",
        "bad_approval_id",
        "bad_approval_level",
        "bad_approval_reason",
        "bad_approval_risk_level",
        "bad_approval_impact_scope",
        "bad_approval_recommended_action",
    }.issubset(set(errors))

    ok, errors = validate_approval_record(
        {
            "schema_version": "bad",
            "request": {},
            "state": "bad",
            "required": "yes",
        }
    )
    assert ok is False
    assert "bad_approval_record_schema_version" in errors
    assert "bad_approval_state" in errors
    assert "bad_approval_required" in errors


def test_validation_helpers_cover_all_reference_paths() -> None:
    assert is_non_empty_str(" x ") is True
    assert is_non_empty_str("  ") is False
    assert is_valid_list(["a", "b"], str) is True
    assert is_valid_list(["a", 1], str) is False
    assert is_valid_list("not-a-list") is False
    assert has_evidence_refs(None) is False
    assert has_evidence_refs({"receipt_command_ids": [" ", "cmd-1"]}) is True
    assert has_evidence_refs({"fields": ["field.a"]}) is True
    assert has_evidence_refs({"rag_hit_ids": ["rag-1"]}) is True
    assert has_evidence_refs({"fields": [" "]}) is False


def test_intent_heuristics_cover_branches() -> None:
    assert guess_side_effects(text="") is False
    assert guess_side_effects(text="请发布服务") is True
    assert guess_side_effects(text="deploy to prod") is True

    assert guess_risk_level(text="普通查询", side_effects=True) == "HIGH"
    assert guess_risk_level(text="请检查 prod secret", side_effects=False) == "HIGH"
    assert guess_risk_level(text="接口 timeout 了", side_effects=False) == "MEDIUM"
    assert guess_risk_level(text="查询报表", side_effects=False) == "LOW"

    metadata = build_intent_metadata(
        task={
            "task_id": "task-1",
            "session_id": "sess-1",
            "source": "user",
            "user_id": "u-1",
            "payload": {"content": "abc"},
        },
        policy_version="p1",
        prompt_version="prompt1",
    )
    assert metadata["content_len"] == 3
    assert build_intent_metadata(task={"payload": []}, policy_version="p2", prompt_version="prompt2")["content_len"] == 0


def test_metrics_service_summarizes_and_renders() -> None:
    reset_metrics()
    record_request("alpha", 100.0)
    record_request("alpha", 300.0, is_error=True)
    record_request("beta", 50.0, is_error=True)

    summary = get_metrics_summary()
    out = generate_prometheus_metrics()

    assert summary["tools"]["alpha"]["request_count"] == 2
    assert summary["tools"]["alpha"]["error_count"] == 1
    assert summary["tools"]["alpha"]["avg_latency_ms"] == 200.0
    assert summary["tools"]["alpha"]["error_rate"] == 0.5
    assert summary["tools"]["beta"]["error_rate"] == 1.0
    assert 'mcp_requests_total{tool="alpha"} 2' in out
    assert 'mcp_request_latency_ms_avg{tool="alpha"} 200.00' in out
    assert 'mcp_errors_total{tool="beta"} 1' in out
    assert 'mcp_error_rate{tool="beta"} 1.0000' in out


@pytest.mark.asyncio
async def test_orchestration_wrappers_delegate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(*, task):
        return {"kind": "proactive", "task_id": task["task_id"]}

    async def fake_user(*, task):
        return {"kind": "user", "task_id": task["task_id"]}

    async def fake_event(*, event, candidate_agents=None):
        return {"kind": "event", "event_id": event["event_id"], "agents": list(candidate_agents or [])}

    monkeypatch.setattr("riskmonitor_multiagent.orchestration.proactive_workflow.run_proactive_workflow", fake_run)
    monkeypatch.setattr("riskmonitor_multiagent.orchestration.multiagent_workflow.run_user_task", fake_user)
    monkeypatch.setattr("riskmonitor_multiagent.orchestration.multiagent_workflow.start_from_event", fake_event)

    assert (await orchestration.run_proactive_workflow(task={"task_id": "t1"}))["kind"] == "proactive"
    assert (await orchestration.run_user_task(task={"task_id": "t2"}))["kind"] == "user"
    assert (await orchestration.start_from_event(event={"event_id": "e1"}, candidate_agents=["orchestrator"]))["agents"] == [
        "orchestrator"
    ]


def test_logging_helpers_and_error_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = error_payload("BAD", "oops", "req-1")
    assert payload == {
        "is_error": True,
        "error": {"code": "BAD", "message": "oops", "request_id": "req-1"},
    }

    record = logging.LogRecord("riskmonitor", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    assert logging_service._RequestIdFilter().filter(record) is True
    assert record.request_id == "-"

    record.request_id = "req-2"
    formatted = logging_service.JsonFormatter().format(record)
    assert '"message": "hello world"' in formatted
    assert '"request_id": "req-2"' in formatted

    logging_service._state["is_configured"] = False
    fake_handler = MagicMock()
    real_root = logging.getLogger()
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setattr(real_root, "handlers", [fake_handler], raising=False)
    monkeypatch.setattr(logging_service.logging, "basicConfig", MagicMock())
    logging_service.configure_logging()
    logging_service.configure_logging()
    assert logging_service._state["is_configured"] is True
    fake_handler.addFilter.assert_called_once()

    info_logger = MagicMock()
    error_logger = MagicMock()
    exception_logger = MagicMock()
    monkeypatch.setattr(logging_service, "_logger", SimpleNamespace(info=info_logger, error=error_logger, exception=exception_logger))
    logging_service.log_info("i", "req-i")
    logging_service.log_error("e", "req-e")
    logging_service.log_exception("x", "req-x")
    assert len(logging_service.new_request_id()) == 32
    info_logger.assert_called_once()
    error_logger.assert_called_once()
    exception_logger.assert_called_once()


def test_config_getters_cover_defaults_and_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    state = SimpleNamespace(
        mysql_host="",
        mysql_port=0,
        mysql_database="",
        mysql_user="",
        mysql_password="  ",
        mysql_connect_timeout=3,
        mysql_read_timeout=5,
        mysql_write_timeout=6,
        mysql_pool_size=7,
        mysql_pool_max_overflow=8,
        mysql_pool_recycle=9,
        llm_api_key="  ",
        llm_base_url=" https://api.example.com/v1/ ",
        llm_model="  ",
        llm_http_referer=" https://app.example.com ",
        llm_app_title=" RiskMonitor ",
        llm_resolve_ip=" 1.1.1.1 ",
        knowledge_db_path="",
        chroma_host="",
        chroma_port=0,
        chroma_collection="",
        chroma_memory_collection="",
        chroma_persist_dir=" /tmp/chroma ",
    )
    monkeypatch.setattr(config, "get_settings", lambda: state)

    assert config.get_mysql_host() == "localhost"
    assert config.get_mysql_port() == 3306
    assert config.get_mysql_database() == "riskmonitor"
    assert config.get_mysql_user() == "admin"
    with pytest.raises(ValueError, match="MYSQL_PASSWORD is not set"):
        config.get_mysql_password()
    with pytest.raises(ValueError, match="LLM_API_KEY is not set"):
        config.get_llm_api_key()
    assert config.get_llm_base_url() == "https://api.example.com/v1"
    assert config.get_llm_model() == "ark-code-latest"
    assert config.get_llm_http_referer() == "https://app.example.com"
    assert config.get_llm_app_title() == "RiskMonitor"
    assert config.get_llm_resolve_ip() == "1.1.1.1"
    assert config.get_chroma_host() == "localhost"
    assert config.get_chroma_port() == 8001
    assert config.get_chroma_collection() == "riskmonitor-alerts"
    assert config.get_chroma_memory_collection() == "riskmonitor-memory"
    assert config.get_chroma_persist_dir() == "/tmp/chroma"
    assert config.get_knowledge_db_path().endswith("data/knowledge.sqlite")

    state.mysql_password = " secret "
    state.llm_api_key = " key "
    assert config.get_mysql_password() == "secret"
    assert config.get_llm_api_key() == "key"


def test_data_access_error_mapping_paths() -> None:
    timeout_error = pymysql.MySQLError("timed out")
    mapped = map_mysql_error(timeout_error, "ping")
    assert mapped.code == "DB_TIMEOUT"
    assert mapped.retriable is True
    assert str(mapped) == "DB_TIMEOUT: mysql timeout op=ping"

    mapped = map_mysql_error(pymysql.err.OperationalError(2003, "boom"), "read")
    assert mapped.code == "DB_UNAVAILABLE"
    mapped = map_mysql_error(pymysql.err.ProgrammingError(1064, "bad sql"), "query")
    assert mapped.code == "DB_QUERY_FAILED"
    mapped = map_mysql_error(pymysql.MySQLError("other"), "other")
    assert mapped.code == "DB_ERROR"

    request = httpx.Request("GET", "https://example.com")
    mapped = map_http_error(httpx.TimeoutException("timeout"), "fetch")
    assert mapped.code == "UPSTREAM_TIMEOUT"
    mapped = map_http_error(httpx.HTTPStatusError("bad", request=request, response=httpx.Response(503, request=request)), "fetch")
    assert mapped.code == "UPSTREAM_BAD_STATUS"
    assert mapped.retriable is True
    mapped = map_http_error(httpx.HTTPStatusError("bad", request=request, response=httpx.Response(404, request=request)), "fetch")
    assert mapped.retriable is False
    assert mapped.code == "UPSTREAM_BAD_STATUS"
    mapped = map_http_error(httpx.RequestError("down", request=request), "fetch")
    assert mapped.code == "UPSTREAM_UNAVAILABLE"
    mapped = map_http_error(ValueError("bad json"), "fetch")
    assert mapped.code == "UPSTREAM_BAD_RESPONSE"
    mapped = map_http_error(RuntimeError("unknown"), "fetch")
    assert mapped.code == "UPSTREAM_ERROR"


def test_mysql_engine_build_get_and_dispose(monkeypatch: pytest.MonkeyPatch) -> None:
    mysql_engine.get_engine.cache_clear()
    monkeypatch.setattr(mysql_engine.config, "get_mysql_user", lambda: "user")
    monkeypatch.setattr(mysql_engine.config, "get_mysql_password", lambda: "pass")
    monkeypatch.setattr(mysql_engine.config, "get_mysql_host", lambda: "host")
    monkeypatch.setattr(mysql_engine.config, "get_mysql_port", lambda: 3307)
    monkeypatch.setattr(mysql_engine.config, "get_mysql_database", lambda: "db")
    monkeypatch.setattr(mysql_engine.config, "get_mysql_connect_timeout_s", lambda: 1.0)
    monkeypatch.setattr(mysql_engine.config, "get_mysql_read_timeout_s", lambda: 2.0)
    monkeypatch.setattr(mysql_engine.config, "get_mysql_write_timeout_s", lambda: 3.0)
    monkeypatch.setattr(mysql_engine.config, "get_mysql_pool_recycle_s", lambda: 4)
    monkeypatch.setattr(mysql_engine.config, "get_mysql_pool_size", lambda: 5)
    monkeypatch.setattr(mysql_engine.config, "get_mysql_max_overflow", lambda: 6)

    created: list[dict] = []

    class _FakeEngine:
        def __init__(self) -> None:
            self.disposed = False

        def dispose(self) -> None:
            self.disposed = True

    fake_engine = _FakeEngine()

    def fake_create_engine(url, **kwargs):
        created.append({"url": url, "kwargs": kwargs})
        return fake_engine

    monkeypatch.setattr(mysql_engine, "create_engine", fake_create_engine)

    url = mysql_engine._build_mysql_url()
    assert url.drivername == "mysql+pymysql"
    assert url.host == "host"
    assert url.port == 3307
    assert url.database == "db"
    assert url.query["charset"] == "utf8mb4"

    assert mysql_engine.get_engine() is fake_engine
    assert mysql_engine.get_engine() is fake_engine
    assert len(created) == 1
    assert created[0]["kwargs"]["connect_args"]["write_timeout"] == 3.0

    mysql_engine.dispose_engine()
    assert fake_engine.disposed is True


def test_health_check_covers_success_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Cursor:
        def __init__(self, row):
            self._row = row
            self.closed = False

        def execute(self, sql):
            assert "SELECT 1" in sql

        def fetchone(self):
            return self._row

        def close(self):
            self.closed = True

    class _Conn:
        def __init__(self, row):
            self.cursor_obj = _Cursor(row)
            self.closed = False

        def cursor(self, *_args, **_kwargs):
            return self.cursor_obj

        def close(self):
            self.closed = True

    class _Engine:
        def __init__(self, action):
            self.action = action

        def raw_connection(self):
            if isinstance(self.action, Exception):
                raise self.action
            if callable(self.action):
                return self.action()
            return self.action

    success_conn = _Conn({"ok": 1})
    monkeypatch.setattr("riskmonitor_multiagent.data_access.health_checks.get_engine", lambda: _Engine(success_conn))
    assert check_mysql_ready() == (True, "ok", None)
    assert success_conn.cursor_obj.closed is True
    assert success_conn.closed is True

    unexpected_conn = _Conn({"ok": 0})
    monkeypatch.setattr("riskmonitor_multiagent.data_access.health_checks.get_engine", lambda: _Engine(unexpected_conn))
    assert check_mysql_ready() == (False, "unexpected_result", None)

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "yes")
    monkeypatch.setenv("MYSQL_HEALTHCHECK_IN_TESTS", "0")
    monkeypatch.setattr(
        "riskmonitor_multiagent.data_access.health_checks.get_engine",
        lambda: _Engine(pymysql.err.OperationalError(2003, "down")),
    )
    assert check_mysql_ready() == (True, "skipped_pytest", None)

    monkeypatch.setattr("riskmonitor_multiagent.data_access.health_checks.get_engine", lambda: _Engine(ValueError("missing")))
    assert check_mysql_ready() == (True, "skipped_missing_config", None)

    monkeypatch.setenv("MYSQL_HEALTHCHECK_IN_TESTS", "1")
    monkeypatch.setattr("riskmonitor_multiagent.data_access.health_checks.get_engine", lambda: _Engine(RuntimeError("boom")))
    ok, message, error = check_mysql_ready()
    assert ok is False
    assert message == "mysql error op=check_mysql_ready"
    assert error is not None and error.code == "DB_ERROR"


def test_mcp_tool_registration_and_error_mapping() -> None:
    calls: list[str] = []

    class _FakeMCP:
        def tool(self):
            def _decorator(func):
                calls.append(func.__name__)
                return func

            return _decorator

    mcp_tools.register_tools(_FakeMCP())
    assert calls == [
        "query_all_positions",
        "query_positions_by_trader",
        "query_positions_by_desk",
        "calculate_total_delta",
        "monitor_desk_exposure",
        "submit_alerts",
        "get_service_metrics",
        "search_similar_alerts",
    ]

    assert mcp_tools._unauthorized_result("req-1")["error"]["code"] == "UNAUTHORIZED"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="approval_required")["error"]["code"] == "APPROVAL_REQUIRED"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="approval_reason_required")["error"]["message"] == "审批缺少理由"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="approval_rejected")["error"]["code"] == "APPROVAL_REJECTED"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="approval_expired")["error"]["code"] == "APPROVAL_EXPIRED"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="rbac_denied")["error"]["code"] == "PERMISSION_DENIED"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="invalid_command")["error"]["code"] == "INVALID_INPUT"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="handler_missing")["error"]["code"] == "TOOL_UNAVAILABLE"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error="tool_budget_exceeded")["error"]["code"] == "TOOL_BUDGET_EXCEEDED"
    assert mcp_tools._receipt_error_to_public_result(request_id="req-2", error=None)["error"]["code"] == "INTERNAL_ERROR"


def test_execute_mcp_tool_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_tools, "new_request_id", lambda: "req-new")
    monkeypatch.setattr(mcp_tools, "new_command_id", lambda: "cmd-1")
    monkeypatch.setattr(mcp_tools, "get_headers_from_ctx", lambda ctx: {"authorization": "Bearer x"})

    class _Meta:
        owner = "risk_analyst"
        default_timeout_ms = 123

    command_calls: list[dict] = []

    def fake_new_agent_command(**kwargs):
        command_calls.append(kwargs)
        return kwargs

    monkeypatch.setattr(mcp_tools, "new_agent_command", fake_new_agent_command)

    monkeypatch.setattr(mcp_tools, "is_authorized", lambda _headers: False)
    result = mcp_tools._execute_mcp_tool(action="query_all_positions", params={}, ctx=object())
    assert result["error"]["code"] == "UNAUTHORIZED"

    monkeypatch.setattr(mcp_tools, "is_authorized", lambda _headers: True)
    monkeypatch.setattr(mcp_tools, "get_tool_meta", lambda _action: None)
    result = mcp_tools._execute_mcp_tool(action="missing", params={}, ctx=None)
    assert result["error"]["code"] == "TOOL_UNAVAILABLE"

    monkeypatch.setattr(mcp_tools, "get_tool_meta", lambda _action: _Meta())
    monkeypatch.setattr(mcp_tools, "execute_agent_command", lambda _command: {"ok": False, "error": "approval_rejected"})
    result = mcp_tools._execute_mcp_tool(action="query_all_positions", params={"x": 1}, ctx=None)
    assert result["error"]["code"] == "APPROVAL_REJECTED"

    monkeypatch.setattr(
        mcp_tools,
        "execute_agent_command",
        lambda _command: {"ok": True, "outputs": {"result": {"value": 1}}},
    )
    result = mcp_tools._execute_mcp_tool(action="query_all_positions", params={"request_id": "req-fixed"}, ctx=None)
    assert result == {"value": 1, "request_id": "req-fixed", "latency_ms": 0.0}

    monkeypatch.setattr(mcp_tools, "execute_agent_command", lambda _command: {"ok": True, "outputs": {}})
    result = mcp_tools._execute_mcp_tool(action="query_all_positions", params={}, ctx=None)
    assert result == {"request_id": "req-new"}
    assert command_calls[-1]["target_agent"] == "risk_analyst"
    assert command_calls[-1]["timeout_ms"] == 123


@pytest.mark.asyncio
async def test_mcp_public_wrappers_forward_params(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_execute(*, action, params, ctx=None):
        calls.append({"action": action, "params": params, "ctx": ctx})
        return {"action": action, "params": params}

    monkeypatch.setattr(mcp_tools, "_execute_mcp_tool", fake_execute)

    assert mcp_tools.search_similar_alerts("query", top_k=3)["action"] == "search_similar_alerts"
    assert mcp_tools.query_all_positions()["action"] == "query_all_positions"
    assert mcp_tools.query_positions_by_trader("trader-1", limit=5, offset=2)["params"]["trader_id"] == "trader-1"
    assert (await mcp_tools.query_positions_by_desk("desk-1", limit=9))["params"]["desk"] == "desk-1"
    assert (await mcp_tools.calculate_total_delta())["action"] == "calculate_total_delta"
    assert (await mcp_tools.monitor_desk_exposure("desk-2", abs_delta_limit=9.9))["params"]["abs_delta_limit"] == 9.9
    assert mcp_tools.submit_alerts([{"alert_id": "a1"}], approval={"approved": True})["params"]["approval"] == {"approved": True}
    assert (await mcp_tools.get_service_metrics())["action"] == "get_service_metrics"
    assert [item["action"] for item in calls] == [
        "search_similar_alerts",
        "query_all_positions",
        "query_positions_by_trader",
        "query_positions_by_desk",
        "calculate_total_delta",
        "monitor_desk_exposure",
        "submit_alerts",
        "get_service_metrics",
    ]


def test_event_message_run_context_contracts() -> None:
    event = normalize_event({"payload": []})
    assert event["schema_version"] == EVENT_SCHEMA_VERSION
    assert event["event_type"] == EventType.TASK_CREATED.value
    assert validate_event(
        {
            "schema_version": "bad",
            "event_id": "",
            "event_type": "bad",
            "source_agent": "",
            "target_agent": "",
            "payload": [],
            "timestamp_ms": 0,
            "correlation_id": "",
            "causation_id": "",
            "priority": "bad",
            "requires_ack": "yes",
        }
    )[0] is False
    assert new_event(event_type=EventType.CRON_TRIGGERED, source_agent="cron")["event_type"] == "cron_triggered"

    message = normalize_message({})
    assert message["schema_version"] == MESSAGE_SCHEMA_VERSION
    assert message["message_type"] == MessageType.REQUEST.value
    ok, errors = validate_message(
        {
            "message_id": "",
            "message_type": "bad",
            "from_agent": "",
            "content": [],
            "timestamp_ms": 0,
            "to_agent": "",
            "in_reply_to": "",
        }
    )
    assert ok is False
    assert "bad_message_type" in errors
    assert validate_message(None) == (False, ["message must be dict"])

    run_context = normalize_run_context({})
    assert run_context["schema_version"] == RUN_CONTEXT_SCHEMA_VERSION
    assert run_context["entry_type"] == "user_task"
    ok, errors = validate_run_context(
        {
            "schema_version": "bad",
            "run_id": "",
            "entry_type": "bad",
            "task_id": "",
            "trigger_event_id": "",
            "trigger_reason": "",
            "trigger_evidence": [],
            "route_decision": [],
            "metadata": [],
        }
    )
    assert ok is False
    assert "bad_metadata" in errors
    assert new_run_context(entry_type="system_event", task_id="task-1", run_id="run-1")["run_id"] == "run-1"


def test_task_graph_normalize_and_replan_edges() -> None:
    built = normalize_task_graph(
        {},
        plan_steps=[
            {"kind": "delegate", "step_id": "s1", "reason": "分析", "target_agent": "risk_analyst"},
            {"kind": "stop", "step_id": "s2", "reason": "结束"},
        ],
    )
    assert ("s1", "s2") in {
        (edge["from_step_id"], edge["to_step_id"])
        for edge in built["edges"]
    }

    normalized = normalize_task_graph(
        {
            "nodes": [
                {"kind": "delegate", "target_agent": "system_engineer"},
                {"step_id": "s2", "kind": "finalize"},
            ],
            "edges": "bad",
        }
    )
    assert normalized["nodes"][0]["step_id"] == "s1"
    assert normalized["nodes"][0]["reason"] == "缺少原因说明 已自动回填"
    assert normalized["nodes"][0]["evidence"] == {"fields": ["task_graph"]}
    assert ("s1", "s2") in {
        (edge["from_step_id"], edge["to_step_id"])
        for edge in normalized["edges"]
    }

    ok, errors = validate_task_graph(
        {
            "schema_version": "",
            "nodes": [
                {"step_id": "s1", "kind": "delegate", "status": "weird", "reason": "", "evidence": [], "target_agent": ""},
                {"step_id": "s1", "kind": "tool_call", "reason": "run", "evidence": {}, "tool_name": ""},
            ],
            "edges": [
                {"from_step_id": "s1", "to_step_id": "missing"},
                "bad",
            ],
        }
    )
    assert ok is False
    assert "bad_task_graph_schema_version" in errors
    assert "duplicate_task_graph_step_id" in errors
    assert "bad_task_graph_status" in errors
    assert "bad_task_graph_reason" in errors
    assert "bad_task_graph_evidence" in errors
    assert "bad_task_graph_delegate_target_agent" in errors
    assert "bad_task_graph_tool_name" in errors
    assert "unknown_task_graph_edge_ref" in errors
    assert "bad_task_graph_edge" in errors

    base = build_task_graph_from_plan_steps(
        [
            {"kind": "delegate", "step_id": "s1", "reason": "分析", "target_agent": "risk_analyst"},
            {"kind": "finalize", "step_id": "s2", "reason": "总结"},
        ]
    )
    replan = build_task_graph_from_plan_steps(
        [
            {"kind": "analyze", "step_id": "s1", "reason": "重试分析"},
        ]
    )
    merged = append_replan_subgraph(base, replan, reason="critic rejected", replan_index=2)
    assert {"rp2", "rp2_s1"}.issubset({node["step_id"] for node in merged["nodes"]})
    assert ("s2", "rp2", "critic_rejected") in {
        (edge["from_step_id"], edge["to_step_id"], edge["condition"])
        for edge in merged["edges"]
    }
