# [OMNI] origin=claude-code domain=tests/teams/csv_to_md ts=2026-04-24T00:00:00Z type=test
"""csv_to_md team contract tests (TDD red/green).

Red phase: run before team is produced → pipeline not registered → all FAIL.
Green phase: after team_builder produces + deploys csv_to_md → all PASS.

NO PATCHING THE TEAM. Failing green = re-generate from team_builder, not fix by hand.

Invokes the requirement's acceptance.py logic for each case.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


# Import shared acceptance logic from requirement doc
ACCEPTANCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "plans" / "agent-framework" / "[2026-04-24]TEAM-BUILDER-REAL-PASS" / "requirements" / "csv_to_md"
sys.path.insert(0, str(ACCEPTANCE_DIR))
import acceptance  # noqa: E402


PIPELINE_NAME = "csv-to-md"


@pytest.fixture(scope="module")
def run_team(make_runner):
    return make_runner(PIPELINE_NAME)


# ── Success cases (逐字节 diff) ────────────────────────────────────────


@pytest.mark.parametrize("case_name,csv_name,md_name", [
    ("case_1_basic", "case_1_basic.csv", "case_1_basic.md"),
    ("case_2_special", "case_2_special.csv", "case_2_special.md"),
    ("case_3_header_only", "case_3_header_only.csv", "case_3_header_only.md"),
])
def test_success_case(run_team, case_name, csv_name, md_name):
    csv_path = ACCEPTANCE_DIR / "fixtures" / csv_name
    expected_path = ACCEPTANCE_DIR / "expected" / md_name
    expected = expected_path.read_text(encoding="utf-8")

    verdict = run_team({"path": str(csv_path)})
    kind_val = getattr(getattr(verdict, "kind", None), "value", None)
    assert kind_val == "pass", f"expect PASS, got {kind_val} · diag={getattr(verdict, 'diagnosis', '')[:300]}"

    actual = acceptance._extract_markdown(verdict.output)
    assert actual is not None, f"output is not markdown string: {type(verdict.output).__name__} · value={str(verdict.output)[:200]}"
    assert actual == expected, (
        f"\nexpected ({len(expected)} bytes):\n{expected!r}\n"
        f"actual   ({len(actual)} bytes):\n{actual!r}"
    )


# ── Error cases ────────────────────────────────────────────────────────


def test_error_file_not_found(run_team):
    verdict = run_team({"path": str(ACCEPTANCE_DIR / "fixtures" / "does_not_exist.csv")})
    kind_val = getattr(getattr(verdict, "kind", None), "value", None)
    assert kind_val == "fail", f"expect FAIL, got {kind_val}"
    diag = (getattr(verdict, "diagnosis", "") or "").lower()
    assert any(k in diag for k in ("not found", "不存在", "no such", "filenotfound")), \
        f"diagnosis should mention file-not-found: {diag[:200]}"


def test_error_bad_utf8(run_team):
    verdict = run_team({
        "path": str(ACCEPTANCE_DIR / "fixtures" / "case_error_bad_utf8.csv"),
        "encoding": "utf-8",
    })
    kind_val = getattr(getattr(verdict, "kind", None), "value", None)
    assert kind_val == "fail", f"expect FAIL, got {kind_val}"
    diag = (getattr(verdict, "diagnosis", "") or "").lower()
    assert any(k in diag for k in ("encoding", "decode", "utf", "unicodedecode")), \
        f"diagnosis should mention encoding: {diag[:200]}"


# ── Reproducibility (same input twice, same output) ─────────────────────


def test_reproducibility(run_team):
    csv_path = ACCEPTANCE_DIR / "fixtures" / "case_1_basic.csv"
    v1 = run_team({"path": str(csv_path)})
    v2 = run_team({"path": str(csv_path)})
    o1 = acceptance._extract_markdown(v1.output)
    o2 = acceptance._extract_markdown(v2.output)
    assert o1 is not None and o2 is not None, "both runs must produce markdown"
    assert o1 == o2, f"two runs must be byte-identical · first={len(o1)} second={len(o2)}"
