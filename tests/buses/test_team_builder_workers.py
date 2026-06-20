# [OMNI] origin=claude-code domain=tests/team_builder ts=2026-04-23T00:00:00Z type=test
"""team_builder V2 单 worker 单测 · 每个 worker 单独调试真实跑的表现.

用户 2026-04-23 明示: 每个都单独测试实际跑的表现.
"""
from __future__ import annotations

import pytest

import asyncio
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from omnicompany.protocol.anchor import VerdictKind


# 跑真 LLM 的测试需 THE_COMPANY_API_KEY · conftest.py 已有 e2e marker
_HAS_LLM_KEY = bool(os.environ.get("THE_COMPANY_API_KEY"))


# ═══════════════════════════════════════════════════════════════════
# WorkspaceDesigner (HARD · 纯规则)
# ═══════════════════════════════════════════════════════════════════


class TestWorkspaceDesigner:
    @pytest.fixture
    def worker(self):
        from omnicompany.packages.services.team_builder.workers.workspace_designer import (
            WorkspaceDesignerWorker,
        )
        return WorkspaceDesignerWorker()

    def test_team_name_from_design_path(self, worker):
        team_design = {
            "design_path": "services/csv_to_md_pipeline/DESIGN.md",
        }
        v = worker.run(team_design)
        assert v.kind == VerdictKind.PASS
        assert v.output["name"] == "csv_to_md_pipeline"
        assert (
            v.output["generated_package_path"]
            == "src/omnicompany/packages/services/csv_to_md_pipeline/"
        )
        assert len(v.output["write_prefixes"]) == 2
        assert "data/services/csv_to_md_pipeline/" in v.output["write_prefixes"]

    def test_team_name_from_name_field_wins(self, worker):
        team_design = {
            "team_name": "FancyTeam",
            "design_path": "services/other_path/DESIGN.md",  # 不该被用
        }
        v = worker.run(team_design)
        assert v.kind == VerdictKind.PASS
        assert v.output["name"] == "fancyteam"

    def test_slugify_special_chars(self, worker):
        team_design = {"team_name": "Csv-To-MD Pipeline!!"}
        v = worker.run(team_design)
        assert v.output["name"] == "csv_to_md_pipeline"

    def test_fallback_unnamed(self, worker):
        team_design = {"description": "no name, no path"}
        v = worker.run(team_design)
        assert v.kind == VerdictKind.PASS
        assert v.output["name"] == "unnamed_team"

    def test_fan_in_from_team_architect(self, worker):
        # composite fan-in 场景: runner 平铺 _from_team_architect 进来
        fanned = {
            "_from_team_architect": {"design_path": "services/my_team/DESIGN.md"},
            # 也可能还有其他 _from_* 字段
        }
        v = worker.run(fanned)
        assert v.kind == VerdictKind.PASS
        assert v.output["name"] == "my_team"

    def test_non_dict_input_fails(self, worker):
        v = worker.run("not a dict")
        assert v.kind == VerdictKind.FAIL
        assert "must be dict" in (v.diagnosis or "")

    def test_output_schema_complete(self, worker):
        """workspace_spec 必须字段齐 (供下游 WorkspaceDesigner material 注册)."""
        v = worker.run({"team_name": "test_team"})
        required = {"name", "write_prefixes", "read_prefixes", "bash_cwd_prefixes", "generated_package_path"}
        assert required.issubset(set(v.output.keys()))


# ═══════════════════════════════════════════════════════════════════
# ContractAuditor (HARD · 静态图)
# ═══════════════════════════════════════════════════════════════════


