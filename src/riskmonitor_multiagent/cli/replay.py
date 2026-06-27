"""run replay CLI helper."""

from __future__ import annotations

import argparse
import sys

from riskmonitor_multiagent.observability.run_trace import get_run_trace_store


def replay_run(run_id: str, *, output_format: str = "text") -> str:
    """按 run_id 渲染统一时间线.

    优先从内存读取 不存在时回退到磁盘快照.
    """
    store = get_run_trace_store()
    if output_format == "json":
        return store.render_replay_json(run_id)
    return store.render_replay(run_id)


def build_parser() -> argparse.ArgumentParser:
    """构建 replay CLI 参数解析器."""
    parser = argparse.ArgumentParser(description="Render run trace replay by run_id")
    parser.add_argument("run_id", help="Target run id")
    parser.add_argument(
        "--format",
        dest="output_format",
        choices=("text", "json"),
        default="text",
        help="Replay output format",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口."""
    parser = build_parser()
    args = parser.parse_args(argv)
    print(replay_run(args.run_id, output_format=args.output_format))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))


__all__ = ["build_parser", "main", "replay_run"]
