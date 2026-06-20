# [OMNI] origin=claude-code domain=repo_architect/pipeline.py ts=2026-04-09T00:00:00Z
# [OMNI] material_id="material:learning.repo.architect.team_topology_spec.py"
"""repo_architect pipeline — 18 节点 DAG, 覆盖 16 formats 完整拓扑。

拓扑:
  input_validator → repo_acquirer → scale_surveyor → mode_selector
      │                                                │
      │                                                ├─ [PASS] external_researcher → docs_reader → adaptive_interviewer
      │                                                └─ [FAIL] default_mode ─┘
      │
      (3 fallback 分支: research_degraded / docs_fallback / interview_defaults)
      │
      ↓
  report_designer → module_scatter → coverage_gater
      │                                   │
      │                                   ├─ retry → module_scatter (feedback loop, max 3)
      │                                   ├─ pass  → validated_drafts
      │                                   └─ fail  → HALT
      ↓
  validated_drafts → cross_validator → report_fuser → coverage_reporter → kb_ingester (EMIT)
"""

from omnicompany.protocol.anchor import (
    AnchorSpec,
    Route,
    RouteAction,
    ValidatorKind,
    ValidatorSpec,
    VerdictKind,
)
from omnicompany.protocol.team import (
    NodeKind,
    TeamEdge,
    TeamNode,
    TeamSpec,
)


def _anchor(
    node_id: str, fmt_in: str, fmt_out: str,
    *, vkind: ValidatorKind, desc: str,
    routes: dict[VerdictKind, Route],
) -> TeamNode:
    return TeamNode(
        id=node_id,
        kind=NodeKind.ANCHOR,
        anchor=AnchorSpec(
            id=f"a_{node_id}",
            name=node_id,
            format_in=fmt_in,
            format_out=fmt_out,
            validator=ValidatorSpec(
                id=f"v_{node_id}",
                kind=vkind,
                description=desc,
            ),
            routes=routes,
        ),
    )


