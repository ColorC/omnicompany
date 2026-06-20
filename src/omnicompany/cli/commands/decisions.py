# [OMNI] origin=ai-ide domain=decisions/cli ts=2026-06-18T00:00:00Z type=cli status=active
# [OMNI] summary="omni decisions — 统一决策库的手记/召回/连边/体检入口。主线=决策记录:手记一条 → 落库 → 查回 → 接进决策树。"
# [OMNI] why="决策记录主线要先能'手记+查回'才算可用(非提取)。提供源无关的人读/手填入口,抽取管线后续往同一库灌数。"
# [OMNI] tags=decisions,cli,decision-record,library
"""omni decisions —— 统一决策库导航 + 手记 + 召回。

手记决策: omni decisions record --kind decision -s "选了X" --reject "A:贵" --choose "X:稳" -r "因为..."
手记猜想: omni decisions record --kind belief   -s "猜Y成立" --risk high --query "怎么验"
查重/召回: omni decisions find "X"      看一条: omni decisions show <id>
接树:     omni decisions link <决策id> rests_on <猜想id>
"""

from __future__ import annotations

import click

from .._access import any_caller

_KINDS = ["decision", "belief", "comment"]


def _parse_opt_why(raw: str) -> tuple[str, str]:
    """'选项:理由' → (选项, 理由)。无冒号则整串为选项。"""
    if ":" in raw:
        opt, why = raw.split(":", 1)
        return opt.strip(), why.strip()
    return raw.strip(), ""


@click.group("decisions")
def cmd_decisions() -> None:
    """统一决策库:手记决策/猜想/评论,召回,接进决策树。"""


@cmd_decisions.command("status")
@any_caller
def cmd_decisions_status() -> None:
    """决策库落点 + 计数(按 kind)。"""
    from collections import Counter

    from omnicompany.packages.domains.decisions import _paths, library

    recs = library.active_records()
    by_kind = Counter(r.get("kind", "?") for r in recs)
    click.echo("== 统一决策库 ==")
    click.echo(f"  库文件 : {_paths.RECORDS_PATH}")
    click.echo(f"  索引   : {_paths.INDEX_PATH}")
    click.echo(f"  记录   : {len(recs)} 条 active "
               f"(决策 {by_kind.get('decision', 0)} · 猜想 {by_kind.get('belief', 0)} · 评论 {by_kind.get('comment', 0)})")
    bad = sum(1 for r in recs if (r.get("validation") or {}).get("ok") is False)
    if bad:
        click.echo(f"  ⚠ 带病  : {bad} 条(omni decisions doctor 看详情)")
    click.echo("  手记   : omni decisions record --kind decision -s \"...\" --reject \"A:理由\" --choose \"B:理由\"")


@cmd_decisions.command("record")
@click.option("--kind", "-k", type=click.Choice(_KINDS), default="decision", help="决策/猜想/评论")
@click.option("--statement", "-s", required=True, help="一句话:决策结论 / 猜想陈述 / 评论要点")
@click.option("--choose", "choose", multiple=True, help="采纳项 '选项:理由'(decision,可多次)")
@click.option("--reject", "reject", multiple=True, help="被否决项 '选项:理由'(decision,可多次)")
@click.option("--rationale", "-r", default="", help="为什么这么选(理由综述)")
@click.option("--anchor", default="", help="挂在哪份载体上 'kind:ref' 如 doc:path/to.md / feishu_msg:<id>")
@click.option("--project", default="", help="所属项目 id(如 vilo / omnicompany)")
@click.option("--track", default="", help="所属轨道 'kind:id',如 plan:DECISION-MEMORY / business:vilo-card-creation")
@click.option("--applies-to", default="", help="针对对象:具体那张卡/材料/对象的描述")
@click.option("--tag", "tags", multiple=True, help="标签(可多次)")
@click.option("--alias", "aliases", multiple=True, help="召回别名(可多次,防术语对不上漏检)")
@click.option("--confidence", type=click.Choice(["high", "medium", "low"]), default=None)
@click.option("--authority", type=click.Choice(["user_explicit", "high", "medium", "low", "derived", "unknown"]),
              default="user_explicit", help="来源权威(默认 user_explicit=本人手记拍板)")
@click.option("--channel", type=click.Choice(["claude", "codex", "feishu", "note", "demogame_doc", "manual"]),
              default="manual", help="来源渠道(手记默认 manual)")
