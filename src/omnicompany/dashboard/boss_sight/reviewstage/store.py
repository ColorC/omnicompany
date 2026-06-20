# [OMNI] origin=ai-ide ts=2026-05-24 type=infra
# [OMNI] material_id="material:dashboard.boss_sight.reviewstage.store.py"
"""MaterialStore — 审阅台 material 持久化.

落实块 4 B4-R1.

设计:
- 单 Material 一份 JSON 在 `data/boss_sight/reviewstage/<material_id>.json`
- 实际内容文件 (image/html/markdown) 在 `data/boss_sight/reviewstage/files/<material_id>.<ext>`
- atomic write: tempfile + rename (Windows 兼容)
- 不引入数据库, 走文件系统 + 内存索引 + best-effort lock; 用户级使用规模够 (审阅台
  通常 <1000 条 material, 不需要 sqlite)
- subscribers 机制: routes.py 的 WS 端点订阅 store, store 写盘 + 状态变化时同步通知

数据模型:
- MaterialKind: image / markdown / html / key_question (Phase A 4 类, 用户原文 §4.2)
- MaterialTier: mandatory / important / processual / ignored (4 级, 用户原文 §4.6)
- MaterialStatus: pending / accepted / rejected / blocked (审阅状态)
- Annotation: AI 批注, 跟正式内容分离 (§4.4.1 / §4.5)
- Comment: 用户评论 (§4.4 / §4.5)
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterable

from omnicompany.packages.services._core.omnicompany.formats import REVIEW_MATERIAL
from omnicompany.packages.services._core.omnicompany.material_events import publish_material_event
from omnicompany.protocol.format import FormatRegistry

from .content_validators import TEXT_KINDS, validate_material_structure
from .material_types import (
    normalize_review_kind,
    normalize_review_tier,
    review_material_tags,
)

_log = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────
# Enums
# ────────────────────────────────────────────────────────────────────────


class MaterialKind(str, Enum):
    """Legacy built-in review material kinds.

    新 kind 的权威扩展路径是注册带 `review.kind.*` tag 的 Format, 不是继续改本 enum。
    """
    image = "image"
    markdown = "markdown"
    html = "html"
    key_question = "key_question"
    # 块 5 B5-R1: §4.2.5 自定义网页模板元编程
    # inline_content 是 JSON 字符串, extra.data_schema_id 指定渲染模板
    custom_web_template = "custom_web_template"


class MaterialTier(str, Enum):
    """4 级 — 用户原文 §4.6.1-4."""
    mandatory = "mandatory"      # 必验收 (阻断)
    important = "important"      # 重要
    processual = "processual"    # 有意义过程性
    ignored = "ignored"          # 其余 / 不审阅


class MaterialStatus(str, Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    blocked = "blocked"      # 必验收发现严重偏差, 需总控调整后再 submit 新版本


class AnnotationKind(str, Enum):
    """批注种类: ai 是总控自动加的, user 是用户手动加的."""
    ai = "ai"
    user = "user"


# ────────────────────────────────────────────────────────────────────────
# Dataclasses
# ────────────────────────────────────────────────────────────────────────


# saved = 已保存但未送达总控(新评论默认). 只有用户显式"发送"才转 delivered。
# saved 不在 cockpit 的未解决/优先白名单里, 故对总控天然隐身 —— 保存评论 ≠ 使用总控。
COMMENT_FEEDBACK_STATUSES = {"saved", "delivered", "read", "to_todo", "todo_done"}


@dataclass
class Annotation:
    """AI 批注 / 用户高亮. 跟正式内容 DOM 分离 (§4.4.1).

    target 字段定位:
    - image: {"x": ..., "y": ..., "w": ..., "h": ...}  归一化 0-1
    - markdown: {"line_start": ..., "line_end": ...} 行号
    - html: {"selector": "..."} CSS 选择器 (圈选元素时)
    - key_question: {"question_index": ...}
    """
    id: str
    kind: AnnotationKind | str
    content: str
    target: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    author: str = "controller"  # controller / user / subagent

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value if isinstance(self.kind, AnnotationKind) else self.kind
        return d


@dataclass
class Comment:
    """用户对 material 的评论. 历史性内容跟正式内容分离 (§4.4.1)."""
    id: str
    content: str
    author: str  # user / controller / subagent
    target: dict[str, Any] = field(default_factory=dict)  # 同 Annotation.target, 可选定位
    created_at: str = ""
    feedback_status: str = "saved"  # 新评论默认只保存, 不自动发总控
    feedback_history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Material:
    """一条待审阅 material 完整状态."""

    id: str
    kind: MaterialKind | str
    tier: MaterialTier | str
    title: str
    status: MaterialStatus | str = MaterialStatus.pending
    # 来源 (§4.3 总控指定 / subagent 写入)
    source_subagent_id: str | None = None
    source_plan_id: str | None = None
    # 内容: 二选一. file_relpath = data/boss_sight/reviewstage/files/<basename> 相对工作目录
    # inline_content = 直接放数据库 (key_question 用 JSON, 短 markdown 也可)
    file_relpath: str | None = None
    inline_content: str | None = None
    # AI 批注 + 用户评论. annotations_allowed=False 时不显批注按钮 (§4.5: 小说类产物)
    annotations: list[Annotation] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    annotations_allowed: bool = True
    # 时间 + history
    created_at: str = ""
    updated_at: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    # 推送标记 (§2.10 总控主动推送)
    pushed_to_user: bool = False
    pushed_reason: str | None = None
    pushed_at: str | None = None
    # 软归档(用户手动): 不删文件, 默认 list 不返回; "已归档"筛选可还原。
    archived: bool = False
    # extra: 留给元编程 phase B
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "id": self.id,
            "kind": self.kind.value if isinstance(self.kind, MaterialKind) else self.kind,
            "tier": self.tier.value if isinstance(self.tier, MaterialTier) else self.tier,
            "title": self.title,
            "status": self.status.value if isinstance(self.status, MaterialStatus) else self.status,
            "source_subagent_id": self.source_subagent_id,
            "source_plan_id": self.source_plan_id,
            "file_relpath": self.file_relpath,
            "inline_content": self.inline_content,
            "annotations": [a.to_dict() for a in self.annotations],
            "comments": [c.to_dict() for c in self.comments],
            "annotations_allowed": self.annotations_allowed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "history": list(self.history),
            "pushed_to_user": self.pushed_to_user,
            "pushed_reason": self.pushed_reason,
            "pushed_at": self.pushed_at,
            "archived": self.archived,
            "extra": dict(self.extra),
        }
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Material:
        annotations = [
            Annotation(
                id=a.get("id", ""),
                kind=a.get("kind", "ai"),
                content=a.get("content", ""),
                target=a.get("target") or {},
                created_at=a.get("created_at", ""),
                author=a.get("author", "controller"),
            )
            for a in (d.get("annotations") or [])
        ]
        comments = [
            Comment(
                id=c.get("id", ""),
                content=c.get("content", ""),
                author=c.get("author", "user"),
                target=c.get("target") or {},
                created_at=c.get("created_at", ""),
                feedback_status=c.get("feedback_status") or "delivered",
                feedback_history=list(c.get("feedback_history") or []),
            )
            for c in (d.get("comments") or [])
        ]
        return cls(
            id=d["id"],
            kind=d.get("kind", "markdown"),
            tier=d.get("tier", "important"),
            title=d.get("title", ""),
            status=d.get("status", "pending"),
            source_subagent_id=d.get("source_subagent_id"),
            source_plan_id=d.get("source_plan_id"),
            file_relpath=d.get("file_relpath"),
            inline_content=d.get("inline_content"),
            annotations=annotations,
            comments=comments,
            annotations_allowed=bool(d.get("annotations_allowed", True)),
            created_at=d.get("created_at", ""),
            updated_at=d.get("updated_at", ""),
            history=list(d.get("history") or []),
            pushed_to_user=bool(d.get("pushed_to_user", False)),
            pushed_reason=d.get("pushed_reason"),
            pushed_at=d.get("pushed_at"),
            archived=bool(d.get("archived", False)),
            extra=dict(d.get("extra") or {}),
        )


# ────────────────────────────────────────────────────────────────────────
# Store
# ────────────────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str = "mat") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _atomic_write(path: Path, data: str) -> None:
    """tempfile + rename. Windows 兼容: 用同目录 tempfile + os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", delete=False,
        dir=str(path.parent), suffix=".tmp",
    )
    try:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
    finally:
        tmp.close()
    os.replace(tmp.name, str(path))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


