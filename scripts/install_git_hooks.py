# [OMNI] origin=claude-code domain=scripts ts=2026-04-08T03:30:00Z
"""install_git_hooks — 把 OmniGuardian 的 git hooks 装到 .git/hooks/。

装两个:
  post-commit  — 每次 commit 后扫最新一个 commit 的变更（已有，幂等覆盖）
  pre-commit   — commit 前扫 staged 文件，CRITICAL 违规阻止 commit

pre-commit 的设计原则（保持和项目现有态度一致）:
  * 绝大多数违规只警告，不阻塞 commit
  * 只有 OMNI-014 (illegal-drawer) 真正阻塞 —— 这条规则是 absolute 判定，
    零误报，含义是"你在 src/omnicompany/ 下建了一个非法 drawer 目录"，
    这种情况必须先 omni guardian register 登记才能提交
  * 可以通过 git commit --no-verify 绕过（紧急情况）

Usage:
    python scripts/install_git_hooks.py
    python scripts/install_git_hooks.py --uninstall
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path


PRE_COMMIT_HOOK = r"""#!/bin/sh
# OmniGuardian pre-commit hook (S3d.3 升级)
#
# 拦截集合 (零误报 absolute 规则,直接阻塞 commit):
#   OMNI-014 illegal-drawer            (src/omnicompany/ 下非法子目录)
#   OMNI-015 forbidden-root-file       (仓库根禁区文件)
#   OMNI-016 packages-direct-child     (packages/ 下非 layer 子目录)
#   OMNI-017 format-not-observable     (package 没注册到 core/pipelines.py)
#   OMNI-018 router-not-observable     (Router 子类没被任何 pipeline 引用)
#
# 其他违规只警告 (OMNI-013 needs_judgment 类 / OMNI-019/020 INFO).
#
# 紧急绕过: git commit --no-verify

if ! command -v omni >/dev/null 2>&1; then
    echo "[OmniPatrol pre-commit] omni 命令未安装,跳过"
    exit 0
fi

PATROL_OUT=$(omni guardian patrol --staged-only --json-out 2>/dev/null)
if [ -z "$PATROL_OUT" ]; then
    exit 0
fi

# 用 python 解析,找拦截集合命中
BLOCKING=$(python -c "
import json, sys
BLOCK_RULES = {'OMNI-014', 'OMNI-015', 'OMNI-016', 'OMNI-017', 'OMNI-018'}
try:
    r = json.loads(sys.stdin.read())
    blockers = [v for v in r.get('violations', []) if v.get('rule_id') in BLOCK_RULES]
    if blockers:
        print('BLOCK')
        for b in blockers:
            print(f\"  {b.get('rule_id')} {b.get('path')}: {b.get('message','')[:200]}\", file=sys.stderr)
except Exception:
    pass
" <<< "$PATROL_OUT" 2>&1)

if echo "$BLOCKING" | head -1 | grep -q "^BLOCK"; then
    echo "$BLOCKING" | tail -n +2 >&2
    echo "" >&2
    echo "[OmniPatrol] commit 被阻止 (零误报 absolute 规则命中)." >&2
    echo "  拦截集合: OMNI-014/015/016/017/018" >&2
    echo "  紧急绕过: git commit --no-verify" >&2
    exit 1
fi

# 软违规 (OMNI-013/019/020 等) 让 post-commit 报告
exit 0
"""

POST_COMMIT_HOOK = r"""#!/bin/sh
# OmniPatrol post-commit hook (S3d.4 升级)
# 每次 git commit 后扫最新 commit + 跑 metadata-report
# 永远 exit 0,只打印软优化建议,不阻塞

if command -v omni >/dev/null 2>&1; then
    # 1. patrol 扫最近一个 commit
    omni guardian patrol --commits 1 --no-uncommitted

    # 2. metadata-report 软优化建议 (输出到 stderr 避免打扰主流程)
    echo ""
    echo "─────────── Metadata Quality (软建议) ───────────"
    omni guardian metadata-report 2>/dev/null | tail -20 || true
fi

exit 0
"""


def find_hooks_dir(root: Path) -> Path | None:
    """找 .git/hooks/ 或 worktree 情况下的实际 hooks 目录。"""
    git_dir = root / ".git"
    if git_dir.is_file():
        # worktree: .git 是一个文件指向真实目录
        for line in git_dir.read_text(encoding="utf-8").splitlines():
            if line.startswith("gitdir:"):
                real = Path(line.split(":", 1)[1].strip())
                if not real.is_absolute():
                    real = (root / real).resolve()
                return real / "hooks"
        return None
    if git_dir.is_dir():
        return git_dir / "hooks"
    return None


def install(root: Path, force: bool = True) -> None:
    hooks = find_hooks_dir(root)
    if hooks is None:
        print(f"[ERR] 找不到 .git/hooks/ 目录（root={root}）")
        sys.exit(1)
    hooks.mkdir(parents=True, exist_ok=True)

    for name, content in [("pre-commit", PRE_COMMIT_HOOK),
                          ("post-commit", POST_COMMIT_HOOK)]:
        target = hooks / name
        if target.exists() and not force:
            print(f"[SKIP] {name} 已存在（加 --force 覆盖）")
            continue
        # 统一写入入口在这种"底层 hook 脚本"场景不适用——
        # guarded_write 只给 .py/.yaml 等源码贴 OmniMark 头，
        # .git/hooks/* 是无扩展名 shell 脚本，不在 stampable 列表里。
        # 所以这里直接 Path.write_text（被 OMNI-013 豁免：scripts/ 下）。
        target.write_text(content, encoding="utf-8", newline="\n")
        # chmod +x
        current = target.stat().st_mode
        target.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"[OK] 装 {target}")


def uninstall(root: Path) -> None:
    hooks = find_hooks_dir(root)
    if hooks is None:
        print("[ERR] 找不到 hooks 目录")
        sys.exit(1)
    removed = 0
    for name in ("pre-commit", "post-commit"):
        target = hooks / name
        if target.exists():
            target.unlink()
            removed += 1
            print(f"[REMOVED] {target}")
    print(f"\n共卸载 {removed} 个 hook")


def main() -> None:
    parser = argparse.ArgumentParser(description="安装/卸载 OmniGuardian git hooks")
    parser.add_argument("--root", default=".", help="项目根目录")
    parser.add_argument("--uninstall", action="store_true", help="卸载而非安装")
    parser.add_argument("--force", action="store_true", default=True,
                        help="覆盖已存在的 hook（默认开启）")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.uninstall:
        uninstall(root)
    else:
        install(root, force=args.force)
        print("\n安装完成。下次 git commit 时:")
        print("  - pre-commit  会扫 staged 文件，OMNI-014 违规会阻塞")
        print("  - post-commit 会扫最新 commit，打印违规报告（不阻塞）")


if __name__ == "__main__":
    main()
