from __future__ import annotations

import importlib
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKER_PATH = (
    ROOT
    / "src"
    / "omnicompany"
    / "packages"
    / "services"
    / "_core"
    / "guardian"
    / "workers"
    / "audit_tow_worker.py"
)


def test_audit_tow_worker_file_is_removed() -> None:
    assert not WORKER_PATH.exists()


def test_worker_exports_do_not_expose_audit_tow_worker() -> None:
    workers = importlib.import_module(
        "omnicompany.packages.services._core.guardian.workers"
    )

    assert not hasattr(workers, "AuditTowWorker")
    assert "AuditTowWorker" not in workers.__all__
    assert "AuditTowWorker" not in {worker.__name__ for worker in workers.ALL_WORKERS}


def test_patrol_shim_has_no_audit_tow_stage() -> None:
    shim = importlib.import_module(
        "omnicompany.packages.services._core.guardian._patrol_shim"
    )
    source = inspect.getsource(shim)

    assert "AuditTowWorker" not in source
    assert "audit_log.entry" not in source
    assert shim._count_by_severity(
        [{"severity": "HIGH"}, {"severity": "HIGH"}, {"severity": "LOW"}, {}]
    ) == {"HIGH": 2, "LOW": 1, "UNKNOWN": 1}


def test_run_guardian_returns_summary_without_fake_sink(monkeypatch) -> None:
    shim = importlib.import_module(
        "omnicompany.packages.services._core.guardian._patrol_shim"
    )

    class FakeGitDiffScanWorker:
        def run(self, input_data):
            assert input_data["guardian.scan_request"]["scan_mode"] == "staged"
            return type(
                "Verdict",
                (),
                {"output": {"scan_ts": "2026-06-13T00:00:00Z", "scan_mode": "staged"}},
            )()

    class FakeRuleEngineWorker:
        def run(self, input_data):
            assert input_data["scan_mode"] == "staged"
            return type(
                "Verdict",
                (),
                {
                    "output": {
                        "scan_ts": "2026-06-13T00:00:00Z",
                        "scan_mode": "staged",
                        "confirmed": [{"severity": "HIGH"}],
                        "needs_judgment": [{"severity": "LOW"}],
                    }
                },
            )()

    monkeypatch.setattr(shim, "GitDiffScanWorker", FakeGitDiffScanWorker)
    monkeypatch.setattr(shim, "RuleEngineWorker", FakeRuleEngineWorker)

    result = shim.run_guardian({"scan_mode": "staged"})

    assert result == {
        "scan_ts": "2026-06-13T00:00:00Z",
        "scan_mode": "staged",
        "violations_found": 2,
        "by_severity": {"HIGH": 1, "LOW": 1},
    }
    assert "persisted_to" not in result


def test_material_registry_has_no_fake_audit_sink() -> None:
    materials = importlib.import_module(
        "omnicompany.packages.services._core.guardian.materials"
    )

    material_ids = {material.id for material in materials.ALL_MATERIALS}
    assert "guardian.violation_set.judged" in material_ids
    assert "audit_log.entry" not in material_ids
    assert not hasattr(materials, "AUDIT_LOG_ENTRY")
