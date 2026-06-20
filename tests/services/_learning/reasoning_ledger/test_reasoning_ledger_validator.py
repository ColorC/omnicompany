from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from omnicompany.packages.services._learning.reasoning_ledger import (
    validate_ledger_case_path,
)


PROJECT_ROOT = Path(__file__).resolve().parents[4]
FIXTURE_CASE = (
    PROJECT_ROOT
    / "tests"
    / "fixtures"
    / "reasoning_ledger"
    / "cases"
    / "explicit_fail_edge_requirement_falsified"
)


def test_fixture_passes_v0_validator() -> None:
    issues = validate_ledger_case_path(FIXTURE_CASE, project_root=PROJECT_ROOT)

    assert _errors(issues) == []


def test_missing_reference_fails(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    claim_path = case / "claims" / "H-034.yaml"
    claim = _load_yaml(claim_path)
    claim["supported_by"] = ["EV-does-not-exist"]
    _write_yaml(claim_path, claim)

    issues = validate_ledger_case_path(case, project_root=PROJECT_ROOT)

    assert _has_error(issues, "missing_reference", object_id="H-034", field="supported_by")


def test_falsified_claim_without_attacker_fails(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    claim_path = case / "claims" / "H-034.yaml"
    claim = _load_yaml(claim_path)
    claim["attacked_by"] = []
    claim["relations"]["conflicts"] = []
    _write_yaml(claim_path, claim)

    for evidence_path in (case / "evidence").glob("*.yaml"):
        evidence = _load_yaml(evidence_path)
        evidence["attacks"] = [item for item in evidence.get("attacks", []) if item != "H-034"]
        _write_yaml(evidence_path, evidence)

    conflict_path = case / "conflicts" / "CON-h038-attacks-h034.yaml"
    conflict = _load_yaml(conflict_path)
    conflict["to"] = "H-038"
    _write_yaml(conflict_path, conflict)

    issues = validate_ledger_case_path(case, project_root=PROJECT_ROOT)

    assert _has_error(issues, "falsified_claim_without_attacker", object_id="H-034")


def test_wrong_directory_type_fails(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    claim_path = case / "claims" / "H-034.yaml"
    claim = _load_yaml(claim_path)
    claim["type"] = "evidence"
    _write_yaml(claim_path, claim)

    issues = validate_ledger_case_path(case, project_root=PROJECT_ROOT)

    assert _has_error(issues, "wrong_directory_type", object_id="H-034", field="type")


def test_artifact_missing_path_warns_or_fails_by_policy(tmp_path: Path) -> None:
    case = _copy_fixture(tmp_path)
    artifact_path = case / "artifacts" / "ART-v21-report.yaml"
    artifact = _load_yaml(artifact_path)
    artifact["artifact_path"] = "docs/no-such-report.md"
    _write_yaml(artifact_path, artifact)

    issues = validate_ledger_case_path(case, project_root=PROJECT_ROOT)

    assert _has_error(issues, "artifact_path_missing", object_id="ART-v21-report")


def _copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "case"
    shutil.copytree(FIXTURE_CASE, target)
    return target


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _errors(issues) -> list:
    return [issue for issue in issues if issue.severity == "error"]


def _has_error(issues, code: str, *, object_id: str | None = None, field: str | None = None) -> bool:
    for issue in issues:
        if issue.severity != "error" or issue.code != code:
            continue
        if object_id is not None and issue.object_id != object_id:
            continue
        if field is not None and issue.field != field:
            continue
        return True
    return False
