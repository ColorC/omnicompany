# [OMNI] origin=ai-ide domain=services/_core/identity ts=2026-05-02T00:00:00Z type=service status=active agent=ai-ide-current
# [OMNI] summary="trace_id 解析跟 active session 写入, hook / CLI / web 共用一份"
# [OMNI] why="不能让 cli 跟 web 各算各的 trace_id 导致同一 claude session 看到两个身份"
# [OMNI] tags=identity,resolver,session,foundation
# [OMNI] material_id="material:core.identity.session_resolver.implementation.py"
"""身份解析: 当前 claude code session 的 trace_id 从哪来.

`resolve_active_trace_id()` 是单一查询入口. 优先级链:

  OMNI_CC_TRACE_ID env   (CLI 显式 / 测试)
  > OMNI_CC_PTY_ID env   (dashboard PTY 启动 claude 时传)
  > active_file 的 trace_id  (SessionStart hook 写的)
  > cc_unknown_<ts>      (fallback warn)

`record_active_session()` 是写入入口, hook + CLI 共用.

`current_session_meta()` 返回完整元数据 (供 omni who / dashboard / 调试).
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


# active session 元数据落盘位置, 跟 cc_wrapper hook 共用
_ACTIVE_FILE_REL = "data/cc_session_active.json"


def _repo_root() -> Path:
    """跟 cc_wrapper/hooks/_shared.repo_root() 同算法 (避免反向 import dashboard)."""
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / "src" / "omnicompany").is_dir() and (d / "docs").is_dir():
            return d
    return Path(__file__).resolve().parents[6]


def _active_file() -> Path:
    return _repo_root() / _ACTIVE_FILE_REL


def _read_active() -> dict[str, Any]:
    p = _active_file()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def resolve_active_trace_id() -> str:
    """返回当前 claude code session 的 trace_id.

    解析优先级:
    1. `OMNI_CC_TRACE_ID` env (CLI 显式设 / 测试 / 脚本)
    2. `OMNI_CC_PTY_ID` env (dashboard PTY 启动 claude 时传给子进程)
    3. `data/cc_session_active.json` 里 active_trace_id (SessionStart hook 写的)
    4. fallback `cc_unknown_<unix_ts>` (warn 级缺省, 仍能跑但跟 dashboard 对不上)
    """
    explicit = os.environ.get("OMNI_CC_TRACE_ID")
    if explicit:
        return explicit
    pty_id = os.environ.get("OMNI_CC_PTY_ID")
    if pty_id:
        return pty_id
    active = _read_active()
    tid = active.get("trace_id") or active.get("active_trace_id")
    if tid:
        return tid
    return f"cc_unknown_{int(time.time())}"


def current_session_meta() -> dict[str, Any]:
    """完整 session 元数据 (供 omni who / dashboard / 调试).

    返回 dict, 字段含:
    - trace_id: 当前解析出的 trace_id
    - source: 'env_explicit' / 'env_pty' / 'active_file' / 'fallback'
    - claude_session_id: hook 抓到的 (可能 None)
    - pty_id: dashboard PTY id (可能 None)
    - active_plan: 当前 active plan 路径 (hook 抓的)
    - started_at: ISO 时间戳
    - cwd: 当前工作目录
    - active_file_path: cc_session_active.json 绝对路径
    """
    explicit = os.environ.get("OMNI_CC_TRACE_ID")
    pty_id = os.environ.get("OMNI_CC_PTY_ID")
    active = _read_active()

    if explicit:
        trace_id, source = explicit, "env_explicit"
    elif pty_id:
        trace_id, source = pty_id, "env_pty"
    elif active.get("trace_id") or active.get("active_trace_id"):
        trace_id = active.get("trace_id") or active.get("active_trace_id")
        source = "active_file"
    else:
        trace_id, source = f"cc_unknown_{int(time.time())}", "fallback"

    return {
        "trace_id": trace_id,
        "source": source,
        "claude_session_id": active.get("claude_session_id"),
        "pty_id": pty_id or active.get("pty_id"),
        "active_plan": active.get("active_plan"),
        "started_at": active.get("started_at"),
        "cwd": active.get("cwd") or os.getcwd(),
        "active_file_path": str(_active_file()),
    }


def record_active_session(
    trace_id: str,
    *,
    claude_session_id: str | None = None,
    pty_id: str | None = None,
    active_plan: str | None = None,
    cwd: str | None = None,
    source: str = "hook",
    extra: dict[str, Any] | None = None,
) -> Path:
    """写当前 session 元数据到 `data/cc_session_active.json`.

    hook + CLI 共用: SessionStart hook 调 (source='hook'), `omni session bind` CLI 调
    (source='cli_bind'). 走同一份函数, 走的逻辑一致, 只是触发方式不同.

    返回写入的文件路径.

    覆盖语义: 整文件覆盖 (不合并), 因为 active session 一份一份切, 不累积.
    """
    if not trace_id:
        raise ValueError("trace_id 不能为空")

    payload: dict[str, Any] = {
        "trace_id": trace_id,
        "claude_session_id": claude_session_id,
        "pty_id": pty_id,
        "active_plan": active_plan,
        "cwd": cwd or os.getcwd(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": source,
    }
    if extra:
        payload.update(extra)

    p = _active_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    # atomic write — 防 hook / pytest 中断时留半截文件 (历史 dogfood 时这里被 pytest 测试污染过).
    # tempfile + os.replace 在 Windows + POSIX 都 atomic (Python 3.3+).
    fd, tmp_path = tempfile.mkstemp(prefix=p.stem + ".", suffix=".tmp", dir=str(p.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, indent=2))
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return p
