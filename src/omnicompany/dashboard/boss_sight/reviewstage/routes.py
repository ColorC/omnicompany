# [OMNI] origin=ai-ide ts=2026-05-24 type=infra
# [OMNI] material_id="material:dashboard.boss_sight.reviewstage.routes.py"
"""审阅台 HTTP + WS API — 块 4 B4-R3.

Endpoints (mounted under /api/boss-sight/reviewstage):
- GET    /                  list materials (filter status/tier/plan_id/pushed_only)
- GET    /{material_id}     detail
- POST   /                  manual submit (用户/外部脚本; 总控走 SubmitToReviewstageRouter)
- POST   /{material_id}/verdict     accept / reject / block
- POST   /{material_id}/comment     用户加评论
- POST   /{material_id}/annotation  AI 批注 (一般总控调; HTTP 留个口子人也能加)
- POST   /{material_id}/tier        调整分级
- DELETE /{material_id}             删除
- GET    /{material_id}/file        拿 material 文件 (image/html/markdown)
- WS     /stream                    实时 push: created / verdict_changed / comment_added / pushed / ...
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from ..entity_registry import normalize_comment_target
from .store import (
    COMMENT_FEEDBACK_STATUSES,
    MaterialKind,
    MaterialStatus,
    MaterialStore,
    MaterialTier,
)

_log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# Singleton store wiring (ccdaemon main.py lifespan 在 app.state 上放 store)
# ────────────────────────────────────────────────────────────────────────


_store_singleton: MaterialStore | None = None
_store_singleton_lock = threading.Lock()


def get_store() -> MaterialStore:
    """全局 store. ccdaemon 单进程; daemon lifespan 启动时 init."""
    global _store_singleton
    with _store_singleton_lock:
        if _store_singleton is None:
            from omnicompany.core.config import omni_workspace_root
            from omnicompany.dashboard.boss_sight.reviewstage.material_types import (
                default_review_format_registry,
            )
            ws_root = omni_workspace_root()  # 唯一权威, 不再硬编码 parents[N]
            # 装配进程级共享 Format 注册表: 让 review.kind.* 扩展 Format 在生产路径可见
            # (此前 registry=None 退化成只认 5 个内置 kind, T2 退出条件在生产不成立)。
            _store_singleton = MaterialStore(
                root=ws_root / "data" / "boss_sight" / "reviewstage",
                format_registry=default_review_format_registry(),
            )
        return _store_singleton


# ────────────────────────────────────────────────────────────────────────
# WS hub — 把 store 同步 callback 转 async broadcast
# ────────────────────────────────────────────────────────────────────────


class ReviewstageHub:
    """WS clients hub. store 同步 callback → asyncio.run_coroutine_threadsafe 推到所有
    连接的 client.
    """

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._lock = threading.Lock()

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def on_store_event(self, event_type: str, material) -> None:
        """store 同步 callback. 转 async broadcast."""
        if self._loop is None:
            return
        mdict = material.to_dict()
        _attach_notes_to_materials([mdict])  # 评论真源在中心 store, wire 出去前水合
        payload = {
            "event_type": event_type,
            "material": mdict,
        }
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)
        except Exception:  # noqa: BLE001
            _log.exception("hub broadcast scheduling failed")

    def broadcast_active(self, material_id: str) -> None:
        """跨表面"激活材料"广播(三区化): 队列/材料页签选中 → 在 WS 流上推 active_material,
        别的 webview(评论次级侧栏等)据此切到该材料。不带 material 实体, 只带 id。"""
        if self._loop is None:
            return
        payload = {"event_type": "active_material", "material_id": material_id}
        try:
            asyncio.run_coroutine_threadsafe(self._broadcast(payload), self._loop)
        except Exception:  # noqa: BLE001
            _log.exception("hub active broadcast scheduling failed")

    async def _broadcast(self, payload: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        with self._lock:
            conns = list(self._connections)
        for ws in conns:
            try:
                await ws.send_json(payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        if dead:
            with self._lock:
                for d in dead:
                    self._connections.discard(d)

    async def add(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._connections.add(ws)

    def remove(self, ws: WebSocket) -> None:
        with self._lock:
            self._connections.discard(ws)


_hub: ReviewstageHub | None = None
_hub_lock = threading.Lock()


def get_hub() -> ReviewstageHub:
    global _hub
    with _hub_lock:
        if _hub is None:
            _hub = ReviewstageHub()
            # store hook 接 hub
            try:
                store = get_store()
                store.subscribe(_hub.on_store_event)
            except Exception:  # noqa: BLE001
                _log.exception("hub attach to store failed")
        return _hub


# ────────────────────────────────────────────────────────────────────────
# Pydantic schemas
# ────────────────────────────────────────────────────────────────────────


class CreateMaterialBody(BaseModel):
    kind: str = Field(..., min_length=1, max_length=120)
    tier: str = Field(..., min_length=1, max_length=120)
    title: str = Field(..., min_length=1, max_length=200)
    source_subagent_id: str | None = None
    source_plan_id: str | None = None
    file_relpath: str | None = None
    inline_content: str | None = None
    annotations_allowed: bool = True
    # 自由元数据袋。网页审阅材料用它携带实时 URL: extra={"live_url": "/walker-game/", "route": "/"}。
    extra: dict[str, Any] | None = None


class ReviewCaptureBody(BaseModel):
    capture_kind: str = Field(..., pattern="^(element_comment|page_snapshot|debug_start)$")
    title: str | None = Field(default=None, max_length=200)
    comment: str = Field(default="", max_length=20000)
    author: str = Field(default="user", max_length=80)
    url: str = Field(default="", max_length=2000)
    route: str = Field(default="", max_length=2000)
    active_tab: dict[str, Any] | None = None
    target: dict[str, Any] | None = None
    page: dict[str, Any] | None = None
    text_snapshot: str | None = Field(default=None, max_length=80000)
    dom_snapshot: str | None = Field(default=None, max_length=240000)
    debug_allowed: bool = False


class VerdictBody(BaseModel):
    # Phase 2 步骤 1 (后端 verdict 字段对齐):
    # 字段名是 reason — 前端 POST body 必须用 "reason", 不是 "comment".
    # 历史脚本误用 comment 会被 Pydantic 丢弃, set_verdict 拿到 reason="" 默认.
    # 真要"评论"用单独的 /comment 端点 (CommentBody.content).
    verdict: str = Field(..., pattern="^(accepted|rejected|blocked|pending)$")
    by: str = "user"
    reason: str = ""


class CommentBody(BaseModel):
    content: str = Field(..., min_length=1)
    author: str = "user"
    target: dict[str, Any] | None = None


class CommentsFileAppendBody(BaseModel):
    content: str = Field(..., min_length=1)
    author: str = "user"
    anchor: str | None = None
    title: str | None = None


class ActiveMaterialBody(BaseModel):
    material_id: str = Field(..., min_length=1, max_length=200)


class AnnotationBody(BaseModel):
    content: str = Field(..., min_length=1)
    kind: str = Field(default="ai", pattern="^(ai|user)$")
    author: str = "controller"
    target: dict[str, Any] | None = None


class TierBody(BaseModel):
    new_tier: str = Field(..., min_length=1, max_length=120)
    by: str = "user"


class MarkPushedBody(BaseModel):
    # Phase 2A: body 可选 — 兼容空 body / {"pushed": true} / {"reason": "..."}.
    # pushed 字段是占位 (现阶段只支持 mark pushed=True, 不支持 unpush). 主要拿 reason.
    pushed: bool = True
    reason: str = "manual_push"


class CommentFeedbackBody(BaseModel):
    status: str = Field(..., pattern="^(saved|delivered|read|to_todo|todo_done)$")
    by: str = "controller"
    note: str = ""


class CommentEditBody(BaseModel):
    content: str = Field(..., min_length=1)
    by: str = "user"


class BatchVerdictBody(BaseModel):
    ids: list[str] = Field(default_factory=list)
    verdict: str = Field(..., pattern="^(accepted|rejected|blocked|pending)$")
    by: str = "user"
    reason: str = ""


class BatchTierBody(BaseModel):
    ids: list[str] = Field(default_factory=list)
    new_tier: str = Field(..., min_length=1, max_length=120)
    by: str = "user"


# ────────────────────────────────────────────────────────────────────────
# Router
# ────────────────────────────────────────────────────────────────────────


reviewstage_router = APIRouter(prefix="/api/boss-sight/reviewstage", tags=["reviewstage"])


def _clip_text(value: Any, limit: int = 60000) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[truncated: {len(text) - limit} chars omitted]"


def _safe_fence(text: str, lang: str = "") -> str:
    safe = text.replace("```", "'''")
    return f"```{lang}\n{safe}\n```"


def _capture_title(body: ReviewCaptureBody) -> str:
    if body.title and body.title.strip():
        return body.title.strip()
    route = body.route or body.url or "current page"
    target = body.target or {}
    label = target.get("label") or target.get("selector") or ""
    if body.capture_kind == "element_comment":
        suffix = f": {label}" if label else ""
        return f"UI element comment{suffix}"[:200]
    if body.capture_kind == "debug_start":
        return f"Codex debug start: {route}"[:200]
    return f"UI page snapshot: {route}"[:200]


def _capture_markdown(body: ReviewCaptureBody) -> str:
    active_tab = body.active_tab or {}
    page = body.page or {}
    target = body.target or {}
    lines: list[str] = [
        f"# {_capture_title(body)}",
        "",
        "## Capture",
        f"- kind: `{body.capture_kind}`",
        f"- route: `{body.route or '-'}`",
        f"- url: `{body.url or '-'}`",
        f"- active_tab: `{active_tab.get('type', '-')}/{active_tab.get('id', '-')}`",
        f"- active_title: `{active_tab.get('title', '-')}`",
        f"- debug_allowed: `{bool(body.debug_allowed)}`",
        "",
    ]
    if body.comment.strip():
        lines.extend(["## User comment", body.comment.strip(), ""])
    if target:
        lines.extend(["## Target element", _safe_fence(json.dumps(target, ensure_ascii=False, indent=2), "json"), ""])
    if page:
        lines.extend(["## Page state", _safe_fence(json.dumps(page, ensure_ascii=False, indent=2), "json"), ""])
    if body.text_snapshot:
        lines.extend(["## Visible text snapshot", _safe_fence(_clip_text(body.text_snapshot, 60000)), ""])
    if body.dom_snapshot:
        lines.extend(["## DOM snapshot", _safe_fence(_clip_text(body.dom_snapshot, 120000), "html"), ""])
    return "\n".join(lines).strip() + "\n"


@reviewstage_router.get("")
async def list_materials(
    status: str | None = None,
    tier: str | None = None,
    plan_id: str | None = None,
    pushed_only: bool = False,
    include_archived: bool = False,
    archived_only: bool = False,
    limit: int = 200,
) -> dict[str, Any]:
    store = get_store()
    # 强制 invalidate cache — omni cli (subagent) 直写 fs, ccdaemon 进程
    # 内存 cache 不会自动 reload. 每次 list 都重读磁盘 (<1000 条 OK).
    store.reload()
    items = store.list(
        status=status, tier=tier, plan_id=plan_id, pushed_only=pushed_only,
        include_archived=include_archived or archived_only,
    )
    if archived_only:
        items = [m for m in items if getattr(m, "archived", False)]
    limit = max(1, min(int(limit), 500))
    return {
        "count": len(items),
        "items": [m.to_dict() for m in items[:limit]],
        "filter": {"status": status, "tier": tier, "plan_id": plan_id, "pushed_only": pushed_only},
    }


@reviewstage_router.get("/_stats")
async def material_stats() -> dict[str, Any]:
    """快速统计 — 给前端顶栏 badge 用."""
    store = get_store()
    all_items = store.list()
    by_status: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    mandatory_unaccepted = 0
    pushed_unread = 0
    for m in all_items:
        st = m.status.value if hasattr(m.status, "value") else m.status
        tr = m.tier.value if hasattr(m.tier, "value") else m.tier
        by_status[st] = by_status.get(st, 0) + 1
        by_tier[tr] = by_tier.get(tr, 0) + 1
        if tr == "mandatory" and st in {"pending", "rejected", "blocked"}:
            mandatory_unaccepted += 1
        if m.pushed_to_user and st == "pending":
            pushed_unread += 1
    return {
        "total": len(all_items),
        "by_status": by_status,
        "by_tier": by_tier,
        "mandatory_unaccepted": mandatory_unaccepted,
        "pushed_unread": pushed_unread,
    }


# 去重(2026-06-14): material 评论真源已迁到中心 authored store(Note)。读材料时把
# material 型 comment notes 取回成 comment 形态, MaterialDetail 不改即可继续渲染。
_NOTE_WRAPPER_KEYS = {"kind", "id", "material_id", "plan_id", "sub_kind", "sub_id",
                      "url", "route", "selector", "title", "locator"}


def _note_to_comment_dict(n: Any) -> dict[str, Any]:
    nt = n.target or {}
    ct = {k: v for k, v in nt.items() if k not in _NOTE_WRAPPER_KEYS}
    if nt.get("sub_kind"):
        ct["kind"] = nt["sub_kind"]
    if nt.get("sub_id"):
        ct["id"] = nt["sub_id"]
    return {
        "id": n.id, "content": n.content, "author": n.author, "target": ct,
        "created_at": n.created_at, "feedback_status": n.feedback_status,
        "feedback_history": n.feedback_history,
    }


def _attach_notes_to_materials(material_dicts: list[dict[str, Any]]) -> None:
    """把 material 型 comment notes(含迁移来的旧评论)就地写回每条 material 的 comments,
    并上尚未被迁移覆盖的旧 comments(按 src_comment_id 去重), 按时间正序。一次 list 批量摊销,
    供 get / WS snapshot / WS broadcast 三处共用 —— 保证前端无论从哪条路拿到的都是水合后的评论。"""
    if not material_dicts:
        return
    try:
        from ..authored.store import get_authored_store
        store = get_authored_store()
        store.reload()
        notes = [n for n in store.list(target_kind="material") if "comment" in (n.uses or [])]
    except Exception:  # noqa: BLE001
        return
    by_mid: dict[str, list[Any]] = {}
    for n in notes:
        nt = n.target or {}
        mid = nt.get("material_id") or nt.get("id")
        if mid:
            by_mid.setdefault(str(mid), []).append(n)
    for d in material_dicts:
        ns = by_mid.get(str(d.get("id"))) or []
        covered = {(n.extra or {}).get("src_comment_id") for n in ns}
        out = [_note_to_comment_dict(n) for n in ns]
        out.extend(c for c in (d.get("comments") or []) if c.get("id") not in covered)
        out.sort(key=lambda c: str(c.get("created_at") or ""))
        d["comments"] = out


@reviewstage_router.get("/{material_id}")
async def get_material(material_id: str) -> dict[str, Any]:
    store = get_store()
    m = store.get(material_id)
    if m is None:
        raise HTTPException(404, f"material {material_id} not found")
    d = m.to_dict()
    _attach_notes_to_materials([d])
    # 评论真源在中心 store; 仍暴露 material 文件绝对路径(历史评论 + 元数据)。
    d["json_path"] = str((store.root / f"{m.id}.json").resolve())
    return d


@reviewstage_router.post("")
async def create_material(body: CreateMaterialBody) -> dict[str, Any]:
    store = get_store()
    try:
        m = store.create(
            kind=body.kind, tier=body.tier, title=body.title,
            source_subagent_id=body.source_subagent_id,
            source_plan_id=body.source_plan_id,
            file_relpath=body.file_relpath,
            inline_content=body.inline_content,
            annotations_allowed=body.annotations_allowed,
            extra=body.extra,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return m.to_dict()


class FromPathBody(BaseModel):
    """#3f 把聊天里出现的文件路径变成审阅材料。path 可绝对、可相对工作区。"""

    path: str = Field(..., min_length=1, max_length=4000)
    title: str | None = Field(default=None, max_length=200)