@click.option("--risk", type=click.Choice(["low", "medium", "high"]), default=None, help="belief: 猜想错了的代价")
@click.option("--query", "evidence_query", default="", help="belief: 怎么验证这个猜想")
@click.option("--boundary", default="", help="decision: 失效边界(什么条件下需重审)")
@any_caller
def cmd_decisions_record(kind, statement, choose, reject, rationale, anchor, project, track, applies_to,
                         tags, aliases, confidence, authority, channel, risk, evidence_query, boundary) -> None:
    """手记一条决策/猜想/评论 → 落统一库。"""
    from omnicompany.packages.domains.decisions import record as record_one

    fields: dict = {"authority": authority, "origin": {"channel": channel}}
    if project:
        fields["project"] = project
    if track:
        tkind, _, tid = track.partition(":")
        fields["track"] = {"kind": (tkind.strip() or "plan"), "id": tid.strip()}
    if applies_to:
        fields["applies_to"] = applies_to
    if tags:
        fields["tags"] = list(tags)
    if aliases:
        fields["aliases"] = list(aliases)
    if confidence:
        fields["confidence"] = confidence
    if anchor:
        akind, _, aref = anchor.partition(":")
        fields["anchor"] = {"kind": (akind.strip() or "other"), "ref": aref.strip()}

    if kind == "decision":
        space = ([{"option": o, "chosen": True, "why": w} for o, w in map(_parse_opt_why, choose)]
                 + [{"option": o, "chosen": False, "why": w} for o, w in map(_parse_opt_why, reject)])
        if space:
            fields["decision_space"] = space
        if rationale:
            fields["rationale"] = rationale
        if boundary:
            fields["boundary"] = boundary
    elif kind == "belief":
        if risk:
            fields["risk_if_wrong"] = risk
        if evidence_query:
            fields["evidence_query"] = evidence_query

    rec = record_one(kind, statement, **fields)
    ok = (rec.get("validation") or {}).get("ok")
    click.echo(f"✓ 记下 {rec['id']}  [{rec['kind']}] {rec['statement'][:50]}")
    if not ok:
        for i in (rec.get("validation") or {}).get("issues") or []:
            click.echo(f"  ⚠ {i}")


@cmd_decisions.command("list")
@click.option("--kind", "-k", type=click.Choice(_KINDS), default=None, help="只看某类")
@click.option("--project", "-p", default=None, help="只看某项目")
@any_caller
def cmd_decisions_list(kind, project) -> None:
    """列决策库里的 active 记录(最新在前)。"""
    from omnicompany.packages.domains.decisions import library

    recs = [r for r in library.active_records()
            if (not kind or r.get("kind") == kind)
            and (not project or (r.get("project") or "") == project)]
    recs.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
    if not recs:
        click.echo("(决策库还空着)" if not (kind or project) else "(没有匹配的记录)")
        return
    click.echo(f"统一决策库 · {len(recs)} 条:")
    for r in recs:
        tr = r.get("track") or {}
        addr = r.get("project") or ""
        if tr.get("id"):
            addr += f"/{tr.get('kind')}:{tr.get('id')}"
        click.echo(f"  {r.get('id',''):<20} [{r.get('kind','')[:8]:<8}] {r.get('status','')[:9]:<9} "
                   f"{(addr[:26]):<26} {r.get('statement','')[:40]}")


@cmd_decisions.command("find")
@click.argument("query")
@any_caller
def cmd_decisions_find(query) -> None:
    """查库里有没有 query 指的决策/猜想(先确定性,零命中再语义兜底)。"""
    from omnicompany.packages.domains.decisions import catalog

    hits = catalog.find(query)
    if not hits:
        click.echo(f"✗ 库内无「{query}」。")
        return
    click.echo(f"✓ {len(hits)} 条命中「{query}」:")
    for r in hits:
        click.echo(f"  {r.get('id',''):<20} [{r.get('kind','')}] {r.get('statement','')[:46]}")


@cmd_decisions.command("recall")
@click.argument("situation")
@any_caller
def cmd_decisions_recall(situation) -> None:
    """回忆:面对某情境,你过去的决策倾向是什么(从决策库聚合,不是查单条)。"""
    from omnicompany.packages.domains.decisions import catalog

    res = catalog.recall(situation)
    if res.get("llm") is False:
        click.echo("(LLM 暂不可用,稍后再试)")
        return
    if not res.get("tendency"):
        click.echo(f"(没从库里归纳出跟「{situation}」相关的明确倾向)")
        return
    click.echo(f"≡ 面对「{situation}」,你过去的倾向:")
    for line in str(res["tendency"]).splitlines():
        click.echo(f"  {line}")
    sup = res.get("supporting") or []
    if sup:
        click.echo("  —— 支撑的决策:")
        for r in sup:
            tr = (r.get("track") or {}).get("id", "")
            click.echo(f"   · [{r.get('project','')}{('/' + tr) if tr else ''}] {r.get('statement','')[:52]}")


