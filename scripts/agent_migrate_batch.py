"""Sequential migration batch v2 — 按小到大 + per-file try/except.

v1 (5-3 早) 死因: repo/learner turn 5 LLM call 输入 39K tokens 后无 output, asyncio loop hang 整个进程被 OS 杀.
v2 修法: 每文件独立 try/except, 单文件死不污染后续. 同时按 size asc 排.
"""
from __future__ import annotations

import asyncio
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from omnicompany.bus.sqlite import SQLiteBus
from omnicompany.packages.services._core.agent_migration import LegacyAgnlMigrationAgent
from omnicompany.protocol.events import FactoryEvent

# 按 size asc · plan C 只跑这 3 个小的, repo/learner + playtest AI IDE 手干
TARGETS = [
    "src/omnicompany/packages/services/_learning/absorption/landmark_picker.py",   # 20K, 7 custom GH/submit tools
    "src/omnicompany/packages/domains/voxel_engine/routers/mod_explorer_agent.py",   # 27K, custom session tools
    "src/omnicompany/packages/domains/gameplay_system/unity_qa/design/routers.py",           # 27K, Unity bridge tools
]

PROJECT_ROOT = Path(r"/workspace/omnicompany")
BACKUP_DIR = Path("/tmp/migration_batch_backups")


async def run_one(bus: SQLiteBus, target: str, idx: int, total: int) -> dict:
    src = PROJECT_ROOT / target
    backup = BACKUP_DIR / target.replace("/", "__").replace(".py", ".pre.py")
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, backup)
    print(f"\n{'='*70}", flush=True)
    print(f"[{idx}/{total}] TARGET: {target}", flush=True)
    print(f"BACKUP: {backup}", flush=True)
    print(f"SIZE: {src.stat().st_size} bytes", flush=True)

    trace_id = f"migration_batch_v2_{Path(target).stem}_{uuid.uuid4().hex[:6]}"
    print(f"TRACE_ID: {trace_id}", flush=True)

    try:
        await bus.publish(FactoryEvent(
            trace_id=trace_id, event_type="task.intent", source="ai-ide",
            payload={"instruction": f"batch v2 migrate {target}"},
            timestamp=datetime.now(timezone.utc),
        ))
        a = LegacyAgnlMigrationAgent(bus=bus)
        # asyncio.wait_for to bound a single agent to 30 min hard cap
        verdict = await asyncio.wait_for(
            a.run({"task": f"迁移 {target}", "trace_id": trace_id}),
            timeout=1800,
        )
        print(f"VERDICT: kind={verdict.kind.value}", flush=True)
        print(f"OUTPUT (truncated 1KB): {str(verdict.output)[:1000]}", flush=True)
        if verdict.diagnosis:
            print(f"DIAGNOSIS: {verdict.diagnosis}", flush=True)
        return {"target": target, "trace_id": trace_id, "kind": verdict.kind.value}
    except asyncio.TimeoutError:
        print(f"!!! TIMEOUT after 30min for {target}", flush=True)
        return {"target": target, "trace_id": trace_id, "kind": "timeout"}
    except Exception as e:
        import traceback
        print(f"!!! AGENT EXCEPTION: {type(e).__name__}: {e}", flush=True)
        print(traceback.format_exc(), flush=True)
        return {"target": target, "trace_id": trace_id, "kind": "crash", "err": str(e)}


async def main():
    bus = SQLiteBus(basename="ide_events.db")
    await bus.connect()
    results = []
    for i, target in enumerate(TARGETS, 1):
        r = await run_one(bus, target, i, len(TARGETS))
        results.append(r)
    print(f"\n{'='*70}\n=== BATCH V2 SUMMARY ({len(results)} files) ===\n{'='*70}", flush=True)
    for r in results:
        print(f"  [{r['kind']:8}] {r['target']}  trace={r['trace_id']}", flush=True)
    await bus.close()


if __name__ == "__main__":
    asyncio.run(main())
