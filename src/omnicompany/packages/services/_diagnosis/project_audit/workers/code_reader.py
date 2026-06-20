# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-20T00:00:00Z type=worker status=active
# [OMNI] summary="CodeReader — 真读项目关键文件的内容节选(README/入口/配置/核心源码),非只看路径。修上一版 auditor'只凭路径判断'的硬伤。HARD。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.code_reader"
"""CodeReader(HARD)。

信任层级 B 类真源的采集器:**agent 真写下的代码内容**才是"到底做出了什么"的权威。
上一版 auditor 只把文件路径清单喂 LLM,无法据代码内容确认功能是否实现 → 误判。
本 worker 按优先级挑关键文件,真读其**内容节选**,连同按语言的代码量统计一起下行,
让 auditor 据"真实代码内容"而非"文件名存在"判断完成度。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker

# 第一优先:能快速交代"这项目是什么、入口在哪、配置怎样"的文件
_TOP_NAMES = (
    "readme", "design", "architecture", "arch", "overview", "spec",
    "pyproject.toml", "package.json", "cargo.toml", "go.mod", "requirements",
    "manifest", "__main__", "main", "index", "cli", "app", "run", "server",
    "__init__",
)
_CODE_EXT = {
    "py": "Python", "ts": "TypeScript", "tsx": "TypeScript", "js": "JavaScript",
    "jsx": "JavaScript", "mjs": "JavaScript", "go": "Go", "rs": "Rust",
    "java": "Java", "cs": "C#", "cpp": "C++", "c": "C", "rb": "Ruby",
    "vue": "Vue", "svelte": "Svelte", "lua": "Lua", "sh": "Shell",
}
_TEXT_EXT = _CODE_EXT.keys() | {"md", "toml", "yaml", "yml", "json", "cfg", "ini", "txt"}
_SKIP_SUBSTR = ("node_modules/", "/dist/", "/build/", ".min.", "vendor/", "/__pycache__/",
                "package-lock", "yarn.lock", "pnpm-lock", "/.cache/", "/data/")


def _priority(rel: str) -> int:
    """越小越优先。综合:顶层文件名命中 / 路径深度浅 / 是源码。"""
    low = rel.lower()
    base = low.rsplit("/", 1)[-1]
    depth = rel.count("/")
    score = depth  # 浅的更中心
    if any(n in base for n in _TOP_NAMES):
        score -= 20
    ext = base.rsplit(".", 1)[-1] if "." in base else ""
    if ext in _CODE_EXT:
        score -= 3
    if ext == "md":
        score -= 2
    if "/test" in low or "test_" in base or low.endswith(".spec.ts"):
        score += 8  # 测试靠后但不排除
    return score


class CodeReader(Worker):
    """真读关键文件内容(B 类真源)。HARD,确定性文件读取。"""

    DESCRIPTION = (
        "据真实文件树挑关键文件(README/设计/入口/配置/核心源码),真读其内容节选并按语言统计代码量,"
        "连同 prompts 一起下行给审计——让判断基于真实代码内容,而非'文件名存在'。"
    )
    FORMAT_IN = "project_audit.enriched"
    FORMAT_OUT = "project_audit.enriched"

    def run(self, input_data: Any) -> Verdict:
        enr = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(enr, dict) or not enr.get("root"):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="enriched 无效(缺 root)", output={})

        rootp = Path(enr["root"])
        all_paths = enr.get("all_paths", []) or []
        target = enr.get("target", {}) or {}
        max_files = int(target.get("max_code_files") or 60)
        per_file_cap = int(target.get("code_char_cap") or 3000)
        total_cap = int(target.get("code_total_cap") or 160_000)

        # 按语言代码量(全量,廉价)
        loc_by_lang: dict[str, int] = {}
        candidates: list[str] = []
        for rel in all_paths:
            low = rel.lower()
            if any(s in "/" + low for s in _SKIP_SUBSTR):
                continue
            ext = low.rsplit(".", 1)[-1] if "." in low else ""
            if ext in _CODE_EXT:
                loc_by_lang[_CODE_EXT[ext]] = loc_by_lang.get(_CODE_EXT[ext], 0) + 1
            if ext in _TEXT_EXT:
                candidates.append(rel)

        candidates.sort(key=_priority)

        code: list[dict] = []
        total_bytes = 0
        for rel in candidates:
            if len(code) >= max_files or total_bytes >= total_cap:
                break
            try:
                text = (rootp / rel).read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            head = text[:per_file_cap]
            total_bytes += len(head)
            code.append({"path": rel, "bytes": len(text), "head": head})

        enr["code"] = code
        enr["code_meta"] = {
            "files_read": len(code),
            "total_bytes": total_bytes,
            "candidates": len(candidates),
            "loc_by_lang": dict(sorted(loc_by_lang.items(), key=lambda x: -x[1])),
            "selection_note": (
                f"按优先级读了 {len(code)}/{len(candidates)} 个文本文件内容节选"
                f"(每文件≤{per_file_cap}字,合计≤{total_cap}字);代码量统计为全量。"
            ),
        }
        return Verdict(kind=VerdictKind.PASS, output=enr)
