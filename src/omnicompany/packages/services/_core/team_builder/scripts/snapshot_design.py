# [OMNI] origin=claude-code domain=services/team_builder/scripts ts=2026-04-25T00:00:00Z type=tool
# [OMNI] material_id="material:core.team_builder.snapshot_script.design_capture.py"
"""snapshot_design · 跑 team-builder 抓 4 份关键 material 落 JSON · 不 deploy.

阶段 0 工具 (TEAM-BUILDER-RECONSTRUCT plan §4.0).

用法:
    python -m omnicompany.packages.services._core.team_builder.scripts.snapshot_design \
        --req-file docs/plans/.../_archive/req_inputs/repo_absorption_req.txt \
        --run-id repo_abs_$(date +%H%M%S)

落:
  data/domains/team_builder/snapshots/<run_id>/
    team_design.json
    worker_design_detailed.json
    material_design_detailed.json
    contract_audit.json
    sink_registration_plan.json (若 dispatch 跑完 + PASS)
    _meta.json

实现: 包装目标 4 个 Worker 的 run() 抓 verdict.output · 不污染主管线 · TeamRunner 路由不变.
"""
from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


_TARGET_NODES = {
    "team_architect": "team_design.json",
    "worker_designer": "worker_design_detailed.json",
    "material_designer": "material_design_detailed.json",
    "contract_auditor": "contract_audit.json",
}


def _wrap_worker_run(worker: Any, node_id: str, captured: dict, out_dir: Path) -> None:
    """包装 worker.run · 抓 verdict.output 落盘 · 透明传递返回值."""
    original_run = worker.run

    if inspect.iscoroutinefunction(original_run):
        async def async_wrapped(input_data):
            verdict = await original_run(input_data)
            _capture(verdict, node_id, captured, out_dir)
            return verdict
        worker.run = async_wrapped
    else:
        def sync_wrapped(input_data):
            verdict = original_run(input_data)
            # verdict 可能仍是 awaitable
            if inspect.isawaitable(verdict):
                # to_thread 保护下不应到这, 但兜一下
                async def _await_and_cap():
                    v = await verdict
                    _capture(v, node_id, captured, out_dir)
                    return v
                return _await_and_cap()
            _capture(verdict, node_id, captured, out_dir)
            return verdict
        worker.run = sync_wrapped


def _capture(verdict: Any, node_id: str, captured: dict, out_dir: Path) -> None:
    output = getattr(verdict, "output", None)
    kind = getattr(getattr(verdict, "kind", None), "value", "?")
    diag = getattr(verdict, "diagnosis", "") or ""
    if output is None:
        captured[node_id] = {"_status": "no_output", "kind": kind, "diagnosis": diag[:300]}
        return
    fname = _TARGET_NODES[node_id]
    path = out_dir / fname
    try:
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        size = path.stat().st_size
        captured[node_id] = {
            "_status": "captured",
            "file": fname,
            "kind": kind,
            "diagnosis": diag[:300],
            "bytes": size,
            "top_keys": (list(output.keys())[:20] if isinstance(output, dict) else None),
        }
        print(f"  [OK] {node_id} → {fname} ({size} bytes · kind={kind})")
    except Exception as e:
        captured[node_id] = {"_status": "write_error", "error": f"{type(e).__name__}: {e}"}
        print(f"  [WARN] {node_id} 写盘失败: {e}")


async def _dispatch_with_capture(req_text: str, captured: dict, out_dir: Path) -> tuple[Any, str]:
    """改写自 core.dispatch.dispatch · 加 worker 包装."""
    from dotenv import load_dotenv
    load_dotenv()

    from omnicompany.core.registry import get_or_raise, discover
    from omnicompany.core.config import resolve_db_path
    discover()
    from omnicompany.bus.sqlite import SQLiteBus
    from omnicompany.runtime.exec.runner import TeamRunner
    from omnicompany.core.dispatch import _call_build_bindings, _load_format_registry_for_domain

    entry = get_or_raise("team-builder")
    pipeline = entry.build_team()
    bindings = _call_build_bindings(entry, {"text": req_text})

    # 包装目标 4 个 worker
    for node_id in _TARGET_NODES:
        worker = bindings.get(node_id)
        if worker is None:
            print(f"  [WARN] 节点 {node_id} 不在 bindings 中 · skip 包装")
            continue
        _wrap_worker_run(worker, node_id, captured, out_dir)

    resolved_db = resolve_db_path(entry.domain)
    resolved_db.parent.mkdir(parents=True, exist_ok=True)
    steps = entry.default_max_steps or 1000
    fmt_registry = _load_format_registry_for_domain(entry.domain)

    print(f"[snapshot] dispatch start · max_steps={steps} · db={resolved_db}")
    async with SQLiteBus(resolved_db) as bus:
        runner = TeamRunner(
            pipeline, bindings, bus,
            max_steps=steps,
            source=entry.domain,
            format_registry=fmt_registry,
        )
        try:
            result = await runner.run({"text": req_text})
        except Exception as e:
            return None, f"runner raised: {type(e).__name__}: {str(e)[:500]}"
    return result, "dispatch ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--req-file", required=True, help="需求文本文件路径")
    ap.add_argument("--run-id", default=None, help="运行 ID · 默认当前时间戳")
    ap.add_argument("--out-dir", default="data/domains/team_builder/snapshots", help="快照根目录")
    args = ap.parse_args()

    req_path = Path(args.req_file)
    if not req_path.exists():
        print(f"[FAIL] req-file 不存在: {req_path}", file=sys.stderr)
        return 2
    req_text = req_path.read_text(encoding="utf-8")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    started = datetime.utcnow().isoformat() + "Z"
    print(f"[snapshot] run_id={run_id} · req {len(req_text)} chars · out={out_dir}")

    captured: dict = {}
    sink, report = asyncio.run(_dispatch_with_capture(req_text, captured, out_dir))
    print(f"[snapshot] dispatch result: {report}")

    # 若 dispatch 跑完产 sink material · 落盘
    if sink is not None:
        sink_obj = sink
        if hasattr(sink, "output"):  # Verdict
            sink_obj = sink.output
        if isinstance(sink_obj, dict):
            (out_dir / "sink_registration_plan.json").write_text(
                json.dumps(sink_obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            print("  [OK] sink → sink_registration_plan.json")

    # 落 _meta
    meta = {
        "run_id": run_id,
        "started_at": started,
        "ended_at": datetime.utcnow().isoformat() + "Z",
        "req_file": str(req_path),
        "req_chars": len(req_text),
        "dispatch_report": report,
        "captured_targets": _TARGET_NODES,
        "captured_status": captured,
    }
    (out_dir / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )

    captured_count = sum(1 for v in captured.values() if v.get("_status") == "captured")
    print(f"\n=== snapshot done · {captured_count}/4 materials captured · {out_dir} ===")
    return 0 if captured_count == 4 else 1


if __name__ == "__main__":
    sys.exit(main())