_TEXT_INLINE_EXTS = {".md", ".markdown", ".txt", ".mdx"}
_FENCE_LANG = {
    ".py": "python", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".jsx": "jsx",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    ".css": "css", ".scss": "scss", ".html": "html", ".htm": "html",
    ".sh": "bash", ".ps1": "powershell", ".sql": "sql", ".go": "go", ".rs": "rust",
}
_SKIP_DIRS = {".git", "node_modules", "data", "dist", "build", ".venv", "venv",
              "__pycache__", ".mypy_cache", ".pytest_cache", "coverage", ".next",
              ".turbo", "site-packages", ".idea", ".vscode"}


def _resolve_existing_path(raw: str, ws: Path) -> Path | None:
    cleaned = raw.strip().strip('"').strip("'")
    if not cleaned:
        return None
    try:
        p = Path(cleaned)
        if p.is_absolute() and p.is_file():
            return p
        cand = (ws / cleaned)
        if cand.is_file():
            return cand
    except OSError:
        return None
    return None


def _material_from_file(store: MaterialStore, path: Path, title: str | None):
    ext = path.suffix.lower()
    kind = "html" if ext in {".html", ".htm"} else "markdown"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        text = f"(无法读取文件文本: {e})"
    text = _clip_text(text, 120000)
    if kind == "html":
        content = text
    elif ext in _TEXT_INLINE_EXTS:
        content = text
    else:
        lang = _FENCE_LANG.get(ext, "")
        content = f"# {path.name}\n\n来源: `{path}`\n\n{_safe_fence(text, lang)}\n"
    return store.create(
        kind=kind,
        tier="important",
        title=(title.strip() if title and title.strip() else path.name),
        inline_content=content,
        source_plan_id="cockpit/from-chat",
        annotations_allowed=True,
        extra={"from_path": str(path)},
    )


