# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-23T00:00:00Z type=test
"""OMNI-040 Stage 3 Clean Migration completeness regression tests.

锁定 S-01 (2026-04-23) 修复:
1. AST 检测覆盖单点/双点/三点相对 import + 绝对 import
2. 不误判 docstring / 注释 / 字符串字面量里的示例代码
3. 豁免 `_archive/` 内部文件
4. 范围扩到 services/<svc>/ 下任何 .py (含顶层 routers.py / 子包)
"""
from __future__ import annotations

from omnicompany.packages.services.guardian.rules._base import FileContext
from omnicompany.packages.services.guardian.rules.stage3_completeness import (
    _check_stage3_completeness,
    _has_archive_import_via_ast,
)


def _ctx(path: str, content: str) -> FileContext:
    return FileContext(path=path, abs_path=path, change_type="M", content=content)


# ── AST 直接函数测试 ───────────────────────────────────────────


def test_ast_catches_double_dot_relative():
    src = "from .._archive.routers_legacy import FooRouter as _Foo\n"
    assert _has_archive_import_via_ast(src) is True


def test_ast_catches_single_dot_relative():
    src = "from ._archive.routers_legacy import (FooRouter, BarRouter)\n"
    assert _has_archive_import_via_ast(src) is True


def test_ast_catches_triple_dot_relative():
    src = "from ..._archive.routers_v3_legacy.foo import BarRouter\n"
    assert _has_archive_import_via_ast(src) is True


def test_ast_catches_absolute_path():
    src = (
        "from omnicompany.packages.services.absorption._archive."
        "routers_v3_legacy.module_explorer import X\n"
    )
    assert _has_archive_import_via_ast(src) is True


def test_ast_ignores_docstring_example():
    src = '''"""
    Example Stage 2 Diamond:
        from .._archive.routers_legacy import FooRouter as _Foo
    """
import os
'''
    assert _has_archive_import_via_ast(src) is False


def test_ast_ignores_comment_example():
    src = "# from .._archive.routers_legacy import FooRouter\nimport os\n"
    assert _has_archive_import_via_ast(src) is False


def test_ast_ignores_string_literal():
    src = 'PATTERN = "from .._archive.routers_legacy import X"\n'
    assert _has_archive_import_via_ast(src) is False


def test_ast_safe_on_syntax_error():
    src = "this is not valid python !@#$\n"
    assert _has_archive_import_via_ast(src) is False


# ── 规则 check 路径测试 ───────────────────────────────────────


def test_rule_catches_top_level_routers_py():
    """services/<svc>/routers.py 顶层 (S-01b 扩范围目标)."""
    src = "from ._archive.routers_legacy import FooRouter\n"
    ctx = _ctx("src/omnicompany/packages/services/team_builder/routers.py", src)
    assert _check_stage3_completeness(ctx) is True


def test_rule_catches_workers_subdir():
    src = "from .._archive.routers_legacy import FooRouter as _F\n"
    ctx = _ctx(
        "src/omnicompany/packages/services/foo/workers/bar.py", src
    )
    assert _check_stage3_completeness(ctx) is True


def test_rule_catches_nested_subpackage():
    """services/<svc>/sub_pkg/foo.py 子包内借壳."""
    src = "from .._archive.routers_v3_legacy.module_x import XxxRouter\n"
    ctx = _ctx(
        "src/omnicompany/packages/services/foo/sub_pkg/bar.py", src
    )
    assert _check_stage3_completeness(ctx) is True


def test_rule_exempts_archive_internal():
    """归档内部文件 import 归档 → 不算违规 (归档不重写历史)."""
    src = "from .routers_v3_legacy import OldRouter\n"
    ctx = _ctx(
        "src/omnicompany/packages/services/foo/_archive/routers_legacy.py", src
    )
    assert _check_stage3_completeness(ctx) is False


def test_rule_skips_non_services_path():
    src = "from .._archive.routers_legacy import FooRouter as _F\n"
    ctx = _ctx("src/omnicompany/runtime/foo.py", src)
    assert _check_stage3_completeness(ctx) is False


def test_rule_skips_non_python():
    src = "from .._archive.routers_legacy import FooRouter\n"
    ctx = _ctx("src/omnicompany/packages/services/foo/notes.md", src)
    assert _check_stage3_completeness(ctx) is False


def test_rule_does_not_false_positive_on_self():
    """规则文件自身的 docstring/regex 示例不应被规则命中 (S-01 关键修复)."""
    import pathlib
    p = pathlib.Path("src/omnicompany/packages/services/guardian/rules/stage3_completeness.py")
    if not p.exists():
        return  # 测试 fixture 缺失时跳过
    ctx = _ctx(p.as_posix(), p.read_text(encoding="utf-8"))
    assert _check_stage3_completeness(ctx) is False, (
        "stage3_completeness.py 自身被命中说明 AST 没生效, S-01 回归"
    )


def test_rule_does_not_false_positive_on_patrol_worker():
    """patrol_worker.py 含字符串 `"from .._archive"` (检测代码), 不应被命中."""
    import pathlib
    p = pathlib.Path("src/omnicompany/packages/services/guardian/workers/patrol_worker.py")
    if not p.exists():
        return
    ctx = _ctx(p.as_posix(), p.read_text(encoding="utf-8"))
    assert _check_stage3_completeness(ctx) is False, (
        "patrol_worker.py 字符串字面量被命中, S-01 回归"
    )
