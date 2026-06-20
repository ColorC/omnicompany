# [OMNI] origin=claude-code ts=2026-04-12T00:00:00Z
"""
tests/test_pipeline_topology.py — Pipeline 拓扑静态检查系统单元测试

覆盖检查注册表模式、Finding 语义化结果、以及各检查项的核心逻辑：
  1-3:  Finding / CheckContext / run_pipeline_checks 基础机制
  4-7:  现有检查：no_entry / isolated / format_break / soft_hard_pairing
  8-12: granted_tag_chain 检查（L2 边级语义约束验证）
  13-14: 检查开关（enabled / disabled 参数）
  15:   check_pipeline_topology 向后兼容接口
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock

from omnicompany.packages.services._diagnosis.doctor.pipeline_topology import (
    Finding,
    PIPELINE_CHECKS,
    PipelineCheckSpec,
    run_pipeline_checks,
    check_pipeline_topology,
    TopologyIssue,
    _build_context,
)
from omnicompany.protocol.format import Format, FormatRegistry
from omnicompany.protocol.pipeline import (
    PipelineSpec,
    PipelineNode,
    PipelineEdge,
    NodeKind,
    NodeMaturity,
)
from omnicompany.protocol.anchor import (
    AnchorSpec,
    Route,
    RouteAction,
    TransformerSpec,
    TransformMethod,
    ValidatorKind,
    ValidatorSpec,
    VerdictKind,
)


# ── 管线构建助手 ──────────────────────────────────────────────────────────────

def _rule_node(nid: str, fmt_in: str = "a", fmt_out: str = "b") -> PipelineNode:
    return PipelineNode(
        id=nid,
        kind=NodeKind.TRANSFORMER,
        transformer=TransformerSpec(
            id=f"{nid}-t",
            name=nid.capitalize(),
            from_format=fmt_in,
            to_format=fmt_out,
            method=TransformMethod.RULE,
            description=f"{nid} rule transformer",
        ),
        maturity=NodeMaturity.MATURE,
    )


def _llm_node(nid: str, fmt_in: str = "a", fmt_out: str = "b") -> PipelineNode:
    return PipelineNode(
        id=nid,
        kind=NodeKind.TRANSFORMER,
        transformer=TransformerSpec(
            id=f"{nid}-t",
            name=nid.capitalize(),
            from_format=fmt_in,
            to_format=fmt_out,
            method=TransformMethod.LLM,
            description=f"{nid} llm transformer",
        ),
        maturity=NodeMaturity.GROWING,
    )


def _anchor_node(nid: str, fmt_in: Any = "a", fmt_out: str = "b") -> PipelineNode:
    return PipelineNode(
        id=nid,
        kind=NodeKind.ANCHOR,
        anchor=AnchorSpec(
            id=f"{nid}-a",
            name=nid.capitalize(),
            format_in=fmt_in,
            format_out=fmt_out,
            validator=ValidatorSpec(
                id=f"{nid}-v",
                kind=ValidatorKind.HARD,
                description=f"{nid} hard validator",
            ),
            routes={VerdictKind.PASS: Route(action=RouteAction.NEXT)},
        ),
        maturity=NodeMaturity.MATURE,
    )


def _edge(src: str, tgt: str, *, feedback: bool = False) -> PipelineEdge:
    return PipelineEdge(source=src, target=tgt, feedback=feedback)


def _spec(nodes: list[PipelineNode], edges: list[PipelineEdge], *, entry: str | None = None) -> PipelineSpec:
    return PipelineSpec(
        id="test.pipeline",
        name="Test Pipeline",
        description="Test pipeline for unit tests",
        nodes=nodes,
        edges=edges,
        entry=entry or (nodes[0].id if nodes else "_none_"),
    )


# ── FormatRegistry 助手 ────────────────────────────────────────────────────────

def _fmt(fid: str, *, tags: list[str] | None = None, required_tags: list[str] | None = None) -> Format:
    return Format(
        id=fid,
        name=fid.replace(".", "-").capitalize(),
        description=f"Test format {fid}",
        tags=tags or [],
        required_tags=required_tags or [],
    )


def _make_reg(*formats: Format) -> FormatRegistry:
    reg = FormatRegistry()
    for f in formats:
        reg.register(f)
    return reg


# ═══════════════════════════════════════════════════════════════════════════
# 1-3: Finding / CheckContext / run_pipeline_checks 基础机制
# ═══════════════════════════════════════════════════════════════════════════

class TestFindingBasics:

    def test_finding_severity_property(self):
        """场景1: Finding.severity 根据 level 返回正确的向后兼容值"""
        assert Finding("x", "blocking",  "loc", "obs").severity == "CRITICAL"
        assert Finding("x", "degrading", "loc", "obs").severity == "HIGH"
        assert Finding("x", "advisory",  "loc", "obs").severity == "MEDIUM"
        assert Finding("x", "info",      "loc", "obs").severity == "INFO"
        assert Finding("x", "unknown",   "loc", "obs").severity == "INFO"  # 未知级别降级

    def test_finding_str(self):
        """场景1: Finding.__str__ 输出格式"""
        f = Finding("no_entry", "blocking", "pipeline", "没有 entry 节点")
        assert "CRITICAL" in str(f)
        assert "no_entry" in str(f)

    def test_check_registry_has_all_expected_ids(self):
        """场景2: 全局检查注册表包含所有预期的检查 ID"""
        ids = {c.id for c in PIPELINE_CHECKS}
        expected = {
            "no_entry", "isolated", "dead_end", "format_break",
            "cycle", "composite_missing", "soft_hard_pairing", "granted_tag_chain",
            "maturity_consistency", "purpose_quality", "duplicate_edge",
        }
        assert expected == ids

    def test_run_pipeline_checks_missing_entry(self):
        """场景3: entry 不在节点列表中 → no_entry blocking Finding"""
        n1 = _rule_node("existing", "a", "b")
        spec = PipelineSpec(
            id="test.empty",
            name="Test",
            description="Test",
            nodes=[n1],
            edges=[],
            entry="nonexistent_entry",
        )
        findings = run_pipeline_checks(spec)
        assert any(f.check_id == "no_entry" and f.level == "blocking" for f in findings)


# ═══════════════════════════════════════════════════════════════════════════
# 4-7: 现有检查项的核心逻辑
# ═══════════════════════════════════════════════════════════════════════════

class TestExistingChecks:

    def test_isolated_node_detected(self):
        """场景4: 孤立节点（无入边且不是 entry）被检测为 degrading"""
        n1 = _rule_node("entry", "a", "b")
        n2 = _rule_node("orphan", "x", "y")  # 不在任何边中
        spec = _spec([n1, n2], [])  # 无边，orphan 不可达
        findings = run_pipeline_checks(spec)
        isolated = [f for f in findings if f.check_id == "isolated"]
        assert any("orphan" in f.location for f in isolated)

    def test_format_break_detected(self):
        """场景5: 直接边 format_out ≠ format_in → blocking"""
        n1 = _rule_node("a_node", "x", "out-a")
        n2 = _rule_node("b_node", "in-b", "y")   # in-b ≠ out-a
        spec = _spec([n1, n2], [_edge("a_node", "b_node")])
        findings = run_pipeline_checks(spec)
        breaks = [f for f in findings if f.check_id == "format_break"]
        assert len(breaks) == 1
        assert breaks[0].level == "blocking"
        assert "a_node→b_node" in breaks[0].location

    def test_format_break_not_detected_when_matching(self):
        """场景5: format_out = format_in → 无断裂"""
        n1 = _rule_node("a_node", "x", "shared")
        n2 = _rule_node("b_node", "shared", "y")
        spec = _spec([n1, n2], [_edge("a_node", "b_node")])
        findings = run_pipeline_checks(spec)
        assert not any(f.check_id == "format_break" for f in findings)

    def test_format_break_not_detected_when_target_accepts_multi_input(self):
        """Anchor format_in can be a list; a matching source format is valid."""
        n1 = _anchor_node("a_node", "x", "shared")
        n2 = _anchor_node("b_node", ["shared", "request"], "y")
        spec = _spec([n1, n2], [_edge("a_node", "b_node")])
        findings = run_pipeline_checks(spec)
        assert not any(f.check_id == "format_break" for f in findings)

    def test_format_break_not_detected_when_target_uses_compact_multi_input_string(self):
        """Generated specs sometimes use 'fmt.a + fmt.b' to mean alternatives."""
        n1 = _rule_node("a_node", "x", "shared")
        n2 = _rule_node("b_node", "shared + request", "y")
        spec = _spec([n1, n2], [_edge("a_node", "b_node")])
        findings = run_pipeline_checks(spec)
        assert not any(f.check_id == "format_break" for f in findings)

    def test_soft_hard_pairing_llm_without_validator(self):
        """场景6: LLM 节点无下游 RULE/ANCHOR → degrading"""
        llm = _llm_node("llm_gen", "a", "b")
        sink = _llm_node("llm_sink", "b", "c")  # 也是 LLM，不算验证
        spec = _spec([llm, sink], [_edge("llm_gen", "llm_sink")])
        findings = run_pipeline_checks(spec)
        pairing = [f for f in findings if f.check_id == "soft_hard_pairing"]
        assert any("llm_gen" in f.location for f in pairing)

    def test_soft_hard_pairing_ok_with_rule_downstream(self):
        """场景7: LLM 节点 → RULE 节点 → 无 soft_hard_pairing 问题"""
        llm = _llm_node("llm_gen", "a", "b")
        validator = _rule_node("validator", "b", "c")
        spec = _spec([llm, validator], [_edge("llm_gen", "validator")])
        findings = run_pipeline_checks(spec)
        assert not any(f.check_id == "soft_hard_pairing" for f in findings)


# ═══════════════════════════════════════════════════════════════════════════
# 8-12: granted_tag_chain 检查
# ═══════════════════════════════════════════════════════════════════════════

class TestGrantedTagChain:

    def test_no_registry_skips_check(self):
        """场景8: 无 format_registry → granted_tag_chain 跳过（无 Finding）"""
        n1 = _rule_node("n1", "fmt.a", "fmt.b")
        n2 = _rule_node("n2", "fmt.b", "fmt.c")
        spec = _spec([n1, n2], [_edge("n1", "n2")])
        findings = run_pipeline_checks(spec)  # no format_registry
        assert not any(f.check_id == "granted_tag_chain" for f in findings)

    def test_required_tags_covered_by_upstream(self):
        """场景9: 上游 format_out.tags 覆盖了下游 format_in.required_tags → 无 Finding"""
        reg = _make_reg(
            _fmt("fmt.source", tags=["domain.gameplay_system", "source.scm"]),
            _fmt("fmt.target", required_tags=["domain.gameplay_system"]),
        )
        n1 = _rule_node("n1", "fmt.source", "fmt.source")
        n2 = _rule_node("n2", "fmt.target", "fmt.out")
        reg.register(_fmt("fmt.out"))
        spec = _spec([n1, n2], [_edge("n1", "n2")])
        findings = run_pipeline_checks(spec, format_registry=reg)
        assert not any(f.check_id == "granted_tag_chain" for f in findings)

    def test_required_tags_not_covered(self):
        """场景10: 上游 format_out 无对应 tag → degrading Finding"""
        reg = _make_reg(
            _fmt("fmt.source", tags=["domain.other"]),  # 没有 source.scm
            _fmt("fmt.target", required_tags=["source.scm"]),
        )
        n1 = _rule_node("n1", "fmt.source", "fmt.source")
        n2 = _rule_node("n2", "fmt.target", "fmt.out")
        reg.register(_fmt("fmt.out"))
        spec = _spec([n1, n2], [_edge("n1", "n2")])
        findings = run_pipeline_checks(spec, format_registry=reg)
        tag_findings = [f for f in findings if f.check_id == "granted_tag_chain"]
        assert len(tag_findings) == 1
        assert tag_findings[0].level == "degrading"
        assert "source.scm" in tag_findings[0].observation
        assert "n2" in tag_findings[0].location

    def test_required_tags_covered_transitively(self):
        """场景11: 标签由两跳以上的祖先节点提供 → BFS 可达，无 Finding"""
        reg = _make_reg(
            _fmt("fmt.root", tags=["source.verified"]),
            _fmt("fmt.mid"),
            _fmt("fmt.leaf", required_tags=["source.verified"]),
        )
        n1 = _rule_node("root", "fmt.root", "fmt.root")
        n2 = _rule_node("mid",  "fmt.mid",  "fmt.mid")
        n3 = _rule_node("leaf", "fmt.leaf", "fmt.out")
        reg.register(_fmt("fmt.out"))
        spec = _spec([n1, n2, n3], [_edge("root", "mid"), _edge("mid", "leaf")])
        findings = run_pipeline_checks(spec, format_registry=reg)
        assert not any(f.check_id == "granted_tag_chain" for f in findings)

    def test_no_required_tags_skips_node(self):
        """场景12: format_in 无 required_tags → 该节点跳过"""
        reg = _make_reg(
            _fmt("fmt.source"),  # 无 tags
            _fmt("fmt.target"),  # 无 required_tags
        )
        n1 = _rule_node("n1", "fmt.source", "fmt.source")
        n2 = _rule_node("n2", "fmt.target", "fmt.out")
        reg.register(_fmt("fmt.out"))
        spec = _spec([n1, n2], [_edge("n1", "n2")])
        findings = run_pipeline_checks(spec, format_registry=reg)
        assert not any(f.check_id == "granted_tag_chain" for f in findings)

    def test_partial_tags_missing_reported(self):
        """场景12b: required_tags 有两个，只覆盖了一个 → 只报缺少的那个"""
        reg = _make_reg(
            _fmt("fmt.source", tags=["domain.gameplay_system"]),
            _fmt("fmt.target", required_tags=["domain.gameplay_system", "content.schema"]),
        )
        n1 = _rule_node("n1", "fmt.source", "fmt.source")
        n2 = _rule_node("n2", "fmt.target", "fmt.out")
        reg.register(_fmt("fmt.out"))
        spec = _spec([n1, n2], [_edge("n1", "n2")])
        findings = run_pipeline_checks(spec, format_registry=reg)
        tag_findings = [f for f in findings if f.check_id == "granted_tag_chain"]
        assert len(tag_findings) == 1
        assert "content.schema" in tag_findings[0].observation
        assert "domain.gameplay_system" not in tag_findings[0].observation  # 已覆盖，不报告


# ═══════════════════════════════════════════════════════════════════════════
# 13-14: 检查开关
# ═══════════════════════════════════════════════════════════════════════════

class TestCheckToggles:

    def test_enabled_only_runs_specified_checks(self):
        """场景13: enabled=['no_entry'] → 只运行 no_entry"""
        n1 = _rule_node("n1", "a", "b")
        n_orphan = _rule_node("orphan", "x", "y")
        spec = _spec([n1, n_orphan], [])  # orphan 孤立

        # 只启用 no_entry
        findings = run_pipeline_checks(spec, enabled=["no_entry"])
        assert all(f.check_id == "no_entry" for f in findings)
        # isolated 不应出现
        assert not any(f.check_id == "isolated" for f in findings)

    def test_disabled_skips_specified_check(self):
        """场景14: disabled=['soft_hard_pairing'] → LLM 节点问题不报"""
        llm = _llm_node("llm_gen", "a", "b")
        sink = _llm_node("sink", "b", "c")
        spec = _spec([llm, sink], [_edge("llm_gen", "sink")])

        findings = run_pipeline_checks(spec, disabled=["soft_hard_pairing"])
        assert not any(f.check_id == "soft_hard_pairing" for f in findings)

    def test_disabled_and_enabled_interact_correctly(self):
        """场景14b: enabled=['isolated', 'soft_hard_pairing'] 且 disabled=['soft_hard_pairing'] → 只有 isolated"""
        llm = _llm_node("llm_gen", "a", "b")
        orphan = _rule_node("orphan", "x", "y")
        spec = _spec([llm, orphan], [])  # orphan 孤立，llm 也孤立

        findings = run_pipeline_checks(
            spec,
            enabled=["isolated", "soft_hard_pairing"],
            disabled=["soft_hard_pairing"],
        )
        ids = {f.check_id for f in findings}
        assert "soft_hard_pairing" not in ids
        # isolated 依然运行（但结果取决于 entry 是否可达，这里两节点都孤立）


# ═══════════════════════════════════════════════════════════════════════════
# 15: 向后兼容接口
# ═══════════════════════════════════════════════════════════════════════════

class TestBackwardCompat:

    def test_check_pipeline_topology_returns_topology_issues(self):
        """场景15: check_pipeline_topology 返回 TopologyIssue 列表（旧接口）"""
        n1 = _rule_node("n1", "a", "b")
        n2 = _rule_node("n2", "c", "d")  # c ≠ b → format_break
        spec = _spec([n1, n2], [_edge("n1", "n2")])

        issues = check_pipeline_topology(spec)
        assert isinstance(issues, list)
        assert all(isinstance(i, TopologyIssue) for i in issues)
        breaks = [i for i in issues if i.check == "format_break"]
        assert len(breaks) == 1
        assert breaks[0].severity == "CRITICAL"

    def test_topology_issue_str(self):
        """场景15b: TopologyIssue.__str__ 格式正确"""
        issue = TopologyIssue(
            check="format_break",
            severity="CRITICAL",
            node_ids=["a", "b"],
            observation="Format 链断裂",
        )
        s = str(issue)
        assert "CRITICAL" in s
        assert "format_break" in s
