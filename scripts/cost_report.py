# [OMNI] origin=claude-code domain=scripts ts=2026-04-28T00:00:00Z type=tool
"""LLM 成本 + 时间诊断工具 (从 events.db 抽取).

用法:
  # 全部事件
  python cost_report.py

  # 时间窗
  python cost_report.py --since 2026-04-26 --until 2026-04-28

  # 指定 db
  python cost_report.py --db data/events.db

  # CSV 导出 trace 详情
  python cost_report.py --since 2026-04-26 --csv out.csv

输出:
  1. 总览 (trace 数 / LLM call 数 / token 总量 / 估算成本 / wall_clock 累计)
  2. 按 worker 类型聚合 (input/output token, LLM 次数, 平均 wall)
  3. 最贵 N 个 trace
  4. tool 调用频率

设计 (2026-04-28 P5 立):
  P5 实测每次 pipeline 试跑后 不知钱花在哪. 立这工具用 events.db 现成的
  router.llm_call.output 事件抽 token + timestamp 计算. 不需要新加埋点.

  qwen3.6-plus 估价 (近似, 实际看账单):
    input  ¥0.0008 / 1k token
    output ¥0.0024 / 1k token
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path("/workspace/omnicompany/data/events.db")
RMB_PER_KTOK_IN = 0.0008
RMB_PER_KTOK_OUT = 0.0024
WORKER_RE = re.compile(r"agent\.(\w+Worker)")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def collect(db_path: Path, since: str | None, until: str | None) -> dict:
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    where = []
    args = []
    if since:
        where.append("timestamp >= ?")
        args.append(since)
    if until:
        where.append("timestamp < ?")
        args.append(until)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    cur.execute(
        f"SELECT trace_id, source, timestamp, event_type, data FROM events{where_sql} ORDER BY timestamp;",
        args,
    )

    trace_first: dict[str, str] = {}
    trace_last: dict[str, str] = {}
    trace_workers: dict[str, set] = defaultdict(set)
    trace_in_tok: dict[str, int] = defaultdict(int)
    trace_out_tok: dict[str, int] = defaultdict(int)
    trace_llm_calls: dict[str, int] = defaultdict(int)
    trace_tool_calls: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    total_in = 0
    total_out = 0
    total_llm = 0

    for trace_id, source, ts, etype, data in cur.fetchall():
        if trace_id not in trace_first:
            trace_first[trace_id] = ts
        trace_last[trace_id] = ts

        m = WORKER_RE.match(source or "")
        if m:
            trace_workers[trace_id].add(m.group(1))

        if etype.startswith("router.tool_") and etype.endswith(".input"):
            tool_name = etype.replace("router.tool_", "").replace(".input", "")
            trace_tool_calls[trace_id][tool_name] += 1

        if etype == "router.llm_call.output":
            try:
                d = json.loads(data)
                payload = d.get("payload", {})
                pdata = payload.get("data", {}) if isinstance(payload, dict) else {}
                usage = pdata.get("usage", {}) if isinstance(pdata, dict) else {}
                if isinstance(usage, dict):
                    it = int(usage.get("input_tokens", 0) or 0)
                    ot = int(usage.get("output_tokens", 0) or 0)
                    total_in += it
                    total_out += ot
                    total_llm += 1
                    trace_in_tok[trace_id] += it
                    trace_out_tok[trace_id] += ot
                    trace_llm_calls[trace_id] += 1
            except Exception:
                pass

    con.close()

    # 计算 wall per trace
    trace_wall = {}
    for tid in trace_first:
        if tid in trace_first and tid in trace_last:
            try:
                t0 = parse_ts(trace_first[tid])
                t1 = parse_ts(trace_last[tid])
                trace_wall[tid] = (t1 - t0).total_seconds()
            except Exception:
                trace_wall[tid] = 0
        else:
            trace_wall[tid] = 0

    return {
        "trace_first": trace_first,
        "trace_last": trace_last,
        "trace_workers": trace_workers,
        "trace_in_tok": trace_in_tok,
        "trace_out_tok": trace_out_tok,
        "trace_llm_calls": trace_llm_calls,
        "trace_tool_calls": trace_tool_calls,
        "trace_wall": trace_wall,
        "total_in": total_in,
        "total_out": total_out,
        "total_llm": total_llm,
    }


def estimate_rmb(in_tok: int, out_tok: int) -> float:
    return (in_tok / 1000) * RMB_PER_KTOK_IN + (out_tok / 1000) * RMB_PER_KTOK_OUT


def kind_of(workers: set) -> str:
    if not workers:
        return "(no_worker)"
    return next(iter(workers))


def print_overview(d: dict) -> None:
    print("=" * 76)
    print("总览")
    print("=" * 76)
    print(f"  trace 数:           {len(d['trace_first']):>10,d}")
    print(f"  LLM call 次:        {d['total_llm']:>10,d}")
    print(f"  Input tokens:       {d['total_in']:>14,d}")
    print(f"  Output tokens:      {d['total_out']:>14,d}")
    print(f"  Total tokens:       {d['total_in'] + d['total_out']:>14,d}")
    rmb = estimate_rmb(d["total_in"], d["total_out"])
    print(f"  估算成本:           约 RMB {rmb:>10.2f}")
    wall = sum(d["trace_wall"].values())
    print(f"  Wall-clock 累计:    {wall:>10,.0f} 秒 = {wall/3600:.2f} 小时 (含并行)")


def print_by_worker(d: dict) -> None:
    by_kind: dict[str, dict] = defaultdict(lambda: {
        "count": 0, "llm_calls": 0, "in_tok": 0, "out_tok": 0, "wall_sum": 0,
    })
    for tid in d["trace_first"]:
        kind = kind_of(d["trace_workers"].get(tid, set()))
        bk = by_kind[kind]
        bk["count"] += 1
        bk["llm_calls"] += d["trace_llm_calls"].get(tid, 0)
        bk["in_tok"] += d["trace_in_tok"].get(tid, 0)
        bk["out_tok"] += d["trace_out_tok"].get(tid, 0)
        bk["wall_sum"] += d["trace_wall"].get(tid, 0)

    print()
    print("=" * 76)
    print("按 worker 类型聚合")
    print("=" * 76)
    print(f"{'worker':45s} {'数':>5s} {'LLM/次':>8s} {'in tok 平均':>12s} {'wall 平均':>10s} {'RMB':>8s}")
    for kind, bk in sorted(by_kind.items(), key=lambda kv: -(kv[1]["in_tok"] + kv[1]["out_tok"])):
        avg_llm = bk["llm_calls"] / bk["count"] if bk["count"] else 0
        avg_in = bk["in_tok"] / bk["count"] if bk["count"] else 0
        avg_wall = bk["wall_sum"] / bk["count"] if bk["count"] else 0
        rmb = estimate_rmb(bk["in_tok"], bk["out_tok"])
        print(f"{kind[:45]:45s} {bk['count']:>5d} {avg_llm:>8.1f} {avg_in:>12,.0f} {avg_wall:>10.0f} {rmb:>8.2f}")


def print_top_traces(d: dict, n: int = 15) -> None:
    print()
    print("=" * 76)
    print(f"最贵的 {n} 个 trace")
    print("=" * 76)
    sorted_traces = sorted(
        d["trace_first"].keys(),
        key=lambda tid: -(d["trace_in_tok"].get(tid, 0) + d["trace_out_tok"].get(tid, 0)),
    )
    print(f"{'trace_id (前 12)':17s} {'wall(s)':>8s} {'LLM 次':>7s} {'in tok':>10s} {'out tok':>9s} {'RMB':>7s}  workers")
    for tid in sorted_traces[:n]:
        in_t = d["trace_in_tok"].get(tid, 0)
        out_t = d["trace_out_tok"].get(tid, 0)
        rmb = estimate_rmb(in_t, out_t)
        ws = ", ".join(sorted(d["trace_workers"].get(tid, set())))[:40] or "(none)"
        wall = d["trace_wall"].get(tid, 0)
        print(f"{tid[:12]:17s} {wall:>8.0f} {d['trace_llm_calls'].get(tid, 0):>7d} {in_t:>10,d} {out_t:>9,d} {rmb:>7.2f}  {ws}")


def print_tools(d: dict) -> None:
    tool_total: dict[str, int] = defaultdict(int)
    for tid in d["trace_first"]:
        for k, v in d["trace_tool_calls"].get(tid, {}).items():
            tool_total[k] += v
    if not tool_total:
        return
    print()
    print("=" * 76)
    print("Tool 调用频率")
    print("=" * 76)
    for tool, n in sorted(tool_total.items(), key=lambda kv: -kv[1]):
        print(f"  {tool:30s} {n:>6d}")


def write_csv(d: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["trace_id", "workers", "wall_sec", "llm_calls", "in_tok", "out_tok", "est_rmb"])
        sorted_traces = sorted(
            d["trace_first"].keys(),
            key=lambda tid: -(d["trace_in_tok"].get(tid, 0) + d["trace_out_tok"].get(tid, 0)),
        )
        for tid in sorted_traces:
            in_t = d["trace_in_tok"].get(tid, 0)
            out_t = d["trace_out_tok"].get(tid, 0)
            ws = ", ".join(sorted(d["trace_workers"].get(tid, set())))
            w.writerow([
                tid,
                ws,
                round(d["trace_wall"].get(tid, 0), 1),
                d["trace_llm_calls"].get(tid, 0),
                in_t,
                out_t,
                round(estimate_rmb(in_t, out_t), 4),
            ])
    print(f"\nCSV 导出: {path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="LLM 成本 + 时间诊断 (events.db)")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="events.db 路径")
    ap.add_argument("--since", default=None, help="ISO 时间 起 (例 2026-04-26)")
    ap.add_argument("--until", default=None, help="ISO 时间 止 (例 2026-04-28)")
    ap.add_argument("--top", type=int, default=15, help="最贵 trace 显示数")
    ap.add_argument("--csv", default=None, help="trace 详情导出 CSV 路径 (可选)")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"!! events.db 不存在: {db_path}", file=sys.stderr)
        return 1

    print(f"DB: {db_path}")
    if args.since or args.until:
        print(f"时间窗: {args.since or '(全)'} ~ {args.until or '(全)'}")
    print()

    d = collect(db_path, args.since, args.until)
    if not d["trace_first"]:
        print("(无 events 命中时间窗)")
        return 0

    print_overview(d)
    print_by_worker(d)
    print_top_traces(d, n=args.top)
    print_tools(d)

    if args.csv:
        write_csv(d, Path(args.csv))

    return 0


if __name__ == "__main__":
    sys.exit(main())
