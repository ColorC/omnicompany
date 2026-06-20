# [OMNI] origin=claude-code domain=tests/doctor ts=2026-04-20T00:00:00Z type=test
"""Blackboard 诊断子域 smoke · 黑板 Worker 对真实 Team 的基本行为验证.

基线选择:
- selftest + semantic_auditor 是 Clean Migration 的"真迁移"金标 Team,
  应对 6 诊断 Worker 产 0 违规 (纯新世界合规).
- 其他 Team (guardian materials / repair) 有历史遗留违规,
  本测试不断言 Team 本身合规, 只断言 Worker 执行成功 (不崩溃)。
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services.omnicompany import Worker
from omnicompany.packages.services.doctor.workers.blackboard import (
    ALL_WORKERS_BLACKBOARD,
    MaterialKindLegalityWorker,
    FormatInModeCheckerWorker,
    VerdictOutputFlatCheckerWorker,
    OrphanWorkerScannerWorker,
    UnconsumedMaterialScannerWorker,
    EmitAsNewJobCheckerWorker,
)


CLEAN_TEAMS = [
    "omnicompany.packages.services._core.selftest",
    # semantic_auditor 已归档 (2026-05-05 诊断重制 step 7)
]


@pytest.fixture(scope="module")
def req_factory():
    def _make(team_path: str) -> dict:
        return {"doctor.blackboard.audit_request": {"team_module_path": team_path}}
    return _make


class TestWorkerRegistration:
    def test_6_workers_registered(self):
        assert len(ALL_WORKERS_BLACKBOARD) == 6

    def test_all_subclass_worker(self):
        for cls in ALL_WORKERS_BLACKBOARD:
            assert issubclass(cls, Worker), f"{cls.__name__} not Worker subclass"

    def test_each_has_format_in_out_description(self):
        for cls in ALL_WORKERS_BLACKBOARD:
            assert cls.FORMAT_IN == "doctor.blackboard.audit_request"
            assert cls.FORMAT_OUT.startswith("doctor.blackboard.")
            assert len(cls.DESCRIPTION) >= 20


class TestCleanTeamZeroViolations:
    """selftest / semantic_auditor 是真迁移金标, 应 0 违规."""

    @pytest.mark.parametrize("team", CLEAN_TEAMS)
    def test_kind_legality(self, team, req_factory):
        v = MaterialKindLegalityWorker().run(req_factory(team))
        assert v.kind.name == "PASS", v.diagnosis
        assert v.output["violation_count"] == 0, f"{team}: {v.output['findings']}"

    @pytest.mark.parametrize("team", CLEAN_TEAMS)
    def test_format_in_mode(self, team, req_factory):
        v = FormatInModeCheckerWorker().run(req_factory(team))
        assert v.kind.name == "PASS"
        assert v.output["violation_count"] == 0, f"{team}: {v.output['findings']}"

    @pytest.mark.parametrize("team", CLEAN_TEAMS)
    def test_output_flat(self, team, req_factory):
        v = VerdictOutputFlatCheckerWorker().run(req_factory(team))
        assert v.kind.name == "PASS"
        assert v.output["violation_count"] == 0, f"{team}: {v.output['findings']}"

    @pytest.mark.parametrize("team", CLEAN_TEAMS)
    def test_orphan_workers(self, team, req_factory):
        v = OrphanWorkerScannerWorker().run(req_factory(team))
        assert v.kind.name == "PASS"
        assert v.output["orphan_count"] == 0, f"{team}: {v.output['findings']}"

    @pytest.mark.parametrize("team", CLEAN_TEAMS)
    def test_unconsumed_materials(self, team, req_factory):
        v = UnconsumedMaterialScannerWorker().run(req_factory(team))
        assert v.kind.name == "PASS"
        assert v.output["unconsumed_count"] == 0, f"{team}: {v.output['findings']}"

    @pytest.mark.parametrize("team", CLEAN_TEAMS)
    def test_emit_as_new_job(self, team, req_factory):
        v = EmitAsNewJobCheckerWorker().run(req_factory(team))
        assert v.kind.name == "PASS"
        # emit 可能有也可能无, 但若有必须有理由. 金标 Team 预期 0 违规.
        assert v.output["violation_count"] == 0, f"{team}: {v.output['findings']}"


class TestInvalidRequest:
    def test_missing_team_path_fails(self):
        v = MaterialKindLegalityWorker().run({"doctor.blackboard.audit_request": {}})
        assert v.kind.name == "FAIL"
        assert "team_module_path" in v.diagnosis

    def test_bad_team_path_fails_gracefully(self):
        v = MaterialKindLegalityWorker().run({
            "doctor.blackboard.audit_request": {"team_module_path": "nonexistent.xyz"}
        })
        assert v.kind.name == "FAIL"
        assert "加载 Team 失败" in v.diagnosis


class TestDetectionCapability:
    """验证 Worker 能真的捕获违规 (用 guardian — 已知有 kind 遗漏)."""

    def test_detects_guardian_kind_gaps(self, req_factory):
        v = MaterialKindLegalityWorker().run(
            req_factory("omnicompany.packages.services.guardian")
        )
        assert v.kind.name == "PASS"
        # guardian.materials.py 的 5 条 Material 当前全未标 kind
        assert v.output["violation_count"] >= 1, "应能捕获 guardian materials kind 缺失"

    def test_guardian_no_longer_has_known_orphans(self, req_factory):
        v = OrphanWorkerScannerWorker().run(
            req_factory("omnicompany.packages.services.guardian")
        )
        assert v.kind.name == "PASS"
        # Guardian's current public package no longer relies on a known orphan
        # module as a diagnostic fixture.
        assert v.output["orphan_count"] == 0, v.output["findings"]