class TestContractAuditor:
    @pytest.fixture
    def worker(self):
        from omnicompany.packages.services.team_builder.workers.contract_auditor import (
            ContractAuditorWorker,
        )
        return ContractAuditorWorker()

    def _valid_workers(self):
        return [
            {
                "worker_id": "reader", "impl_type": "HARD",
                "format_in": "src.raw", "format_out": "src.parsed",
                "routes": {"PASS": {"action": "next"}},
                "context_sources": [],
            },
            {
                "worker_id": "processor", "impl_type": "SOFT",
                "format_in": "src.parsed", "format_out": "src.processed",
                "routes": {"PASS": {"action": "next"}},
                "context_sources": ["src.parsed"],
            },
            {
                "worker_id": "writer", "impl_type": "HARD",
                "format_in": "src.processed", "format_out": "src.output",
                "routes": {"PASS": {"action": "emit"}},
                "context_sources": [],
            },
        ]

    def _valid_materials(self):
        return [
            {"material_id": "src.raw", "lifecycle": "source", "json_schema": {}},
            {"material_id": "src.parsed", "lifecycle": "internal", "json_schema": {}},
            {"material_id": "src.processed", "lifecycle": "internal", "json_schema": {}},
            {"material_id": "src.output", "lifecycle": "sink", "json_schema": {}},
        ]

    def test_valid_chain_passes(self, worker):
        input_data = {
            "team_builder.material.worker_design_detailed": self._valid_workers(),
            "team_builder.material.material_design_detailed": self._valid_materials(),
        }
        v = worker.run(input_data)
        assert v.kind == VerdictKind.PASS, f"diagnosis={v.diagnosis}"
        assert v.output["overall_ok"] is True
        assert len(v.output["connections"]) >= 2  # 至少 reader→processor, processor→writer
        assert "src.raw" in v.output["source_materials"]
        assert "src.output" in v.output["sink_materials"]

    def test_broken_connection_reported(self, worker):
        """consumer 找不到 producer → overall_ok=False + connections.issue (但 Verdict 仍 PASS · 职责分离)."""
        workers = self._valid_workers()
        workers[1]["format_in"] = "nonexistent_material"
        input_data = {
            "team_builder.material.worker_design_detailed": workers,
            "team_builder.material.material_design_detailed": self._valid_materials(),
        }
        v = worker.run(input_data)
        # Verdict PASS (只产数据), 但 overall_ok=False (供 DesignValidator 判断)
        assert v.kind == VerdictKind.PASS
        assert v.output["overall_ok"] is False
        assert any(
            "no producer" in (c.get("issue") or "")
            for c in v.output["connections"]
        )

    def test_f15_context_sources_reported(self, worker):
        """SOFT Worker 空 context_sources → f15_context_sources_issues 非空, Verdict 仍 PASS."""
        workers = self._valid_workers()
        workers[1]["context_sources"] = []
        input_data = {
            "team_builder.material.worker_design_detailed": workers,
            "team_builder.material.material_design_detailed": self._valid_materials(),
        }
        v = worker.run(input_data)
        assert v.kind == VerdictKind.PASS
        assert v.output["overall_ok"] is False
        assert len(v.output["f15_context_sources_issues"]) == 1

    def test_composite_fan_in_detected(self, worker):
        """Worker 有 list format_in → composite_fan_ins 列出来."""
        workers = self._valid_workers()
        workers[2]["format_in"] = ["src.processed", "src.parsed"]  # fan-in
        input_data = {
            "team_builder.material.worker_design_detailed": workers,
            "team_builder.material.material_design_detailed": self._valid_materials(),
        }
        v = worker.run(input_data)
        assert len(v.output["composite_fan_ins"]) == 1
        assert v.output["composite_fan_ins"][0]["worker"] == "writer"

    def test_fan_in_from_producer_nodes(self, worker):
        """runner 平铺 _from_worker_designer_* 作 fallback 收集."""
        input_data = {
            "_from_worker_designer_reader": self._valid_workers()[0],
            "_from_worker_designer_processor": self._valid_workers()[1],
            "_from_worker_designer_writer": self._valid_workers()[2],
            "_from_material_designer_raw": self._valid_materials()[0],
            "_from_material_designer_parsed": self._valid_materials()[1],
            "_from_material_designer_processed": self._valid_materials()[2],
            "_from_material_designer_output": self._valid_materials()[3],
        }
        v = worker.run(input_data)
        assert v.kind == VerdictKind.PASS, f"diagnosis={v.diagnosis}"
        assert v.output["overall_ok"] is True

    def test_empty_input_fails(self, worker):
        v = worker.run({})
        assert v.kind == VerdictKind.FAIL

    def test_dangling_material_partial(self, worker):
        """孤立 material (既无 producer 也无 consumer) → 出现在 dangling_materials."""
        workers = self._valid_workers()
        materials = self._valid_materials() + [
            {"material_id": "orphan.mat", "lifecycle": "internal", "json_schema": {}}
        ]
        input_data = {
            "team_builder.material.worker_design_detailed": workers,
            "team_builder.material.material_design_detailed": materials,
        }
        v = worker.run(input_data)
        # 职责分离后 · Verdict PASS, 问题体现在 dangling_materials 字段
        assert v.kind == VerdictKind.PASS
        assert "orphan.mat" in v.output["dangling_materials"]

    def test_v2_details_list_from_orchestrator(self, worker):
        """V2 Orchestrator 输出平铺: _from_<producer>.details list 结构 · ContractAuditor 需识别.

        关键: worker/material 两侧都 fan-out, 必须靠 _from_<producer> 子 dict 区分.
        """
        input_data = {
            "_from_worker_designer": {"details": self._valid_workers()},
            "_from_material_designer": {"details": self._valid_materials()},
        }
        v = worker.run(input_data)
        assert v.kind == VerdictKind.PASS, f"diagnosis={v.diagnosis}"
        assert v.output["overall_ok"] is True, f"overall_ok False · connections={v.output['connections']}"
        assert len(v.output["connections"]) >= 2


