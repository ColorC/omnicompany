# [OMNI] origin=codex domain=services/team_builder/scripts ts=2026-05-18 type=tool
# [OMNI] material_id="material:core.team_builder.provider_baseline_from_snapshot.cli.py"
"""Create a current-format provider baseline from a saved TeamBuilder design snapshot.

The script intentionally reuses WorkerCodeOrchestrator.  It does not deploy the
generated team and writes only under _scratch/team_builder_real_material_validation.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import py_compile
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.agent.external_workers import (
    ExternalAgentPermissionMode,
)
from omnicompany.packages.services._core.team_builder.workers.code_gen_soft import (
    WorkerCodeOrchestrator,
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[7]


def materialization_root(root: Path) -> Path:
    return root / "_scratch" / "team_builder_real_material_validation"


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _team_slug(team_name: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", team_name.strip())
    return text.strip("._-") or "unnamed_team"


def _safe_rel_path(raw: str) -> Path | None:
    text = raw.replace("\\", "/").strip("/")
    if not text:
        return None
    path = Path(text)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    return path


def load_snapshot(snapshot_dir: Path) -> dict[str, Any]:
    return {
        "team_design": _read_json(snapshot_dir / "team_design.json"),
        "worker_design_detailed": _read_json(snapshot_dir / "worker_design_detailed.json"),
        "material_design_detailed": _read_json(snapshot_dir / "material_design_detailed.json"),
        "contract_audit": _read_json(snapshot_dir / "contract_audit.json"),
    }


def build_input_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "_from_team_architect": snapshot.get("team_design") or {},
        "_from_worker_designer": snapshot.get("worker_design_detailed") or {},
        "_from_material_designer": snapshot.get("material_design_detailed") or {},
    }


def build_baseline_plan(
    *,
    root: Path,
    snapshot_dir: Path,
    snapshot: dict[str, Any],
    provider: str,
    permission: str,
    model_policy: str,
    timeout_s: float,
) -> dict[str, Any]:
    team_design = snapshot.get("team_design") if isinstance(snapshot.get("team_design"), dict) else {}
    worker_design = snapshot.get("worker_design_detailed") if isinstance(snapshot.get("worker_design_detailed"), dict) else {}
    material_design = snapshot.get("material_design_detailed") if isinstance(snapshot.get("material_design_detailed"), dict) else {}
    workers = worker_design.get("details") if isinstance(worker_design.get("details"), list) else []
    materials = material_design.get("details") if isinstance(material_design.get("details"), list) else []

    missing: list[str] = []
    if not team_design:
        missing.append("snapshot 缺 team_design.json 或内容无效。")
    if not workers:
        missing.append("snapshot 缺 worker_design_detailed.details。")
    if not materials:
        missing.append("snapshot 缺 material_design_detailed.details。")

    team_name = str(team_design.get("team_name") or "")
    command = (
        "python -m omnicompany.packages.services._core.team_builder.scripts.provider_baseline_from_snapshot "
        f"--snapshot {snapshot_dir} --provider {provider} --permission {permission} "
        f"--model-policy {model_policy} --timeout {timeout_s:g}"
    )
    return {
        "available": True,
        "ready": not missing,
        "verdict": "ready_for_explicit_baseline" if not missing else "blocked",
        "team_name": team_name,
        "provider": provider,
        "permission": permission,
        "model_policy": model_policy,
        "timeout_s": timeout_s,
        "summary": (
            "设计快照可转成当前格式 provider 基线；执行结果只写 _scratch。"
            if not missing else f"设计快照不能转成 provider 基线：{len(missing)} 个输入缺口。"
        ),
        "counts": {
            "workers": len(workers),
            "materials": len(materials),
            "missing": len(missing),
        },
        "missing": missing,
        "safety_gates": [
            {
                "id": "reuse_worker_code_orchestrator",
                "status": "pass",
                "summary": "复用现有 WorkerCodeOrchestrator，不新增第二套 provider 执行器。",
            },
            {
                "id": "scratch_only",
                "status": "pass",
                "summary": "执行只写 _scratch/team_builder_real_material_validation，不部署 generated team。",
            },
            {
                "id": "readonly_provider",
                "status": "pass" if permission == "readonly" else "warning",
                "summary": "默认只读运行外部 provider；若 provider 写文件，external worker 会记录权限风险。",
            },
        ],
        "command": command,
        "source": {
            "snapshot_dir": str(snapshot_dir.relative_to(root)) if snapshot_dir.is_relative_to(root) else str(snapshot_dir),
            "materialization_root": "_scratch/team_builder_real_material_validation",
        },
    }


def _write_generated_files(code_root: Path, files: dict[str, Any]) -> list[str]:
    written: list[str] = []
    for raw_rel, content in files.items():
        if not isinstance(content, str):
            continue
        rel = _safe_rel_path(str(raw_rel))
        if rel is None:
            continue
        target = code_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(str(rel).replace("\\", "/"))
    return written


def _compile_generated_files(code_root: Path, written_files: list[str]) -> tuple[int, list[dict[str, Any]]]:
    failures: list[dict[str, Any]] = []
    for rel in written_files:
        path = code_root / rel
        if path.suffix != ".py":
            continue
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append({"path": rel, "error": str(exc)})
    return len(failures), failures


async def execute_baseline(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    snapshot_dir = Path(args.snapshot)
    if not snapshot_dir.is_absolute():
        snapshot_dir = root / snapshot_dir
    snapshot = load_snapshot(snapshot_dir)
    plan = build_baseline_plan(
        root=root,
        snapshot_dir=snapshot_dir,
        snapshot=snapshot,
        provider=args.provider,
        permission=args.permission,
        model_policy=args.model_policy,
        timeout_s=args.timeout,
    )
    if args.dry_run:
        return {"mode": "dry_run", "plan": plan}
    if not plan["ready"]:
        return {"mode": "blocked", "plan": plan}

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    orchestrator = WorkerCodeOrchestrator(
        external_provider=args.provider,
        external_permission_mode=ExternalAgentPermissionMode(args.permission),
        external_model_policy=args.model_policy,
        external_timeout_s=args.timeout,
        external_cwd=root,
    )
    verdict = await orchestrator.run(build_input_payload(snapshot))
    ended_at = datetime.now().astimezone().isoformat(timespec="seconds")

    output = _jsonable(verdict.output if isinstance(verdict.output, dict) else {})
    files = output.get("files") if isinstance(output.get("files"), dict) else {}
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{stamp}-{_team_slug(plan['team_name'])}-{args.provider}-snapshot"
    out_dir = materialization_root(root) / run_id
    materials_dir = out_dir / "materials"
    code_root = out_dir / "code_package_files"
    materials_dir.mkdir(parents=True, exist_ok=True)
    code_root.mkdir(parents=True, exist_ok=True)

    written_files = _write_generated_files(code_root, files)
    compile_fail_count, compile_failures = _compile_generated_files(code_root, written_files)
    worker_success = int(output.get("success_count") or 0)
    worker_fail = int(output.get("fail_count") or 0)
    worker_bundle = {
        "files": files,
        "success_count": worker_success,
        "fail_count": worker_fail,
        "lint_summary": output.get("lint_summary") if isinstance(output.get("lint_summary"), list) else [],
        "external_agent_runs": output.get("external_agent_runs") if isinstance(output.get("external_agent_runs"), list) else [],
        "written_files": written_files,
    }

    for name in ["team_design", "worker_design_detailed", "material_design_detailed", "contract_audit"]:
        value = snapshot.get(name)
        if value:
            (materials_dir / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    (materials_dir / "worker_code_files_bundle.json").write_text(
        json.dumps(worker_bundle, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    summary = {
        "mode": "snapshot_provider_baseline",
        "run_id": run_id,
        "team_name": plan["team_name"],
        "provider": args.provider,
        "permission": args.permission,
        "model_policy": args.model_policy,
        "started_at_local": started_at,
        "ended_at_local": ended_at,
        "verdict_kind": getattr(verdict.kind, "value", str(verdict.kind)),
        "diagnosis": verdict.diagnosis,
        "materials": {
            "team_design": snapshot.get("team_design") or {},
            "worker_design_detailed": snapshot.get("worker_design_detailed") or {},
            "material_design_detailed": snapshot.get("material_design_detailed") or {},
            "contract_audit": snapshot.get("contract_audit") or {},
            "worker_code_files_bundle": worker_bundle,
        },
        "verification": {
            "worker_success_count": worker_success,
            "worker_fail_count": worker_fail,
            "compile_fail_count": compile_fail_count,
            "compile_failures": compile_failures,
            "external_agent_runs": worker_bundle["external_agent_runs"],
        },
        "plan": plan,
        "source": {
            "snapshot_dir": plan["source"]["snapshot_dir"],
            "summary": str((out_dir / "summary.json").relative_to(root)),
            "code_package_files": str(code_root.relative_to(root)),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", default="data/domains/team_builder/snapshots/repo_abs_140156")
    parser.add_argument("--provider", default="claude-code")
    parser.add_argument("--permission", default="readonly", choices=[mode.value for mode in ExternalAgentPermissionMode])
    parser.add_argument("--model-policy", default="none", choices=["none", "cheap"])
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = asyncio.run(execute_baseline(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("mode") != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
