# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-15T00:00:00Z type=module status=active
# [OMNI] material_id="material:services.learning.hypothesis.store.crud_jtms.py"
"""hypothesis.store — HypothesisEntry 数据类 + HypothesisStore CRUD + JTMS 依赖回溯。

不依赖 LLM。纯确定性逻辑。
- HypothesisEntry: dataclass，对应 hypothesis.store.snapshot 内的 entries 单元
- HypothesisStore: 内存操作 + JSON 落盘，提供 add / update_state / apply_diff / backpropagate
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from omnicompany.core.config import resolve_db_dir


# ── 类型别名 ────────────────────────────────────────────────────────────────

HypothesisKind = Literal["state", "transition", "policy", "invariant"]
HypothesisState = Literal["candidate", "active", "solidified", "falsified", "archived"]


# ── HypothesisEntry ─────────────────────────────────────────────────────────

@dataclass
class HypothesisEntry:
    """单条假设，对应 hypothesis.store.snapshot entries 内的元素。"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: HypothesisKind = "policy"
    trigger: str = ""
    predicted: str = ""
    actual: str | None = None
    scene_fingerprint: dict = field(default_factory=dict)
    evidence_count: int = 0
    counterexample_count: int = 0
    state: HypothesisState = "candidate"
    depends_on: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def _touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def add_evidence(self) -> None:
        self.evidence_count += 1
        self._touch()

    def add_counterexample(self, actual: str | None = None) -> None:
        self.counterexample_count += 1
        if actual:
            self.actual = actual
        self._touch()

    def transition_to(self, new_state: HypothesisState) -> None:
        self.state = new_state
        self._touch()


# ── HypothesisStore ─────────────────────────────────────────────────────────

