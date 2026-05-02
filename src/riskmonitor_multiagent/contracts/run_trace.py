from __future__ import annotations

from typing import Any

from riskmonitor_multiagent.utils import is_non_empty_str

RUN_TRACE_SCHEMA_VERSION = "run_trace.v2"
RUN_TRACE_ENTRY_CATEGORIES = {
    "task",
    "plan",
    "step",
    "message",
    "command",
    "receipt",
    "approval",
    "memory",
    "final",
    "version_snapshot",
}


def validate_run_trace(snapshot: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(snapshot, dict):
        return False, ["run_trace must be dict"]
    if snapshot.get("schema_version") != RUN_TRACE_SCHEMA_VERSION:
        errors.append("bad_run_trace_schema_version")
    if not is_non_empty_str(snapshot.get("run_id")):
        errors.append("bad_run_trace_run_id")
    if not is_non_empty_str(snapshot.get("entry_type")):
        errors.append("bad_run_trace_entry_type")
    if not is_non_empty_str(snapshot.get("status")):
        errors.append("bad_run_trace_status")
    if not isinstance(snapshot.get("version_snapshot"), dict):
        errors.append("bad_run_trace_version_snapshot")
    if not isinstance(snapshot.get("failure_summary"), dict):
        errors.append("bad_run_trace_failure_summary")
    entries = snapshot.get("entries")
    if not isinstance(entries, list):
        errors.append("bad_run_trace_entries")
    else:
        for entry in entries:
            if not isinstance(entry, dict):
                errors.append("bad_run_trace_entry")
                continue
            if entry.get("category") not in RUN_TRACE_ENTRY_CATEGORIES:
                errors.append("bad_run_trace_entry_category")
            if not is_non_empty_str(entry.get("trace_type")):
                errors.append("bad_run_trace_trace_type")
            if not isinstance(entry.get("timestamp_ms"), int):
                errors.append("bad_run_trace_timestamp_ms")
            if not isinstance(entry.get("summary"), dict):
                errors.append("bad_run_trace_summary")
            if not isinstance(entry.get("payload"), dict):
                errors.append("bad_run_trace_payload")
    return len(errors) == 0, errors


def normalize_run_trace(snapshot: dict[str, Any]) -> dict[str, Any]:
    raw = dict(snapshot) if isinstance(snapshot, dict) else {}
    return {
        "schema_version": RUN_TRACE_SCHEMA_VERSION,
        "run_id": str(raw.get("run_id") or ""),
        "entry_type": str(raw.get("entry_type") or ""),
        "status": str(raw.get("status") or "unknown"),
        "task_id": str(raw.get("task_id") or "") or None,
        "version_snapshot": dict(raw.get("version_snapshot") or {}),
        "failure_summary": dict(raw.get("failure_summary") or {}),
        "summary": dict(raw.get("summary") or {}),
        "entries": [
            {
                "category": str(entry.get("category") or ""),
                "trace_type": str(entry.get("trace_type") or ""),
                "timestamp_ms": int(entry.get("timestamp_ms") or 0),
                "status": str(entry.get("status") or "recorded"),
                "summary": dict(entry.get("summary") or {}),
                "payload": dict(entry.get("payload") or {}),
            }
            for entry in raw.get("entries", [])
            if isinstance(entry, dict)
        ],
    }


__all__ = [
    "RUN_TRACE_SCHEMA_VERSION",
    "RUN_TRACE_ENTRY_CATEGORIES",
    "validate_run_trace",
    "normalize_run_trace",
]
