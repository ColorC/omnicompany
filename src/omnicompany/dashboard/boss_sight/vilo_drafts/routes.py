# [OMNI] origin=ai-ide domain=dashboard/boss_sight ts=2026-06-14T00:00:00Z type=infra status=active
# [OMNI] summary="Vilo 草稿区文件 CRUD 路由 — 给 tabletop demo 创作者工作台的草稿面板用。"
# [OMNI] why="用户要在 viloapp 开发者模式直接管理草稿；草稿是 故事/vilo-wants-to-know/wiki/drafts 下的 .md 文件，浏览器要后端读写。"
# [OMNI] tags=vilo,drafts,file-crud
"""Vilo 草稿区文件 CRUD。

挂载于 /api/boss-sight/vilo-drafts。目标目录在 omnicompany 仓外
(workspace/故事/vilo-wants-to-know/wiki/drafts)，所以不走 guarded_write
(它只管 omnicompany 仓内、且会给 .md 贴 OmniMark 头污染正文)，用普通 Path 读写 +
resolve 后容器校验防穿越，仿 captures/routes.py 拿根目录的方式。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

vilo_drafts_router = APIRouter(prefix="/api/boss-sight/vilo-drafts", tags=["vilo-drafts"])

_ALLOWED_SUFFIX = ".md"
_TEMPLATE_CARD = "_模板-草稿卡.md"
_TEMPLATE_EVENT = "_模板-草稿事件.md"


def _drafts_root() -> Path:
    # omni_workspace_root() = .../workspace/omnicompany → .parent = .../workspace
    # (与 captures/routes.py 同一权威拿法，别硬编码盘符)。
    from omnicompany.core.config import omni_workspace_root
    return (omni_workspace_root().parent / "故事" / "vilo-wants-to-know" / "wiki" / "drafts").resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _resolve_in_root(rel: str) -> Path:
    """把前端传来的相对路径(如 'cards/草稿-x.md')解析进 drafts 根，防穿越 + 限 .md。"""
    if not rel or rel.strip() in (".", ".."):
        raise HTTPException(400, "缺少文件名")
    root = _drafts_root()
    cand = (root / rel).resolve()
    if not _is_relative_to(cand, root):
        raise HTTPException(400, f"路径越界: {rel}")
    if cand.suffix.lower() != _ALLOWED_SUFFIX:
        raise HTTPException(400, "只允许 .md 文件")
    return cand


class SaveBody(BaseModel):
    path: str = Field(..., max_length=400)       # 相对 drafts 根，如 cards/草稿-x.md
    content: str = Field(..., max_length=200000)


class CreateBody(BaseModel):
    name: str = Field(..., max_length=120)       # 随手中文名，不含路径/后缀
    kind: str = Field(default="card", pattern="^(card|event)$")


class RenameBody(BaseModel):
    rel: str = Field(..., max_length=400)         # 现有草稿相对路径(cards/草稿-x.md)
    new_name: str = Field(..., max_length=120)    # 新文件名 stem(不含路径/后缀)


def _list_drafts() -> list[dict[str, Any]]:
    root = _drafts_root()
    if not root.exists():
        return []
    items: list[dict[str, Any]] = []
    for p in sorted(root.rglob(f"*{_ALLOWED_SUFFIX}")):
        if p.name.startswith("_"):           # 跳过模板/占位说明(_模板-*, _这里放*)
            continue
        rel = p.relative_to(root).as_posix()
        items.append({
            "id": rel,                        # 相对路径当唯一 id，前端 ref.id 直接是它
            "rel": rel,
            "name": p.stem,
            "path": str(p),                   # 绝对路径(给"复制路径"用)
            "dir": p.parent.relative_to(root).as_posix() or ".",
        })
    return items


@vilo_drafts_router.get("")
async def list_drafts(q: str = Query(default="")) -> dict[str, Any]:
    items = _list_drafts()
    if q:
        ql = q.lower()
        hit: list[dict[str, Any]] = []
        for it in items:
            if ql in it["name"].lower() or ql in it["rel"].lower():
                hit.append(it)
                continue
            try:                              # 内容命中(文件少，直接读全文)
                if ql in _resolve_in_root(it["rel"]).read_text(encoding="utf-8").lower():
                    hit.append(it)
            except OSError:
                pass
        items = hit
    return {"count": len(items), "items": items}


@vilo_drafts_router.get("/file")
async def read_draft(path: str = Query(...)) -> dict[str, Any]:
    p = _resolve_in_root(path)
    if not p.exists():
        raise HTTPException(404, f"草稿不存在: {path}")
    try:
        content = p.read_text(encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"读取失败: {e}") from e
    return {"path": str(p), "rel": path, "content": content}


@vilo_drafts_router.put("/file")
async def save_draft(body: SaveBody) -> dict[str, Any]:
    p = _resolve_in_root(body.path)
    if not p.parent.exists():
        raise HTTPException(400, f"目标目录不存在: {body.path}")
    try:
        p.write_text(body.content, encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"保存失败: {e}") from e
    return {"saved_path": str(p), "rel": body.path}


def _slugify_target(name: str, kind: str) -> str:
    safe = name.strip().replace("/", "-").replace("\\", "-").strip(". ")
    if not safe:
        raise HTTPException(400, "名字不能为空")
    sub = "cards" if kind == "card" else "events"
    return f"{sub}/草稿-{safe}.md"


@vilo_drafts_router.post("/create")
async def create_draft(body: CreateBody) -> dict[str, Any]:
    root = _drafts_root()
    rel = _slugify_target(body.name, body.kind)
    p = _resolve_in_root(rel)
    if p.exists():
        raise HTTPException(409, f"已存在同名草稿: {rel}")
    tpl = root / (_TEMPLATE_CARD if body.kind == "card" else _TEMPLATE_EVENT)
    try:
        seed = tpl.read_text(encoding="utf-8") if tpl.exists() else f"# 草稿 · {body.name}\n"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(seed, encoding="utf-8")
    except OSError as e:
        raise HTTPException(500, f"新建失败: {e}") from e
    return {"created_path": str(p), "rel": rel, "name": p.stem}


@vilo_drafts_router.post("/rename")
async def rename_draft(body: RenameBody) -> dict[str, Any]:
    """重命名草稿(改文件名, 同目录)。new_name = 新 stem; 不含路径/后缀。"""
    src = _resolve_in_root(body.rel)
    if not src.exists():
        raise HTTPException(404, f"草稿不存在: {body.rel}")
    safe = body.new_name.strip().replace("/", "-").replace("\\", "-").strip(". ")
    if not safe:
        raise HTTPException(400, "名字不能为空")
    if safe.startswith("_"):                       # _ 开头被列表当模板/占位跳过
        raise HTTPException(400, "名字不能以 _ 开头")
    root = _drafts_root()
    dst = (src.parent / f"{safe}.md").resolve()
    if not _is_relative_to(dst, root):
        raise HTTPException(400, "路径越界")
    if dst == src:                                 # 名字没变, 原样返回
        rel = dst.relative_to(root).as_posix()
        return {"rel": rel, "path": str(dst), "name": dst.stem}
    if dst.exists():
        raise HTTPException(409, f"已存在同名草稿: {dst.name}")
    try:
        src.rename(dst)
    except OSError as e:
        raise HTTPException(500, f"重命名失败: {e}") from e
    rel = dst.relative_to(root).as_posix()
    return {"rel": rel, "path": str(dst), "name": dst.stem}


@vilo_drafts_router.delete("/file")
async def delete_draft(path: str = Query(...)) -> dict[str, Any]:
    p = _resolve_in_root(path)
    if not p.exists():
        raise HTTPException(404, f"草稿不存在: {path}")
    try:
        p.unlink()
    except OSError as e:
        raise HTTPException(500, f"删除失败: {e}") from e
    return {"deleted": True, "rel": path}


__all__ = ["vilo_drafts_router"]
