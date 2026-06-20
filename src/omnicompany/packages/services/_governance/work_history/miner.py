# [OMNI] origin=claude-code domain=services/_governance/work_history ts=2026-06-12T12:00:00Z type=router
# [OMNI] material_id="material:governance.work_history.mining_pipeline.py"
"""工作历史挖掘管线 — map(分块提信号) → cluster(去重聚类) → reduce(终稿)。

产出 data/governance/work_history/:
- findings-<ts>.json: {"recurring_needs": [...], "recurring_corrections": [...]}
- report-<ts>.md: 人读报告(中文)
- latest.json: 指向最近一次的指针(消费方: quick_actions 重生成、总控)

重复需求 = 用户反复让 AI 干的活(quick_actions 的唯一合法证据来源);
重复指正 = 用户反复纠偏的内容(对照两边 memory 标注"是否已被记录")。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnicompany.core.config import omni_workspace_root
from omnicompany.runtime.llm.batch import (
    JsonCheckpoint,
    load_json_checkpoint,
    run_parallel_items,
    write_json_checkpoint,
)
from omnicompany.runtime.llm.structured import call_json, default_structured_model
from .sources import claude_user_messages, codex_user_messages, memory_snippets

CHUNK_CHARS = 9000
# 2026-06-12 实跑教训: 220 行/批的聚类输出会撞 max_tokens 截断 → JSON 解析失败
CLUSTER_BATCH = 120

MAP_SYSTEM = """你是用户工作历史整理员。输入是用户在 AI 编码会话里亲手发的消息(已去系统注入), 每行格式 [日期|来源|目录] 内容。
提取两类信号:
A. need(需求/工作内容): 用户让 AI 做的具体业务动作, 要可归类可复发(如"跑某游戏config_table""按 figma 生成组件""重启测试服""整理周报")。一次性闲聊、纯确认("好""继续")不算。
B. correction(指正/纠偏): 用户对 AI 工作方式的不满、纠正、立规矩(如"别问我小事""先调研再做""测试要走真实 UI")。
输出严格 JSON, 不要其它文字:
{"signals":[{"kind":"need|correction","gist":"不超过20字概括","quote":"一句代表性原话(截断60字内)","project":"目录/内容推断的项目词, 如 gameplay_system/prefab/omnicompany/quant/walker/vilo/unknown"}]}
没有信号输出 {"signals":[]}。宁缺毋滥。"""

CLUSTER_SYSTEM = """你是信号聚类员。输入若干行同一类型的信号: gist|project|quote。
把同义/同主题的合并成簇, 输出严格 JSON:
{"clusters":[{"title":"不超过18字","count":合并的条数,"projects":["出现过的项目词"],"examples":["最多3条代表性quote"]}]}
硬性要求:
1. 簇要具体到"能据此开一项工作"的粒度(如"按figma临摹标准组件""重启游戏测试服"), 禁止"全栈优化""项目管理"这类大箩筐。
2. 不要丢信息量大的簇; 只出现一次且无代表性的可弃。
3. examples 必须原样照抄输入里的 quote, 不许改写。
不要其它文字。"""

REDUCE_SYSTEM = """你是用户工作历史的总编辑。输入: (1) 需求簇 (2) 指正簇 (3) 用户已有的长期 memory 摘要。
产出终稿, 输出严格 JSON:
{"recurring_needs":[{"title":"不超过18字","count":次数,"projects":[...],"examples":["原话(60字内)x≤3"],"quick_action_hint":"若适合做成项目页一键工作选项, 给一句建议; 否则 null"}],
 "recurring_corrections":[{"title":"不超过18字","count":次数,"examples":[...],"already_in_memory":true|false}]}
