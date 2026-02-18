from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.orchestration.context_store import FileContextStore
from riskmonitor_multiagent.orchestration.state_machine import run_state_machine


async def _main_async(event_id: str) -> int:
    store = FileContextStore()
    snap = store.get_event_snapshot_by_event_id(event_id=event_id)
    if not isinstance(snap, dict):
        print(json.dumps({"ok": False, "error": "event_snapshot_not_found", "event_id": event_id}, ensure_ascii=False))
        return 1
    out = await run_state_machine(event=snap)
    print(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if out.get("ok") is True else 2


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--event-id", required=True)
    args = p.parse_args()
    return asyncio.run(_main_async(str(args.event_id)))


if __name__ == "__main__":
    raise SystemExit(main())

