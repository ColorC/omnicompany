# [OMNI] origin=claude-code domain=services/_governance ts=2026-06-13T10:20:00Z type=router
# [OMNI] material_id="material:governance.scheduler.cron_tick_runner.py"
"""治理定时 runner — 让 .omni/cron/ 里的治理任务真正会跑(治本"想起来用")。

背景: ScheduleCronRouter 只**写** .omni/cron/<name>.json 任务定义, 仓里此前**没有执行消费者**
(sentinel 不跑它们), 任务是惰性的。本模块补上最小 runner:

  omni governance cron-tick   # 读全部 cron 任务, 跑到期的, 更新 last_run_at

由**一个**外部触发器(OS cron / Windows 任务计划 / sentinel)每隔几分钟调一次 cron-tick,
它就把所有到期的治理任务(每日 plans-run/docs-refs、每周 history-run/docs-timeliness、提交)分发掉。
schedulable 的根本不需要人"想起来"。

到期判定走 cadence 区间(@hourly/@daily/@weekly/@monthly): last_run_at 为空或已过区间即到期。
原始 5 段 cron 表达式保守按每日处理(治理用 preset 即可, 不引入完整 cron 解析)。
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnicompany.core.config import omni_workspace_root

_CADENCE_SECONDS = {
    "@hourly": 3600,
    "@daily": 86400,
    "@weekly": 604800,
    "@monthly": 2592000,
    "@yearly": 31536000,
}

# 本部门标准治理任务(ensure 时若缺则建)
_GOVERNANCE_TASKS = [
    {"name": "gov-plans-daily", "schedule": "@daily",
     "command": "omni governance plans-run --only-missing",
     "description": "每日: 新计划归属 + 中文标题 + 格式检查"},
    {"name": "gov-docs-refs-daily", "schedule": "@daily",
     "command": "omni governance docs-refs",
     "description": "每日: 文档引用完整性(断链/失效行锚, 确定性)"},
    {"name": "gov-commit-daily", "schedule": "@daily",
     "command": "omni governance commit-run --apply",
     "description": "每日: 性价比模型严格分批提交(防 git 改动堆积)"},
    {"name": "gov-decisions-daily", "schedule": "@daily",
     "command": "omni governance decisions-run",
     "description": "每日: 标记 llm_input 的札记 → 结构化决策(进总控 ctx)"},
    {"name": "gov-history-weekly", "schedule": "@weekly",
     "command": "omni governance history-run",
     "description": "每周: 对话重复需求/指正挖掘"},
    {"name": "gov-docs-timeliness-weekly", "schedule": "@weekly",
     "command": "omni governance docs-timeliness",
     "description": "每周: 规范/计划/报告时效性(过期/被取代/冲突)"},
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def cron_dir() -> Path:
    d = omni_workspace_root() / ".omni" / "cron"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_tasks() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in sorted(cron_dir().glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def _cadence_seconds(schedule: str) -> int:
    s = (schedule or "").strip().lower()
    if s in _CADENCE_SECONDS:
        return _CADENCE_SECONDS[s]
    return 86400  # 原始 cron 表达式保守按每日(治理用 preset)


def is_due(task: dict[str, Any], now: datetime | None = None) -> bool:
    now = now or _now()
    last = task.get("last_run_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return True
    return (now - last_dt).total_seconds() >= _cadence_seconds(task.get("schedule", ""))


def ensure_governance_tasks() -> list[str]:
    """缺失的标准治理 cron 任务补建, 返回新建的任务名。已存在的不动(保留其 last_run_at)。"""
    created: list[str] = []
    d = cron_dir()
    for t in _GOVERNANCE_TASKS:
        p = d / f"{t['name']}.json"
        if p.exists():
            continue
        p.write_text(json.dumps({
            **t, "prompt": "", "created_at": _now().isoformat(), "last_run_at": None,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        created.append(t["name"])
    return created


def tick(*, dry_run: bool = False, now: datetime | None = None) -> dict[str, Any]:
    """跑一遍: 找到期任务, 执行其 command, 更新 last_run_at。"""
    now = now or _now()
    d = cron_dir()
    ran: list[dict[str, Any]] = []
    for f in sorted(d.glob("*.json")):
        try:
            task = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not is_due(task, now):
            continue
        cmd = (task.get("command") or "").strip()
        rec = {"name": task.get("name"), "command": cmd, "ran": False}
        if not cmd:
            rec["skipped"] = "无 command(prompt 型任务需 agent 消费, 此 runner 只跑 command)"
            ran.append(rec)
            continue
        if dry_run:
            rec["would_run"] = True
            ran.append(rec)
            continue
        try:
            proc = subprocess.run(cmd, shell=True, cwd=str(omni_workspace_root()),
                                  capture_output=True, text=True, timeout=1800,
                                  encoding="utf-8", errors="replace")
            rec["ran"] = True
            rec["returncode"] = proc.returncode
            rec["tail"] = (proc.stdout or proc.stderr or "")[-300:]
            task["last_run_at"] = now.isoformat()
            f.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
        ran.append(rec)
    return {"checked_at": now.isoformat(), "dry_run": dry_run, "ran": ran, "due_count": len(ran)}