class HypothesisStore:
    """内存假设库，支持 JSON 落盘和 JTMS 依赖回溯。

    用法示例::

        store = HypothesisStore.load_or_create(session_id, domain)
        store.add(HypothesisEntry(kind="policy", trigger="...", predicted="..."))
        store.set_state(entry_id, "falsified")   # 触发 JTMS 回溯
        store.save(iteration=3)
    """

    def __init__(self, session_id: str, domain: str) -> None:
        self.session_id = session_id
        self.domain = domain
        self._entries: dict[str, HypothesisEntry] = {}  # id → entry
        self._tainted: set[str] = set()  # 待 JTMS 回溯处理

    # ── 工厂方法 ───────────────────────────────────────────────────────────

    @classmethod
    def load_or_create(cls, session_id: str, domain: str) -> "HypothesisStore":
        """从磁盘恢复或新建空 store。"""
        store = cls(session_id, domain)
        latest = store._session_dir() / "latest.json"
        if latest.exists():
            data = json.loads(latest.read_text(encoding="utf-8"))
            for raw in data.get("entries", []):
                e = HypothesisEntry(**{k: v for k, v in raw.items() if k in HypothesisEntry.__dataclass_fields__})
                store._entries[e.id] = e
            store._tainted = set(data.get("tainted_ids", []))
        return store

    # ── CRUD ────────────────────────────────────────────────────────────────

    def add(self, entry: HypothesisEntry) -> HypothesisEntry:
        """添加新假设。若已存在相同 id 则跳过（幂等）。"""
        if entry.id not in self._entries:
            self._entries[entry.id] = entry
        return self._entries[entry.id]

    def get(self, entry_id: str) -> HypothesisEntry | None:
        return self._entries.get(entry_id)

    def all(self) -> list[HypothesisEntry]:
        return list(self._entries.values())

    def by_state(self, state: HypothesisState) -> list[HypothesisEntry]:
        return [e for e in self._entries.values() if e.state == state]

    # ── 状态转移 + JTMS 回溯 ────────────────────────────────────────────────

    def set_state(self, entry_id: str, new_state: HypothesisState) -> None:
        """更新假设状态，若 new_state='falsified' 则触发 JTMS 反向广播。"""
        entry = self._entries.get(entry_id)
        if entry is None:
            return
        entry.transition_to(new_state)
        if new_state == "falsified":
            self._backpropagate(entry_id)

    def _backpropagate(self, falsified_id: str) -> None:
        """JTMS 风格依赖回溯：凡 depends_on 含 falsified_id 的在役假设，降回候选并标记 tainted。

        不做同步打断，只标记。Reflector / 下一轮 Experimenter 会看到 tainted_ids。
        hard-core 假设（depends_on 为空且 kind='invariant'）不进入回溯。
        """
        for entry in self._entries.values():
            if falsified_id in entry.depends_on and entry.state in ("active", "solidified"):
                # 降级：回到候选，保留证据计数（标记 tainted 供重查）
                entry.state = "candidate"
                entry._touch()
                self._tainted.add(entry.id)

    def apply_diff(self, diff: dict) -> list[str]:
        """把 reflect.diff 格式的 dict apply 到 store，返回变更 id 列表。

        diff 结构：{"new_entries": [...], "state_changes": [...]}
        new_entries 超过 3 条时拒绝（StoreUpdateNode 应在上游 validator 拦截）。
        """
        changed: list[str] = []

        # 新假设
        new_entries = diff.get("new_entries", [])
        if len(new_entries) > 3:
            raise ValueError(f"reflect.diff 包含 {len(new_entries)} 条新假设，超过上限 3 条")

        for raw in new_entries:
            e = HypothesisEntry(
                kind=raw["kind"],
                trigger=raw["trigger"],
                predicted=raw["predicted"],
            )
            self.add(e)
            # 初始 verbatim_evidence 计为第一条证据
            if raw.get("verbatim_evidence", "").strip():
                e.add_evidence()
            changed.append(e.id)

        # 状态变更（逐条处理，单条失败不中断后续）
        import logging as _logging
        _log = _logging.getLogger(__name__)
        for change in diff.get("state_changes", []):
            hid = change["hypothesis_id"]
            new_state = change["new_state"]
            # 兼容两种字段名：Reflector 输出 verbatim_evidence，早期设计用 trigger_observation
            evidence = change.get("verbatim_evidence") or change.get("trigger_observation") or ""
            if not evidence.strip():
                _log.warning("state_change for %s 跳过：缺少 verbatim_evidence", hid)
                continue
            if hid not in self._entries:
                _log.warning("state_change for %s 跳过：id 不存在", hid)
                continue
            entry = self._entries[hid]
            if new_state == "falsified":
                entry.add_counterexample(evidence)
            else:
                entry.add_evidence()
            self.set_state(hid, new_state)
            changed.append(hid)

        return changed

    # ── 持久化 ──────────────────────────────────────────────────────────────

    def _session_dir(self) -> Path:
        """data/hypothesis/sessions/<domain>/<session_id>/ — 通过 config.resolve_db_dir 构造。"""
        base = resolve_db_dir("hypothesis") / "sessions" / self.domain / self.session_id
        base.mkdir(parents=True, exist_ok=True)
        return base

    def save(self, iteration: int) -> Path:
        """落盘当前快照到 iter_<N>.json 和 latest.json。"""
        data = {
            "session_id": self.session_id,
            "domain": self.domain,
            "iteration": iteration,
            "entries": [asdict(e) for e in self._entries.values()],
            "tainted_ids": list(self._tainted),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        p = self._session_dir()
        (p / f"iter_{iteration:03d}.json").write_text(payload, encoding="utf-8")
        (p / "latest.json").write_text(payload, encoding="utf-8")
        return p / "latest.json"

    def to_snapshot_dict(self, iteration: int) -> dict:
        """返回符合 hypothesis.store.snapshot schema 的 dict（供 Format 流使用）。"""
        return {
            "session_id": self.session_id,
            "domain": self.domain,
            "iteration": iteration,
            "entries": [asdict(e) for e in self._entries.values()],
            "tainted_ids": list(self._tainted),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