@cmd_decisions.command("show")
@click.argument("record_id")
@any_caller
def cmd_decisions_show(record_id) -> None:
    """看一条记录的全貌(含决策空间/链/挑战日志)。"""
    import json

    from omnicompany.packages.domains.decisions import library

    rec = library.get(record_id)
    if not rec:
        click.echo(f"✗ 无此记录: {record_id}")
        return
    click.echo(json.dumps(rec, ensure_ascii=False, indent=2))


@cmd_decisions.command("link")
@click.argument("src_id")
@click.argument("rel", type=click.Choice(["rests_on", "supersedes", "parent", "related"]))
@click.argument("dst_id")
@any_caller
def cmd_decisions_link(src_id, rel, dst_id) -> None:
    """给决策树加边:src --rel--> dst(如 决策 rests_on 猜想)。"""
    from omnicompany.packages.domains.decisions import catalog, library

    try:
        rec = library.add_link(src_id, rel, dst_id)
    except ValueError as e:
        click.echo(f"✗ {e}")
        return
    catalog.rebuild_index()
    click.echo(f"✓ {src_id} --{rel}--> {dst_id}")
    click.echo(f"  links: {rec.get('links')}")


@cmd_decisions.command("mark")
@click.argument("record_id")
@click.argument("status")
@any_caller
def cmd_decisions_mark(record_id, status) -> None:
    """改一条记录的生命周期状态(decision: adopted/superseded… · belief: falsified… · comment: resolved/promoted)。"""
    from omnicompany.packages.domains.decisions import catalog, library

    try:
        rec = library.set_status(record_id, status)
    except ValueError as e:
        click.echo(f"✗ {e}")
        return
    catalog.rebuild_index()
    click.echo(f"✓ {record_id} → status={rec.get('status')}")


@cmd_decisions.command("doctor")
@any_caller
def cmd_decisions_doctor() -> None:
    """列带病记录:落库校验不过(缺字段/决策没列被否决项/猜想没标风险)。"""
    from omnicompany.packages.domains.decisions import library

    recs = library.active_records()
    bad = [(r, (r.get("validation") or {}).get("issues") or [])
           for r in recs if (r.get("validation") or {}).get("ok") is False]
    if not bad:
        click.echo(f"✓ {len(recs)} 条记录全部合法。")
        return
    click.echo(f"⚠ {len(bad)}/{len(recs)} 条带病:")
    for r, issues in bad:
        click.echo(f"  {r.get('id','')}  {r.get('statement','')[:36]}")
        for i in issues[:5]:
            click.echo(f"      - {i}")


@cmd_decisions.command("extract-run")
@click.option("--batch", "-n", default=3, help="本次炼几个会话(小的先)")
@click.option("--model", "-m", default=None, help="便宜模型档(默认 omni 默认结构化模型;可传 gpt-5.3-codex 等)")
@click.option("--loop", is_flag=True, help="循环炼到 pending 清空(后台持续炼化用)")
@any_caller
def cmd_decisions_extract_run(batch, model, loop) -> None:
    """后台炼化存量对话:断点续跑/增量。每批炼 N 个未炼会话,带证据+严格归位,去重并库,标 checkpoint。"""
    from omnicompany.packages.domains.decisions import extract_run

    rounds = 0
    while True:
        res = extract_run.run_batch(limit=batch, model=model)
        rounds += 1
        for p in res["processed"]:
            tag = f"+{p['added']}" if "error" not in p else f"ERR {p['error']}"
            click.echo(f"  [{p['session'][:8]}] {tag}")
        click.echo(f"  本轮 {len(res['processed'])} 个,剩 {res['remaining']} 个未炼")
        if not loop or res["remaining"] == 0 or not res["processed"]:
            break
    click.echo(f"完成 {rounds} 轮。" + ("(pending 已清空)" if extract_run.status()["remaining"] == 0 else ""))


@cmd_decisions.command("extract-status")
@any_caller
def cmd_decisions_extract_status() -> None:
    """炼化进度:已炼/未炼会话数、剩余体量、出错数。"""
    from omnicompany.packages.domains.decisions import extract_run

    s = extract_run.status()
    click.echo(f"炼化进度: 已炼 {s['done']} 个会话 · 未炼 {s['remaining']} 个(约 {s['remaining_mb']}MB)· 出错 {s['errors']} 个")


@cmd_decisions.command("reindex")
@any_caller
def cmd_decisions_reindex() -> None:
    """把当前库投影重建 index.json(供 grep / 人读)。"""
    from omnicompany.packages.domains.decisions import _paths, catalog

    res = catalog.rebuild_index()
    click.echo(f"✓ 索引重建:{res['total']} 条 → {_paths.INDEX_PATH}")
