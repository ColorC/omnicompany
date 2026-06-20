# [OMNI] origin=codex domain=services/team_builder/scripts ts=2026-05-18 type=tool
# [OMNI] material_id="material:core.team_builder.provider_same_input_trial.cli.py"
"""Run or plan a same-input WorkerCodeOrchestrator provider trial.

This script reuses a saved TeamBuilder materialization summary as input.  It is
intended for provider comparison only: source repository writes are not needed,
and actual provider execution should stay in readonly mode unless explicitly
changed by a human.
"""

from __future__ import annotations

import argparse
import asyncio
import json
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
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_baseline_summary(root: Path, run_id: str | None = None) -> tuple[Path, dict[str, Any]]:
    base = materialization_root(root)
    if run_id:
        run_dir = base / run_id
        summary = _read_json(run_dir / "summary.json")
        if not summary:
            raise RuntimeError(f"baseline summary not found or invalid: {run_dir / 'summary.json'}")
        return run_dir, summary
    candidates = [path for path in base.iterdir() if path.is_dir() and (path / "summary.json").is_file()] if base.is_dir() else []
    if not candidates:
        raise RuntimeError(f"no TeamBuilder materialization summaries under {base}")
    run_dir = max(candidates, key=lambda path: ((path / "summary.json").stat().st_mtime, path.name))
    return run_dir, _read_json(run_dir / "summary.json")


def build_input_payload(summary: dict[str, Any]) -> dict[str, Any]:
    materials = summary.get("materials") if isinstance(summary.get("materials"), dict) else {}
    return {
        "_from_team_architect": materials.get("team_design") or {},
        "_from_worker_designer": materials.get("worker_design_detailed") or {},
        "_from_material_designer": materials.get("material_design_detailed") or {},
    }


def _external_runs(summary: dict[str, Any]) -> list[dict[str, Any]]:
    materials = summary.get("materials") if isinstance(summary.get("materials"), dict) else {}
    verification = summary.get("verification") if isinstance(summary.get("verification"), dict) else {}
    worker_bundle = materials.get("worker_code_files_bundle") if isinstance(materials.get("worker_code_files_bundle"), dict) else {}
    runs = verification.get("external_agent_runs") or worker_bundle.get("external_agent_runs") or []
    return [item for item in runs if isinstance(item, dict)]


