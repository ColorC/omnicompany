"""CLI runner: Phase Ia Step 3 规则聚合 Agent Loop.

读 14 份 extraction_reports + 规则库 v0.2 + catalog，
产 phase_Ia_agent_proposals.md（v0.3 升级提议）。

用法：
  python scripts/run_proposal_aggregator.py
  python scripts/run_proposal_aggregator.py --reports-dir <custom> --out <custom.md>
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import logging
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s %(levelname)s %(name)s] %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
    force=True,
)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from omnicompany.packages.domains.gameplay_system.ux.routers.proposal_aggregator_loop import (
    ProposalAggregatorLoop,
)
from omnicompany.bus.sqlite import SQLiteBus


_PLAN_ROOT = Path(
    "/workspace/omnicompany/docs/plans/[2026-04-16]A-SERIES-COMPONENT-MAPPING"
)
_DEFAULT_REPORTS_DIR = _PLAN_ROOT / "stage1_observations" / "extraction_reports"
_DEFAULT_RULES = _PLAN_ROOT / "stage1_observations" / "_rules_structural.md"
_DEFAULT_CATALOG = _PLAN_ROOT / "stage1_observations" / "exemplar_catalog.md"
_DEFAULT_OUT = _PLAN_ROOT / "phase_Ia_agent_proposals.md"


_BUS_DB = ROOT / "data" / "domains" / "gameplay_system" / "events.db"
_BUS_SINGLETON: SQLiteBus | None = None


def _get_bus() -> SQLiteBus:
    global _BUS_SINGLETON
    if _BUS_SINGLETON is None:
        _BUS_DB.parent.mkdir(parents=True, exist_ok=True)
        _BUS_SINGLETON = SQLiteBus(db_path=_BUS_DB)
    return _BUS_SINGLETON


async def _run(input_data: dict, model: str) -> dict:
    bus = _get_bus()
    await bus.connect()
    loop = ProposalAggregatorLoop(model=model, bus=bus)
    t0 = time.time()
    try:
        verdict = await loop.run(input_data)
        elapsed = time.time() - t0
        out = verdict.output if isinstance(verdict.output, dict) else {}
        return {
            "verdict": str(verdict.kind) if hasattr(verdict, "kind") else "?",
            "proposals_path": out.get("proposals_path", ""),
            "turn_count": out.get("turn_count", 0),
            "submitted": out.get("submitted", False),
            "elapsed_sec": round(elapsed, 1),
            "reason": out.get("reason", ""),
        }
    except Exception as exc:
        return {
            "verdict": "CRASH",
            "error": str(exc),
            "elapsed_sec": round(time.time() - t0, 1),
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reports-dir", default=str(_DEFAULT_REPORTS_DIR))
    ap.add_argument("--rules", default=str(_DEFAULT_RULES))
    ap.add_argument("--catalog", default=str(_DEFAULT_CATALOG))
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    ap.add_argument("--model", default="qwen3.6-plus")
    args = ap.parse_args()

    reports_dir = Path(args.reports_dir)
    if not reports_dir.is_dir():
        raise SystemExit(f"[FATAL] reports_dir not found: {reports_dir}")

    md_files = list(reports_dir.glob("pbui_*.md"))
    if len(md_files) < 2:
        raise SystemExit(
            f"[FATAL] reports_dir 内 pbui_*.md 少于 2 份（当前 {len(md_files)} 份），不值得聚合"
        )

    print(f"聚合 {len(md_files)} 份 extraction_reports，model={args.model}")
    print(f"reports_dir: {reports_dir}")
    print(f"out: {args.out}")

    input_data = {
        "reports_dir": str(reports_dir).replace("\\", "/"),
        "rules_library_path": str(args.rules).replace("\\", "/"),
        "catalog_path": str(args.catalog).replace("\\", "/"),
        "proposals_output_path": str(args.out).replace("\\", "/"),
    }

    result = asyncio.run(_run(input_data, args.model))

    print("\n=== SUMMARY ===")
    status = "✓" if result.get("submitted") else ("✗" if result["verdict"] == "CRASH" else "…")
    print(
        f"  {status} aggregation: {result['verdict']} "
        f"(turns={result.get('turn_count', '?')}, {result['elapsed_sec']}s)"
    )
    if result.get("proposals_path"):
        print(f"     → {result['proposals_path']}")
    if result.get("reason"):
        print(f"  reason: {result['reason']}")
    if result.get("error"):
        print(f"  error: {result['error']}")


if __name__ == "__main__":
    main()