def _search_files_by_name(ws: Path, needle: str, limit: int = 8) -> list[dict[str, str]]:
    needle = needle.lower()
    if not needle:
        return []
    hits: list[dict[str, str]] = []
    visited = 0
    for dirpath, dirnames, filenames in os.walk(ws):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            visited += 1
            if needle in fn.lower():
                full = Path(dirpath) / fn
                try:
                    rel = str(full.relative_to(ws))
                except ValueError:
                    rel = str(full)
                hits.append({"path": str(full), "rel": rel, "name": fn})
                if len(hits) >= limit:
                    return hits
        if visited > 60000:  # 兜底: 别在超大工作区里走太久
            break
    return hits


@reviewstage_router.post("/from_path")
async def material_from_path(body: FromPathBody) -> dict[str, Any]:
    """#3f: 严格匹配到文件 → 直接建审阅材料; 匹配不上 → 按文件名快速搜出前几个候选返回。"""
    from omnicompany.core.config import omni_workspace_root
    ws = omni_workspace_root()
    store = get_store()
    resolved = _resolve_existing_path(body.path, ws)
    if resolved is not None:
        try:
            m = _material_from_file(store, resolved, body.title)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"matched": True, "material": m.to_dict()}
    name = Path(body.path.strip().strip('"').strip("'")).name
    candidates = _search_files_by_name(ws, name, limit=8)
    return {"matched": False, "candidates": candidates, "query": name}