def build_trial_plan(
    *,
    root: Path,
    baseline_run_dir: Path,
    summary: dict[str, Any],
    provider: str,
    permission: str,
    model_policy: str,
    timeout_s: float,
) -> dict[str, Any]:
    input_payload = build_input_payload(summary)
    worker_details = input_payload["_from_worker_designer"].get("details") if isinstance(input_payload["_from_worker_designer"], dict) else []
    material_details = input_payload["_from_material_designer"].get("details") if isinstance(input_payload["_from_material_designer"], dict) else []
    team_design = input_payload["_from_team_architect"] if isinstance(input_payload["_from_team_architect"], dict) else {}
    external_runs = _external_runs(summary)
    baseline_by_worker = {str(item.get("worker_id") or ""): item for item in external_runs}

    missing: list[str] = []
    if not team_design:
        missing.append("baseline summary 缺 team_design。")
    if not worker_details:
        missing.append("baseline summary 缺 worker_design_detailed.details。")
    if not material_details:
        missing.append("baseline summary 缺 material_design_detailed.details。")
    if not external_runs:
        missing.append("baseline summary 缺 external_agent_runs，无法比较 baseline provider 证据。")

    workers = []
    for detail in worker_details if isinstance(worker_details, list) else []:
        if not isinstance(detail, dict):
            continue
        worker_id = str(detail.get("worker_id") or "")
        baseline = baseline_by_worker.get(worker_id, {})
        workers.append({
            "worker_id": worker_id,
            "cn_name": str(detail.get("cn_name") or ""),
            "impl_type": str(detail.get("impl_type") or ""),
            "format_in": detail.get("format_in"),
            "format_out": detail.get("format_out"),
            "baseline_provider": str(baseline.get("provider") or ""),
            "baseline_status": str(baseline.get("status") or ""),
            "baseline_prompt_chars": int(baseline.get("prompt_chars") or 0),
            "baseline_rel_path": str(baseline.get("rel_path") or ""),
        })

    command = (
        "python -m omnicompany.packages.services._core.team_builder.scripts.provider_same_input_trial "
        f"--baseline-run {baseline_run_dir.name} --provider {provider} --permission {permission} "
        f"--model-policy {model_policy} --timeout {timeout_s:g}"
    )
    return {
        "available": True,
        "verdict": "ready_for_explicit_trial" if not missing else "blocked",
        "ready": not missing,
        "baseline_run_id": baseline_run_dir.name,
        "team_name": str(summary.get("team_name") or team_design.get("team_name") or ""),
        "baseline_provider": str(summary.get("provider") or ""),
        "target_provider": provider,
        "permission": permission,
        "model_policy": model_policy,
        "timeout_s": timeout_s,
        "summary": (
            "Codex 同口径试验已具备只读执行计划。"
            if not missing else f"Codex 同口径试验计划被阻断：{len(missing)} 个输入缺口。"
        ),
        "counts": {
            "workers": len(workers),
            "materials": len(material_details) if isinstance(material_details, list) else 0,
            "baseline_external_runs": len(external_runs),
            "missing": len(missing),
        },
        "workers": workers,
        "missing": missing,
        "safety_gates": [
            {"id": "readonly", "status": "pass" if permission == "readonly" else "warning", "summary": "默认只读运行 provider；若 provider 写文件，external worker 会标记权限违规。"},
            {"id": "same_input_materials", "status": "pass" if not missing else "warning", "summary": "输入来自同一 baseline summary 的 team_design、worker_design_detailed 和 material_design_detailed。"},
            {"id": "scratch_output", "status": "pass", "summary": "试验结果只写 _scratch/team_builder_provider_trials，不写真实 generated team 源码。"},
        ],
        "command": command,
        "source": {
            "baseline_summary": str((baseline_run_dir / "summary.json").relative_to(root)),
            "trial_root": "_scratch/team_builder_provider_trials",
        },
    }


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


async def execute_trial(args: argparse.Namespace) -> dict[str, Any]:
    root = repo_root()
    baseline_run_dir, summary = load_baseline_summary(root, args.baseline_run)
    plan = build_trial_plan(
        root=root,
        baseline_run_dir=baseline_run_dir,
        summary=summary,
        provider=args.provider,
        permission=args.permission,
        model_policy=args.model_policy,
        timeout_s=args.timeout,
    )
    if args.dry_run:
        return {"mode": "dry_run", "plan": plan}
    if not plan["ready"]:
        return {"mode": "blocked", "plan": plan}

    orchestrator = WorkerCodeOrchestrator(
        external_provider=args.provider,
        external_permission_mode=ExternalAgentPermissionMode(args.permission),
        external_model_policy=args.model_policy,
        external_timeout_s=args.timeout,
        external_cwd=root,
    )
    verdict = await orchestrator.run(build_input_payload(summary))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = root / "_scratch" / "team_builder_provider_trials" / f"{stamp}-{baseline_run_dir.name}-{args.provider}"
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": "executed",
        "baseline_run_id": baseline_run_dir.name,
        "provider": args.provider,
        "permission": args.permission,
        "model_policy": args.model_policy,
        "verdict_kind": getattr(verdict.kind, "value", str(verdict.kind)),
        "diagnosis": verdict.diagnosis,
        "output": _jsonable(verdict.output),
        "plan": plan,
        "source": {
            "trial_summary": str((out_dir / "summary.json").relative_to(root)),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-run", default=None)
    parser.add_argument("--provider", default="codex")
    parser.add_argument("--permission", default="readonly", choices=[mode.value for mode in ExternalAgentPermissionMode])
    parser.add_argument("--model-policy", default="cheap", choices=["none", "cheap"])
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    payload = asyncio.run(execute_trial(args))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("mode") != "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(main())