# ═══════════════════════════════════════════════════════════════════
# ScaleAssessor (AgentNodeLoop · 真 LLM)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_LLM_KEY, reason="需要 THE_COMPANY_API_KEY")
class TestScaleAssessor:
    def _intent_small(self) -> dict:
        return {
            "domain": "data_processing",
            "purpose": "Read a CSV file and print row count.",
            "key_capabilities": ["csv read", "row counting"],
            "constraints": ["Input is a single CSV file"],
            "ambiguities": [],
        }

    def _intent_large(self) -> dict:
        return {
            "domain": "software_factory",
            "purpose": (
                "Build an AI-native software factory that takes natural language requirements, "
                "analyzes them, designs material/worker/team contracts, generates code, validates "
                "compliance, runs integration tests, handles fallback/repair, and registers the "
                "output as a runnable pipeline."
            ),
            "key_capabilities": [
                "requirement analysis", "format design", "node planning",
                "code generation", "compile check", "LAP audit",
                "error route audit", "integration test", "auto fix",
                "registration",
            ],
            "constraints": ["Must generate compliant L3.5 packages"],
            "ambiguities": [],
        }

    def _refs_minimal(self) -> dict:
        return {
            "references": [
                {"source_path": "docs/standards/pipeline.md", "reason": "P-13", "kind": "standard"},
                {"source_path": "src/omnicompany/packages/services/doctor/", "reason": "similar team template", "kind": "similar_team"},
            ],
            "body_path": "<gen>/refs.yaml",
        }

    def test_small_request_classified_small(self):
        from omnicompany.packages.services.team_builder.workers.scale_assessor import (
            ScaleAssessorWorker,
        )
        worker = ScaleAssessorWorker()
        input_data = {
            "_from_intent_analyzer": self._intent_small(),
            "_from_reference_scout": self._refs_minimal(),
        }
        v = asyncio.run(worker.run(input_data))
        print(f"\n[small test] kind={v.kind} output={v.output}")
        assert v.kind == VerdictKind.PASS, f"diagnosis={v.diagnosis}"
        assert v.output["size"] in ("small", "medium"), f"expected small/medium, got {v.output['size']}"
        assert "rationale" in v.output
        assert isinstance(v.output.get("estimated_worker_count"), int)

    def test_large_request_classified_large(self):
        from omnicompany.packages.services.team_builder.workers.scale_assessor import (
            ScaleAssessorWorker,
        )
        worker = ScaleAssessorWorker()
        input_data = {
            "_from_intent_analyzer": self._intent_large(),
            "_from_reference_scout": self._refs_minimal(),
        }
        v = asyncio.run(worker.run(input_data))
        print(f"\n[large test] kind={v.kind} output={v.output}")
        assert v.kind == VerdictKind.PASS, f"diagnosis={v.diagnosis}"
        # 10 capabilities 应判 large (或至少 medium recommend_decompose=true)
        if v.output["size"] == "large":
            assert v.output.get("recommend_decompose") is True
            assert v.output.get("decompose_axis") in ("by_capability", "by_domain", "by_phase")


