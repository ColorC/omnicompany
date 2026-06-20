"""replay_agent_trace — 从 events.db 按 trace_id 复现 Agent Loop 全过程。

对应 plan.md §10.5.1 [E3] 退出条件：
"写 scripts/replay_agent_trace.py 能按 trace_id 顺序打印每步 input/output，
 无需访问任何内存状态"

用法：
  python scripts/replay_agent_trace.py <trace_id>
  python scripts/replay_agent_trace.py <trace_id> --db data/domains/gameplay_system/events.db
  python scripts/replay_agent_trace.py <trace_id> --verbose   # 展示完整 payload
  python scripts/replay_agent_trace.py --list-recent          # 列最近 20 个 trace
  python scripts/replay_agent_trace.py --list-recent --db data/domains/gameplay_system/events.db

默认 DB 路径：data/events.db → 如缺失按 domain 猜（data/domains/gameplay_system/events.db）
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
from pathlib import Path

# Windows UTF-8 stdout
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent

_DEFAULT_DB_CANDIDATES = [
    ROOT / "data" / "events.db",
    ROOT / "data" / "domains" / "gameplay_system" / "events.db",
]


def _find_db(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = ROOT / p
        if not p.exists():
            sys.exit(f"[ERROR] db not found: {p}")
        return p
    for cand in _DEFAULT_DB_CANDIDATES:
        if cand.exists():
            return cand
    sys.exit(
        "[ERROR] no events.db found. Candidates tried:\n  "
        + "\n  ".join(str(c) for c in _DEFAULT_DB_CANDIDATES)
    )


def _open(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def list_recent(conn: sqlite3.Connection, limit: int = 20) -> None:
    """列最近 N 个唯一 trace_id，带事件计数 + 起止时间。"""
    rows = conn.execute(
        """
        SELECT trace_id,
               COUNT(*) AS n_events,
               MIN(timestamp) AS started_at,
               MAX(timestamp) AS ended_at
        FROM events
        GROUP BY trace_id
        ORDER BY ended_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    if not rows:
        print("[no traces]")
        return
    print(f"{'trace_id':<40} {'n_events':>8}  {'started':<20} → {'ended':<20}")
    print("-" * 110)
    for r in rows:
        print(
            f"{r['trace_id']:<40} {r['n_events']:>8}  "
            f"{r['started_at'][:19]:<20} → {r['ended_at'][:19]:<20}"
        )


def replay(conn: sqlite3.Connection, trace_id: str, *, verbose: bool = False) -> int:
    """按 trace_id 顺序打印每条事件。返回事件数。"""
    rows = conn.execute(
        """
        SELECT id, parent_id, event_type, source, timestamp, data
        FROM events
        WHERE trace_id = ?
        ORDER BY timestamp, id
        """,
        (trace_id,),
    ).fetchall()
    if not rows:
        print(f"[no events for trace_id={trace_id}]")
        return 0

    # Summary
    by_type: dict[str, int] = {}
    for r in rows:
        by_type[r["event_type"]] = by_type.get(r["event_type"], 0) + 1

    print(f"=== trace_id={trace_id} ===")
    print(f"total events: {len(rows)}")
    print(f"event types ({len(by_type)}):")
    for t, n in sorted(by_type.items()):
        print(f"  [{n:>4}]  {t}")
    print("-" * 80)

    # Chronological walk
    for i, r in enumerate(rows, 1):
        ts_short = r["timestamp"][11:23]  # HH:MM:SS.mmm
        print(f"\n[{i:>4}] {ts_short}  {r['event_type']}  (source={r['source']})")
        try:
            payload = json.loads(r["data"])
        except json.JSONDecodeError:
            print(f"    data: <unparsable> {r['data'][:200]}")
            continue

        # 每类事件的精简摘要
        summary = _summarize(r["event_type"], payload)
        if summary:
            print(f"    {summary}")
        if verbose:
            print("    ── full payload ──")
            for line in json.dumps(payload, ensure_ascii=False, indent=2, default=str).splitlines():
                print(f"    {line}")

    print("\n" + "=" * 80)
    print(f"replay complete. {len(rows)} events.")
    return len(rows)


def _summarize(event_type: str, payload: dict) -> str:
    """事件类型特定摘要（不展开完整 payload）。"""
    if not isinstance(payload, dict):
        return ""

    inner = payload.get("payload") or payload  # FactoryEvent payload nesting
    data = inner.get("data") if isinstance(inner, dict) else None

    # Router input/output
    if event_type.startswith("router.") and event_type.endswith(".input"):
        if isinstance(data, dict):
            return f"format={inner.get('format_id','?')}  keys={sorted(data.keys())[:6]}"
        return f"format={inner.get('format_id','?')}"
    if event_type.startswith("router.") and event_type.endswith(".output"):
        v = inner.get("verdict_kind", "?")
        if isinstance(data, dict):
            return f"verdict={v}  format={inner.get('format_id','?')}  keys={sorted(data.keys())[:6]}"
        return f"verdict={v}  format={inner.get('format_id','?')}"

    # Agent signals
    if event_type == "agent.turn.start":
        return f"turn={inner.get('turn')}"
    if event_type == "agent.turn.end":
        return f"turn={inner.get('turn')}  tool_calls={inner.get('tool_calls')}"
    if event_type == "agent.loop.start":
        return f"max_turns={inner.get('max_turns')}"
    if event_type == "agent.loop.finish":
        return f"reason={inner.get('reason')}  turn_count={inner.get('turn_count')}"
    if event_type == "agent.budget_exhaust":
        return f"max_turns={inner.get('max_turns')}"

    return ""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("trace_id", nargs="?", help="trace_id to replay")
    ap.add_argument("--db", help="events.db path (default: data/events.db)")
    ap.add_argument("--verbose", action="store_true", help="show full event payloads")
    ap.add_argument("--list-recent", action="store_true", help="list recent trace_ids and exit")
    ap.add_argument("--limit", type=int, default=20, help="list-recent limit (default 20)")
    args = ap.parse_args()

    db_path = _find_db(args.db)
    print(f"[db] {db_path}\n")

    with _open(db_path) as conn:
        if args.list_recent:
            list_recent(conn, limit=args.limit)
            return
        if not args.trace_id:
            ap.error("trace_id required (or use --list-recent)")
        replay(conn, args.trace_id, verbose=args.verbose)


if __name__ == "__main__":
    main()
