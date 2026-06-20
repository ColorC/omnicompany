# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-17T00:00:00Z type=pipeline status=active
# [OMNI] material_id="material:services.learning.hypothesis.team.session_controller.py"
"""hypothesis.pipeline — 假设探索循环控制器（v4: 语义判断）。

产出：每个 domain 一份主题文档（.md），含内嵌假设列表 + 第三人称史官叙事。
文档位置：data/knowledge/hypotheses/<domain>.md

循环结构：
  load or create 主题文档
  for iteration in range(max_iterations):
    主 agent（Experimenter）自由探索 → 产出行为轨迹
    总结 agent（Reflector，AgentNodeLoop）
      读轨迹 + 当前假设文档
      用工具箱（add_evidence/set_maturity/create_hypothesis 等）直接编辑文档
      所有状态判定都是它的语义判断

代码不做任何自动状态转移、不做自动证据匹配。
"""

from __future__ import annotations

import asyncio
import logging
import pathlib
import uuid
from datetime import datetime, timezone

from omnicompany.packages.services._learning.hypothesis.routers import ExperimenterRouter, ReflectorRouter
from omnicompany.packages.services._learning.knowledge.store import KBStore
from omnicompany.packages.services._learning.knowledge.index import KBIndex
from omnicompany.packages.services._learning.knowledge.schema import KHypothesisEntry

try:
    from dotenv import load_dotenv as _load_dotenv
    _ENV_FILE = pathlib.Path(__file__).parents[5] / ".env"
    if _ENV_FILE.exists():
        _load_dotenv(_ENV_FILE)
except ImportError:
    pass

log = logging.getLogger(__name__)
_PROJECT_ROOT = str(pathlib.Path(__file__).parents[5])


# ═══════════════════════════════════════════════════════════
# 主题文档操作
# ═══════════════════════════════════════════════════════════

def _load_topic_doc(store: KBStore, domain: str) -> KHypothesisEntry | None:
    """加载 domain 对应的主题文档。不存在返回 None。"""
    idx = KBIndex.from_store(store)
    doc_id = f"kb.hyp.{domain}"
    return idx.get(doc_id)


def _create_topic_doc(domain: str, goal: str, scene: dict) -> KHypothesisEntry:
    """创建新的主题文档。"""
    return KHypothesisEntry(
        id=f"kb.hyp.{domain}",
        name=f"{domain} 探索笔记",
        description=goal,
        maturity="draft",
        tags=[f"domain.{domain}"],
        scene=scene,
        hypotheses=[],
    )


def _extract_narratives_from_body(body: str) -> list[str]:
    """从已有文档的 body 里提取探索过程段落（给 Reflector 延续用）。"""
    narratives: list[str] = []
    if not body:
        return narratives
    in_section = False
    for line in body.splitlines():
        if line.strip().startswith("## 探索过程"):
            in_section = True
            continue
        if in_section:
            if line.strip().startswith("## "):
                break
            if line.strip().startswith("- "):
                narratives.append(line.strip()[2:])
    return narratives