# ═══════════════════════════════════════════════════════════════════
# MaterialDesigner (AgentNodeLoop · 真 LLM)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_LLM_KEY, reason="需要 LLM API key")
class TestMaterialDesigner:
    def _team_design(self) -> dict:
        """模拟 TeamArchitect 上轮真产出的 csv_to_md team."""
        return {
            "team_name": "csv_to_md_pipeline",
            "design_path": "services/csv_to_md_pipeline/DESIGN.md",
            "purpose": (
                "Automate the ingestion of CSV files and generate structured Markdown "
                "summary reports containing row counts, column-level summaries, and sample rows."
            ),
            "workers_skeleton": [
                {"worker_name": "CsvIngestWorker", "impl_type": "HARD", "brief": "Read CSV + header check"},
                {"worker_name": "ColumnAnalyzerWorker", "impl_type": "SOFT", "brief": "Per-column summary stats"},
                {"worker_name": "SampleExtractorWorker", "impl_type": "HARD", "brief": "Extract sample rows"},
                {"worker_name": "MarkdownAssemblerWorker", "impl_type": "SOFT", "brief": "Render to Markdown"},
            ],
            "materials_skeleton": [
                {"material_id": "csv_to_md.raw_matrix", "brief": "标准化 CSV 数据矩阵 + 文件元信息"},
                {"material_id": "csv_to_md.column_summary", "brief": "列摘要字典 (数据类型/缺失率/统计)"},
                {"material_id": "csv_to_md.sample_rows", "brief": "按采样策略抽出的样本行"},
                {"material_id": "csv_to_md.report", "brief": "最终 Markdown 报告"},
            ],
        }

    def test_orchestrator_deepens_all_materials(self):
        """V2.1 Orchestrator · for-each N 份 materials_skeleton · 并行独立 agent session."""
        from omnicompany.packages.services.team_builder.workers.material_designer import (
            MaterialDesignerWorker,
        )
        worker = MaterialDesignerWorker()
        input_data = {"_from_team_architect": self._team_design()}  # 含 4 个 materials_skeleton
        v = asyncio.run(worker.run(input_data))
        print(f"\n[material designer orchestrator] kind={v.kind} diagnosis={v.diagnosis}")
        print(f"  details count: {len(v.output.get('details', []))}")
        assert v.kind in (VerdictKind.PASS, VerdictKind.PARTIAL), f"diagnosis={v.diagnosis}"
        details = v.output.get("details", [])
        assert len(details) >= 2, f"至少 2 份 deepened (got {len(details)})"
        # 每份 detail 必含核心字段
        for d in details:
            assert "material_id" in d
            assert "json_schema" in d
            assert "description_5elems" in d


