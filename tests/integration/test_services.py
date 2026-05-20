"""Service 层真实集成测试.

连接真实 MySQL 数据库，测试完整的业务流程：
- alert_rules_service: breach 评估与 alert 生成
- breach_service: 限额判断
- exposure_service: 敞口计算
- 端到端流程: 插入头寸 → 计算敞口 → 检测 breach → 生成 alert → 持久化 → 查询验证
"""

import uuid
from datetime import date
from decimal import Decimal

import pymysql
import pytest

from riskmonitor_multiagent.services.alert_rules_service import (
    _determine_severity,
    evaluate_desk_delta_breach,
    format_alerts_for_response,
)
from riskmonitor_multiagent.services.breach_service import build_abs_delta_breaches
from riskmonitor_multiagent.services.exposure_compute import (
    compute_position_pv_usd,
    to_float,
)
from riskmonitor_multiagent.services.exposure_service import compute_exposure
from tests.integration.factories import AlertFactory, PositionFactory


# ---------------------------------------------------------------------------
# Alert Rules Service
# ---------------------------------------------------------------------------


class TestAlertRulesService:
    """alert_rules_service 真实集成测试."""

    def test_evaluate_breach_generates_alert(self):
        """真实评估breach - 超阈值应生成alert."""
        alerts = evaluate_desk_delta_breach(
            desk="IntTest Desk",
            abs_delta=1_500_000.0,
            threshold=1_000_000.0,
            request_id="inttest-req-001",
        )
        assert len(alerts) == 1
        alert = alerts[0]
        assert alert["alert_type"] == "DESK_DELTA_BREACH"
        assert alert["severity"] in ("INFO", "WARNING", "CRITICAL")
        assert alert["desk"] == "IntTest Desk"
        assert alert["metric_value"] == 1_500_000.0
        assert alert["threshold_value"] == 1_000_000.0
        assert alert["breach_amount"] == 500_000.0
        assert alert["request_id"] == "inttest-req-001"
        assert alert["acknowledged"] is False

    def test_no_breach_no_alert(self):
        """未超阈值不应生成alert."""
        alerts = evaluate_desk_delta_breach(
            desk="Safe Desk",
            abs_delta=800_000.0,
            threshold=1_000_000.0,
            request_id="inttest-req-002",
        )
        assert alerts == []

    def test_exact_threshold_no_alert(self):
        """刚好等于阈值不应生成alert（需要严格超过）."""
        alerts = evaluate_desk_delta_breach(
            desk="Edge Desk",
            abs_delta=1_000_000.0,
            threshold=1_000_000.0,
            request_id="inttest-req-003",
        )
        assert alerts == []

    def test_severity_critical(self):
        """breach超50%应为CRITICAL."""
        severity = _determine_severity(breach_amount=600_000.0, threshold=1_000_000.0)
        assert severity == "CRITICAL"

    def test_severity_warning(self):
        """breach超20%但不足50%应为WARNING."""
        severity = _determine_severity(breach_amount=300_000.0, threshold=1_000_000.0)
        assert severity == "WARNING"

    def test_severity_info(self):
        """breach不足20%应为INFO."""
        severity = _determine_severity(breach_amount=100_000.0, threshold=1_000_000.0)
        assert severity == "INFO"

    def test_format_alerts_for_response(self):
        """格式化告警列表."""
        alerts = evaluate_desk_delta_breach(
            desk="Format Desk",
            abs_delta=2_000_000.0,
            threshold=1_000_000.0,
            request_id="inttest-req-004",
        )
        formatted = format_alerts_for_response(alerts)
        assert len(formatted) == 1
        item = formatted[0]
        # 格式化后应包含这些字段
        assert "alert_id" in item
        assert "alert_type" in item
        assert "severity" in item
        assert "desk" in item
        assert "metric_name" in item
        assert "metric_value" in item
        assert "threshold_value" in item
        assert "breach_amount" in item
        assert "message" in item
        # 不应包含非格式化字段
        assert "acknowledged" not in item
        assert "acknowledged_at" not in item


