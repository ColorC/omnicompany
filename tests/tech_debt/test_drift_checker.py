# [OMNI] origin=claude-code domain=services/tech_debt ts=2026-04-18T00:00:00Z
"""drift_checker + omni debt add 单测。"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omnicompany.packages.services.tech_debt.drift_checker import (  # noqa: E402
    check_design_md_drift,
    check_plan_drift,
    run_drift_audit,
    _parse_omnimark_status,
)
from omnicompany.packages.services.tech_debt.registry_io import (  # noqa: E402
    load_registry,
    append_row,
)


_REGISTRY_TEMPLATE = """<!-- [OMNI] origin=test -->

# REGISTRY

## §活跃违规（Guardian / OMNI 规则产出）

| ID | 规则ID | 路径/目标 | 级别 | 首现 | 持续扫描数 | 状态 |
|---|---|---|---|---|---|---|

---

## §语义合规待审（SemanticAuditor 产出 / 人工识别）

| ID | 标准来源 | 目标 | 疑似违规描述 | 信心 | 处置 | 状态 |
|---|---|---|---|---|---|---|

---

## §文档漂移（DESIGN.md / plan.md 未反映现状）

| ID | 类型 | 目标 | 最后代码/原始变更 | 最后文档更新 | 漂移天数 | 状态 |
|---|---|---|---|---|---|---|

---

## §计划回流欠债（archived plan → DESIGN.md 未写）

| ID | 归档 plan | 目标 DESIGN.md | 状态 |
|---|---|---|---|

---

## §能力缺口（docs/gaps/ 摘要）

| Gap | 一句话描述 | 优先级 | 状态 |
|---|---|---|---|

---

## §已解决