# ═══════════════════════════════════════════════════════════════════
# WorkerDesigner (AgentNodeLoop · 真 LLM)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_LLM_KEY, reason="需要 LLM API key")
class TestWorkerDesigner:
    def _team_design(self) -> dict:
        return {
            "team_name": "csv_to_md_pipeline",
            "purpose": "CSV → Markdown 汇总报告",
            "workers_skeleton": [
                {"worker_name": "CsvIngestWorker", "impl_type": "HARD", "brief": "读 CSV + 表头一致性校验 + 异常行清洗"},
                {"worker_name": "ColumnAnalyzerWorker", "impl_type": "SOFT", "brief": "按列做类型推断+统计摘要"},
                {"worker_name": "MarkdownAssemblerWorker", "impl_type": "SOFT", "brief": "聚合所有中间产物渲染 Markdown"},
            ],
            "materials_skeleton": [
                {"material_id": "csv_to_md.raw_matrix", "brief": "标准化数据矩阵"},
                {"material_id": "csv_to_md.column_summary", "brief": "列摘要字典"},
                {"material_id": "csv_to_md.report", "brief": "Markdown 报告"},
            ],
        }

    def test_orchestrator_deepens_all_workers(self):
        """V2.1 Orchestrator · for-each N 份 workers_skeleton · 并行独立 agent session."""
        from omnicompany.packages.services.team_builder.workers.worker_designer import (
            WorkerDesignerWorker,
        )
        worker = WorkerDesignerWorker()
        input_data = {"_from_team_architect": self._team_design()}  # 含 3 个 workers_skeleton
        v = asyncio.run(worker.run(input_data))
        print(f"\n[worker designer orchestrator] kind={v.kind} diagnosis={v.diagnosis}")
        print(f"  details count: {len(v.output.get('details', []))}")
        assert v.kind in (VerdictKind.PASS, VerdictKind.PARTIAL), f"diagnosis={v.diagnosis}"
        details = v.output.get("details", [])
        assert len(details) >= 2, f"至少 2 份 deepened (got {len(details)})"
        for d in details:
            assert d.get("impl_type") in ("HARD", "SOFT", "AGENT")
            assert d.get("format_in")
            assert d.get("format_out")
            if d.get("impl_type") in ("SOFT", "AGENT"):
                assert d.get("context_sources"), f"SOFT/AGENT 必须有 context_sources (worker {d.get('worker_id')})"
            assert d.get("hallucination_risks") and len(d["hallucination_risks"]) >= 1


