# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-19T00:00:00Z type=worker status=active
# [OMNI] summary="TreeEnumeratorWorker — os.walk 全量枚举项目文件树(遍历,非抽样)。HARD。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.tree_enumerator"
"""TreeEnumeratorWorker(HARD)— 遍历项目真实文件树,不抽样、不信任何说明文件。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker

_PLAN_HINTS = ("plan", "roadmap", "active", "journal", "goal", "checklist", "review", "postmortem")


class TreeEnumeratorWorker(Worker):
    """os.walk 全量枚举项目文件树。HARD,确定性,可重放。"""

    DESCRIPTION = (
        "对项目根做 os.walk 全量遍历(排除 .git/node_modules 等),统计文件总数、"
        "按扩展名、按顶层目录,落全部相对路径,并挑出计划类文档。非 grep 命中,是遍历。"
    )
    FORMAT_IN = "project_audit.target"
    FORMAT_OUT = "project_audit.tree"

    def run(self, input_data: Any) -> Verdict:
        payload = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(payload, dict):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="target 非 dict", output={})
        root = payload.get("root")
        if not root or not Path(root).exists():
            return Verdict(kind=VerdictKind.FAIL, diagnosis=f"项目根不存在: {root}", output={})

        exclude = set(payload.get("exclude") or [".git", "node_modules", "__pycache__", ".venv", ".idea"])
        rootp = Path(root)
        total = 0
        by_ext: dict[str, int] = {}
        by_top: dict[str, int] = {}
        all_paths: list[str] = []
        plan_files: list[str] = []

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in exclude]
            for fn in filenames:
                full = Path(dirpath) / fn
                try:
                    rel = str(full.relative_to(rootp)).replace("\\", "/")
                except Exception:
                    continue
                total += 1
                ext = (full.suffix.lower().lstrip(".") or "(none)")
                by_ext[ext] = by_ext.get(ext, 0) + 1
                top = rel.split("/", 1)[0] if "/" in rel else "(root)"
                by_top[top] = by_top.get(top, 0) + 1
                all_paths.append(rel)
                low = rel.lower()
                if low.endswith(".md") and any(h in low for h in _PLAN_HINTS):
                    plan_files.append(rel)

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "root": root,
                "total_files": total,
                "by_ext": dict(sorted(by_ext.items(), key=lambda x: -x[1])),
                "by_top_dir": dict(sorted(by_top.items(), key=lambda x: -x[1])),
                "all_paths": all_paths,
                "plan_files": plan_files,
                "target": payload,
            },
        )
