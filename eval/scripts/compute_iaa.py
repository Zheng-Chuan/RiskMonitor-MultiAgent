from __future__ import annotations

import json
from pathlib import Path


def load_jsonl(path: str | Path) -> list[dict]:
    rows: list[dict] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compute_simple_agreement(a_path: str | Path, b_path: str | Path) -> dict[str, float]:
    rows_a = {row["case_id"]: row for row in load_jsonl(a_path)}
    rows_b = {row["case_id"]: row for row in load_jsonl(b_path)}
    shared_ids = sorted(set(rows_a) & set(rows_b))
    if not shared_ids:
        return {"sample_count": 0.0, "agreement": 0.0}
    matched = sum(1 for case_id in shared_ids if rows_a[case_id] == rows_b[case_id])
    return {"sample_count": float(len(shared_ids)), "agreement": matched / len(shared_ids)}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Compute simple annotation agreement")
    parser.add_argument("annotator_a")
    parser.add_argument("annotator_b")
    args = parser.parse_args()
    print(json.dumps(compute_simple_agreement(args.annotator_a, args.annotator_b), ensure_ascii=False, indent=2))