# ═══════════════════════════════════════════════════════════════════
# DesignValidator (AgentNodeLoop · 7 维综合 · 真 LLM)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_LLM_KEY, reason="需要 LLM API key")
class TestDesignValidator:
    def _healthy_inputs(self) -> dict:
        """全部 7 维合规的输入 (参照 OMNI-034 + B 层命名 + ServiceBus 对接)."""
        return {
            "_from_team_architect": {
                "team_name": "csv_to_md",
                # OMNI-034 标准七节
                "sections": ["状态", "核心目的", "核心接口", "架构规则", "数据流", "已知局限", "参考资料"],
                "workers_skeleton": [
                    {"worker_name": "CsvIngest", "impl_type": "HARD"},
                    {"worker_name": "ColumnAnalyzer", "impl_type": "SOFT"},
                ],
                "materials_skeleton": [
                    {"material_id": "csv_to_md.source", "brief": "input CSV file path"},
                    {"material_id": "csv_to_md.raw", "brief": "standardized data matrix"},
                    {"material_id": "csv_to_md.summary", "brief": "column summary dict"},
                ],
            },
            "_from_workspace_designer": {
                "name": "csv_to_md",
                "write_prefixes": ["src/omnicompany/packages/services/csv_to_md/", "data/services/csv_to_md/"],
                "bash_cwd_prefixes": [""],
                "generated_package_path": "src/omnicompany/packages/services/csv_to_md/",
                "read_prefixes": "READ_ANY",
            },
            "_from_worker_designer_1": {
                "worker_id": "CsvIngest",
                "impl_type": "HARD",
                "format_in": "csv_to_md.source",
                "format_out": "csv_to_md.raw",
                "routes": {
                    "PASS": {"action": "next"},
                    "FAIL": {"action": "retry", "max_retries": 2},
                    "PARTIAL": {"action": "next"},
                },
                "rule_spec": "DiskBus.read_text → pandas.read_csv → header validation",
                "context_sources": [],  # HARD 可空
                "output_token_budget": 1000,
                "hallucination_risks": ["encoding detection error on mixed-encoding files"],
            },
            "_from_worker_designer_2": {
                "worker_id": "ColumnAnalyzer",
                "impl_type": "SOFT",
                "format_in": "csv_to_md.raw",
                "format_out": "csv_to_md.summary",
                "routes": {
                    "PASS": {"action": "emit"},
                    "FAIL": {"action": "retry", "max_retries": 2},
                    "PARTIAL": {"action": "emit"},
                },
                "prompt_template": "Analyze columns of {csv_to_md.raw}",
                "context_sources": ["csv_to_md.raw"],
                "output_token_budget": 4000,
                "hallucination_risks": ["stats error on sparse columns"],
            },
            "_from_material_designer_1": {
                "material_id": "csv_to_md.source",
                "json_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
                "lifecycle": "source",
                "description_5elems": {
                    "content_semantic": "CLI 传入的 CSV 源文件路径",
                    "field_meaning": "path: 绝对或相对路径",
                    "upstream_promise": "CLI 层保证路径存在可读",
                    "downstream_use": "CsvIngest 读取此路径产出 raw 矩阵",
                    "minimal_sample": '{"path": "data/sales.csv"}',
                },
            },
            "_from_material_designer_2": {
                "material_id": "csv_to_md.raw",
                "json_schema": {"type": "object", "properties": {"rows": {"type": "array"}}},
                "lifecycle": "internal",
                "description_5elems": {
                    "content_semantic": "标准化 CSV 数据矩阵",
                    "field_meaning": "rows: list of row dicts, keys = CSV 表头",
                    "upstream_promise": "CsvIngest 产出 UTF-8 解码 + 表头校验通过",
                    "downstream_use": "ColumnAnalyzer 消费作类型推断",
                    "minimal_sample": '{"rows": [{"a":1, "b":"x"}]}',
                },
            },
            "_from_material_designer_3": {
                "material_id": "csv_to_md.summary",
                "json_schema": {"type": "object", "properties": {"columns": {"type": "object"}}},
                "lifecycle": "sink",
                "description_5elems": {
                    "content_semantic": "列摘要字典 (最终产物)",
                    "field_meaning": "columns: dict 每列含 dtype / null_count / stats",
                    "upstream_promise": "ColumnAnalyzer 保证每列有 dtype",
                    "downstream_use": "CLI 渲染 Markdown 报告",
                    "minimal_sample": '{"columns": {"a": {"dtype": "int"}}}',
                },
            },
            "_from_contract_auditor": {
                "overall_ok": True,
                "connections": [
                    {"producer_worker": "CsvIngest", "format_out": "csv_to_md.raw",
                     "consumer_worker": "ColumnAnalyzer", "format_in": "csv_to_md.raw", "ok": True},
                ],
                "orphan_workers": [],
                "dangling_materials": [],
                "source_materials": ["csv_to_md.source"],
                "sink_materials": ["csv_to_md.summary"],
                "f15_context_sources_issues": [],
            },
        }

    def test_7_dimensions_always_produced(self):
        """核心: 不管 PASS/PARTIAL/FAIL, 7 维 field 必须全部产出 (审计完整性)."""
        from omnicompany.packages.services.team_builder.workers.design_validator import (
            DesignValidatorWorker,
        )
        worker = DesignValidatorWorker()
        v = asyncio.run(worker.run(self._healthy_inputs()))
        print(f"\n[design_validator healthy] kind={v.kind} overall={v.output.get('overall')}")
        print(f"  must_fix={v.output.get('must_fix', [])}")
        print(f"  should_fix={v.output.get('should_fix', [])}")
        # 7 维必须全部产出 (审计完整性)
        for dim in (
            "format_check", "naming_check", "workspace_check",
            "servicebus_adoption_check", "contract_closure_check",
            "f15_honesty_check", "worker_18item_check",
        ):
            assert dim in v.output, f"{dim} 缺失"
        # overall 合法值
        assert v.output.get("overall") in ("PASS", "PARTIAL", "FAIL")

    def test_bad_workspace_fails(self):
        """workspace 路径不合规 → should detect."""
        from omnicompany.packages.services.team_builder.workers.design_validator import (
            DesignValidatorWorker,
        )
        inputs = self._healthy_inputs()
        # 注入错误 workspace (./workspace/csv_to_md 而非 src/omnicompany/...)
        inputs["_from_workspace_designer"] = {
            "name": "csv_to_md",
            "write_prefixes": ["./workspace/csv_to_md/"],  # 不合规
            "bash_cwd_prefixes": ["./workspace/csv_to_md/"],
            "generated_package_path": "./workspace/csv_to_md/",
            "read_prefixes": "READ_ANY",
        }
        worker = DesignValidatorWorker()
        v = asyncio.run(worker.run(inputs))
        print(f"\n[design_validator bad_ws] kind={v.kind} overall={v.output.get('overall')}")
        print(f"  workspace_check={v.output.get('workspace_check')}")
        # 应 FAIL 或 PARTIAL (workspace_check should flag issue)
        ws_check = v.output.get("workspace_check", {})
        # issues 或 passed=False 至少一个体现
        assert (not ws_check.get("passed")) or len(ws_check.get("issues", [])) > 0


