"""Forgiving material structure validators for BOSS SIGHT reviewstage.

Validators never reject a material. They only return warning records that are
stored in material.extra.structure_warnings and history.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


TEXT_KINDS = {"markdown", "html", "key_question", "custom_web_template", "webgame-spec"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


def _warning(code: str, message: str, *, path: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {
        "code": code,
        "severity": "warning",
        "message": message,
    }
    if path:
        item["path"] = path
    return item


def _parse_json(content: str | None) -> tuple[Any | None, str | None]:
    if not content or not content.strip():
        return None, "content is empty"
    try:
        return json.loads(content), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc.msg}"


def validate_material_structure(
    *,
    kind: str,
    title: str,
    inline_content: str | None,
    file_relpath: str | None,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    extra = extra or {}
    title = (title or "").strip()
    content = inline_content or ""

    if len(title) < 5:
        warnings.append(_warning("title_too_short", "title is very short", path="title"))

    if kind in TEXT_KINDS and not content.strip() and not file_relpath:
        warnings.append(_warning("text_content_empty", "text material has no readable content", path="content"))

    if kind == "markdown" and content.strip():
        if not re.search(r"^#{1,6}\s+\S+", content, flags=re.MULTILINE):
            warnings.append(_warning("markdown_missing_heading", "markdown has no heading", path="inline_content"))
        if re.search(r"\b(TODO|TBD|FIXME)\b", content, flags=re.IGNORECASE):
            warnings.append(_warning("markdown_has_placeholder", "markdown contains TODO/TBD/FIXME markers", path="inline_content"))

    # live_url 型 html 材料的真内容是实时网页(iframe), inline_content 只是回退说明,
    # 不该按"完整 html 文档"校验。仅对纯 inline html 才查 fragment/script。
    if kind == "html" and content.strip() and not str(extra.get("live_url") or "").strip():
        lower = content.lower()
        if "<script" in lower:
            warnings.append(_warning("html_contains_script", "html contains script tags", path="inline_content"))
        if "<html" not in lower and "<body" not in lower and "<!doctype" not in lower:
            warnings.append(_warning("html_fragment_only", "html looks like a fragment without html/body root", path="inline_content"))

    if kind == "key_question":
        data, err = _parse_json(content)
        if err:
            warnings.append(_warning("key_question_invalid_json", err, path="inline_content"))
        elif not isinstance(data, dict):
            warnings.append(_warning("key_question_not_object", "key_question payload should be a JSON object", path="inline_content"))
        else:
            if not str(data.get("question") or "").strip():
                warnings.append(_warning("key_question_missing_question", "key_question.question is missing", path="question"))
            options = data.get("options")
            if options is not None and not isinstance(options, list):
                warnings.append(_warning("key_question_options_not_list", "key_question.options should be a list", path="options"))

    if kind == "custom_web_template":
        schema_id = str(extra.get("data_schema_id") or "").strip()
        data, err = _parse_json(content)
        if not schema_id:
            warnings.append(_warning("custom_template_missing_schema", "custom_web_template is missing extra.data_schema_id", path="extra.data_schema_id"))
        if err:
            warnings.append(_warning("custom_template_invalid_json", err, path="inline_content"))
        elif not isinstance(data, (dict, list)):
            warnings.append(_warning("custom_template_unexpected_json", "custom_web_template payload should be an object or list", path="inline_content"))
        elif schema_id == "branch_storyline_v1":
            nodes = data.get("nodes") if isinstance(data, dict) else None
            if not isinstance(nodes, list) or not nodes:
                warnings.append(_warning("branch_storyline_missing_nodes", "branch_storyline_v1 payload should include a non-empty nodes list", path="nodes"))
        elif schema_id == "filetree_diff_v1":
            files = data.get("files") if isinstance(data, dict) else None
            if not isinstance(files, list):
                warnings.append(_warning("filetree_diff_missing_files", "filetree_diff_v1 payload should include a files list", path="files"))

    # webgame-spec: 主体型审阅材料, 法定三件套(引导演示/文档/文件树 diff)。仅警告不拒绝。
    if kind == "webgame-spec":
        if content.strip() and not re.search(r"^#{1,6}\s+\S+", content, flags=re.MULTILINE):
            warnings.append(_warning("webgame_spec_missing_heading", "webgame-spec spec 报告没有标题(应是 wiki-core markdown 文档)", path="inline_content"))
        for key, label in (
            ("demo", "引导演示(tour / html live_url 材料)"),
            ("doc", "文档(wiki 文档页 / 材料)"),
            ("filetree_diff", "文件树 diff 兄弟材料"),
        ):
            if not str(extra.get(key) or "").strip():
                warnings.append(_warning(
                    f"webgame_spec_missing_{key}",
                    f"webgame-spec 缺三件套之一: {label} — 在 extra.{key} 给出材料 id 或链接",
                    path=f"extra.{key}",
                ))

    if kind == "image" and file_relpath:
        suffix = Path(file_relpath).suffix.lower()
        if suffix and suffix not in IMAGE_EXTS:
            warnings.append(_warning("image_unusual_extension", f"image file extension is unusual: {suffix}", path="file_relpath"))

    return warnings


__all__ = ["TEXT_KINDS", "validate_material_structure"]
