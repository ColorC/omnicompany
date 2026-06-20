"""工作区污染哨兵测试 (2026-05-04 立).

哲学: canary 系统健康. 任一 FAIL 表示哨兵不再保护工作区根/D 盘根免受 bash bug 产物污染.

覆盖:
  - 顶层非白名单文件/目录 → 备份后删除
  - 白名单内项 → 不动
  - Windows 设备名 (nul / con / aux 等) → 直接删 (不备份)
  - 干跑模式不真动文件
  - 罚单 jsonl append-only 落盘
  - 哨兵唤醒时调用 (通过模拟 sentinel.run_one_pass 间接验证, 这里只测扫描函数本身)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian.workspace_pollution import (
    PollutionTicket,
    scan_pollution,
    run_workspace_pollution_scan,
    _D_DRIVE_ROOT_WHITELIST,
    _WORKSPACE_ROOT_WHITELIST,
    _WINDOWS_DEVICE_NAMES,
)


# ─── 基础: 白名单常量正确性 ────────────────────────────────────────


class TestWhitelistContents:
    """canary: 白名单是否包含合法核心目录. 任一 FAIL 表示白名单漂移."""

    def test_workspace_whitelist_has_omnicompany(self):
        assert "omnicompany" in _WORKSPACE_ROOT_WHITELIST

    def test_workspace_whitelist_has_critical_dotfiles(self):
        assert ".claude" in _WORKSPACE_ROOT_WHITELIST
        assert ".omni" in _WORKSPACE_ROOT_WHITELIST

    def test_d_drive_whitelist_has_scm(self):
        assert "scm" in _D_DRIVE_ROOT_WHITELIST

    def test_d_drive_whitelist_has_recorder_trigger(self):
        """RecorderTrigger 是某录屏工具运行目录, 不是 bash bug 产物."""
        assert "RecorderTrigger" in _D_DRIVE_ROOT_WHITELIST

    def test_device_names_complete(self):
        """nul / con / aux / prn / lpt1~9 / com1~9 都要在."""
        for name in ("nul", "con", "aux", "prn"):
            assert name in _WINDOWS_DEVICE_NAMES
        for i in range(1, 10):
            assert f"lpt{i}" in _WINDOWS_DEVICE_NAMES
            assert f"com{i}" in _WINDOWS_DEVICE_NAMES


# ─── 扫描行为核心 ─────────────────────────────────────────────────


class TestScanPollutionCore:
    """canary: 扫描函数对污染必然命中, 对白名单必然放行."""

    def test_pollution_file_caught_and_removed(self, tmp_path):
        """新建一个非白名单文件 → 扫描后应被备份删除."""
        whitelist = frozenset({"keep_this.txt"})
        # 一个白名单内, 一个污染
        (tmp_path / "keep_this.txt").write_text("ok")
        (tmp_path / "pollution.tmp").write_text("garbage")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        tickets = scan_pollution(tmp_path, whitelist, omni_root=omni_root)

        # 污染被处置
        assert len(tickets) == 1
        assert tickets[0].original_path.endswith("pollution.tmp")
        # 原文件已删
        assert not (tmp_path / "pollution.tmp").exists()
        # 白名单内不动
        assert (tmp_path / "keep_this.txt").exists()
        # 备份在
        backup_path = Path(tickets[0].backup_path)
        assert backup_path.exists()
        assert backup_path.read_text() == "garbage"

    def test_pollution_dir_caught_and_removed(self, tmp_path):
        """非白名单目录 → 整目录备份后删除."""
        whitelist = frozenset()
        (tmp_path / "junk_dir").mkdir()
        (tmp_path / "junk_dir" / "inner.txt").write_text("inside")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        tickets = scan_pollution(tmp_path, whitelist, omni_root=omni_root)

        assert len(tickets) == 1
        assert tickets[0].item_type == "dir"
        assert not (tmp_path / "junk_dir").exists()
        # 备份目录结构保留
        backup = Path(tickets[0].backup_path)
        assert backup.is_dir()
        assert (backup / "inner.txt").read_text() == "inside"

    def test_dry_run_does_not_modify(self, tmp_path):
        """干跑: 报告污染但不删."""
        whitelist = frozenset()
        (tmp_path / "pollution.txt").write_text("x")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        tickets = scan_pollution(tmp_path, whitelist, dry_run=True, omni_root=omni_root)

        assert len(tickets) == 1
        # 文件仍在
        assert (tmp_path / "pollution.txt").exists()
        assert tickets[0].backup_path == "(dry-run)"

    def test_empty_whitelist_full_clean(self, tmp_path):
        """空白名单 = 全部视为污染."""
        whitelist = frozenset()
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        (tmp_path / "sub").mkdir()

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        tickets = scan_pollution(tmp_path, whitelist, omni_root=omni_root)

        assert len(tickets) == 3

    def test_full_whitelist_no_action(self, tmp_path):
        """所有项都在白名单 → 0 罚单."""
        whitelist = frozenset({"a.txt", "b.txt"})
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        tickets = scan_pollution(tmp_path, whitelist, omni_root=omni_root)

        assert len(tickets) == 0
        assert (tmp_path / "a.txt").exists()
        assert (tmp_path / "b.txt").exists()

    def test_nonexistent_scan_root_safe(self, tmp_path):
        """扫不存在的根 → 返空, 不抛异常."""
        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        tickets = scan_pollution(
            tmp_path / "nonexistent",
            frozenset(),
            omni_root=omni_root,
        )
        assert tickets == []


# ─── 罚单落盘 ──────────────────────────────────────────────────────


class TestTicketLogging:
    """canary: 罚单 jsonl append-only 落盘可查."""

    def test_tickets_jsonl_appended(self, tmp_path):
        """处置过的罚单写到 .omni/quarantine/workspace_pollution/tickets.jsonl"""
        whitelist = frozenset()
        (tmp_path / "garbage.txt").write_text("g")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        scan_pollution(tmp_path, whitelist, omni_root=omni_root)

        ticket_log = omni_root / ".omni" / "quarantine" / "workspace_pollution" / "tickets.jsonl"
        assert ticket_log.exists()
        lines = ticket_log.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert entry["original_path"].endswith("garbage.txt")
        assert entry["item_type"] == "file"
        assert "ticket_id" in entry

    def test_dry_run_does_not_write_log(self, tmp_path):
        """干跑不写 jsonl."""
        whitelist = frozenset()
        (tmp_path / "x.txt").write_text("x")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)
        scan_pollution(tmp_path, whitelist, dry_run=True, omni_root=omni_root)

        ticket_log = omni_root / ".omni" / "quarantine" / "workspace_pollution" / "tickets.jsonl"
        assert not ticket_log.exists()


# ─── 多目标编排 ───────────────────────────────────────────────────


class TestRunFullScan:
    """canary: 多个扫描目标编排."""

    def test_multi_target_scan(self, tmp_path):
        """两个独立扫描根, 各有自己的白名单."""
        root_a = tmp_path / "root_a"
        root_a.mkdir()
        (root_a / "ok.txt").write_text("ok")
        (root_a / "bad.txt").write_text("bad")

        root_b = tmp_path / "root_b"
        root_b.mkdir()
        (root_b / "evil.bin").write_text("evil")

        # omni_root 必须在扫描范围外, 否则它本身会被当污染
        omni_root = tmp_path.parent / f"omni_proj_{tmp_path.name}"
        omni_root.mkdir(exist_ok=True)

        targets = (
            ("root_a", root_a, frozenset({"ok.txt"})),
            ("root_b", root_b, frozenset()),
        )
        result = run_workspace_pollution_scan(targets=targets, omni_root=omni_root)

        assert result["total_tickets"] == 2
        assert result["by_root"]["root_a"] == 1
        assert result["by_root"]["root_b"] == 1
        # ok.txt 留, 其他全清
        assert (root_a / "ok.txt").exists()
        assert not (root_a / "bad.txt").exists()
        assert not (root_b / "evil.bin").exists()


# ─── canary: 集成到哨兵唤醒流程 ──────────────────────────────────


class TestSentinelIntegration:
    """canary: 哨兵 run_one_pass 调用了污染清理.

    FAIL 意味着 sentinel.py 接通点被回退或破坏, 哨兵不再扫工作区污染.
    """

    def test_sentinel_imports_pollution_module(self):
        """sentinel.py 必须能 import workspace_pollution 模块."""
        from omnicompany.packages.services._core.guardian import sentinel
        # 看源码里有没有引用
        sentinel_src = Path(sentinel.__file__).read_text(encoding="utf-8")
        assert "from .workspace_pollution import run_workspace_pollution_scan" in sentinel_src, (
            "sentinel.py 缺少 workspace_pollution 接通点 (run_one_pass 未集成)"
        )
