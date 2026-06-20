# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-25T00:00:00Z type=test
"""HealthReporter result-extraction contract.

The live HealthReporter is an AgentNodeLoop and requires a real EventBus. These
tests only cover the post-LLM JSON extraction contract, so they instantiate the
extractor router directly and never run the agent loop or call an LLM.
"""

from __future__ import annotations

import json

import pytest

from omnicompany.packages.services._core.guardian.routers import _HealthReporterExtractResult
from omnicompany.protocol.anchor import VerdictKind


_SCHEMA_WITH_CRITICAL = json.dumps(
    {
        "verdict": "unhealthy",
        "issues": [
            {
                "severity": "critical",
                "category": "root_contamination",
                "field": "root_stray_files",
                "message": "root has runtime files outside legal drawers",
                "evidence": "scan found /foo.db /bar.db /baz.db at repo root",
                "fix_hint": "move them to data/<domain>/ or delete them",
            }
        ],
        "summary": "one critical root contamination issue",
        "top_actions": ["clean root stray files"],
        "report": "full report text",
    }
)

_SCHEMA_NO_CRITICAL = json.dumps(
    {
        "verdict": "healthy",
        "issues": [
            {
                "severity": "major",
                "category": "omnimark_missing",
                "field": "packages/services/foo/bar.py",
                "message": "missing OmniMark header",
                "evidence": "first line: import os",
                "fix_hint": "add an OmniMark header",
            },
            {
                "severity": "minor",
                "category": "style",
                "field": "workers/xxx.py",
                "message": "description is too short",
                "evidence": "DESCRIPTION='x'",
                "fix_hint": "expand the description",
            },
        ],
        "summary": "no critical issues",
        "top_actions": ["add OmniMark header"],
        "report": "full report text",
    }
)

_SCHEMA_EMPTY = json.dumps(
    {
        "verdict": "healthy",
        "issues": [],
        "summary": "clean",
        "top_actions": [],
        "report": "no issues found",
    }
)


@pytest.fixture
def reporter() -> _HealthReporterExtractResult:
    return _HealthReporterExtractResult(bus=object())


def _extract(reporter: _HealthReporterExtractResult, text: str):
    return reporter.extract(
        final_text=text,
        messages=[],
        turn_count=0,
        stop_reason="finish",
    )


def test_critical_issue_fails_passed(reporter: _HealthReporterExtractResult):
    verdict = _extract(reporter, _SCHEMA_WITH_CRITICAL)

    assert verdict.kind == VerdictKind.FAIL
    assert verdict.output["passed"] is False
    assert verdict.output["counts"]["critical"] == 1


def test_only_major_minor_passes(reporter: _HealthReporterExtractResult):
    verdict = _extract(reporter, _SCHEMA_NO_CRITICAL)

    assert verdict.kind == VerdictKind.PASS
    assert verdict.output["passed"] is True
    assert verdict.output["counts"]["critical"] == 0
    assert verdict.output["counts"]["major"] == 1
    assert verdict.output["counts"]["minor"] == 1


def test_verdict_string_matches_critical_gate(reporter: _HealthReporterExtractResult):
    verdict = _extract(reporter, _SCHEMA_WITH_CRITICAL)

    assert verdict.output["verdict"] == "unhealthy"
    assert verdict.output["passed"] is False


def test_output_has_no_health_score_field(reporter: _HealthReporterExtractResult):
    for scenario in (_SCHEMA_WITH_CRITICAL, _SCHEMA_NO_CRITICAL, _SCHEMA_EMPTY):
        verdict = _extract(reporter, scenario)
        assert "health_score" not in verdict.output


def test_output_preserves_backward_compat_fields(reporter: _HealthReporterExtractResult):
    verdict = _extract(reporter, _SCHEMA_NO_CRITICAL)

    assert "total_issues" in verdict.output
    assert "report" in verdict.output
    assert "top_actions" in verdict.output
    assert "issues" in verdict.output
    assert "counts" in verdict.output
    assert verdict.output["total_issues"] == len(verdict.output["issues"])


def test_empty_issues_also_no_score(reporter: _HealthReporterExtractResult):
    verdict = _extract(reporter, _SCHEMA_EMPTY)

    assert "health_score" not in verdict.output
    assert verdict.output["passed"] is True
    assert verdict.output["counts"] == {"critical": 0, "major": 0, "minor": 0}


def test_parse_error_no_score_in_fallback(reporter: _HealthReporterExtractResult):
    verdict = _extract(reporter, "not json at all")

    assert verdict.kind == VerdictKind.FAIL
    if verdict.output:
        assert "health_score" not in verdict.output