# ---------------------------------------------------------------------------
# Breach Service
# ---------------------------------------------------------------------------


class TestBreachService:
    """breach_service 真实集成测试."""

    def test_abs_delta_breach_detected(self):
        """total_delta 超过限额应生成违规记录."""
        breaches = build_abs_delta_breaches(total_delta=1_200_000.0, abs_delta_limit=1_000_000.0)
        assert len(breaches) == 1
        b = breaches[0]
        assert b["type"] == "ABS_DELTA_LIMIT"
        assert b["metric"] == "total_delta"
        assert b["value"] == 1_200_000.0
        assert b["threshold"] == 1_000_000.0

    def test_negative_delta_breach(self):
        """负方向 total_delta 超限（绝对值判断）."""
        breaches = build_abs_delta_breaches(total_delta=-1_500_000.0, abs_delta_limit=1_000_000.0)
        assert len(breaches) == 1
        assert breaches[0]["value"] == -1_500_000.0

    def test_within_limit_no_breach(self):
        """未超限返回空列表."""
        breaches = build_abs_delta_breaches(total_delta=500_000.0, abs_delta_limit=1_000_000.0)
        assert breaches == []

    def test_exact_limit_no_breach(self):
        """刚好等于限额不应产生breach."""
        breaches = build_abs_delta_breaches(total_delta=1_000_000.0, abs_delta_limit=1_000_000.0)
        assert breaches == []


# ---------------------------------------------------------------------------
# Exposure Compute Service
# ---------------------------------------------------------------------------


class TestExposureCompute:
    """exposure_compute 真实集成测试."""

    def test_to_float_valid(self):
        """正常数值转换."""
        assert to_float(100) == 100.0
        assert to_float("3.14") == 3.14
        assert to_float(Decimal("999.99")) == 999.99

    def test_to_float_invalid(self):
        """无效输入返回None."""
        assert to_float(None) is None
        assert to_float("abc") is None
        assert to_float("") is None

    def test_compute_position_pv_usd(self):
        """计算单笔头寸PV."""
        position = {
            "security_id": "AAPL",
            "currency": "USD",
            "quantity": 1000,
        }
        snapshot = {
            "prices": {"AAPL": 175.0},
            "fx_rates": {"USD": 1.0},
        }
        pv = compute_position_pv_usd(position, snapshot)
        assert pv == 175_000.0

    def test_compute_position_pv_with_fx(self):
        """计算非USD头寸PV（含汇率转换）."""
        position = {
            "security_id": "EURUSD-FWD",
            "currency": "EUR",
            "quantity": 10_000_000,
        }
        snapshot = {
            "prices": {"EURUSD-FWD": 0.01},
            "fx_rates": {"EUR": 1.08},
        }
        pv = compute_position_pv_usd(position, snapshot)
        assert abs(pv - 108_000.0) < 0.01

    def test_compute_position_missing_price(self):
        """缺少价格时PV为0."""
        position = {"security_id": "UNKNOWN", "currency": "USD", "quantity": 1000}
        snapshot = {"prices": {}, "fx_rates": {"USD": 1.0}}
        pv = compute_position_pv_usd(position, snapshot)
        assert pv == 0.0


class TestExposureService:
    """exposure_service 真实集成测试."""

    def test_compute_exposure_single_position(self):
        """单笔头寸敞口计算."""
        positions = [
            {"security_id": "AAPL", "currency": "USD", "quantity": 1000, "delta": 600.0}
        ]
        snapshot = {"prices": {"AAPL": 175.0}, "fx_rates": {"USD": 1.0}}
        total_delta, total_pv, by_currency = compute_exposure(positions, snapshot)
        assert total_delta == 600.0
        assert total_pv == 175_000.0
        assert "USD" in by_currency
        assert by_currency["USD"]["delta"] == 600.0

    def test_compute_exposure_multi_currency(self):
        """多币种头寸敞口计算."""
        positions = [
            {"security_id": "AAPL", "currency": "USD", "quantity": 1000, "delta": 600.0},
            {"security_id": "EURUSD-FWD", "currency": "EUR", "quantity": 5_000_000, "delta": 50_000.0},
        ]
        snapshot = {
            "prices": {"AAPL": 175.0, "EURUSD-FWD": 0.01},
            "fx_rates": {"USD": 1.0, "EUR": 1.08},
        }
        total_delta, total_pv, by_currency = compute_exposure(positions, snapshot)
        assert total_delta == 50_600.0
        assert "USD" in by_currency
        assert "EUR" in by_currency
        assert by_currency["EUR"]["delta"] == 50_000.0

    def test_compute_exposure_empty_positions(self):
        """空头寸列表."""
        total_delta, total_pv, by_currency = compute_exposure([], {})
        assert total_delta == 0.0
        assert total_pv == 0.0
        assert by_currency == {}


