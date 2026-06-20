# [OMNI] origin=claude-code domain=tests/buses ts=2026-04-23T00:00:00Z type=test
"""runtime.buses smoke test · 四条业务 bus + 基类基本可用."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from omnicompany.runtime.buses import (
    BashBus,
    BusRejection,
    DiskBus,
    HumanBus,
    HumanKind,
    WebBus,
    Workspace,
)
from omnicompany.runtime.buses.human_bus import QuestionStatus


@pytest.fixture
def tmp_audit(tmp_path: Path) -> Path:
    return tmp_path / "audit.jsonl"


# ---------- DiskBus ----------


def test_disk_bus_write_and_audit(tmp_audit: Path, tmp_path: Path):
    extra_prefixes = (str(tmp_path).lower(),)
    bus = DiskBus(audit_log_path=tmp_audit, extra_allowed_prefixes=extra_prefixes)
    target = tmp_path / "hello.txt"
    bus.write(target, "world", atomic=True)
    assert target.read_text() == "world"
    records = bus.audit_tail()
    assert any(r.action == "write" and r.ok for r in records)


def test_disk_bus_rejects_system_path(tmp_audit: Path):
    bus = DiskBus(audit_log_path=tmp_audit)
    with pytest.raises(BusRejection) as exc:
        bus.write("C:/Windows/forbidden.txt", "x")
    assert "system-sensitive" in exc.value.reason.lower()


def test_disk_bus_rejects_unknown_workspace(tmp_audit: Path):
    bus = DiskBus(audit_log_path=tmp_audit)
    with pytest.raises(BusRejection) as exc:
        bus.write("F:/random_disk/test.txt", "x")
    assert "outside known workspaces" in exc.value.reason.lower()


def test_disk_bus_append(tmp_audit: Path, tmp_path: Path):
    bus = DiskBus(audit_log_path=tmp_audit, extra_allowed_prefixes=(str(tmp_path).lower(),))
    target = tmp_path / "log.jsonl"
    bus.append(target, '{"a": 1}\n')
    bus.append(target, '{"a": 2}\n')
    assert target.read_text().count("\n") == 2


# ---------- Workspace ----------


def test_disk_bus_workspace_allows_write(tmp_audit: Path, tmp_path: Path):
    # workspace 声明: 仅允许写入 tmp_path/allowed/
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    ws = Workspace(
        name="test_ws",
        write_prefixes=(str(allowed),),
    )
    bus = DiskBus(audit_log_path=tmp_audit, workspace=ws)
    # 允许
    bus.write(allowed / "ok.txt", "x")
    # 拒绝 (在 tmp_path 下但不在 allowed 子目录)
    with pytest.raises(BusRejection) as exc:
        bus.write(tmp_path / "forbidden.txt", "x")
    assert "workspace" in exc.value.reason.lower()


def test_disk_bus_workspace_overrides_extra_prefixes(tmp_audit: Path, tmp_path: Path):
    """声明 workspace 时, extra_allowed_prefixes 被忽略 (workspace 优先)."""
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    ws = Workspace(name="test_ws", write_prefixes=(str(allowed),))
    bus = DiskBus(
        audit_log_path=tmp_audit,
        workspace=ws,
        extra_allowed_prefixes=(str(other).lower(),),
    )
    # workspace 允许
    bus.write(allowed / "ok.txt", "x")
    # extra_prefixes 声明但 workspace 不允许 → 拒
    with pytest.raises(BusRejection):
        bus.write(other / "no.txt", "x")


def test_disk_bus_workspace_still_rejects_system(tmp_audit: Path):
    """即使 workspace 声明也不能写系统敏感目录 (系统黑名单硬覆盖)."""
    ws = Workspace(name="bad_ws", write_prefixes=("c:/windows/",))
    bus = DiskBus(audit_log_path=tmp_audit, workspace=ws)
    with pytest.raises(BusRejection) as exc:
        bus.write("c:/windows/malicious.txt", "x")
    assert "system-sensitive" in exc.value.reason.lower()


def test_bash_bus_workspace_cwd(tmp_audit: Path, tmp_path: Path):
    """BashBus 用 workspace.bash_cwd_prefixes 限 cwd."""
    ws = Workspace(
        name="test_ws",
        bash_cwd_prefixes=(str(tmp_path),),
    )
    bus = BashBus(audit_log_path=tmp_audit, workspace=ws)
    # cwd 在允许范围
    result = bus.run(["python", "--version"], cwd=tmp_path, timeout=10)
    assert result.returncode == 0
    # cwd 超出范围
    with pytest.raises(BusRejection) as exc:
        bus.run(["python", "--version"], cwd="C:/", timeout=10)
    assert "workspace" in exc.value.reason.lower()


def test_workspace_for_package_helper():
    """for_package 便捷构造 workspace."""
    from omnicompany.runtime.buses import for_package

    ws = for_package("packages/services/team_builder")
    assert ws.name == "team_builder"
    # 至少有 2 个写入前缀 (src + data)
    assert len(ws.write_prefixes) >= 2
    # bash cwd 至少能跑项目根
    assert len(ws.bash_cwd_prefixes) >= 1


# ---------- WebBus ----------


def test_web_bus_precheck_accepts_http(tmp_audit: Path):
    bus = WebBus(audit_log_path=tmp_audit)
    # 不抛
    bus.precheck_url("https://api.openai.com/v1/chat/completions", "POST")
    bus.precheck_url("http://localhost:8080/test", "GET")


def test_web_bus_precheck_rejects_invalid(tmp_audit: Path):
    bus = WebBus(audit_log_path=tmp_audit)
    with pytest.raises(BusRejection):
        bus.precheck_url("ftp://example.com/file", "GET")
    with pytest.raises(BusRejection):
        bus.precheck_url("", "GET")


def test_web_bus_audit_correlation(tmp_audit: Path):
    bus = WebBus(audit_log_path=tmp_audit)
    cid = bus.audit_request("https://api.openai.com/v1/models", "GET", payload_size=0)
    bus.audit_response(cid, status=200, body_size=1024, elapsed_ms=120.5)
    records = bus.audit_tail()
    assert any(r.action == "request" for r in records)
    assert any(r.action == "response" for r in records)


def test_web_bus_whitelist_enforcement(tmp_audit: Path):
    bus = WebBus(audit_log_path=tmp_audit, enforce_host_whitelist=True)
    # 允许 (精确 host)
    bus.precheck_url("http://localhost:8080/test", "GET")
    # 允许 (后缀匹配)
    bus.precheck_url("https://api.openai.com/v1/models", "GET")
    bus.precheck_url("https://api.some-tenant.feishu.cn/x", "GET")
    bus.precheck_url("https://raw.githubusercontent.com/a/b/c", "GET")
    # 拒绝
    with pytest.raises(BusRejection):
        bus.precheck_url("https://evil.example.com/pwn", "POST")


# ---------- BashBus ----------


def test_bash_bus_run_simple(tmp_audit: Path):
    bus = BashBus(audit_log_path=tmp_audit)
    # Windows/Unix 通用的命令: python --version
    result = bus.run(["python", "--version"], timeout=10)
    assert result.returncode == 0
    records = bus.audit_tail()
    assert any(r.action == "exec" and r.ok for r in records)


def test_bash_bus_rejects_dangerous(tmp_audit: Path):
    bus = BashBus(audit_log_path=tmp_audit)
    with pytest.raises(BusRejection) as exc:
        bus.run("rm -rf /", shell=True)
    assert "dangerous" in exc.value.reason.lower()


def test_bash_bus_rejects_format_c(tmp_audit: Path):
    bus = BashBus(audit_log_path=tmp_audit)
    with pytest.raises(BusRejection):
        bus.run("format C:", shell=True)


def test_bash_bus_rejects_bad_cwd(tmp_audit: Path):
    bus = BashBus(audit_log_path=tmp_audit)
    with pytest.raises(BusRejection):
        bus.run(["echo", "hi"], cwd="F:/nowhere")


def test_bash_bus_dry_run(tmp_audit: Path):
    bus = BashBus(audit_log_path=tmp_audit)
    result = bus.run(["python", "-c", "print('should not run')"], dry_run=True)
    assert result.returncode == 0
    assert "[dry-run]" in result.stderr


# ---------- HumanBus ----------


def test_human_bus_auto_continue(tmp_audit: Path, tmp_path: Path):
    bus = HumanBus(audit_log_path=tmp_audit, inbox_path=tmp_path / "inbox.db")
    q = bus.ask(
        "Accept LLM response?",
        kind=HumanKind.AUTO_CONTINUE,
        default="yes",
        source="smoke",
    )
    assert q.status == QuestionStatus.DEFAULT_APPLIED
    assert q.answer == "yes"


def test_human_bus_auto_continue_requires_default(tmp_audit: Path, tmp_path: Path):
    bus = HumanBus(audit_log_path=tmp_audit, inbox_path=tmp_path / "inbox.db")
    with pytest.raises(BusRejection):
        bus.ask("no default provided", kind=HumanKind.AUTO_CONTINUE)


def test_human_bus_blocking_enters_inbox(tmp_audit: Path, tmp_path: Path):
    bus = HumanBus(audit_log_path=tmp_audit, inbox_path=tmp_path / "inbox.db")
    q = bus.ask(
        "Unknown change, proceed?",
        kind=HumanKind.HUMAN_BLOCKING,
        source="absorption",
        context={"file": "foo.py"},
    )
    assert q.status == QuestionStatus.PENDING
    inbox = bus.inbox()
    assert any(item.id == q.id for item in inbox)


def test_human_bus_resolve(tmp_audit: Path, tmp_path: Path):
    bus = HumanBus(audit_log_path=tmp_audit, inbox_path=tmp_path / "inbox.db")
    q = bus.ask("ok?", kind=HumanKind.HUMAN_BLOCKING, source="test")
    resolved = bus.resolve(q.id, "no")
    assert resolved.status == QuestionStatus.RESOLVED
    assert resolved.answer == "no"
    # 不能 resolve 两次
    with pytest.raises(BusRejection):
        bus.resolve(q.id, "yes again")


def test_human_bus_core_diagnose(tmp_audit: Path, tmp_path: Path):
    bus = HumanBus(audit_log_path=tmp_audit, inbox_path=tmp_path / "inbox.db")
    q = bus.ask(
        "DB lock timeout",
        kind=HumanKind.CORE_DIAGNOSE,
        source="team_runner",
    )
    assert q.status == QuestionStatus.PENDING
    assert q.kind == HumanKind.CORE_DIAGNOSE
    # 可以按 kind 过滤
    diag_only = bus.inbox(kind=HumanKind.CORE_DIAGNOSE)
    assert len(diag_only) == 1


def test_human_bus_expire(tmp_audit: Path, tmp_path: Path):
    import time as _time

    bus = HumanBus(audit_log_path=tmp_audit, inbox_path=tmp_path / "inbox.db")
    q = bus.ask("expire me", kind=HumanKind.HUMAN_BLOCKING, source="test")
    # 强制把 created_at 改到古代
    with bus._conn() as conn:
        conn.execute(
            "UPDATE questions SET created_at = ? WHERE id = ?",
            (_time.time() - 10 * 86400, q.id),
        )
    count = bus.expire_old(older_than_seconds=7 * 86400)
    assert count == 1
    got = bus.get(q.id)
    assert got is not None
    assert got.status == QuestionStatus.EXPIRED
