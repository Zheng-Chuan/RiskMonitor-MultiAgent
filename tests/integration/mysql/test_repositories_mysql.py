"""Repository 层真实集成测试.

连接 Docker 中的真实 MySQL，不使用 mock。
每个测试使用唯一前缀数据，测试结束后清理。
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import pymysql
import pytest

from riskmonitor_multiagent.data_access import alerts_repository, audit_repository, positions_repository
from riskmonitor_multiagent.data_access.mysql_engine import get_engine
from tests.integration.factories import AlertFactory, AuditEventFactory, PositionFactory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_cleanup_cursor():
    """获取一个用于清理数据的连接和游标."""
    conn = get_engine().raw_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    return conn, cursor


def _cleanup_alerts(*alert_ids: str):
    """按 alert_id 清理."""
    if not alert_ids:
        return
    conn, cursor = _get_cleanup_cursor()
    try:
        placeholders = ",".join(["%s"] * len(alert_ids))
        cursor.execute(f"DELETE FROM alerts WHERE alert_id IN ({placeholders})", alert_ids)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _cleanup_positions(*position_ids: str):
    """按 position_id 清理."""
    if not position_ids:
        return
    conn, cursor = _get_cleanup_cursor()
    try:
        placeholders = ",".join(["%s"] * len(position_ids))
        cursor.execute(f"DELETE FROM positions WHERE position_id IN ({placeholders})", position_ids)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _cleanup_audit_events(*audit_ids: str):
    """按 audit_id 清理."""
    if not audit_ids:
        return
    conn, cursor = _get_cleanup_cursor()
    try:
        placeholders = ",".join(["%s"] * len(audit_ids))
        cursor.execute(f"DELETE FROM audit_events WHERE audit_id IN ({placeholders})", audit_ids)
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _insert_position(pos: dict):
    """直接插入一条 position 记录（positions_repository 只有读操作）."""
    conn, cursor = _get_cleanup_cursor()
    try:
        cursor.execute(
            """
            INSERT INTO positions (position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                pos["position_id"], pos["trader_id"], pos["desk"],
                pos["security_id"], pos["quantity"], pos["delta"],
                pos["entry_date"], pos["currency"],
            ),
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()


def _make_alert_record(factory_dict: dict) -> dict:
    """将 AlertFactory 输出补充为 save_alert 要求的完整字段."""
    record = dict(factory_dict)
    record.setdefault("created_at", datetime.now())
    record.setdefault("acknowledged", False)
    record.setdefault("acknowledged_at", None)
    record.setdefault("acknowledged_by", None)
    return record


# ===========================================================================
# Alerts Repository Tests
# ===========================================================================