@reviewstage_router.post("/capture")
async def capture_review_context(body: ReviewCaptureBody) -> dict[str, Any]:
    """Create a review material from a human UI capture.

    This keeps element comments, page snapshots, and explicit Codex debug
    starts in the same reviewstage loop as ordinary material feedback.
    """
    store = get_store()
    title = _capture_title(body)
    tier = "important" if body.capture_kind in {"element_comment", "debug_start"} or body.comment.strip() else "processual"
    extra = {
        "capture": {
            "kind": body.capture_kind,
            "url": body.url,
            "route": body.route,
            "active_tab": body.active_tab or {},
            "target": body.target or {},
            "page": body.page or {},
            "debug_allowed": bool(body.debug_allowed),
        },
    }
    try:
        m = store.create(
            kind=MaterialKind.markdown,
            tier=tier,
            title=title,
            source_plan_id="cockpit/user-capture",
            inline_content=_capture_markdown(body),
            annotations_allowed=True,
            extra=extra,
        )
        if body.comment.strip():
            # 圈选/快照/调试交接是基础交互, 必须快且独立。这里**不**走
            # normalize_comment_target —— 它会 build_entity_index 全量扫工作区(实测 ~5s),
            # 把一个基础捕获拖成几秒级阻塞。捕获评论极少用 @实体, 直接存原始 target(已含
            # selector/label/rect 等), 评论闭环不受影响。@实体解析留给常规审阅评论端点。
            store.add_comment(
                m.id,
                content=body.comment,
                author=body.author or "user",
                target=body.target or {},
            )
            m = store.get(m.id) or m
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    result = m.to_dict()
    # 给前端"复制"用: 该捕获材料落盘的绝对路径(含完整快照/圈选内容), agent 可直接读。
    try:
        result.setdefault("extra", {}).setdefault("capture", {})["saved_path"] = str(
            (get_store().root / f"{m.id}.json").resolve()
        )
    except Exception:  # noqa: BLE001
        pass
    return result