硬性规则: recurring_needs 只能来自需求簇, recurring_corrections 只能来自指正簇, 两边内容不得互相复制。
排序按 count 降序; 需求保留 count>=2 的, 指正全部保留。already_in_memory: 对照 memory 摘要判断该指正是否已被沉淀。不要其它文字。"""

MAP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["signals"],
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "gist"],
                "properties": {
                    "kind": {"type": "string", "enum": ["need", "correction"]},
                    "gist": {"type": "string", "minLength": 1},
                    "quote": {"type": "string"},
                    "project": {"type": "string"},
                },
            },
        },
    },
}

CLUSTER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["clusters"],
    "properties": {
        "clusters": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "count"],
                "properties": {
                    "title": {"type": "string", "minLength": 1},
                    "count": {"type": "integer"},
                    "projects": {"type": "array", "items": {"type": "string"}},
                    "examples": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

FINDINGS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["recurring_needs", "recurring_corrections"],
    "properties": {
        "recurring_needs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "count"],
                "properties": {
                    "title": {"type": "string"},
                    "count": {"type": "integer"},
                    "projects": {"type": "array", "items": {"type": "string"}},
                    "examples": {"type": "array", "items": {"type": "string"}},
                    "quick_action_hint": {"type": ["string", "null"]},
                },
            },
        },
        "recurring_corrections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["title", "count"],
                "properties": {
                    "title": {"type": "string"},
                    "count": {"type": "integer"},
                    "examples": {"type": "array", "items": {"type": "string"}},
                    "already_in_memory": {"type": ["boolean", "null"]},
                },
            },
        },
    },
}

ASSIGN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["assign"],
    "properties": {
        "assign": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["idx", "projects"],
                "properties": {
                    "idx": {"type": "integer"},
                    "projects": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}

ASSIGN_MODEL_ENV = "OMNI_STRUCTURED_ASSIGN_MODEL"
ASSIGN_MODEL_DEFAULT = "glm-5.1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def out_dir() -> Path:
    d = omni_workspace_root() / "data" / "governance" / "work_history"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _signals_checkpoint() -> JsonCheckpoint:
    return JsonCheckpoint(
        data_path=out_dir() / "_last_signals.json",
        meta_path=out_dir() / "_last_meta.json",
        missing_error="没有 _last_signals.json, 不能 --from-signals",
    )


def _clusters_checkpoint() -> JsonCheckpoint:
    return JsonCheckpoint(data_path=out_dir() / "_last_clusters.json")


def _collect(days: int, source: str) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = []
    if source in ("all", "claude"):
        msgs.extend(claude_user_messages(days))
    if source in ("all", "codex"):
        msgs.extend(codex_user_messages(days))
    msgs.sort(key=lambda m: m["ts"])
    return msgs


def _chunks(msgs: list[dict[str, Any]]) -> list[str]:
    chunks, buf, size = [], [], 0
    for m in msgs:
        line = f"[{m['ts'][:10]}|{m['src']}|{Path(str(m['proj'])).name[:30]}] {m['text']}"
        if size + len(line) > CHUNK_CHARS and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        buf.append(line)
        size += len(line)
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def _map_chunk(chunk: str, model: str) -> list[dict[str, Any]]:
    res = call_json(system=MAP_SYSTEM, user=chunk, schema=MAP_SCHEMA, model=model,
                    caller="governance.work_history.map", max_tokens=4000)
    return [s for s in (res.get("signals") or []) if isinstance(s, dict) and s.get("gist")]


def _cluster_one_kind(kind: str, signals: list[dict[str, Any]], model: str, echo,
                      failures: list[str]) -> list[dict[str, Any]]:
    """单一类型信号的聚类。kind 由代码标注, 不让模型填(2026-06-12: 模型把提示词里的
    枚举字面量 need|correction 原样抄成 kind 值, 下游分流两边落空)。"""
    lines = [f"{s.get('gist')}|{s.get('project')}|{s.get('quote', '')[:60]}" for s in signals]
    batches = [lines[i:i + CLUSTER_BATCH] for i in range(0, len(lines), CLUSTER_BATCH)]
    clusters: list[dict[str, Any]] = []
    for i, b in enumerate(batches):
        # 单批失败只丢这一批, 不许炸全场(2026-06-12: map 273 块的成果被一个聚类批拖死)
        try:
            res = call_json(system=CLUSTER_SYSTEM, user="\n".join(b), schema=CLUSTER_SCHEMA, model=model,
                            caller=f"governance.work_history.cluster.{kind}", max_tokens=12000)
            clusters.extend(res.get("clusters") or [])
        except Exception as e:  # noqa: BLE001
            failures.append(f"cluster[{kind}] 批 {i + 1}: {e}")
        echo(f"  聚类[{kind}] 批 {i + 1}/{len(batches)} → 累计 {len(clusters)} 簇")
    if len(batches) > 1 and len(clusters) > 8:
        # 跨批再合一轮(只合并同义簇, 粒度要求同上)
        lines2 = [f"{c.get('title')}(x{c.get('count')})|{','.join(c.get('projects') or [])}|{(c.get('examples') or [''])[0][:60]}"
                  for c in clusters]
        try:
            res = call_json(system=CLUSTER_SYSTEM, user="\n".join(lines2), schema=CLUSTER_SCHEMA, model=model,
                            caller=f"governance.work_history.cluster2.{kind}", max_tokens=12000)
            merged = res.get("clusters") or []
            if merged:
                clusters = merged
                echo(f"  聚类[{kind}] 跨批合并 → {len(clusters)} 簇")
        except Exception as e:  # noqa: BLE001
            failures.append(f"cluster[{kind}] 跨批合并: {e}(保留未合并簇)")
    for c in clusters:
        c["kind"] = kind
    return clusters


def _cluster(signals: list[dict[str, Any]], model: str, echo,
             failures: list[str]) -> list[dict[str, Any]]:
    def _norm(k: Any) -> str:
        k = str(k or "").strip().lower()
        return "correction" if k.startswith("correction") else "need"
    needs = [s for s in signals if _norm(s.get("kind")) == "need"]
    corrs = [s for s in signals if _norm(s.get("kind")) == "correction"]
    return (_cluster_one_kind("need", needs, model, echo, failures)
            + _cluster_one_kind("correction", corrs, model, echo, failures))


def run_mining(*, days: int = 45, source: str = "all", model: str | None = None,
               workers: int = 4, limit_chunks: int | None = None,
               from_signals: bool = False, echo: Any = None) -> dict[str, Any]:
    log = echo or (lambda s: None)
    model = model or default_structured_model()
    failures: list[str] = []
    if from_signals:
        # 从上次落盘的 map 产物续跑(map 是最贵的一段; 聚类/终稿改提示词后重跑用)
        loaded = load_json_checkpoint(_signals_checkpoint())
        if not loaded.ok:
            return {"ok": False, "error": loaded.error}
        signals = loaded.data if isinstance(loaded.data, list) else []
        meta_prev = loaded.meta
        msgs_n, chunks_n = meta_prev.get("messages", 0), meta_prev.get("chunks", 0)
        log(f"从落盘信号续跑: {len(signals)} 条信号, 模型 {model}")
    else:
        msgs = _collect(days, source)
        chunks = _chunks(msgs)
        if limit_chunks:
            chunks = chunks[:limit_chunks]
        msgs_n, chunks_n = len(msgs), len(chunks)
        log(f"用户消息 {msgs_n} 条(近 {days} 天, 源 {source}) → {chunks_n} 块, 模型 {model}")

        map_run = run_parallel_items(
            chunks,
            lambda chunk: _map_chunk(chunk, model),
            workers=workers,
            item_label=lambda index, _chunk: f"map 块 {index}",
            echo=log,
            progress_label="map",
            progress_every=10,
            status_run_id="governance.work_history.map",
        )
        signals = [signal for chunk_signals in map_run.results for signal in chunk_signals]
        failures.extend(map_run.failures)

    if not signals:
        return {"ok": False, "error": "没有提取到任何信号", "failures": failures}

    # 中间产物落盘 — map 是最贵的一段, 后面再炸也能从这里续跑
    write_json_checkpoint(
        _signals_checkpoint(),
        signals,
        meta={"messages": msgs_n, "chunks": chunks_n, "days": days, "source": source},
    )

    clusters = _cluster(signals, model, log, failures)
    write_json_checkpoint(_clusters_checkpoint(), clusters)
    mems = memory_snippets()
    mem_brief = "\n\n".join(f"### {m['src']}\n{m['text'][:1200]}" for m in mems[:40])
    # kind 在代码层分流, 不指望模型自己分(2026-06-12 冒烟: 终稿把需求复制进了指正栏)
    need_clusters = [c for c in clusters if c.get("kind") == "need"]
    corr_clusters = [c for c in clusters if c.get("kind") == "correction"]
    user = ("## 需求簇\n" + json.dumps(need_clusters, ensure_ascii=False)
            + "\n\n## 指正簇\n" + json.dumps(corr_clusters, ensure_ascii=False)
            + "\n\n## 用户已有 memory 摘要\n" + mem_brief[:30000])
    try:
        findings = call_json(system=REDUCE_SYSTEM, user=user, schema=FINDINGS_SCHEMA, model=model,
                             caller="governance.work_history.reduce", max_tokens=8000)
    except Exception as e:  # noqa: BLE001
        # 终稿降级: 直接用簇出稿(没有润色/memory比对), 保证一定有产物
        failures.append(f"reduce 失败, 降级出稿: {e}")
        key = lambda c: -(c.get("count") or 0)  # noqa: E731
        findings = {
            "reduce_degraded": True,
            "recurring_needs": [
                {"title": c.get("title"), "count": c.get("count"),
                 "projects": c.get("projects") or [], "examples": c.get("examples") or [],
                 "quick_action_hint": None}
                for c in sorted(need_clusters, key=key) if (c.get("count") or 0) >= 2],
            "recurring_corrections": [
                {"title": c.get("title"), "count": c.get("count"),
                 "examples": c.get("examples") or [], "already_in_memory": None}
                for c in sorted(corr_clusters, key=key)],
        }

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    meta = {"generated_at": _now(), "days": days, "source": source, "model": model,
            "messages": msgs_n, "chunks": chunks_n, "signals": len(signals),
            "clusters": len(clusters), "failures": failures}
    fj = out_dir() / f"findings-{stamp}.json"
    fj.write_text(json.dumps({**meta, **findings}, ensure_ascii=False, indent=1), encoding="utf-8")
    rp = out_dir() / f"report-{stamp}.md"
    rp.write_text(_render_report(findings, meta), encoding="utf-8")
    (out_dir() / "latest.json").write_text(json.dumps(
        {"findings": fj.name, "report": rp.name, **meta}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    return {"ok": True, **meta, "findings_file": str(fj), "report": str(rp),
            "needs": len(findings.get("recurring_needs") or []),
            "corrections": len(findings.get("recurring_corrections") or [])}


ASSIGN_SYSTEM = """你是工作历史的项目分配员。输入: (1) 已注册项目清单 (2) 重复需求/重复指正条目(带粗糙的项目词提示)。
给每条分配 0~2 个注册项目 id:
- 这条工作/指正明确属于某项目的日常 → 给该项目 id
- 通用工作方式类(如"报告要通俗""即刻开工")或跨全部项目 → 空数组
- 项目词提示是粗糙线索(有错拼/目录名), 以条目内容为准
输出严格 JSON: {"assign":[{"idx":0,"projects":["项目id"]}]}, 不要其它文字。"""


def assign_projects(*, model: str | None = None, echo: Any = None) -> dict[str, Any]:
    """把最近一次 findings 的需求/指正分配到注册项目, 写回 findings 文件。

    用户(2026-06-12): "重复需求和重复指正可以分配到项目上"。消费方:
    /api/projects/{id}/findings → 项目详情页「历史证据」页签。
    """
    log = echo or (lambda s: None)
    model = model or default_structured_model(env_var=ASSIGN_MODEL_ENV, fallback=ASSIGN_MODEL_DEFAULT)
    ptr = out_dir() / "latest.json"
    if not ptr.is_file():
        return {"ok": False, "error": "还没跑过 history-run"}
    meta = json.loads(ptr.read_text(encoding="utf-8"))
    fpath = out_dir() / meta["findings"]
    findings = json.loads(fpath.read_text(encoding="utf-8"))

    from omnicompany.core.projects_registry import list_projects
    catalog = [{"id": p["id"], "name": p.get("name"), "desc": (p.get("desc") or "")[:80]}
               for p in list_projects()]

    items = []
    for kind_key in ("recurring_needs", "recurring_corrections"):
        for it in findings.get(kind_key) or []:
            items.append({"idx": len(items), "kind": kind_key, "title": it.get("title"),
                          "hints": it.get("projects") or [],
                          "example": (it.get("examples") or [""])[0][:60], "_ref": it})
    if not items:
        return {"ok": False, "error": "findings 里没有条目"}

    user = ("## 已注册项目\n" + json.dumps(catalog, ensure_ascii=False)
            + "\n\n## 条目\n" + json.dumps(
                [{k: v for k, v in it.items() if k != "_ref"} for it in items],
                ensure_ascii=False))
    res = call_json(system=ASSIGN_SYSTEM, user=user, schema=ASSIGN_SCHEMA, model=model,
                    caller="governance.work_history.assign", max_tokens=8000)
    valid = {c["id"] for c in catalog}
    assigned_n = 0
    by_idx = {int(a.get("idx", -1)): a for a in res.get("assign") or []}
    for it in items:
        a = by_idx.get(it["idx"])
        projs = [p for p in (a.get("projects") or []) if p in valid] if a else []
        it["_ref"]["assigned"] = projs
        if projs:
            assigned_n += 1
    findings["assigned_at"] = _now()
    findings["assign_model"] = model
    fpath.write_text(json.dumps(findings, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"已分配 {assigned_n}/{len(items)} 条(其余判定为通用/跨项目)")
    return {"ok": True, "total": len(items), "assigned": assigned_n,
            "findings_file": str(fpath)}


def latest_findings() -> dict[str, Any] | None:
    ptr = out_dir() / "latest.json"
    if not ptr.is_file():
        return None
    try:
        meta = json.loads(ptr.read_text(encoding="utf-8"))
        return json.loads((out_dir() / meta["findings"]).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        return None


def _render_report(findings: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        f"# 工作历史整理报告 — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"近 {meta['days']} 天 · {meta['source']} · 用户消息 {meta['messages']} 条 → "
        f"信号 {meta['signals']} → 簇 {meta['clusters']} · 模型 {meta['model']}",
        "",
        "## 重复需求(quick_actions 的合法证据来源)",
        "",
    ]
    for n in findings.get("recurring_needs") or []:
        lines.append(f"- **{n.get('title')}** ×{n.get('count')} ({', '.join(n.get('projects') or [])})")
        for q in (n.get("examples") or [])[:2]:
            lines.append(f"  - 「{q}」")
        if n.get("quick_action_hint"):
            lines.append(f"  - 建议: {n['quick_action_hint']}")
    lines += ["", "## 重复指正(工作方式纠偏)", ""]
    for c in findings.get("recurring_corrections") or []:
        mark = "已沉淀" if c.get("already_in_memory") else "**未沉淀**"
        lines.append(f"- **{c.get('title')}** ×{c.get('count')} [{mark}]")
        for q in (c.get("examples") or [])[:2]:
            lines.append(f"  - 「{q}」")
    if meta.get("failures"):
        lines += ["", "## 失败块", ""] + [f"- {f}" for f in meta["failures"]]
    return "\n".join(lines) + "\n"