# ---------------------------------------------------------------------------
# End-to-End Business Flow (with real MySQL)
# ---------------------------------------------------------------------------


class TestEndToEndBusinessFlow:
    """端到端业务流程：真实 MySQL + Service 层联动."""

    def test_read_positions_compute_exposure_detect_breach(self, real_db_cursor, real_db_connection):
        """从真实DB读取头寸 → 计算敞口 → 检测breach."""
        # 1. 从 DB 读取 Equities desk 的头寸
        real_db_cursor.execute(
            "SELECT position_id, trader_id, desk, security_id, quantity, delta, currency "
            "FROM positions WHERE desk = %s",
            ("Equities",),
        )
        rows = real_db_cursor.fetchall()
        assert len(rows) > 0, "Equities desk 应有测试数据"

        # 2. 构造 positions 列表供 exposure 计算
        positions = []
        for row in rows:
            positions.append({
                "security_id": row["security_id"],
                "currency": row["currency"],
                "quantity": float(row["quantity"]),
                "delta": float(row["delta"]),
            })

        # 3. 使用 snapshot 计算 exposure
        snapshot = {
            "prices": {p["security_id"]: 100.0 for p in positions},
            "fx_rates": {"USD": 1.0, "EUR": 1.08, "GBP": 1.26, "JPY": 0.0067},
        }
        total_delta, total_pv, by_currency = compute_exposure(positions, snapshot)
        assert isinstance(total_delta, float)
        assert isinstance(total_pv, float)

        # 4. 用 breach_service 检测是否超限（用一个较小的阈值）
        breaches = build_abs_delta_breaches(total_delta=total_delta, abs_delta_limit=100.0)
        # Equities desk 有多笔头寸，total delta 绝对值应大于 100
        assert len(breaches) > 0

    def test_generate_alert_and_persist_to_mysql(self, real_db_cursor, real_db_connection):
        """生成alert并持久化到真实MySQL，然后查询验证."""
        # 1. 生成 alert
        request_id = f"inttest-{uuid.uuid4().hex[:8]}"
        alerts = evaluate_desk_delta_breach(
            desk="IntTest E2E Desk",
            abs_delta=2_000_000.0,
            threshold=1_000_000.0,
            request_id=request_id,
        )
        assert len(alerts) == 1
        alert = alerts[0]

        # 2. 持久化到 alerts 表
        real_db_cursor.execute(
            """INSERT INTO alerts
               (alert_id, request_id, alert_type, severity, desk, trader_id,
                metric_name, metric_value, threshold_value, breach_amount, message,
                acknowledged)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                alert["alert_id"],
                alert["request_id"],
                alert["alert_type"],
                alert["severity"],
                alert["desk"],
                alert.get("trader_id"),
                alert["metric_name"],
                alert["metric_value"],
                alert["threshold_value"],
                alert["breach_amount"],
                alert["message"],
                alert["acknowledged"],
            ),
        )

        # 3. 查询验证
        real_db_cursor.execute(
            "SELECT * FROM alerts WHERE alert_id = %s", (alert["alert_id"],)
        )
        row = real_db_cursor.fetchone()
        assert row is not None
        assert row["request_id"] == request_id
        assert row["alert_type"] == "DESK_DELTA_BREACH"
        assert row["severity"] == "CRITICAL"  # breach 100% > 50%
        assert row["desk"] == "IntTest E2E Desk"
        assert float(row["metric_value"]) == 2_000_000.0
        assert float(row["threshold_value"]) == 1_000_000.0
        assert float(row["breach_amount"]) == 1_000_000.0

    def test_insert_positions_and_full_pipeline(self, real_db_cursor, real_db_connection):
        """插入测试头寸 → 完整pipeline → 验证结果."""
        desk_name = f"IntTest-{uuid.uuid4().hex[:6]}"
        request_id = f"inttest-{uuid.uuid4().hex[:8]}"

        # 1. 插入测试头寸
        test_positions = [
            PositionFactory.create(desk=desk_name, delta=Decimal("800000.0000"), currency="USD"),
            PositionFactory.create(desk=desk_name, delta=Decimal("600000.0000"), currency="USD"),
            PositionFactory.create(desk=desk_name, delta=Decimal("-200000.0000"), currency="EUR"),
        ]
        for pos in test_positions:
            real_db_cursor.execute(
                """INSERT INTO positions
                   (position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    pos["position_id"],
                    pos["trader_id"],
                    pos["desk"],
                    pos["security_id"],
                    pos["quantity"],
                    pos["delta"],
                    pos["entry_date"],
                    pos["currency"],
                ),
            )

        # 2. 读取回来
        real_db_cursor.execute(
            "SELECT security_id, currency, quantity, delta FROM positions WHERE desk = %s",
            (desk_name,),
        )
        rows = real_db_cursor.fetchall()
        assert len(rows) == 3

        # 3. 计算 exposure
        positions = [
            {
                "security_id": r["security_id"],
                "currency": r["currency"],
                "quantity": float(r["quantity"]),
                "delta": float(r["delta"]),
            }
            for r in rows
        ]
        snapshot = {
            "prices": {p["security_id"]: 50.0 for p in positions},
            "fx_rates": {"USD": 1.0, "EUR": 1.08},
        }
        total_delta, total_pv, by_currency = compute_exposure(positions, snapshot)

        # total_delta = 800000 + 600000 + (-200000) = 1200000
        assert abs(total_delta - 1_200_000.0) < 0.01

        # 4. breach 检测
        breaches = build_abs_delta_breaches(total_delta=total_delta, abs_delta_limit=1_000_000.0)
        assert len(breaches) == 1

        # 5. 生成 alert
        alerts = evaluate_desk_delta_breach(
            desk=desk_name,
            abs_delta=abs(total_delta),
            threshold=1_000_000.0,
            request_id=request_id,
        )
        assert len(alerts) == 1
        assert alerts[0]["severity"] in ("INFO", "WARNING", "CRITICAL")

        # 6. 持久化 alert
        alert = alerts[0]
        real_db_cursor.execute(
            """INSERT INTO alerts
               (alert_id, request_id, alert_type, severity, desk, trader_id,
                metric_name, metric_value, threshold_value, breach_amount, message,
                acknowledged)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                alert["alert_id"],
                alert["request_id"],
                alert["alert_type"],
                alert["severity"],
                alert["desk"],
                alert.get("trader_id"),
                alert["metric_name"],
                alert["metric_value"],
                alert["threshold_value"],
                alert["breach_amount"],
                alert["message"],
                alert["acknowledged"],
            ),
        )

        # 7. 查询验证
        real_db_cursor.execute(
            "SELECT * FROM alerts WHERE request_id = %s", (request_id,)
        )
        persisted = real_db_cursor.fetchone()
        assert persisted is not None
        assert persisted["desk"] == desk_name
        assert persisted["alert_type"] == "DESK_DELTA_BREACH"

    def test_redis_cache_basic(self, real_redis):
        """验证 Redis 基本读写操作."""
        key = f"inttest:service:{uuid.uuid4().hex[:8]}"
        real_redis.set(key, "hello-risk-monitor")
        val = real_redis.get(key)
        assert val == b"hello-risk-monitor"
        real_redis.delete(key)
        assert real_redis.get(key) is None