| ID | 类型 | 解决日期 | 解决方式 |
|---|---|---|---|
"""


@pytest.fixture
def fake_root(tmp_path):
    (tmp_path / "docs" / "tech_debt").mkdir(parents=True)
    (tmp_path / "docs" / "tech_debt" / "REGISTRY.md").write_text(
        _REGISTRY_TEMPLATE, encoding="utf-8",
    )
    return tmp_path


def _touch(path: Path, mtime_days_ago: int):
    """辅助：设置文件 mtime 为 N 天前。"""
    ts = time.time() - mtime_days_ago * 86400
    os.utime(path, (ts, ts))


# ═══ DESIGN.md 漂移 ══════════════════════════════════════════════


class TestDesignMdDrift:
    def _make_package(self, root: Path, rel: str, design_days_ago: int, code_days_ago: int):
        pkg = root / rel
        pkg.mkdir(parents=True, exist_ok=True)
        design = pkg / "DESIGN.md"
        design.write_text(
            "<!-- [OMNI] origin=x status=active -->\n# DESIGN\n",
            encoding="utf-8",
        )
        _touch(design, design_days_ago)
        code = pkg / "foo.py"
        code.write_text("# code\n", encoding="utf-8")
        _touch(code, code_days_ago)

    def test_detects_drift(self, tmp_path):
        self._make_package(tmp_path, "src/omnicompany/pkg_a", design_days_ago=30, code_days_ago=1)
        findings = check_design_md_drift(tmp_path, days_threshold=14)
        assert len(findings) == 1
        f = findings[0]
        assert f.kind == "design_md_drift"
        assert f.target.endswith("pkg_a/DESIGN.md")
        assert f.drift_days >= 14

    def test_no_drift_when_design_newer(self, tmp_path):
        self._make_package(tmp_path, "src/omnicompany/pkg_b", design_days_ago=1, code_days_ago=30)
        findings = check_design_md_drift(tmp_path, days_threshold=14)
        assert findings == []

    def test_no_drift_below_threshold(self, tmp_path):
        self._make_package(tmp_path, "src/omnicompany/pkg_c", design_days_ago=10, code_days_ago=1)
        findings = check_design_md_drift(tmp_path, days_threshold=14)
        assert findings == []

    def test_skip_graveyard(self, tmp_path):
        self._make_package(tmp_path, "src/omnicompany/_graveyard/old", design_days_ago=30, code_days_ago=1)
        findings = check_design_md_drift(tmp_path)
        assert findings == []

    def test_skip_when_no_code(self, tmp_path):
        # 只有 DESIGN.md 没 .py
        pkg = tmp_path / "src" / "omnicompany" / "pkg_d"
        pkg.mkdir(parents=True)
        (pkg / "DESIGN.md").write_text("<!-- [OMNI] -->\n", encoding="utf-8")
        _touch(pkg / "DESIGN.md", 30)
        findings = check_design_md_drift(tmp_path)
        assert findings == []


# ═══ Plan 漂移 ═══════════════════════════════════════════════════


class TestPlanDrift:
    def _make_plan(self, root: Path, dir_name: str, status: str, mtime_days_ago: int):
        pd = root / "docs" / "plans" / dir_name
        pd.mkdir(parents=True)
        pm = pd / "plan.md"
        pm.write_text(
            f"<!-- [OMNI] origin=x status={status} -->\n# plan\n",
            encoding="utf-8",
        )
        _touch(pm, mtime_days_ago)
        return pm

    def test_detects_stale_active(self, tmp_path):
        self._make_plan(tmp_path, "[2026-04-10]TEST", status="active", mtime_days_ago=20)
        findings = check_plan_drift(tmp_path, stale_threshold_days=14, old_threshold_days=180)
        stale = [f for f in findings if f.kind == "plan_stale"]
        assert len(stale) == 1
        assert stale[0].drift_days >= 14

    def test_old_plan_regardless_of_edit(self, tmp_path):
        # 目录日期很久，但刚编辑过 → 应判 plan_old（因 mtime 新）
        self._make_plan(tmp_path, "[2024-01-01]ANCIENT", status="draft", mtime_days_ago=1)
        findings = check_plan_drift(tmp_path, stale_threshold_days=14, old_threshold_days=30)
        old = [f for f in findings if f.kind == "plan_old"]
        assert len(old) == 1

    def test_archived_skipped(self, tmp_path):
        self._make_plan(tmp_path, "[2024-01-01]DONE", status="archived", mtime_days_ago=100)
        findings = check_plan_drift(tmp_path)
        assert findings == []

    def test_archive_dir_skipped(self, tmp_path):
        # docs/plans/_archive/ 下的 plan 不算
        arch = tmp_path / "docs" / "plans" / "_archive" / "[2024-01-01]X"
        arch.mkdir(parents=True)
        (arch / "plan.md").write_text("<!-- [OMNI] status=active -->\n", encoding="utf-8")
        _touch(arch / "plan.md", 100)
        findings = check_plan_drift(tmp_path)
        assert findings == []

    def test_status_parsing(self, tmp_path):
        p = tmp_path / "plan.md"
        p.write_text(
            "<!-- [OMNI] origin=x domain=y ts=z type=doc status=design -->\n",
            encoding="utf-8",
        )
        assert _parse_omnimark_status(p) == "design"

    def test_malformed_dir_skipped(self, tmp_path):
        # 没日期前缀
        bad = tmp_path / "docs" / "plans" / "no-date"
        bad.mkdir(parents=True)
        (bad / "plan.md").write_text("<!-- [OMNI] status=active -->\n", encoding="utf-8")
        _touch(bad / "plan.md", 100)
        findings = check_plan_drift(tmp_path)
        assert findings == []


# ═══ run_drift_audit（端到端）════════════════════════════════════


class TestRunAudit:
    def test_dry_run_no_write(self, fake_root):
        pkg = fake_root / "src" / "omnicompany" / "pkg_x"
        pkg.mkdir(parents=True)
        (pkg / "DESIGN.md").write_text("<!-- [OMNI] -->\n", encoding="utf-8")
        _touch(pkg / "DESIGN.md", 30)
        (pkg / "x.py").write_text("# x\n", encoding="utf-8")
        _touch(pkg / "x.py", 1)

        result = run_drift_audit(fake_root, dry_run=True)
        assert result["dry_run"] is True
        assert result["total_findings"] >= 1
        assert result["added"] == 0
        # REGISTRY 未变
        snapshot = load_registry(fake_root)
        assert len(snapshot.sections["doc_drift"]) == 0

    def test_writes_to_registry(self, fake_root):
        pkg = fake_root / "src" / "omnicompany" / "pkg_y"
        pkg.mkdir(parents=True)
        (pkg / "DESIGN.md").write_text("<!-- [OMNI] -->\n", encoding="utf-8")
        _touch(pkg / "DESIGN.md", 30)
        (pkg / "y.py").write_text("# y\n", encoding="utf-8")
        _touch(pkg / "y.py", 1)

        result = run_drift_audit(fake_root)
        assert result["added"] >= 1
        snapshot = load_registry(fake_root)
        assert len(snapshot.sections["doc_drift"]) >= 1
        row = snapshot.sections["doc_drift"][0]
        assert row.fields["kind"] == "design_md_drift"
        assert "pkg_y" in row.fields["target"]

    def test_dedup_on_repeat_scan(self, fake_root):
        pkg = fake_root / "src" / "omnicompany" / "pkg_z"
        pkg.mkdir(parents=True)
        (pkg / "DESIGN.md").write_text("<!-- [OMNI] -->\n", encoding="utf-8")
        _touch(pkg / "DESIGN.md", 30)
        (pkg / "z.py").write_text("# z\n", encoding="utf-8")
        _touch(pkg / "z.py", 1)

        r1 = run_drift_audit(fake_root)
        assert r1["added"] >= 1
        # 二跑：同 (kind, target) 已 open → 全部 deduped
        r2 = run_drift_audit(fake_root)
        assert r2["added"] == 0
        assert r2["deduped"] == r1["added"]


# ═══ append_row（通用）═══════════════════════════════════════════


class TestAppendRow:
    def test_add_to_activity(self, fake_root):
        r = append_row(
            fake_root, "activity",
            fields={"rule_id": "OMNI-TEST", "path": "src/x.py",
                    "severity": "HIGH", "first_seen": "2026-04-18",
                    "scan_count": "1"},
        )
        assert r.ok
        assert r.action == "added"
        assert r.row_id.startswith("D-")
        snapshot = load_registry(fake_root)
        assert len(snapshot.sections["activity"]) == 1

    def test_dedup_on_conflict(self, fake_root):
        fields = {"rule_id": "OMNI-X", "path": "src/y.py", "severity": "HIGH",
                  "first_seen": "2026-04-18", "scan_count": "1"}
        r1 = append_row(fake_root, "activity", fields, dedup_keys=("rule_id", "path"))
        assert r1.action == "added"
        r2 = append_row(fake_root, "activity", fields, dedup_keys=("rule_id", "path"))
        assert r2.action == "deduped"
        assert r2.row_id == r1.row_id

    def test_unknown_section(self, fake_root):
        r = append_row(fake_root, "not_a_section", {})
        assert not r.ok
        assert r.action == "error"

    def test_missing_registry(self, tmp_path):
        r = append_row(tmp_path, "activity", {"rule_id": "X"})
        assert not r.ok
        assert "不存在" in r.error


# ═══ omni debt add CLI ═══════════════════════════════════════════


class TestDebtAddCLI:
    def test_add_capability_gap(self, fake_root):
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        runner = CliRunner()
        result = runner.invoke(cmd_debt, [
            "add", "capability_gap",
            "--fields", '{"description":"autocompact 失效","priority":"P1"}',
            "--root", str(fake_root), "--json",
        ])
        assert result.exit_code == 0, result.output
        out = json.loads(result.output)
        assert out["ok"] is True
        assert out["action"] == "added"
        assert out["row_id"].startswith("G-")

    def test_add_dedup_on_duplicate(self, fake_root):
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        runner = CliRunner()
        args_base = [
            "add", "activity",
            "--fields", '{"rule_id":"OVERSEER","path":"x","severity":"HIGH"}',
            "--dedup-on", "rule_id,path",
            "--root", str(fake_root), "--json",
        ]
        r1 = runner.invoke(cmd_debt, args_base)
        r2 = runner.invoke(cmd_debt, args_base)
        assert r1.exit_code == 0
        assert r2.exit_code == 0
        out1 = json.loads(r1.output)
        out2 = json.loads(r2.output)
        assert out1["action"] == "added"
        assert out2["action"] == "deduped"
        assert out1["row_id"] == out2["row_id"]

    def test_add_bad_json(self, fake_root):
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        runner = CliRunner()
        result = runner.invoke(cmd_debt, [
            "add", "activity", "--fields", "not-json",
            "--root", str(fake_root),
        ])
        assert result.exit_code == 2

    def test_add_invalid_section(self, fake_root):
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        runner = CliRunner()
        result = runner.invoke(cmd_debt, [
            "add", "nonexistent", "--fields", "{}",
        ])
        assert result.exit_code == 2  # click 自动拒绝非法 choice


# ═══ scan --drift-only ═══════════════════════════════════════════


class TestScanDriftOnly:
    def test_drift_only_skips_guardian(self, fake_root):
        from click.testing import CliRunner
        from omnicompany.cli.commands.debt import cmd_debt
        runner = CliRunner()
        result = runner.invoke(cmd_debt, [
            "scan", "--drift-only", "--root", str(fake_root), "--json",
        ])
        assert result.exit_code == 0
        # 输出 JSON（命令头部还会打 [drift] cyan 文字，所以只看 json 部分）
        # 从 output 里找 JSON
        idx = result.output.find("{")
        out = json.loads(result.output[idx:])
        assert out["mode"] == "drift-only"
        assert out["guardian"] is None  # 跳过
        assert out["drift"] is not None
