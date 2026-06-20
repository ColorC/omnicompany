# [OMNI] origin=claude-code domain=services/_governance/doc_steward ts=2026-06-13T08:10:00Z type=router
# [OMNI] material_id="material:governance.doc_steward.freshness_pipeline.py"
"""文档时效性治理管线 — plan / report / 规范 的维护。

背景(2026-06-13 用户): "内部应当建立管线去维护计划, 报告 —— 尤其是规范的时效性。"
方法遵 docs/standards/concepts/governance_semantic_first.md: **语义判断用性价比模型为主,
确定性规律(如断链)用代码扫**。本部门两层:

1. 引用完整性(确定性, 无需 LLM): 扫 markdown 链接 / 行锚 指向**已不存在的文件**。
   便宜、不误报、可单测。这是"断链/陈旧指针"这类批量规律的结晶(规则化的那一半)。
2. 时效性(语义, 性价比模型): 逐篇判规范是否**过期/被取代/自相矛盾/另立权威**。
   走 runtime/llm/structured.call_json + runtime/llm/batch.run_parallel_items。

产物落 data/governance/doc_steward/, 只报 findings 不自动改文档(改文档是另一种危险操作)。
消费方: omni governance docs-* CLI; 后续可上 dashboard。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnicompany.core.config import omni_workspace_root

# ── 目标发现 ────────────────────────────────────────────────────────

_TARGET_GLOBS: dict[str, tuple[str, ...]] = {
    "standard": ("docs/standards/**/*.md",),
    "plan": ("docs/plans/**/plan.md",),
    "report": ("docs/reports/**/*.md",),
}
_SKIP_DIR_PARTS = ("_archive", "_graveyard", "__pycache__")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def report_dir() -> Path:
    d = omni_workspace_root() / "data" / "governance" / "doc_steward"
    d.mkdir(parents=True, exist_ok=True)
    return d


def discover_targets(kinds: tuple[str, ...] | None = None, root: Path | None = None) -> list[tuple[str, Path]]:
    """返回 (kind, 绝对路径) 列表。跳过归档/坟场。"""
    base = root or omni_workspace_root()
    wanted = kinds or tuple(_TARGET_GLOBS.keys())
    out: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for kind in wanted:
        for pat in _TARGET_GLOBS.get(kind, ()):  # noqa: B007
            for p in base.glob(pat):
                if not p.is_file():
                    continue
                if any(part in _SKIP_DIR_PARTS for part in p.parts):
                    continue
                if p in seen:
                    continue
                seen.add(p)
                out.append((kind, p))
    return out


# ── 第一层: 引用完整性(确定性) ──────────────────────────────────────

@dataclass
class DocFinding:
    doc: str            # 相对仓库根的文档路径
    kind: str           # standard | plan | report
    category: str       # broken_ref | broken_anchor | stale_pointer | timeliness | ...
    detail: str
    target: str = ""    # 指向的(失效)目标
    by: str = "doc_steward"

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc": self.doc, "kind": self.kind, "category": self.category,
            "detail": self.detail, "target": self.target, "by": self.by,
        }


# markdown 链接 [text](target) — target 不含空格/右括号
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def _is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "//", "#")) or target.startswith("data:")


def scan_references(abs_path: Path, root: Path | None = None) -> list[DocFinding]:
    """确定性扫一篇文档里指向**已不存在文件**的 markdown 链接/行锚。"""
    base = root or omni_workspace_root()
    try:
        rel = str(abs_path.relative_to(base)).replace("\\", "/")
    except ValueError:
        rel = str(abs_path)
    kind = _classify_kind(rel)
    try:
        text = abs_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    findings: list[DocFinding] = []
    for raw in _MD_LINK_RE.findall(text):
        target = raw.strip()
        if not target or _is_external(target):
            continue
        # 去掉锚点片段(#Lnnn / #heading)只校验文件存在性
        file_part = target.split("#", 1)[0]
        if not file_part or file_part.startswith("[["):  # wikilink 非文件链接
            continue
        # 解析: 先相对文档目录, 再相对仓库根
        cand_doc_rel = (abs_path.parent / file_part).resolve()
        cand_root_rel = (base / file_part.lstrip("/")).resolve()
        if cand_doc_rel.exists() or cand_root_rel.exists():
            continue
        anchored = "#" in target
        findings.append(DocFinding(
            doc=rel, kind=kind,
            category="broken_anchor" if anchored else "broken_ref",
            detail=f"链接目标文件不存在: {target}",
            target=target,
        ))
    return findings


def _classify_kind(rel: str) -> str:
    if rel.startswith("docs/standards/"):
        return "standard"
    if rel.startswith("docs/plans/"):
        return "plan"
    if rel.startswith("docs/reports/"):
        return "report"
    return "doc"


def run_reference_audit(kinds: tuple[str, ...] | None = None, root: Path | None = None,
                        write: bool = True) -> dict[str, Any]:
    """全量跑确定性引用完整性审计, 返回 {findings, counts, ...}, 可落盘。"""
    base = root or omni_workspace_root()
    targets = discover_targets(kinds, root=base)
    all_findings: list[DocFinding] = []
    for _kind, p in targets:
        all_findings.extend(scan_references(p, root=base))
    payload = {
        "kind": "reference_audit",
        "generated_at": _now(),
        "scanned_docs": len(targets),
        "findings": [f.to_dict() for f in all_findings],
        "counts": {"broken_ref": sum(1 for f in all_findings if f.category == "broken_ref"),
                   "broken_anchor": sum(1 for f in all_findings if f.category == "broken_anchor")},
    }
    if write:
        out = report_dir() / "reference_audit.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["_written"] = str(out)
    return payload


# ── 第二层: 时效性(语义, 性价比模型) ────────────────────────────────

SYSTEM_PROMPT = """你是 omnicompany 仓库的规范/文档时效性治理员。给你一篇文档(规范/计划/报告)的节选,
判定它是否还反映现状。只输出 JSON, 不要其它文字。