class TestAlertsRepository:
    """alerts_repository 真实集成测试."""

    def test_save_and_get_alert(self):
        """保存单条 alert 并按 ID 查询."""
        alert = _make_alert_record(AlertFactory.create())
        alert_id = alert["alert_id"]

        try:
            alerts_repository.save_alert(alert)

            result = alerts_repository.get_alert_by_id(alert_id)
            assert result is not None
            assert result["alert_id"] == alert_id
            assert result["severity"] == alert["severity"]
            assert result["desk"] == alert["desk"]
            assert result["message"] == alert["message"]
        finally:
            _cleanup_alerts(alert_id)

    def test_save_alerts_batch(self):
        """批量保存多条 alert."""
        alerts = [_make_alert_record(AlertFactory.create()) for _ in range(3)]
        alert_ids = [a["alert_id"] for a in alerts]

        try:
            alerts_repository.save_alerts_batch(alerts)

            for aid in alert_ids:
                result = alerts_repository.get_alert_by_id(aid)
                assert result is not None
                assert result["alert_id"] == aid
        finally:
            _cleanup_alerts(*alert_ids)

    def test_save_alerts_batch_empty_list(self):
        """批量保存空列表不报错."""
        alerts_repository.save_alerts_batch([])

    def test_get_alert_by_id_not_found(self):
        """查询不存在的 alert_id 返回 None."""
        result = alerts_repository.get_alert_by_id("nonexistent-alert-id-xyz")
        assert result is None

    def test_get_alerts_by_request_id(self):
        """按 request_id 查询关联的多条 alert."""
        shared_request_id = f"inttest-req-{uuid.uuid4().hex[:8]}"
        alerts = [
            _make_alert_record(AlertFactory.create(request_id=shared_request_id, severity="HIGH")),
            _make_alert_record(AlertFactory.create(request_id=shared_request_id, severity="WARNING")),
        ]
        alert_ids = [a["alert_id"] for a in alerts]

        try:
            alerts_repository.save_alerts_batch(alerts)

            results = alerts_repository.get_alerts_by_request_id(shared_request_id)
            assert len(results) == 2
            result_ids = {r["alert_id"] for r in results}
            assert set(alert_ids) == result_ids
        finally:
            _cleanup_alerts(*alert_ids)

    def test_get_alerts_by_request_id_empty(self):
        """查询不存在的 request_id 返回空列表."""
        results = alerts_repository.get_alerts_by_request_id("nonexistent-req-id")
        assert results == []

    def test_get_recent_alerts_no_filter(self):
        """查询最近的 alert，无过滤条件."""
        alert = _make_alert_record(AlertFactory.create(severity="CRITICAL"))
        alert_id = alert["alert_id"]

        try:
            alerts_repository.save_alert(alert)

            results = alerts_repository.get_recent_alerts(limit=10)
            assert len(results) >= 1
            found = any(r["alert_id"] == alert_id for r in results)
            assert found, "刚插入的 alert 应在最近列表中"
        finally:
            _cleanup_alerts(alert_id)

    def test_get_recent_alerts_filter_by_severity(self):
        """按 severity 过滤."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        alert_high = _make_alert_record(AlertFactory.create(severity="HIGH", desk=unique_desk))
        alert_low = _make_alert_record(AlertFactory.create(severity="LOW", desk=unique_desk))
        ids = [alert_high["alert_id"], alert_low["alert_id"]]

        try:
            alerts_repository.save_alerts_batch([alert_high, alert_low])

            results = alerts_repository.get_recent_alerts(limit=100, severity="HIGH")
            result_ids = {r["alert_id"] for r in results}
            assert alert_high["alert_id"] in result_ids
            assert alert_low["alert_id"] not in result_ids
        finally:
            _cleanup_alerts(*ids)

    def test_get_recent_alerts_filter_by_desk(self):
        """按 desk 过滤."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        alert_in = _make_alert_record(AlertFactory.create(desk=unique_desk))
        alert_out = _make_alert_record(AlertFactory.create(desk="Other Desk"))
        ids = [alert_in["alert_id"], alert_out["alert_id"]]

        try:
            alerts_repository.save_alerts_batch([alert_in, alert_out])

            results = alerts_repository.get_recent_alerts(limit=100, desk=unique_desk)
            result_ids = {r["alert_id"] for r in results}
            assert alert_in["alert_id"] in result_ids
            assert alert_out["alert_id"] not in result_ids
        finally:
            _cleanup_alerts(*ids)

    def test_get_recent_alerts_filter_by_severity_and_desk(self):
        """同时按 severity 和 desk 过滤."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        alert_match = _make_alert_record(AlertFactory.create(severity="CRITICAL", desk=unique_desk))
        alert_wrong_sev = _make_alert_record(AlertFactory.create(severity="LOW", desk=unique_desk))
        alert_wrong_desk = _make_alert_record(AlertFactory.create(severity="CRITICAL", desk="Wrong Desk"))
        ids = [alert_match["alert_id"], alert_wrong_sev["alert_id"], alert_wrong_desk["alert_id"]]

        try:
            alerts_repository.save_alerts_batch([alert_match, alert_wrong_sev, alert_wrong_desk])

            results = alerts_repository.get_recent_alerts(limit=100, severity="CRITICAL", desk=unique_desk)
            result_ids = {r["alert_id"] for r in results}
            assert alert_match["alert_id"] in result_ids
            assert alert_wrong_sev["alert_id"] not in result_ids
            assert alert_wrong_desk["alert_id"] not in result_ids
        finally:
            _cleanup_alerts(*ids)

    def test_get_recent_alerts_limit(self):
        """limit 参数限制返回数量."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        alerts = [_make_alert_record(AlertFactory.create(desk=unique_desk)) for _ in range(5)]
        ids = [a["alert_id"] for a in alerts]

        try:
            alerts_repository.save_alerts_batch(alerts)

            results = alerts_repository.get_recent_alerts(limit=2, desk=unique_desk)
            assert len(results) == 2
        finally:
            _cleanup_alerts(*ids)


