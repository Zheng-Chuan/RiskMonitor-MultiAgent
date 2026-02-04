#!/usr/bin/env python3

from __future__ import annotations

import argparse
import random
import time
from datetime import date

import pymysql

from riskmonitor_multiagent.data_access.mysql_engine import get_engine


def _pick_desks() -> list[str]:
    return [
        "Equity Derivatives",
        "FX Derivatives",
        "Fixed Income",
        "Commodities",
        "Credit Trading",
    ]


def _fetch_position_ids_by_desk(conn, *, desk: str, limit: int) -> list[str]:
    cur = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT position_id
            FROM positions
            WHERE desk = %s
            ORDER BY entry_date DESC
            LIMIT %s
            """,
            (desk, int(limit)),
        )
        rows = list(cur.fetchall())
        return [r["position_id"] for r in rows if isinstance(r, dict) and isinstance(r.get("position_id"), str)]
    finally:
        cur.close()


def _update_position_delta(conn, *, position_id: str, delta: float) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE positions
            SET delta = %s, updated_at = CURRENT_TIMESTAMP
            WHERE position_id = %s
            """,
            (float(delta), position_id),
        )
    finally:
        cur.close()


def _insert_position(conn, *, position_id: str, desk: str, delta: float) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO positions(position_id, trader_id, desk, security_id, quantity, delta, entry_date, currency)
            VALUES(%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                position_id,
                f"STRESS-{random.randint(1, 9):03d}",
                desk,
                f"STRESS-SEC-{random.randint(1, 9999):04d}",
                float(random.randint(1, 1000)),
                float(delta),
                date.today().isoformat(),
                "USD",
            ),
        )
    finally:
        cur.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject many positions updates to create a storm scenario.")
    parser.add_argument("--n", type=int, default=200, help="number of updates")
    parser.add_argument("--desks", type=str, default=",".join(_pick_desks()), help="comma separated desks")
    parser.add_argument("--breach-delta", type=float, default=120000.0, help="delta value used to trigger breach")
    parser.add_argument("--sleep-ms", type=int, default=0, help="sleep between updates in ms")
    parser.add_argument("--new-ratio", type=float, default=0.05, help="ratio of inserts among all updates")
    args = parser.parse_args()

    desks = [d.strip() for d in (args.desks or "").split(",") if d.strip()]
    if not desks:
        raise SystemExit("no desks")

    engine = get_engine()
    conn = engine.raw_connection()
    try:
        all_positions: dict[str, list[str]] = {}
        for d in desks:
            ids = _fetch_position_ids_by_desk(conn, desk=d, limit=50)
            all_positions[d] = ids

        started = time.monotonic()
        for i in range(int(args.n)):
            desk = random.choice(desks)
            do_insert = random.random() < float(args.new_ratio)
            if do_insert:
                pid = f"STRESS-{int(time.time()*1000)}-{i:06d}"
                _insert_position(conn, position_id=pid, desk=desk, delta=float(args.breach_delta))
            else:
                candidates = all_positions.get(desk) or []
                if not candidates:
                    pid = f"STRESS-{int(time.time()*1000)}-{i:06d}"
                    _insert_position(conn, position_id=pid, desk=desk, delta=float(args.breach_delta))
                    all_positions.setdefault(desk, []).append(pid)
                else:
                    pid = random.choice(candidates)
                    bump = float(args.breach_delta) + float(random.randint(-5000, 5000))
                    _update_position_delta(conn, position_id=pid, delta=bump)

            if (i + 1) % 50 == 0:
                conn.commit()
            if args.sleep_ms > 0:
                time.sleep(float(args.sleep_ms) / 1000.0)

        conn.commit()
        elapsed = time.monotonic() - started
        rps = float(args.n) / elapsed if elapsed > 0 else 0.0
        print(f"Injected n={args.n} updates in {elapsed:.2f}s, rps={rps:.1f}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