class MaterialStore:
    """审阅台 material 持久化.

    Path layout:
        <root>/<material_id>.json     # Material metadata
        <root>/files/<basename>       # 实际内容文件 (image/html/markdown)

    Subscribers: store 写盘 + 状态转移时同步触发. 用于:
    - WS endpoint 实时推送
    - subagent.spawned 时阻断检查 (块 4 R8)
    """

    SUBDIR_FILES: ClassVar[str] = "files"

    def __init__(self, root: Path | str, *, format_registry: FormatRegistry | None = None) -> None:
        self.root = Path(root)
        self.files_dir = self.root / self.SUBDIR_FILES
        # 2026-06-13: 每材料一个评论 markdown 文件(用户自读自写/VSCode 直接编辑)。
        # 与 reviewstage Comment 数组分离 — 走 comments-file API, 不发 store 事件、不唤起总控。
        self.comments_dir = self.root / "comments"
        self.format_registry = format_registry
        self._lock = threading.RLock()
        self._cache: dict[str, Material] | None = None
        self._subscribers: list[Callable[[str, Material], None]] = []
        self.root.mkdir(parents=True, exist_ok=True)
        self.files_dir.mkdir(parents=True, exist_ok=True)
        self.comments_dir.mkdir(parents=True, exist_ok=True)

    # ── subscribe ─────────────────────────────────────────────────────

    def subscribe(self, callback: Callable[[str, Material], None]) -> None:
        """订阅写事件. callback(event_type, material) — 同步调用. event_type ∈
        {'created', 'updated', 'verdict_changed', 'comment_added', 'annotation_added',
        'pushed', 'deleted'}."""
        self._subscribers.append(callback)

    def _notify(self, event_type: str, material: Material) -> None:
        for cb in self._subscribers:
            try:
                cb(event_type, material)
            except Exception:  # noqa: BLE001
                _log.exception("MaterialStore subscriber failed: %s", event_type)

    # ── cache / load ─────────────────────────────────────────────────

    def _ensure_loaded(self) -> dict[str, Material]:
        if self._cache is None:
            self._cache = {}
            for p in self.root.glob("*.json"):
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    m = Material.from_dict(data)
                    self._cache[m.id] = m
                except (OSError, json.JSONDecodeError, KeyError):
                    _log.exception("MaterialStore: skip corrupt %s", p)
        return self._cache

    def reload(self) -> None:
        """强制清缓存, 下次 _ensure_loaded 真重新读盘. 测试/外部修改时用."""
        with self._lock:
            self._cache = None

    # ── CRUD ─────────────────────────────────────────────────────────

    def _persist(self, m: Material) -> None:
        m.updated_at = _now_iso()
        path = self.root / f"{m.id}.json"
        _atomic_write(path, json.dumps(m.to_dict(), ensure_ascii=False, indent=2))

    # ── 评论文件(每材料一个 markdown) ─────────────────────────────────
    # 用户 2026-06-13: 评论不进 Comment 数组、不自动发总控; 落一个 .md, 追加式,
    # 用户可在 VSCode 直接编辑; dashboard 渲染并提供追加/打开。每条评论 = 一个 `## [时间]` 段。

    def comments_file_path(self, material_id: str) -> Path:
        safe = "".join(ch for ch in material_id if ch.isalnum() or ch in "_-")
        return self.comments_dir / f"{safe or 'unknown'}.md"

    def write_comments_file(self, material_id: str, content: str) -> str:
        """整文件替换(就地编辑/删除某条评论用)。content = 用户改后的完整 .md。"""
        text = (content or "").strip()
        _atomic_write(self.comments_file_path(material_id), text + ("\n" if text else ""))
        return text

    def read_comments_file(self, material_id: str, *, title: str | None = None) -> str:
        # 文件即真源, 纯评论内容; 不预置标题/说明文字(那些是网页的事, 不塞进文件)。
        path = self.comments_file_path(material_id)
        if path.exists():
            try:
                return path.read_text(encoding="utf-8")
            except OSError:
                return ""
        return ""

    def append_comment_block(
        self, material_id: str, content: str, *, author: str = "user",
        anchor: str | None = None, title: str | None = None,
    ) -> str:
        content = (content or "").strip()
        if not content:
            raise ValueError("comment content is empty")
        base = self.read_comments_file(material_id, title=title)
        anchor_line = f"\n> 锚点: {anchor.strip()}\n" if anchor and anchor.strip() else ""
        block = f"## [{_now_iso()}] {author}{anchor_line}\n{content}\n"
        new_text = (base.rstrip() + "\n\n" + block) if base.strip() else block
        _atomic_write(self.comments_file_path(material_id), new_text)
        return new_text

    def _resolve_declared_file_path(self, file_relpath: str) -> Path:
        path = Path(file_relpath)
        if path.is_absolute():
            return path
        root = self.root.resolve()
        candidate = (self.root / path).resolve()
        if not _is_relative_to(candidate, root):
            raise ValueError("file_relpath must stay under reviewstage root")
        return candidate

    def _prepare_declared_file(self, file_relpath: str, inline_content: str | None) -> None:
        path = self._resolve_declared_file_path(file_relpath)
        if inline_content is None:
            if not path.is_file():
                raise ValueError(f"file_relpath does not exist: {file_relpath}")
            return
        if Path(file_relpath).is_absolute():
            raise ValueError("inline_content cannot write to absolute file_relpath")
        _atomic_write(path, inline_content)

    def _read_declared_file_text(self, file_relpath: str, *, cap: int = 120_000) -> str | None:
        path = self._resolve_declared_file_path(file_relpath)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        return text[:cap]

    def create(
        self,
        *,
        kind: MaterialKind | str,
        tier: MaterialTier | str,
        title: str,
        source_subagent_id: str | None = None,
        source_plan_id: str | None = None,
        file_relpath: str | None = None,
        inline_content: str | None = None,
        annotations_allowed: bool = True,
        extra: dict[str, Any] | None = None,
    ) -> Material:
        """新建 material 落盘 + emit 'created'."""
        # 校验: enum 只保留内置兼容; 扩展 kind/tier 走 Format tags。
        kind_text = normalize_review_kind(kind, self.format_registry)
        tier_text = normalize_review_tier(tier, self.format_registry)
        try:
            kind_v: MaterialKind | str = MaterialKind(kind_text)
        except ValueError:
            kind_v = kind_text
        try:
            tier_v: MaterialTier | str = MaterialTier(tier_text)
        except ValueError:
            tier_v = tier_text
        if not title.strip():
            raise ValueError("title required")
        if file_relpath is None and inline_content is None:
            raise ValueError("must provide file_relpath or inline_content")
        if file_relpath is not None:
            self._prepare_declared_file(file_relpath, inline_content)
        extra_v = dict(extra or {})
        validation_content = inline_content
        if validation_content is None and file_relpath is not None and kind_text in TEXT_KINDS:
            validation_content = self._read_declared_file_text(file_relpath)
        structure_warnings = validate_material_structure(
            kind=kind_text,
            title=title.strip(),
            inline_content=validation_content,
            file_relpath=file_relpath,
            extra=extra_v,
        )
        if structure_warnings:
            extra_v["structure_warnings"] = structure_warnings

        with self._lock:
            self._ensure_loaded()
            mid = _new_id("mat")
            now = _now_iso()
            history = [{"event": "created", "at": now}]
            if structure_warnings:
                history.append({
                    "event": "structure_warning",
                    "at": now,
                    "count": len(structure_warnings),
                    "warnings": structure_warnings,
                })
            m = Material(
                id=mid,
                kind=kind_v,
                tier=tier_v,
                title=title.strip(),
                status=MaterialStatus.pending,
                source_subagent_id=source_subagent_id,
                source_plan_id=source_plan_id,
                file_relpath=file_relpath,
                inline_content=inline_content,
                annotations_allowed=annotations_allowed,
                created_at=now,
                updated_at=now,
                history=history,
                extra=extra_v,
            )
            self._cache[mid] = m
            self._persist(m)
            self._notify("created", m)
            _log.info("MaterialStore created: id=%s kind=%s tier=%s", mid, kind_text, tier_text)
            event_payload = m.to_dict()
        publish_material_event(
            REVIEW_MATERIAL.id,
            event_payload,
            source="boss_sight.reviewstage",
            tags=review_material_tags(kind_text, tier_text),
        )
        return m

    def get(self, material_id: str) -> Material | None:
        with self._lock:
            return self._ensure_loaded().get(material_id)

    def list(
        self,
        *,
        status: MaterialStatus | str | None = None,
        tier: MaterialTier | str | None = None,
        plan_id: str | None = None,
        subagent_id: str | None = None,
        pushed_only: bool = False,
        include_archived: bool = False,
    ) -> list[Material]:
        with self._lock:
            items = list(self._ensure_loaded().values())
        # 默认不返回已软归档的材料; 只有"已归档"视图显式 include_archived 才带上。
        if not include_archived:
            items = [m for m in items if not getattr(m, "archived", False)]
        if status is not None:
            sv = status.value if isinstance(status, MaterialStatus) else status
            items = [m for m in items if (m.status.value if isinstance(m.status, MaterialStatus) else m.status) == sv]
        if tier is not None:
            tv = tier.value if isinstance(tier, MaterialTier) else tier
            items = [m for m in items if (m.tier.value if isinstance(m.tier, MaterialTier) else m.tier) == tv]
        if plan_id is not None:
            items = [m for m in items if m.source_plan_id == plan_id]
        if subagent_id is not None:
            items = [m for m in items if m.source_subagent_id == subagent_id]
        if pushed_only:
            items = [m for m in items if m.pushed_to_user]
        items.sort(key=lambda m: m.created_at, reverse=True)
        return items

    def set_verdict(
        self,
        material_id: str,
        verdict: MaterialStatus | str,
        *,
        by: str = "user",
        reason: str = "",
    ) -> Material:
        """status 转移. 'rejected' / 'blocked' / 'accepted' / 重置回 'pending'.

        history 记一条 audit. emit 'verdict_changed'.
        """
        v = MaterialStatus(verdict) if not isinstance(verdict, MaterialStatus) else verdict
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            old_status = m.status.value if isinstance(m.status, MaterialStatus) else m.status
            m.status = v
            m.history.append({
                "event": "verdict",
                "from": old_status, "to": v.value,
                "by": by, "reason": reason, "at": _now_iso(),
            })
            self._persist(m)
            self._notify("verdict_changed", m)
            return m

    def set_archived(self, material_id: str, archived: bool, *, by: str = "user") -> Material:
        """软归档/还原。不删文件; 仅置 archived 标志, 默认 list 不再返回。"""
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            m.archived = bool(archived)
            m.history.append({
                "event": "archived" if archived else "unarchived",
                "by": by, "at": _now_iso(),
            })
            self._persist(m)
            self._notify("updated", m)
            return m

    def add_comment(
        self,
        material_id: str,
        *,
        content: str,
        author: str = "user",
        target: dict[str, Any] | None = None,
    ) -> Comment:
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            now = _now_iso()
            c = Comment(
                id=_new_id("cmt"),
                content=content.strip(),
                author=author,
                target=target or {},
                created_at=now,
                feedback_status="saved",  # 只保存, 不发总控; 用户显式发送时再转 delivered
                feedback_history=[{"status": "saved", "by": author, "at": now}],
            )
            m.comments.append(c)
            mentions = c.target.get("mentions") if isinstance(c.target, dict) else None
            mention_count = len(mentions) if isinstance(mentions, list) else 0
            m.history.append({
                "event": "comment",
                "by": author,
                "at": c.created_at,
                "mention_count": mention_count,
                "comment_id": c.id,
                "feedback_status": c.feedback_status,
            })
            self._persist(m)
            self._notify("comment_added", m)
            return c

    def set_comment_feedback(
        self,
        material_id: str,
        comment_id: str,
        *,
        status: str,
        by: str = "controller",
        note: str = "",
    ) -> Comment:
        if status not in COMMENT_FEEDBACK_STATUSES:
            raise ValueError(f"invalid comment feedback status: {status}")
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            comment = next((c for c in m.comments if c.id == comment_id), None)
            if comment is None:
                raise KeyError(comment_id)
            old = comment.feedback_status or "delivered"
            now = _now_iso()
            comment.feedback_status = status
            comment.feedback_history.append({
                "from": old,
                "status": status,
                "by": by,
                "note": note,
                "at": now,
            })
            m.history.append({
                "event": "comment_feedback",
                "comment_id": comment_id,
                "from": old,
                "to": status,
                "by": by,
                "note": note,
                "at": now,
            })
            self._persist(m)
            self._notify("updated", m)
            return comment

    def edit_comment(
        self,
        material_id: str,
        comment_id: str,
        *,
        content: str,
        by: str = "user",
    ) -> Comment:
        """改一条已存评论的正文。不改 feedback_status(saved 仍 saved), 不唤起总控。"""
        content = (content or "").strip()
        if not content:
            raise ValueError("comment content is empty")
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            comment = next((c for c in m.comments if c.id == comment_id), None)
            if comment is None:
                raise KeyError(comment_id)
            now = _now_iso()
            old = comment.content
            comment.content = content
            comment.feedback_history.append({
                "event": "edit", "by": by, "at": now,
                "old_len": len(old), "new_len": len(content),
            })
            m.history.append({
                "event": "comment_edit", "comment_id": comment_id, "by": by, "at": now,
            })
            self._persist(m)
            self._notify("updated", m)  # 非 comment_added: 不触发任何总控路径
            return comment

    def add_annotation(
        self,
        material_id: str,
        *,
        content: str,
        kind: AnnotationKind | str = AnnotationKind.ai,
        author: str = "controller",
        target: dict[str, Any] | None = None,
    ) -> Annotation:
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            if not m.annotations_allowed:
                raise PermissionError(
                    f"material {material_id} has annotations_allowed=False; "
                    "this material kind (e.g. 小说) does not accept annotations (§4.5)"
                )
            k = AnnotationKind(kind) if not isinstance(kind, AnnotationKind) else kind
            a = Annotation(
                id=_new_id("ann"),
                kind=k,
                content=content.strip(),
                target=target or {},
                created_at=_now_iso(),
                author=author,
            )
            m.annotations.append(a)
            m.history.append({"event": "annotation", "by": author, "at": a.created_at})
            self._persist(m)
            self._notify("annotation_added", m)
            return a

    def mark_pushed(self, material_id: str, *, reason: str) -> Material:
        """块 4 R7: 总控调 push_material_to_user 时打标记 + emit 'pushed'."""
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            m.pushed_to_user = True
            m.pushed_reason = reason
            m.pushed_at = _now_iso()
            m.history.append({"event": "pushed", "reason": reason, "at": m.pushed_at})
            self._persist(m)
            self._notify("pushed", m)
            return m

    def adjust_tier(
        self, material_id: str, *, new_tier: MaterialTier | str, by: str = "user",
    ) -> Material:
        """§4.6.5 准则可调: 用户/总控调 material 分级. history 留 audit."""
        tier_text = normalize_review_tier(new_tier, self.format_registry)
        try:
            nt: MaterialTier | str = MaterialTier(tier_text)
        except ValueError:
            nt = tier_text
        with self._lock:
            m = self.get(material_id)
            if m is None:
                raise KeyError(material_id)
            old = m.tier.value if isinstance(m.tier, MaterialTier) else m.tier
            m.tier = nt
            m.history.append({
                "event": "tier_change", "from": old, "to": tier_text,
                "by": by, "at": _now_iso(),
            })
            self._persist(m)
            self._notify("updated", m)
            return m

    def delete(self, material_id: str) -> bool:
        with self._lock:
            m = self.get(material_id)
            if m is None:
                return False
            (self.root / f"{material_id}.json").unlink(missing_ok=True)
            # 也删 file 内容
            if m.file_relpath:
                f = self.resolve_file_path(m)
                if f is not None and f.is_file():
                    f.unlink(missing_ok=True)
            self._cache.pop(material_id, None)
            self._notify("deleted", m)
            return True

    # ── 阻断查询 (块 4 R8 联通块 3 R8 硬 guard) ───────────────────────

    def has_unaccepted_mandatory(self, plan_id: str | None) -> list[Material]:
        """块 4 R8: 检查某 plan 有没有未通过的 mandatory material.

        spawn_subagent 启动前调这个. 返回有阻断的 material 列表 (空则可放行).
        """
        if not plan_id:
            return []
        blockers: list[Material] = []
        for m in self.list(plan_id=plan_id, tier=MaterialTier.mandatory):
            st = m.status.value if isinstance(m.status, MaterialStatus) else m.status
            if st in {"pending", "rejected", "blocked"}:
                blockers.append(m)
        return blockers

    # ── 写 file (image / html / md) ──────────────────────────────────

    def stage_file_from_path(self, src: Path | str, *, suggested_ext: str = "") -> str:
        """从工作区某文件拷贝到 files/<id>.<ext>, 返回 file_relpath (相对 store root)."""
        src_path = Path(src)
        if not src_path.is_file():
            raise FileNotFoundError(str(src_path))
        ext = suggested_ext or src_path.suffix or ".bin"
        if not ext.startswith("."):
            ext = "." + ext
        fname = f"{_new_id('file')}{ext}"
        dest = self.files_dir / fname
        shutil.copy2(src_path, dest)
        return f"{self.SUBDIR_FILES}/{fname}"

    def stage_file_from_bytes(self, data: bytes, *, ext: str) -> str:
        """直接把字节流落到 files/<id>.<ext>."""
        if not ext.startswith("."):
            ext = "." + ext
        fname = f"{_new_id('file')}{ext}"
        dest = self.files_dir / fname
        dest.write_bytes(data)
        return f"{self.SUBDIR_FILES}/{fname}"

    def resolve_file_path(self, m: Material) -> Path | None:
        """拿 material 文件绝对路径."""
        if not m.file_relpath:
            return None
        p = Path(m.file_relpath)
        if p.is_absolute():
            return p if p.is_file() else None
        try:
            candidate = self._resolve_declared_file_path(m.file_relpath)
        except ValueError:
            return None
        return candidate if candidate.is_file() else None
