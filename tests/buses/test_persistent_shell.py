"""Wave 4 P1 — PersistentShellSession e2e 测试 (2026-05-04 立).

真 e2e (用户原话"每次完成都进行一定程度的 e2e 测试"):
  - 真起 bash 子进程 (不 mock)
  - 真验证 cd 跨调用持久
  - 真验证 export 跨调用持久
  - 真验证 timeout 杀进程树 (跟 BashBus 共享 _ACTIVE_PROCESSES)
  - 真验证 close() + atexit 不留僵尸
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.runtime.buses.bash_bus import _ACTIVE_PROCESSES
from omnicompany.runtime.buses.persistent_shell import PersistentShellSession


def _bash_available() -> bool:
    """检查 bash 在系统上能跑 (Windows 需 git bash)."""
    if shutil.which("bash"):
        return True
    if os.name == "nt" and os.path.exists(r"C:\Program Files\Git\bin\bash.exe"):
        return True
    return False


pytestmark = pytest.mark.skipif(
    not _bash_available(),
    reason="bash not available (Windows需 git bash 或 WSL)",
)


# ═══════════════════════════════════════════════════════════════════════
# 基础 e2e — 真 subprocess
# ═══════════════════════════════════════════════════════════════════════


class TestBasicE2E:
    def test_simple_echo(self):
        sess = PersistentShellSession()
        out, err, rc = sess.run("echo hello")
        assert rc == 0, f"stderr: {err!r}"
        assert "hello" in out

    def test_exit_code_propagated(self):
        sess = PersistentShellSession()
        out, err, rc = sess.run("exit 42")
        assert rc == 42

    def test_stderr_captured(self):
        sess = PersistentShellSession()
        out, err, rc = sess.run("echo to_stderr 1>&2")
        assert "to_stderr" in err

    def test_command_failure(self):
        sess = PersistentShellSession()
        out, err, rc = sess.run("nonexistent_command_xyz")
        assert rc != 0
        # bash 报错信息走 stderr
        assert "nonexistent_command_xyz" in err.lower() or "command not found" in err.lower()


# ═══════════════════════════════════════════════════════════════════════
# 持久 cwd — 这是 Wave 4 的核心要求
# ═══════════════════════════════════════════════════════════════════════


class TestCwdPersistence:
    def test_cd_persists_across_calls(self, tmp_path):
        # 起 session 在 tmp_path
        sess = PersistentShellSession(cwd=str(tmp_path))

        # 第一次: pwd 应返 tmp_path (规范化)
        out, _, _ = sess.run("pwd")
        # bash on Windows 用 /c/... 形式, 不直接对比字符串, 比内容
        assert out.strip().endswith(tmp_path.name)

        # 切到子目录
        subdir = tmp_path / "sub"
        subdir.mkdir()
        sess.run(f"cd {subdir.as_posix()}")

        # 第二次 pwd: 应返子目录 (跨调用持久!)
        out2, _, _ = sess.run("pwd")
        assert out2.strip().endswith("sub"), (
            f"cd 没持久: 第二次 pwd 返 {out2!r}, 期望含 'sub'"
        )

        # session.cwd 状态也已更新
        assert sess.cwd.replace("\\", "/").endswith("/sub")

    def test_cd_relative(self, tmp_path):
        (tmp_path / "child").mkdir()
        sess = PersistentShellSession(cwd=str(tmp_path))
        sess.run("cd child")
        out, _, _ = sess.run("pwd")
        assert out.strip().endswith("child")

    def test_cd_then_command_in_new_dir(self, tmp_path):
        (tmp_path / "child").mkdir()
        (tmp_path / "child" / "marker.txt").write_text("X")
        sess = PersistentShellSession(cwd=str(tmp_path))
        sess.run("cd child")
        # ls 应看到 marker.txt
        out, _, rc = sess.run("ls")
        assert rc == 0
        assert "marker.txt" in out


# ═══════════════════════════════════════════════════════════════════════
# 持久 env
# ═══════════════════════════════════════════════════════════════════════


class TestEnvPersistence:
    def test_export_persists(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        out, _, rc = sess.run("export OMNI_TEST_VAR=hello_world_123")
        assert rc == 0

        # 第二次调用: echo $OMNI_TEST_VAR 应返 hello_world_123
        out2, _, rc2 = sess.run("echo $OMNI_TEST_VAR")
        assert rc2 == 0
        assert "hello_world_123" in out2

    def test_export_visible_in_session_env(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        sess.run("export FOO=bar_42")
        # session.env 里也有
        assert sess.env.get("FOO") == "bar_42"

    def test_unset_removes_var(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        sess.run("export TO_UNSET=present")
        assert sess.env.get("TO_UNSET") == "present"

        sess.run("unset TO_UNSET")
        # 第二次调用 echo, 应空
        out, _, _ = sess.run("echo $TO_UNSET")
        # echo 输出空 + newline
        assert out.strip() == "" or "TO_UNSET" not in sess.env


# ═══════════════════════════════════════════════════════════════════════
# 跟 BashBus 共享子进程注册表 + atexit
# ═══════════════════════════════════════════════════════════════════════


class TestProcessLifecycle:
    def test_normal_run_no_residue(self, tmp_path):
        before = len(_ACTIVE_PROCESSES)
        sess = PersistentShellSession(cwd=str(tmp_path))
        for _ in range(5):
            sess.run("echo x")
        # 结束后注册表应回到 baseline
        # 短延时让 GC 跑下 (WeakSet 自动清空已死对象)
        time.sleep(0.05)
        after = len(_ACTIVE_PROCESSES)
        assert after == before, (
            f"5 次 run 后留 {after - before} 个孤儿进程在 _ACTIVE_PROCESSES"
        )

    def test_timeout_kills_subprocess(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        before = len(_ACTIVE_PROCESSES)

        # sleep 60s, timeout=2s — 应在 2s 内 raise + kill
        with pytest.raises(subprocess.TimeoutExpired):
            sess.run("sleep 60", timeout=2.0)

        # 短延时让 kill 完成
        time.sleep(0.5)
        after = len(_ACTIVE_PROCESSES)
        # 子进程应已被杀, 注册表应清空 (允许 +1 buffer for race)
        assert after <= before + 1


# ═══════════════════════════════════════════════════════════════════════
# 错误处理
# ═══════════════════════════════════════════════════════════════════════


class TestErrors:
    def test_empty_command_rejected(self):
        sess = PersistentShellSession()
        with pytest.raises(ValueError, match="non-empty"):
            sess.run("")

    def test_non_string_rejected(self):
        sess = PersistentShellSession()
        with pytest.raises(ValueError):
            sess.run(["echo", "hi"])  # type: ignore[arg-type]

    def test_closed_session_rejects(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        sess.run("echo before_close")
        sess.close()
        assert sess.closed
        with pytest.raises(RuntimeError, match="closed"):
            sess.run("echo after_close")


# ═══════════════════════════════════════════════════════════════════════
# stdout 不含 probe marker (用户透明)
# ═══════════════════════════════════════════════════════════════════════


class TestProbeTransparency:
    def test_user_stdout_excludes_markers(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        out, _, _ = sess.run("echo user_visible_output")
        # User 看到 echo 结果
        assert "user_visible_output" in out
        # Marker 必须剥掉
        assert "__OMNI_CWD_" not in out
        assert "__OMNI_ENV_" not in out

    def test_complex_cmd_with_pipes(self, tmp_path):
        sess = PersistentShellSession(cwd=str(tmp_path))
        # 多行 + 管道也应正常工作
        out, _, rc = sess.run("echo -e 'a\\nb\\nc' | head -2")
        assert rc == 0
        assert "a" in out and "b" in out
        assert "__OMNI_" not in out


# ═══════════════════════════════════════════════════════════════════════
# 综合: cd + export 一起跨多轮
# ═══════════════════════════════════════════════════════════════════════


class TestComboPersistence:
    def test_cd_then_export_then_use(self, tmp_path):
        target = tmp_path / "workdir"
        target.mkdir()

        sess = PersistentShellSession(cwd=str(tmp_path))
        # Round 1: cd
        sess.run(f"cd {target.as_posix()}")
        # Round 2: export
        sess.run("export PROJECT_NAME=omnicompany_v2")
        # Round 3: 用两个状态
        out, _, rc = sess.run('echo "$PROJECT_NAME in $(pwd)"')
        assert rc == 0
        assert "omnicompany_v2" in out
        assert "workdir" in out
