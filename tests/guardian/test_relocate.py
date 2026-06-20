"""OmniTow.relocate + relocate_judge 单元测试 (2026-04-28).

覆盖三路径:
  1. 豁免命中 → 仅 warn, 不 mv (D1 D3 铁律)
  2. 信心 ≥ 0.8 → mv 文件, 罚单 resolved
  3. 信心 < 0.8 / LLM 失败 → 降级 quarantine

干跑模式 (OMNI_GUARDIAN_DRY_RUN=1):
  - relocate_judge 返 mock decision (target_path, confidence=0.5, ...)
  - tow_truck 信心 < 0.8 自动降级 quarantine, 不真 mv
  → 因此干跑 smoke 走"降级 quarantine"路径 (而非真 mv)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian.relocate_judge import (
    RelocateDecision,
    judge_relocate_target,
    _parse_decision,
)
from omnicompany.packages.services._core.guardian.tow_truck import OmniTow, Ticket


# ─── relocate_judge 单元测试 ────────────────────────────────────


class TestRelocateJudgeDryRun:
    def test_dry_run_returns_mock(self, monkeypatch):
        monkeypatch.setenv("OMNI_GUARDIAN_DRY_RUN", "1")
        d = judge_relocate_target(
            path="docs/plans/x/foo.py",
            content="import torch",
            rule_id="OMNI-035g",
            rule_message="docs/ 禁 .py",
        )
        assert d is not None
        assert d.target_path.startswith("data/_workspaces/dry-run/")
        assert d.confidence == 0.5
        assert "dry-run" in d.model.lower()


class TestParseDecision:
    def test_valid_json(self):
        text = '{"target_path": "data/_workspaces/x/foo.py", "confidence": 0.9, "reason": "import torch 训练脚本"}'
        d = _parse_decision(text)
        assert d is not None
        assert d.target_path == "data/_workspaces/x/foo.py"
        assert d.confidence == 0.9

    def test_with_markdown_fence(self):
        text = '```json\n{"target_path": "data/x.py", "confidence": 0.8, "reason": "ok"}\n```'
        d = _parse_decision(text)
        assert d is not None
        assert d.target_path == "data/x.py"

    def test_missing_target_path_returns_none(self):
        text = '{"confidence": 0.9, "reason": "ok"}'
        assert _parse_decision(text) is None

    def test_invalid_confidence_returns_none(self):
        text = '{"target_path": "x", "confidence": "not_a_number", "reason": "ok"}'
        assert _parse_decision(text) is None

    def test_confidence_out_of_range_returns_none(self):
        text = '{"target_path": "x", "confidence": 1.5, "reason": "ok"}'
        assert _parse_decision(text) is None

    def test_normalize_backslash(self):
        text = '{"target_path": "data\\\\x.py", "confidence": 0.9, "reason": "ok"}'
        d = _parse_decision(text)
        assert d is not None
        assert "/" in d.target_path
        assert "\\" not in d.target_path

    def test_invalid_json_returns_none(self):
        assert _parse_decision("not json at all") is None


# ─── OmniTow.relocate 路径测试 ────────────────────────────────────


@pytest.fixture
def fake_root(tmp_path):
    """给一个干净的临时项目根, 内含 .omni/ 目录."""
    (tmp_path / ".omni").mkdir()
    (tmp_path / ".omni" / "guardian").mkdir()
    return tmp_path


@pytest.fixture
def fake_violation_file(fake_root):
    """造一个 docs/plans/[2026-04-28]TEST/foo.py 违规文件."""
    plan_dir = fake_root / "docs" / "plans" / "[2026-04-28]TEST"
    plan_dir.mkdir(parents=True)
    f = plan_dir / "foo.py"
    f.write_text("import os\nprint('hello')\n", encoding="utf-8")
    return "docs/plans/[2026-04-28]TEST/foo.py"


def make_violation(path: str, rule_id: str = "OMNI-035g") -> dict:
    return {
        "ticket_id": "T-TEST-001",
        "rule_id": rule_id,
        "severity": "HIGH",
        "path": path,
        "message": "测试用违规",
        "disposition": ["relocate"],
    }


class TestRelocateWhitelistFastPath:
    def test_whitelisted_skip_relocate(self, fake_root, fake_violation_file, monkeypatch):
        """命中豁免 → 仅 warn, 不 mv, recommended_action 标'存量豁免'."""
        # 写一条豁免覆盖该路径
        from omnicompany.packages.services._core.guardian.hygiene_whitelist import (
            add_whitelist_entry,
        )
        add_whitelist_entry(
            fake_root, "OMNI-035g",
            "docs/plans/[2026-04-28]TEST/*",
            reason="测试豁免", added_by="test",
            expires="2026-12-31",
        )

        tow = OmniTow(project_root=fake_root)
        v = make_violation(fake_violation_file)
        ticket = tow.process(v)

        # 文件未被挪动
        assert (fake_root / fake_violation_file).exists()
        # recommended_action 提到豁免
        assert "豁免" in ticket.recommended_action


class TestRelocateDryRunPath:
    def test_dry_run_low_conf_falls_to_quarantine_phase2(
        self, fake_root, fake_violation_file, monkeypatch
    ):
        """干跑模式: judge 返 confidence=0.5 < 0.8 → 降级 quarantine.

        Phase 2 未启用 → quarantine 跳过, 仅记日志, 文件原地未动.
        """
        monkeypatch.setenv("OMNI_GUARDIAN_DRY_RUN", "1")
        tow = OmniTow(project_root=fake_root, phase2=False)
        v = make_violation(fake_violation_file)
        ticket = tow.process(v)

        # 文件未挪 (Phase 2 未启)
        assert (fake_root / fake_violation_file).exists()
        # recommended_action 提到信心或降级
        rec = ticket.recommended_action.lower()
        assert "0.50" in rec or "降级" in ticket.recommended_action or "quarantine" in rec


class TestRelocateMockHighConf:
    def test_mock_high_confidence_real_mv(
        self, fake_root, fake_violation_file, monkeypatch
    ):
        """mock judge_relocate_target 返高信心 → 真 mv, 罚单 resolved."""
        from omnicompany.packages.services._core.guardian import tow_truck as tt_mod

        # mock judge_relocate_target
        def fake_judge(path, content, rule_id, rule_message):
            return RelocateDecision(
                target_path="data/_workspaces/test/scripts/foo.py",
                confidence=0.95,
                reason="测试 mock 高信心",
                model="mock",
            )

        # 注入到 relocate_judge 模块 (因为 tow_truck 内部 from .relocate_judge import judge_relocate_target)
        import omnicompany.packages.services._core.guardian.relocate_judge as rj_mod
        monkeypatch.setattr(rj_mod, "judge_relocate_target", fake_judge)

        # 也 patch 拖车 _do_relocate 内部的 import 引用 (Python re-import 时按名字查模块表)
        monkeypatch.setattr(
            "omnicompany.packages.services._core.guardian.relocate_judge.judge_relocate_target",
            fake_judge,
        )

        tow = OmniTow(project_root=fake_root)
        v = make_violation(fake_violation_file)
        ticket = tow.process(v)

        # 原文件已挪
        src = fake_root / fake_violation_file
        target = fake_root / "data/_workspaces/test/scripts/foo.py"
        assert not src.exists(), "原路径仍存在"
        assert target.exists(), "目标路径不存在"
        assert ticket.status == "resolved"
        assert "relocate" in ticket.recommended_action.lower()


# 注: disposition 进阶 / Literal 字面量 / 规则注册 之类的 echo 类断言已移到
# test_canary_violations.py 的 TestCanaryRulesRegistration (端到端 canary 视角).
# 这里只保留三路径分支 + JSON 解析容错 (有真分辨力的逻辑/边界).
