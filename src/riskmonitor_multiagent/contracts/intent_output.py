from __future__ import annotations

from typing import Any


INTENT_OUTPUT_SCHEMA_VERSION = "intent_output.v2"


def _is_non_empty_str(v: object) -> bool:
    return isinstance(v, str) and bool(v.strip())


def validate_intent_output(output: dict[str, Any]) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(output, dict):
        return False, ["output must be dict"]

    schema_version = output.get("schema_version")
    if schema_version is None:
        pass
    elif not _is_non_empty_str(schema_version):
        errors.append("bad_schema_version")
    elif schema_version != INTENT_OUTPUT_SCHEMA_VERSION:
        errors.append("unsupported_schema_version")

    primary = output.get("primary_intent_type")
    if not _is_non_empty_str(primary):
        errors.append("bad_primary_intent_type")

    intents = output.get("intents")
    if not isinstance(intents, list) or len(intents) == 0:
        errors.append("bad_intents")
    else:
        for it in intents:
            if not isinstance(it, dict):
                errors.append("bad_intent_item")
                continue
            if not _is_non_empty_str(it.get("intent_type")):
                errors.append("bad_intent_item_type")
            conf = it.get("confidence")
            if conf is None:
                errors.append("missing_intent_item_confidence")
            else:
                try:
                    f = float(conf)
                    if f < 0.0 or f > 1.0:
                        errors.append("bad_intent_item_confidence")
                except Exception:
                    errors.append("bad_intent_item_confidence")
            slots = it.get("slots")
            if slots is not None and not isinstance(slots, dict):
                errors.append("bad_intent_item_slots")

    risk_level = output.get("risk_level")
    if not _is_non_empty_str(risk_level) or risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        errors.append("bad_risk_level")

    pr = output.get("permission_requirements")
    if pr is not None and not isinstance(pr, dict):
        errors.append("bad_permission_requirements")
    if isinstance(pr, dict):
        if not isinstance(pr.get("side_effects"), bool):
            errors.append("bad_side_effects")
        if not isinstance(pr.get("requires_human_approval"), bool):
            errors.append("bad_requires_human_approval")
        allowed_tools = pr.get("allowed_tools")
        if allowed_tools is not None and not isinstance(allowed_tools, list):
            errors.append("bad_allowed_tools")

    dis = output.get("disambiguation")
    if dis is not None and not isinstance(dis, dict):
        errors.append("bad_disambiguation")
    if isinstance(dis, dict):
        if not isinstance(dis.get("has_multiple"), bool):
            errors.append("bad_disambiguation_has_multiple")
        if dis.get("has_multiple") is True and not _is_non_empty_str(dis.get("explanation")):
            errors.append("bad_disambiguation_explanation")

    evidence = output.get("evidence")
    if evidence is not None and not isinstance(evidence, dict):
        errors.append("bad_evidence")
    if isinstance(evidence, dict):
        has_receipts = isinstance(evidence.get("receipt_command_ids"), list) and any(_is_non_empty_str(x) for x in evidence.get("receipt_command_ids"))
        has_fields = isinstance(evidence.get("fields"), list) and any(_is_non_empty_str(x) for x in evidence.get("fields"))
        has_rag = isinstance(evidence.get("rag_hit_ids"), list) and any(_is_non_empty_str(x) for x in evidence.get("rag_hit_ids"))
        if not (has_receipts or has_fields or has_rag):
            errors.append("missing_key_intent_evidence_refs")

    degraded = output.get("degraded")
    if degraded is not None and not isinstance(degraded, bool):
        errors.append("bad_degraded")
    if isinstance(degraded, bool) and degraded:
        if not _is_non_empty_str(output.get("degraded_reason")):
            errors.append("bad_degraded_reason")
        degraded_scope = output.get("degraded_scope")
        if not isinstance(degraded_scope, list) or not degraded_scope or not all(_is_non_empty_str(x) for x in degraded_scope):
            errors.append("bad_degraded_scope")

    return len(errors) == 0, errors


