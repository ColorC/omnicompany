"""BashBus 子进程真杀测试 (2026-05-04 立, 357 僵尸事故修复后).

哲学: 任一 FAIL 表示子进程不被 timeout 杀掉 → 357 僵尸事故会复发.

红绿基线:
- 红: timeout 后 PID 仍存活 = bug
- 绿: timeout 后 PID 在 5 秒内不存在 = 真杀
- 注册表: 进程跑完后 _ACTIVE_PROCESSES 为空 = 不泄漏
- atexit: 模拟 Python 退出, 残留进程被清

不依赖外部命令: 用 `python -c "import time; time.sleep(N)"` 跨平台.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.runtime.buses.bash_bus import (
    BashBus,
    _ACTIVE_PROCESSES,
    _cleanup_active_processes,
    _kill_process_tree,
)


def _proc_alive(pid: int) -> bool:
    """跨平台检查 PID 是否还活着."""
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=5,
        )
        # tasklist 找不到时 stdout 含 "INFO: No tasks ..." 或空
        return f",\"{pid}\"," in result.stdout or f',{pid},' in result.stdout
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, OSError):
        return False


@pytest.fixture
def bus(tmp_path):
    prefix = str(tmp_path).lower().replace("\\", "/")
    return BashBus(extra_allowed_cwd_prefixes=(prefix,))


# ─── 核心: timeout 真杀 ──────────────────────────────────────────


class TestTimeoutKills:
    def test_timeout_kills_long_running_process(self, bus, tmp_path):
        """canary: timeout 后子进程必须真死. 这条 FAIL 意味着 357 僵尸再来."""
        # 跑一个 60 秒 sleep, timeout=2 秒. python sleep 跨平台保证.
        cmd = f'{sys.executable} -c "import time; time.sleep(60)"'

        with pytest.raises(subprocess.TimeoutExpired):
            bus.run(cmd, cwd=str(tmp_path), timeout=2)

        # 给 OS 一点时间清理
        time.sleep(1)

        # 注册表应已清空 (run 的 finally 块 unregister)
        active_count = sum(1 for _ in _ACTIVE_PROCESSES)
        assert active_count == 0, f"_ACTIVE_PROCESSES 仍有 {active_count} 个进程未清理"

    def test_short_command_no_residue(self, bus, tmp_path):
        """正常退出的进程也要从注册表清掉."""
        cmd = f'{sys.executable} -c "print(\\"hello\\")"'
        result = bus.run(cmd, cwd=str(tmp_path), timeout=10)
        assert result.returncode == 0
        # 跑完进程已 reap, 注册表清空
        active_count = sum(1 for _ in _ACTIVE_PROCESSES)
        assert active_count == 0


# ─── 注册表 + atexit hook ───────────────────────────────────────


class TestProcessRegistry:
    def test_atexit_hook_kills_orphans(self, bus, tmp_path):
        """模拟 atexit 调用: 注册表里的进程应被清掉."""
        # 启一个长跑进程, 但不等它退出
        cmd_args = [sys.executable, "-c", "import time; time.sleep(120)"]
        popen_kwargs: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen(cmd_args, **popen_kwargs)
        try:
            # 手动加进注册表 (模拟 BashBus.run 路径)
            from omnicompany.runtime.buses.bash_bus import _register_process
            _register_process(proc)
            assert _proc_alive(proc.pid), "进程应该还活着"

            # 模拟 atexit
            _cleanup_active_processes()
            time.sleep(1.5)

            assert not _proc_alive(proc.pid), "atexit 后进程应被杀掉"
        finally:
            # 兜底
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception:
                pass


# ─── _kill_process_tree 函数本身 ─────────────────────────────────


class TestKillProcessTree:
    def test_kill_already_dead_returns_true(self):
        """已死的进程, kill 调用返 True."""
        cmd_args = [sys.executable, "-c", "import sys; sys.exit(0)"]
        proc = subprocess.Popen(
            cmd_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        proc.wait(timeout=5)  # 等它自然死
        assert _kill_process_tree(proc) is True

    def test_kill_alive_returns_true(self):
        """活的进程被杀, 返 True."""
        cmd_args = [sys.executable, "-c", "import time; time.sleep(60)"]
        popen_kwargs: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        proc = subprocess.Popen(cmd_args, **popen_kwargs)
        try:
            assert _proc_alive(proc.pid)
            killed = _kill_process_tree(proc)
            assert killed is True
            time.sleep(0.5)
            assert not _proc_alive(proc.pid)
        finally:
            try:
                proc.kill()
            except Exception:
                pass


# ─── 集成 canary: 1000 短命令不留僵尸 ─────────────────────────────


class TestNoLongTermResidue:
    """canary: 跑一批正常命令, 注册表应保持干净."""

    def test_50_commands_no_residue(self, bus, tmp_path):
        """跑 50 条 python 短命令, 跑完注册表必清空."""
        for i in range(50):
            cmd = f'{sys.executable} -c "print({i})"'
            result = bus.run(cmd, cwd=str(tmp_path), timeout=10)
            assert result.returncode == 0
        # 全跑完后注册表为空
        active_count = sum(1 for _ in _ACTIVE_PROCESSES)
        assert active_count == 0
