# [OMNI] origin=claude-code domain=services/semantic_auditor ts=2026-04-18T00:00:00Z
"""semantic_auditor Phase B2 单测 — LLMAuditRouter 外壳 + FindingWriterRouter。

覆盖：
  - LLMAuditRouter：
    * mock AuditAgent 返回 JSON → 合并 findings
    * LLM 返回非法 JSON → parse_errors 捕获
    * LLM 抛异常 → parse_errors 捕获
    * 无 excerpts → 空 findings
    * 无 bus（测试友好）：注入 agent mock 绕过
  - FindingWriterRouter：
    * 合法 Finding → append REGISTRY §语义合规待审 + ARCH-CHANGES
    * confidence < 0.7 → status=needs_human_review
    * 缺字段 / standard_id 非法 → rejected
    * 去重：(standard_id, target_path) 已存在 open → 不重复写
    * 多条混合：部分合法部分拒
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omnicompany.protocol.anchor import Verdict, VerdictKind  # noqa: E402
from omnicompany.packages.services.semantic_auditor.routers import (  # noqa: E402
    LLMAuditRouter,
    FindingWriterRouter,
)
from omnicompany.packages.services.semantic_auditor.pipeline import (  # noqa: E402
    build_pipeline,
)


_YAML = """
standards:
  - id: TEST-ONE
    file: test_one.md
    applies_to: [router]
    path_match: ["src/**/*.py"]
    excerpt_strategy: full
  - id: TEST-TWO
    file: test_two.md
    applies_to: [design_md]
    path_match: ["**/DESIGN.md"]
    excerpt_strategy: full

kind_inference:
  - kind: router
    match: ["src/**/*.py"]
  - kind: design_md
    match: ["**/DESIGN.md"]
"""

_REGISTRY_TEMPLATE = """<!-- [OMNI] origin=test domain=test ts=2026-04-18 -->

# REGISTRY

## §活跃违规（Guardian / OMNI 规则产出）

| ID | 规则ID | 路径/目标 | 级别 | 首现 | 持续扫描数 | 状态 |
|---|---|---|---|---|---|---|

---

## §语义合规待审（SemanticAuditor 产出 / 人工识别）

| ID | 标准来源 | 目标 | 疑似违规描述 | 信心 | 处置 | 状态 |
|---|---|---|---|---|---|---|
| SA-001 | TEST-ONE | src/existing.py | 先有的条目 | 0.95 | 保留 | open |

