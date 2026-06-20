# [OMNI] origin=claude-code domain=services/hypothesis/reflector_daemon.py ts=2026-04-18T00:00:00Z
# [OMNI] material_id="material:services.learning.hypothesis.reflectord_daemon.lockstep_engine.py"
"""hypothesis.reflector_daemon — 双脑 lockstep 反思脑 daemon (2026-04-18)。

与 Experimenter 通过 in-process asyncio.Queue 通信，严格同步 (Experimenter
每 turn 末 block 等 daemon 处理完才走下一步)。所有语义事件同时落 EventBus:
  - hyp.step_observation   (Experimenter 发)
  - hyp.reflection_result  (daemon 完成一次反思后发)
  - hyp.context_substitution (daemon 可选发，为下一 turn 准备)

为什么 in-process 通道而非纯 bus.subscribe():
  SQLiteBus.subscribe 内部 1s 轮询，严格同步下每 turn 会引入 ~2s 延迟。
  in-process Queue 零延迟，且**语义上依然是"事件订阅"**——daemon 是 Experimenter
  的事件订阅者，只是订阅通道既有内存 Queue 也有 bus（后者用于可审计/可回放）。

Reflector 粒度:
  每个 observation 触发一次小 agent loop (~3-4 turns)，不是长多轮——
  "对一步行为的反思" 是有限任务，不该跑 200 turn 那种。
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# 数据结构
# ════════════════════════════════════════════════════════════════════════════


@dataclass
class StepObservation:
    """Experimenter 一步的完整可观察单元。对应 Format hypothesis.step_observation。"""
    session_id: str
    turn: int
    tool: str
    args: dict
    result: str
    doc_snapshot: dict = field(default_factory=dict)

    def to_payload(self) -> dict:
        # 2026-04-18 零容忍截断：完整 result 给反思脑。之前 [:4000] 会让 Reflector
        # 对后半 tool result 无感知。见 docs/standards/llm_first.md 原则 3。
        return {
            "session_id": self.session_id,
            "turn": self.turn,
            "tool": self.tool,
            "args": self.args,
            "result": self.result if isinstance(self.result, str) else str(self.result),
            "doc_snapshot": self.doc_snapshot,
        }


@dataclass
class ContextSubstitution:
    """反思脑反哺主脑的上下文代换候选。对应 Format hypothesis.context_substitution。"""
    session_id: str
    observation_turn: int
    kind: str          # fact | warning | hint | hypothesis_ref | redirect
    priority: int      # 0-10
    content: str

    def to_payload(self) -> dict:
        return {
            "session_id": self.session_id,
            "observation_turn": self.observation_turn,
            "kind": self.kind,
            "priority": self.priority,
            "content": self.content,
        }


@dataclass
class ReflectionResult:
    """反思脑对一个 observation 的反思产物。对应 Format hypothesis.reflection_result。"""
    session_id: str
    observation_turn: int
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    validator_ok: bool = False
    validator_errors: int = 0
    emitted_substitution: bool = False
    summary: str = ""
    substitutions: list[ContextSubstitution] = field(default_factory=list)

    def to_payload(self) -> dict:
        return {
            "session_id": self.session_id,
            "observation_turn": self.observation_turn,
            "added": self.added,
            "modified": self.modified,
            "deleted": self.deleted,
            "validator_ok": self.validator_ok,
            "validator_errors": self.validator_errors,
            "emitted_substitution": self.emitted_substitution,
            "summary": self.summary[:200],
        }


# ════════════════════════════════════════════════════════════════════════════
# Daemon
# ════════════════════════════════════════════════════════════════════════════


class ReflectorDaemon:
    """反思脑 daemon。

    生命周期:
      d = ReflectorDaemon(reflector=ReflectorRouter(bus=bus), bus=bus, session_id=...)
      await d.start()
      ...  # Experimenter 在 on_turn_end_async 调 d.submit_and_wait(obs)
      await d.stop()  # 发毒丸信号让 worker 退出
    """

    def __init__(
        self,
        *,
        reflector: Any,          # ReflectorRouter 实例
        bus: Any | None = None,
        session_id: str,
        doc_path: str,
        per_step_max_turns: int = 8,
        reflection_timeout: float = 120.0,
    ) -> None:
        self._reflector = reflector
        self._bus = bus
        self._session_id = session_id
        self._doc_path = doc_path
        self._per_step_max_turns = per_step_max_turns
        self._reflection_timeout = reflection_timeout

        self._inbox: asyncio.Queue = asyncio.Queue()
        self._done_events: dict[int, asyncio.Event] = {}
        self._results: dict[int, ReflectionResult] = {}
        self._task: asyncio.Task | None = None
        self._stopped = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopped = True
        await self._inbox.put(None)
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                log.warning("[reflector_daemon] stop timeout，取消任务")
                self._task.cancel()

    async def submit_and_wait(
        self, observation: StepObservation
    ) -> ReflectionResult:
        """Experimenter 调用：提交一步观察 + block 等反思完成，返回结果。

        如果 daemon 失败，返回一个 empty result 不阻塞主循环（错误事件也 emit）。
        """
        turn = observation.turn
        done_event = asyncio.Event()
        self._done_events[turn] = done_event
        await self._inbox.put(observation)
        try:
            await asyncio.wait_for(done_event.wait(), timeout=self._reflection_timeout)
        except asyncio.TimeoutError:
            log.warning(
                "[reflector_daemon] turn %d 反思超时 %ss，主脑继续",
                turn, self._reflection_timeout,
            )
            return ReflectionResult(
                session_id=self._session_id, observation_turn=turn,
                summary="reflection_timeout",
            )
        return self._results.pop(turn, ReflectionResult(
            session_id=self._session_id, observation_turn=turn,
            summary="no_result",
        ))

    # ── 内部 worker ──

    async def _run(self) -> None:
        while True:
            obs = await self._inbox.get()
            if obs is None:
                break
            try:
                result = await asyncio.wait_for(
                    self._reflect_one(obs),
                    timeout=self._reflection_timeout,
                )
            except asyncio.TimeoutError:
                log.warning("[reflector_daemon] _reflect_one turn %d 内部超时", obs.turn)
                result = ReflectionResult(
                    session_id=self._session_id, observation_turn=obs.turn,
                    summary="internal_timeout",
                )
            except Exception as exc:
                log.exception("[reflector_daemon] _reflect_one turn %d 失败", obs.turn)
                result = ReflectionResult(
                    session_id=self._session_id, observation_turn=obs.turn,
                    summary=f"error: {type(exc).__name__}: {exc}"[:200],
                )
            self._results[obs.turn] = result
            ev = self._done_events.pop(obs.turn, None)
            if ev is not None:
                ev.set()

    async def _reflect_one(self, obs: StepObservation) -> ReflectionResult:
        """执行一次反思。"""
        # 1. emit step_observation 到 bus
        await self._emit_event(
            "hyp.step_observation", obs.to_payload(),
            tags=["hypothesis", "step_observation", "lockstep"],
        )

        # 2. 取当前 validator 状态（反思前）
        pre_state = self._snapshot_doc_state()

        # 3. 跑 Reflector 小 agent loop —— 复用现有 ReflectorRouter
        #    注入单步 trace（1 个元素），让它在文档上做一次编辑周期
        #    关键：per_step_max_turns 压成 3-4
        trace_single = [{"tool": obs.tool, "args": obs.args, "result": obs.result}]

        # 临时压缩 max_turns（小循环，由 per_step_max_turns 控制，默认 8）
        from omnicompany.runtime.agent.agent_loop_config import (
            LoopConfig, CompactConfig, PermissionConfig,
        )
        original_cfg = getattr(self._reflector, "_config", None)
        self._reflector._config = LoopConfig(
            max_turns=self._per_step_max_turns,
            compact=getattr(original_cfg, "compact", CompactConfig(auto_compact_enabled=False)),
            permission=getattr(original_cfg, "permission", PermissionConfig(mode="default")),
        )
        try:
            verdict = await self._reflector.run({
                "trace": trace_single,
                "doc_path": self._doc_path,
                "iteration": obs.turn,
                "session_id": self._session_id,
                "origin": "internal-engine",
                "agent_name": "ReflectorDaemon",
                "domain": "services/hypothesis",
            })
        finally:
            self._reflector._config = original_cfg

        # 4. 对比前后状态得出 diff
        post_state = self._snapshot_doc_state()
        added, modified, deleted = _diff_hypothesis_sets(pre_state, post_state)

        from omnicompany.packages.services._learning.hypothesis.validator import validate_hypothesis_doc
        v = validate_hypothesis_doc(self._doc_path)

        # 5. 决定是否发 context_substitution
        #    最小版本：如果 Reflector 加了新假设 / 修改了状态，就 emit 一条 hint
        subs: list[ContextSubstitution] = []
        if added:
            subs.append(ContextSubstitution(
                session_id=self._session_id,
                observation_turn=obs.turn,
                kind="fact",
                priority=7,
                content=f"[反思脑·turn {obs.turn}] 本步观察触发新假设: {', '.join(added)}",
            ))
        if deleted:
            subs.append(ContextSubstitution(
                session_id=self._session_id,
                observation_turn=obs.turn,
                kind="warning",
                priority=8,
                content=f"[反思脑·turn {obs.turn}] 本步观察导致假设被证否归档: {', '.join(deleted)}",
            ))

        result = ReflectionResult(
            session_id=self._session_id,
            observation_turn=obs.turn,
            added=added,
            modified=modified,
            deleted=deleted,
            validator_ok=v.get("ok", False),
            validator_errors=len(v.get("errors", [])),
            emitted_substitution=bool(subs),
            summary=f"added={len(added)} modified={len(modified)} deleted={len(deleted)}",
            substitutions=subs,
        )

        # 6. emit 结果事件
        await self._emit_event(
            "hyp.reflection_result", result.to_payload(),
            tags=["hypothesis", "reflection_result", "lockstep"],
        )
        for sub in subs:
            await self._emit_event(
                "hyp.context_substitution", sub.to_payload(),
                tags=["hypothesis", "context_substitution", "lockstep"],
            )

        return result

    def _snapshot_doc_state(self) -> set[str]:
        """取当前假设文档里所有 hypothesis id 的集合（供 diff）。"""
        try:
            import yaml
            import re
            from pathlib import Path
            text = Path(self._doc_path).read_text(encoding="utf-8")
            m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL | re.MULTILINE)
            if not m:
                return set()
            fm = yaml.safe_load(m.group(1)) or {}
            hyps = fm.get("hypotheses", []) or []
            deleted = fm.get("deleted_hypotheses", []) or []
            active = {h.get("id") for h in hyps if isinstance(h, dict) and h.get("id")}
            arch = {f"deleted:{d.get('id')}" for d in deleted if isinstance(d, dict) and d.get("id")}
            return active | arch
        except Exception:
            return set()

    async def _emit_event(
        self, event_type: str, payload: dict, tags: list[str],
    ) -> None:
        if self._bus is None:
            return
        try:
            from omnicompany.protocol.events import FactoryEvent
            await self._bus.publish(FactoryEvent(
                trace_id=self._session_id,
                event_type=event_type,
                source="hypothesis.reflector_daemon",
                payload=payload,
                tags=tags,
            ))
        except Exception as exc:
            log.debug("[reflector_daemon] emit %s failed: %s", event_type, exc)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════


def _diff_hypothesis_sets(pre: set[str], post: set[str]) -> tuple[list[str], list[str], list[str]]:
    """粗略 diff：只识别 active 集合的增/减；modified 暂不精确（留 future）。"""
    added = sorted(post - pre)
    deleted = sorted(pre - post)
    # active → deleted 的归档（`id` 变 `deleted:id`）手动处理
    pre_active = {x for x in pre if not x.startswith("deleted:")}
    post_deleted = {x.removeprefix("deleted:") for x in post if x.startswith("deleted:")}
    archived = sorted(pre_active & post_deleted)
    if archived:
        # archived 视为 deleted
        deleted = sorted(set(deleted) | set(archived))
        # 并从 added 里去掉 deleted: 前缀的条目
        added = [a for a in added if not a.startswith("deleted:")]
    return added, [], deleted