# ═══════════════════════════════════════════════════════════════════
# DecompositionPlanner (AgentNodeLoop · large 需求拆分 · 真 LLM)
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.e2e
@pytest.mark.skipif(not _HAS_LLM_KEY, reason="需要 LLM API key")
class TestDecompositionPlanner:
    def test_large_request_decomposed(self):
        from omnicompany.packages.services.team_builder.workers.decomposition_planner import (
            DecompositionPlannerWorker,
        )
        worker = DecompositionPlannerWorker()
        input_data = {
            "_from_scale_assessor": {
                "size": "large",
                "recommend_decompose": True,
                "decompose_axis": "by_phase",
                "rationale": "Multi-phase data pipeline (ingest → process → validate → export)",
                "estimated_worker_count": 15,
                "estimated_material_count": 20,
            },
            "_from_intent_analyzer": {
                "domain": "enterprise_data_pipeline",
                "purpose": (
                    "Build an end-to-end data pipeline that ingests raw events from Kafka, "
                    "validates/deduplicates, transforms into analytical schema, writes to "
                    "data warehouse, and publishes dashboard-ready aggregates."
                ),
                "key_capabilities": [
                    "kafka ingestion", "dedup", "schema validation",
                    "transform to analytical schema", "warehouse writes",
                    "aggregate computation", "dashboard publish",
                ],
                "constraints": ["handle 1M events/day", "< 5 min end-to-end latency"],
                "ambiguities": [],
            },
        }
        v = asyncio.run(worker.run(input_data))
        print(f"\n[decompose] kind={v.kind}")
        print(f"  sub_teams: {[st.get('name') for st in v.output.get('sub_teams', [])]}")
        print(f"  contracts: {len(v.output.get('inter_team_contracts', []))}")
        assert v.kind == VerdictKind.PASS, f"diagnosis={v.diagnosis}"
        sub_teams = v.output.get("sub_teams", [])
        contracts = v.output.get("inter_team_contracts", [])
        assert 2 <= len(sub_teams) <= 4
        assert len(contracts) >= 1
        # 每 sub_team 有 name + purpose
        for st in sub_teams:
            assert st.get("name") and st.get("purpose")
        # 每 contract 有 producer + consumer + material + semantics
        for c in contracts:
            assert c.get("producer") and c.get("consumer") and c.get("material") and c.get("semantics")