---
"""


@pytest.fixture
def fake_root(tmp_path):
    (tmp_path / "docs" / "standards").mkdir(parents=True)
    (tmp_path / "docs" / "standards" / "standards-index.yaml").write_text(_YAML, encoding="utf-8")
    (tmp_path / "test_one.md").write_text("std one", encoding="utf-8")
    (tmp_path / "test_two.md").write_text("std two", encoding="utf-8")
    (tmp_path / "docs" / "tech_debt").mkdir(parents=True)
    (tmp_path / "docs" / "tech_debt" / "REGISTRY.md").write_text(
        _REGISTRY_TEMPLATE, encoding="utf-8"
    )
    return tmp_path


# ═══ Mock AuditAgent =============================================


class _MockAgent:
    """可配置的假 AuditAgent。
    - scripted: list[返回值]，每次 run 弹一条
    - raise_on: 指定 trace_id 抛异常
    """

    def __init__(self, scripted: list | None = None, raise_on: str | None = None):
        self._scripted = list(scripted or [])
        self._raise_on = raise_on
        self.calls: list[dict] = []

    async def run(self, input_data: dict):
        self.calls.append(input_data)
        tid = input_data.get("trace_id", "")
        if self._raise_on and self._raise_on in tid:
            raise RuntimeError(f"mock fail for {tid}")
        if not self._scripted:
            return Verdict(
                kind=VerdictKind.PASS,
                output={"text": json.dumps({"findings": []}), "turn_count": 1,
                        "stop_reason": "finish_tool", "trace_id": tid},
            )
        val = self._scripted.pop(0)
        if isinstance(val, Exception):
            raise val
        return Verdict(
            kind=VerdictKind.PASS,
            output={"text": val, "turn_count": 1,
                    "stop_reason": "finish_tool", "trace_id": tid},
        )


# ═══ LLMAuditRouter ==============================================


class TestLLMAuditRouter:
    @pytest.mark.asyncio
    async def test_findings_parsed_and_merged(self, fake_root):
        mock = _MockAgent(scripted=[
            json.dumps({"findings": [
                {"standard_id": "TEST-ONE", "target_path": "src/a.py",
                 "description": "issue A", "line_hint": 10, "confidence": 0.9,
                 "recommended_action": "fix it"},
            ]}),
            json.dumps({"findings": []}),
        ])
        r = LLMAuditRouter(agent=mock)
        v = await r.run({
            "project_root": str(fake_root),
            "excerpts": [
                {"target": {"path": "src/a.py", "kind": "router"},
                 "standard_id": "TEST-ONE", "excerpt_text": "excerpt 1"},
                {"target": {"path": "src/b.py", "kind": "router"},
                 "standard_id": "TEST-ONE", "excerpt_text": "excerpt 2"},
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["finding_count"] == 1
        assert v.output["audit_count"] == 2
        assert v.output["findings"][0]["target_path"] == "src/a.py"
        assert v.output["parse_errors"] == []

    @pytest.mark.asyncio
    async def test_invalid_json_goes_to_parse_errors(self, fake_root):
        mock = _MockAgent(scripted=["not a json"])
        r = LLMAuditRouter(agent=mock)
        v = await r.run({
            "project_root": str(fake_root),
            "excerpts": [
                {"target": {"path": "src/a.py", "kind": "router"},
                 "standard_id": "TEST-ONE", "excerpt_text": "x"},
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["finding_count"] == 0
        assert len(v.output["parse_errors"]) == 1
        assert "JSON 解析失败" in v.output["parse_errors"][0]["reason"]

    @pytest.mark.asyncio
    async def test_agent_exception_captured(self, fake_root):
        mock = _MockAgent(raise_on="TEST-ONE")
        r = LLMAuditRouter(agent=mock)
        v = await r.run({
            "project_root": str(fake_root),
            "excerpts": [
                {"target": {"path": "src/x.py", "kind": "router"},
                 "standard_id": "TEST-ONE", "excerpt_text": "x"},
            ],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["finding_count"] == 0
        assert len(v.output["parse_errors"]) == 1
        assert "agent.run 异常" in v.output["parse_errors"][0]["reason"]

    @pytest.mark.asyncio
    async def test_empty_excerpts(self, fake_root):
        mock = _MockAgent()
        r = LLMAuditRouter(agent=mock)
        v = await r.run({"project_root": str(fake_root), "excerpts": []})
        assert v.kind == VerdictKind.PASS
        assert v.output["finding_count"] == 0
        assert v.output["audit_count"] == 0
        assert mock.calls == []

    @pytest.mark.asyncio
    async def test_missing_excerpts_key_fails(self, fake_root):
        r = LLMAuditRouter(agent=_MockAgent())
        v = await r.run({"project_root": str(fake_root)})
        assert v.kind == VerdictKind.FAIL

    @pytest.mark.asyncio
    async def test_findings_field_is_not_list(self, fake_root):
        mock = _MockAgent(scripted=[json.dumps({"findings": "not a list"})])
        r = LLMAuditRouter(agent=mock)
        v = await r.run({
            "project_root": str(fake_root),
            "excerpts": [
                {"target": {"path": "src/a.py", "kind": "router"},
                 "standard_id": "TEST-ONE", "excerpt_text": "x"},
            ],
        })
        assert v.output["finding_count"] == 0
        assert len(v.output["parse_errors"]) == 1


# ═══ FindingWriterRouter =========================================


class TestFindingWriterRouter:
    def _read_registry(self, root: Path) -> str:
        return (root / "docs/tech_debt/REGISTRY.md").read_text(encoding="utf-8")

    def test_valid_finding_appended(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(fake_root),
            "findings": [{
                "standard_id": "TEST-ONE",
                "target_path": "src/new.py",
                "description": "problem here",
                "line_hint": 42,
                "confidence": 0.85,
                "recommended_action": "refactor",
            }],
        })
        assert v.kind == VerdictKind.PASS
        assert v.output["added"] == 1
        assert v.output["rejected"] == []
        content = self._read_registry(fake_root)
        assert "SA-002" in content
        assert "src/new.py" in content
        assert "(L42)" in content
        assert "0.85" in content
        # ARCH event 也应该写入
        arch = (fake_root / "docs/ARCH-CHANGES.jsonl").read_text(encoding="utf-8")
        events = [json.loads(line) for line in arch.strip().splitlines()]
        assert any(e["event_type"] == "finding-generated" for e in events)

    def test_low_confidence_goes_to_human_review(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(fake_root),
            "findings": [{
                "standard_id": "TEST-ONE", "target_path": "src/low.py",
                "description": "weak signal", "confidence": 0.4,
                "recommended_action": "check", "line_hint": 1,
            }],
        })
        assert v.output["added"] == 1
        content = self._read_registry(fake_root)
        assert "needs_human_review" in content

    def test_rejects_unknown_standard(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(fake_root),
            "findings": [{
                "standard_id": "NOT-IN-INDEX", "target_path": "src/x.py",
                "description": "x", "confidence": 0.9,
                "recommended_action": "y",
            }],
        })
        assert v.output["added"] == 0
        assert len(v.output["rejected"]) == 1
        assert "未知 standard_id" in v.output["rejected"][0]["reason"]

    def test_rejects_missing_field(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(fake_root),
            "findings": [{
                "standard_id": "TEST-ONE", "target_path": "src/x.py",
                # 缺 description
                "confidence": 0.9, "recommended_action": "y",
            }],
        })
        assert v.output["added"] == 0
        assert "缺字段 description" in v.output["rejected"][0]["reason"]

    def test_rejects_out_of_range_confidence(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(fake_root),
            "findings": [{
                "standard_id": "TEST-ONE", "target_path": "src/x.py",
                "description": "x", "confidence": 1.5,
                "recommended_action": "y",
            }],
        })
        assert v.output["added"] == 0
        assert "confidence" in v.output["rejected"][0]["reason"]

    def test_dedup_existing_open(self, fake_root):
        r = FindingWriterRouter()
        # 已有 SA-001 | TEST-ONE | src/existing.py | open
        v = r.run({
            "project_root": str(fake_root),
            "findings": [{
                "standard_id": "TEST-ONE",
                "target_path": "src/existing.py",
                "description": "same target",
                "confidence": 0.9, "recommended_action": "y",
            }],
        })
        assert v.output["added"] == 0
        assert v.output["deduped"] == 1

    def test_mixed_valid_and_rejected(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(fake_root),
            "findings": [
                {"standard_id": "TEST-ONE", "target_path": "src/a.py",
                 "description": "a", "confidence": 0.9,
                 "recommended_action": "fix a"},
                {"standard_id": "TEST-BAD", "target_path": "src/b.py",
                 "description": "b", "confidence": 0.9,
                 "recommended_action": "fix b"},
                "not a dict",
            ],
        })
        assert v.output["added"] == 1
        assert len(v.output["rejected"]) == 2

    def test_empty_findings(self, fake_root):
        r = FindingWriterRouter()
        v = r.run({"project_root": str(fake_root), "findings": []})
        assert v.kind == VerdictKind.PASS
        assert v.output["added"] == 0

    def test_missing_registry_fails_gracefully(self, tmp_path):
        (tmp_path / "docs" / "standards").mkdir(parents=True)
        (tmp_path / "docs" / "standards" / "standards-index.yaml").write_text(_YAML, encoding="utf-8")
        (tmp_path / "test_one.md").write_text("x", encoding="utf-8")
        (tmp_path / "test_two.md").write_text("x", encoding="utf-8")
        r = FindingWriterRouter()
        v = r.run({
            "project_root": str(tmp_path),
            "findings": [{
                "standard_id": "TEST-ONE", "target_path": "x",
                "description": "x", "confidence": 0.9,
                "recommended_action": "y",
            }],
        })
        assert v.kind == VerdictKind.FAIL
        assert "REGISTRY" in v.output["reason"]


# ═══ Pipeline ====================================================


class TestPipeline5Nodes:
    def test_five_node_spec(self):
        spec = build_pipeline()
        node_ids = [n.id for n in spec.nodes]
        assert node_ids == [
            "artifact_selector",
            "standard_matcher",
            "excerpt_retriever",
            "llm_auditor",
            "finding_writer",
        ]
        assert len(spec.edges) == 4
        # 首尾 format
        assert spec.nodes[0].transformer.from_format == "semantic_auditor.artifact-request"
        assert spec.nodes[-1].transformer.to_format == "semantic_auditor.finding-written"
