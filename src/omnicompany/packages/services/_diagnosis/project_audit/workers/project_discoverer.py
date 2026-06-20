# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-20T00:00:00Z type=worker status=active
# [OMNI] summary="ProjectDiscoverer — 从会话日志的真实 cwd + 仓库扫描枚举'我真做过的项目',按归属边界标记 owned(开源依赖 owned=False)。HARD。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.project_discoverer"
"""ProjectDiscoverer(HARD)。

完整性的第一道保证(plan §四):**先枚举全部项目,再要求逐个覆盖**——堵死"漏掉项目"。
据真源发现:我在本地 claude/codex 真正工作过的目录(会话 cwd 频次)+ 仓库扫描出的项目根。
按归属边界(§1.3)标 owned:我指挥 agent 编辑过的=True;只是用的开源依赖=False。
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker

from ._sessions import default_session_roots, first_cwd, iter_session_files, _norm_path

# 已知开源依赖(我只是用/集成,绝不算我做的;归属边界 §1.3)
_OPEN_SOURCE = (
    "claudecodeui", "figmatocode", "figma-ui", "omnicompany-public", "dockview",
    "gitleaks", "mem0", "backtrader", "flow-launcher", "sharex", "node_modules",
    "claude-agent-sdk", "amo0725",
)
# 噪声 cwd(临时/缓存/codex 自身会话目录,不算项目)
_NOISE = ("appdata/local/temp", "/temp/", "/.cache/", "/tmp/", "documents/codex/", "/new-chat")
_REPO_MARKERS = (".git", "pyproject.toml", "package.json", "Cargo.toml", "go.mod")


def _is_open_source(path_norm: str) -> bool:
    return any(o in path_norm for o in _OPEN_SOURCE)


def _is_noise(path_norm: str) -> bool:
    return any(n in path_norm for n in _NOISE)


def _collapse_to_project(cwd_norm: str, repo_roots_norm: list[str]) -> str:
    """把子目录 cwd 收敛到项目根:若 cwd 在某 repo_root 下,取 repo_root 的下一级作为项目根。"""
    for rr in repo_roots_norm:
        if cwd_norm == rr:
            return cwd_norm
        if cwd_norm.startswith(rr + "/"):
            rest = cwd_norm[len(rr) + 1:]
            first = rest.split("/", 1)[0]
            return f"{rr}/{first}"
    return cwd_norm


class ProjectDiscoverer(Worker):
    """枚举我真做过的项目(会话 cwd + 仓库扫描),归属过滤。HARD。"""

    DESCRIPTION = (
        "扫 ~/.claude 与 ~/.codex 全部会话的真实 cwd 统计工作频次,收敛到项目根,"
        "再与仓库扫描合并,按归属边界标 owned(开源依赖 owned=False),产出'我真做过的项目'清单。"
    )
    FORMAT_IN = "project_audit.discover_seed"
    FORMAT_OUT = "project_audit.project_list"

    def run(self, input_data: Any) -> Verdict:
        seed = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(seed, dict):
            seed = {}
        session_roots = seed.get("session_roots") or default_session_roots()
        repo_roots = seed.get("repo_roots") or ["/workspace", "/scm/main/AIWorkSpace"]
        min_sessions = int(seed.get("min_sessions") or 1)
        repo_roots_norm = [_norm_path(r) for r in repo_roots]

        # 1) 会话 cwd 频次 → 收敛到项目根
        proj_sessions: Counter = Counter()
        raw_cwds: Counter = Counter()
        scanned = 0
        for fp in iter_session_files(session_roots):
            scanned += 1
            cwd = first_cwd(fp)
            if not cwd:
                continue
            cn = _norm_path(cwd)
            raw_cwds[cn] += 1
            if _is_noise(cn):
                continue
            proj = _collapse_to_project(cn, repo_roots_norm)
            proj_sessions[proj] += 1

        # 2) 仓库扫描补全(可能有我做过但近期无会话的项目)
        from_repo: set[str] = set()
        for rr in repo_roots:
            rr = os.path.expanduser(rr)
            if not os.path.isdir(rr):
                continue
            try:
                for child in os.listdir(rr):
                    cp = os.path.join(rr, child)
                    if not os.path.isdir(cp):
                        continue
                    if any((Path(cp) / m).exists() for m in _REPO_MARKERS) or os.path.isdir(os.path.join(cp, "src")):
                        from_repo.add(_norm_path(cp))
            except Exception:
                continue

        # 3) 合并 + 归属裁定
        all_roots = set(proj_sessions) | from_repo
        projects: list[dict] = []
        for r in sorted(all_roots):
            sc = proj_sessions.get(r, 0)
            if sc < min_sessions and r not in from_repo:
                continue
            if _is_noise(r):
                continue
            exists = os.path.isdir(r)
            owned = not _is_open_source(r)
            evidence = []
            if sc:
                evidence.append(f"{sc} 次本地会话工作于此 cwd")
            if r in from_repo:
                evidence.append("仓库扫描命中项目标记")
            projects.append({
                "name": Path(r).name,
                "root": r,
                "owned": owned,
                "exists": exists,
                "session_count": sc,
                "evidence": "; ".join(evidence) or "(无)",
                "note": "开源依赖(我只是用/集成,非我做)" if not owned else "",
            })

        projects.sort(key=lambda p: (-p["session_count"], p["root"]))
        owned_n = sum(1 for p in projects if p["owned"])
        out = {
            "projects": projects,
            "summary": (
                f"扫 {scanned} 个会话文件,得 {len(raw_cwds)} 个不同 cwd;收敛 + 仓库扫描后 "
                f"{len(projects)} 个候选项目,其中 owned(我真做的)={owned_n}、开源依赖={len(projects)-owned_n}。"
                "owned=True 的需逐个进 project_audit 全量遍历核实(完整性铁律)。"
            ),
        }
        return Verdict(kind=VerdictKind.PASS, output=out)