# ===========================================================================
# Positions Repository Tests
# ===========================================================================


class TestPositionsRepository:
    """positions_repository 真实集成测试."""

    def test_fetch_all_positions(self):
        """获取所有 positions（数据库中有演示数据）."""
        results = positions_repository.fetch_all_positions()
        assert isinstance(results, list)
        # DB中有init_db.sql插入的演示数据
        assert len(results) > 0
        # 检查返回字段
        row = results[0]
        assert "position_id" in row
        assert "trader_id" in row
        assert "desk" in row
        assert "delta" in row

    def test_fetch_all_positions_includes_test_data(self):
        """插入测试数据后应出现在 fetch_all 结果中."""
        pos = PositionFactory.create(position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}")
        _insert_position(pos)

        try:
            results = positions_repository.fetch_all_positions()
            found = any(r["position_id"] == pos["position_id"] for r in results)
            assert found, "插入的测试数据应出现在 fetch_all_positions 结果中"
        finally:
            _cleanup_positions(pos["position_id"])

    def test_fetch_positions_by_desk(self):
        """按 desk 分页查询."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        positions = [
            PositionFactory.create(
                position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
                desk=unique_desk,
            )
            for _ in range(3)
        ]
        for p in positions:
            _insert_position(p)
        ids = [p["position_id"] for p in positions]

        try:
            results = positions_repository.fetch_positions_by_desk(
                desk_name=unique_desk,
                start_date=None,
                end_date=None,
                limit=10,
                offset=0,
            )
            assert len(results) == 3
            for r in results:
                assert r["desk"] == unique_desk
        finally:
            _cleanup_positions(*ids)

    def test_fetch_positions_by_desk_pagination(self):
        """fetch_positions_by_desk 分页 offset 正确."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        positions = [
            PositionFactory.create(
                position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
                desk=unique_desk,
            )
            for _ in range(5)
        ]
        for p in positions:
            _insert_position(p)
        ids = [p["position_id"] for p in positions]

        try:
            page1 = positions_repository.fetch_positions_by_desk(
                desk_name=unique_desk, start_date=None, end_date=None, limit=3, offset=0,
            )
            page2 = positions_repository.fetch_positions_by_desk(
                desk_name=unique_desk, start_date=None, end_date=None, limit=3, offset=3,
            )
            assert len(page1) == 3
            assert len(page2) == 2
            # 两页之间无重复
            ids_page1 = {r["position_id"] for r in page1}
            ids_page2 = {r["position_id"] for r in page2}
            assert ids_page1.isdisjoint(ids_page2)
        finally:
            _cleanup_positions(*ids)

    def test_fetch_positions_by_desk_empty(self):
        """不存在的 desk 返回空列表."""
        results = positions_repository.fetch_positions_by_desk(
            desk_name="nonexistent-desk-xyz",
            start_date=None,
            end_date=None,
            limit=10,
            offset=0,
        )
        assert results == []

    def test_fetch_positions_by_desk_with_date_range(self):
        """按 desk + 日期范围查询."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        today = date.today()
        old_date = today - timedelta(days=30)
        recent_date = today - timedelta(days=1)

        pos_old = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            desk=unique_desk,
            entry_date=old_date,
        )
        pos_recent = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            desk=unique_desk,
            entry_date=recent_date,
        )
        _insert_position(pos_old)
        _insert_position(pos_recent)
        ids = [pos_old["position_id"], pos_recent["position_id"]]

        try:
            # 只查最近7天
            results = positions_repository.fetch_positions_by_desk(
                desk_name=unique_desk,
                start_date=str(today - timedelta(days=7)),
                end_date=str(today),
                limit=10,
                offset=0,
            )
            result_ids = {r["position_id"] for r in results}
            assert pos_recent["position_id"] in result_ids
            assert pos_old["position_id"] not in result_ids
        finally:
            _cleanup_positions(*ids)

    def test_fetch_positions_by_trader(self):
        """按 trader_id 查询."""
        unique_trader = f"inttest-trader-{uuid.uuid4().hex[:6]}"
        positions = [
            PositionFactory.create(
                position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
                trader_id=unique_trader,
            )
            for _ in range(3)
        ]
        for p in positions:
            _insert_position(p)
        ids = [p["position_id"] for p in positions]

        try:
            results = positions_repository.fetch_positions_by_trader(trader_id=unique_trader)
            assert len(results) == 3
            for r in results:
                assert r["trader_id"] == unique_trader
        finally:
            _cleanup_positions(*ids)

    def test_fetch_positions_by_trader_with_date_range(self):
        """按 trader + 日期范围查询."""
        unique_trader = f"inttest-trader-{uuid.uuid4().hex[:6]}"
        today = date.today()
        pos_in_range = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            trader_id=unique_trader,
            entry_date=today - timedelta(days=2),
        )
        pos_out_range = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            trader_id=unique_trader,
            entry_date=today - timedelta(days=60),
        )
        _insert_position(pos_in_range)
        _insert_position(pos_out_range)
        ids = [pos_in_range["position_id"], pos_out_range["position_id"]]

        try:
            results = positions_repository.fetch_positions_by_trader(
                trader_id=unique_trader,
                start_date=str(today - timedelta(days=7)),
                end_date=str(today),
            )
            result_ids = {r["position_id"] for r in results}
            assert pos_in_range["position_id"] in result_ids
            assert pos_out_range["position_id"] not in result_ids
        finally:
            _cleanup_positions(*ids)

    def test_fetch_positions_by_trader_not_found(self):
        """查询不存在的 trader 返回空列表."""
        results = positions_repository.fetch_positions_by_trader(trader_id="nonexistent-trader-xyz")
        assert results == []

    def test_fetch_total_delta(self):
        """聚合总 delta."""
        result = positions_repository.fetch_total_delta()
        # 数据库中有演示数据，总delta应该是某个非零值
        assert isinstance(result, float)

    def test_fetch_total_delta_includes_test_data(self):
        """插入测试数据后 total_delta 会增加."""
        delta_before = positions_repository.fetch_total_delta()

        pos = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            delta=Decimal("12345.0000"),
        )
        _insert_position(pos)

        try:
            delta_after = positions_repository.fetch_total_delta()
            assert abs(delta_after - delta_before - 12345.0) < 0.01
        finally:
            _cleanup_positions(pos["position_id"])

    def test_fetch_desk_delta_summary(self):
        """按 desk 聚合 delta 汇总."""
        results = positions_repository.fetch_desk_delta_summary()
        assert isinstance(results, list)
        assert len(results) > 0
        row = results[0]
        assert "desk" in row
        assert "desk_delta" in row
        assert "position_count" in row

    def test_fetch_desk_delta_summary_with_test_desk(self):
        """插入特定desk的数据后，汇总中可以找到该desk."""
        unique_desk = f"inttest-desk-{uuid.uuid4().hex[:6]}"
        pos1 = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            desk=unique_desk,
            delta=Decimal("100.0000"),
        )
        pos2 = PositionFactory.create(
            position_id=f"inttest-pos-{uuid.uuid4().hex[:8]}",
            desk=unique_desk,
            delta=Decimal("200.0000"),
        )
        _insert_position(pos1)
        _insert_position(pos2)
        ids = [pos1["position_id"], pos2["position_id"]]

        try:
            results = positions_repository.fetch_desk_delta_summary()
            desk_row = next((r for r in results if r["desk"] == unique_desk), None)
            assert desk_row is not None
            assert float(desk_row["desk_delta"]) == pytest.approx(300.0, abs=0.01)
            assert desk_row["position_count"] == 2
        finally:
            _cleanup_positions(*ids)


# ===========================================================================
# Audit Repository Tests
# ===========================================================================


class TestAuditRepository:
    """audit_repository 真实集成测试."""

    def test_save_and_get_audit_record(self):
        """保存审计记录并按 ID 查询."""
        record = AuditEventFactory.create()
        audit_id = record["audit_id"]

        try:
            audit_repository.save_audit_record(record)

            result = audit_repository.get_audit_record_by_id(audit_id)
            assert result is not None
            assert result["audit_id"] == audit_id
            assert result["target_agent"] == record["target_agent"]
            assert result["action"] == record["action"]
            assert result["actor"] == record["actor"]
            assert result["ok"] == record["ok"]
        finally:
            _cleanup_audit_events(audit_id)

    def test_get_audit_record_by_id_not_found(self):
        """查询不存在的 audit_id 返回 None."""
        result = audit_repository.get_audit_record_by_id("nonexistent-audit-id-xyz")
        assert result is None

    def test_save_audit_records_batch(self):
        """批量保存审计记录."""
        records = AuditEventFactory.create_batch(count=4)
        audit_ids = [r["audit_id"] for r in records]

        try:
            audit_repository.save_audit_records_batch(records)

            for aid in audit_ids:
                result = audit_repository.get_audit_record_by_id(aid)
                assert result is not None
                assert result["audit_id"] == aid
        finally:
            _cleanup_audit_events(*audit_ids)

    def test_save_audit_records_batch_empty(self):
        """批量保存空列表不报错."""
        audit_repository.save_audit_records_batch([])

    def test_get_audit_records_by_event_id(self):
        """按 event_id 查询多条审计记录."""
        shared_event_id = f"inttest-event-{uuid.uuid4().hex[:8]}"
        records = [
            AuditEventFactory.create(event_id=shared_event_id, action=f"action-{i}")
            for i in range(3)
        ]
        audit_ids = [r["audit_id"] for r in records]

        try:
            audit_repository.save_audit_records_batch(records)

            results = audit_repository.get_audit_records_by_event_id(shared_event_id)
            assert len(results) == 3
            result_audit_ids = {r["audit_id"] for r in results}
            assert set(audit_ids) == result_audit_ids
        finally:
            _cleanup_audit_events(*audit_ids)

    def test_get_audit_records_by_event_id_empty(self):
        """查询不存在的 event_id 返回空列表."""
        results = audit_repository.get_audit_records_by_event_id("nonexistent-event-id")
        assert results == []

    def test_get_audit_records_by_event_id_limit(self):
        """limit 参数限制返回数量."""
        shared_event_id = f"inttest-event-{uuid.uuid4().hex[:8]}"
        records = [
            AuditEventFactory.create(event_id=shared_event_id)
            for _ in range(5)
        ]
        audit_ids = [r["audit_id"] for r in records]

        try:
            audit_repository.save_audit_records_batch(records)

            results = audit_repository.get_audit_records_by_event_id(shared_event_id, limit=2)
            assert len(results) == 2
        finally:
            _cleanup_audit_events(*audit_ids)

    def test_save_audit_record_with_approval_fields(self):
        """保存含审批信息的审计记录."""
        record = AuditEventFactory.create(
            approved=True,
            approved_by="manager-001",
            approval_reason="within risk limit",
        )
        audit_id = record["audit_id"]

        try:
            audit_repository.save_audit_record(record)

            result = audit_repository.get_audit_record_by_id(audit_id)
            assert result is not None
            assert result["approved"] == 1  # MySQL stores boolean as tinyint
            assert result["approved_by"] == "manager-001"
            assert result["approval_reason"] == "within risk limit"
        finally:
            _cleanup_audit_events(audit_id)

    def test_save_audit_record_with_error(self):
        """保存含错误信息的审计记录."""
        record = AuditEventFactory.create(
            ok=False,
            error="Connection timeout to downstream service",
        )
        audit_id = record["audit_id"]

        try:
            audit_repository.save_audit_record(record)

            result = audit_repository.get_audit_record_by_id(audit_id)
            assert result is not None
            assert result["ok"] == 0  # MySQL boolean
            assert result["error"] == "Connection timeout to downstream service"
        finally:
            _cleanup_audit_events(audit_id)
