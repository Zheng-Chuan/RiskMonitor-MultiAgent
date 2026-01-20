#!/usr/bin/env python3

import argparse
import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any


def utc_now_iso() -> str:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return now.isoformat().replace("+00:00", "Z")


def default_snapshot() -> dict[str, Any]:
    # 行情快照 demo 数据.
    # 目标: 让 Week 1 垂直切片可复现, 且覆盖多 desk、多资产的 security_id.
    return {
        "as_of": utc_now_iso(),
        "prices": {
            # 股票衍生品
            "AAPL-CALL-175-20250331": 12.34,
            "GOOGL-PUT-140-20250630": 8.90,
            "MSFT-CALL-420-20250331": 10.12,
            "TSLA-PUT-250-20250228": 15.67,
            "NVDA-CALL-900-20250630": 22.22,
            "META-CALL-520-20250331": 9.11,
            "AMZN-PUT-160-20250430": 7.77,
            # 外汇衍生品
            "EURUSD-FWD-20250331": 1.09,
            "GBPUSD-CALL-1.30-20250228": 0.05,
            "USDJPY-PUT-150-20250331": 0.04,
            # 固定收益 / 大宗商品 / 信用衍生品
            "US10Y-IRS-20250331": 0.02,
            "EUR5Y-IRS-20250630": 0.015,
            "WTI-FUT-20250228": 78.5,
            "GOLD-FUT-20250331": 2050.0,
            "JPM-CDS-20250630": 0.012,
        },
        "fx_rates": {
            # 外汇口径: 1 单位本币对应的 USD 价值
            "USD": 1.0,
            "EUR": 1.1,
            "GBP": 1.25,
            "JPY": 0.0068,
            "CHF": 1.12,
        },
    }


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802  pylint: disable=invalid-name
        if self.path in {"/snapshot", "/snapshot/"}:
            self._write_json(200, default_snapshot())
            return
        if self.path in {"/health", "/health/"}:
            self._write_json(200, {"status": "ok"})
            return

        self._write_json(404, {"error": {"code": "NOT_FOUND", "message": "not found"}})

    def log_message(self, format: str, *args: Any) -> None:  
        # 演示场景下减少 stdout 噪音.
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Market snapshot demo server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9010)
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"market snapshot server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
