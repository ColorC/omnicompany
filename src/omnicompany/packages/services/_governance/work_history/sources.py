# [OMNI] origin=claude-code domain=services/_governance/work_history ts=2026-06-12T12:00:00Z type=infra
# [OMNI] material_id="material:governance.work_history.message_extractors.py"
"""对话历史抽取器 — 从 claude code / codex 的会话 jsonl 里只抽**用户亲手发的消息**。

格式事实(2026-06-12 实测):
- claude: ~/.claude/projects/<dir>/<session>.jsonl, 行 {"type":"user","message":{"content":...}};
  噪声: <system-reminder>/<command-*>/<local-command-*>/<ide_*> 注入、Caveat 包装、tool_result 块。
- codex: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl, 行 {"type":"response_item",
  "payload":{"type":"message","role":"user","content":[{"type":"input_text","text":...}]}};
  噪声: role=user 形态的系统注入(<environment_context>/<permissions/"# AGENTS.md"等)。
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Iterator

CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
CODEX_MEMORIES = Path.home() / ".codex" / "memories"

MSG_MAX_CHARS = 1500

# 整段剥除的注入标签(成对), 以及剥完后按前缀丢弃的行为
_STRIP_TAG_RE = re.compile(
    r"<(system-reminder|ide_selection|ide_opened_file|ide_diagnostics|local-command-stdout|"
    r"local-command-caveat|command-name|command-message|command-args)>.*?</\1>",
    re.DOTALL,
)
_DROP_PREFIXES = (
    "<", "Caveat:", "# AGENTS.md", "[Request interrupted",
    # 假"用户"消息: claude 压缩续接摘要 / codex 计划交接 — 都是 AI 生成, 不是用户原话
    "This session is being continued", "A previous agent",
)


_SURROGATE_RE = re.compile(r"[\ud800-\udfff]")


def _clean(text: str) -> str:
    t = _STRIP_TAG_RE.sub("", text or "").strip()
    if not t or any(t.startswith(p) for p in _DROP_PREFIXES):
        return ""
    # 历史 jsonl 里偶见孤立代理字符(损坏的 \udcXX 转义) — 不清掉的话发 API 时
    # utf-8 编码直接炸(2026-06-12 实跑: 4 个块各白重试 5 轮)
    t = _SURROGATE_RE.sub("", t)
    return t[:MSG_MAX_CHARS]


def claude_user_messages(days: int) -> Iterator[dict[str, Any]]:
    cutoff = time.time() - days * 86400
    if not CLAUDE_PROJECTS.is_dir():
        return
    for proj_dir in sorted(CLAUDE_PROJECTS.iterdir()):
        if not proj_dir.is_dir():
            continue
        for f in proj_dir.glob("*.jsonl"):
            try:
                if f.stat().st_mtime < cutoff:
                    continue
            except OSError:
                continue
            try:
                with f.open(encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        try:
                            obj = json.loads(line)
                        except (json.JSONDecodeError, ValueError):
                            continue
                        if obj.get("type") != "user" or obj.get("isMeta"):
                            continue
                        content = (obj.get("message") or {}).get("content")
                        if isinstance(content, str):
                            texts = [content]
                        elif isinstance(content, list):
                            texts = [b.get("text", "") for b in content
                                     if isinstance(b, dict) and b.get("type") == "text"]
                        else:
                            continue
                        text = _clean("\n".join(t for t in texts if t))
                        if len(text) < 8:
                            continue
                        yield {"src": "claude", "proj": proj_dir.name,
                               "ts": str(obj.get("timestamp") or ""), "text": text}
            except OSError:
                continue


def codex_user_messages(days: int) -> Iterator[dict[str, Any]]:
    cutoff = time.time() - days * 86400
    if not CODEX_SESSIONS.is_dir():
        return
    for f in sorted(CODEX_SESSIONS.rglob("*.jsonl")):
        try:
            if f.stat().st_mtime < cutoff:
                continue
        except OSError:
            continue
        cwd = ""
        try:
            with f.open(encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    t = obj.get("type")
                    payload = obj.get("payload") or {}
                    if t == "session_meta":
                        cwd = str(payload.get("cwd") or "")
                        continue
                    if t != "response_item" or payload.get("type") != "message" \
                            or payload.get("role") != "user":
                        continue
                    texts = [c.get("text", "") for c in payload.get("content") or []
                             if isinstance(c, dict) and c.get("type") == "input_text"]
                    text = _clean("\n".join(x for x in texts if x))
                    if len(text) < 8:
                        continue
                    yield {"src": "codex", "proj": cwd,
                           "ts": str(obj.get("timestamp") or ""), "text": text}
        except OSError:
            continue


def memory_snippets(max_chars_per_file: int = 2500) -> list[dict[str, str]]:
    """两边 AI 的长期 memory(已沉淀的规范) — 供 reduce 阶段对照'是否已被记录'。"""
    out: list[dict[str, str]] = []
    if CLAUDE_PROJECTS.is_dir():
        for mem_dir in CLAUDE_PROJECTS.glob("*/memory"):
            for f in sorted(mem_dir.glob("*.md")):
                try:
                    out.append({"src": f"claude-memory:{f.name}",
                                "text": f.read_text(encoding="utf-8", errors="ignore")[:max_chars_per_file]})
                except OSError:
                    continue
    if CODEX_MEMORIES.is_dir():
        for f in sorted(CODEX_MEMORIES.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in (".md", ".txt", ".json"):
                continue
            try:
                if f.stat().st_size > 200_000:
                    continue
                out.append({"src": f"codex-memory:{f.name}",
                            "text": f.read_text(encoding="utf-8", errors="ignore")[:max_chars_per_file]})
            except OSError:
                continue
    return out
