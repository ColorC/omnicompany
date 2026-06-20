# [OMNI] origin=ai-ide ts=2026-05-23 type=spike status=v0 belongs_to=dashboard/boss-sight
# [OMNI] material_id="material:scripts.boss_sight_scan_sessions.py"
"""BOSS SIGHT v0 spike · 扫描本机所有 cli agent session

三源:
  1. Claude Code: ~/.claude/projects/{escaped-cwd}/{session-uuid}.jsonl
  2. Codex:       ~/.codex/sessions/{YYYY}/{MM}/{DD}/rollout-{ts}-{uuid}.jsonl
  3. omni_chat:   {omnicompany}/data/cc_sessions.json

输出:
  stdout 一份 markdown 概览 (按最近活动倒序)
  可选 --write-to <path> 落盘

属于 BOSS SIGHT v0 第一个原型. 后续封装成 dashboard service 时迁出 scripts/.
对应需求: docs/plans/dashboard/[2026-05-23]BOSS-SIGHT/user_directives.md U-016.

跑法:
  python omnicompany/scripts/boss_sight_scan_sessions.py [--top 50] [--write-to path.md]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


# [INF] active 阈值. 实操可调. 给个保守值 5 分钟先看分布.
ACTIVE_THRESHOLD_SECONDS = 5 * 60


@dataclass
class SessionEntry:
    source: str           # 'claude_code' | 'codex' | 'omni_chat'
    session_id: str
    cwd: str | None
    file_path: str
    file_size: int
    last_activity_ts: str       # ISO 8601
    last_activity_age_sec: float
    is_active: bool
    first_user_text: str | None
    extra: dict | None = None   # provider-specific 元数据 (name / status / active_plan 等)


# 按需读取上限. U-021: jsonl 是行式文件, 禁止扫整文件来算简单统计.
# session_meta 在第 1 行, 真正首条 user 通常在前 50 行内. 100 行是安全上限.
MAX_READ_LINES_FOR_PREVIEW = 100


# ---- claude_code -----------------------------------------------------------

def _unescape_claude_cwd(escaped: str) -> str:
    """e.g. 'e--workspace' -> 'e:\\workspace'

    claude code 用 '-' 替换所有的 ':' 和路径分隔符. 第一段单字母通常是 Windows 盘符.
    """
    if len(escaped) >= 3 and escaped[1] == '-' and escaped[0].isalpha():
        drive = escaped[0]
        rest = escaped[2:].replace('-', os.sep)
        return f"{drive}:{os.sep}{rest}"
    return escaped.replace('-', os.sep)


def _is_real_user_text(text: str) -> bool:
    """跳过 environment_context / system-reminder 等系统注入消息, 只认人类首条."""
    if not text:
        return False
    head = text.lstrip()[:120].lower()
    skip_markers = (
        '<environment_context>',
        '<system-reminder>',
        '<command-name>',
        '<local-command-stdout>',
        '<command-message>',
    )
    return not any(marker in head for marker in skip_markers)


def _read_first_user_text_claude(jsonl_path: Path, limit: int = 200) -> str | None:
    """U-021: 局部读, 最多扫 MAX_READ_LINES_FOR_PREVIEW 行就停."""
    try:
        with jsonl_path.open('r', encoding='utf-8', errors='replace') as f:
            for idx, line in enumerate(f):
                if idx >= MAX_READ_LINES_FOR_PREVIEW:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get('type') != 'user':
                    continue
                msg = obj.get('message')
                if not isinstance(msg, dict):
                    continue
                content = msg.get('content')
                text: str | None = None
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    for blk in content:
                        if isinstance(blk, dict) and blk.get('type') == 'text':
                            text = blk.get('text') or ''
                            break
                if text and _is_real_user_text(text):
                    return text[:limit]
        return None
    except (OSError, UnicodeDecodeError):
        return None


def scan_claude_code(home: Path) -> list[SessionEntry]:
    out: list[SessionEntry] = []
    projects = home / '.claude' / 'projects'
    if not projects.is_dir():
        return out
    now = datetime.now(timezone.utc)
    for proj_dir in projects.iterdir():
        if not proj_dir.is_dir():
            continue
        cwd = _unescape_claude_cwd(proj_dir.name)
        for jsonl in proj_dir.glob('*.jsonl'):
            try:
                stat = jsonl.stat()
            except OSError:
                continue
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            age = (now - mtime).total_seconds()
            out.append(SessionEntry(
                source='claude_code',
                session_id=jsonl.stem,
                cwd=cwd,
                file_path=str(jsonl),
                file_size=stat.st_size,
                last_activity_ts=mtime.isoformat(),
                last_activity_age_sec=age,
                is_active=age < ACTIVE_THRESHOLD_SECONDS,
                first_user_text=_read_first_user_text_claude(jsonl),
            ))
    return out


# ---- codex -----------------------------------------------------------------

def _read_codex_meta_and_first_user(jsonl_path: Path, limit: int = 200) -> tuple[str | None, str | None]:
    """U-021: 局部读, 最多扫 MAX_READ_LINES_FOR_PREVIEW 行.

    第一行通常是 session_meta (含 cwd), 真正人类首条 user 在前 30 行内.
    跳过 environment_context / system-reminder 注入. 永远不扫整文件.
    """
    cwd: str | None = None
    first_user: str | None = None
    try:
        with jsonl_path.open('r', encoding='utf-8', errors='replace') as f:
            for idx, line in enumerate(f):
                if idx >= MAX_READ_LINES_FOR_PREVIEW:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if cwd is None and obj.get('type') == 'session_meta':
                    cwd = (obj.get('payload') or {}).get('cwd')
                if first_user is None:
                    payload = obj.get('payload') or {}
                    if obj.get('type') == 'response_item' and payload.get('type') == 'message' and payload.get('role') == 'user':
                        content = payload.get('content') or []
                        if isinstance(content, list):
                            for blk in content:
                                if isinstance(blk, dict) and blk.get('type') in ('input_text', 'text'):
                                    candidate = (blk.get('text') or '')[:limit]
                                    if _is_real_user_text(candidate):
                                        first_user = candidate
                                        break
                if cwd is not None and first_user is not None:
                    break
    except (OSError, UnicodeDecodeError):
        pass
    return cwd, first_user


def _codex_session_id_from_filename(stem: str) -> str:
    """rollout-2026-05-21T23-12-38-019e4b18-8436-7e90-a37f-aa34676420c0 -> uuid 末 5 段"""
    parts = stem.split('-')
    if len(parts) >= 5:
        return '-'.join(parts[-5:])
    return stem


def scan_codex(home: Path) -> list[SessionEntry]:
    out: list[SessionEntry] = []
    sessions_dir = home / '.codex' / 'sessions'
    if not sessions_dir.is_dir():
        return out
    now = datetime.now(timezone.utc)
    for jsonl in sessions_dir.rglob('rollout-*.jsonl'):
        try:
            stat = jsonl.stat()
        except OSError:
            continue
        mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        age = (now - mtime).total_seconds()
        cwd, first_user = _read_codex_meta_and_first_user(jsonl)
        out.append(SessionEntry(
            source='codex',
            session_id=_codex_session_id_from_filename(jsonl.stem),
            cwd=cwd,
            file_path=str(jsonl),
            file_size=stat.st_size,
            last_activity_ts=mtime.isoformat(),
            last_activity_age_sec=age,
            is_active=age < ACTIVE_THRESHOLD_SECONDS,
            first_user_text=first_user,
        ))
    return out


# ---- omni_chat -------------------------------------------------------------

def scan_omni_chat(workspace: Path) -> list[SessionEntry]:
    out: list[SessionEntry] = []
    cc_path = workspace / 'data' / 'cc_sessions.json'
    if not cc_path.is_file():
        return out
    try:
        data = json.loads(cc_path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return out
    if not isinstance(data, dict):
        return out
    now = datetime.now(timezone.utc)
    for sid, fields in data.items():
        if not isinstance(fields, dict):
            continue
        cwd = fields.get('cwd')
        # 时间锚: ended_at > started_at; 都是 unix timestamp (float)
        ended_at = fields.get('ended_at')
        started_at = fields.get('started_at')
        ts = ended_at if isinstance(ended_at, (int, float)) else started_at
        if isinstance(ts, (int, float)):
            mtime = datetime.fromtimestamp(ts, tz=timezone.utc)
        else:
            mtime = now
        age = (now - mtime).total_seconds()
        # active 判定: omni_chat 自己说 alive 也算 active (即便 mtime 旧)
        is_active = (age < ACTIVE_THRESHOLD_SECONDS) or bool(fields.get('alive'))
        # 提首条 user from history_summary
        first_user = None
        hist = fields.get('history_summary')
        if isinstance(hist, list):
            for entry in hist:
                if isinstance(entry, dict) and entry.get('role') == 'user':
                    first_user = (entry.get('text') or '')[:200]
                    break
        out.append(SessionEntry(
            source='omni_chat',
            session_id=sid,
            cwd=cwd,
            file_path=str(cc_path),
            file_size=0,
            last_activity_ts=mtime.isoformat(),
            last_activity_age_sec=age,
            is_active=is_active,
            first_user_text=first_user,
            extra={
                'name': fields.get('name'),
                'provider': fields.get('provider'),
                'kind': fields.get('kind'),
                'status': fields.get('status'),
                'active_plan': fields.get('active_plan'),
                'claude_session_id': fields.get('claude_session_id'),
            },
        ))
    return out


# ---- output ----------------------------------------------------------------

def _fmt_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds / 60)}m"
    if seconds < 86400:
        return f"{int(seconds / 3600)}h"
    return f"{int(seconds / 86400)}d"


def _fmt_size(bytes_: int) -> str:
    if bytes_ < 1024:
        return f"{bytes_}B"
    if bytes_ < 1024 * 1024:
        return f"{bytes_ // 1024}K"
    return f"{bytes_ / (1024 * 1024):.1f}M"


def format_markdown(entries: list[SessionEntry], top: int = 50) -> str:
    entries_sorted = sorted(entries, key=lambda e: e.last_activity_ts, reverse=True)
    total = len(entries)
    by_src = {
        s: sum(1 for e in entries if e.source == s)
        for s in ('claude_code', 'codex', 'omni_chat')
    }
    active_count = sum(1 for e in entries if e.is_active)

    md = [
        "# BOSS SIGHT · session 扫描结果 (v0 spike)",
        "",
        f"扫描时刻: {datetime.now(timezone.utc).isoformat()}",
        f"active 阈值: {ACTIVE_THRESHOLD_SECONDS}s",
        "",
        f"**总数 {total}** (claude_code={by_src['claude_code']}, codex={by_src['codex']}, omni_chat={by_src['omni_chat']})",
        f"**active {active_count}** (jsonl 在最近 {ACTIVE_THRESHOLD_SECONDS}s 内被追加, 或 omni_chat alive=true)",
        "",
        f"按最近活动倒序展示前 {top} 条.",
        "",
        "| 状态 | 来源 | cwd | 上次活动 | size | session_id | 首条 user 消息 |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in entries_sorted[:top]:
        status = "**ACTIVE**" if e.is_active else f"{_fmt_age(e.last_activity_age_sec)} ago"
        cwd = (e.cwd or '?').replace('|', '\\|')
        sid_short = e.session_id[:12] + '...' if len(e.session_id) > 12 else e.session_id
        first_msg = (e.first_user_text or '').replace('\r\n', ' ').replace('\n', ' ').replace('|', '\\|')[:80]
        md.append(
            f"| {status} | {e.source} | `{cwd}` | {e.last_activity_ts[:19]} | {_fmt_size(e.file_size)} | `{sid_short}` | {first_msg} |"
        )
    return '\n'.join(md) + '\n'


# ---- main ------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="BOSS SIGHT v0 spike: scan all cli agent sessions on this machine")
    parser.add_argument('--home', default=os.path.expanduser('~'),
                        help='HOME 目录 (默认 ~)')
    parser.add_argument('--workspace', default=r'/workspace\omnicompany',
                        help='omnicompany 仓库根 (含 data/cc_sessions.json)')
    parser.add_argument('--top', type=int, default=50, help='展示前 N 条')
    parser.add_argument('--write-to', default=None, help='可选: 也写 markdown 到该路径')
    args = parser.parse_args(argv)

    # Windows default console is gbk; force utf-8 so non-ASCII session text doesn't crash stdout.
    try:
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    home = Path(args.home)
    workspace = Path(args.workspace)

    entries: list[SessionEntry] = []
    entries.extend(scan_claude_code(home))
    entries.extend(scan_codex(home))
    entries.extend(scan_omni_chat(workspace))

    md = format_markdown(entries, top=args.top)
    sys.stdout.write(md)

    if args.write_to:
        Path(args.write_to).write_text(md, encoding='utf-8')
        print(f"\n[written] {args.write_to}", file=sys.stderr)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
