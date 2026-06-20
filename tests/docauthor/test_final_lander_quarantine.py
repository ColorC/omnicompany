# [OMNI] origin=claude-code domain=tests/docauthor ts=2026-04-25T00:00:00Z type=test
"""FinalLanderWorker 隔离纪律测试 · 2026-04-25 修正.

铁律: passed=True 才写 src/, exhausted-not-passed 必须隔离到 drafts/_quarantine/<slug>/,
不污染产品文档区域.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnicompany.packages.services.docauthor.workers.final_lander import FinalLanderWorker
from omnicompany.protocol.anchor import VerdictKind


def _verdict(passed: bool, *, target: str, target_type: str = "manifest",
             iter_num: int = 0, max_refine: int = 1, draft: str = "# fake content\n",
             counts: dict | None = None, issues: list | None = None) -> dict:
    return {
        "docauthor.review-verdict": {
            "passed": passed,
            "target_type": target_type,
            "target_path": target,
            "target_service_path": target if target_type == "manifest" else "",
            "target_package_path": target if target_type == "design" else "",
            "iter": iter_num,
            "max_refine_iters": max_refine,
            "draft_content": draft,
            "scan_evidence": {},
            "verdict": "healthy" if passed else "unhealthy",
            "counts": counts or ({"critical": 0, "major": 0, "minor": 0} if passed
                                 else {"critical": 2, "major": 0, "minor": 0}),
            "issues": issues or ([] if passed else [
                {"severity": "critical", "field": "x", "message": "fail",
                 "evidence": "test", "fix_hint": "fix"}
            ]),
            "llm_notes": "test",
        }
    }


@pytest.fixture
def tmp_repo(tmp_path):
    """临时 repo · 保 src/ 真写盘观察清晰."""
    (tmp_path / "src" / "omnicompany" / "packages" / "services" / "fake_svc").mkdir(parents=True)
    return tmp_path


def test_passed_writes_to_src(tmp_repo):
    w = FinalLanderWorker(repo_root=tmp_repo)
    target = "src/omnicompany/packages/services/fake_svc"
    out = w.run(_verdict(True, target=target, draft="# good\n"))
    assert out.kind == VerdictKind.PASS
    o = out.output
    assert o["passed"] is True
    assert o["quarantined"] is False
    assert o["terminal_status"] == "passed"
    assert o["write_status"] == "written"
    landing = tmp_repo / o["landing_rel"]
    assert landing.exists()
    assert landing.read_text(encoding="utf-8") == "# good\n"
    # src 路径下
    assert "src/omnicompany" in o["landing_rel"].replace("\\", "/")
    # 不在 _quarantine
    assert "_quarantine" not in o["landing_rel"]


def test_exhausted_not_passed_goes_to_quarantine(tmp_repo):
    w = FinalLanderWorker(repo_root=tmp_repo)
    target = "src/omnicompany/packages/services/fake_svc"
    out = w.run(_verdict(False, target=target, iter_num=1, max_refine=1,
                         draft="# bad\n"))
    assert out.kind == VerdictKind.PASS    # Worker 仍 PASS · 但 quarantined=True
    o = out.output
    assert o["passed"] is False
    assert o["quarantined"] is True
    assert o["terminal_status"] == "quarantined_at_iter_1"
    assert o["write_status"] == "quarantined"
    # 落到 quarantine 区
    assert "data/services/docauthor/drafts/_quarantine/" in o["landing_rel"].replace("\\", "/")
    # src/ 不应当被写
    src_landing = tmp_repo / "src/omnicompany/packages/services/fake_svc/.omni/manifest.yaml"
    assert not src_landing.exists(), "src/ should NOT be written when quarantined"
    # quarantine 文件存在
    qpath = tmp_repo / o["landing_rel"]
    assert qpath.exists()
    # 同目录有 issues.json
    issues_path = qpath.parent / "issues.json"
    assert issues_path.exists()
    issues_data = json.loads(issues_path.read_text(encoding="utf-8"))
    assert issues_data["passed"] is False
    assert issues_data["counts"]["critical"] == 2


def test_design_passed_writes_to_src(tmp_repo):
    w = FinalLanderWorker(repo_root=tmp_repo)
    target = "src/omnicompany/packages/services/fake_svc"
    out = w.run(_verdict(True, target=target, target_type="design",
                         draft="<!-- [OMNI] -->\n# fake\n"))
    o = out.output
    assert o["passed"] is True
    assert o["quarantined"] is False
    assert o["landing_rel"].endswith("/DESIGN.md")
    landing = tmp_repo / o["landing_rel"]
    assert landing.exists()


def test_design_exhausted_goes_to_quarantine(tmp_repo):
    w = FinalLanderWorker(repo_root=tmp_repo)
    target = "src/omnicompany/packages/services/fake_svc"
    out = w.run(_verdict(False, target=target, target_type="design",
                         iter_num=1, max_refine=1, draft="<!-- bad -->\n"))
    o = out.output
    assert o["quarantined"] is True
    assert o["terminal_status"] == "quarantined_at_iter_1"
    assert "_quarantine" in o["landing_rel"]
    assert o["landing_rel"].endswith("/DESIGN.md")
    # src 没写
    assert not (tmp_repo / "src/omnicompany/packages/services/fake_svc/DESIGN.md").exists()


def test_relauncher_phase_returns_FAIL(tmp_repo):
    """iter < max 且未通过 → FinalLander FAIL · 让 Relauncher 处理."""
    w = FinalLanderWorker(repo_root=tmp_repo)
    target = "src/omnicompany/packages/services/fake_svc"
    out = w.run(_verdict(False, target=target, iter_num=0, max_refine=1))
    assert out.kind == VerdictKind.FAIL    # 不写, 不 emit
