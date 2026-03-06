#!/usr/bin/env python3

import argparse
import json
from pathlib import Path


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        obj = json.loads(s)
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _case_mean(records: list[dict]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict]] = {}
    for r in records:
        cid = str(r.get("case_id") or "")
        if not cid:
            continue
        grouped.setdefault(cid, []).append(r)

    out: dict[str, dict[str, float]] = {}
    for cid, rows in grouped.items():
        n = float(len(rows))
        q = [x.get("quality") if isinstance(x.get("quality"), dict) else {} for x in rows]
        out[cid] = {
            "latency_ms": float(sum(float(x.get("latency_ms") or 0.0) for x in rows) / n),
            "pass_rate": float(sum(1.0 if bool(x.get("ok")) else 0.0 for x in rows) / n),
            "evidence_missing_rate": float(sum(float(x.get("evidence_missing_rate") or 0.0) for x in q) / n),
            "receipt_binding_rate": float(sum(float(x.get("receipt_binding_rate") or 0.0) for x in q) / n),
            "step_reason_coverage": float(sum(float(x.get("step_reason_coverage") or 0.0) for x in q) / n),
            "contract_fail_rate": float(sum(float(x.get("contract_fail_rate") or 0.0) for x in q) / n),
            "explainability_score": float(sum(float(x.get("explainability_score") or 0.0) for x in q) / n),
        }
    return out


def _case_missing_steps(records: list[dict]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {}
    for r in records:
        cid = str(r.get("case_id") or "")
        if not cid:
            continue
        steps = r.get("evidence_missing_steps")
        if not isinstance(steps, list):
            continue
        s = grouped.setdefault(cid, set())
        for step_id in steps:
            if isinstance(step_id, str) and step_id.strip():
                s.add(step_id)
    return {k: sorted(list(v)) for k, v in grouped.items()}


def main() -> int:
    parser = argparse.ArgumentParser(prog="compare_runs")
    parser.add_argument("--base", type=str, required=True)
    parser.add_argument("--cand", type=str, required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[2]
    results_dir = root / "eval" / "results"
    base_summary_path = results_dir / f"{args.base}.summary.json"
    cand_summary_path = results_dir / f"{args.cand}.summary.json"
    base_records_path = results_dir / f"{args.base}.jsonl"
    cand_records_path = results_dir / f"{args.cand}.jsonl"
    if not base_summary_path.exists() or not cand_summary_path.exists() or not base_records_path.exists() or not cand_records_path.exists():
        raise FileNotFoundError("summary_or_records_not_found")

    base = _load_json(base_summary_path)
    cand = _load_json(cand_summary_path)
    base_records = _load_jsonl(base_records_path)
    cand_records = _load_jsonl(cand_records_path)
    base_agg = base.get("aggregates") if isinstance(base.get("aggregates"), dict) else {}
    cand_agg = cand.get("aggregates") if isinstance(cand.get("aggregates"), dict) else {}
    keys = sorted(set(base_agg.keys()) | set(cand_agg.keys()))

    delta: dict[str, float] = {}
    for k in keys:
        try:
            delta[k] = round(float(cand_agg.get(k, 0.0)) - float(base_agg.get(k, 0.0)), 6)
        except Exception:
            continue

    base_case = _case_mean(base_records)
    cand_case = _case_mean(cand_records)
    base_missing_steps = _case_missing_steps(base_records)
    cand_missing_steps = _case_missing_steps(cand_records)
    case_ids = sorted(set(base_case.keys()) | set(cand_case.keys()))
    case_delta: dict[str, dict[str, float]] = {}
    evidence_hotspots: list[dict[str, object]] = []
    for cid in case_ids:
        b = base_case.get(cid, {})
        c = cand_case.get(cid, {})
        d = {
            "pass_rate": round(float(c.get("pass_rate", 0.0) - b.get("pass_rate", 0.0)), 6),
            "latency_ms": round(float(c.get("latency_ms", 0.0) - b.get("latency_ms", 0.0)), 6),
            "evidence_missing_rate": round(float(c.get("evidence_missing_rate", 0.0) - b.get("evidence_missing_rate", 0.0)), 6),
            "receipt_binding_rate": round(float(c.get("receipt_binding_rate", 0.0) - b.get("receipt_binding_rate", 0.0)), 6),
            "step_reason_coverage": round(float(c.get("step_reason_coverage", 0.0) - b.get("step_reason_coverage", 0.0)), 6),
            "contract_fail_rate": round(float(c.get("contract_fail_rate", 0.0) - b.get("contract_fail_rate", 0.0)), 6),
            "explainability_score": round(float(c.get("explainability_score", 0.0) - b.get("explainability_score", 0.0)), 6),
        }
        case_delta[cid] = d
        cand_missing = float(c.get("evidence_missing_rate", 0.0))
        if cand_missing > 0.0:
            evidence_hotspots.append(
                {
                    "case_id": cid,
                    "candidate_evidence_missing_rate": round(cand_missing, 6),
                    "delta": d["evidence_missing_rate"],
                    "candidate_missing_steps": cand_missing_steps.get(cid, []),
                    "base_missing_steps": base_missing_steps.get(cid, []),
                }
            )
    evidence_hotspots.sort(key=lambda x: float(x.get("candidate_evidence_missing_rate") or 0.0), reverse=True)

    out = {
        "base": args.base,
        "candidate": args.cand,
        "base_pass_rate": base.get("pass_rate"),
        "candidate_pass_rate": cand.get("pass_rate"),
        "aggregates_delta": delta,
        "case_delta": case_delta,
        "evidence_missing_hotspots": evidence_hotspots[:20],
    }
    out_path = results_dir / f"{args.cand}.diff.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"ok": True, "diff_path": str(out_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
