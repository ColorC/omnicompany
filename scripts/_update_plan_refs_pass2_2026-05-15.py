#!/usr/bin/env python3
"""Second-pass plan path ref update after dropping _capabilities/_projects/ layer.

Maps:
  plans/_projects/<topic>/ → plans/<topic>/
  plans/_capabilities/<cap>/ → plans/omnicompany-<cap>/
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

REPLACEMENTS = [
    # _projects/<topic>/ → <topic>/
    ("plans/_projects/agent-framework/", "plans/agent-framework/"),
    ("plans/_projects/voxel_engine/", "plans/voxel_engine/"),
    ("plans/_projects/dashboard/", "plans/dashboard/"),
    ("plans/_projects/diagnosis/", "plans/diagnosis/"),
    ("plans/_projects/format-material/", "plans/format-material/"),
    ("plans/_projects/guardian/", "plans/guardian/"),
    ("plans/_projects/gameplay_system/", "plans/gameplay_system/"),
    ("plans/_projects/stage-experiments/", "plans/stage-experiments/"),
    # _capabilities/<cap>/ → omnicompany-<cap>/
    ("plans/_capabilities/计划跟进/", "plans/omnicompany-计划跟进/"),
    ("plans/_capabilities/调研吸收/", "plans/omnicompany-调研吸收/"),
    # bare (no slash)
    ("plans/_projects/agent-framework", "plans/agent-framework"),
    ("plans/_projects/voxel_engine", "plans/voxel_engine"),
    ("plans/_projects/dashboard", "plans/dashboard"),
    ("plans/_projects/diagnosis", "plans/diagnosis"),
    ("plans/_projects/format-material", "plans/format-material"),
    ("plans/_projects/guardian", "plans/guardian"),
    ("plans/_projects/gameplay_system", "plans/gameplay_system"),
    ("plans/_projects/stage-experiments", "plans/stage-experiments"),
    ("plans/_capabilities/计划跟进", "plans/omnicompany-计划跟进"),
    ("plans/_capabilities/调研吸收", "plans/omnicompany-调研吸收"),
    ("plans/_projects", "plans"),       # catchall
    ("plans/_capabilities", "plans"),
]

SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv", "temp", "tmp", ".omni"}
SKIP_FILES = {
    "_migrate_plans_2026-05-15.sh", "_update_plan_refs_2026-05-15.py",
    "_flatten_plans_2026-05-15.sh", "_update_plan_refs_pass2_2026-05-15.py",
}
TEXT_EXTS = {".md", ".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".yaml", ".yml",
             ".jsonl", ".txt", ".html"}


def should_process(p: Path) -> bool:
    if p.name in SKIP_FILES:
        return False
    if p.suffix.lower() not in TEXT_EXTS:
        return False
    parts = set(p.parts)
    if parts & SKIP_DIRS:
        return False
    return True


def process_file(p: Path) -> int:
    try:
        content = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return 0
    orig = content
    n_total = 0
    for old, new in REPLACEMENTS:
        n = content.count(old)
        if n:
            content = content.replace(old, new)
            n_total += n
    if content != orig:
        p.write_text(content, encoding="utf-8")
        return n_total
    return 0


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    total_files = 0
    total_replacements = 0
    changes = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if not should_process(p):
                continue
            n = process_file(p)
            if n:
                rel = p.relative_to(root)
                changes.append((str(rel), n))
                total_files += 1
                total_replacements += n
    changes.sort(key=lambda x: -x[1])
    for path, n in changes[:25]:
        print(f"  {n:4d}  {path}")
    if len(changes) > 25:
        print(f"  ... and {len(changes) - 25} more files")
    print(f"\nTOTAL: {total_replacements} replacements across {total_files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
