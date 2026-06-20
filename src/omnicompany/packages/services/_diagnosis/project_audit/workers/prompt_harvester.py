# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit/workers ts=2026-06-20T00:00:00Z type=worker status=active
# [OMNI] summary="PromptHarvester — 跨全部会话日志(claude+codex)按 cwd/路径/关键词捞出'我亲口给 agent 的原始 prompt'(A 类真源)。HARD。"
# [OMNI] material_id="material:services._diagnosis.project_audit.workers.prompt_harvester"
"""PromptHarvester(HARD)。

信任层级 A 类真源的采集器:**只认我在本地 claude/codex 亲口给 agent 的原始 prompt**,
它是"我想做什么、我做了什么决定"的唯一权威。

为什么不靠目录名匹配:实测会话日志不按项目干净分目录(主目录 e--workspace 单独
就 1.6GB、跨多项目)。所以按三类信号跨全部会话检索:
1. 会话 cwd 落在项目根内;2. prompt 文本里提到项目根/项目名;3. 自定义关键词。
廉价预筛(整文件字节级 token 命中)避免对 1.6GB 全量 json 解析。
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.packages.services._core.omnicompany import Worker

from ._sessions import (
    default_session_roots, file_mentions, iter_session_files,
    iter_user_prompts, _norm_path,
)


def _normspace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


class PromptHarvester(Worker):
    """捞我的原始 prompt(A 类真源)。HARD,确定性文件检索。"""

    DESCRIPTION = (
        "跨 ~/.claude 与 ~/.codex 全部会话日志,按 会话cwd / 项目路径 / 项目名 / 关键词 "
        "捞出我亲口给 agent 的原始 prompt(过滤系统注入与工具回显),去重、按时序保留、留采集痕迹。"
    )
    FORMAT_IN = "project_audit.tree"
    FORMAT_OUT = "project_audit.enriched"

    def run(self, input_data: Any) -> Verdict:
        tree = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else input_data
        if not isinstance(tree, dict) or not tree.get("root"):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="tree 无效(缺 root)", output={})

        target = tree.get("target", {}) or {}
        root = tree["root"]
        name = target.get("name") or Path(root).name
        root_norm = _norm_path(root)
        root_base = Path(root).name.lower()

        # 匹配 token:项目根、根 basename、项目名、用户自定义关键词
        tokens = [root_norm, root_base, name.lower()]
        tokens += [k.lower() for k in (target.get("harvest_keywords") or [])]
        tokens = [t for t in dict.fromkeys(tokens) if t and len(t) >= 3]

        session_roots = target.get("session_roots") or default_session_roots()
        max_prompts = int(target.get("max_prompts") or 400)
        per_prompt_cap = int(target.get("prompt_char_cap") or 1200)

        scanned = matched_files = matched_sessions = total_seen = 0
        seen_hashes: set[int] = set()
        prompts: list[dict] = []

        for fp in iter_session_files(session_roots):
            scanned += 1
            if not file_mentions(fp, tokens):
                continue
            matched_files += 1
            file_hit = False
            for rec in iter_user_prompts(fp):
                total_seen += 1
                text = rec.get("text") or ""
                cwd_norm = _norm_path(rec.get("cwd"))
                low = text.lower()
                # 相关性:会话 cwd 落在项目内,或文本提到根/名/关键词
                cwd_match = bool(cwd_norm) and (root_norm in cwd_norm or cwd_norm in root_norm or root_base in cwd_norm)
                text_match = any(t in low for t in tokens)
                if not (cwd_match or text_match):
                    continue
                h = hash(_normspace(text)[:600])
                if h in seen_hashes:
                    continue
                seen_hashes.add(h)
                file_hit = True
                prompts.append({
                    "text": text[:per_prompt_cap],
                    "full_len": len(text),
                    "source": os.path.basename(fp),
                    "cwd": rec.get("cwd"),
                    "ts": rec.get("ts"),
                    "via": "cwd" if cwd_match else "text",
                })
            if file_hit:
                matched_sessions += 1

        # 按时间戳排序(无 ts 的沉底),截断并如实记录
        prompts.sort(key=lambda p: (p.get("ts") or ""))
        truncated = len(prompts) > max_prompts
        kept = prompts[:max_prompts]

        enriched = dict(tree)
        enriched["prompts"] = kept
        enriched["prompt_meta"] = {
            "match_tokens": tokens,
            "scanned_files": scanned,
            "matched_files": matched_files,
            "matched_sessions": matched_sessions,
            "total_prompts_seen": total_seen,
            "total_relevant": len(prompts),
            "kept": len(kept),
            "truncated": truncated,
            "via_cwd": sum(1 for p in kept if p["via"] == "cwd"),
            "via_text": sum(1 for p in kept if p["via"] == "text"),
        }
        # 即便 0 命中也 PASS(项目可能没会话日志);下游据此诚实标注
        return Verdict(
            kind=VerdictKind.PASS,
            output=enriched,
            diagnosis=None if kept else f"未在会话日志里找到 {name} 相关的原始 prompt(tokens={tokens})",
        )
