#!/usr/bin/env python3
"""Update plan path references after 2026-05-15 reorg (能力轴+项目轴).

Skips:
- .git/, node_modules/, dist/, build/
- The migration script itself
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

# Order: most specific to least specific
REPLACEMENTS = [
    # _infra/<topic>/ → _projects/<topic>/ or _capabilities/<cap>/
    ("plans/_infra/agent-framework/", "plans/_projects/agent-framework/"),
    ("plans/_infra/dashboard/", "plans/_projects/dashboard/"),
    ("plans/_infra/diagnosis/", "plans/_projects/diagnosis/"),
    ("plans/_infra/format-material/", "plans/_projects/format-material/"),
    ("plans/_infra/guardian/", "plans/_projects/guardian/"),
    ("plans/_infra/learning-kb/", "plans/_capabilities/调研吸收/"),
    ("plans/_infra/stage-experiments/", "plans/_projects/stage-experiments/"),
    # domain/voxel_engine: flatten _milestones/_north-star/_paths
    ("plans/domain/voxel_engine/_milestones/", "plans/_projects/voxel_engine/"),
    ("plans/domain/voxel_engine/_north-star/", "plans/_projects/voxel_engine/"),
    ("plans/domain/voxel_engine/_paths/", "plans/_projects/voxel_engine/"),
    ("plans/domain/voxel_engine/_archive/", "plans/_projects/voxel_engine/_archive/"),
    # domain/voxel_engine/ catchall (stray files like project.md, CLEANUP_MANIFEST...)
    ("plans/domain/voxel_engine/", "plans/_projects/voxel_engine/"),
    # domain/gameplay_system sub-areas: flatten
    ("plans/domain/gameplay_system/battle/", "plans/_projects/gameplay_system/"),
    ("plans/domain/gameplay_system/demo-dev/", "plans/_projects/gameplay_system/"),
    ("plans/domain/gameplay_system/kb-ingest/", "plans/_projects/gameplay_system/"),
    ("plans/domain/gameplay_system/table-pipeline/", "plans/_projects/gameplay_system/"),
    ("plans/domain/gameplay_system/ux-figma/", "plans/_projects/gameplay_system/"),
    # domain/gameplay_system/ catchall
    ("plans/domain/gameplay_system/", "plans/_projects/gameplay_system/"),
    # archive nested cleanup
    ("plans/_archive/_infra/dashboard/", "plans/_archive/"),
    # bare references (no trailing slash)
    ("plans/_infra/agent-framework", "plans/_projects/agent-framework"),
    ("plans/_infra/dashboard", "plans/_projects/dashboard"),
    ("plans/_infra/diagnosis", "plans/_projects/diagnosis"),
    ("plans/_infra/format-material", "plans/_projects/format-material"),
    ("plans/_infra/guardian", "plans/_projects/guardian"),
    ("plans/_infra/learning-kb", "plans/_capabilities/调研吸收"),
    ("plans/_infra/stage-experiments", "plans/_projects/stage-experiments"),
    ("plans/_infra", "plans/_projects"),  # last resort for bare _infra mentions
    ("plans/domain/voxel_engine", "plans/_projects/voxel_engine"),
    ("plans/domain/gameplay_system", "plans/_projects/gameplay_system"),
]

SKIP_DIRS = {".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
             "data", "temp", "tmp", ".omni"}
SKIP_FILES = {"_migrate_plans_2026-05-15.sh", "_update_plan_refs_2026-05-15.py"}
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


def process_file(p: Path) -> tuple[int, list[str]]:
    try:
        content = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return 0, []
    orig = content
    hits = []
    for old, new in REPLACEMENTS:
        n = content.count(old)
        if n:
            content = content.replace(old, new)
            hits.append(f"  {old!r} → {new!r} × {n}")
    if content != orig:
        p.write_text(content, encoding="utf-8")
        return sum(int(h.split("× ")[1]) for h in hits), hits
    return 0, hits


def main() -> int:
    root = Path(__file__).resolve().parent.parent  # omnicompany/
    total_files = 0
    total_replacements = 0
    changed_files = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            p = Path(dirpath) / name
            if not should_process(p):
                continue
            n, _hits = process_file(p)
            if n:
                rel = p.relative_to(root)
                changed_files.append((str(rel), n))
                total_files += 1
                total_replacements += n
    changed_files.sort(key=lambda x: -x[1])
    for path, n in changed_files[:30]:
        print(f"  {n:4d}  {path}")
    if len(changed_files) > 30:
        print(f"  ... and {len(changed_files) - 30} more files")
    print(f"\nTOTAL: {total_replacements} replacements across {total_files} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
