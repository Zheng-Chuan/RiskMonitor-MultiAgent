#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from riskmonitor_multiagent.knowledge.chroma_store import ChromaVectorStore
from riskmonitor_multiagent.knowledge.ingest import ingest_recent_alerts


def _cmd_ingest_alerts(args: argparse.Namespace) -> int:
    result = ingest_recent_alerts(limit=args.limit, severity=args.severity, desk=args.desk)
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    store = ChromaVectorStore()
    res = store.query_alerts(query_text=args.query, top_k=args.top_k)
    out = {
        "query": args.query,
        "top_k": args.top_k,
        "vector_db": "chroma",
        "results": [
            {
                "alert_id": r.metadata.get("alert_id") or r.doc_id,
                "similarity": float(round(r.similarity, 6)),
                "metadata": r.metadata,
                "snippet": r.document[:200],
            }
            for r in res
        ],
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="kb")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ingest = sub.add_parser("ingest-alerts")
    ingest.add_argument("--limit", type=int, default=500)
    ingest.add_argument("--severity", type=str, default=None)
    ingest.add_argument("--desk", type=str, default=None)
    ingest.set_defaults(func=_cmd_ingest_alerts)

    query = sub.add_parser("query")
    query.add_argument("--query", type=str, required=True)
    query.add_argument("--top-k", type=int, default=5)
    query.set_defaults(func=_cmd_query)

    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