@reviewstage_router.post("/active")
async def set_active_material(body: ActiveMaterialBody) -> dict[str, Any]:
    """跨表面"激活材料"同步(三区化): 某表面(队列/材料页签)选中材料 → 在审阅 WS 流上回广播
    active_material 事件, 让别的 webview(评论次级侧栏/编辑区材料页等)切到同一条。无副作用、不落库。"""
    get_hub().broadcast_active(body.material_id)
    return {"ok": True, "material_id": body.material_id}


@reviewstage_router.post("/{material_id}/verdict")
async def set_verdict(material_id: str, body: VerdictBody) -> dict[str, Any]:
    store = get_store()
    try:
        m = store.set_verdict(material_id, body.verdict, by=body.by, reason=body.reason)
    except KeyError:
        raise HTTPException(404, f"material {material_id} not found")
    return m.to_dict()


class ArchiveBody(BaseModel):
    archived: bool = True
    by: str = "user"


@reviewstage_router.post("/{material_id}/archive")
async def set_archived(material_id: str, body: ArchiveBody | None = None) -> dict[str, Any]:
    """软归档/还原一条材料(用户手动)。不删文件; 默认 list 不再返回。"""
    store = get_store()
    archived = body.archived if body is not None else True
    by = body.by if body is not None else "user"
    try:
        m = store.set_archived(material_id, archived, by=by)
    except KeyError:
        raise HTTPException(404, f"material {material_id} not found")
    return m.to_dict()