def normalize_intent_output(output: dict[str, Any]) -> dict[str, Any]:
    out = dict(output) if isinstance(output, dict) else {}
    out.setdefault("schema_version", INTENT_OUTPUT_SCHEMA_VERSION)
    out.setdefault("primary_intent_type", "unknown")
    out.setdefault("intents", [{"intent_type": out.get("primary_intent_type") or "unknown", "slots": {}, "confidence": 0.0}])
    out.setdefault("disambiguation", {"has_multiple": False, "explanation": "", "notes": []})
    out.setdefault("risk_level", "HIGH")
    out.setdefault(
        "permission_requirements",
        {"side_effects": False, "requires_human_approval": False, "allowed_tools": None},
    )
    out.setdefault("evidence", {"fields": ["unknown"]})
    out.setdefault("degraded", False)

    if not isinstance(out.get("intents"), list) or not out.get("intents"):
        out["intents"] = [{"intent_type": out.get("primary_intent_type") or "unknown", "slots": {}, "confidence": 0.0}]
    fixed_intents: list[dict[str, Any]] = []
    for it in out.get("intents") if isinstance(out.get("intents"), list) else []:
        if not isinstance(it, dict):
            continue
        row = dict(it)
        if not _is_non_empty_str(row.get("intent_type")):
            row["intent_type"] = "unknown"
        if not isinstance(row.get("slots"), dict):
            row["slots"] = {}
        try:
            row["confidence"] = float(row.get("confidence") or 0.0)
        except Exception:
            row["confidence"] = 0.0
        row["confidence"] = max(0.0, min(1.0, float(row["confidence"])))
        fixed_intents.append(row)
    if not fixed_intents:
        fixed_intents = [{"intent_type": out.get("primary_intent_type") or "unknown", "slots": {}, "confidence": 0.0}]
    fixed_intents.sort(key=lambda x: (-float(x.get("confidence") or 0.0), str(x.get("intent_type") or "")))
    out["intents"] = fixed_intents

    if not isinstance(out.get("permission_requirements"), dict):
        out["permission_requirements"] = {"side_effects": False, "requires_human_approval": False, "allowed_tools": None}
    if not isinstance(out.get("disambiguation"), dict):
        out["disambiguation"] = {"has_multiple": False, "explanation": "", "notes": []}
    if not isinstance(out.get("evidence"), dict):
        out["evidence"] = {"fields": ["unknown"]}
    if isinstance(out["evidence"], dict) and "fields" not in out["evidence"]:
        out["evidence"]["fields"] = ["unknown"]
    if not _is_non_empty_str(out.get("primary_intent_type")):
        out["primary_intent_type"] = str(out["intents"][0].get("intent_type") or "unknown")
    if _is_non_empty_str(out.get("primary_intent_type")):
        out["primary_intent_type"] = str(out.get("primary_intent_type")).strip()

    pr = out.get("permission_requirements")
    if isinstance(pr, dict):
        if not isinstance(pr.get("side_effects"), bool):
            pr["side_effects"] = False
        if not isinstance(pr.get("requires_human_approval"), bool):
            pr["requires_human_approval"] = False
        if "allowed_tools" in pr and pr["allowed_tools"] is not None and not isinstance(pr["allowed_tools"], list):
            pr["allowed_tools"] = None

    dis = out.get("disambiguation")
    if isinstance(dis, dict):
        has_multiple = len(out["intents"]) > 1
        dis["has_multiple"] = bool(has_multiple)
        notes = dis.get("notes")
        if not isinstance(notes, list):
            dis["notes"] = []
        if has_multiple and not _is_non_empty_str(dis.get("explanation")):
            types = [str(x.get("intent_type") or "unknown") for x in out["intents"]]
            dis["explanation"] = f"检测到多意图 {', '.join(types)} 已按置信度排序并选择主意图"
        if not has_multiple and not isinstance(dis.get("explanation"), str):
            dis["explanation"] = ""

    if not isinstance(out.get("degraded"), bool):
        out["degraded"] = False
    if out.get("degraded") is True:
        if not _is_non_empty_str(out.get("degraded_reason")):
            out["degraded_reason"] = "unknown"
        degraded_scope = out.get("degraded_scope")
        if not isinstance(degraded_scope, list) or not degraded_scope:
            out["degraded_scope"] = ["intent"]
    return out
