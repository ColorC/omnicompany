# [OMNI] origin=claude-code domain=omnicompany/repo_absorption ts=2026-04-25T00:00:00Z type=worker
# [OMNI] material_id="material:learning.repo.absorption.worker.repo_scanner_hard.py"
"""RepoScannerWorker — repo_absorption Team Worker #1 (HARD).

Worker 协议:
  FORMAT_IN  = repo_absorption.scan_config
  FORMAT_OUT = repo_absorption.file_inventory

职责: 接收扫描配置 (repo_path + top_n)，递归枚举仓库下所有 .py 文件，
      用 Path.stat 提取行数与字节大小，产出结构化文件索引。
      纯确定性 HARD 节点，不调 LLM，跨平台兼容 (Windows/Linux/macOS)。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

logger = logging.getLogger(__name__)

# 排除目录：遍历 .py 文件时跳过这些目录
_SKIP_DIRS = frozenset({
    ".git", "__pycache__", ".venv", "venv", "node_modules",
    ".mypy_cache", ".pytest_cache", ".tox", ".nox",
    ".eggs", "*.egg-info", "dist", "build",
})


class RepoScannerWorker(Worker):
    """递归扫描仓库，产出 .py 文件清单 (行数 + 大小)。"""

    DESCRIPTION = (
        "接收 repo_absorption.scan_config (repo_path + top_n)，"
        "递归遍历 repo_path 下所有 .py 文件 (跳过 .git/__pycache__/venv 等目录，"
        "不跟随符号链接)，用 Path.stat 统计每文件的行数与字节大小，"
        "产出 repo_absorption.file_inventory 含全量文件清单。"
    )
    FORMAT_IN = "repo_absorption.scan_config"
    FORMAT_OUT = "repo_absorption.file_inventory"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        repo_path_str = input_data.get("repo_path")
        if not repo_path_str:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="repo_path 缺失或为空",
            )

        repo_path = Path(repo_path_str)

        # 验证目录存在且可读
        if not repo_path.exists():
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"repo_path 不存在: {repo_path}",
            )
        if not repo_path.is_dir():
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"repo_path 不是目录: {repo_path}",
            )

        files: list[dict[str, Any]] = []

        try:
            # rglob 不跟随符号链接 (默认行为)，跨平台兼容
            for py_file in repo_path.rglob("*.py"):
                # 跳过被排除的目录中的文件
                if any(part in _SKIP_DIRS for part in py_file.parts):
                    continue
                # 跳过符号链接指向的 .py 文件 (不跟随软链)
                if py_file.is_symlink():
                    continue
                # 只处理常规文件
                if not py_file.is_file():
                    continue

                try:
                    stat = py_file.stat()
                    size_bytes = stat.st_size

                    # 统计行数：按文本打开，跨平台换行符自动处理
                    with py_file.open("r", encoding="utf-8", errors="replace") as f:
                        line_count = sum(1 for _ in f)

                    rel_path = str(py_file.relative_to(repo_path))

                    files.append({
                        "rel_path": rel_path,
                        "line_count": line_count,
                        "size_bytes": size_bytes,
                    })
                except (OSError, PermissionError) as e:
                    logger.warning("RepoScanner: 跳过不可读文件 %s: %s", py_file, e)
                    continue

        except Exception as e:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"扫描 repo_path 失败: {type(e).__name__}: {e}",
            )

        # 按相对路径排序，保证输出确定性
        files.sort(key=lambda f: f["rel_path"])

        total_files = len(files)

        # top_n 从输入透传，保持默认值 5
        top_n = input_data.get("top_n", 5)
        if not isinstance(top_n, int) or top_n < 1:
            top_n = 5

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "repo_path": str(repo_path),
                "top_n": top_n,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_files": total_files,
                "files": files,
            },
            diagnosis=f"扫描完成: {total_files} 个 .py 文件",
            confidence=1.0,
        )
