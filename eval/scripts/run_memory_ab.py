from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_ROOT = REPO_ROOT / "eval" / "results" / "memory_ab"
TRACKED_METRICS = [
    "task_success_rate",
    "evidence_coverage",
    "memory_hit_rate",
    "memory_usefulness",
    "resume_success_rate",
    "few_shot_reuse_rate",
    "role_drift_rate",
    "memory_cross_talk_rate",
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _behavior_metrics(payload: dict[str, Any]) -> dict[str, float]:
    metrics = payload.get("behavior_metrics") if isinstance(payload.get("behavior_metrics"), dict) else {}
    return {name: float(metrics.get(name, 0.0)) for name in TRACKED_METRICS}


def _build_delta(primary: dict[str, float], baseline: dict[str, float]) -> dict[str, float]:
    return {
        key: round(primary.get(key, 0.0) - baseline.get(key, 0.0), 4)
        for key in TRACKED_METRICS
    }


def _write_markdown(summary_path: Path, summary: dict[str, Any]) -> None:
    primary = summary["runs"]["memory_on"]["metrics"]
    lines = [
        "# 7.3 Unified Memory A B Report",
        "",
        f"- generated_at: {summary['generated_at']}",
        f"- category: {summary['category']}",
        f"- limit: {summary['limit']}",
        "",
        "## Runs",
    ]
    for mode, payload in summary["runs"].items():
        lines.append(f"- {mode}: {payload['result_path']}")
    lines.extend(["", "## Deltas"])
    for mode, payload in summary["runs"].items():
        if mode == "memory_on":
            continue
        lines.append(f"- memory_on vs {mode}")
        for metric, delta in payload["delta_vs_memory_on"].items():
            sign = "+" if delta >= 0 else ""
            lines.append(f"  - {metric}: {primary.get(metric, 0.0):.4f} vs {payload['metrics'].get(metric, 0.0):.4f} ({sign}{delta:.4f})")
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run_one(*, mode: str, output_path: Path, category: str, limit: int) -> None:
    command = [
        sys.executable,
        "-m",
        "eval.cli",
        "run",
        "--category",
        category,
        "--baseline-mode",
        mode,
        "--output",
        str(output_path),
        "--no-llm-judge",
    ]
    if limit > 0:
        command.extend(["--limit", str(limit)])
    env = dict(os.environ)
    src_path = str(REPO_ROOT / "src")
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}:{existing_pythonpath}"
    subprocess.run(command, cwd=REPO_ROOT, env=env, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 7.3 memory A B evaluation")
    parser.add_argument("--category", default="memory", help="Benchmark category")
    parser.add_argument("--limit", type=int, default=0, help="Limit case count")
    parser.add_argument("--output-dir", default=str(RESULTS_ROOT), help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    run_paths = {
        "memory_on": output_dir / f"{stamp}_memory_on.json",
        "memory_off": output_dir / f"{stamp}_memory_off.json",
        "private_disabled": output_dir / f"{stamp}_private_disabled.json",
    }
    baseline_modes = {
        "memory_on": "primary",
        "memory_off": "memory_off",
        "private_disabled": "private_disabled",
    }

    for label, mode in baseline_modes.items():
        _run_one(
            mode=mode,
            output_path=run_paths[label],
            category=args.category,
            limit=args.limit,
        )

    primary_metrics = _behavior_metrics(_load_json(run_paths["memory_on"]))
    summary: dict[str, Any] = {
        "generated_at": stamp,
        "category": args.category,
        "limit": args.limit,
        "runs": {},
    }
    for label, path in run_paths.items():
        metrics = _behavior_metrics(_load_json(path))
        summary["runs"][label] = {
            "baseline_mode": baseline_modes[label],
            "result_path": str(path.relative_to(REPO_ROOT)),
            "metrics": metrics,
            "delta_vs_memory_on": _build_delta(primary_metrics, metrics) if label != "memory_on" else {},
        }

    summary_path = output_dir / f"{stamp}_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = output_dir / f"{stamp}_summary.md"
    _write_markdown(markdown_path, summary)
    print(f"summary_json={summary_path}")
    print(f"summary_md={markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
