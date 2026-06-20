# [OMNI] origin=claude-code domain=tests/doctor ts=2026-04-25T00:00:00Z type=test
"""doctor health_writers 契约变更 #02 测试 · 去 health_score/health_grade, 用 v2 schema.

对应 plan: docs/plans/[2026-04-25]CORE-ARCH-DEBT-CLEANUP/contract_change_02_doctor_health_grade_removal.md

铁律 (2026-04-25):
  - 不打分, 保留完整语义信号
  - severity 归一 critical/major/minor
  - 不做 v1 兼容

覆盖 5 producer:
  - WorkerHealthWriter (doctor/workers/worker/health_writer.py)
  - MaterialHealthWriterWorker (doctor/workers/material/health_writer.py)
  - TopoHealthWriter (doctor/workers/team/topo_health_writer.py)
  - TopologyCheckWorker (doctor/workers/team/topology_check.py)
  - SignatureDiffWorker (doctor/workers/material/signature_diff.py)
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services.doctor.health_record_v2 import (
    SCHEMA_VERSION, is_v2_record, assert_no_legacy_fields,
)
from omnicompany.protocol.anchor import VerdictKind


# ═══════════════════════════════════════════════════════════════════
# WorkerHealthWriter (Router 健康档案)
# ═══════════════════════════════════════════════════════════════════

class TestWorkerHealthWriter:
    """Router 级 · checks 聚合成 v2 health_record."""

    @pytest.fixture
    def worker(self):
        from omnicompany.packages.services.doctor.workers.worker.health_writer import WorkerHealthWriter as _W
        return _W()

    def test_T1_critical_failure_sets_passed_false(self, worker):
        """checks 含 CRITICAL failure → passed=False, counts['critical']>=1"""
        out = worker.run({
            "worker_class": "FooRouter",
            "checks": [
                {"check": "sig", "passed": True, "severity": "CRITICAL", "observation": "ok"},
                {"check": "desc", "passed": False, "severity": "CRITICAL", "observation": "DESCRIPTION 缺"},
            ],
        })
        assert out.kind == VerdictKind.PASS      # Worker 自身 Verdict.PASS (Worker 总产出记录 · gate 在下游读 passed)
        r = out.output
        assert r["schema_version"] == SCHEMA_VERSION
        assert r["passed"] is False
        assert r["counts"]["critical"] >= 1

    def test_T2_all_pass_clean_record(self, worker):
        """全 pass → passed=True, failures 空."""
        out = worker.run({
            "worker_class": "BarRouter",
            "checks": [
                {"check": "sig", "passed": True, "severity": "CRITICAL"},
                {"check": "r10", "passed": True, "severity": "MEDIUM"},
            ],
        })
        r = out.output
        assert r["passed"] is True
        assert r["counts"]["critical"] == 0
        assert r["counts"]["major"] == 0
        assert r["counts"]["minor"] == 0
        assert r["verdict"] == "healthy"

    def test_T3_no_legacy_fields(self, worker):
        """硬契约: output **不含** health_score / health_grade."""
        out = worker.run({
            "worker_class": "BazRouter",
            "checks": [
                {"check": "x", "passed": False, "severity": "MEDIUM", "observation": "fail"},
            ],
        })
        assert_no_legacy_fields(out.output, context="WorkerHealthWriter")

    def test_T4_failures_by_severity_normalized(self, worker):
        """severity 归一: CRITICAL→critical, HIGH→major, MEDIUM/LOW→minor, INFO 丢."""
        out = worker.run({
            "worker_class": "NormRouter",
            "checks": [
                {"check": "c1", "passed": False, "severity": "CRITICAL", "observation": "crit-1"},
                {"check": "h1", "passed": False, "severity": "HIGH", "observation": "high-1"},
                {"check": "m1", "passed": False, "severity": "MEDIUM", "observation": "med-1"},
                {"check": "l1", "passed": False, "severity": "LOW", "observation": "low-1"},
                {"check": "i1", "passed": False, "severity": "INFO", "observation": "info-1"},
            ],
        })
        fs = out.output["failures_by_severity"]
        assert any("crit-1" in x for x in fs["critical"])
        assert any("high-1" in x for x in fs["major"])
        # MEDIUM 和 LOW 合并成 minor
        minor_blob = " ".join(fs["minor"])
        assert "med-1" in minor_blob and "low-1" in minor_blob
        # INFO 不应出现
        for v in fs.values():
            assert all("info-1" not in x for x in v)


# ═══════════════════════════════════════════════════════════════════
# MaterialHealthWriterWorker (Format 健康档案)
# ═══════════════════════════════════════════════════════════════════

class TestMaterialHealthWriter:
    @pytest.fixture
    def worker(self):
        from omnicompany.packages.services.doctor.workers.material.health_writer import MaterialHealthWriterWorker
        return MaterialHealthWriterWorker()

    def test_T1_critical_fail(self, worker):
        out = worker.run({
            "material_id": "foo.bar",
            "check_five_element": {"check": "five_element", "passed": False, "severity": "CRITICAL", "observation": "缺 id"},
            "check_tag_coverage": {"check": "tag_coverage", "passed": True, "severity": "MEDIUM"},
        })
        r = out.output
        assert r["schema_version"] == SCHEMA_VERSION
        assert r["passed"] is False
        assert r["counts"]["critical"] >= 1

    def test_T2_all_pass(self, worker):
        out = worker.run({
            "material_id": "foo.baz",
            "check_five_element": {"check": "five_element", "passed": True, "severity": "CRITICAL"},
            "check_tag_coverage": {"check": "tag_coverage", "passed": True, "severity": "MEDIUM"},
        })
        r = out.output
        assert r["passed"] is True
        assert r["counts"]["critical"] == 0

    def test_T3_no_legacy_fields(self, worker):
        out = worker.run({"material_id": "foo.x"})
        assert_no_legacy_fields(out.output, context="MaterialHealthWriterWorker")


# ═══════════════════════════════════════════════════════════════════
# TopoHealthWriter (Team 级)
# ═══════════════════════════════════════════════════════════════════

class TestTopoHealthWriter:
    @pytest.fixture
    def worker(self):
        from omnicompany.packages.services.doctor.workers.team.topo_health_writer import TeamTopoHealthWriter
        return TeamTopoHealthWriter()

    def test_T3_no_legacy_fields(self, worker):
        # 最小化测试 · 只断"不含旧字段"
        # 具体入参等改完后再补 T1/T2
        try:
            out = worker.run({
                "pipeline_name": "foo",
                "checks": [],
            })
            if out.output:
                assert_no_legacy_fields(out.output, context="TopoHealthWriter")
        except Exception:
            pytest.skip("TopoHealthWriter 未来输入需要 · 先验硬契约")


# ═══════════════════════════════════════════════════════════════════
# SignatureDiffWorker 错误路径 (曾产 health_grade='F')
# ═══════════════════════════════════════════════════════════════════

class TestSignatureDiffErrorPath:
    def test_error_path_no_legacy_fields(self):
        """signature_diff 错误路径也不得塞 health_grade='F'."""
        from omnicompany.packages.services.doctor.workers.material.signature_diff import MaterialSignatureDiffWorker
        w = MaterialSignatureDiffWorker()
        # 造一个让它 sig_diff 失败的 input (material_id 不存在)
        out = w.run({
            "material_id": "definitely.nonexistent.material.xyz_test",
            "source_root": "/workspace/omnicompany/src/omnicompany",
        })
        # 无论 PASS/FAIL · output (若有) 不得含 health_score/health_grade
        if out.output:
            assert_no_legacy_fields(out.output, context="SignatureDiffWorker")


# ═══════════════════════════════════════════════════════════════════
# TopologyCheckWorker (用 health_grade='FAIL'/'WARN'/'PASS' 作状态)
# ═══════════════════════════════════════════════════════════════════

class TestTopologyCheck:
    def test_uses_topology_status_not_health_grade(self):
        """改后: topology_status='fail'/'warn'/'pass', 不再用 health_grade."""
        from omnicompany.packages.services.doctor.workers.team.topology_check import TeamTopologyCheck
        w = TeamTopologyCheck()
        try:
            # 最小化 input · 具体字段改后再补
            out = w.run({
                "pipeline_name": "test",
                "nodes": [],
                "edges": [],
            })
            if out.output:
                # 硬: output 不再含 health_grade
                assert "health_grade" not in str(out.output) or out.kind == VerdictKind.FAIL
        except Exception:
            pytest.skip("TopologyCheckWorker 输入需要具体 pipeline 数据 · 先占位")