@reviewstage_router.post("/{material_id}/comment")
async def add_comment(material_id: str, body: CommentBody) -> dict[str, Any]:
    # 去重(2026-06-14): 评论统一进中心 authored store(Note), 不再写 Material.comments[]。
    # 读路径(MaterialDetail)同步改查 /notes/by-target/material/{id}。旧 comments[] 冻结为历史。
    store = get_store()
    m = store.get(material_id)
    if m is None:
        raise HTTPException(404, f"material {material_id} not found")
    ctarget = normalize_comment_target(body.content, body.target) or {}
    sub = {k: v for k, v in ctarget.items() if k not in ("kind", "id")}
    target = {
        "kind": "material", "id": material_id, "material_id": material_id,
        "plan_id": getattr(m, "source_plan_id", None),
        "sub_kind": ctarget.get("kind"), "sub_id": ctarget.get("id"), **sub,
    }
    from ..authored.store import get_authored_store
    n = get_authored_store().create(
        content=body.content, author=body.author, target=target, uses=["comment"],
    )
    # 回成 comment 形态(兼容旧调用取 id/content/feedback_status)
    return {**n.to_dict(), "comment_id": n.id}


@reviewstage_router.get("/{material_id}/comments-file")
async def get_comments_file(material_id: str, title: str | None = None) -> dict[str, Any]:
    """每材料一个评论 markdown 文件: 读内容 + 绝对路径(供前端渲染 / VSCode 打开)。
    不进 Comment 数组、不发 store 事件、不唤起总控(用户 2026-06-13)。"""
    store = get_store()
    content = store.read_comments_file(material_id, title=title)
    path = store.comments_file_path(material_id)
    return {
        "material_id": material_id,
        "content": content,
        "path": str(path),
        "abs_path": str(path.resolve()),
        "exists": path.exists(),
    }