判据(每条独立给, 没有就不给):
- superseded: 这份被更新的规范取代了, 却仍标 active(例如旧 DESIGN 七节模板 vs 新三件套规范)。
- outdated: 描述的接口/路径/机制已经变了(指向的代码搬家或删除、流程已重写)。
- conflict: 与另一份现行规范冲突, 没有谁服从谁的声明。
- competing_authority: 这份在另立一套"唯一权威", 没有指回已确立的权威文件。
不确定时不要报。证据要引文档里的具体句子或指向。

输出: {"findings": [{"category": "superseded|outdated|conflict|competing_authority", "detail": "<=40字", "evidence": "引原文/指向"}]}"""

TIMELINESS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["category", "detail"],
                "properties": {
                    "category": {"type": "string",
                                 "enum": ["superseded", "outdated", "conflict", "competing_authority"]},
                    "detail": {"type": "string"},
                    "evidence": {"type": "string"},
                },
            },
        },
    },
}

_EXCERPT_CHARS = 2400


def _excerpt(abs_path: Path) -> str:
    try:
        return abs_path.read_text(encoding="utf-8", errors="replace")[:_EXCERPT_CHARS]
    except OSError:
        return ""


def judge_timeliness(abs_path: Path, *, model: str | None = None, root: Path | None = None) -> list[DocFinding]:
    """对单篇文档跑语义时效性判断(性价比模型)。"""
    from omnicompany.runtime.llm.structured import call_json
    base = root or omni_workspace_root()
    try:
        rel = str(abs_path.relative_to(base)).replace("\\", "/")
    except ValueError:
        rel = str(abs_path)
    excerpt = _excerpt(abs_path)
    if not excerpt.strip():
        return []
    user = f"文档路径: {rel}\n\n节选:\n{excerpt}"
    result = call_json(system=SYSTEM_PROMPT, user=user, schema=TIMELINESS_SCHEMA,
                       model=model, caller="doc_steward.judge_timeliness", max_tokens=1500)
    out: list[DocFinding] = []
    for f in (result or {}).get("findings", []) or []:
        out.append(DocFinding(
            doc=rel, kind=_classify_kind(rel), category=str(f.get("category", "timeliness")),
            detail=str(f.get("detail", ""))[:200], target=str(f.get("evidence", ""))[:200],
        ))
    return out


def run_timeliness(*, kinds: tuple[str, ...] = ("standard",), model: str | None = None,
                   limit: int | None = None, workers: int = 4, root: Path | None = None,
                   write: bool = True, echo: Any = None) -> dict[str, Any]:
    """批量跑语义时效性治理(默认只扫规范)。失败按项隔离, 走通用批量执行器。"""
    from omnicompany.runtime.llm.batch import run_parallel_items
    base = root or omni_workspace_root()
    targets = [p for _k, p in discover_targets(kinds, root=base)]
    if limit:
        targets = targets[:limit]

    def _worker(p: Path) -> list[dict[str, Any]]:
        return [f.to_dict() for f in judge_timeliness(p, model=model, root=base)]

    result = run_parallel_items(
        targets, _worker, workers=workers, progress_label="doc_steward.timeliness",
        item_label=lambda i, p: p.name, echo=echo,
    )
    findings: list[dict[str, Any]] = []
    for r in result.results:
        if r:
            findings.extend(r)
    payload = {
        "kind": "timeliness",
        "generated_at": _now(),
        "model": model or "default",
        "scanned_docs": len(targets),
        "failed_docs": len(result.failures),
        "findings": findings,
    }
    if write:
        stamp = _now().replace(":", "").replace("-", "")[:15]
        out = report_dir() / f"timeliness-{stamp}.json"
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        (report_dir() / "timeliness-latest.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        payload["_written"] = str(out)
    return payload


def latest_findings() -> dict[str, Any]:
    """读最近一次治理产物(引用审计 + 时效性), 供 CLI/报告。"""
    d = report_dir()
    out: dict[str, Any] = {"reference_audit": None, "timeliness": None}
    ref = d / "reference_audit.json"
    if ref.is_file():
        out["reference_audit"] = json.loads(ref.read_text(encoding="utf-8"))
    tl = d / "timeliness-latest.json"
    if tl.is_file():
        out["timeliness"] = json.loads(tl.read_text(encoding="utf-8"))
    return out
