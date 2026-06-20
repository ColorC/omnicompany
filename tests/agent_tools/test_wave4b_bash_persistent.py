"""Wave 4 续 — BashRouter 接 PersistentShellSession e2e (2026-05-05 立).

真 e2e:
  - persistent=true 走 PersistentShellSession (cd / export 跨调用持久)
  - persistent=false (默认) 走 BashBus (每次 fresh subprocess)
  - abort_event 透传 (Wave 8 集成)
  - 危险命令黑名单复用 BashBus (persistent 不绕过)
  - INPUT_SCHEMA / DESCRIPTION 含 persistent 字段
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.bash import BashRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    ToolContext,
    ToolExecutionError,
)
from omnicompany.runtime.buses import BashBus


def _bash_available() -> bool:
    if shutil.which("bash"):
        return True
    if os.name == "nt" and os.path.exists(r"C:\Program Files\Git\bin\bash.exe"):
        return True
    return False


pytestmark = pytest.mark.skipif(
    not _bash_available(),
    reason="bash not available",
)


# ═══════════════════════════════════════════════════════════════════════
# Schema / Description
# ═══════════════════════════════════════════════════════════════════════


class TestPersistentSchema:
    def test_persistent_in_input_schema(self):
        props = BashRouter.INPUT_SCHEMA["properties"]
        assert "persistent" in props
        assert props["persistent"]["type"] == "boolean"

    def test_persistent_default_false_documented(self):
        props = BashRouter.INPUT_SCHEMA["properties"]
        desc = props["persistent"]["description"]
        assert "default false" in desc.lower() or "Default false" in desc


# ═══════════════════════════════════════════════════════════════════════
# 实例构造 — BashRouter 带 BashBus
# ═══════════════════════════════════════════════════════════════════════


def _new_router(tmp_path: Path) -> BashRouter:
    """绕 SingleToolRouter __init__ bus 校验, 直接 new 一个."""
    r = BashRouter.__new__(BashRouter)
    # 手装最小状态 — bash_bus 必须有, allowed cwd 必须含 tmp_path
    r._bash_bus = BashBus(
        extra_allowed_cwd_prefixes=(str(tmp_path).lower(),),
    )
    r._bus = None
    r._executor = None
    r._persistent_session = None
    return r


# ═══════════════════════════════════════════════════════════════════════
# Wave 4 续 — persistent=true 走 PersistentShellSession
# ═══════════════════════════════════════════════════════════════════════


class TestPersistentMode:
    def test_persistent_cd_persists(self, tmp_path):
        """persistent=true 时 cd 跨调用持久."""
        (tmp_path / "child").mkdir()
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))

        # 第一次: cd 子目录
        r._execute({
            "command": "cd child",
            "persistent": True,
            "cwd": str(tmp_path),
        }, ctx)

        # 第二次: pwd 应返子目录
        out2 = r._execute({
            "command": "pwd",
            "persistent": True,
        }, ctx)
        # session_cwd hint 含 child
        assert "child" in out2
        assert "session_cwd" in out2

    def test_persistent_export_persists(self, tmp_path):
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))

        r._execute({
            "command": "export OMNI_BASH_TEST=value42",
            "persistent": True,
            "cwd": str(tmp_path),
        }, ctx)

        out = r._execute({
            "command": "echo $OMNI_BASH_TEST",
            "persistent": True,
        }, ctx)
        assert "value42" in out

    def test_session_lazy_constructed(self, tmp_path):
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))
        # 还没 persistent 调用前, session 是 None
        assert r._persistent_session is None
        # 第一次 persistent=true 调用后 session 起
        r._execute({"command": "echo hi", "persistent": True, "cwd": str(tmp_path)}, ctx)
        assert r._persistent_session is not None

    def test_non_persistent_no_session(self, tmp_path):
        """persistent=false (默认) 不应启 session."""
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))
        r._execute({"command": "echo hi", "cwd": str(tmp_path)}, ctx)
        assert r._persistent_session is None  # 仍是 None


# ═══════════════════════════════════════════════════════════════════════
# 安全 — 危险命令黑名单 persistent 模式不绕过
# ═══════════════════════════════════════════════════════════════════════


class TestPersistentSafety:
    def test_dangerous_blocked_in_persistent(self, tmp_path):
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))
        with pytest.raises(ToolExecutionError, match="dangerous pattern"):
            r._execute({
                "command": "rm -rf /",
                "persistent": True,
                "cwd": str(tmp_path),
            }, ctx)


# ═══════════════════════════════════════════════════════════════════════
# Wave 8 集成 — abort_event 透传
# ═══════════════════════════════════════════════════════════════════════


class TestPersistentAbort:
    def test_abort_kills_persistent_session_command(self, tmp_path):
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))
        ctx.abort_event = threading.Event()

        # 0.5s 触发 abort
        timer = threading.Timer(0.5, ctx.abort_event.set)
        timer.start()

        with pytest.raises(ToolExecutionError, match="ABORTED"):
            r._execute({
                "command": "sleep 60",
                "persistent": True,
                "timeout_sec": 10,
                "cwd": str(tmp_path),
            }, ctx)

        timer.cancel()


# ═══════════════════════════════════════════════════════════════════════
# 默认模式 (BashBus) 仍工作
# ═══════════════════════════════════════════════════════════════════════


class TestDefaultModeStillWorks:
    def test_default_mode_runs_via_bashbus(self, tmp_path):
        r = _new_router(tmp_path)
        ctx = ToolContext(cwd=str(tmp_path))
        out = r._execute({
            "command": "echo from_bashbus",
            "cwd": str(tmp_path),
        }, ctx)
        assert "from_bashbus" in out
        # 默认模式不含 session_cwd hint
        assert "session_cwd" not in out
