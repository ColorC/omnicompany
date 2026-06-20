# [OMNI] origin=ai-ide ts=2026-06-03 type=infra
"""捕获(圈选/快照/调试交接)落盘 + 批量交给总控读取 的后端路由。

挂载于 /api/boss-sight/captures(跟 reviewstage 完全分开 —— 用户明示捕获不进审阅队列)。

- POST   /api/boss-sight/captures           保存一条捕获到 data/boss_sight/captures/pending/<ts>.md
- GET    /api/boss-sight/captures           列 pending 数量 + 文件
- POST   /api/boss-sight/captures/dispatch  把 pending/* 移到 batch_<ts>/, 注入一条消息给唯一总控让其 Read 处理
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from omnicompany.packages.services._core.omnicompany.formats import CAPTURE
from omnicompany.packages.services._core.omnicompany.material_events import publish_material_event

captures_router = APIRouter(prefix="/api/boss-sight/captures", tags=["captures"])


def _captures_root() -> Path:
    # 用户明示 2026-06-04: 路径太长, 在 workspace 下放一个专门文件夹。
    # omni_workspace_root() = .../workspace/omnicompany → .parent = .../workspace。
    # 复制文件直接落根(最短路径); 提交进 pending/ 子目录; dispatch 批次 batch_<ts>/。
    from omnicompany.core.config import omni_workspace_root
    return omni_workspace_root().parent / "captures"


def _pending_dir() -> Path:
    d = _captures_root() / "pending"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _clips_dir() -> Path:
    # 「复制」把完整内容(含大段 HTML)写这里(captures 根, 路径最短), 剪贴板只放文件路径一行
    # (用户明示 2026-06-04: 还是太长, 就留文件路径)。clips 不计入「待处理」、不进 dispatch 批次。
    d = _captures_root()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _capture_filename(body: "CaptureBody", ts: str) -> str:
    """文件名体现一点元素(用户明示 2026-06-04), 但保持短: <短名>-<HHMMSS>-<3hex>.md。"""
    t = body.target or {}
    raw = str(t.get("label") or t.get("selector") or body.capture_kind)
    slug = re.sub(r"[^0-9A-Za-z_-]+", "-", raw).strip("-")[:24] or body.capture_kind
    hhmmss = ts.split("T")[-1] if "T" in ts else ts
    return f"{slug}-{hhmmss}-{uuid.uuid4().hex[:3]}.md"


class CaptureBody(BaseModel):
    capture_kind: str = Field(..., pattern="^(element_comment|page_snapshot|debug_start)$")
    title: str | None = Field(default=None, max_length=200)
    comment: str = Field(default="", max_length=20000)
    url: str = Field(default="", max_length=2000)
    route: str = Field(default="", max_length=2000)
    target: dict[str, Any] | None = None
    text_snapshot: str | None = Field(default=None, max_length=80000)
    dom_snapshot: str | None = Field(default=None, max_length=240000)
    # 真实截图: 由能截到自身的同文档表面(如 vilo demo 自己 html2canvas)发来的 data:image/png;base64,...
    # dashboard 抓不到跨文档 iframe, 所以截图职责在被截的应用侧, 这里只负责落盘 + 挂到 page_element 札记。
    image_data_url: str | None = Field(default=None, max_length=8_000_000)
    # True(提交)= 存到 pending 进 dispatch 批次; False(复制)= 存到 clips 只为拿文件链接。
    enqueue: bool = True


_KIND_LABEL = {
    "element_comment": "圈选元素",
    "page_snapshot": "页面快照",
    "debug_start": "Codex 调试交接",
}


def _safe_fence(text: str, lang: str = "") -> str:
    body = str(text).replace("```", "`\u200b``")
    return f"```{lang}\n{body}\n```"


def _save_image_data_url(data_url: str, ts: str) -> str | None:
    """\u628a data:image/png;base64,... \u843d\u5230 captures \u6839\u4e0b\u7684\u56fe\u7247\u6587\u4ef6, \u8fd4\u56de\u76f8\u5bf9 captures \u6839\u7684\u8def\u5f84
    (\u4f9b GET /file?path= \u8bfb\u53d6\u3001\u5199\u8fdb note.captures)\u3002\u89e3\u6790\u5931\u8d25\u8fd4\u56de None\u3002"""
    import base64
    import re as _re
    m = _re.match(r"^data:image/(png|jpeg|jpg|webp);base64,(.+)$", (data_url or "").strip(), _re.DOTALL)
    if not m:
        return None
    ext = "jpg" if m.group(1) in ("jpeg", "jpg") else m.group(1)
    try:
        raw = base64.b64decode(m.group(2), validate=False)
    except Exception:  # noqa: BLE001
        return None
    if not raw or len(raw) > 6_000_000:
        return None
    hhmmss = ts.split("T")[-1] if "T" in ts else ts
    name = f"shot-{hhmmss}-{uuid.uuid4().hex[:6]}.{ext}"
    try:
        (_clips_dir() / name).write_bytes(raw)
    except OSError:
        return None
    return name  # \u76f8\u5bf9 captures \u6839


def _render_md(body: CaptureBody, ts: str) -> str:
    t = body.target or {}
    lines = [
        f"# 捕获 · {_KIND_LABEL.get(body.capture_kind, body.capture_kind)}",
        "",
        f"- 时间: {ts}",
        f"- 类型: {body.capture_kind}",
        f"- URL: {body.url}",
        f"- 路由: {body.route}",
    ]
    if t.get("selector"):
        lines.append(f"- 选择器: `{t.get('selector')}`")
    if t.get("label"):
        lines.append(f"- 标签: {t.get('label')}")
    if t.get("text"):
        lines.append(f"- 文本: {str(t.get('text'))[:500]}")
    lines += ["", "## 用户批注", "", (body.comment.strip() or "(无)")]
    form_values = t.get("form_values") if isinstance(t.get("form_values"), list) else []
    if form_values:
        lines += ["", "## 表单当前值"]
        for idx, item in enumerate(form_values[:20], start=1):
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or item.get("id") or item.get("tag") or f"field-{idx}")
            lines += ["", f"### {idx}. {label}"]
            if item.get("selector"):
                lines.append(f"- 选择器: `{item.get('selector')}`")
            if item.get("checked") is not None:
                lines.append(f"- checked: {bool(item.get('checked'))}")
            lines += ["", _safe_fence(str(item.get("value") or "")[:8000], "text")]
    if t.get("outer_html"):
        lines += ["", "## 元素 HTML", "", "```html", str(t.get("outer_html"))[:8000], "```"]
    if body.capture_kind == "page_snapshot" and body.text_snapshot:
        lines += ["", "## 页面文本快照", "", body.text_snapshot[:40000]]
    return "\n".join(lines)


@captures_router.post("")
async def save_capture(body: CaptureBody) -> dict[str, Any]:
    """保存捕获到文件(不创建审阅材料、不进审阅队列)。

    enqueue=True(提交)→ pending/(进 dispatch 批次, 计入待处理数);
    enqueue=False(复制)→ clips/(只为给剪贴板一个文件链接, 不计入待处理)。
    """
    ts = time.strftime("%Y%m%dT%H%M%S")
    name = _capture_filename(body, ts)
    d = _pending_dir() if body.enqueue else _clips_dir()
    path = d / name
    try:
        path.write_text(_render_md(body, ts), encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"capture write failed: {e}") from e
    pending = sorted(_pending_dir().glob("*.md"))
    saved_path = str(path.resolve())
    # 真实截图(若发来): 落盘成图片, 相对路径挂到 page_element 札记的 captures(集中管理面渲染缩略图)。
    shot_rel = _save_image_data_url(body.image_data_url, ts) if body.image_data_url else None
    # 圈选评论(element_comment)统一并进札记: 建一个 page_element Note, 进集中管理面。
    # (page_snapshot/debug_start 不是"评论", 不建 note。)
    note_id = None
    if body.capture_kind == "element_comment" and (body.comment or "").strip():
        try:
            from ..authored.store import get_authored_store
            loc = body.target or {}
            n = get_authored_store().create(
                content=body.comment.strip(),
                target={
                    "kind": "page_element",
                    "id": (loc.get("selector") or body.route or body.url or "page")[:200],
                    "url": body.url, "route": body.route,
                    "selector": loc.get("selector"),
                    "title": body.title or loc.get("label"),
                    "locator": loc,
                },
                uses=["comment"],
                captures=[shot_rel] if shot_rel else None,
                extra={"src_capture": saved_path},
            )
            note_id = n.id
        except Exception:
            pass
    payload = body.model_dump()
    payload.update({"path": saved_path, "saved_path": saved_path, "created_at": ts, "shot": shot_rel})
    publish_material_event(CAPTURE.id, payload, source="boss_sight.captures")
    return {"saved_path": saved_path, "pending_count": len(pending), "note_id": note_id, "shot": shot_rel}


@captures_router.get("")
async def list_captures() -> dict[str, Any]:
    d = _pending_dir()
    items = [{"name": p.name, "path": str(p.resolve())} for p in sorted(d.glob("*.md"))]
    return {"pending_count": len(items), "items": items}


@captures_router.get("/file")
async def get_capture_file(path: str):
    """读 captures 根下的截图(集中管理面渲染 note.captures 缩略图)。path 相对 captures 根, 防越界。"""
    from fastapi.responses import FileResponse
    root = _captures_root().resolve()
    p = (root / path).resolve()
    if root != p and root not in p.parents:
        raise HTTPException(400, "path 越界")
    if not p.is_file():
        raise HTTPException(404, "file not found")
    media = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
             ".webp": "image/webp", ".gif": "image/gif"}.get(p.suffix.lower())
    return FileResponse(str(p), media_type=media)


def _find_canonical_controller(mgr: Any) -> Any | None:
    """唯一(最新非归档)总控 —— 与 ControllerWaker._find_active_controllers / 前端 ControllerChat 同规则。"""
    sessions = getattr(mgr, "_sessions", {})
    live = [
        s for s in sessions.values()
        if getattr(s, "provider", "") == "controller"
        and getattr(s, "ended_at", None) is None
        and not getattr(s, "archived", False)
    ]
    if not live:
        return None
    live.sort(key=lambda s: getattr(s, "started_at", 0) or 0, reverse=True)
    return live[0]


@captures_router.post("/dispatch")
async def dispatch_captures() -> dict[str, Any]:
    """把 pending 的捕获整体交给唯一总控读取处理。

    1) 把 pending/* 移到 captures/batch_<ts>/(immutable 批次, 下一批回到干净 pending)。
    2) 注入一条消息给唯一总控, 让它逐个 Read 这批 .md 文件并处理。
    """
    d = _pending_dir()
    pending = sorted(d.glob("*.md"))
    if not pending:
        return {"dispatched": False, "reason": "没有待处理的捕获", "count": 0}

    try:
        from omnicompany.dashboard.ccdaemon.chat import get_chat_manager
        mgr = get_chat_manager()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"chat manager unavailable: {e}") from e

    controller = _find_canonical_controller(mgr)
    if controller is None:
        return {
            "dispatched": False,
            "reason": "没有活跃总控会话, 请先打开总控对话再试",
            "count": len(pending),
        }

    batch_ts = time.strftime("%Y%m%dT%H%M%S")
    batch_dir = _captures_root() / f"batch_{batch_ts}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    moved: list[Path] = []
    for p in pending:
        dest = batch_dir / p.name
        try:
            p.rename(dest)
            moved.append(dest)
        except OSError:
            continue

    file_list = "\n".join(f"  - {m.resolve()}" for m in moved)
    msg = (
        "[用户捕获批次, not_user: true]\n"
        f"用户在驾驶舱提交了 {len(moved)} 条 UI 捕获(圈选/快照/调试交接, 含用户批注), 已存到目录:\n"
        f"{batch_dir.resolve()}\n\n"
        "请逐个用 Read 读取这些 .md 文件(每条含: 圈选目标的选择器·文本·HTML 或页面快照 + 用户批注), "
        "理解用户想指出 / 想改什么, 再决定动作(派 subagent 改界面 / 记问题到 plan / 直接回应); "
        "处理完用自然语言把这批的结论汇总给用户。\n"
        f"文件:\n{file_list}"
    )
    try:
        await mgr.submit_user_prompt(controller, msg, record_history=True)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"inject to controller failed: {e}") from e

    return {
        "dispatched": True,
        "count": len(moved),
        "batch_dir": str(batch_dir.resolve()),
        "controller_session": getattr(controller, "id", None),
    }


__all__ = ["captures_router"]
