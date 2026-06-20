# [OMNI] origin=claude-code domain=tests/teams/repo_absorption ts=2026-04-24T00:00:00Z type=test
"""repo_absorption team contract tests (TDD red/green).

Red: pipeline not registered → FAIL.
Green: team produced + deployed → verify_payload on output.

NO PATCHING. Failing green = re-generate via team_builder.

Structure + truthfulness assertions (Q1-Q3 per requirement §5).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


ACCEPTANCE_DIR = Path(__file__).resolve().parents[3] / "docs" / "plans" / "agent-framework" / "[2026-04-24]TEAM-BUILDER-REAL-PASS" / "requirements" / "repo_absorption"
sys.path.insert(0, str(ACCEPTANCE_DIR))
import acceptance  # noqa: E402


PIPELINE_NAME = "repo-absorption"


@pytest.fixture(scope="module")
def run_team(make_runner):
    return make_runner(PIPELINE_NAME)


# ── Success cases ─────────────────────────────────────────────────────


@pytest.mark.parametrize("case_name,input_dict,repo_rel_path", [
    ("case_1_runtime_llm", {"repo_path": "src/omnicompany/runtime/llm", "top_n": 5}, "src/omnicompany/runtime/llm"),
    ("case_2_protocol", {"repo_path": "src/omnicompany/protocol", "top_n": 5}, "src/omnicompany/protocol"),
])
def test_success_case(run_team, case_name, input_dict, repo_rel_path):
    verdict = run_team(input_dict)
    kind_val = getattr(getattr(verdict, "kind", None), "value", None)
    assert kind_val == "pass", f"expect PASS, got {kind_val} · diag={getattr(verdict, 'diagnosis', '')[:300]}"

    payload = acceptance._extract_payload(verdict.output)
    assert payload is not None, \
        f"output 里找不到 proposals/report_markdown · got type={type(verdict.output).__name__}"

    ok, errs = acceptance.verify_payload(payload, repo_rel_path)
    assert ok, f"{len(errs)} failures:\n" + "\n".join(f"  - {e}" for e in errs[:10])


# ── Error cases ───────────────────────────────────────────────────────


def test_error_repo_not_exist(run_team):
    verdict = run_team({"repo_path": "/does/not/exist/surely", "top_n": 3})
    kind_val = getattr(getattr(verdict, "kind", None), "value", None)
    assert kind_val == "fail", f"expect FAIL, got {kind_val}"
    diag = (getattr(verdict, "diagnosis", "") or "").lower()
    assert any(k in diag for k in ("not exist", "not found", "不存在", "no such")), \
        f"diagnosis should mention not-exist: {diag[:200]}"


# ── Reproducibility (same input twice → both PASS structure, content may differ) ──


def test_reproducibility_structure(run_team):
    """LLM 非确定性 · 不要求两次内容一致 · 但两次都必须满足结构 + 质量断言."""
    inp = {"repo_path": "src/omnicompany/runtime/llm", "top_n": 5}
    for run_idx in (1, 2):
        v = run_team(inp)
        kind_val = getattr(getattr(v, "kind", None), "value", None)
        assert kind_val == "pass", f"run {run_idx}: expect PASS, got {kind_val}"
        payload = acceptance._extract_payload(v.output)
        assert payload is not None, f"run {run_idx}: output missing proposals/report"
        ok, errs = acceptance.verify_payload(payload, "src/omnicompany/runtime/llm")
        assert ok, f"run {run_idx}: {errs[:5]}"
