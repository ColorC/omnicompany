from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

import pytest

from omnicompany.packages.services._core.team_builder.scripts import provider_baseline_from_snapshot as script


def _write_snapshot(root: Path) -> Path:
    snapshot_dir = root / "data" / "domains" / "team_builder" / "snapshots" / "sample"
    snapshot_dir.mkdir(parents=True)
    (snapshot_dir / "team_design.json").write_text(json.dumps({
        "team_name": "repo_absorption",
        "workers_skeleton": [{"worker_name": "RepoScannerWorker"}],
        "materials_skeleton": [{"material_id": "repo.input.request"}],
    }, ensure_ascii=False), encoding="utf-8")
    (snapshot_dir / "worker_design_detailed.json").write_text(json.dumps({
        "details": [
            {
                "worker_id": "repo_scanner",
                "cn_name": "仓库扫描器",
                "impl_type": "HARD",
                "format_in": "repo.input.request",
                "format_out": "repo.material.scan",
            }
        ]
    }, ensure_ascii=False), encoding="utf-8")
    (snapshot_dir / "material_design_detailed.json").write_text(json.dumps({
        "details": [
            {
                "material_id": "repo.input.request",
                "json_schema": {"type": "object", "required": ["repo_path"]},
            },
            {
                "material_id": "repo.material.scan",
                "json_schema": {"type": "object", "required": ["files"]},
            },
        ]
    }, ensure_ascii=False), encoding="utf-8")
    return snapshot_dir


def test_provider_baseline_snapshot_plan_is_scratch_only(tmp_path: Path) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    snapshot = script.load_snapshot(snapshot_dir)

    plan = script.build_baseline_plan(
        root=tmp_path,
        snapshot_dir=snapshot_dir,
        snapshot=snapshot,
        provider="claude-code",
        permission="readonly",
        model_policy="none",
        timeout_s=900.0,
    )

    assert plan["ready"] is True
    assert plan["team_name"] == "repo_absorption"
    assert plan["counts"] == {"workers": 1, "materials": 2, "missing": 0}
    assert any(gate["id"] == "reuse_worker_code_orchestrator" and gate["status"] == "pass" for gate in plan["safety_gates"])
    assert "provider_baseline_from_snapshot" in plan["command"]
    assert plan["source"]["materialization_root"] == "_scratch/team_builder_real_material_validation"


@pytest.mark.asyncio
async def test_provider_baseline_snapshot_execute_writes_current_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot_dir = _write_snapshot(tmp_path)
    monkeypatch.setattr(script, "repo_root", lambda: tmp_path)

    class FakeKind:
        value = "pass"

    class FakeVerdict:
        kind = FakeKind()
        diagnosis = "1/1 workers"
        output = {
            "files": {
                "workers/repo_scanner.py": "from __future__ import annotations\n\nVALUE = 1\n",
            },
            "success_count": 1,
            "fail_count": 0,
            "lint_summary": [],
            "external_agent_runs": [
                {"worker_id": "repo_scanner", "provider": "claude-code", "status": "succeeded"}
            ],
        }

    class FakeOrchestrator:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, _: object) -> FakeVerdict:
            return FakeVerdict()

    monkeypatch.setattr(script, "WorkerCodeOrchestrator", FakeOrchestrator)
    payload = await script.execute_baseline(Namespace(
        snapshot=str(snapshot_dir),
        provider="claude-code",
        permission="readonly",
        model_policy="none",
        timeout=1.0,
        dry_run=False,
    ))

    summary_path = tmp_path / payload["source"]["summary"]
    assert summary_path.is_file()
    assert payload["mode"] == "snapshot_provider_baseline"
    assert payload["team_name"] == "repo_absorption"
    assert payload["verification"]["worker_success_count"] == 1
    assert payload["verification"]["compile_fail_count"] == 0
    assert payload["materials"]["worker_code_files_bundle"]["external_agent_runs"][0]["provider"] == "claude-code"
    assert (summary_path.parent / "code_package_files" / "workers" / "repo_scanner.py").is_file()
