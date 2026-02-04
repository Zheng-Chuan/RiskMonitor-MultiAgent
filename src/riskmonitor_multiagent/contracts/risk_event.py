from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

RISK_EVENT_SCHEMA_VERSION = "risk_event.v1"

_SEVERITIES = {"INFO", "WARNING", "CRITICAL"}
_CATEGORIES = {"system", "business"}


def _iso_utc_from_ms(epoch_ms: int) -> str:
    dt = datetime.fromtimestamp(epoch_ms / 1000.0, tz=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _parse_iso_utc(value: str) -> Optional[datetime]:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_event_id(*, topic: str, partition: int, offset: int) -> str:
    return f"{topic}:{int(partition)}:{int(offset)}"


@dataclass(frozen=True)
class RiskEvent:
    schema_version: str
    event_id: str
    correlation_id: str
    causation_id: Optional[str]
    occurred_at: str
    producer: str
    severity: str
    category: str
    actionability: bool
    confidence: float
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "occurred_at": self.occurred_at,
            "producer": self.producer,
            "severity": self.severity,
            "category": self.category,
            "actionability": self.actionability,
            "confidence": self.confidence,
            "payload": self.payload,
        }


def validate_risk_event(event: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(event, dict):
        return False, ["event must be dict"]

    required_str = [
        "schema_version",
        "event_id",
        "correlation_id",
        "occurred_at",
        "producer",
        "severity",
        "category",
    ]
    for key in required_str:
        v = event.get(key)
        if not isinstance(v, str) or not v.strip():
            errors.append(f"missing_or_bad_{key}")

    schema_version = event.get("schema_version")
    if isinstance(schema_version, str) and schema_version != RISK_EVENT_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    causation_id = event.get("causation_id")
    if causation_id is not None and (not isinstance(causation_id, str) or not causation_id.strip()):
        errors.append("bad_causation_id")

    occurred_at = event.get("occurred_at")
    if isinstance(occurred_at, str) and _parse_iso_utc(occurred_at) is None:
        errors.append("bad_occurred_at")

    severity = event.get("severity")
    if isinstance(severity, str) and severity not in _SEVERITIES:
        errors.append("bad_severity")

    category = event.get("category")
    if isinstance(category, str) and category not in _CATEGORIES:
        errors.append("bad_category")

    actionability = event.get("actionability")
    if not isinstance(actionability, bool):
        errors.append("bad_actionability")

    confidence = event.get("confidence")
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        errors.append("bad_confidence")

    payload = event.get("payload")
    if not isinstance(payload, dict):
        errors.append("bad_payload")

    return len(errors) == 0, errors


def normalize_cdc_event(
    *,
    raw_record: dict[str, Any],
    topic: str,
    partition: int,
    offset: int,
    message_ts_ms: Optional[int],
    producer: str = "debezium",
) -> RiskEvent:
    ts_ms = message_ts_ms
    if ts_ms is None:
        ts_candidate = raw_record.get("__ts_ms") or raw_record.get("ts_ms") or raw_record.get("event_ts_ms")
        if isinstance(ts_candidate, int):
            ts_ms = ts_candidate
        elif isinstance(ts_candidate, str) and ts_candidate.isdigit():
            ts_ms = int(ts_candidate)

    if ts_ms is None:
        ts_ms = int(time.time() * 1000)

    event_id = build_event_id(topic=topic, partition=partition, offset=offset)
    payload = dict(raw_record)
    payload["_meta"] = {
        "topic": topic,
        "partition": int(partition),
        "offset": int(offset),
        "message_ts_ms": int(ts_ms),
    }
    return RiskEvent(
        schema_version=RISK_EVENT_SCHEMA_VERSION,
        event_id=event_id,
        correlation_id=event_id,
        causation_id=None,
        occurred_at=_iso_utc_from_ms(int(ts_ms)),
        producer=producer,
        severity="INFO",
        category="business",
        actionability=False,
        confidence=1.0,
        payload=payload,
    )


def build_breach_event(
    *,
    source_event: RiskEvent,
    desk: str,
    exposure: float,
    threshold: float,
    now_ms: Optional[int] = None,
) -> RiskEvent:
    source_event_id = source_event.event_id
    event_id = f"{source_event_id}:breach"
    severity = "CRITICAL" if abs(exposure) >= abs(threshold) * 2.0 else "WARNING"
    ts_ms = int(now_ms) if isinstance(now_ms, int) else int(time.time() * 1000)
    payload = {
        "signal_type": "desk_exposure_breach",
        "desk": desk,
        "exposure": float(exposure),
        "threshold": float(threshold),
        "source_event_id": source_event_id,
        "source_producer": source_event.producer,
        "source_occurred_at": source_event.occurred_at,
        "source_payload_meta": source_event.payload.get("_meta") if isinstance(source_event.payload, dict) else None,
    }
    return RiskEvent(
        schema_version=RISK_EVENT_SCHEMA_VERSION,
        event_id=event_id,
        correlation_id=source_event.correlation_id,
        causation_id=source_event_id,
        occurred_at=_iso_utc_from_ms(ts_ms),
        producer="sentinel",
        severity=severity,
        category="business",
        actionability=True,
        confidence=0.9,
        payload=payload,
    )

