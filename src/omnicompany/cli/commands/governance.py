# [OMNI] origin=claude-code ts=2026-06-12 type=cli
# [OMNI] material_id="material:cli.governance.steward_and_history_verbs.py"
"""omni governance — 治理部门 CLI (计划治理 + 工作历史整理, 便宜模型干活)。

  omni governance plans-run       # deepseek 全量分类计划→项目 + 中文标题 + 格式检查
  omni governance plans-status    # 读覆盖表摘要(不调模型)
  omni governance history-run     # 抽 claude/codex 用户消息 → 重复需求/重复指正
  omni governance history-report  # 打印最近一次工作历史报告
  omni governance actions-check   # PROJECT_INDEX quick_actions 的 skill 存在性体检(确定性)
  omni governance docs-refs       # 文档引用完整性(断链/失效行锚, 确定性, 不调模型)
  omni governance docs-timeliness # 规范/计划/报告时效性(过期/被取代/冲突, 性价比模型为主)
  omni governance docs-report     # 打印最近一次文档治理摘要
  omni governance commit-run      # 性价比模型严格分批 git 提交(默认 dry-run, --apply 真提交)
  omni governance decisions-run   # 标记 llm_input 的札记 → 结构化决策(进总控 ctx)
  omni governance catalog         # 列出所有治理管线 + 档期 + 上次跑(唯一发现面)
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import click

from omnicompany.runtime.llm.structured import DEFAULT_STRUCTURED_MODEL, DEFAULT_STRUCTURED_MODEL_ENV

from .._access import any_caller, external_or_controller


@click.group("governance")
def cmd_governance() -> None:
    """治理部门: 计划治理(plan_steward) / 工作历史整理(work_history)。"""


@cmd_governance.command("plans-run")
@external_or_controller
@click.option("--model", default=None, show_default=f"{DEFAULT_STRUCTURED_MODEL_ENV} or {DEFAULT_STRUCTURED_MODEL}")
@click.option("--limit", type=int, default=None, help="只处理前 N 个(冒烟用)")
@click.option("--only-missing", is_flag=True, help="只补登记覆盖表里还没有的计划(增量)")
@click.option("--workers", type=int, default=4, show_default=True)
@click.option("--dry-run", is_flag=True, help="只分类不落盘")
def cmd_plans_run(model: str | None, limit: int | None, only_missing: bool, workers: int, dry_run: bool) -> None:
    """全量计划治理: 归属分类 + 汉化 + 格式检查 → data/registry/plan_governance.json。"""
    from omnicompany.packages.services._governance.plan_steward import run_governance
    summary = run_governance(model=model, limit=limit, only_missing=only_missing,
                             workers=workers, dry_run=dry_run, echo=click.echo)
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@cmd_governance.command("plans-status")
@any_caller
def cmd_plans_status() -> None:
    """覆盖表摘要(不调模型)。"""
    from omnicompany.packages.services._governance.plan_steward import governance_summary
    click.echo(json.dumps(governance_summary(), ensure_ascii=False, indent=2))


@cmd_governance.command("plans-benchmark")
@any_caller
@click.option("--apply", "apply_", is_flag=True, help="把金标签持久化进覆盖表(立即生效)")
def cmd_plans_benchmark(apply_: bool) -> None:
    """便宜模型 vs 金标签一致率(金标签=主力模型/人亲读内容后的判定, benchmark.json)。"""
    from omnicompany.packages.services._governance.plan_steward.steward import benchmark_report
    click.echo(json.dumps(benchmark_report(apply=apply_), ensure_ascii=False, indent=2))


@cmd_governance.command("history-run")
@external_or_controller
@click.option("--days", type=int, default=45, show_default=True)
@click.option("--source", type=click.Choice(["all", "claude", "codex"]), default="all", show_default=True)
@click.option("--model", default=None, show_default=f"{DEFAULT_STRUCTURED_MODEL_ENV} or {DEFAULT_STRUCTURED_MODEL}")
@click.option("--workers", type=int, default=4, show_default=True)
@click.option("--limit-chunks", type=int, default=None, help="只跑前 N 块(冒烟用)")
@click.option("--from-signals", is_flag=True, help="从上次落盘的信号续跑(跳过最贵的 map 段)")
def cmd_history_run(days: int, source: str, model: str | None, workers: int,
                    limit_chunks: int | None, from_signals: bool) -> None:
    """工作历史整理: 用户消息 → 重复需求 / 重复指正 → data/governance/work_history/。"""
    from omnicompany.packages.services._governance.work_history import run_mining
    summary = run_mining(days=days, source=source, model=model, workers=workers,
                         limit_chunks=limit_chunks, from_signals=from_signals, echo=click.echo)
    click.echo(json.dumps(summary, ensure_ascii=False, indent=2))


@cmd_governance.command("history-assign")
@external_or_controller
@click.option("--model", default=None, show_default="OMNI_STRUCTURED_ASSIGN_MODEL or glm-5.1")
def cmd_history_assign(model: str | None) -> None:
    """把最近一次 findings 的重复需求/指正分配到注册项目(项目详情页「历史证据」消费)。"""
    from omnicompany.packages.services._governance.work_history.miner import assign_projects
    click.echo(json.dumps(assign_projects(model=model, echo=click.echo), ensure_ascii=False, indent=2))


@cmd_governance.command("history-report")
@any_caller
def cmd_history_report() -> None:
    """打印最近一次工作历史整理报告。"""
    from omnicompany.packages.services._governance.work_history.miner import out_dir
    ptr = out_dir() / "latest.json"
    if not ptr.is_file():
        click.echo("还没跑过 history-run。")
        raise SystemExit(1)
    meta = json.loads(ptr.read_text(encoding="utf-8"))
    click.echo((out_dir() / meta["report"]).read_text(encoding="utf-8"))


@cmd_governance.command("actions-check")
@any_caller
@click.option("--json-output", is_flag=True)
def cmd_actions_check(json_output: bool) -> None:
    """各项目 PROJECT_INDEX 的 quick_actions 体检: 绑定的 skill 是否真实存在(确定性, 不调模型)。"""
    from omnicompany.core.config import omni_workspace_root
    from omnicompany.core.projects_registry import list_projects, parse_index_file

    skill_dirs = [
        Path.home() / ".claude" / "skills",
        omni_workspace_root() / ".claude" / "skills",
    ]
    known = {d.name for sd in skill_dirs if sd.is_dir() for d in sd.iterdir() if d.is_dir()}

    rows = []
    for p in list_projects():
        if not p.get("index_path"):
            continue
        parsed = parse_index_file(p["index_path"])
        for a in ((parsed.get("data") or {}).get("quick_actions") or []) if parsed.get("ok") else []:
            skill = a.get("skill")
            rows.append({
                "project": p["id"],
                "label": a.get("label"),
                "skill": skill,
                "skill_exists": (skill in known) if skill else None,
            })
    if json_output:
        click.echo(json.dumps({"known_skills": sorted(known), "actions": rows},
                              ensure_ascii=False, indent=2))
        return
    bad = [r for r in rows if r["skill"] and not r["skill_exists"]]
    none_ = [r for r in rows if not r["skill"]]
    click.echo(f"quick_actions 共 {len(rows)} 条; 绑定不存在 skill 的 {len(bad)} 条; 未绑定 skill 的 {len(none_)} 条")
    for r in bad:
        click.echo(f"  [虚构skill] {r['project']}: {r['label']} → /{r['skill']}")
    for r in none_:
        click.echo(f"  [待建技能] {r['project']}: {r['label']}")


@cmd_governance.command("docs-refs")
@any_caller
@click.option("--json-output", is_flag=True)
def cmd_docs_refs(json_output: bool) -> None:
    """文档引用完整性体检(确定性, 不调模型): 扫规范/计划/报告里指向已不存在文件的链接/行锚。"""
    from omnicompany.packages.services._governance.doc_steward import run_reference_audit
    res = run_reference_audit(write=True)
    if json_output:
        click.echo(json.dumps(res, ensure_ascii=False, indent=2))
        return
    click.echo(f"扫描 {res['scanned_docs']} 篇; 断链 {res['counts']['broken_ref']} / 失效行锚 {res['counts']['broken_anchor']}")
    for f in res["findings"][:40]:
        click.echo(f"  [{f['category']}] {f['doc']} → {f['target']}")
    if len(res["findings"]) > 40:
        click.echo(f"  … 还有 {len(res['findings']) - 40} 条, 见 {res.get('_written')}")


@cmd_governance.command("docs-timeliness")
@any_caller
@click.option("--model", default=None, help="覆盖默认性价比模型")
@click.option("--kind", default="standard", type=click.Choice(["standard", "plan", "report"]))
@click.option("--limit", type=int, default=None)
@click.option("--workers", type=int, default=4)
def cmd_docs_timeliness(model: str | None, kind: str, limit: int | None, workers: int) -> None:
    """文档时效性语义治理(性价比模型为主): 判规范是否过期/被取代/冲突/另立权威。"""
    from omnicompany.packages.services._governance.doc_steward import run_timeliness
    res = run_timeliness(kinds=(kind,), model=model, limit=limit, workers=workers, echo=click.echo)
    click.echo(f"扫描 {res['scanned_docs']} 篇(失败 {res['failed_docs']}); 时效性 findings {len(res['findings'])} 条")
    for f in res["findings"][:40]:
        click.echo(f"  [{f['category']}] {f['doc']}: {f['detail']}")
    click.echo(f"产物: {res.get('_written')}")


@cmd_governance.command("docs-report")
@any_caller
def cmd_docs_report() -> None:
    """打印最近一次文档治理摘要(引用审计 + 时效性)。"""
    from omnicompany.packages.services._governance.doc_steward import latest_findings
    data = latest_findings()
    ref = data.get("reference_audit")
    tl = data.get("timeliness")
    if ref:
        click.echo(f"引用审计({ref['generated_at']}): {ref['scanned_docs']} 篇, 断链 {len(ref['findings'])} 条")
    else:
        click.echo("还没跑过 docs-refs。")
    if tl:
        click.echo(f"时效性({tl['generated_at']}, 模型 {tl['model']}): {tl['scanned_docs']} 篇, findings {len(tl['findings'])} 条")
    else:
        click.echo("还没跑过 docs-timeliness。")


@cmd_governance.command("commit-run")
@external_or_controller
@click.option("--model", default=None, help="覆盖默认性价比模型")
@click.option("--apply", "apply_", is_flag=True, help="真提交(默认 dry-run 只出批次计划)")
@click.option("--workers", type=int, default=4)
def cmd_commit_run(model: str | None, apply_: bool, workers: int) -> None:
    """性价比模型严格分批 git 提交: 低重复明文必读、禁盲目全量、逐批显式 add+commit。

    默认 dry-run 只出批次计划供抽查; 加 --apply 才真提交(pre-commit 卫士逐批兜底)。
    """
    from omnicompany.packages.services._governance.commit_steward import run_commit
    res = run_commit(model=model, dry_run=not apply_, workers=workers, echo=click.echo)
    if res.get("changes") == 0:
        click.echo(res.get("message", "工作区干净"))
        return
    click.echo(f"改动 {res['changes']} 文件 → {res['batches']} 批"
               f"(map 失败 {res['map_failed']}); {'真提交' if apply_ else 'DRY-RUN 计划'}")
    for b in res["plan"]:
        click.echo(f"\n■ {b['subject']}  ({len(b['files'])} 文件)")
        if b.get("body"):
            click.echo("  " + b["body"].replace("\n", "\n  "))
    if res.get("uncommitted_left"):
        click.echo(f"\n留工作区未提交(读不到/判不准) {len(res['uncommitted_left'])} 个:")
        for f in res["uncommitted_left"][:20]:
            click.echo(f"  - {f}")
    if apply_:
        ok = sum(1 for a in res["applied"] if a.get("committed"))
        click.echo(f"\n已提交 {ok}/{len(res['applied'])} 批; 计划见 {res.get('_written')}")
    else:
        click.echo(f"\n计划落盘: {res.get('_written')}  (确认无误后加 --apply 真提交)")


@cmd_governance.command("decisions-run")
@external_or_controller
@click.option("--model", default=None, help="覆盖默认性价比模型(默认 qwen3.6-plus)")
@click.option("--reextract", is_flag=True, help="重提全部(默认只提新增/失败的 llm_input 札记)")
def cmd_decisions_run(model: str | None, reextract: bool) -> None:
    """决策提取: 标记 llm_input 的札记 → 结构化决策 → data/boss_sight/authored_decisions.json。

    手动 = 直接跑此 verb; 定期 = scheduler 的 gov-decisions-daily 每日调同函数。
    产物经 cockpit_workflow 的 ctx_summary.decisions 段进总控首轮上下文。
    """
    from omnicompany.dashboard.boss_sight.authored.extract import extract_decisions
    kw: dict = {"reextract": reextract}
    if model:
        kw["model"] = model
    res = extract_decisions(**kw)
    click.echo(json.dumps(res, ensure_ascii=False, indent=2))


@cmd_governance.command("resume-run")
@external_or_controller
@click.option("--model", default=None, show_default=f"{DEFAULT_STRUCTURED_MODEL_ENV} or {DEFAULT_STRUCTURED_MODEL}")
@click.option("--sources", default="scm,git", show_default=True, help="逗号分隔: scm,git,internal_tracker,chat_platform")
@click.option("--scm-limit", type=int, default=None, help="scm changelist 上限(冒烟用)")
@click.option("--git-limit-per-repo", type=int, default=None, help="每个 git 仓 commit 上限")
@click.option("--scm-since", default=None, help="scm 起始日期, 形如 2026/01/01")
@click.option("--stage-tag", default="full", show_default=True, help="staging 文件标签")
@click.option("--workers", type=int, default=4, show_default=True)
@click.option("--dry-run", is_flag=True, help="不落 findings/run 文件")
def cmd_resume_run(model: str | None, sources: str, scm_limit: int | None,
                   git_limit_per_repo: int | None, scm_since: str | None,
                   stage_tag: str, workers: int, dry_run: bool) -> None:
    """简历资料库: 多源采集 → 归属闸 → 泛化摘要 → 能力矩阵+成就时间线。"""
    from omnicompany.packages.services._governance.resume_steward import run_resume
    srcs = tuple(s.strip() for s in sources.split(",") if s.strip())
    res = run_resume(sources=srcs, model=model, scm_limit=scm_limit,
                     git_limit_per_repo=git_limit_per_repo, scm_since=scm_since,
                     stage_tag=stage_tag, workers=workers, dry_run=dry_run, echo=click.echo)
    click.echo(json.dumps(res, ensure_ascii=False, indent=2))


@cmd_governance.command("resume-gold")
@external_or_controller
@click.option("--source-tag", default="smoke", show_default=True, help="benchmark 样本的 staging 标签")
@click.option("--model", default=None, show_default="OMNI_RESUME_BASELINE_MODEL or claude-sonnet-4-6")
@click.option("--workers", type=int, default=3, show_default=True)
def cmd_resume_gold(source_tag: str, model: str | None, workers: int) -> None:
    """基准模型亲读样本产金标(benchmark.json), 权威高于便宜模型。"""
    from omnicompany.packages.services._governance.resume_steward import produce_gold
    res = produce_gold(source_tag=source_tag, model=model, workers=workers, echo=click.echo)
    click.echo(json.dumps(res, ensure_ascii=False, indent=2))


@cmd_governance.command("resume-benchmark")
@any_caller
@click.option("--source-tag", default="smoke", show_default=True)
@click.option("--cheap-model", default=None, show_default=f"{DEFAULT_STRUCTURED_MODEL_ENV} or {DEFAULT_STRUCTURED_MODEL}")
@click.option("--judge-model", default=None, show_default="OMNI_RESUME_BASELINE_MODEL or claude-sonnet-4-6")
@click.option("--workers", type=int, default=3, show_default=True)
def cmd_resume_benchmark(source_tag: str, cheap_model: str | None,
                         judge_model: str | None, workers: int) -> None:
    """便宜模型 vs 金标一致率(attribution 精确 + 能力重叠 + 摘要基准裁判语义等价)。"""
    from omnicompany.packages.services._governance.resume_steward import benchmark_report
    res = benchmark_report(source_tag=source_tag, cheap_model=cheap_model,
                           judge_model=judge_model, workers=workers, echo=click.echo)
    click.echo(json.dumps(res, ensure_ascii=False, indent=2))


@cmd_governance.command("resume-reduce")
@external_or_controller
@click.option("--stage-tag", default="all", show_default=True, help="从该 staging 的 MAP 缓存重算")
def cmd_resume_reduce(stage_tag: str) -> None:
    """从 MAP 缓存重算 REDUCE → findings(迭代聚合/合并逻辑而不重跑昂贵的 MAP)。"""
    from omnicompany.packages.services._governance.resume_steward import rebuild_findings
    res = rebuild_findings(stage_tag=stage_tag, echo=click.echo)
    click.echo(json.dumps(res, ensure_ascii=False, indent=2))


@cmd_governance.command("resume-report")
@any_caller
def cmd_resume_report() -> None:
    """打印最近一次简历资料库的能力矩阵 + 成就时间线摘要。"""
    from omnicompany.packages.services._governance.resume_steward import latest
    data = latest()
    if not data:
        click.echo("还没跑过 resume-run。")
        raise SystemExit(1)
    click.echo(f"能力 {len(data.get('capabilities') or [])} 项, 成就 {len(data.get('accomplishments') or [])} 条"
               f"(本人 {data.get('mine')}/{data.get('units')}, 待复核 {data.get('by_attribution', {}).get('review_needed', 0)})")
    for c in (data.get("capabilities") or [])[:20]:
        click.echo(f"  [能力] {c.get('name')} ×{c.get('evidence_count')} {c.get('sources')}")
    for a in (data.get("accomplishments") or [])[:20]:
        click.echo(f"  [成就] {a.get('title')} ({a.get('timespan')}) — {a.get('summary')}")


@cmd_governance.command("job-run")
@any_caller
@click.option("--model", default=None, show_default="qwen3.6-plus")
@click.option("--workers", type=int, default=12, show_default=True)
def cmd_job_run(model: str | None, workers: int) -> None:
    """求职 Phase 0: 大厂官网公开 API 抓岗 → 按画像匹配排序 → 招聘策划可投清单。"""
    from omnicompany.packages.services._governance.job_steward import run_discovery
    res = run_discovery(model=model, workers=workers, echo=click.echo)
    click.echo(json.dumps(res, ensure_ascii=False, indent=2))


# 治理管线目录: 唯一可枚举面 (agent/总控一条命令即知有哪些治理管线、该不该跑)
_GOVERNANCE_CATALOG = [
    {"verb": "plans-run", "what": "计划→项目归属 + 中文标题 + 格式检查", "cadence": "每日(--only-missing)", "kind": "语义"},
    {"verb": "history-run", "what": "对话里重复需求/指正提取", "cadence": "每周", "kind": "语义"},
    {"verb": "docs-refs", "what": "文档引用完整性(断链/失效行锚)", "cadence": "每日", "kind": "确定性"},
    {"verb": "docs-timeliness", "what": "规范/计划/报告时效性(过期/被取代/冲突)", "cadence": "每周", "kind": "语义"},
    {"verb": "commit-run", "what": "性价比模型严格分批 git 提交", "cadence": "定时/大改后", "kind": "语义+确定性"},
    {"verb": "decisions-run", "what": "标记 llm_input 的札记 → 结构化决策(进总控 ctx)", "cadence": "每日", "kind": "语义"},
    {"verb": "actions-check", "what": "PROJECT_INDEX quick_actions 的 skill 存在性体检", "cadence": "按需", "kind": "确定性"},
    {"verb": "resume-run", "what": "多源(scm/git/internal_tracker/chat_platform)采集 → 归属+泛化摘要 → 简历资料库", "cadence": "按需", "kind": "语义"},
    {"verb": "job-run", "what": "大厂官网公开API抓岗 → 按画像匹配 → 招聘策划可投清单(Phase 0)", "cadence": "按需/每日", "kind": "语义"},
]


@cmd_governance.command("catalog")
@any_caller
@click.option("--json-output", is_flag=True)
def cmd_catalog(json_output: bool) -> None:
    """列出所有治理管线 + 档期 + 上次跑时间(agent/总控发现可用治理操作的唯一面)。"""
    import json as _json
    from pathlib import Path

    from omnicompany.core.config import omni_workspace_root
    gov = omni_workspace_root() / "data" / "governance"
    last_runs = {
        "plans-run": gov / "plan_steward",
        "history-run": gov / "work_history" / "latest.json",
        "docs-refs": gov / "doc_steward" / "reference_audit.json",
        "docs-timeliness": gov / "doc_steward" / "timeliness-latest.json",
        "commit-run": gov / "commit_steward" / "commit_last.json",
        "decisions-run": gov.parent / "boss_sight" / "authored_decisions.json",
        "resume-run": gov / "resume_steward" / "latest.json",
    }
    rows = []
    for item in _GOVERNANCE_CATALOG:
        ptr = last_runs.get(item["verb"])
        last = ""
        if isinstance(ptr, Path) and ptr.exists():
            try:
                last = datetime.fromtimestamp(ptr.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                last = "?"
        rows.append({**item, "last_run": last or "未跑过"})
    if json_output:
        click.echo(_json.dumps(rows, ensure_ascii=False, indent=2))
        return
    click.echo("治理管线目录 (omni governance <verb>):")
    for r in rows:
        click.echo(f"  {r['verb']:<16} [{r['kind']:<8}] {r['what']}")
        click.echo(f"  {'':<16} 档期 {r['cadence']} · 上次 {r['last_run']}")


@cmd_governance.command("cron-tick")
@external_or_controller
@click.option("--dry-run", is_flag=True, help="只列到期任务不执行")
@click.option("--ensure", is_flag=True, help="先补建标准治理 cron 任务再跑")
def cmd_cron_tick(dry_run: bool, ensure: bool) -> None:
    """跑一遍治理定时任务(由 OS cron/sentinel 每隔几分钟调一次, 分发到期的治理管线)。"""
    from omnicompany.packages.services._governance.scheduler import ensure_governance_tasks, tick
    if ensure:
        created = ensure_governance_tasks()
        if created:
            click.echo(f"补建治理 cron 任务: {', '.join(created)}")
    res = tick(dry_run=dry_run)
    if not res["ran"]:
        click.echo("无到期治理任务。")
        return
    click.echo(f"到期任务 {res['due_count']} 个 ({'DRY-RUN' if dry_run else '已执行'}):")
    for r in res["ran"]:
        mark = "would-run" if r.get("would_run") else ("ok" if r.get("ran") else r.get("skipped") or r.get("error") or "?")
        click.echo(f"  {r['name']}: {r['command']}  → {mark}")


@cmd_governance.command("cron-list")
@any_caller
def cmd_cron_list() -> None:
    """列出治理定时任务及其下次是否到期。"""
    from omnicompany.packages.services._governance.scheduler import is_due, load_tasks
    tasks = load_tasks()
    if not tasks:
        click.echo("还没有 cron 任务(omni governance cron-tick --ensure 可补建标准治理任务)。")
        return
    for t in tasks:
        due = "★到期" if is_due(t) else "已跑过"
        click.echo(f"  {t.get('name'):<26} {t.get('schedule','?'):<10} {due}  上次 {t.get('last_run_at') or '从未'}")
        click.echo(f"  {'':<26} {t.get('command') or t.get('description','')}")