@reviewstage_router.post("/{material_id}/comments-file")
async def append_comments_file(material_id: str, body: CommentsFileAppendBody) -> dict[str, Any]:
    """追加一条评论到该材料的 markdown 文件(一个 `## [时间]` 段)。不唤起总控。

    去重(2026-06-14): 评论真源统一进中心 authored store —— 先建一条 material 型 Note(真源),
    .md 文件降级为给 VSCode 直接看的镜像视图, 不再是独立数据岛(消除"审阅台 .md 评论"重复入口)。"""
    store = get_store()
    try:
        from ..authored.store import get_authored_store
        m = store.get(material_id)
        get_authored_store().create(
            content=body.content, author=body.author or "user",
            target={"kind": "material", "id": material_id, "material_id": material_id,
                    "plan_id": getattr(m, "source_plan_id", None) if m else None},
            uses=["comment"], extra={"src": "comments-file"},
        )
    except Exception:  # noqa: BLE001
        pass  # 中心 store 落库失败不挡 .md 镜像写入(向后兼容)
    try:
        content = store.append_comment_block(
            material_id, body.content, author=body.author, anchor=body.anchor, title=body.title,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    path = store.comments_file_path(material_id)
    return {"material_id": material_id, "content": content, "path": str(path), "abs_path": str(path.resolve())}


class CommentsFileWriteBody(BaseModel):
    content: str = ""


@reviewstage_router.put("/{material_id}/comments-file")
async def write_comments_file(material_id: str, body: CommentsFileWriteBody) -> dict[str, Any]:
    """整文件替换该材料的评论 .md(就地编辑/删除某条评论后存回)。不唤起总控。"""
    store = get_store()
    content = store.write_comments_file(material_id, body.content)
    path = store.comments_file_path(material_id)
    return {"material_id": material_id, "content": content, "path": str(path), "abs_path": str(path.resolve())}


@reviewstage_router.post("/{material_id}/comments/{comment_id}/feedback")
async def set_comment_feedback(
    material_id: str,
    comment_id: str,
    body: CommentFeedbackBody,
) -> dict[str, Any]:
    # 去重后评论是 Note(id 形如 note_xxx); 反馈转发到中心 store
    if comment_id.startswith("note_"):
        from ..authored.store import get_authored_store
        try:
            n = get_authored_store().update(comment_id, feedback_status=body.status, by=body.by)
        except KeyError as e:
            raise HTTPException(404, f"note not found: {e}") from e
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {**n.to_dict(), "comment_id": n.id}
    store = get_store()
    if body.status not in COMMENT_FEEDBACK_STATUSES:
        raise HTTPException(400, f"invalid comment feedback status: {body.status}")
    try:
        c = store.set_comment_feedback(
            material_id,
            comment_id,
            status=body.status,
            by=body.by,
            note=body.note,
        )
    except KeyError as e:
        raise HTTPException(404, f"material/comment not found: {e}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return c.to_dict()


@reviewstage_router.patch("/{material_id}/comments/{comment_id}")
async def edit_comment(material_id: str, comment_id: str, body: CommentEditBody) -> dict[str, Any]:
    """改一条已存评论的正文(存后修改)。不改状态、不发总控。"""
    store = get_store()
    try:
        c = store.edit_comment(material_id, comment_id, content=body.content, by=body.by)
    except KeyError as e:
        raise HTTPException(404, f"material/comment not found: {e}") from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return c.to_dict()


@reviewstage_router.post("/{material_id}/annotation")
async def add_annotation(material_id: str, body: AnnotationBody) -> dict[str, Any]:
    store = get_store()
    try:
        a = store.add_annotation(
            material_id, content=body.content, kind=body.kind,
            author=body.author, target=body.target,
        )
    except KeyError:
        raise HTTPException(404, f"material {material_id} not found")
    except PermissionError as e:
        raise HTTPException(403, str(e))
    return a.to_dict()


@reviewstage_router.post("/{material_id}/tier")
async def set_tier(material_id: str, body: TierBody) -> dict[str, Any]:
    store = get_store()
    try:
        m = store.adjust_tier(material_id, new_tier=body.new_tier, by=body.by)
    except KeyError:
        raise HTTPException(404, f"material {material_id} not found")
    return m.to_dict()


@reviewstage_router.post("/{material_id}/mark_pushed")
async def mark_pushed(material_id: str, body: MarkPushedBody | None = None) -> dict[str, Any]:
    """Phase 2A: 标记 material 已推送给人 (set pushed_to_user=True + emit 'pushed').

    body 可选: 空 / {"pushed": true} / {"pushed": true, "reason": "..."}.
    store.mark_pushed 内部已 _notify("pushed") → hub broadcast → WS 推前端.
    """
    store = get_store()
    reason = body.reason if body is not None else "manual_push"
    try:
        m = store.mark_pushed(material_id, reason=reason)
    except KeyError:
        raise HTTPException(404, f"material {material_id} not found")
    return m.to_dict()


@reviewstage_router.delete("/{material_id}")
async def delete_material(material_id: str) -> dict[str, Any]:
    store = get_store()
    ok = store.delete(material_id)
    if not ok:
        raise HTTPException(404, f"material {material_id} not found")
    return {"ok": True, "deleted": material_id}


class BatchDeleteBody(BaseModel):
    """批量删 material. 默认只删非 pending (避免误清正待审阅).
    传 include_pending=True 才会真清空全部.
    """

    include_pending: bool = False
    ids: list[str] = Field(default_factory=list)
    status: MaterialStatus | str | None = None  # 仅删指定状态
    tier: MaterialTier | str | None = None      # 仅删指定 tier
    plan_id: str | None = None
    pushed_only: bool = False


@reviewstage_router.post("/batch_delete")
async def batch_delete(body: BatchDeleteBody) -> dict[str, Any]:
    """批量删 material — 用户"清空所有审阅材料"按钮的后端."""
    store = get_store()
    if body.ids:
        items = [m for mid in body.ids if (m := store.get(mid)) is not None]
        found = {m.id for m in items}
        not_found = [mid for mid in body.ids if mid not in found]
    else:
        items = store.list(
            status=body.status,
            tier=body.tier,
            plan_id=body.plan_id,
            pushed_only=body.pushed_only,
        )
        not_found = []
    deleted: list[str] = []
    skipped_pending: int = 0
    for m in items:
        status_v = m.status.value if hasattr(m.status, "value") else m.status
        if not body.include_pending and status_v == "pending" and body.status is None:
            skipped_pending += 1
            continue
        if store.delete(m.id):
            deleted.append(m.id)
    return {
        "ok": True,
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
        "skipped_pending": skipped_pending,
        "not_found": not_found,
    }


@reviewstage_router.post("/batch_verdict")
async def batch_verdict(body: BatchVerdictBody) -> dict[str, Any]:
    store = get_store()
    changed: list[str] = []
    not_found: list[str] = []
    skipped: list[dict[str, str]] = []
    for mid in body.ids:
        try:
            store.set_verdict(mid, body.verdict, by=body.by, reason=body.reason)
            changed.append(mid)
        except KeyError:
            not_found.append(mid)
        except Exception as e:  # noqa: BLE001
            skipped.append({"id": mid, "error": str(e)})
    return {
        "ok": True,
        "changed_count": len(changed),
        "changed_ids": changed,
        "not_found": not_found,
        "skipped": skipped,
    }


@reviewstage_router.post("/batch_tier")
async def batch_tier(body: BatchTierBody) -> dict[str, Any]:
    store = get_store()
    changed: list[str] = []
    not_found: list[str] = []
    skipped: list[dict[str, str]] = []
    for mid in body.ids:
        try:
            store.adjust_tier(mid, new_tier=body.new_tier, by=body.by)
            changed.append(mid)
        except KeyError:
            not_found.append(mid)
        except Exception as e:  # noqa: BLE001
            skipped.append({"id": mid, "error": str(e)})
    return {
        "ok": True,
        "changed_count": len(changed),
        "changed_ids": changed,
        "not_found": not_found,
        "skipped": skipped,
    }


@reviewstage_router.get("/{material_id}/file")
async def get_material_file(material_id: str):
    store = get_store()
    m = store.get(material_id)
    if m is None:
        raise HTTPException(404, f"material {material_id} not found")
    if m.inline_content is not None and not m.file_relpath:
        # inline 直接返
        kind = m.kind.value if hasattr(m.kind, "value") else m.kind
        media_type = {
            "markdown": "text/markdown; charset=utf-8",
            "html": "text/html; charset=utf-8",
            "key_question": "application/json; charset=utf-8",
        }.get(kind, "text/plain; charset=utf-8")
        return PlainTextResponse(content=m.inline_content, media_type=media_type)
    fp = store.resolve_file_path(m)
    if fp is None:
        raise HTTPException(404, f"material {material_id} file missing")
    kind = m.kind.value if hasattr(m.kind, "value") else m.kind
    media_type = None
    if kind == "image":
        ext = fp.suffix.lower()
        media_type = {
            ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml", ".gif": "image/gif", ".webp": "image/webp",
        }.get(ext)
    elif kind == "html":
        media_type = "text/html; charset=utf-8"
    elif kind == "markdown":
        media_type = "text/markdown; charset=utf-8"
    return FileResponse(str(fp), media_type=media_type)


@reviewstage_router.websocket("/stream")
async def reviewstage_stream(ws: WebSocket) -> None:
    """实时事件流. 服务器推: {event_type, material}. client 不需要发任何东西."""
    hub = get_hub()
    if hub._loop is None:
        hub.attach_loop(asyncio.get_running_loop())
    await hub.add(ws)
    # 发一个 snapshot 让 client 直接渲染
    try:
        store = get_store()
        items = [m.to_dict() for m in store.list()]
        _attach_notes_to_materials(items)  # 评论真源在中心 store, snapshot 出去前水合
        snapshot = {
            "event_type": "snapshot",
            "items": items,
        }
        await ws.send_json(snapshot)
        # 维持连接
        while True:
            try:
                # client 偶尔发 ping, 收掉
                await asyncio.wait_for(ws.receive_text(), timeout=60.0)
            except asyncio.TimeoutError:
                # 主动 ping
                await ws.send_json({"event_type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        _log.exception("reviewstage WS error")
    finally:
        hub.remove(ws)


__all__ = ["reviewstage_router", "get_store", "get_hub"]
