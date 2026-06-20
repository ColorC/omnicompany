# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-23T00:00:00Z type=test
"""I-19 hook installer regression tests.

锁定:
1. 无 .git → HookInstallError
2. hook absent → 装模板
3. 已装同模板 → skipped-current
4. 已装但漂移 (仍含 marker) → refreshed
5. foreign (用户自定义, 无 marker) → 默认 skip, --force 则备份后覆盖
6. 安装后 hook 可执行位置正确
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.packages.services._core.guardian.hook_installer import (
    HookInstallError,
    MANAGED_MARKER,
    PRE_COMMIT_TEMPLATE,
    POST_COMMIT_TEMPLATE,
    check_hooks,
    install_hooks,
)


def _init_fake_git(tmp_path: Path) -> Path:
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    return tmp_path


def test_no_git_raises(tmp_path: Path):
    with pytest.raises(HookInstallError):
        install_hooks(tmp_path)


def test_fresh_install_writes_templates(tmp_path: Path):
    _init_fake_git(tmp_path)
    result = install_hooks(tmp_path)
    assert result == {"pre-commit": "installed", "post-commit": "installed"}
    hooks = tmp_path / ".git" / "hooks"
    assert (hooks / "pre-commit").read_text(encoding="utf-8") == PRE_COMMIT_TEMPLATE
    assert (hooks / "post-commit").read_text(encoding="utf-8") == POST_COMMIT_TEMPLATE


def test_reinstall_is_idempotent(tmp_path: Path):
    _init_fake_git(tmp_path)
    install_hooks(tmp_path)
    result = install_hooks(tmp_path)
    assert result == {
        "pre-commit": "skipped-current",
        "post-commit": "skipped-current",
    }


def test_managed_stale_gets_refreshed(tmp_path: Path):
    _init_fake_git(tmp_path)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        f"#!/bin/sh\n{MANAGED_MARKER}\n# old version\necho stale\n",
        encoding="utf-8",
    )
    result = install_hooks(tmp_path)
    assert result["pre-commit"] == "refreshed"
    assert hook.read_text(encoding="utf-8") == PRE_COMMIT_TEMPLATE


def test_foreign_skipped_without_force(tmp_path: Path):
    _init_fake_git(tmp_path)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    user_content = "#!/bin/sh\n# user custom hook\necho hi\n"
    hook.write_text(user_content, encoding="utf-8")
    result = install_hooks(tmp_path)
    assert result["pre-commit"] == "skipped-foreign"
    # 未被覆盖
    assert hook.read_text(encoding="utf-8") == user_content


def test_foreign_replaced_with_force_backs_up(tmp_path: Path):
    _init_fake_git(tmp_path)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    user_content = "#!/bin/sh\n# user custom\necho hi\n"
    hook.write_text(user_content, encoding="utf-8")
    result = install_hooks(tmp_path, force=True)
    assert result["pre-commit"] == "replaced-foreign"
    # 覆盖成功
    assert hook.read_text(encoding="utf-8") == PRE_COMMIT_TEMPLATE
    # 有备份
    backups = list((tmp_path / ".git" / "hooks").glob("pre-commit.bak-omni-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == user_content


def test_dry_run_does_not_write(tmp_path: Path):
    _init_fake_git(tmp_path)
    result = install_hooks(tmp_path, dry_run=True)
    assert result == {"pre-commit": "installed", "post-commit": "installed"}
    assert not (tmp_path / ".git" / "hooks" / "pre-commit").exists()


def test_check_hooks_reports_absent(tmp_path: Path):
    _init_fake_git(tmp_path)
    status = check_hooks(tmp_path)
    assert status == {"pre-commit": "absent", "post-commit": "absent"}


def test_check_hooks_reports_managed_current_after_install(tmp_path: Path):
    _init_fake_git(tmp_path)
    install_hooks(tmp_path)
    status = check_hooks(tmp_path)
    assert status == {
        "pre-commit": "managed-current",
        "post-commit": "managed-current",
    }


def test_check_hooks_reports_foreign(tmp_path: Path):
    _init_fake_git(tmp_path)
    (tmp_path / ".git" / "hooks" / "pre-commit").write_text(
        "#!/bin/sh\necho custom\n", encoding="utf-8",
    )
    status = check_hooks(tmp_path)
    assert status["pre-commit"] == "foreign"


def test_check_hooks_no_git_directory(tmp_path: Path):
    status = check_hooks(tmp_path)
    assert status == {"pre-commit": "no-git", "post-commit": "no-git"}


def test_templates_contain_managed_marker():
    """模板必须含 marker, 否则 install 后自己判成 foreign."""
    assert MANAGED_MARKER in PRE_COMMIT_TEMPLATE
    assert MANAGED_MARKER in POST_COMMIT_TEMPLATE