def _render_body(doc: KHypothesisEntry, narratives: list[str]) -> str:
    """从文档的结构化数据生成人类可读 body。"""
    lines = [f"# {doc.name}", ""]
    lines.append(doc.description)
    lines.append("")

    hyps = doc.hypotheses or []

    # 关系图
    if hyps:
        lines.append("## 关系图")
        lines.append("")
        lines.append("```")
        roots = [h for h in hyps if not h.get("depends_on") and not h.get("derived_from")]
        non_roots = [h for h in hyps if h.get("depends_on") or h.get("derived_from")]
        for r in roots:
            status_mark = {"living": "✓", "stable": "✅", "deprecated": "✗"}.get(r.get("maturity", ""), "?")
            lines.append(f"[{status_mark}] {r['id']}: {r.get('summary', '')}")
            for c in non_roots:
                parent = c.get("derived_from") or ""
                deps = c.get("depends_on", [])
                if parent == r["id"] or r["id"] in deps:
                    cs = {"living": "✓", "stable": "✅", "deprecated": "✗"}.get(c.get("maturity", ""), "?")
                    rel = "精化" if parent == r["id"] else "依赖"
                    lines.append(f"  └─[{cs}] {c['id']}: {c.get('summary', '')} ({rel})")
        # 矛盾
        seen_contras: set[tuple[str, str]] = set()
        for h in hyps:
            for cid in h.get("contradicts", []) or []:
                pair = tuple(sorted([h["id"], cid]))
                if pair in seen_contras:
                    continue
                seen_contras.add(pair)
                lines.append(f"  ✗ {pair[0]} ⟷ {pair[1]} (矛盾)")
        lines.append("```")
        lines.append("")

    # 每条假设的详细 section
    for i, h in enumerate(hyps):
        hid = h.get("id", f"H{i}")
        summary = h.get("summary", "")
        mat = h.get("maturity", "draft")
        label = {"draft": "待验证", "living": "验证中",
                 "stable": "已证实", "deprecated": "已证伪"}.get(mat, "待验证")
        kind = h.get("kind", "")

        prefix = "[已证伪] " if mat == "deprecated" else ""
        lines.append(f"## {prefix}{hid}: {summary}")
        lines.append("")
        lines.append(f"**状态**: {label} · **类型**: {kind}")

        # 关联
        deps = h.get("depends_on", []) or []
        derived = h.get("derived_from", "")
        contras = h.get("contradicts", []) or []
        if deps:
            lines.append(f"**依赖**: {', '.join(deps)}")
        if derived:
            lines.append(f"**精化自**: {derived}")
        if contras:
            lines.append(f"**矛盾**: {', '.join(contras)}")
        lines.append("")

        # 验证条件
        fmt_in = h.get("format_in", {}) or {}
        fmt_out = h.get("format_out", {}) or {}
        if fmt_in.get("command"):
            lines.append(f"触发: `{fmt_in['command']}`")
        if fmt_out.get("summary"):
            lines.append(f"预期: {fmt_out['summary']}")
        elif fmt_out:
            # 兼容旧格式
            parts = []
            if fmt_out.get("exit_code") is not None:
                parts.append(f"exit_code=={fmt_out['exit_code']}")
            if fmt_out.get("output_contains"):
                parts.append(f"输出含 {fmt_out['output_contains']}")
            if parts:
                lines.append(f"预期: {', '.join(parts)}")
        if fmt_in.get("command") or fmt_out:
            lines.append("")

        # 证据
        evidence = h.get("evidence", [])
        if isinstance(evidence, list) and evidence:
            lines.append("**证据**")
            for e in evidence:
                if isinstance(e, dict):
                    desc = e.get("描述") or e.get("description") or ""
                    src = e.get("出处") or e.get("source") or ""
                    line = f"- {desc}"
                    if src:
                        line += f"（出处：{src}）"
                    lines.append(line)
                else:
                    lines.append(f"- {e}")
            lines.append("")

        # 反例
        counters = h.get("counterexamples", [])
        if isinstance(counters, list) and counters:
            lines.append("**反例**")
            for c in counters:
                if isinstance(c, dict):
                    desc = c.get("描述") or c.get("description") or ""
                    src = c.get("出处") or c.get("source") or ""
                    line = f"- {desc}"
                    if src:
                        line += f"（出处：{src}）"
                    lines.append(line)
                else:
                    lines.append(f"- {c}")
            lines.append("")

        # 状态变化日志（Reflector 调 set_maturity 时写入）
        state_log = h.get("state_log", [])
        if state_log:
            lines.append("**状态变化**")
            for entry in state_log:
                lines.append(
                    f"- {entry.get('从','?')} → {entry.get('到','?')}: {entry.get('理由','')}"
                )
            lines.append("")

    # 探索过程（史官叙事，按轮次累积）
    if narratives:
        lines.append("## 探索过程")
        lines.append("")
        for n in narratives:
            lines.append(f"- {n}")
        lines.append("")

    # 场景
    if doc.scene:
        lines.append("## 场景")
        lines.append("")
        for k, v in doc.scene.items():
            lines.append(f"- {k}: {v}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════════════════════

async def _run_session_async(session_config: dict) -> dict:
    session_id = session_config["session_id"]
    domain = session_config["domain"]
    max_iterations = session_config["max_iterations"]
    scene = session_config.get("scene", {})
    goal = session_config.get("goal", "")

    # 启动时注册本服务的 Formats 到 FormatRegistry（幂等）
    try:
        from omnicompany.protocol.format import create_builtin_registry
        from omnicompany.packages.services._learning.hypothesis.formats import register_formats
        _registry = create_builtin_registry()
        register_formats(_registry)
    except Exception as exc:
        log.warning("[hyp] 注册 Formats 失败（非致命）: %s", exc)

    # 初始化 EventBus，session_id 作为 trace_id 贯穿
    bus = None
    try:
        from omnicompany.bus.sqlite import SQLiteBus
        from omnicompany.protocol.events import FactoryEvent
        from omnicompany.protocol.registry import EventType
        bus = SQLiteBus()
        await bus.connect()
        # 发 TASK_INTENT 事件（session 开始）
        await bus.publish(FactoryEvent(
            trace_id=session_id,
            event_type=EventType.TASK_INTENT.value,
            source=f"hypothesis.pipeline.{domain}",
            payload={
                "instruction": goal,
                "domain": domain,
                "max_iterations": max_iterations,
                "scene": scene,
                "session_id": session_id,
            },
            tags=["hypothesis", f"domain.{domain}"],
        ))
    except Exception as exc:
        log.warning("[hyp] EventBus 初始化失败（降级无事件）: %s", exc)
        bus = None

    store = KBStore(_PROJECT_ROOT)
    # 把 bus 传给 routers，它们内置的 TOOL_CALL / TOOL_RESULT / LLM_CALL 会自动流出
    experimenter = ExperimenterRouter(bus=bus)
    reflector = ReflectorRouter(bus=bus)

    # 加载或创建主题文档
    doc = _load_topic_doc(store, domain)
    if doc is None:
        doc = _create_topic_doc(domain, goal, scene)
        # 创建：先走一次 KBStore.write_entry 落盘，确保文件存在供 Reflector 编辑
        body = _render_body(doc, [])
        store.write_entry(doc, body=body, overwrite=True)
        # write_entry 后 source_path 可能未填，重新 load 取
        doc = _load_topic_doc(store, domain) or doc
        log.info("[hyp] 创建新主题文档: %s -> %s", doc.id, doc.source_path)
    else:
        log.info("[hyp] 加载已有文档: %s (%d 条假设) path=%s",
                 doc.id, len(doc.hypotheses), doc.source_path)

    doc_path = doc.source_path

    for iteration in range(max_iterations):
        # 重新 load 以反映上一轮 Reflector 的文件改动
        idx = KBIndex.from_store(store)
        doc = idx.get(doc.id) or doc
        hyps = doc.hypotheses
        log.info("[hyp] iter %d | 假设 %d 条", iteration, len(hyps))

        # ── 主 agent：自由探索 ────────────────────
        store_snap = {
            "iteration": iteration,
            "entries": [
                {"id": h["id"], "kind": h.get("kind", ""),
                 "state": h.get("maturity", "draft"),
                 "trigger": (h.get("format_in", {}) or {}).get("command", ""),
                 "predicted": h.get("summary", "")}
                for h in hyps
            ],
        }
        exp_verdict = await experimenter.run({"store": store_snap, "session": session_config})
        if exp_verdict.output is None:
            log.warning("[hyp] Experimenter 无输出，终止")
            break
        trace = exp_verdict.output.get("trace", [])
        log.info("[hyp] iter %d | Experimenter 调用了 %d 次工具", iteration, len(trace))

        # ── 总结 agent：直接编辑文件 ──────────────
        # origin=internal-engine 让 Reflector 的 edit/write 通过 shield
        # （shield 规则：data/ 只有 internal-engine/internal-guardian 能写）
        ref_verdict = await reflector.run({
            "trace": trace,
            "doc_path": doc_path,
            "iteration": iteration,
            "session_id": session_id,
            "origin": "internal-engine",
            "agent_name": "ReflectorRouter",
            "domain": "services/hypothesis",
        })

        # 最终安全网校验
        from omnicompany.packages.services._learning.hypothesis.validator import validate_hypothesis_doc
        check = validate_hypothesis_doc(doc_path)
        if not check["ok"]:
            log.warning(
                "[hyp] iter %d | Reflector 结束时文档校验失败: %d errors",
                iteration, len(check["errors"])
            )
            for err in check["errors"][:5]:
                log.warning("  - %s", err)
        else:
            by_mat = check["stats"].get("by_maturity", {})
            total = check["stats"].get("total_hypotheses", 0)
            deleted = check["stats"].get("deleted_count", 0)
            log.info(
                "[hyp] iter %d | 文档校验 PASS: %d 条假设, 状态分布 %s, 归档 %d",
                iteration, total, by_mat, deleted
            )

        # 每轮完成后 emit 事件（含全量轮次状态，支持断点续跑）
        if bus is not None:
            try:
                from omnicompany.protocol.events import FactoryEvent
                from omnicompany.protocol.registry import EventType
                await bus.publish(FactoryEvent(
                    trace_id=session_id,
                    event_type=EventType.STATE_CHANGE.value,
                    source=f"hypothesis.pipeline.{domain}",
                    payload={
                        "session_id": session_id,
                        "domain": domain,
                        "iteration": iteration,
                        "doc_path": doc_path,
                        "trace_length": len(trace),
                        "validation": check,
                    },
                    tags=["hypothesis", f"domain.{domain}", "iteration"],
                ))
            except Exception as exc:
                log.warning("[hyp] iter 事件发射失败: %s", exc)

    # 最终状态
    idx = KBIndex.from_store(store)
    final_doc = idx.get(doc.id)
    total = len(final_doc.hypotheses) if final_doc else 0
    by_mat: dict[str, int] = {}
    deleted_count = 0
    if final_doc:
        for h in final_doc.hypotheses:
            m = h.get("maturity", "draft")
            by_mat[m] = by_mat.get(m, 0) + 1
        deleted_count = len(getattr(final_doc, "deleted_hypotheses", []) or [])

    result = {
        "document_id": doc.id,
        "document_path": doc_path,
        "total_hypotheses": total,
        "by_maturity": by_mat,
        "deleted_count": deleted_count,
    }

    # 发 TASK_FINISH 事件 + 关闭 bus
    if bus is not None:
        try:
            from omnicompany.protocol.events import FactoryEvent
            from omnicompany.protocol.registry import EventType
            await bus.publish(FactoryEvent(
                trace_id=session_id,
                event_type=EventType.TASK_FINISH.value,
                source=f"hypothesis.pipeline.{domain}",
                payload={
                    "session_id": session_id,
                    "domain": domain,
                    "result": result,
                },
                tags=["hypothesis", f"domain.{domain}"],
            ))
            await bus.close()
        except Exception as exc:
            log.warning("[hyp] EventBus 收尾失败（非致命）: %s", exc)

    return result


def run_session(session_config: dict) -> dict:
    """同步入口。"""
    return asyncio.run(_run_session_async(session_config))


# ═══════════════════════════════════════════════════════════
# 双脑 lockstep 入口 (2026-04-18)
# ═══════════════════════════════════════════════════════════

async def _run_lockstep_session_async(session_config: dict) -> dict:
    """双脑 lockstep 模式：Experimenter 每 turn 末等 ReflectorDaemon 完成。

    与 _run_session_async 的区别：
      - 不再外层 for max_iterations 循环调 Experimenter + Reflector 串行
      - 启一个 ReflectorDaemon task，Experimenter 每 turn on_turn_end_async 提交观察
      - daemon 跑小 agent loop（3-4 turns）编辑文档，emit reflection_result
      - daemon 可选 emit context_substitution 反哺下一 turn
    """
    from omnicompany.packages.services._learning.hypothesis.routers import LockstepExperimenterRouter
    from omnicompany.packages.services._learning.hypothesis.reflector_daemon import ReflectorDaemon

    session_id = session_config["session_id"]
    domain = session_config["domain"]
    scene = session_config.get("scene", {})
    goal = session_config.get("goal", "")

    # 注册 Formats
    try:
        from omnicompany.protocol.format import create_builtin_registry
        from omnicompany.packages.services._learning.hypothesis.formats import register_formats
        register_formats(create_builtin_registry())
    except Exception as exc:
        log.warning("[hyp-lockstep] 注册 Formats 失败（非致命）: %s", exc)

    # 初始化 bus
    bus = None
    try:
        from omnicompany.bus.sqlite import SQLiteBus
        from omnicompany.protocol.events import FactoryEvent
        from omnicompany.protocol.registry import EventType
        bus = SQLiteBus()
        await bus.connect()
        await bus.publish(FactoryEvent(
            trace_id=session_id,
            event_type=EventType.TASK_INTENT.value,
            source=f"hypothesis.pipeline.{domain}.lockstep",
            payload={"instruction": goal, "domain": domain,
                     "mode": "lockstep", "session_id": session_id, "scene": scene},
            tags=["hypothesis", f"domain.{domain}", "lockstep"],
        ))
    except Exception as exc:
        log.warning("[hyp-lockstep] bus 初始化失败（降级无事件）: %s", exc)
        bus = None

    store = KBStore(_PROJECT_ROOT)
    # 加载或创建文档
    doc = _load_topic_doc(store, domain)
    if doc is None:
        doc = _create_topic_doc(domain, goal, scene)
        body = _render_body(doc, [])
        store.write_entry(doc, body=body, overwrite=True)
        doc = _load_topic_doc(store, domain) or doc
        log.info("[hyp-lockstep] 创建新主题文档: %s -> %s", doc.id, doc.source_path)
    else:
        log.info("[hyp-lockstep] 加载已有文档: %s (%d 条假设)",
                 doc.id, len(doc.hypotheses))
    doc_path = doc.source_path

    # 构造 Reflector + daemon
    reflector = ReflectorRouter(bus=bus)
    daemon = ReflectorDaemon(
        reflector=reflector,
        bus=bus,
        session_id=session_id,
        doc_path=doc_path,
        per_step_max_turns=8,          # 每步反思 ≤8 turn（read+decide+edit+validate+fix+finish）
        reflection_timeout=180.0,
    )
    await daemon.start()

    # 构造 Lockstep Experimenter
    experimenter = LockstepExperimenterRouter(daemon=daemon, bus=bus)

    # 把 session 状态注入 Experimenter 首条 message
    idx = KBIndex.from_store(store)
    doc = idx.get(doc.id) or doc
    hyps = doc.hypotheses
    store_snap = {
        "iteration": 0,
        "entries": [
            {"id": h["id"], "kind": h.get("kind", ""),
             "state": h.get("maturity", "draft"),
             "trigger": (h.get("format_in", {}) or {}).get("command", ""),
             "predicted": h.get("summary", "")}
            for h in hyps
        ],
    }

    result: dict = {}
    try:
        exp_verdict = await experimenter.run({
            "store": store_snap,
            "session": session_config,
            "session_id": session_id,  # 修 trace_id bug
            "trace_id": session_id,
            "origin": "internal-engine",
            "agent_name": "LockstepExperimenterRouter",
            "domain": "services/hypothesis",
        })
        trace = exp_verdict.output.get("trace", []) if exp_verdict.output else []
        log.info("[hyp-lockstep] Experimenter 结束：%d 次工具调用", len(trace))
    finally:
        await daemon.stop()

    # 最终状态
    from omnicompany.packages.services._learning.hypothesis.validator import validate_hypothesis_doc
    check = validate_hypothesis_doc(doc_path)
    log.info(
        "[hyp-lockstep] 最终 validator: ok=%s errors=%d total_hyp=%d",
        check["ok"], len(check["errors"]),
        check["stats"].get("total_hypotheses", 0),
    )

    result = {
        "document_id": doc.id,
        "document_path": doc_path,
        "validator_ok": check["ok"],
        "validator_errors": len(check["errors"]),
        "total_hypotheses": check["stats"].get("total_hypotheses", 0),
        "by_maturity": check["stats"].get("by_maturity", {}),
        "deleted_count": check["stats"].get("deleted_count", 0),
    }

    # TASK_FINISH + 关 bus
    if bus is not None:
        try:
            from omnicompany.protocol.events import FactoryEvent
            from omnicompany.protocol.registry import EventType
            await bus.publish(FactoryEvent(
                trace_id=session_id,
                event_type=EventType.TASK_FINISH.value,
                source=f"hypothesis.pipeline.{domain}.lockstep",
                payload={"session_id": session_id, "result": result},
                tags=["hypothesis", f"domain.{domain}", "lockstep"],
            ))
            await bus.close()
        except Exception as exc:
            log.warning("[hyp-lockstep] 收尾失败（非致命）: %s", exc)

    return result


def run_lockstep_session(session_config: dict) -> dict:
    """双脑 lockstep 模式的同步入口。"""
    return asyncio.run(_run_lockstep_session_async(session_config))


def new_session(domain: str, goal: str, tools: list[str] | None = None,
                max_iterations: int = 3, env: dict | None = None,
                scene: dict | None = None) -> dict:
    return {
        "session_id": str(uuid.uuid4()),
        "domain": domain,
        "goal": goal,
        "tools": tools or [],
        "max_iterations": max_iterations,
        "env": env or {"MSYS_NO_PATHCONV": "1"},
        "scene": scene or {},
    }


# ═══════════════════════════════════════════════════════════
# TeamSpec (拓扑声明，供 omni describe / register 用)
# ═══════════════════════════════════════════════════════════
#
# 说明：hypothesis 的真实执行走 run_session() 的外部 N 轮循环。
# 这里的 TeamSpec 是**拓扑的可视化声明**，让 `omni describe hypothesis`
# 能展示数据流。运行时不由 TeamRunner 驱动（loop 不在 TeamSpec 语义内）。
#
# 未来可把 run_session 迁入 TeamRunner + iteration_gate 自循环的形态，
# 但当前先满足可观测性。

from omnicompany.protocol.team import (
    NodeKind, NodeMaturity, TeamEdge, TeamNode, TeamSpec,
)
from omnicompany.protocol.anchor import (
    TransformerSpec, TransformMethod,
    Route, RouteAction, VerdictKind,
)


def build_team() -> TeamSpec:
    """hypothesis 探索管线拓扑（描述用）。

    真实执行入口是 hypothesis.pipeline.run_session，它外部驱动 N 轮
    Experimenter→Reflector 循环。TeamRunner 调用此 spec 只会跑一轮。
    """
    nodes = [
        TeamNode(
            id="experimenter",
            kind=NodeKind.TRANSFORMER,
            transformer=TransformerSpec(
                id="hypothesis-experimenter",
                name="Experimenter",
                description=(
                    "主 agent（AgentNodeLoop）。读 session + 当前假设库，"
                    "自由用 bash/read_file/glob/grep 探索目标系统，"
                    "输出完整行为轨迹（tool_use + tool_result 对列表）。"
                ),
                from_format="hypothesis.session",
                to_format="hypothesis.factlog",
                method=TransformMethod.LLM,
            ),
            maturity=NodeMaturity.GROWING,
        ),
        TeamNode(
            id="reflector",
            kind=NodeKind.TRANSFORMER,
            transformer=TransformerSpec(
                id="hypothesis-reflector",
                name="Reflector",
                description=(
                    "总结 agent（AgentNodeLoop，origin=internal-engine）。"
                    "读 Experimenter 行为轨迹 + 当前文档，用 IDE_TOOLS 直接编辑 "
                    ".md 文件（加证据/改状态/创建假设/归档删除/写史官叙事）。"
                    "每次写后调 validate_hypothesis_doc 自查。"
                ),
                from_format="hypothesis.factlog",
                to_format="hypothesis.store_diff",
                method=TransformMethod.LLM,
            ),
            maturity=NodeMaturity.GROWING,
        ),
    ]

    edges = [
        TeamEdge(
            source="experimenter",
            target="reflector",
            condition=VerdictKind.PASS,
        ),
    ]

    return TeamSpec(
        id="hypothesis",
        name="假设探索管线",
        description=(
            "Experimenter→Reflector 两阶段管线。TeamSpec 是拓扑声明，"
            "真实多轮循环由 hypothesis.pipeline.run_session 外部驱动。"
        ),
        purpose=(
            "给 agent 可跨 session 累积的知识沉淀设施：自由探索 + 归纳假设 + "
            "记录证据与状态转移 + 维护关系网络"
        ),
        nodes=nodes,
        edges=edges,
        entry="experimenter",
    )