def build_team() -> TeamSpec:
    """构建 repo-architect 管线 — 18 节点覆盖 16 formats。"""

    nodes: list[TeamNode] = [
        # ── 阶段 1 准备 (4 主节点 + 1 兜底) ─────────────────────
        _anchor(
            "input_validator", "repo-architect.input", "repo-architect.input",
            vkind=ValidatorKind.HARD,
            desc="严格校验输入 schema, url/local_path 互斥, focus 长度限制",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="repo_acquirer"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "repo_acquirer", "repo-architect.input", "repo-architect.acquired-repo",
            vkind=ValidatorKind.HARD,
            desc="git clone 或 mount local_path, 扫描文件树统计语言分布",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="repo_identity_anchor"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "repo_identity_anchor",
            "repo-architect.acquired-repo", "repo-architect.repo-identity",
            vkind=ValidatorKind.HARD,
            desc=(
                "从 pyproject.toml/package.json/Cargo.toml/go.mod/README/git remote 提取"
                "canonical_name + disambiguation_hint, 防止 LLM 按 repo_name 把同名外部项目"
                "的知识幻觉成本项目"
            ),
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="scale_surveyor"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "scale_surveyor", "repo-architect.repo-identity", "repo-architect.scaled-survey",
            vkind=ValidatorKind.HARD,
            desc="识别真实源码模块 (穿透到第二层包 via __init__.py 等 marker), 输出 code_modules",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="mode_selector"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "mode_selector", "repo-architect.scaled-survey", "repo-architect.mode-selected",
            vkind=ValidatorKind.SOFT,
            desc="向用户确认分析 mode + style + focus_areas, 失败走 default_mode 兜底",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="external_researcher"),
                VerdictKind.FAIL: Route(action=RouteAction.NEXT, target="default_mode"),
            },
        ),
        _anchor(
            "default_mode", "repo-architect.scaled-survey", "repo-architect.mode-selected",
            vkind=ValidatorKind.HARD,
            desc="mode_selector 失败兜底: 根据 complexity_score 自动推断 mode",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="external_researcher"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),

        # ── 阶段 2 信息收集 (3 主 + 3 兜底) ────────────────────
        _anchor(
            "external_researcher", "repo-architect.mode-selected", "repo-architect.research-notes",
            vkind=ValidatorKind.SOFT,
            desc="LLM 做外部调研 (社区/生态/issue), 失败走 research_degraded",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="docs_reader"),
                VerdictKind.FAIL: Route(action=RouteAction.NEXT, target="research_degraded"),
            },
        ),
        _anchor(
            "research_degraded", "repo-architect.mode-selected", "repo-architect.research-notes",
            vkind=ValidatorKind.HARD,
            desc="external_researcher 失败兜底: 输出空 shape 标记 degraded",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="docs_reader"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "docs_reader", "repo-architect.mode-selected", "repo-architect.docs-summary",
            vkind=ValidatorKind.SOFT,
            desc="定位 README/docs/ 用 LLM 提取 summary + design_decisions",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="adaptive_interviewer"),
                VerdictKind.FAIL: Route(action=RouteAction.NEXT, target="docs_fallback"),
            },
        ),
        _anchor(
            "docs_fallback", "repo-architect.mode-selected", "repo-architect.docs-summary",
            vkind=ValidatorKind.HARD,
            desc="docs_reader 失败兜底: 输出空文档 shape",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="adaptive_interviewer"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "adaptive_interviewer", "repo-architect.mode-selected", "repo-architect.user-focus-profile",
            vkind=ValidatorKind.SOFT,
            desc="UserInquiry 与用户 1-3 轮交互细化焦点, 失败走 interview_defaults",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="report_designer"),
                VerdictKind.FAIL: Route(action=RouteAction.NEXT, target="interview_defaults"),
            },
        ),
        _anchor(
            "interview_defaults", "repo-architect.mode-selected", "repo-architect.user-focus-profile",
            vkind=ValidatorKind.HARD,
            desc="adaptive_interviewer 失败兜底: 使用默认 focus_areas",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="report_designer"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),

        # ── 阶段 3 报告骨架 ────────────────────────────────────
        _anchor(
            "report_designer", "repo-architect.user-focus-profile", "repo-architect.report-skeleton",
            vkind=ValidatorKind.SOFT,
            desc="综合前序输入设计 sections + focus_modules + mermaid_hints",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="module_drafter"),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=2),
            },
        ),

        # ── 阶段 4 并行分析 (SCATTER leaf + collector) ─────────
        _anchor(
            "module_drafter", "repo-architect.report-skeleton", "repo-architect.module-draft",
            vkind=ValidatorKind.SOFT,
            desc="SCATTER leaf: 对每个 focus_module 产生单模块 draft (4 维度 + coverage)",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="draft_collector"),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=2),
            },
        ),
        _anchor(
            "draft_collector", "repo-architect.module-draft", "repo-architect.draft-set",
            vkind=ValidatorKind.HARD,
            desc="SCATTER collector: 汇聚 module-draft 为 draft-set, 计算 analysis_status",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="coverage_gater"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),

        # ── 阶段 5 质量门 + 验证 ───────────────────────────────
        _anchor(
            "coverage_gater", "repo-architect.draft-set", "repo-architect.coverage-feedback",
            vkind=ValidatorKind.HARD,
            desc="对 draft-set 打分判定 pass/retry/fail, 触发 feedback loop",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="validated_drafts_producer"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "validated_drafts_producer", "repo-architect.coverage-feedback", "repo-architect.validated-drafts",
            vkind=ValidatorKind.HARD,
            desc="过滤 pass 的 drafts (保留 complete/partial), 聚合 missing_aspects, 输出 validated-drafts",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="cross_validator"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "cross_validator", "repo-architect.validated-drafts", "repo-architect.cross-validation",
            vkind=ValidatorKind.SOFT,
            desc="检查 drafts 间接口/依赖/描述一致性, 输出 inconsistencies 列表",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="report_fuser"),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=2),
            },
        ),

        # ── 阶段 6 融合发布 ────────────────────────────────────
        _anchor(
            "report_fuser", "repo-architect.cross-validation", "repo-architect.arch-report",
            vkind=ValidatorKind.SOFT,
            desc="融合所有中间产物为最终 markdown 报告, 落盘 data/absorption/reports/",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="coverage_reporter"),
                VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=2),
            },
        ),
        _anchor(
            "coverage_reporter", "repo-architect.arch-report", "repo-architect.coverage-report",
            vkind=ValidatorKind.HARD,
            desc="生成覆盖率汇总 markdown 表格, 落 data/absorption/coverage/",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.NEXT, target="kb_ingester"),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
        _anchor(
            "kb_ingester", "repo-architect.coverage-report", "repo-architect.kb-entry",
            vkind=ValidatorKind.HARD,
            desc="转成 OmniKB KRepoArchitectEntry, 为未来相似 repo 分析提供跨仓库对齐",
            routes={
                VerdictKind.PASS: Route(action=RouteAction.EMIT),
                VerdictKind.FAIL: Route(action=RouteAction.HALT),
            },
        ),
    ]

    # ── 边声明说明 ───────────────────────────────────────────────
    # 2026-04-09 修复 in_degree 错算 bug:
    # 原先声明了 default_mode→external_researcher 等 fallback 边, 造成
    # external_researcher 等下游节点的 in_degree=2, runner 以为是 join barrier,
    # 等 mode_selector 和 default_mode 两条都到齐才执行 (但两者互斥,永远不会都到)。
    # 修复: fallback→downstream 的路由由 fallback 节点自身的 anchor.routes.PASS.target
    # 负责 (runner 的 explicit_target 机制会走这条, 不依赖 TeamEdge)。
    # 这里 edges 只声明"逻辑主干 + FAIL 分岔", 不再重复声明 fallback 合流。
    edges = [
        # 阶段 1 主链
        TeamEdge(source="input_validator", target="repo_acquirer", condition=VerdictKind.PASS),
        TeamEdge(source="repo_acquirer", target="repo_identity_anchor", condition=VerdictKind.PASS),
        TeamEdge(source="repo_identity_anchor", target="scale_surveyor", condition=VerdictKind.PASS),
        TeamEdge(source="scale_surveyor", target="mode_selector", condition=VerdictKind.PASS),
        TeamEdge(source="mode_selector", target="external_researcher", condition=VerdictKind.PASS),
        TeamEdge(source="mode_selector", target="default_mode", condition=VerdictKind.FAIL),

        # 阶段 2 信息收集 (仅 happy path + FAIL 分岔, 不声明 fallback 合流)
        TeamEdge(source="external_researcher", target="docs_reader", condition=VerdictKind.PASS),
        TeamEdge(source="external_researcher", target="research_degraded", condition=VerdictKind.FAIL),
        TeamEdge(source="docs_reader", target="adaptive_interviewer", condition=VerdictKind.PASS),
        TeamEdge(source="docs_reader", target="docs_fallback", condition=VerdictKind.FAIL),
        TeamEdge(source="adaptive_interviewer", target="report_designer", condition=VerdictKind.PASS),
        TeamEdge(source="adaptive_interviewer", target="interview_defaults", condition=VerdictKind.FAIL),

        # 阶段 3-6 主链
        TeamEdge(source="report_designer", target="module_drafter", condition=VerdictKind.PASS),
        TeamEdge(source="module_drafter", target="draft_collector", condition=VerdictKind.PASS),
        TeamEdge(source="draft_collector", target="coverage_gater", condition=VerdictKind.PASS),
        TeamEdge(source="coverage_gater", target="validated_drafts_producer", condition=VerdictKind.PASS),
        TeamEdge(source="validated_drafts_producer", target="cross_validator", condition=VerdictKind.PASS),
        TeamEdge(source="cross_validator", target="report_fuser", condition=VerdictKind.PASS),
        TeamEdge(source="report_fuser", target="coverage_reporter", condition=VerdictKind.PASS),
        TeamEdge(source="coverage_reporter", target="kb_ingester", condition=VerdictKind.PASS),
    ]

    return TeamSpec(
        id="repo-architect",
        name="repo-architect",
        description=(
            "仓库架构深度分析管线 — 输入 GitHub URL 或本地路径, 输出完整架构报告 + "
            "覆盖率证明 + OmniKB 条目。翻译自 yzddmr6/repo-analyzer SOTA skill, "
            "作为 absorption 循环的核心深度阅读工具。"
        ),
        entry="input_validator",
        nodes=nodes,
        edges=edges,
        tags=["domain.repo_architect", "absorption", "deep_read"],
    )
