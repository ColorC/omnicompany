# [OMNI] origin=ai-ide ts=2026-05-09 type=test
# [OMNI] material_id="material:tests.dashboard.ccdaemon_log_rotation.unit_test.py"
"""ccdaemon log rotation 单元测试 (阶段 9 exit_criteria 8).

跟 lifecycle.rotate_log_if_oversize 配套. 验证:
- size <= max_bytes 时不滚动
- size > max_bytes 时滚动: .log → .log.1, .log.1 → .log.2, ..., 最老 .log.<N> 删
- backup_count 上限有效
- 文件不存在时返 False
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.dashboard.ccdaemon import lifecycle


@pytest.fixture
def temp_log(monkeypatch, tmp_path):
    """重定向 lifecycle.log_file 到临时目录, 不污染真 data/."""
    fake_log = tmp_path / "cc_daemon.log"
    monkeypatch.setattr(lifecycle, "log_file", lambda: fake_log)
    return fake_log


def test_rotate_no_file(temp_log):
    """File 不存在 — 返 False, 不报错."""
    assert not temp_log.exists()
    assert lifecycle.rotate_log_if_oversize() is False


def test_rotate_under_threshold(temp_log):
    """Size <= max_bytes — 不滚, 文件不动."""
    temp_log.write_bytes(b"x" * 1024)  # 1KB
    assert lifecycle.rotate_log_if_oversize(max_bytes=10 * 1024 * 1024) is False
    assert temp_log.read_bytes() == b"x" * 1024
    # 没创建 .log.1
    assert not (temp_log.parent / "cc_daemon.log.1").exists()


def test_rotate_above_threshold_first_time(temp_log):
    """Size > max_bytes — 滚动, .log → .log.1, .log 重新空."""
    temp_log.write_bytes(b"a" * 2048)
    rotated = lifecycle.rotate_log_if_oversize(max_bytes=1024)
    assert rotated is True
    # .log 现在是空 (新建)
    assert temp_log.exists()
    assert temp_log.stat().st_size == 0
    # .log.1 含原内容
    log1 = temp_log.parent / "cc_daemon.log.1"
    assert log1.exists()
    assert log1.read_bytes() == b"a" * 2048


def test_rotate_chain_preserves_old_backups(temp_log):
    """三轮滚动 → .log.1 .log.2 .log.3 都按时间倒序保留, 内容对得上."""
    # 第 1 轮
    temp_log.write_bytes(b"R1" * 1000)
    lifecycle.rotate_log_if_oversize(max_bytes=512)
    # 第 2 轮 (新写)
    temp_log.write_bytes(b"R2" * 1000)
    lifecycle.rotate_log_if_oversize(max_bytes=512)
    # 第 3 轮
    temp_log.write_bytes(b"R3" * 1000)
    lifecycle.rotate_log_if_oversize(max_bytes=512)

    # 现在: .log = empty, .log.1 = R3, .log.2 = R2, .log.3 = R1
    assert (temp_log.parent / "cc_daemon.log.1").read_bytes() == b"R3" * 1000
    assert (temp_log.parent / "cc_daemon.log.2").read_bytes() == b"R2" * 1000
    assert (temp_log.parent / "cc_daemon.log.3").read_bytes() == b"R1" * 1000


def test_rotate_drops_oldest_at_backup_count(temp_log):
    """滚 6 次 (backup_count=5 默认), 最老的 R1 应当被丢."""
    for i in range(1, 7):
        temp_log.write_bytes(f"R{i}".encode() * 1000)
        lifecycle.rotate_log_if_oversize(max_bytes=512, backup_count=5)

    # 现在: .log.1 = R6, .log.2 = R5, .log.3 = R4, .log.4 = R3, .log.5 = R2; R1 丢
    assert (temp_log.parent / "cc_daemon.log.1").read_bytes().startswith(b"R6")
    assert (temp_log.parent / "cc_daemon.log.5").read_bytes().startswith(b"R2")
    # .log.6 不该存在
    assert not (temp_log.parent / "cc_daemon.log.6").exists()


def test_rotate_returns_correct_bool(temp_log):
    """返回值: True = 真滚, False = 没滚."""
    # 没滚情况
    temp_log.write_bytes(b"x" * 100)
    assert lifecycle.rotate_log_if_oversize(max_bytes=1024) is False

    # 真滚情况
    temp_log.write_bytes(b"x" * 5000)
    assert lifecycle.rotate_log_if_oversize(max_bytes=1024) is True
    # 滚后再调 — 当前 .log 是空, 不应再滚
    assert lifecycle.rotate_log_if_oversize(max_bytes=1024) is False
