"""测试数据工厂 - 生成符合数据库schema的真实数据.

这些工厂函数生成的数据可以直接插入到真实MySQL中，
字段与 scripts/init_db.sql 中定义的 schema 完全一致。
"""

import time
import uuid
from datetime import date, datetime
from decimal import Decimal


class PositionFactory:
    """positions 表数据工厂."""

    @staticmethod
    def create(
        position_id: str | None = None,
        trader_id: str = "test-trader-001",
        desk: str = "Test Desk",
        security_id: str = "TEST-SEC-001",
        quantity: Decimal = Decimal("1000.0000"),
        delta: Decimal = Decimal("500000.0000"),
        entry_date: date | None = None,
        currency: str = "USD",
    ) -> dict:
        return {
            "position_id": position_id or f"test-pos-{uuid.uuid4().hex[:8]}",
            "trader_id": trader_id,
            "desk": desk,
            "security_id": security_id,
            "quantity": quantity,
            "delta": delta,
            "entry_date": entry_date or date.today(),
            "currency": currency,
        }

    @staticmethod
    def create_batch(count: int = 5, **kwargs) -> list[dict]:
        """批量创建 position 记录."""
        return [PositionFactory.create(**kwargs) for _ in range(count)]


class AlertFactory:
    """alerts 表数据工厂."""

    @staticmethod
    def create(
        alert_id: str | None = None,
        request_id: str | None = None,
        alert_type: str = "DELTA_BREACH",
        severity: str = "WARNING",
        desk: str = "Test Desk",
        trader_id: str = "test-trader-001",
        metric_name: str = "abs_delta",
        metric_value: Decimal = Decimal("1200000.00"),
        threshold_value: Decimal = Decimal("1000000.00"),
        breach_amount: Decimal = Decimal("200000.00"),
        message: str = "Test alert - delta breach detected",
    ) -> dict:
        return {
            "alert_id": alert_id or f"test-alert-{uuid.uuid4().hex[:8]}",
            "request_id": request_id or str(uuid.uuid4()),
            "alert_type": alert_type,
            "severity": severity,
            "desk": desk,
            "trader_id": trader_id,
            "metric_name": metric_name,
            "metric_value": metric_value,
            "threshold_value": threshold_value,
            "breach_amount": breach_amount,
            "message": message,
        }

    @staticmethod
    def create_batch(count: int = 5, **kwargs) -> list[dict]:
        """批量创建 alert 记录."""
        return [AlertFactory.create(**kwargs) for _ in range(count)]


class AuditEventFactory:
    """audit_events 表数据工厂."""

    @staticmethod
    def create(
        audit_id: str | None = None,
        event_id: str | None = None,
        correlation_id: str | None = None,
        run_id: str | None = None,
        command_id: str | None = None,
        target_agent: str = "test-agent",
        action: str = "test-action",
        actor: str = "test-user",
        approved: bool = False,
        approved_by: str | None = None,
        approval_reason: str | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> dict:
        return {
            "audit_id": audit_id or f"test-audit-{uuid.uuid4().hex[:8]}",
            "ts_ms": int(time.time() * 1000),
            "event_id": event_id or str(uuid.uuid4()),
            "correlation_id": correlation_id or str(uuid.uuid4()),
            "run_id": run_id or str(uuid.uuid4()),
            "command_id": command_id or str(uuid.uuid4()),
            "target_agent": target_agent,
            "action": action,
            "actor": actor,
            "approved": approved,
            "approved_by": approved_by,
            "approval_reason": approval_reason,
            "ok": ok,
            "error": error,
        }

    @staticmethod
    def create_batch(count: int = 5, **kwargs) -> list[dict]:
        """批量创建 audit_event 记录."""
        return [AuditEventFactory.create(**kwargs) for _ in range(count)]
