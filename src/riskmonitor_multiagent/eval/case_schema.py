from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    task: dict[str, Any]
    tags: list[str]


def load_benchmark_cases(path: str) -> list[BenchmarkCase]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    raw = p.read_text(encoding="utf-8")
    cases: list[BenchmarkCase] = []
    for line_no, line in enumerate(raw.splitlines(), start=1):
        s = line.strip()
        if not s:
            continue
        obj = json.loads(s)
        if not isinstance(obj, dict):
            raise ValueError(f"bad_case_line:{line_no}")
        case_id = obj.get("case_id")
        task = obj.get("task")
        tags = obj.get("tags")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"bad_case_id:{line_no}")
        if not isinstance(task, dict):
            raise ValueError(f"bad_task:{line_no}")
        if tags is None:
            tags = []
        if not isinstance(tags, list) or not all(isinstance(x, str) for x in tags):
            raise ValueError(f"bad_tags:{line_no}")
        cases.append(BenchmarkCase(case_id=case_id.strip(), task=task, tags=[str(x) for x in tags]))
    if not cases:
        raise ValueError("empty_benchmark_cases")
    return cases

