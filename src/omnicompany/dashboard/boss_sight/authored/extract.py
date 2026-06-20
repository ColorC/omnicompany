# [OMNI] origin=ai-ide domain=dashboard/boss_sight ts=2026-06-14T00:00:00Z type=infra status=active
# [OMNI] summary="把标记为 llm_input 的札记, 用性价比模型提炼成结构化决策。增量 checkpoint。"
# [OMNI] why="用户要'作为 llm 输入的决策由性价比 team 定期/手动提取成结构化输入'喂总控。"
# [OMNI] tags=authored,decisions,extraction,governance
"""决策提取: uses 含 llm_input 的札记 → 结构化决策, 落 data/boss_sight/authored_decisions.json。

复用统一 LLM 面 runtime.llm.structured.call_json + 默认便宜模型, 不自己开线程池(顺序 + 逐条
checkpoint, 增量只提取新增的)。手动: 调 extract_decisions(); 定期: 接 governance scheduler。
消费: cockpit_workflow 把这些决策塞进总控 ctx_summary 的 decisions 段。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decision_gist": {"type": "string", "description": "这条札记表达的决策/指示, 一句话提炼"},
        "scope": {"type": "string", "description": "作用范围: 如某 project/plan/全局/某材料"},
        "constraint": {"type": "string", "description": "硬约束或要求(如有), 否则空串"},
        "applies_to": {"type": "string", "description": "应作用于谁(project/plan id 或对象描述)"},
    },
    "required": ["decision_gist", "scope"],
}

_SYSTEM = (
    "你是把用户随手写的札记提炼成'给执行 agent 的结构化决策输入'的助手。"
    "只提炼用户的意图/指示/约束, 不臆造。输出严格 JSON。"
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decisions_path() -> Path:
    from omnicompany.core.config import omni_workspace_root
    return omni_workspace_root() / "data" / "boss_sight" / "authored_decisions.json"


def _load_existing() -> dict[str, Any]:
    p = _decisions_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save(existing: dict[str, Any]) -> None:
    p = _decisions_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def extract_decisions(*, model: str = "qwen3.6-plus", reextract: bool = False) -> dict[str, Any]:
    """提取 uses 含 llm_input 的札记为结构化决策。增量(已提取的跳过, reextract=True 重提)。"""
    from .store import get_authored_store

    store = get_authored_store()
    notes = [n for n in store.list() if "llm_input" in (n.uses or [])]
    existing = {} if reextract else _load_existing()
    todo = [n for n in notes if n.id not in existing or existing[n.id].get("error")]

    errors = 0
    for n in todo:
        target_ctx = json.dumps(n.target, ensure_ascii=False)
        user = f"札记正文:\n{n.content}\n\n关联对象(target): {target_ctx}\n所属项目: {n.project_id}"
        try:
            from omnicompany.runtime.llm.structured import call_json
            d = call_json(system=_SYSTEM, user=user, schema=DECISION_SCHEMA,
                          model=model, caller="authored.extract", max_tokens=1200)
            existing[n.id] = {
                "note_id": n.id, **d, "project": n.project_id,
                "target_kind": (n.target or {}).get("kind"),
                "extracted_at": _now_iso(),
            }
        except Exception as e:  # noqa: BLE001
            existing[n.id] = {"note_id": n.id, "error": str(e)[:200], "extracted_at": _now_iso()}
            errors += 1
        _save(existing)   # 逐条 checkpoint, 续跑安全

    return {"total_llm_input": len(notes), "newly_extracted": len(todo),
            "errors": errors, "decisions_total": len(existing)}


def load_decisions() -> list[dict[str, Any]]:
    """供总控 ctx 消费: 返回已提取的结构化决策(去掉 error 项)。"""
    return [v for v in _load_existing().values() if isinstance(v, dict) and not v.get("error")]


if __name__ == "__main__":
    print(extract_decisions())
