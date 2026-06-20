"""OMNI-035f~j 内部细节测试 (2026-04-28 立, 2026-04-28 瘦身).

**只保留有分辨力的部分**:
  - 035j 大文件 stat() 边界 (> vs >=, 文件不存在 except)

端到端检测 / 注册检查 / 误报防御 全部移到 test_canary_violations.py
(系统健康 canary, 跑 RuleEngine 而非单独 _check_xxx).

删掉的 echo 类测试 (此前反模式):
  - "p.endswith('.py') 应返 True" 这种复述 Python 内置
  - "_check_docs_python(ctx('docs/x.py')) == True" 这种复述 if 条件
  - 红样本 / 绿样本 一对一覆盖每条 path 规则
理由: 写错根本不可能编译过, 跑一次 patrol 立刻爆 — 单元测试无分辨力.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian import FileContext
from omnicompany.packages.services._core.guardian.rules.distributed_docs import (
    _check_docs_large_file,
)


def _ctx(path: str, abs_path: str | None = None) -> FileContext:
    return FileContext(
        path=path,
        abs_path=abs_path or f"e:/fake/{path}",
        change_type="M",
        content=None,
        omnimark=None,
    )


# ─── OMNI-035j 大文件 stat() 边界 ──────────────────────────────────
# 这里有真分辨力: stat() 路径错 / 阈值用 > vs >= / 文件不存在 except 分支
# 这些是"系统跑出来不会立刻爆"的边界, 单元测试有意义.


class TestLargeFileBoundary:
    def test_threshold_exact_1mb_not_violate(self, tmp_path):
        """边界: 正好 1 MB 不触发 (用 > 而非 >=). 阈值漂移会被这条抓住."""
        f = tmp_path / "exact_1mb.bin"
        f.write_bytes(b"x" * (1 * 1024 * 1024))
        assert not _check_docs_large_file(_ctx("docs/x/exact.bin", abs_path=str(f)))

    def test_threshold_just_over_violates(self, tmp_path):
        """边界: 1 MB + 1 byte 触发."""
        f = tmp_path / "over.bin"
        f.write_bytes(b"x" * (1 * 1024 * 1024 + 1))
        assert _check_docs_large_file(_ctx("docs/x/over.bin", abs_path=str(f)))

    def test_missing_file_does_not_crash(self):
        """abs_path 不存在: stat() 抛异常, 规则按未违规处理 (不能让 patrol 整个挂掉)."""
        c = _ctx("docs/plans/missing.bin", abs_path="/no/such/path.bin")
        # 不抛, 返 False
        assert _check_docs_large_file(c) is False

    def test_outside_docs_unaffected(self, tmp_path):
        """非 docs/ 路径不受 035j 管 (这个不是 echo, 是 scope 边界 — 防止规则漂移到全仓库)."""
        f = tmp_path / "huge.bin"
        f.write_bytes(b"x" * (5 * 1024 * 1024))
        assert not _check_docs_large_file(_ctx("data/huge.bin", abs_path=str(f)))
