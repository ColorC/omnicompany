from __future__ import annotations

import json

import pytest

from omnicompany.dashboard.controlplane import catalogue


def test_material_attribution_report_keeps_read_clues_separate(monkeypatch) -> None:
    def fake_latest(*, worker=None, material=None, target=None):
        return {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "provider": "claude-code",
            "started_at_local": "2026-05-17 20:00:00",
            "review": {
                "kind": "pass",
                "verdict": "pass",
                "critical_count": 0,
                "warning_count": 0,
                "issues": [],
            },
            "worker_runs": [
                {
                    "worker_id": "material_usage_mapper",
                    "status": "succeeded",
                    "provider": "claude-code",
                    "run_id": "worker-run",
                    "rel_path": "workers/material_usage_mapper.py",
                    "material_io_links": [
                        {
                            "material_id": "team_observer.material.run_artifact_bundle",
                            "direction": "read",
                            "registration_status": "declared",
                            "human_title": "run artifact bundle",
                            "human_summary": "声明输入。",
                            "evidence_summary": "来自 FORMAT_IN。",
                        }
                    ],
                    "produced_content_materials": [
                        {
                            "material_id": "team_builder.generated_file.unit.workers.material_usage_mapper.py",
                            "direction": "write",
                            "registration_status": "generated-candidate",
                            "human_title": "生成产物：material_usage_mapper.py",
                            "human_summary": "外部代理生成了这个文件。",
                            "evidence_summary": "来自 changed_files。",
                        }
                    ],
                    "resource_material_links": [
                        {
                            "material_id": "",
                            "direction": "read",
                            "registration_status": "candidate",
                            "human_title": "工作区文件：team.py",
                            "human_summary": "读取过工作区源码。",
                            "evidence_summary": "来自 Read 工具目标。",
                        }
                    ],
                    "inferred_material_read_links": [],
                    "static_field_access": {
                        "input_field_reads": {
                            "team_observer.material.run_artifact_bundle": ["team_id", "files"],
                        },
                        "missing_input_required": {},
                        "missing_output_required": [],
                        "output_field_writes": ["nodes", "edges"],
                    },
                }
            ],
        }

    monkeypatch.setattr(catalogue, "_latest_team_builder_materialization", fake_latest)

    report = catalogue._material_attribution_report()

    assert report["available"] is True
    assert report["verdict"] == "warning"
    assert report["counts"]["generated_artifacts"] == 1
    assert report["counts"]["read_clues"] == 1
    assert report["counts"]["confirmed_reads"] == 0
    assert report["counts"]["read_groups"] == 2
    assert report["worker_reports"][0]["read_clues"][0]["kind_label"] == "实战读取线索"
    assert report["worker_reports"][0]["confirmed_reads"] == []
    assert [group["group_kind"] for group in report["read_groups"]] == ["tool_clues", "unconfirmed"]
    assert report["read_groups"][0]["status"] == "evidence"
    assert report["read_groups"][1]["status"] == "candidate"
    assert "不能当作事实 material 读边" in report["read_groups"][1]["decision"]
    confirmed_gate = next(gate for gate in report["quality_gates"] if gate["id"] == "confirmed_reads")
    assert confirmed_gate["status"] == "warning"
    assert "没有伪装成事实" in confirmed_gate["summary"]


def test_material_attribution_report_splits_content_mentions_from_gaps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    target_file = tmp_path / "src" / "omnicompany" / "packages" / "services" / "_learning" / "knowledge" / "routers.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        '# [OMNI] material_id="material:unit.knowledge_router"\n',
        encoding="utf-8",
    )

    def fake_latest(*, worker=None, material=None, target=None):
        return {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "provider": "claude-code",
            "started_at_local": "2026-05-17 20:00:00",
            "review": {"kind": "pass", "verdict": "pass", "issues": []},
            "worker_runs": [
                {
                    "worker_id": "health_report_writer",
                    "status": "succeeded",
                    "provider": "claude-code",
                    "run_id": "worker-run",
                    "rel_path": "workers/health_report_writer.py",
                    "material_io_links": [
                        {"material_id": "team_observer.material.material_lineage_graph", "direction": "read"}
                    ],
                    "produced_content_materials": [
                        {"material_id": "team_builder.generated_file.unit.health_report_writer.py", "direction": "write"}
                    ],
                    "resource_material_links": [
                        {
                            "material_id": "",
                            "direction": "read",
                            "registration_status": "candidate",
                            "resource_kind": "workspace",
                            "target": "file_path=src/omnicompany/packages/services/knowledge/routers.py",
                            "human_title": "旧 knowledge 路径",
                            "evidence_summary": "Read 结果内容里提到了旧路径。",
                        }
                    ],
                    "inferred_material_read_links": [
                        {
                            "material_id": "material:unit.confirmed",
                            "direction": "read",
                            "registration_status": "declared-in-file",
                            "target": "file_path=src/confirmed.py",
                        }
                    ],
                    "tool_events": [
                        {
                            "index": 3,
                            "tool": "Read",
                            "read_like": True,
                            "targets": ["file_path=src/omnicompany/packages/services/_utility/skill_importer/workers/requirement_draft.py"],
                            "result_paths": ["src/omnicompany/packages/services/knowledge/routers.py"],
                            "result_path_evidence_kind": "content_mention_path",
                        }
                    ],
                    "static_field_access": {
                        "input_field_reads": {"team_observer.material.material_lineage_graph": ["nodes"]},
                        "missing_input_required": {},
                        "missing_output_required": [],
                        "output_field_writes": ["summary_cn"],
                    },
                }
            ],
        }

    monkeypatch.setattr(catalogue, "_latest_team_builder_materialization", fake_latest)

    report = catalogue._material_attribution_report()

    assert report["verdict"] == "pass"
    assert report["counts"]["unconfirmed_read_clues"] == 0
    assert report["counts"]["content_mention_read_clues"] == 1
    assert [group["group_kind"] for group in report["read_groups"]] == ["tool_clues", "content_mentions", "confirmed"]
    content_group = next(group for group in report["read_groups"] if group["group_kind"] == "content_mentions")
    assert content_group["status"] == "explanatory"
    assert "不是 worker 直接读取" in content_group["decision"]
    assert content_group["sample_material_ids"] == ["material:unit.knowledge_router"]
    assert report["open_questions"] == []
    confirmed_gate = next(gate for gate in report["quality_gates"] if gate["id"] == "confirmed_reads")
    assert confirmed_gate["status"] == "pass"


def test_team_builder_read_clue_resolution_plan_explains_unresolved(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    team_builder_dir = tmp_path / "src" / "omnicompany" / "packages" / "services" / "_core" / "team_builder"
    team_builder_dir.mkdir(parents=True)
    (team_builder_dir / "demo_worker.py").write_text(
        '# [OMNI] material_id="material:unit.demo_worker.py"\nclass DemoWorker(Worker):\n    pass\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "warning",
            "summary": "material warning",
            "worker_reports": [
                {
                    "worker_id": "mapper",
                    "tool_events": [
                        {
                            "index": 0,
                            "tool": "Grep",
                            "event_type": "AssistantMessage",
                            "read_like": True,
                            "targets": [
                                "dir_path=src/omnicompany/packages/services/_core/team_builder",
                                "pattern=DemoWorker",
                            ],
                        },
                        {
                            "index": 1,
                            "tool": "Read",
                            "event_type": "AssistantMessage",
                            "read_like": True,
                            "targets": [
                                "file_path=src/omnicompany/packages/services/_core/team_builder/demo_worker.py"
                            ],
                        },
                    ],
                    "read_clues": [
                        {
                            "title": "目录读取线索",
                            "target": "dir_path=src/omnicompany/packages/services/_core/team_builder",
                            "resource_kind": "workspace",
                            "evidence_summary": "List 工具读取目录。",
                            "evidence": ["List src/omnicompany/packages/services/_core/team_builder"],
                        },
                        {
                            "title": "grep 命令线索",
                            "target": "command=grep material_id src/omnicompany/packages/services/_core/team_builder",
                            "resource_kind": "workspace",
                            "evidence_summary": "grep 命令需要回放命中文件。",
                        },
                        {
                            "title": "已确认文件",
                            "target": "file_path=src/example.py",
                            "resource_kind": "workspace",
                            "declared_material_ids": ["material:example.source"],
                            "evidence_summary": "文件头声明 material_id。",
                        },
                    ],
                }
            ],
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_read_clue_resolution_plan()

    assert plan["available"] is True
    assert plan["verdict"] == "warning"
    assert plan["counts"]["read_clues"] == 3
    assert plan["counts"]["confirmed"] == 1
    assert plan["counts"]["confirmed_read_edges"] == 0
    assert plan["counts"]["unresolved"] == 2
    assert plan["counts"]["candidate_materialized"] == 1
    assert plan["counts"]["candidate_materials"] == 1
    assert plan["counts"]["unexpanded"] == 1
    assert plan["counts"]["tool_scope_confirmed"] == 1
    assert plan["counts"]["tool_read_confirmed_materials"] == 1
    assert plan["counts"]["content_mention_path_materials"] == 0
    assert plan["counts"]["auto_expandable"] == 1
    assert plan["counts"]["trace_replay_required"] == 1
    assert [action["category"] for action in plan["actions"]] == ["expand_directory", "tool_trace_replay"]
    assert all("不能作为确认 material 读边" in action["reason"] for action in plan["actions"])
    assert plan["actions"][0]["status"] == "candidate_materialized"
    assert "目录 src/omnicompany/packages/services/_core/team_builder" in plan["actions"][0]["review_target"]
    assert plan["actions"][0]["material_id_hits"] == ["material:unit.demo_worker.py"]
    assert plan["actions"][0]["candidate_materials"][0]["material_id"] == "material:unit.demo_worker.py"
    assert plan["actions"][0]["candidate_materials"][0]["needs_confirmation"] is True
    assert plan["actions"][0]["tool_confirmation"]["status"] == "scope_and_read_confirmed"
    assert plan["actions"][0]["tool_confirmation"]["confirmed_materials"][0]["material_id"] == "material:unit.demo_worker.py"
    assert plan["actions"][0]["review_examples"][0]["path"].endswith("demo_worker.py")
    assert plan["actions"][0]["raw_evidence"] == ["List src/omnicompany/packages/services/_core/team_builder"]
    assert plan["source"]["read_clue_resolution_plan_material"].endswith("team_read_clue_resolution_plan.json")
    assert (tmp_path / plan["source"]["read_clue_resolution_plan_material"]).exists()


def test_declared_file_resource_link_is_synthesized_as_confirmed_read() -> None:
    resource_links = [
        {
            "material_id": "workspace.file.example_py",
            "target": "file_path=src/example.py",
            "target_key": "file_path",
            "normalized_target": "src/example.py",
            "candidate_kind": "file",
            "resource_kind": "workspace",
            "declared_material_ids": ["material:example.source_file.py"],
            "evidence": ["Read example.py"],
        }
    ]

    inferred = catalogue._synthesize_declared_file_read_links(resource_links, [])

    assert len(inferred) == 1
    assert inferred[0]["material_id"] == "material:example.source_file.py"
    assert inferred[0]["registration_status"] == "declared-in-file"
    assert inferred[0]["candidate_material_id"] == "workspace.file.example_py"
    assert "OMNI material_id" in inferred[0]["evidence_summary"]


def test_glob_read_target_can_promote_files_with_omni_headers() -> None:
    material_ids = catalogue._materialization_declared_material_ids(
        "pattern=src/omnicompany/packages/services/_core/team_builder/workers/*.py",
        "src/omnicompany/packages/services/_core/team_builder/workers/*.py",
    )

    assert "material:core.team_builder.hard_template_generators.six_file.py" in material_ids
    assert "material:core.team_builder.compile_checker.three_layer.py" in material_ids


def test_team_builder_test_report_smokes_generated_package(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "unit-run"
    code_root = run_dir / "code_package_files"
    materials_dir = run_dir / "materials"
    (code_root / "workers").mkdir(parents=True)
    (code_root / ".omni").mkdir()
    materials_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (materials_dir / "code_package.json").write_text(
        json.dumps({"team_name": "unit_generated_team"}),
        encoding="utf-8",
    )
    (code_root / "__init__.py").write_text("", encoding="utf-8")
    (code_root / "DESIGN.md").write_text("# DESIGN\n", encoding="utf-8")
    (code_root / ".omni" / "workspace.yaml").write_text("name: unit\n", encoding="utf-8")
    (code_root / "formats.py").write_text("def register_formats(registry):\n    return registry\n", encoding="utf-8")
    (code_root / "team.py").write_text(
        "class Node:\n"
        "    def __init__(self, id):\n"
        "        self.id = id\n"
        "class Spec:\n"
        "    id = 'unit_generated_team'\n"
        "    entry = 'worker_a'\n"
        "    nodes = [Node('worker_a')]\n"
        "    edges = []\n"
        "def build_team():\n"
        "    return Spec()\n",
        encoding="utf-8",
    )
    (code_root / "run.py").write_text(
        "from .workers.worker_a import WorkerA\n"
        "def build_bindings(input_dict=None):\n"
        "    return {'worker_a': WorkerA()}\n",
        encoding="utf-8",
    )
    (code_root / "workers" / "__init__.py").write_text("", encoding="utf-8")
    (code_root / "workers" / "worker_a.py").write_text(
        "from omnicompany.protocol.anchor import Verdict, VerdictKind\n"
        "class WorkerA:\n"
        "    FORMAT_IN = 'unit.input.observation_request'\n"
        "    FORMAT_OUT = 'unit.material.bundle'\n"
        "    def run(self, input_data):\n"
        "        return Verdict(kind=VerdictKind.PASS, output={'ok': True}, diagnosis='unit pass')\n",
        encoding="utf-8",
    )

    report = catalogue._team_builder_test_report()

    assert report["available"] is True
    assert report["verdict"] == "pass"
    assert report["counts"]["worker_files"] == 1
    assert report["counts"]["executed_workers"] == 1
    assert report["counts"]["stubbed_workers"] == 0
    assert report["worker_run_smoke"]["status"] == "pass"
    assert report["smoke"]["team_id"] == "unit_generated_team"
    assert report["smoke"]["missing_bindings"] == []
    assert report["contract_coverage"]["status"] == "no_contract_registry"
    assert report["source"]["contract_coverage_material"].endswith("team_contract_coverage.json")
    assert (materials_dir / "team_test_report.json").is_file()
    assert (materials_dir / "team_doctor_findings.json").is_file()
    assert (materials_dir / "team_contract_coverage.json").is_file()

    findings_report = catalogue._team_builder_latest_doctor_findings_report()
    assert findings_report["available"] is True
    assert findings_report["team_name"] == "unit_generated_team"
    assert findings_report["counts"]["total"] == 1
    assert findings_report["findings"][0]["check_id"] == "team_builder.contract.coverage_missing"


def test_team_builder_contract_coverage_matches_existing_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "contract-run"
    (run_dir / "materials").mkdir(parents=True)
    contract_dir = tmp_path / "tests" / "teams" / "unit_generated_team"
    contract_dir.mkdir(parents=True)
    (contract_dir / "test_contract.py").write_text(
        "PIPELINE_NAME = 'unit-generated-team'\n",
        encoding="utf-8",
    )

    report = catalogue._team_builder_contract_coverage_report("unit_generated_team", "contract-run", run_dir)

    assert report["verdict"] == "warning"
    assert report["status"] == "configured"
    assert report["counts"]["available_contracts"] == 1
    assert report["counts"]["matching_contracts"] == 1
    assert report["counts"]["executed_contracts"] == 0
    assert report["matching_contracts"][0]["slug"] == "unit_generated_team"
    assert report["matching_contracts"][0]["pipeline_name"] == "unit-generated-team"
    assert report["quality_gates"][1]["status"] == "pass"
    assert (run_dir / "materials" / "team_contract_coverage.json").is_file()


def test_team_builder_contract_execution_writes_result_material(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "contract-run"
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (materials_dir / "code_package.json").write_text(
        json.dumps({"team_name": "unit_generated_team"}),
        encoding="utf-8",
    )
    contract_dir = tmp_path / "tests" / "teams" / "unit_generated_team"
    contract_dir.mkdir(parents=True)
    (contract_dir / "test_contract.py").write_text(
        "PIPELINE_NAME = 'unit-generated-team'\n",
        encoding="utf-8",
    )

    class Completed:
        returncode = 0
        stdout = "1 passed\n"
        stderr = ""

    monkeypatch.setattr(catalogue.subprocess, "run", lambda *args, **kwargs: Completed())

    report = catalogue._team_builder_execute_contracts_report()

    assert report["verdict"] == "pass"
    assert report["status"] == "executed"
    assert report["counts"]["executed_contracts"] == 1
    assert report["contracts"][0]["status"] == "pass"
    assert report["contracts"][0]["path"] == "tests\\teams\\unit_generated_team\\test_contract.py" or report["contracts"][0]["path"] == "tests/teams/unit_generated_team/test_contract.py"
    assert (materials_dir / "team_contract_execution_result.json").is_file()

    coverage = catalogue._team_builder_contract_coverage_report("unit_generated_team", "contract-run", run_dir)
    assert coverage["status"] == "executed"
    assert coverage["verdict"] == "pass"
    assert coverage["counts"]["executed_contracts"] == 1


def test_team_builder_doctor_reports_contract_execution_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_generated_team",
            "doctor_findings": [],
            "worker_run_smoke": {"skipped_workers": []},
            "contract_coverage": {
                "available": True,
                "verdict": "fail",
                "counts": {"matching_contracts": 1, "executed_contracts": 1},
                "latest_execution": {
                    "available": True,
                    "summary": "contract failed",
                    "contracts": [
                        {
                            "slug": "unit_generated_team",
                            "path": "tests/teams/unit_generated_team/test_contract.py",
                            "status": "fail",
                            "returncode": 1,
                            "stdout_tail": "FAILED test_contract.py::test_success_case",
                            "stderr_tail": "",
                            "command": "python -m pytest -q tests/teams/unit_generated_team/test_contract.py --team-mode=programmatic",
                        }
                    ],
                },
            },
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_result",
        lambda: {"available": False, "verdict": "not_run", "counts": {}},
    )
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {"available": True, "verdict": "pass", "read_groups": []},
    )

    report = catalogue._team_builder_latest_doctor_findings_report()

    assert report["verdict"] == "fail"
    assert report["counts"]["blocking"] == 1
    finding = report["findings"][0]
    assert finding["check_id"] == "team_builder.contract.execution_failed"
    assert finding["level"] == "blocking"
    assert "FAILED test_contract.py::test_success_case" in finding["observation"]


def test_team_builder_repair_plan_classifies_contract_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_generated_team",
            "verdict": "fail",
            "summary": "contract fail",
            "counts": {"total": 1, "blocking": 1},
            "findings": [
                {
                    "id": "team_builder.contract.execution_failed:unit_generated_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "level": "blocking",
                    "location": "team:unit_generated_team",
                    "observation": "contract 执行失败: tests/teams/unit_generated_team/test_contract.py",
                    "implication": "acceptance 已明确失败，应进入 repair_required。",
                    "cross_refs": ["tests/teams/unit_generated_team/test_contract.py", "contract_execution"],
                }
            ],
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_repair_plan()
    action = plan["actions"][0]

    assert plan["verdict"] == "repair_required"
    assert plan["counts"]["repair_required"] == 1
    assert action["policy_rule_id"] == "contract_failure_patch_plan_only"
    assert action["automation_level"] == "patch_plan_only"
    assert action["auto_safe"] is False
    assert "contract execution 失败详情" in action["next_action"]
    assert [item["endpoint"] for item in action["validation_actions"]] == [
        "/api/team-builder-materialization/contract-execution/latest",
        "/api/team-builder-materialization/repair-patch-candidates/latest",
    ]


def test_team_builder_test_doctor_findings_keep_worker_skip_reason() -> None:
    gates = [
        catalogue._test_gate(
            "worker_run_smoke",
            "worker 业务 run smoke",
            "warning",
            "已执行 1 个 worker，跳过 1 个，失败 0 个。",
            ["health_report_writer 跳过: requires_llm"],
        )
    ]
    worker_payload = {
        "doctor_findings": [
            {
                "check_id": "team_builder.worker_run_smoke.requires_llm",
                "level": "advisory",
                "location": "node:health_report_writer",
                "node_ids": ["health_report_writer"],
                "observation": "业务 run smoke 跳过：这个 worker 需要调用 LLM。",
                "implication": "完整端到端通过还需要受控 LLM smoke 或模型调用 stub。",
            }
        ]
    }

    findings = catalogue._team_builder_test_doctor_findings("unit_generated_team", gates, worker_payload)

    assert any(item["check_id"] == "team_builder.test.worker_run_smoke" for item in findings)
    skip = next(item for item in findings if item["check_id"] == "team_builder.worker_run_smoke.requires_llm")
    assert skip["level"] == "advisory"
    assert skip["node_ids"] == ["health_report_writer"]


def test_team_builder_doctor_findings_include_unconfirmed_read_groups(monkeypatch) -> None:
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_generated_team",
            "verdict": "warning",
            "summary": "test warning",
            "doctor_findings": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "read_groups": [
                {
                    "id": "read_group:health_report_writer:unconfirmed",
                    "worker_id": "health_report_writer",
                    "group_kind": "unconfirmed",
                    "title": "health_report_writer 的待确认读取线索",
                    "summary": "仍有 3 条工具读取线索缺少确认。",
                    "decision": "只能作为审阅线索，不能当作事实 material 读边。",
                    "next_action": "补工具输出路径或 Read 证据。",
                    "count": 3,
                    "sample_targets": ["src/omnicompany/packages/services/_learning/knowledge/routers.py"],
                    "sample_material_ids": ["material:unit.knowledge_router"],
                },
                {
                    "id": "read_group:health_report_writer:confirmed",
                    "worker_id": "health_report_writer",
                    "group_kind": "confirmed",
                    "title": "health_report_writer 的确认读取关系",
                    "summary": "已经确认。",
                    "decision": "可消费。",
                    "next_action": "保留。",
                    "count": 2,
                    "sample_targets": [],
                    "sample_material_ids": [],
                },
            ],
        },
    )

    report = catalogue._team_builder_latest_doctor_findings_report()

    assert report["counts"]["total"] == 1
    finding = report["findings"][0]
    assert finding["check_id"] == "team_builder.material.unconfirmed_read_group"
    assert finding["level"] == "advisory"
    assert finding["node_ids"] == ["health_report_writer"]
    assert finding["material_ids"] == ["material:unit.knowledge_router"]
    assert "不能当作事实 material 读边" in finding["implication"]
    assert report["source"]["material_report_endpoint"].endswith("/report/latest")


def test_team_builder_material_gap_validation_resolves_relocated_paths(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    target_file = tmp_path / "src" / "omnicompany" / "packages" / "services" / "_learning" / "knowledge" / "routers.py"
    target_file.parent.mkdir(parents=True)
    target_file.write_text(
        '# [OMNI] material_id="material:unit.knowledge_router"\n',
        encoding="utf-8",
    )
    renamed_file = tmp_path / "src" / "omnicompany" / "packages" / "services" / "_core" / "team_builder" / "routers.py"
    renamed_file.parent.mkdir(parents=True)
    renamed_file.write_text(
        '# [OMNI] material_id="material:unit.team_builder_routers"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "read_groups": [
                {
                    "id": "read_group:worker:unconfirmed",
                    "worker_id": "worker",
                    "group_kind": "unconfirmed",
                    "title": "worker 的待确认读取线索",
                    "sample_targets": [
                        "file_path=src/omnicompany/packages/services/knowledge/routers.py",
                        "file_path=src/omnicompany/packages/services/workflow_factory/routers.py",
                    ],
                }
            ],
        },
    )

    report = catalogue._team_builder_material_gap_validation_report()

    assert report["available"] is True
    assert report["verdict"] == "pass"
    assert report["counts"]["targets"] == 2
    assert report["counts"]["resolved_targets"] == 2
    assert report["counts"]["relocated_targets"] == 2
    assert report["counts"]["material_id_hits"] == 2
    assert report["counts"]["missing_targets"] == 0
    targets = report["groups"][0]["targets"]
    assert targets[0]["status"] == "material_id_found"
    assert targets[0]["material_ids"] == ["material:unit.knowledge_router"]
    assert targets[0]["resolution_kind"] == "relocated_path"
    assert targets[1]["status"] == "material_id_found"
    assert targets[1]["resolution_kind"] == "renamed_alias"
    assert targets[1]["material_ids"] == ["material:unit.team_builder_routers"]
    assert report["source"]["material_gap_validation_material"].endswith("team_material_gap_validation_report.json")


def test_team_builder_read_clue_resolution_uses_relocated_path_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    learning_file = tmp_path / "src" / "omnicompany" / "packages" / "services" / "_learning" / "absorption" / "landmark_picker.py"
    learning_file.parent.mkdir(parents=True)
    learning_file.write_text(
        '# [OMNI] material_id="material:unit.learning_landmark_picker"\n',
        encoding="utf-8",
    )
    renamed_file = tmp_path / "src" / "omnicompany" / "packages" / "services" / "_core" / "team_builder" / "routers.py"
    renamed_file.parent.mkdir(parents=True)
    renamed_file.write_text(
        '# [OMNI] material_id="material:unit.team_builder_routers"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "warning",
            "summary": "material warning",
            "worker_reports": [
                {
                    "worker_id": "health_report_writer",
                    "tool_events": [
                        {
                            "index": 5,
                            "tool": "Read",
                            "read_like": True,
                            "targets": ["file_path=src/omnicompany/packages/services/_utility/skill_importer/workers/requirement_draft.py"],
                            "result_paths": [
                                "src/omnicompany/packages/services/absorption/landmark_picker.py",
                                "src/omnicompany/packages/services/workflow_factory/routers.py",
                            ],
                        }
                    ],
                    "read_clues": [
                        {
                            "title": "旧 absorption 路径",
                            "target": "file_path=src/omnicompany/packages/services/absorption/landmark_picker.py",
                            "resource_kind": "workspace",
                            "evidence_summary": "工具输出里出现旧路径。",
                        },
                        {
                            "title": "旧 workflow_factory 路径",
                            "target": "file_path=src/omnicompany/packages/services/workflow_factory/routers.py",
                            "resource_kind": "workspace",
                            "evidence_summary": "工具输出里出现旧路径。",
                        },
                    ],
                }
            ],
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_read_clue_resolution_plan()

    assert plan["available"] is True
    assert plan["counts"]["unresolved"] == 0
    assert plan["counts"]["candidate_materialized"] == 0
    assert plan["counts"]["candidate_materials"] == 0
    assert plan["counts"]["unexpanded"] == 0
    assert plan["counts"]["tool_read_confirmed_materials"] == 0
    assert plan["counts"]["content_mention_path_clues"] == 2
    assert plan["counts"]["content_mention_path_materials"] == 2
    assert plan["counts"]["tool_scope_confirmed"] == 0
    assert plan["actions"] == []
    assert plan["content_mention_actions"][0]["status"] == "content_mention_explained"
    assert "_learning/absorption/landmark_picker.py" in plan["content_mention_actions"][0]["review_target"]
    assert plan["content_mention_actions"][0]["material_id_hits"] == ["material:unit.learning_landmark_picker"]
    assert "_core/team_builder/routers.py" in plan["content_mention_actions"][1]["review_target"]
    assert plan["content_mention_actions"][1]["candidate_materials"][0]["material_id"] == "material:unit.team_builder_routers"
    assert plan["content_mention_actions"][1]["tool_confirmation"]["status"] == "content_mention_path_without_scope_event"
    assert plan["content_mention_actions"][1]["tool_confirmation"]["confirmed_materials"][0]["evidence_kind"] == "content_mention_path"


def test_team_builder_test_report_records_llm_stub_evidence(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "llm-run"
    code_root = run_dir / "code_package_files"
    materials_dir = run_dir / "materials"
    (code_root / "workers").mkdir(parents=True)
    (code_root / ".omni").mkdir()
    materials_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (materials_dir / "code_package.json").write_text(
        json.dumps({"team_name": "unit_llm_team"}),
        encoding="utf-8",
    )
    (code_root / "__init__.py").write_text("", encoding="utf-8")
    (code_root / "DESIGN.md").write_text("# DESIGN\n", encoding="utf-8")
    (code_root / ".omni" / "workspace.yaml").write_text("name: unit\n", encoding="utf-8")
    (code_root / "formats.py").write_text("def register_formats(registry):\n    return registry\n", encoding="utf-8")
    (code_root / "team.py").write_text(
        "class Node:\n"
        "    def __init__(self, id):\n"
        "        self.id = id\n"
        "class Spec:\n"
        "    id = 'unit_llm_team'\n"
        "    entry = 'soft_worker'\n"
        "    nodes = [Node('soft_worker')]\n"
        "    edges = []\n"
        "def build_team():\n"
        "    return Spec()\n",
        encoding="utf-8",
    )
    (code_root / "run.py").write_text(
        "from .workers.soft_worker import SoftWorker\n"
        "def build_bindings(input_dict=None):\n"
        "    return {'soft_worker': SoftWorker()}\n",
        encoding="utf-8",
    )
    (code_root / "workers" / "__init__.py").write_text("", encoding="utf-8")
    (code_root / "workers" / "soft_worker.py").write_text(
        "from omnicompany.protocol.anchor import Verdict, VerdictKind\n"
        "def call_llm_json(**kwargs):\n"
        "    raise RuntimeError('真实模型不应在单测里调用')\n"
        "class SoftWorker:\n"
        "    FORMAT_IN = 'unit.input.observation_request'\n"
        "    FORMAT_OUT = 'unit.material.health_report'\n"
        "    def run(self, input_data):\n"
        "        result = call_llm_json(\n"
        "            system='请输出中文结论，并保持 JSON。',\n"
        "            user='严格 JSON: summary_cn, risks, next_checks。',\n"
        "            model='unit-model',\n"
        "            max_tokens=123,\n"
        "        )\n"
        "        return Verdict(kind=VerdictKind.PASS, output=result, diagnosis='soft pass')\n",
        encoding="utf-8",
    )

    report = catalogue._team_builder_test_report()

    assert report["verdict"] == "warning"
    assert report["counts"]["stubbed_workers"] == 1
    assert report["counts"]["skipped_workers"] == 1
    stubbed = report["worker_run_smoke"]["stubbed_workers"][0]
    assert stubbed["worker_id"] == "soft_worker"
    assert stubbed["kind"] == "pass"
    call = report["worker_run_smoke"]["llm_stub_calls"][0]
    assert call["model"] == "unit-model"
    assert call["max_tokens"] == 123
    assert call["expected_output_keys"] == ["summary_cn", "risks", "next_checks"]
    assert call["has_json_instruction"] is True
    assert call["has_chinese_instruction"] is True


def test_team_builder_worker_smoke_stubs_llm_client(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    package_dir = tmp_path / "unit_llm_client_team"
    (package_dir / "workers").mkdir(parents=True)
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "team.py").write_text(
        "class Node:\n"
        "    def __init__(self, id):\n"
        "        self.id = id\n"
        "class Spec:\n"
        "    id = 'unit_llm_client_team'\n"
        "    nodes = [Node('soft_worker')]\n"
        "def build_team():\n"
        "    return Spec()\n",
        encoding="utf-8",
    )
    (package_dir / "run.py").write_text(
        "from .workers.soft_worker import SoftWorker\n"
        "def build_bindings(input_dict=None):\n"
        "    return {'soft_worker': SoftWorker()}\n",
        encoding="utf-8",
    )
    (package_dir / "workers" / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "workers" / "soft_worker.py").write_text(
        "from omnicompany.protocol.anchor import Verdict, VerdictKind\n"
        "from omnicompany.runtime.llm.llm import LLMClient\n"
        "class SoftWorker:\n"
        "    FORMAT_IN = 'unit.input.observation_request'\n"
        "    FORMAT_OUT = 'unit.material.health_report'\n"
        "    def run(self, input_data):\n"
        "        client = LLMClient(role='ide_agent', max_tokens=321, tools=[])\n"
        "        response = client.call(\n"
        "            messages=[{'role': 'user', 'content': '严格 JSON: summary_cn, risks, next_checks。'}],\n"
        "            system='请输出中文结论，并保持 JSON。',\n"
        "        )\n"
        "        text = ''.join(block.text for block in response.content if hasattr(block, 'text'))\n"
        "        return Verdict(kind=VerdictKind.PASS, output={'raw': text}, diagnosis='llmclient pass')\n",
        encoding="utf-8",
    )

    result = catalogue._run_generated_worker_run_smoke(package_dir, "unit_llm_client_team")
    payload = result["result"]

    assert result["returncode"] == 0
    assert payload["status"] == "warning"
    assert payload["stubbed_workers"][0]["worker_id"] == "soft_worker"
    assert payload["stubbed_workers"][0]["kind"] == "pass"
    assert payload["stubbed_workers"][0]["stub"] == "LLMClient.call"
    call = payload["llm_stub_calls"][0]
    assert call["model"] == "ide_agent"
    assert call["max_tokens"] == 321
    assert call["has_json_instruction"] is True
    assert call["has_chinese_instruction"] is True


def test_team_builder_repair_plan_classifies_llm_gap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_generated_team",
            "verdict": "warning",
            "summary": "unit",
            "counts": {"total": 1, "advisory": 1},
            "findings": [
                {
                    "id": "team_builder.worker_run_smoke.requires_llm:health_report_writer",
                    "check_id": "team_builder.worker_run_smoke.requires_llm",
                    "level": "advisory",
                    "location": "node:health_report_writer",
                    "node_ids": ["health_report_writer"],
                    "observation": "业务 run smoke 跳过：这个 worker 需要调用 LLM。",
                }
            ],
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_repair_plan()

    assert plan["verdict"] == "validation_gap"
    assert plan["counts"]["repair_required"] == 0
    assert plan["actions"][0]["category"] == "validation_gap"
    assert plan["actions"][0]["auto_safe"] is False
    assert plan["actions"][0]["policy_rule_id"] == "validation_gap_no_code_change"
    assert plan["actions"][0]["automation_level"] == "none"
    assert "受控 LLM 回放计划" in plan["actions"][0]["next_action"]
    assert plan["actions"][0]["validation_actions"][0]["endpoint"].endswith("/llm-replay-plan/latest")
    assert plan["actions"][0]["validation_actions"][0]["action_kind"] == "api_probe"


def test_team_builder_repair_plan_material_gap_has_validation_actions(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_generated_team",
            "verdict": "warning",
            "summary": "unit",
            "counts": {"total": 1, "advisory": 1},
            "findings": [
                {
                    "id": "team_builder.material.unconfirmed_read_group:health_report_writer",
                    "check_id": "team_builder.material.unconfirmed_read_group",
                    "level": "advisory",
                    "location": "node:health_report_writer",
                    "node_ids": ["health_report_writer"],
                    "material_ids": ["workspace.file.demo"],
                    "observation": "仍有 1 条读取线索未确认。",
                    "implication": "不能当作事实 material 读边。",
                }
            ],
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_repair_plan()
    action = plan["actions"][0]

    assert plan["verdict"] == "validation_gap"
    assert action["category"] == "validation_gap"
    assert action["policy_rule_id"] == "validation_gap_no_code_change"
    assert "读取线索消解计划" in action["next_action"]
    assert [item["action_kind"] for item in action["validation_actions"]] == ["api_probe", "controlled_replay"]
    assert action["validation_actions"][0]["endpoint"].endswith("/read-clue-resolution/latest")
    assert action["validation_actions"][1]["endpoint"].endswith("/material-gap-validation/latest")
    assert "不直接改 worker 代码" in action["validation_actions"][1]["safety"]


def test_team_builder_repair_plan_classifies_runtime_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_generated_team",
            "verdict": "fail",
            "summary": "unit",
            "counts": {"total": 1, "blocking": 1},
            "findings": [
                {
                    "id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "level": "blocking",
                    "location": "node:failing_worker",
                    "node_ids": ["failing_worker"],
                    "material_ids": ["unit.input.observation_request", "unit.material.failed_report"],
                    "observation": "业务 run smoke 执行失败：controlled failure",
                    "implication": "生成 team 的真实业务链路已经出现可复现失败，应进入 doctor/repair 阶段。",
                }
            ],
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_repair_plan()
    action = plan["actions"][0]

    assert plan["verdict"] == "repair_required"
    assert plan["counts"]["repair_required"] == 1
    assert plan["counts"]["auto_safe"] == 0
    assert action["category"] == "repair_required"
    assert action["policy_rule_id"] == "runtime_failure_patch_plan_only"
    assert action["automation_level"] == "patch_plan_only"
    assert action["auto_safe"] is False


def test_team_builder_repair_probe_captures_failure_and_blocks_autofix(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)

    report = catalogue._team_builder_repair_probe_report()

    assert report["available"] is True
    assert report["verdict"] == "pass"
    assert report["counts"]["captured_failures"] == 1
    assert report["counts"]["doctor_findings"] >= 1
    assert report["counts"]["repair_required"] >= 1
    assert report["counts"]["auto_safe"] == 0
    assert any(
        finding["check_id"] == "team_builder.worker_run_smoke.failed"
        and finding["level"] == "blocking"
        for finding in report["doctor_findings"]
    )
    assert report["repair_plan"]["verdict"] == "repair_required"
    assert report["repair_plan"]["actions"][0]["policy_rule_id"] == "runtime_failure_patch_plan_only"
    assert report["quality_gates"][1]["id"] == "worker_failure_captured"
    assert report["quality_gates"][1]["status"] == "pass"
    assert (tmp_path / report["source"]["repair_probe_material"]).is_file()


def test_team_builder_repair_dry_run_applies_scoped_patch_and_clears_findings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)

    report = catalogue._team_builder_repair_dry_run_report()

    assert report["available"] is True
    assert report["verdict"] == "pass"
    assert report["counts"]["before_failures"] == 1
    assert report["counts"]["before_findings"] >= 1
    assert report["counts"]["repair_required"] >= 1
    assert report["counts"]["patch_files"] == 1
    assert report["counts"]["after_failures"] == 0
    assert report["counts"]["after_findings"] == 0
    assert report["counts"]["fixed_workers"] == 1
    assert report["counts"]["auto_safe"] == 0
    assert report["patch_plan"]["dry_run_applied"] is True
    assert report["patch_plan"]["scope"] == "scratch_only"
    assert report["patch_plan"]["changed_files"] == ["workers/failure_probe_worker.py"]
    assert report["patch_plan"]["auto_safe"] is False
    assert "VerdictKind.FAIL" in report["patch_plan"]["diff"]
    assert "VerdictKind.PASS" in report["patch_plan"]["diff"]
    assert report["before"]["repair_actions"][0]["policy_rule_id"] == "runtime_failure_patch_plan_only"
    assert report["after"]["worker_run_smoke"]["status"] == "pass"
    assert all(gate["status"] == "pass" for gate in report["quality_gates"])
    assert (tmp_path / report["source"]["repair_dry_run_material"]).is_file()


def test_team_builder_repair_patch_candidates_locate_worker_source(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    package_dir = tmp_path / "_scratch" / "team_builder_test_reports" / "unit-run" / "unit_team"
    worker_path = package_dir / "workers" / "failing_worker.py"
    worker_path.parent.mkdir(parents=True)
    worker_path.write_text(
        "from omnicompany.protocol.anchor import VerdictKind\n\n"
        "class FailingWorker:\n"
        "    def run(self, input_data):\n"
        "        return {'kind': VerdictKind.FAIL, 'diagnosis': 'unit failure'}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "repair_required",
            "summary": "unit repair required",
            "counts": {"actions": 1, "repair_required": 1, "validation_gap": 0, "observe_only": 0, "auto_safe": 0},
            "actions": [
                {
                    "id": "repair_action:0",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "level": "blocking",
                    "location": "node:failing_worker",
                    "category": "repair_required",
                    "policy_rule_id": "runtime_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "observation": "unit worker failed",
                    "rationale": "runtime failure needs patch plan",
                    "next_action": "生成候选补丁计划。",
                    "validation_actions": [],
                    "node_ids": ["failing_worker"],
                    "material_ids": ["unit.input", "unit.output"],
                }
            ],
            "source": {"repair_plan_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_plan.json"},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "source": {"test_package_dir": str(package_dir.relative_to(tmp_path))},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_dry_run_report",
        lambda: {
            "available": True,
            "verdict": "pass",
            "summary": "dry-run pass",
            "counts": {"before_failures": 1, "patch_files": 1, "after_failures": 0, "after_findings": 0},
            "source": {"repair_dry_run_material": "_scratch/team_builder_repair_dry_run/unit/materials/team_repair_dry_run_report.json"},
        },
    )

    report = catalogue._team_builder_repair_patch_candidates_report()

    assert report["available"] is True
    assert report["verdict"] == "ready_for_manual_patch"
    assert report["counts"]["candidates"] == 1
    assert report["counts"]["source_located"] == 1
    assert report["counts"]["source_missing"] == 0
    assert report["counts"]["dry_run_verified"] == 1
    assert report["counts"]["auto_safe"] == 0
    assert report["counts"]["manual_required"] == 1
    candidate = report["candidates"][0]
    assert candidate["status"] == "source_located"
    assert candidate["worker_id"] == "failing_worker"
    assert candidate["policy_rule_id"] == "runtime_failure_patch_plan_only"
    assert candidate["proposed_patch"]["changed_files"] == [
        "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
    ]
    assert candidate["safety"]["auto_apply_allowed"] is False
    assert candidate["safety"]["requires_human_confirmation"] is True
    assert "GET /api/team-builder-materialization/doctor-findings/latest" in candidate["verification_commands"]
    assert report["source"]["repair_patch_candidates_material"].endswith("team_repair_patch_candidates.json")
    assert (tmp_path / report["source"]["repair_patch_candidates_material"]).is_file()


def test_team_builder_repair_patch_candidates_locate_contract_failure_sources(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    code_root = tmp_path / "_scratch" / "team_builder_real_material_validation" / "unit-run" / "code_package_files"
    (code_root / "workers").mkdir(parents=True)
    (code_root / "team.py").write_text("def build_team():\n    return None\n", encoding="utf-8")
    (code_root / "run.py").write_text("def build_bindings(input_dict=None):\n    return {}\n", encoding="utf-8")
    (code_root / "workers" / "observer_worker.py").write_text(
        "class ObserverWorker:\n    pass\n",
        encoding="utf-8",
    )
    contract_path = tmp_path / "tests" / "teams" / "unit_team" / "test_contract.py"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text("PIPELINE_NAME = 'unit-team'\n\ndef test_fail():\n    assert False\n", encoding="utf-8")
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "repair_required",
            "summary": "contract repair required",
            "counts": {"actions": 1, "repair_required": 1, "validation_gap": 0, "observe_only": 0, "auto_safe": 0},
            "actions": [
                {
                    "id": "repair_action:0",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "level": "blocking",
                    "location": "team:unit_team",
                    "category": "repair_required",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "observation": "contract 执行失败",
                    "rationale": "acceptance failed",
                    "next_action": "查看 contract execution 失败详情。",
                    "validation_actions": [],
                    "node_ids": [],
                    "material_ids": [],
                    "cross_refs": ["tests/teams/unit_team/test_contract.py", "contract_execution"],
                }
            ],
            "source": {"repair_plan_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_plan.json"},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "source": {"code_package_files": str(code_root.relative_to(tmp_path))},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_dry_run_report",
        lambda: {
            "available": True,
            "verdict": "pass",
            "summary": "dry-run pass",
            "counts": {"before_failures": 1, "patch_files": 1, "after_failures": 0, "after_findings": 0},
            "source": {"repair_dry_run_material": "_scratch/team_builder_repair_dry_run/unit/materials/team_repair_dry_run_report.json"},
        },
    )

    report = catalogue._team_builder_repair_patch_candidates_report()
    candidate = report["candidates"][0]

    assert report["verdict"] == "ready_for_manual_patch"
    assert candidate["status"] == "source_located"
    assert candidate["worker_id"] == ""
    assert candidate["contract_sources"][0]["path"] in {
        "tests\\teams\\unit_team\\test_contract.py",
        "tests/teams/unit_team/test_contract.py",
    }
    assert candidate["proposed_patch"]["scope"] == "generated_package_only"
    assert "code_package_files" in candidate["proposed_patch"]["changed_files"][0]
    assert candidate["verification_commands"][0] == "GET /api/team-builder-materialization/contract-execution/latest"


def test_team_builder_repair_apply_gate_requires_manual_review(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "candidate ready",
            "counts": {
                "actions": 1,
                "candidates": 1,
                "source_located": 1,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 1,
            },
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "category": "repair_required",
                    "policy_rule_id": "runtime_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "source located",
                    "observation": "unit failure",
                    "next_action": "review",
                    "source_candidates": [
                        {
                            "path": "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py",
                            "exists": True,
                            "material_ids": [],
                            "excerpt": "class FailingWorker",
                        }
                    ],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_worker_only",
                        "changed_files": [
                            "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                        ],
                        "diff": "",
                        "reason": "manual",
                    },
                    "verification_commands": [
                        "GET /api/team-builder-materialization/test-report/latest",
                        "GET /api/team-builder-materialization/doctor-findings/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "safety": {
                        "dry_run_first": True,
                        "requires_human_confirmation": True,
                        "auto_apply_allowed": False,
                        "reason": "manual only",
                    },
                }
            ],
            "dry_run_reference": {"verdict": "pass"},
            "source": {
                "repair_patch_candidates_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_patch_candidates.json"
            },
        },
    )

    report = catalogue._team_builder_repair_apply_gate_report()

    assert report["available"] is True
    assert report["verdict"] == "ready_for_human_review"
    assert report["counts"]["candidates"] == 1
    assert report["counts"]["source_located"] == 1
    assert report["counts"]["dry_run_verified"] == 1
    assert report["counts"]["manual_required"] == 1
    assert report["counts"]["auto_apply_allowed"] == 0
    assert report["counts"]["apply_ready"] == 1
    item = report["review_items"][0]
    assert item["status"] == "ready_for_human_review"
    assert item["worker_id"] == "failing_worker"
    assert item["changed_files"] == ["_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"]
    assert item["safety"]["auto_apply_allowed"] is False
    assert item["safety"]["requires_human_confirmation"] is True
    assert not item["blocked_reasons"]
    assert any("人工批准" in text for text in item["required_confirmations"])
    assert "GET /api/team-builder-materialization/closure/latest" in item["verification_commands"]
    assert report["quality_gates"][3]["id"] == "auto_apply_blocked"
    assert report["quality_gates"][3]["status"] == "pass"
    assert report["source"]["repair_apply_gate_material"].endswith("team_repair_apply_gate.json")
    assert (tmp_path / report["source"]["repair_apply_gate_material"]).is_file()


def test_team_builder_repair_apply_gate_preserves_contract_failure_scope(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "contract candidate ready",
            "counts": {
                "actions": 1,
                "candidates": 1,
                "source_located": 1,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 1,
            },
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "category": "repair_required",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "contract source located",
                    "observation": "contract failed",
                    "next_action": "review contract and generated package",
                    "source_candidates": [
                        {
                            "path": "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py",
                            "exists": True,
                            "material_ids": [],
                            "excerpt": "def build_team",
                        },
                        {
                            "path": "_scratch/team_builder_real_material_validation/unit-run/code_package_files/workers/observer_worker.py",
                            "exists": True,
                            "material_ids": [],
                            "excerpt": "class ObserverWorker",
                        },
                    ],
                    "contract_sources": [
                        {
                            "path": "tests/teams/unit_team/test_contract.py",
                            "exists": True,
                            "material_ids": [],
                            "excerpt": "def test_success_case",
                        }
                    ],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_package_only",
                        "changed_files": [
                            "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py",
                            "_scratch/team_builder_real_material_validation/unit-run/code_package_files/workers/observer_worker.py",
                        ],
                        "diff": "",
                        "reason": "manual",
                    },
                    "verification_commands": [
                        "GET /api/team-builder-materialization/contract-execution/latest",
                        "GET /api/team-builder-materialization/test-report/latest",
                        "GET /api/team-builder-materialization/doctor-findings/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "safety": {
                        "dry_run_first": True,
                        "requires_human_confirmation": True,
                        "auto_apply_allowed": False,
                        "reason": "manual only",
                    },
                }
            ],
            "dry_run_reference": {"verdict": "pass"},
            "source": {
                "repair_patch_candidates_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_patch_candidates.json"
            },
        },
    )

    report = catalogue._team_builder_repair_apply_gate_report()
    item = report["review_items"][0]

    assert report["verdict"] == "ready_for_human_review"
    assert item["check_id"] == "team_builder.contract.execution_failed"
    assert item["worker_id"] == ""
    assert item["contract_files"] == ["tests/teams/unit_team/test_contract.py"]
    assert item["source_files"] == [
        "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py",
        "_scratch/team_builder_real_material_validation/unit-run/code_package_files/workers/observer_worker.py",
    ]
    assert all(not path.replace("\\", "/").startswith("tests/teams/") for path in item["changed_files"])
    assert any("不能为了通过而修改 contract" in text for text in item["required_confirmations"])
    assert "GET /api/team-builder-materialization/contract-execution/latest" in item["verification_commands"]
    assert not item["blocked_reasons"]


def test_team_builder_repair_apply_gate_blocks_contract_as_patch_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "bad contract candidate",
            "counts": {
                "actions": 1,
                "candidates": 1,
                "source_located": 1,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 1,
            },
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "category": "repair_required",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "contract source located",
                    "observation": "contract failed",
                    "next_action": "review",
                    "source_candidates": [
                        {
                            "path": "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py",
                            "exists": True,
                            "material_ids": [],
                            "excerpt": "def build_team",
                        }
                    ],
                    "contract_sources": [
                        {
                            "path": "tests/teams/unit_team/test_contract.py",
                            "exists": True,
                            "material_ids": [],
                            "excerpt": "def test_success_case",
                        }
                    ],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_package_only",
                        "changed_files": ["tests/teams/unit_team/test_contract.py"],
                        "diff": "",
                        "reason": "bad target",
                    },
                    "verification_commands": [
                        "GET /api/team-builder-materialization/contract-execution/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "safety": {
                        "dry_run_first": True,
                        "requires_human_confirmation": True,
                        "auto_apply_allowed": False,
                        "reason": "manual only",
                    },
                }
            ],
            "dry_run_reference": {"verdict": "pass"},
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_apply_gate_report()
    item = report["review_items"][0]

    assert report["verdict"] == "blocked"
    assert item["status"] == "blocked"
    assert "contract 失败修复不能把 contract 文件列为补丁目标。" in item["blocked_reasons"]


def test_team_builder_repair_patch_diff_proposal_is_clean_without_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no candidates",
            "counts": {"candidates": 0},
            "quality_gates": [],
            "candidates": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "gate closed",
            "counts": {"review_items": 0},
            "quality_gates": [],
            "review_items": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_patch_diff_proposal_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["candidates"] == 0
    assert report["counts"]["diff_ready"] == 0
    assert report["source"]["repair_patch_diff_proposal_material"].endswith("team_repair_patch_diff_proposal.json")
    assert (tmp_path / report["source"]["repair_patch_diff_proposal_material"]).is_file()


def test_team_builder_repair_patch_diff_proposal_generates_deterministic_probe_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    worker_path = tmp_path / "_scratch" / "team_builder_test_reports" / "unit-run" / "unit_team" / "workers" / "failure_probe_worker.py"
    worker_path.parent.mkdir(parents=True)
    worker_text = (
        "from omnicompany.packages.services._core.types import VerdictKind\n\n"
        "def run(input_dict=None):\n"
        "    return {\n"
        "        'kind': VerdictKind.FAIL,\n"
        "        'probe': 'controlled_failure',\n"
        "        'diagnosis': 'controlled failure: repair probe worker returned FAIL on purpose',\n"
        "    }\n"
    )
    worker_path.write_text(worker_text, encoding="utf-8")
    changed_rel = str(worker_path.relative_to(tmp_path))
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "candidate ready",
            "counts": {"candidates": 1},
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.worker_run_smoke.failed:failure_probe_worker",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failure_probe_worker",
                    "category": "repair_required",
                    "policy_rule_id": "runtime_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "source located",
                    "observation": "controlled failure",
                    "next_action": "review",
                    "source_candidates": [{"path": changed_rel, "exists": True, "material_ids": [], "excerpt": "VerdictKind.FAIL"}],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_worker_only",
                        "changed_files": [changed_rel],
                        "diff": "",
                        "reason": "manual",
                    },
                    "verification_commands": [
                        "GET /api/team-builder-materialization/test-report/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "safety": {"dry_run_first": True, "requires_human_confirmation": True, "auto_apply_allowed": False, "reason": "manual only"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_human_review",
            "summary": "gate ready",
            "counts": {"review_items": 1},
            "quality_gates": [],
            "review_items": [
                {
                    "id": "repair_apply_gate:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_human_review",
                    "changed_files": [changed_rel],
                    "source_files": [changed_rel],
                    "contract_files": [],
                    "verification_commands": ["GET /api/team-builder-materialization/closure/latest"],
                    "safety": {"auto_apply_allowed": False, "requires_human_confirmation": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_patch_diff_proposal_report()
    proposal = report["proposals"][0]

    assert report["verdict"] == "diff_ready"
    assert report["counts"]["diff_ready"] == 1
    assert proposal["status"] == "diff_ready"
    assert proposal["diff_source"] == "deterministic_rule"
    assert "VerdictKind.FAIL" in proposal["diff"]
    assert "VerdictKind.PASS" in proposal["diff"]
    assert proposal["safety"]["writes_files"] is False
    assert worker_path.read_text(encoding="utf-8") == worker_text


def test_team_builder_repair_patch_diff_proposal_blocks_contract_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "bad target",
            "counts": {"candidates": 1},
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "category": "repair_required",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "bad target",
                    "observation": "contract failed",
                    "next_action": "review",
                    "source_candidates": [],
                    "contract_sources": [],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_package_only",
                        "changed_files": ["tests/teams/unit_team/test_contract.py"],
                        "diff": "",
                        "reason": "bad target",
                    },
                    "verification_commands": ["GET /api/team-builder-materialization/closure/latest"],
                    "safety": {"dry_run_first": True, "requires_human_confirmation": True, "auto_apply_allowed": False, "reason": "manual only"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "blocked",
            "summary": "gate blocked",
            "counts": {"review_items": 1},
            "quality_gates": [],
            "review_items": [
                {
                    "id": "repair_apply_gate:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "blocked",
                    "changed_files": ["tests/teams/unit_team/test_contract.py"],
                    "source_files": [],
                    "contract_files": ["tests/teams/unit_team/test_contract.py"],
                    "verification_commands": ["GET /api/team-builder-materialization/closure/latest"],
                    "blocked_reasons": ["contract target"],
                    "safety": {"auto_apply_allowed": False, "requires_human_confirmation": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_patch_diff_proposal_report()
    proposal = report["proposals"][0]

    assert report["verdict"] == "blocked"
    assert report["quality_gates"][1]["id"] == "target_scope_safe"
    assert report["quality_gates"][1]["status"] == "fail"
    assert proposal["status"] == "blocked"
    assert "contract failure 的补丁目标不能是 tests/teams 下的 contract 文件。" in proposal["missing_requirements"]


def test_team_builder_repair_approval_record_matches_current_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    diff_text = "diff --git a/workers/failing_worker.py b/workers/failing_worker.py\n"
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "changed_files": ["_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"],
                    "diff": diff_text,
                    "diff_source": "deterministic_rule",
                    "missing_requirements": [],
                }
            ],
            "source": {"repair_patch_diff_proposal_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_patch_diff_proposal.json"},
        },
    )

    report = catalogue._team_builder_record_repair_approval({
        "candidate_id": "repair_patch_candidate:0",
        "approved": True,
        "approved_by": "unit-test",
        "reason": "确认受控 diff 可以进入下一步执行门。",
        "diff_sha256": catalogue._team_builder_diff_sha256(diff_text),
    })

    item = report["approval_items"][0]
    assert report["verdict"] == "approved"
    assert report["counts"]["approved"] == 1
    assert item["approval_valid"] is True
    assert item["approved_by"] == "unit-test"
    assert (tmp_path / report["source"]["repair_approval_records_material"]).is_file()


def test_team_builder_repair_approval_detects_stale_diff_hash(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    diff_text = "diff --git a/current.py b/current.py\n"
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "changed_files": ["_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"],
                    "diff": diff_text,
                    "diff_source": "deterministic_rule",
                    "missing_requirements": [],
                }
            ],
            "source": {},
        },
    )
    catalogue._team_builder_write_repair_approval_records("unit-run", [
        {
            "candidate_id": "repair_patch_candidate:0",
            "approved": True,
            "approved_by": "unit-test",
            "approved_at": "2026-05-18T00:00:00+00:00",
            "reason": "old diff",
            "diff_sha256": catalogue._team_builder_diff_sha256("old diff"),
        }
    ])

    report = catalogue._team_builder_repair_approval_report()
    item = report["approval_items"][0]

    assert report["verdict"] == "stale_or_mismatch"
    assert report["counts"]["stale_or_mismatch"] == 1
    assert item["approval_valid"] is False
    assert item["status"] == "stale_or_mismatch"


def test_team_builder_repair_execution_readiness_is_clean_without_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no candidates",
            "counts": {
                "actions": 0,
                "candidates": 0,
                "source_located": 0,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 0,
            },
            "quality_gates": [],
            "candidates": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "gate closed",
            "counts": {
                "candidates": 0,
                "source_located": 0,
                "dry_run_verified": 1,
                "manual_required": 0,
                "auto_apply_allowed": 0,
                "review_items": 0,
                "apply_ready": 0,
            },
            "quality_gates": [],
            "review_items": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_execution_readiness_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["candidates"] == 0
    assert report["counts"]["execution_ready"] == 0
    assert report["quality_gates"][4]["id"] == "auto_apply_blocked"
    assert report["source"]["repair_execution_readiness_material"].endswith("team_repair_execution_readiness.json")
    assert (tmp_path / report["source"]["repair_execution_readiness_material"]).is_file()


def test_team_builder_repair_execution_readiness_waits_for_diff_and_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "candidate ready",
            "counts": {
                "actions": 1,
                "candidates": 1,
                "source_located": 1,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 1,
            },
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "category": "repair_required",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "ready",
                    "observation": "contract failed",
                    "next_action": "review",
                    "source_candidates": [],
                    "contract_sources": [],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_package_only",
                        "changed_files": [
                            "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py"
                        ],
                        "diff": "",
                        "reason": "manual",
                    },
                    "verification_commands": [
                        "GET /api/team-builder-materialization/contract-execution/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "safety": {
                        "dry_run_first": True,
                        "requires_human_confirmation": True,
                        "auto_apply_allowed": False,
                        "reason": "manual only",
                    },
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_human_review",
            "summary": "gate ready",
            "counts": {
                "candidates": 1,
                "source_located": 1,
                "dry_run_verified": 1,
                "manual_required": 1,
                "auto_apply_allowed": 0,
                "review_items": 1,
                "apply_ready": 1,
            },
            "quality_gates": [],
            "review_items": [
                {
                    "id": "repair_apply_gate:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_human_review",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "changed_files": [
                        "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py"
                    ],
                    "source_files": [
                        "_scratch/team_builder_real_material_validation/unit-run/code_package_files/team.py"
                    ],
                    "contract_files": ["tests/teams/unit_team/test_contract.py"],
                    "required_confirmations": [],
                    "verification_commands": [
                        "GET /api/team-builder-materialization/contract-execution/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "apply_modes": [],
                    "blocked_reasons": [],
                    "safety": {"auto_apply_allowed": False, "requires_human_confirmation": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_execution_readiness_report()
    item = report["execution_items"][0]

    assert report["verdict"] == "waiting_for_patch_diff"
    assert report["counts"]["review_ready"] == 1
    assert report["counts"]["diff_ready"] == 0
    assert report["counts"]["approval_recorded"] == 0
    assert item["status"] == "waiting_for_patch_diff"
    assert "候选补丁还没有实际 diff，不能进入真实应用。" in item["missing_requirements"]
    assert "尚未记录显式人工批准。" in item["missing_requirements"]
    assert report["quality_gates"][1]["id"] == "patch_diff_present"
    assert report["quality_gates"][1]["status"] == "warning"


def test_team_builder_repair_execution_readiness_uses_diff_proposal(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    candidate_payload = {
        "available": True,
        "run_id": "unit-run",
        "team_name": "unit_team",
        "verdict": "ready_for_manual_patch",
        "summary": "candidate ready",
        "counts": {
            "actions": 1,
            "candidates": 1,
            "source_located": 1,
            "source_missing": 0,
            "dry_run_verified": 1,
            "auto_safe": 0,
            "manual_required": 1,
        },
        "quality_gates": [],
        "candidates": [
            {
                "id": "repair_patch_candidate:0",
                "status": "source_located",
                "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                "check_id": "team_builder.worker_run_smoke.failed",
                "worker_id": "failing_worker",
                "category": "repair_required",
                "policy_rule_id": "runtime_failure_patch_plan_only",
                "automation_level": "patch_plan_only",
                "auto_safe": False,
                "summary": "ready",
                "observation": "worker failed",
                "next_action": "review",
                "source_candidates": [],
                "proposed_patch": {
                    "mode": "manual_or_ai_generated",
                    "scope": "generated_worker_only",
                    "changed_files": [
                        "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                    ],
                    "diff": "",
                    "reason": "manual",
                },
                "verification_commands": [
                    "GET /api/team-builder-materialization/test-report/latest",
                    "GET /api/team-builder-materialization/closure/latest",
                ],
                "safety": {
                    "dry_run_first": True,
                    "requires_human_confirmation": True,
                    "auto_apply_allowed": False,
                    "reason": "manual only",
                },
            }
        ],
        "source": {},
    }
    apply_gate_payload = {
        "available": True,
        "run_id": "unit-run",
        "team_name": "unit_team",
        "verdict": "ready_for_human_review",
        "summary": "gate ready",
        "counts": {
            "candidates": 1,
            "source_located": 1,
            "dry_run_verified": 1,
            "manual_required": 1,
            "auto_apply_allowed": 0,
            "review_items": 1,
            "apply_ready": 1,
        },
        "quality_gates": [],
        "review_items": [
            {
                "id": "repair_apply_gate:0",
                "candidate_id": "repair_patch_candidate:0",
                "status": "ready_for_human_review",
                "check_id": "team_builder.worker_run_smoke.failed",
                "worker_id": "failing_worker",
                "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                "policy_rule_id": "runtime_failure_patch_plan_only",
                "changed_files": [
                    "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                ],
                "source_files": [
                    "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                ],
                "contract_files": [],
                "required_confirmations": [],
                "verification_commands": [
                    "GET /api/team-builder-materialization/test-report/latest",
                    "GET /api/team-builder-materialization/closure/latest",
                ],
                "apply_modes": [],
                "blocked_reasons": [],
                "safety": {"auto_apply_allowed": False, "requires_human_confirmation": True, "reason": "manual"},
            }
        ],
        "source": {},
    }
    monkeypatch.setattr(catalogue, "_team_builder_repair_patch_candidates_report", lambda: candidate_payload)
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_gate_report", lambda: apply_gate_payload)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "changed_files": [
                        "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                    ],
                    "diff": "diff --git a/failing_worker.py b/failing_worker.py\n",
                    "diff_source": "deterministic_rule",
                    "missing_requirements": [],
                }
            ],
            "source": {"repair_patch_diff_proposal_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_patch_diff_proposal.json"},
        },
    )

    report = catalogue._team_builder_repair_execution_readiness_report()
    item = report["execution_items"][0]

    assert report["verdict"] == "awaiting_explicit_approval"
    assert report["counts"]["diff_ready"] == 1
    assert report["counts"]["approval_recorded"] == 0
    assert item["has_diff"] is True
    assert item["diff_source"] == "deterministic_rule"
    assert "候选补丁还没有实际 diff，不能进入真实应用。" not in item["missing_requirements"]
    assert "尚未记录显式人工批准。" in item["missing_requirements"]


def test_team_builder_repair_execution_readiness_uses_approval_material(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    diff_text = "diff --git a/failing_worker.py b/failing_worker.py\n"
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "candidate ready",
            "counts": {
                "actions": 1,
                "candidates": 1,
                "source_located": 1,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 1,
            },
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "category": "repair_required",
                    "policy_rule_id": "runtime_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "ready",
                    "observation": "worker failed",
                    "next_action": "review",
                    "source_candidates": [],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_worker_only",
                        "changed_files": [
                            "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                        ],
                        "diff": "",
                        "reason": "manual",
                    },
                    "verification_commands": [
                        "GET /api/team-builder-materialization/test-report/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "safety": {
                        "dry_run_first": True,
                        "requires_human_confirmation": True,
                        "auto_apply_allowed": False,
                        "reason": "manual only",
                    },
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_human_review",
            "summary": "gate ready",
            "counts": {
                "candidates": 1,
                "source_located": 1,
                "dry_run_verified": 1,
                "manual_required": 1,
                "auto_apply_allowed": 0,
                "review_items": 1,
                "apply_ready": 1,
            },
            "quality_gates": [],
            "review_items": [
                {
                    "id": "repair_apply_gate:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_human_review",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "policy_rule_id": "runtime_failure_patch_plan_only",
                    "changed_files": [
                        "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                    ],
                    "source_files": [
                        "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                    ],
                    "contract_files": [],
                    "required_confirmations": [],
                    "verification_commands": [
                        "GET /api/team-builder-materialization/test-report/latest",
                        "GET /api/team-builder-materialization/closure/latest",
                    ],
                    "apply_modes": [],
                    "blocked_reasons": [],
                    "safety": {"auto_apply_allowed": False, "requires_human_confirmation": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "changed_files": [
                        "_scratch/team_builder_test_reports/unit-run/unit_team/workers/failing_worker.py"
                    ],
                    "diff": diff_text,
                    "diff_source": "deterministic_rule",
                    "missing_requirements": [],
                }
            ],
            "source": {"repair_patch_diff_proposal_material": "_scratch/team_builder_real_material_validation/unit-run/materials/team_repair_patch_diff_proposal.json"},
        },
    )
    catalogue._team_builder_write_repair_approval_records("unit-run", [
        {
            "candidate_id": "repair_patch_candidate:0",
            "approved": True,
            "approved_by": "unit-test",
            "approved_at": "2026-05-18T00:00:00+00:00",
            "reason": "approve deterministic diff",
            "diff_sha256": catalogue._team_builder_diff_sha256(diff_text),
        }
    ])

    report = catalogue._team_builder_repair_execution_readiness_report()
    item = report["execution_items"][0]

    assert report["verdict"] == "ready_for_explicit_apply"
    assert report["counts"]["diff_ready"] == 1
    assert report["counts"]["approval_recorded"] == 1
    assert report["counts"]["execution_ready"] == 1
    assert item["approval_recorded"] is True
    assert item["approval_status"] == "approved"
    assert not item["missing_requirements"]


def test_team_builder_repair_execution_readiness_blocks_contract_target(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_manual_patch",
            "summary": "bad target",
            "counts": {
                "actions": 1,
                "candidates": 1,
                "source_located": 1,
                "source_missing": 0,
                "dry_run_verified": 1,
                "auto_safe": 0,
                "manual_required": 1,
            },
            "quality_gates": [],
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "status": "source_located",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "category": "repair_required",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "automation_level": "patch_plan_only",
                    "auto_safe": False,
                    "summary": "bad target",
                    "observation": "contract failed",
                    "next_action": "review",
                    "source_candidates": [],
                    "contract_sources": [],
                    "proposed_patch": {
                        "mode": "manual_or_ai_generated",
                        "scope": "generated_package_only",
                        "changed_files": ["tests/teams/unit_team/test_contract.py"],
                        "diff": "diff --git a/tests/teams/unit_team/test_contract.py b/tests/teams/unit_team/test_contract.py\n",
                        "reason": "bad target",
                    },
                    "verification_commands": ["GET /api/team-builder-materialization/closure/latest"],
                    "approval": {"approved": True},
                    "safety": {
                        "dry_run_first": True,
                        "requires_human_confirmation": True,
                        "auto_apply_allowed": False,
                        "reason": "manual only",
                    },
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_gate_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_human_review",
            "summary": "gate ready",
            "counts": {
                "candidates": 1,
                "source_located": 1,
                "dry_run_verified": 1,
                "manual_required": 1,
                "auto_apply_allowed": 0,
                "review_items": 1,
                "apply_ready": 1,
            },
            "quality_gates": [],
            "review_items": [
                {
                    "id": "repair_apply_gate:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_human_review",
                    "check_id": "team_builder.contract.execution_failed",
                    "worker_id": "",
                    "finding_id": "team_builder.contract.execution_failed:unit_team",
                    "policy_rule_id": "contract_failure_patch_plan_only",
                    "changed_files": ["tests/teams/unit_team/test_contract.py"],
                    "source_files": [],
                    "contract_files": ["tests/teams/unit_team/test_contract.py"],
                    "required_confirmations": [],
                    "verification_commands": ["GET /api/team-builder-materialization/closure/latest"],
                    "apply_modes": [],
                    "blocked_reasons": [],
                    "safety": {"auto_apply_allowed": False, "requires_human_confirmation": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_execution_readiness_report()
    item = report["execution_items"][0]

    assert report["verdict"] == "blocked"
    assert report["quality_gates"][2]["id"] == "target_scope_safe"
    assert report["quality_gates"][2]["status"] == "fail"
    assert item["status"] == "blocked"
    assert "contract failure 的补丁目标不能是 tests/teams 下的 contract 文件。" in item["missing_requirements"]


def test_team_builder_repair_apply_preview_is_clean_without_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_execution_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no execution candidates",
            "counts": {
                "candidates": 0,
                "review_ready": 0,
                "diff_ready": 0,
                "approval_recorded": 0,
                "execution_ready": 0,
                "blocked": 0,
            },
            "quality_gates": [],
            "execution_items": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no diff",
            "counts": {"candidates": 0, "diff_ready": 0, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_apply_preview_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["items"] == 0
    assert report["counts"]["real_writes"] == 0
    assert report["quality_gates"][1]["id"] == "scratch_only"
    assert report["source"]["repair_apply_preview_material"].endswith("team_repair_apply_preview.json")
    assert (tmp_path / report["source"]["repair_apply_preview_material"]).is_file()


def test_team_builder_repair_apply_preview_blocks_unready_candidate(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_execution_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "awaiting_explicit_approval",
            "summary": "approval missing",
            "counts": {
                "candidates": 1,
                "review_ready": 1,
                "diff_ready": 1,
                "approval_recorded": 0,
                "execution_ready": 0,
                "blocked": 0,
            },
            "quality_gates": [],
            "execution_items": [
                {
                    "id": "repair_execution_readiness:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "awaiting_explicit_approval",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "changed_files": ["src/generated/failing_worker.py"],
                    "contract_files": [],
                    "review_item_status": "ready_for_human_review",
                    "has_diff": True,
                    "approval_recorded": False,
                    "missing_requirements": ["尚未记录显式人工批准。"],
                    "verification_commands": ["GET /api/team-builder-materialization/test-report/latest"],
                    "safety": {"auto_apply_allowed": False, "requires_explicit_approval": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "changed_files": ["src/generated/failing_worker.py"],
                    "diff": "diff --git a/src/generated/failing_worker.py b/src/generated/failing_worker.py\n",
                    "diff_source": "unit",
                    "missing_requirements": [],
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_apply_preview_report()
    item = report["preview_items"][0]

    assert report["verdict"] == "blocked"
    assert report["counts"]["preview_ready"] == 0
    assert item["status"] == "blocked"
    assert "执行就绪检查尚未放行该候选。" in item["blocked_reasons"]
    assert report["counts"]["files_written"] == 0
    assert report["counts"]["real_writes"] == 0


def test_team_builder_repair_apply_preview_writes_scratch_before_after_for_ready_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    source_path = tmp_path / rel_path
    before = "result = 'fail'\nreason = 'controlled_failure'\n"
    after = "result = 'pass'\nreason = 'repaired_success'\n"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(before, encoding="utf-8")
    diff_text = catalogue._team_builder_diff_text(rel_path, before, after)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_execution_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_explicit_apply",
            "summary": "ready",
            "counts": {
                "candidates": 1,
                "review_ready": 1,
                "diff_ready": 1,
                "approval_recorded": 1,
                "execution_ready": 1,
                "blocked": 0,
            },
            "quality_gates": [],
            "execution_items": [
                {
                    "id": "repair_execution_readiness:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_explicit_apply",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "failing_worker",
                    "finding_id": "team_builder.worker_run_smoke.failed:failing_worker",
                    "changed_files": [rel_path],
                    "contract_files": [],
                    "review_item_status": "ready_for_human_review",
                    "has_diff": True,
                    "approval_recorded": True,
                    "missing_requirements": [],
                    "verification_commands": ["GET /api/team-builder-materialization/test-report/latest"],
                    "safety": {"auto_apply_allowed": False, "requires_explicit_approval": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "changed_files": [rel_path],
                    "diff": diff_text,
                    "diff_source": "unit",
                    "missing_requirements": [],
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_apply_preview_report()
    item = report["preview_items"][0]

    assert report["verdict"] == "preview_ready"
    assert report["counts"]["preview_ready"] == 1
    assert report["counts"]["files_written"] == 2
    assert report["counts"]["real_writes"] == 0
    assert item["status"] == "preview_ready"
    assert item["safety"]["writes_real_files"] is False
    assert source_path.read_text(encoding="utf-8") == before
    assert (tmp_path / item["before_preview_files"][0]).read_text(encoding="utf-8") == before
    assert (tmp_path / item["after_preview_files"][0]).read_text(encoding="utf-8") == after


def test_team_builder_repair_apply_preview_expands_multi_file_to_scratch_file_set(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_a = "src/generated/workers/report_writer.py"
    rel_b = "src/generated/formats.py"
    before_a = "status = 'fail'\nreason = 'missing_summary'\n"
    after_a = "status = 'pass'\nreason = 'summary_written'\n"
    before_b = "FORMAT = 'old'\n"
    after_b = "FORMAT = 'new'\n"
    for rel_path, content in [(rel_a, before_a), (rel_b, before_b)]:
        source_path = tmp_path / rel_path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(content, encoding="utf-8")
    diff_text = (
        catalogue._team_builder_diff_text(rel_a, before_a, after_a)
        + catalogue._team_builder_diff_text(rel_b, before_b, after_b)
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_execution_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_explicit_apply",
            "summary": "ready",
            "counts": {
                "candidates": 1,
                "review_ready": 1,
                "diff_ready": 1,
                "approval_recorded": 1,
                "execution_ready": 1,
                "blocked": 0,
            },
            "quality_gates": [],
            "execution_items": [
                {
                    "id": "repair_execution_readiness:0",
                    "candidate_id": "repair_patch_candidate:multi",
                    "status": "ready_for_explicit_apply",
                    "check_id": "team_builder.worker_run_smoke.failed",
                    "worker_id": "report_writer",
                    "finding_id": "team_builder.worker_run_smoke.failed:report_writer",
                    "changed_files": [rel_a, rel_b],
                    "contract_files": [],
                    "review_item_status": "ready_for_human_review",
                    "has_diff": True,
                    "approval_recorded": True,
                    "missing_requirements": [],
                    "verification_commands": ["GET /api/team-builder-materialization/test-report/latest"],
                    "safety": {"auto_apply_allowed": False, "requires_explicit_approval": True, "reason": "manual"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:multi",
                    "status": "diff_ready",
                    "changed_files": [rel_a, rel_b],
                    "diff": diff_text,
                    "diff_source": "unit",
                    "missing_requirements": [],
                }
            ],
            "source": {},
        },
    )

    preview = catalogue._team_builder_repair_apply_preview_report()
    item = preview["preview_items"][0]

    assert preview["verdict"] == "preview_ready"
    assert preview["counts"]["preview_ready"] == 1
    assert preview["counts"]["multi_file_preview_ready"] == 1
    assert preview["counts"]["files_previewed"] == 2
    assert preview["counts"]["files_written"] == 4
    assert preview["counts"]["real_writes"] == 0
    assert item["multi_file"] is True
    assert len(item["file_previews"]) == 2
    assert (tmp_path / item["before_preview_files"][0]).read_text(encoding="utf-8") == before_a
    assert (tmp_path / item["after_preview_files"][0]).read_text(encoding="utf-8") == after_a
    assert (tmp_path / item["before_preview_files"][1]).read_text(encoding="utf-8") == before_b
    assert (tmp_path / item["after_preview_files"][1]).read_text(encoding="utf-8") == after_b
    assert (tmp_path / rel_a).read_text(encoding="utf-8") == before_a
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == before_b

    execution = catalogue._team_builder_repair_apply_execution_report()
    execution_item = execution["apply_items"][0]

    assert execution["verdict"] == "ready_for_explicit_apply"
    assert execution["counts"]["file_set_ready"] == 1
    assert execution["counts"]["real_writes"] == 0
    assert execution_item["status"] == "ready_for_explicit_apply"
    assert execution_item["file_set"] is True


def test_team_builder_file_set_apply_and_rollback_write_all_files_with_extra_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_a = "src/generated/workers/report_writer.py"
    rel_b = "src/generated/formats.py"
    before_a = "status = 'fail'\nreason = 'missing_summary'\n"
    after_a = "status = 'pass'\nreason = 'summary_written'\n"
    before_b = "FORMAT = 'old'\n"
    after_b = "FORMAT = 'new'\n"
    for rel_path, content in [(rel_a, before_a), (rel_b, before_b)]:
        source_path = tmp_path / rel_path
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_text(content, encoding="utf-8")
    diff_text = (
        catalogue._team_builder_diff_text(rel_a, before_a, after_a)
        + catalogue._team_builder_diff_text(rel_b, before_b, after_b)
    )
    diff_sha = catalogue._team_builder_diff_sha256(diff_text)
    preview_root = tmp_path / "_scratch" / "team_builder_repair_apply_preview" / "unit-run" / "repair_patch_candidate_multi"
    preview_paths = []
    for rel_path, before, after in [(rel_a, before_a, after_a), (rel_b, before_b, after_b)]:
        before_preview = preview_root / "before" / rel_path
        after_preview = preview_root / "after" / rel_path
        before_preview.parent.mkdir(parents=True, exist_ok=True)
        after_preview.parent.mkdir(parents=True, exist_ok=True)
        before_preview.write_text(before, encoding="utf-8")
        after_preview.write_text(after, encoding="utf-8")
        preview_paths.append((before_preview, after_preview))

    file_previews = [
        {
            "changed_file": rel_a,
            "before_preview_file": str(preview_paths[0][0].relative_to(tmp_path)),
            "after_preview_file": str(preview_paths[0][1].relative_to(tmp_path)),
            "before_sha256": catalogue._team_builder_file_sha256(preview_paths[0][0]),
            "after_sha256": catalogue._team_builder_file_sha256(preview_paths[0][1]),
            "diff_sha256": catalogue._team_builder_diff_sha256(catalogue._team_builder_diff_text(rel_a, before_a, after_a)),
        },
        {
            "changed_file": rel_b,
            "before_preview_file": str(preview_paths[1][0].relative_to(tmp_path)),
            "after_preview_file": str(preview_paths[1][1].relative_to(tmp_path)),
            "before_sha256": catalogue._team_builder_file_sha256(preview_paths[1][0]),
            "after_sha256": catalogue._team_builder_file_sha256(preview_paths[1][1]),
            "diff_sha256": catalogue._team_builder_diff_sha256(catalogue._team_builder_diff_text(rel_b, before_b, after_b)),
        },
    ]
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_preview_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "preview_ready",
            "summary": "file set preview ready",
            "counts": {"items": 1, "preview_ready": 1, "blocked": 0, "files_written": 4, "files_previewed": 2, "multi_file_preview_ready": 1, "real_writes": 0},
            "quality_gates": [],
            "preview_items": [
                {
                    "id": "repair_apply_preview:0",
                    "candidate_id": "repair_patch_candidate:multi",
                    "status": "preview_ready",
                    "changed_files": [rel_a, rel_b],
                    "file_count": 2,
                    "multi_file": True,
                    "before_preview_files": [item["before_preview_file"] for item in file_previews],
                    "after_preview_files": [item["after_preview_file"] for item in file_previews],
                    "file_previews": file_previews,
                    "blocked_reasons": [],
                    "diff_sha256": diff_sha,
                    "safety": {"scope": "scratch_only", "writes_real_files": False, "requires_final_apply_confirmation": True, "reason": "preview only"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:multi",
                    "status": "diff_ready",
                    "changed_files": [rel_a, rel_b],
                    "diff": diff_text,
                    "diff_source": "unit",
                    "missing_requirements": [],
                }
            ],
            "source": {},
        },
    )

    with pytest.raises(catalogue.HTTPException) as excinfo:
        catalogue._team_builder_execute_repair_apply({
            "candidate_id": "repair_patch_candidate:multi",
            "apply": True,
            "diff_sha256": diff_sha,
            "applied_by": "unit-test",
            "reason": "missing file set token",
            "confirmations": ["confirm_real_file_write"],
        })
    assert excinfo.value.status_code == 400
    assert (tmp_path / rel_a).read_text(encoding="utf-8") == before_a
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == before_b

    apply_report = catalogue._team_builder_execute_repair_apply({
        "candidate_id": "repair_patch_candidate:multi",
        "apply": True,
        "diff_sha256": diff_sha,
        "applied_by": "unit-test",
        "reason": "apply file set",
        "confirmations": ["confirm_real_file_write", "confirm_file_set_write"],
    })
    apply_item = apply_report["apply_items"][0]

    assert (tmp_path / rel_a).read_text(encoding="utf-8") == after_a
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == after_b
    assert apply_report["verdict"] == "applied"
    assert apply_report["counts"]["real_writes"] == 2
    assert apply_report["counts"]["file_set_applied"] == 1
    assert apply_item["file_set"] is True
    assert len(apply_item["file_records"]) == 2
    assert apply_report["records"][0]["real_writes"] == 2
    assert len(apply_report["records"][0]["file_records"]) == 2

    rollback_readiness = catalogue._team_builder_repair_rollback_readiness_report()
    rollback_item = rollback_readiness["rollback_items"][0]

    assert rollback_readiness["verdict"] == "ready_for_explicit_rollback"
    assert rollback_item["file_set"] is True
    assert len(rollback_item["file_records"]) == 2

    rollback_report = catalogue._team_builder_execute_repair_rollback({
        "candidate_id": "repair_patch_candidate:multi",
        "rollback": True,
        "before_sha256": rollback_item["before_sha256"],
        "after_sha256": rollback_item["after_sha256"],
        "rolled_back_by": "unit-test",
        "reason": "rollback file set",
        "confirmations": ["confirm_real_file_rollback", "confirm_file_set_rollback"],
    })

    assert (tmp_path / rel_a).read_text(encoding="utf-8") == before_a
    assert (tmp_path / rel_b).read_text(encoding="utf-8") == before_b
    assert rollback_report["verdict"] == "rolled_back"
    assert rollback_report["counts"]["real_writes"] == 2
    assert rollback_report["counts"]["file_set_rolled_back"] == 1
    assert len(rollback_report["records"][0]["file_records"]) == 2


def test_team_builder_repair_apply_execution_report_is_clean_without_preview_candidates(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_preview_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no preview",
            "counts": {"items": 0, "preview_ready": 0, "blocked": 0, "files_written": 0, "real_writes": 0},
            "quality_gates": [],
            "preview_items": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_apply_execution_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["items"] == 0
    assert report["counts"]["real_writes"] == 0
    assert report["quality_gates"][1]["id"] == "explicit_execute_only"
    assert report["source"]["repair_apply_execution_report_material"].endswith("team_repair_apply_execution_report.json")
    assert (tmp_path / report["source"]["repair_apply_execution_report_material"]).is_file()


def test_team_builder_execute_repair_apply_blocks_without_preview_ready(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    source_path = tmp_path / rel_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("result = 'fail'\n", encoding="utf-8")
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_preview_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "blocked",
            "summary": "blocked",
            "counts": {"items": 1, "preview_ready": 0, "blocked": 1, "files_written": 0, "real_writes": 0},
            "quality_gates": [],
            "preview_items": [
                {
                    "id": "repair_apply_preview:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "blocked",
                    "changed_files": [rel_path],
                    "before_preview_files": [],
                    "after_preview_files": [],
                    "blocked_reasons": ["执行就绪检查尚未放行该候选。"],
                    "diff_sha256": "abc",
                    "safety": {"scope": "scratch_only", "writes_real_files": False, "requires_final_apply_confirmation": True, "reason": "preview only"},
                }
            ],
            "source": {},
        },
    )

    with pytest.raises(catalogue.HTTPException) as excinfo:
        catalogue._team_builder_execute_repair_apply({
            "candidate_id": "repair_patch_candidate:0",
            "apply": True,
            "diff_sha256": "abc",
            "applied_by": "unit-test",
            "reason": "test blocked preview",
            "confirmations": ["confirm_real_file_write"],
        })

    assert excinfo.value.status_code == 409
    assert source_path.read_text(encoding="utf-8") == "result = 'fail'\n"


def test_team_builder_execute_repair_apply_writes_real_file_after_explicit_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    source_path = tmp_path / rel_path
    before = "result = 'fail'\nreason = 'controlled_failure'\n"
    after = "result = 'pass'\nreason = 'repaired_success'\n"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text(before, encoding="utf-8")
    diff_text = catalogue._team_builder_diff_text(rel_path, before, after)
    diff_sha = catalogue._team_builder_diff_sha256(diff_text)
    preview_before = tmp_path / "_scratch" / "team_builder_repair_apply_preview" / "unit-run" / "repair_patch_candidate_0" / "before" / rel_path
    preview_after = tmp_path / "_scratch" / "team_builder_repair_apply_preview" / "unit-run" / "repair_patch_candidate_0" / "after" / rel_path
    preview_before.parent.mkdir(parents=True, exist_ok=True)
    preview_after.parent.mkdir(parents=True, exist_ok=True)
    preview_before.write_text(before, encoding="utf-8")
    preview_after.write_text(after, encoding="utf-8")
    preview_before_rel = str(preview_before.relative_to(tmp_path))
    preview_after_rel = str(preview_after.relative_to(tmp_path))
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_preview_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "preview_ready",
            "summary": "preview ready",
            "counts": {"items": 1, "preview_ready": 1, "blocked": 0, "files_written": 2, "real_writes": 0},
            "quality_gates": [],
            "preview_items": [
                {
                    "id": "repair_apply_preview:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "preview_ready",
                    "changed_files": [rel_path],
                    "before_preview_files": [preview_before_rel],
                    "after_preview_files": [preview_after_rel],
                    "blocked_reasons": [],
                    "diff_sha256": diff_sha,
                    "safety": {"scope": "scratch_only", "writes_real_files": False, "requires_final_apply_confirmation": True, "reason": "preview only"},
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_diff_proposal_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "diff_ready",
            "summary": "diff ready",
            "counts": {"candidates": 1, "diff_ready": 1, "needs_ai_or_human_diff": 0, "blocked": 0, "unsafe_targets": 0},
            "quality_gates": [],
            "proposals": [
                {
                    "id": "repair_patch_diff_proposal:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "diff_ready",
                    "changed_files": [rel_path],
                    "diff": diff_text,
                    "diff_source": "unit",
                    "missing_requirements": [],
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_execute_repair_apply({
        "candidate_id": "repair_patch_candidate:0",
        "apply": True,
        "diff_sha256": diff_sha,
        "applied_by": "unit-test",
        "reason": "apply explicit tested diff",
        "confirmations": ["confirm_real_file_write"],
    })
    item = report["apply_items"][0]

    assert source_path.read_text(encoding="utf-8") == after
    assert report["verdict"] == "applied"
    assert report["counts"]["applied"] == 1
    assert report["counts"]["real_writes"] == 1
    assert item["status"] == "applied"
    assert item["applied_by"] == "unit-test"
    assert report["records"][0]["changed_file"] == rel_path
    assert report["records"][0]["before_preview_file"] == preview_before_rel
    assert report["records"][0]["real_writes"] == 1
    assert (tmp_path / report["source"]["repair_apply_execution_records_material"]).is_file()


def test_team_builder_repair_post_apply_verification_is_clean_without_applied_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no apply",
            "counts": {"items": 0, "preview_ready": 0, "applied": 0, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 0},
            "quality_gates": [],
            "apply_items": [],
            "records": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_post_apply_verification_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["applied"] == 0
    assert report["counts"]["pending"] == 0
    assert report["source"]["repair_post_apply_verification_material"].endswith("team_repair_post_apply_verification_result.json")
    assert (tmp_path / report["source"]["repair_post_apply_verification_material"]).is_file()


def test_team_builder_repair_post_apply_verification_waits_for_rerun_after_apply(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "preview_ready": 0, "applied": 1, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 1},
            "quality_gates": [],
            "apply_items": [
                {
                    "id": "repair_apply_execution:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "applied",
                    "summary": "applied",
                    "changed_files": ["src/generated/failing_worker.py"],
                    "diff_sha256": "abc",
                    "real_writes": 1,
                    "blocked_reasons": [],
                }
            ],
            "records": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_post_apply_verification_report()
    item = report["verification_items"][0]

    assert report["verdict"] == "awaiting_verification"
    assert report["counts"]["applied"] == 1
    assert report["counts"]["pending"] == 1
    assert item["status"] == "pending_verification"
    assert "POST /api/team-builder-materialization/repair-post-apply-verification/execute" in item["required_commands"]


def test_team_builder_execute_repair_post_apply_verification_passes_when_rerun_is_clean(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "preview_ready": 0, "applied": 1, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 1},
            "quality_gates": [],
            "apply_items": [
                {
                    "id": "repair_apply_execution:0",
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "applied",
                    "summary": "applied",
                    "changed_files": ["src/generated/failing_worker.py"],
                    "diff_sha256": "abc",
                    "real_writes": 1,
                    "blocked_reasons": [],
                }
            ],
            "records": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_execute_contracts_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "contract pass",
            "counts": {"executed_contracts": 1, "failed_contracts": 0},
            "contracts": [{"path": "tests/teams/unit_team/test_contract.py", "status": "pass"}],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "test pass",
            "counts": {},
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "doctor clean",
            "counts": {"total": 0, "blocking": 0},
            "findings": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "repair clean",
            "counts": {"repair_required": 0},
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_closure_status",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "closure pass",
            "missing": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_execute_repair_post_apply_verification({
        "verify": True,
        "verified_by": "unit-test",
        "reason": "verify after apply",
        "confirmations": ["confirm_post_apply_verification"],
    })

    assert report["verdict"] == "pass"
    assert report["counts"]["verified"] == 1
    assert report["counts"]["contract_failed"] == 0
    assert report["counts"]["doctor_findings"] == 0
    assert report["counts"]["repair_required"] == 0
    assert report["quality_gates"][0]["status"] == "pass"
    assert report["quality_gates"][3]["status"] == "pass"
    assert (tmp_path / report["source"]["repair_post_apply_verification_material"]).is_file()


def test_team_builder_repair_outcome_reconciliation_is_clean_without_applied_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no apply",
            "counts": {"items": 0, "applied": 0, "real_writes": 0},
            "apply_items": [],
            "records": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_post_apply_verification_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no verification",
            "counts": {"applied": 0, "verified": 0, "pending": 0, "failed": 0},
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_outcome_reconciliation_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["applied"] == 0
    assert report["source"]["repair_outcome_reconciliation_material"].endswith("team_repair_outcome_reconciliation.json")
    assert (tmp_path / report["source"]["repair_outcome_reconciliation_material"]).is_file()


def test_team_builder_repair_outcome_reconciliation_flags_missing_baseline(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "applied": 1, "real_writes": 1},
            "apply_items": [],
            "records": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "applied": True,
                    "changed_file": "src/generated/failing_worker.py",
                    "diff_sha256": "abc",
                    "real_writes": 1,
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_post_apply_verification_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "verified",
            "counts": {"applied": 1, "verified": 1, "pending": 0, "failed": 0},
            "applied_records": [{"candidate_id": "repair_patch_candidate:0"}],
            "reports": {
                "doctor_findings": {"available": True, "verdict": "pass", "findings": [], "counts": {"total": 0}},
                "repair_plan": {"available": True, "verdict": "clean", "counts": {"repair_required": 0}},
                "closure": {"available": True, "verdict": "pass"},
            },
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_outcome_reconciliation_report()
    item = report["reconciliation_items"][0]

    assert report["verdict"] == "missing_baseline"
    assert report["counts"]["missing_baseline"] == 1
    assert item["status"] == "missing_baseline"
    assert report["quality_gates"][0]["status"] == "warning"


def test_team_builder_repair_outcome_reconciliation_resolves_findings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    before_finding = {
        "id": "team_builder.worker_run_smoke.failed:failing_worker",
        "check_id": "team_builder.worker_run_smoke.failed",
        "worker_id": "failing_worker",
        "observation": "worker failed before patch",
    }
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "applied": 1, "real_writes": 1},
            "apply_items": [],
            "records": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "applied": True,
                    "changed_file": "src/generated/failing_worker.py",
                    "diff_sha256": "abc",
                    "before_reports": {
                        "doctor_findings": {"available": True, "verdict": "fail", "findings": [before_finding], "counts": {"total": 1}},
                        "repair_plan": {"available": True, "verdict": "repair_required", "counts": {"repair_required": 1}},
                        "closure": {"available": True, "verdict": "fail"},
                    },
                    "real_writes": 1,
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_post_apply_verification_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "verified",
            "counts": {"applied": 1, "verified": 1, "pending": 0, "failed": 0},
            "applied_records": [{"candidate_id": "repair_patch_candidate:0"}],
            "reports": {
                "doctor_findings": {"available": True, "verdict": "pass", "findings": [], "counts": {"total": 0}},
                "repair_plan": {"available": True, "verdict": "clean", "counts": {"repair_required": 0}},
                "closure": {"available": True, "verdict": "pass"},
            },
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_outcome_reconciliation_report()
    item = report["reconciliation_items"][0]

    assert report["verdict"] == "pass"
    assert report["counts"]["resolved_findings"] == 1
    assert report["counts"]["introduced_findings"] == 0
    assert report["counts"]["persistent_findings"] == 0
    assert item["status"] == "reconciled"
    assert item["before"]["doctor_findings"] == 1
    assert item["after"]["doctor_findings"] == 0


def test_team_builder_repair_outcome_reconciliation_detects_new_findings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    before_finding = {
        "id": "team_builder.worker_run_smoke.failed:failing_worker",
        "check_id": "team_builder.worker_run_smoke.failed",
        "worker_id": "failing_worker",
        "observation": "worker failed before patch",
    }
    new_finding = {
        "id": "team_builder.contract.execution_failed:unit_team",
        "check_id": "team_builder.contract.execution_failed",
        "worker_id": "",
        "observation": "contract failed after patch",
    }
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "applied": 1, "real_writes": 1},
            "apply_items": [],
            "records": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "applied": True,
                    "changed_file": "src/generated/failing_worker.py",
                    "diff_sha256": "abc",
                    "before_reports": {
                        "doctor_findings": {"available": True, "verdict": "fail", "findings": [before_finding], "counts": {"total": 1}},
                        "repair_plan": {"available": True, "verdict": "repair_required", "counts": {"repair_required": 1}},
                        "closure": {"available": True, "verdict": "fail"},
                    },
                    "real_writes": 1,
                }
            ],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_post_apply_verification_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "fail",
            "summary": "verified failed",
            "counts": {"applied": 1, "verified": 0, "pending": 0, "failed": 1},
            "applied_records": [{"candidate_id": "repair_patch_candidate:0"}],
            "reports": {
                "doctor_findings": {"available": True, "verdict": "fail", "findings": [new_finding], "counts": {"total": 1}},
                "repair_plan": {"available": True, "verdict": "repair_required", "counts": {"repair_required": 1}},
                "closure": {"available": True, "verdict": "fail"},
            },
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_outcome_reconciliation_report()
    item = report["reconciliation_items"][0]

    assert report["verdict"] == "regression"
    assert report["counts"]["resolved_findings"] == 1
    assert report["counts"]["introduced_findings"] == 1
    assert item["status"] == "regression"
    assert item["introduced_findings"][0]["check_id"] == "team_builder.contract.execution_failed"
    assert report["quality_gates"][2]["status"] == "fail"


def test_team_builder_repair_rollback_readiness_is_clean_without_applied_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no apply",
            "counts": {"items": 0, "applied": 0, "real_writes": 0},
            "apply_items": [],
            "records": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_readiness_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["applied"] == 0
    assert report["counts"]["rollback_ready"] == 0
    assert report["source"]["repair_rollback_readiness_material"].endswith("team_repair_rollback_readiness.json")
    assert (tmp_path / report["source"]["repair_rollback_readiness_material"]).is_file()


def test_team_builder_repair_rollback_readiness_marks_ready_with_matching_before_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    target = tmp_path / rel_path
    before_snapshot = tmp_path / "_scratch" / "team_builder_repair_apply_preview" / "unit-run" / "repair_patch_candidate_0" / "before" / rel_path
    before = "result = 'fail'\n"
    after = "result = 'pass'\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    before_snapshot.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(after, encoding="utf-8")
    before_snapshot.write_text(before, encoding="utf-8")
    before_snapshot_rel = str(before_snapshot.relative_to(tmp_path))
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "applied": 1, "real_writes": 1},
            "apply_items": [],
            "records": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "applied": True,
                    "changed_file": rel_path,
                    "diff_sha256": "abc",
                    "before_sha256": catalogue._team_builder_file_sha256(before_snapshot),
                    "after_sha256": catalogue._team_builder_file_sha256(target),
                    "before_preview_file": before_snapshot_rel,
                    "real_writes": 1,
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_readiness_report()
    item = report["rollback_items"][0]

    assert report["verdict"] == "ready_for_explicit_rollback"
    assert report["counts"]["rollback_ready"] == 1
    assert item["status"] == "ready_for_explicit_rollback"
    assert item["current_matches_after"] is True
    assert item["before_snapshot_valid"] is True
    assert item["blocked_reasons"] == []


def test_team_builder_repair_rollback_readiness_blocks_stale_current_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    target = tmp_path / rel_path
    before_snapshot = tmp_path / "_scratch" / "team_builder_repair_apply_preview" / "unit-run" / "repair_patch_candidate_0" / "before" / rel_path
    before = "result = 'fail'\n"
    after = "result = 'pass'\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    before_snapshot.parent.mkdir(parents=True, exist_ok=True)
    before_snapshot.write_text(before, encoding="utf-8")
    target.write_text(after, encoding="utf-8")
    after_sha = catalogue._team_builder_file_sha256(target)
    target.write_text("result = 'manual_change'\n", encoding="utf-8")
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "applied": 1, "real_writes": 1},
            "apply_items": [],
            "records": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "applied": True,
                    "changed_file": rel_path,
                    "diff_sha256": "abc",
                    "before_sha256": catalogue._team_builder_file_sha256(before_snapshot),
                    "after_sha256": after_sha,
                    "before_preview_file": str(before_snapshot.relative_to(tmp_path)),
                    "real_writes": 1,
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_readiness_report()
    item = report["rollback_items"][0]

    assert report["verdict"] == "stale_or_mismatch"
    assert report["counts"]["stale_or_mismatch"] == 1
    assert item["status"] == "stale_or_mismatch"
    assert item["current_matches_after"] is False
    assert report["quality_gates"][1]["status"] == "fail"


def test_team_builder_repair_rollback_readiness_blocks_missing_before_snapshot(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("result = 'pass'\n", encoding="utf-8")
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_apply_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "applied",
            "summary": "applied",
            "counts": {"items": 1, "applied": 1, "real_writes": 1},
            "apply_items": [],
            "records": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "applied": True,
                    "changed_file": rel_path,
                    "diff_sha256": "abc",
                    "before_sha256": "missing",
                    "after_sha256": catalogue._team_builder_file_sha256(target),
                    "real_writes": 1,
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_readiness_report()
    item = report["rollback_items"][0]

    assert report["verdict"] == "missing_before_snapshot"
    assert report["counts"]["missing_before_snapshot"] == 1
    assert item["status"] == "missing_before_snapshot"
    assert item["before_snapshot_valid"] is False
    assert report["quality_gates"][2]["status"] == "fail"


def test_team_builder_repair_rollback_execution_report_is_clean_without_ready_items(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_rollback_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no rollback",
            "counts": {"applied": 0, "rollback_ready": 0, "blocked": 0, "stale_or_mismatch": 0, "missing_before_snapshot": 0, "real_writes": 0},
            "quality_gates": [],
            "rollback_items": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_execution_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["items"] == 0
    assert report["counts"]["real_writes"] == 0
    assert report["source"]["repair_rollback_execution_report_material"].endswith("team_repair_rollback_execution_report.json")
    assert (tmp_path / report["source"]["repair_rollback_execution_report_material"]).is_file()


def test_team_builder_execute_repair_rollback_blocks_without_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_rollback_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_explicit_rollback",
            "summary": "ready",
            "counts": {"applied": 1, "rollback_ready": 1, "blocked": 0, "stale_or_mismatch": 0, "missing_before_snapshot": 0, "real_writes": 1},
            "quality_gates": [],
            "rollback_items": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_explicit_rollback",
                    "changed_file": "src/generated/failing_worker.py",
                    "before_sha256": "before",
                    "after_sha256": "after",
                    "before_preview_file": "_scratch/team_builder_repair_apply_preview/unit-run/repair_patch_candidate_0/before/src/generated/failing_worker.py",
                    "blocked_reasons": [],
                }
            ],
            "source": {},
        },
    )

    with pytest.raises(catalogue.HTTPException) as excinfo:
        catalogue._team_builder_execute_repair_rollback({
            "candidate_id": "repair_patch_candidate:0",
            "rollback": True,
            "before_sha256": "before",
            "after_sha256": "after",
            "rolled_back_by": "unit-test",
            "reason": "missing confirmation",
            "confirmations": [],
        })

    assert excinfo.value.status_code == 400


def test_team_builder_execute_repair_rollback_writes_before_snapshot_after_explicit_confirmation(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    rel_path = "src/generated/failing_worker.py"
    target = tmp_path / rel_path
    before_snapshot = tmp_path / "_scratch" / "team_builder_repair_apply_preview" / "unit-run" / "repair_patch_candidate_0" / "before" / rel_path
    before = "result = 'fail'\n"
    after = "result = 'pass'\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    before_snapshot.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(after, encoding="utf-8")
    before_snapshot.write_text(before, encoding="utf-8")
    before_sha = catalogue._team_builder_file_sha256(before_snapshot)
    after_sha = catalogue._team_builder_file_sha256(target)
    before_snapshot_rel = str(before_snapshot.relative_to(tmp_path))
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_rollback_readiness_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_explicit_rollback",
            "summary": "ready",
            "counts": {"applied": 1, "rollback_ready": 1, "blocked": 0, "stale_or_mismatch": 0, "missing_before_snapshot": 0, "real_writes": 1},
            "quality_gates": [],
            "rollback_items": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "ready_for_explicit_rollback",
                    "summary": "ready",
                    "changed_file": rel_path,
                    "diff_sha256": "abc",
                    "before_sha256": before_sha,
                    "after_sha256": after_sha,
                    "current_sha256": after_sha,
                    "before_preview_file": before_snapshot_rel,
                    "before_snapshot_sha256": before_sha,
                    "target_scope_safe": True,
                    "current_matches_after": True,
                    "before_snapshot_valid": True,
                    "blocked_reasons": [],
                }
            ],
            "source": {},
        },
    )

    report = catalogue._team_builder_execute_repair_rollback({
        "candidate_id": "repair_patch_candidate:0",
        "rollback": True,
        "before_sha256": before_sha,
        "after_sha256": after_sha,
        "rolled_back_by": "unit-test",
        "reason": "rollback explicit tested patch",
        "confirmations": ["confirm_real_file_rollback"],
    })
    item = report["rollback_items"][0]

    assert target.read_text(encoding="utf-8") == before
    assert report["verdict"] == "rolled_back"
    assert report["counts"]["rolled_back"] == 1
    assert report["counts"]["real_writes"] == 1
    assert item["status"] == "rolled_back"
    assert item["rolled_back_by"] == "unit-test"
    assert report["records"][0]["rollback_from_sha256"] == after_sha
    assert report["records"][0]["rollback_to_sha256"] == before_sha
    assert (tmp_path / report["source"]["repair_rollback_execution_records_material"]).is_file()


def test_team_builder_repair_rollback_post_verification_is_clean_without_rollback_records(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_rollback_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "clean",
            "summary": "no rollback",
            "counts": {"items": 0, "ready": 0, "rolled_back": 0, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 0},
            "rollback_items": [],
            "records": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_post_verification_report()

    assert report["verdict"] == "clean"
    assert report["counts"]["rolled_back"] == 0
    assert report["source"]["repair_rollback_post_verification_material"].endswith("team_repair_rollback_post_verification_result.json")
    assert (tmp_path / report["source"]["repair_rollback_post_verification_material"]).is_file()


def test_team_builder_repair_rollback_post_verification_waits_after_rollback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_rollback_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "rolled_back",
            "summary": "rolled back",
            "counts": {"items": 1, "ready": 0, "rolled_back": 1, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 1},
            "rollback_items": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "rolled_back",
                    "changed_file": "src/generated/failing_worker.py",
                    "rollback_from_sha256": "after",
                    "rollback_to_sha256": "before",
                    "current_sha256": "before",
                }
            ],
            "records": [],
            "source": {},
        },
    )

    report = catalogue._team_builder_repair_rollback_post_verification_report()

    assert report["verdict"] == "awaiting_verification"
    assert report["counts"]["rolled_back"] == 1
    assert report["counts"]["pending"] == 1
    assert report["verification_items"][0]["required_commands"][0].endswith("repair-rollback-post-verification/execute")


def test_team_builder_execute_repair_rollback_post_verification_passes_with_visible_restored_findings(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    old_finding = {
        "id": "team_builder.worker_run_smoke.failed:failing_worker",
        "check_id": "team_builder.worker_run_smoke.failed",
        "observation": "original failure restored after rollback",
    }
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_rollback_execution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "rolled_back",
            "summary": "rolled back",
            "counts": {"items": 1, "ready": 0, "rolled_back": 1, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 1},
            "rollback_items": [
                {
                    "candidate_id": "repair_patch_candidate:0",
                    "status": "rolled_back",
                    "changed_file": "src/generated/failing_worker.py",
                    "rollback_from_sha256": "after",
                    "rollback_to_sha256": "before",
                    "current_sha256": "before",
                }
            ],
            "records": [],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_execute_contracts_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "fail",
            "summary": "contract restored original failure",
            "counts": {"executed_contracts": 1, "failed_contracts": 1},
            "contracts": [{"path": "tests/teams/unit_team/test_contract.py", "status": "fail"}],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "fail",
            "summary": "test restored original failure",
            "counts": {},
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "fail",
            "summary": "doctor sees restored original finding",
            "counts": {"total": 1, "blocking": 1},
            "findings": [old_finding],
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "repair_required",
            "summary": "repair required restored",
            "counts": {"repair_required": 1},
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_closure_status",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "fail",
            "summary": "closure restored original failure",
            "missing": ["repair"],
            "source": {},
        },
    )

    report = catalogue._team_builder_execute_repair_rollback_post_verification({
        "verify": True,
        "verified_by": "unit-test",
        "reason": "verify rollback state",
        "confirmations": ["confirm_post_rollback_verification"],
    })

    assert report["verdict"] == "pass"
    assert report["counts"]["verified"] == 1
    assert report["counts"]["doctor_findings"] == 1
    assert report["counts"]["repair_required"] == 1
    assert report["quality_gates"][0]["status"] == "pass"
    assert report["quality_gates"][2]["status"] == "warning"
    assert (tmp_path / report["source"]["repair_rollback_post_verification_material"]).is_file()


def test_team_builder_repair_closure_rollup_is_clean_without_open_repair_work(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)

    def report(verdict: str = "clean", summary: str = "clean", counts: dict | None = None) -> dict:
        return {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": verdict,
            "summary": summary,
            "counts": counts or {},
            "source": {},
        }

    monkeypatch.setattr(catalogue, "_team_builder_latest_repair_plan", lambda: report(counts={"repair_required": 0, "validation_gap": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_patch_candidates_report", lambda: report(counts={"candidates": 0, "located_sources": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_gate_report", lambda: report(counts={"review_items": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_patch_diff_proposal_report", lambda: report(counts={"diff_ready": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_approval_report", lambda: report(counts={"proposals": 0, "approved": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_execution_readiness_report", lambda: report(counts={"execution_ready": 0, "blocked": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_preview_report", lambda: report(counts={"preview_ready": 0, "blocked": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_execution_report", lambda: report(counts={"applied": 0, "blocked": 0, "real_writes": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_post_apply_verification_report", lambda: report(counts={"pending": 0, "failed": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_outcome_reconciliation_report", lambda: report(counts={"reconciled": 0, "missing_baseline": 0, "introduced_findings": 0, "persistent_findings": 0, "pending_verification": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_readiness_report", lambda: report(counts={"rollback_ready": 0, "blocked": 0, "stale_or_mismatch": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_execution_report", lambda: report(counts={"rolled_back": 0, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_post_verification_report", lambda: report(counts={"pending": 0, "failed": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_safety_policy", lambda: {"available": True, "source": {}})

    rollup = catalogue._team_builder_repair_closure_rollup_report()

    assert rollup["verdict"] == "clean"
    assert rollup["counts"]["pending_stages"] == 0
    assert rollup["counts"]["failed_stages"] == 0
    assert rollup["next_actions"][0]["id"] == "scan_real_run_repair_candidates"
    assert rollup["next_actions"][0]["endpoint"] == "/api/team-builder-materialization/repair-real-run-candidate-scan/latest"
    assert rollup["source"]["repair_closure_rollup_material"].endswith("team_repair_closure_rollup.json")
    assert (tmp_path / rollup["source"]["repair_closure_rollup_material"]).is_file()


def test_team_builder_repair_closure_rollup_points_to_post_apply_verification_when_applied_patch_is_pending(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)

    def report(verdict: str = "clean", summary: str = "clean", counts: dict | None = None) -> dict:
        return {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": verdict,
            "summary": summary,
            "counts": counts or {},
            "source": {},
        }

    monkeypatch.setattr(catalogue, "_team_builder_latest_repair_plan", lambda: report(counts={"repair_required": 0, "validation_gap": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_patch_candidates_report", lambda: report(counts={"candidates": 0, "located_sources": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_gate_report", lambda: report(counts={"review_items": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_patch_diff_proposal_report", lambda: report(counts={"diff_ready": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_approval_report", lambda: report(counts={"proposals": 0, "approved": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_execution_readiness_report", lambda: report(counts={"execution_ready": 0, "blocked": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_preview_report", lambda: report(counts={"preview_ready": 0, "blocked": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_execution_report", lambda: report(counts={"applied": 1, "blocked": 0, "real_writes": 1}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_post_apply_verification_report", lambda: report("awaiting_verification", "pending post apply", {"pending": 1, "failed": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_outcome_reconciliation_report", lambda: report("awaiting_verification", "pending reconciliation", {"reconciled": 0, "missing_baseline": 0, "introduced_findings": 0, "persistent_findings": 0, "pending_verification": 1}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_readiness_report", lambda: report(counts={"rollback_ready": 0, "blocked": 0, "stale_or_mismatch": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_execution_report", lambda: report(counts={"rolled_back": 0, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_post_verification_report", lambda: report(counts={"pending": 0, "failed": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_safety_policy", lambda: {"available": True, "source": {}})

    rollup = catalogue._team_builder_repair_closure_rollup_report()
    stage = next(item for item in rollup["stages"] if item["id"] == "apply_and_verify")

    assert rollup["verdict"] == "action_required"
    assert stage["status"] == "pending_verification"
    assert rollup["next_actions"][0]["id"] == "verify_applied_patch"
    assert rollup["quality_gates"][2]["status"] == "warning"


def test_team_builder_repair_closure_rollup_exposes_multi_file_multi_candidate_risk(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)

    def report(verdict: str = "clean", summary: str = "clean", counts: dict | None = None) -> dict:
        return {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": verdict,
            "summary": summary,
            "counts": counts or {},
            "source": {},
        }

    monkeypatch.setattr(catalogue, "_team_builder_latest_repair_plan", lambda: report("repair_required", "repair required", {"repair_required": 1, "validation_gap": 0}))
    monkeypatch.setattr(
        catalogue,
        "_team_builder_repair_patch_candidates_report",
        lambda: {
            **report("ready_for_manual_patch", "two candidates", {"candidates": 2, "source_located": 2}),
            "candidates": [
                {
                    "id": "repair_patch_candidate:0",
                    "proposed_patch": {"changed_files": ["src/generated/a.py", "src/generated/b.py"]},
                },
                {
                    "id": "repair_patch_candidate:1",
                    "proposed_patch": {"changed_files": ["src/generated/c.py"]},
                },
            ],
        },
    )
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_gate_report", lambda: report(counts={"review_items": 2}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_patch_diff_proposal_report", lambda: report(counts={"diff_ready": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_approval_report", lambda: report(counts={"proposals": 0, "approved": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_execution_readiness_report", lambda: report(counts={"execution_ready": 0, "blocked": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_preview_report", lambda: report(counts={"preview_ready": 0, "blocked": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_apply_execution_report", lambda: report(counts={"applied": 0, "blocked": 0, "real_writes": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_post_apply_verification_report", lambda: report(counts={"pending": 0, "failed": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_outcome_reconciliation_report", lambda: report(counts={"reconciled": 0, "missing_baseline": 0, "introduced_findings": 0, "persistent_findings": 0, "pending_verification": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_readiness_report", lambda: report(counts={"rollback_ready": 0, "blocked": 0, "stale_or_mismatch": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_execution_report", lambda: report(counts={"rolled_back": 0, "blocked": 0, "stale_or_mismatch": 0, "real_writes": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_rollback_post_verification_report", lambda: report(counts={"pending": 0, "failed": 0}))
    monkeypatch.setattr(catalogue, "_team_builder_repair_safety_policy", lambda: {"available": True, "source": {}})

    rollup = catalogue._team_builder_repair_closure_rollup_report()

    assert rollup["counts"]["multi_candidate_count"] == 2
    assert rollup["counts"]["multi_file_candidate_count"] == 1
    assert rollup["generalization"]["single_file_execution_limit"] is False
    assert len(rollup["generalization"]["blockers"]) == 2
    assert rollup["quality_gates"][4]["status"] == "warning"


def test_team_builder_repair_generalization_trial_is_read_only_and_exposes_guards(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "unit-run"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(catalogue, "_team_builder_latest_run_dir", lambda: (run_dir, ""))

    report = catalogue._team_builder_repair_generalization_trial_report()

    assert report["verdict"] == "guarded_trial_ready"
    assert report["counts"]["candidate_count"] == 3
    assert report["counts"]["multi_file_candidate_count"] == 1
    assert report["counts"]["contract_target_count"] == 1
    assert report["counts"]["real_writes"] == 0
    assert report["quality_gates"][1]["id"] == "multi_file_real_apply_guarded"
    assert report["quality_gates"][2]["id"] == "contract_target_rejected"
    assert report["trial_cases"][1]["id"] == "multi_file_preview_guard"
    assert report["controlled_candidates"][0]["priority"] == 1
    assert report["source"]["repair_generalization_trial_material"].endswith("team_repair_generalization_trial.json")
    assert (tmp_path / report["source"]["repair_generalization_trial_material"]).is_file()


def test_team_builder_real_generated_file_set_trial_applies_verifies_and_rolls_back(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(catalogue, "_team_builder_latest_run_dir", lambda: (None, "no run"))

    report = catalogue._team_builder_real_generated_file_set_trial_report()

    assert report["available"] is True
    assert report["verdict"] == "pass"
    assert report["counts"]["changed_files"] == 2
    assert report["counts"]["files_previewed"] == 2
    assert report["counts"]["files_applied"] == 2
    assert report["counts"]["files_rolled_back"] == 2
    assert report["counts"]["before_failures"] == 1
    assert report["counts"]["post_apply_passed"] == 1
    assert report["counts"]["rollback_restored"] == 1
    assert report["counts"]["real_repo_writes"] == 0
    assert len(report["file_records"]) == 2
    assert all(record["after_apply_sha256"] == record["after_sha256"] for record in report["file_records"])
    assert all(record["after_rollback_sha256"] == record["before_sha256"] for record in report["file_records"])
    assert report["smoke"]["before_worker"]["status"] == "fail"
    assert report["smoke"]["after_apply_worker"]["status"] == "pass"
    assert report["smoke"]["after_rollback_worker"]["status"] == "fail"
    assert report["quality_gates"][3]["id"] == "file_set_apply_verified"
    assert report["quality_gates"][3]["status"] == "pass"
    assert report["quality_gates"][4]["id"] == "file_set_rollback_verified"
    assert report["quality_gates"][4]["status"] == "pass"
    material_path = tmp_path / report["source"]["repair_real_generated_file_set_trial_material"]
    assert material_path.is_file()


def test_team_builder_repair_real_run_candidate_scan_separates_failure_from_validation_gap(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    root = tmp_path / "_scratch" / "team_builder_real_material_validation"
    failed_run = root / "20260517-010000-failed"
    validation_run = root / "20260517-020000-validation-gap"
    for run_dir in [failed_run, validation_run]:
        (run_dir / "materials").mkdir(parents=True)
        (run_dir / "summary.json").write_text("{}", encoding="utf-8")

    (failed_run / "code_package_files" / "workers").mkdir(parents=True)
    (failed_run / "code_package_files" / "workers" / "material_usage_mapper.py").write_text(
        "class MaterialUsageMapperWorker:\n    pass\n",
        encoding="utf-8",
    )
    (failed_run / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "warning_count": 0,
            "issues": [
                {
                    "worker_id": "material_usage_mapper",
                    "severity": "critical",
                    "issue": "required field files was not read",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    (validation_run / "materials" / "team_doctor_findings.json").write_text(
        json.dumps({
            "findings": [
                {
                    "id": "team_builder.worker_run_smoke.requires_llm:writer",
                    "level": "advisory",
                    "target_id": "writer",
                }
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (validation_run / "materials" / "team_repair_plan.json").write_text(
        json.dumps({
            "counts": {"actions": 1, "repair_required": 0, "validation_gap": 1},
            "actions": [
                {
                    "id": "repair_action:0",
                    "category": "validation_gap",
                    "automation_level": "none",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = catalogue._team_builder_repair_real_run_candidate_scan_report()

    assert report["available"] is True
    assert report["verdict"] == "failure_candidate_needs_doctor"
    assert report["counts"]["runs_scanned"] == 2
    assert report["counts"]["failure_candidates"] == 1
    assert report["counts"]["repair_ready_candidates"] == 0
    assert report["counts"]["validation_gap_runs"] == 1
    assert report["counts"]["source_ready_candidates"] == 1
    assert report["quality_gates"][1]["id"] == "failure_and_validation_gap_separated"
    assert report["quality_gates"][2]["id"] == "repair_requires_explicit_candidate"
    assert report["candidates"][0]["run_id"] == "20260517-010000-failed"
    assert report["candidates"][0]["classification"] == "failure_without_repair_plan"
    assert report["candidates"][0]["source_ready"] is True
    assert report["next_actions"][0]["id"] == "replay_failed_run_to_repair_plan"
    material_path = tmp_path / report["source"]["scan_material"]
    assert material_path.is_file()


def test_team_builder_repair_real_run_replay_plan_consumes_code_review_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-010000-failed"
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    (run_dir / "code_package_files" / "workers").mkdir(parents=True)
    (run_dir / "code_package_files" / "workers" / "material_usage_mapper.py").write_text(
        "class MaterialUsageMapperWorker:\n    def run(self, input_data):\n        events = input_data.get('events', [])\n        return events\n",
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = catalogue._team_builder_repair_real_run_replay_plan_report()

    assert report["available"] is True
    assert report["verdict"] == "repair_plan_ready"
    assert report["counts"]["code_review_issues"] == 1
    assert report["counts"]["repair_required"] == 1
    assert report["counts"]["source_located"] == 1
    assert report["counts"]["diffs_generated"] == 0
    assert report["counts"]["real_repo_writes"] == 0
    assert report["findings"][0]["target_id"] == "material_usage_mapper"
    assert report["findings"][0]["required_not_read"] == ["files"]
    assert report["repair_actions"][0]["category"] == "repair_required"
    assert report["repair_actions"][0]["automation_level"] == "patch_plan_only"
    assert report["repair_actions"][0]["changed_files"][0].endswith("workers/material_usage_mapper.py")
    assert report["next_actions"][0]["id"] == "generate_reviewable_real_run_diff"
    material_path = tmp_path / report["source"]["replay_plan_material"]
    assert material_path.is_file()


def test_team_builder_repair_real_run_diff_preview_generates_reviewable_diff(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-010000-failed"
    source_path = run_dir / "code_package_files" / "workers" / "material_usage_mapper.py"
    source_path.parent.mkdir(parents=True)
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    source_path.write_text(
        "\n".join([
            "class MaterialUsageMapperWorker:",
            "    def run(self, input_data):",
            "        bundle = input_data",
            "        events: list[dict] = bundle.get(\"events\", [])",
            "        workspace_roots: list[str] = bundle.get(\"workspace_roots\", [])",
            "        nodes = []",
            "        confidence_notes = []",
            "        seen_node_ids = set()",
            "        def _ensure_node(node_id, node_type, label=None):",
            "            nodes.append({\"id\": node_id})",
            "        # Add workspace root nodes",
            "        for root in workspace_roots:",
            "            _ensure_node(f\"ws:{root}\", \"workspace\", root)",
            "",
            "        return nodes",
            "",
        ]),
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = catalogue._team_builder_repair_real_run_diff_preview_report()

    assert report["available"] is True
    assert report["verdict"] == "diff_preview_ready"
    assert report["counts"]["repair_actions"] == 1
    assert report["counts"]["diff_ready"] == 1
    assert report["counts"]["files_previewed"] == 1
    assert report["counts"]["real_repo_writes"] == 0
    record = report["diff_records"][0]
    assert record["worker_id"] == "material_usage_mapper"
    assert record["required_input_fields"] == ["files"]
    assert 'bundle.get("files", [])' in record["diff"]
    assert "declared_file" in record["diff"]
    assert (tmp_path / record["before_preview_file"]).is_file()
    assert (tmp_path / record["after_preview_file"]).is_file()
    assert report["next_actions"][0]["id"] == "review_real_run_diff_preview"
    assert (tmp_path / report["source"]["diff_preview_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")


def test_team_builder_repair_real_run_diff_review_requires_explicit_approval(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-010000-failed"
    source_path = run_dir / "code_package_files" / "workers" / "material_usage_mapper.py"
    source_path.parent.mkdir(parents=True)
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    source_path.write_text(
        "\n".join([
            "class MaterialUsageMapperWorker:",
            "    def run(self, input_data):",
            "        bundle = input_data",
            "        events: list[dict] = bundle.get(\"events\", [])",
            "        workspace_roots: list[str] = bundle.get(\"workspace_roots\", [])",
            "        nodes = []",
            "        confidence_notes = []",
            "        seen_node_ids = set()",
            "        def _ensure_node(node_id, node_type, label=None):",
            "            nodes.append({\"id\": node_id})",
            "        # Add workspace root nodes",
            "        for root in workspace_roots:",
            "            _ensure_node(f\"ws:{root}\", \"workspace\", root)",
            "",
            "        return nodes",
            "",
        ]),
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = catalogue._team_builder_repair_real_run_diff_review_report()

    assert report["available"] is True
    assert report["verdict"] == "review_ready"
    assert report["counts"]["diff_records"] == 1
    assert report["counts"]["ready_for_review"] == 1
    assert report["counts"]["requires_explicit_approval"] == 1
    assert report["counts"]["real_repo_writes"] == 0
    item = report["review_items"][0]
    assert item["status"] == "ready_for_explicit_review"
    assert item["target_scope_safe"] is True
    assert item["source_matches_before"] is True
    assert item["required_input_fields"] == ["files"]
    assert "declared_file" in " ".join(item["risk_notes"])
    assert report["quality_gates"][3]["id"] == "explicit_approval_required"
    assert report["next_actions"][0]["id"] == "build_real_run_explicit_apply_gate"
    assert (tmp_path / report["source"]["diff_review_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")


def test_team_builder_repair_real_run_apply_gate_stays_read_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-010000-failed"
    source_path = run_dir / "code_package_files" / "workers" / "material_usage_mapper.py"
    source_path.parent.mkdir(parents=True)
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    source_path.write_text(
        "\n".join([
            "class MaterialUsageMapperWorker:",
            "    def run(self, input_data):",
            "        bundle = input_data",
            "        events: list[dict] = bundle.get(\"events\", [])",
            "        workspace_roots: list[str] = bundle.get(\"workspace_roots\", [])",
            "        nodes = []",
            "        confidence_notes = []",
            "        seen_node_ids = set()",
            "        def _ensure_node(node_id, node_type, label=None):",
            "            nodes.append({\"id\": node_id})",
            "        # Add workspace root nodes",
            "        for root in workspace_roots:",
            "            _ensure_node(f\"ws:{root}\", \"workspace\", root)",
            "",
            "        return nodes",
            "",
        ]),
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = catalogue._team_builder_repair_real_run_apply_gate_report()

    assert report["available"] is True
    assert report["verdict"] == "ready_for_explicit_apply_preview"
    assert report["counts"]["review_items"] == 1
    assert report["counts"]["apply_preview_ready"] == 1
    assert report["counts"]["required_confirmation_tokens"] == 3
    assert report["counts"]["real_repo_writes"] == 0
    item = report["apply_items"][0]
    assert item["status"] == "ready_for_explicit_apply_preview"
    assert item["required_confirmations"] == [
        "confirm_real_run_diff_review",
        "confirm_real_run_file_set_write",
        "confirm_post_apply_replay_required",
    ]
    assert item["post_apply_verification"][0].startswith("重新执行 generated package code review")
    assert report["quality_gates"][3]["id"] == "get_apply_gate_is_read_only"
    assert report["next_actions"][0]["id"] == "generate_real_run_apply_preview"
    assert (tmp_path / report["source"]["apply_gate_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")


def test_team_builder_repair_real_run_apply_preview_writes_scratch_file_set(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-010000-failed"
    source_path = run_dir / "code_package_files" / "workers" / "material_usage_mapper.py"
    source_path.parent.mkdir(parents=True)
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    source_path.write_text(
        "\n".join([
            "class MaterialUsageMapperWorker:",
            "    def run(self, input_data):",
            "        bundle = input_data",
            "        events: list[dict] = bundle.get(\"events\", [])",
            "        workspace_roots: list[str] = bundle.get(\"workspace_roots\", [])",
            "        nodes = []",
            "        confidence_notes = []",
            "        seen_node_ids = set()",
            "        def _ensure_node(node_id, node_type, label=None):",
            "            nodes.append({\"id\": node_id})",
            "        # Add workspace root nodes",
            "        for root in workspace_roots:",
            "            _ensure_node(f\"ws:{root}\", \"workspace\", root)",
            "",
            "        return nodes",
            "",
        ]),
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    report = catalogue._team_builder_repair_real_run_apply_preview_report()

    assert report["available"] is True
    assert report["verdict"] == "preview_ready"
    assert report["counts"]["apply_items"] == 1
    assert report["counts"]["preview_ready"] == 1
    assert report["counts"]["files_previewed"] == 1
    assert report["counts"]["real_repo_writes"] == 0
    item = report["preview_items"][0]
    assert item["status"] == "preview_ready"
    assert item["file_set"] is True
    assert item["file_count"] == 1
    assert item["required_confirmations"] == [
        "confirm_real_run_diff_review",
        "confirm_real_run_file_set_write",
        "confirm_post_apply_replay_required",
    ]
    record = item["file_records"][0]
    assert (tmp_path / record["before_preview_file"]).is_file()
    assert (tmp_path / record["after_preview_file"]).is_file()
    assert record["before_sha256"] == record["source_current_sha256"]
    assert report["quality_gates"][3]["id"] == "real_run_preview_is_read_only"
    assert report["next_actions"][0]["id"] == "execute_real_run_apply_with_confirmations"
    assert (tmp_path / report["source"]["apply_preview_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")
    assert 'bundle.get("files", [])' in (tmp_path / record["after_preview_file"]).read_text(encoding="utf-8")


def test_team_builder_repair_real_run_apply_execution_requires_confirmations(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-010000-failed"
    source_path = run_dir / "code_package_files" / "workers" / "material_usage_mapper.py"
    source_path.parent.mkdir(parents=True)
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    source_path.write_text(
        "\n".join([
            "class MaterialUsageMapperWorker:",
            "    def run(self, input_data):",
            "        bundle = input_data",
            "        events: list[dict] = bundle.get(\"events\", [])",
            "        workspace_roots: list[str] = bundle.get(\"workspace_roots\", [])",
            "        nodes = []",
            "        confidence_notes = []",
            "        seen_node_ids = set()",
            "        def _ensure_node(node_id, node_type, label=None):",
            "            nodes.append({\"id\": node_id})",
            "        # Add workspace root nodes",
            "        for root in workspace_roots:",
            "            _ensure_node(f\"ws:{root}\", \"workspace\", root)",
            "",
            "        return nodes",
            "",
        ]),
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    preview = catalogue._team_builder_repair_real_run_apply_preview_report()
    assert preview["verdict"] == "preview_ready"
    awaiting_outcome = catalogue._team_builder_real_run_outcome_reconciliation_report()
    assert awaiting_outcome["verdict"] == "awaiting_apply"
    assert awaiting_outcome["quality_gates"][1]["id"] == "real_run_post_apply_verified"
    assert awaiting_outcome["quality_gates"][1]["status"] == "warning"
    assert awaiting_outcome["quality_gates"][2]["id"] == "real_run_no_new_failures"
    assert awaiting_outcome["quality_gates"][2]["status"] == "warning"
    assert awaiting_outcome["quality_gates"][3]["id"] == "real_run_original_findings_resolved"
    assert awaiting_outcome["quality_gates"][3]["status"] == "warning"
    awaiting_rollback = catalogue._team_builder_real_run_rollback_readiness_report()
    assert awaiting_rollback["verdict"] == "awaiting_apply"
    assert awaiting_rollback["counts"]["ready"] == 1
    assert awaiting_rollback["counts"]["applied"] == 0
    assert awaiting_rollback["quality_gates"][1]["id"] == "real_run_current_file_matches_after"
    assert awaiting_rollback["quality_gates"][1]["status"] == "warning"
    awaiting_rollback_execution = catalogue._team_builder_real_run_rollback_execution_report()
    assert awaiting_rollback_execution["verdict"] == "awaiting_apply"
    assert awaiting_rollback_execution["quality_gates"][0]["id"] == "real_run_rollback_readiness_required"
    assert awaiting_rollback_execution["quality_gates"][0]["status"] == "warning"
    awaiting_rollback_post = catalogue._team_builder_real_run_rollback_post_verification_report()
    assert awaiting_rollback_post["verdict"] == "awaiting_apply"
    assert awaiting_rollback_post["quality_gates"][1]["id"] == "real_run_post_rollback_verification_executed"
    assert awaiting_rollback_post["quality_gates"][1]["status"] == "warning"
    awaiting_rollup = catalogue._team_builder_real_run_closure_rollup_report()
    assert awaiting_rollup["verdict"] == "action_required"
    assert awaiting_rollup["counts"]["ready_to_apply"] == 1
    assert awaiting_rollup["counts"]["apply_rehearsal_passed"] == 1
    assert awaiting_rollup["counts"]["apply_rehearsal_blocked"] == 0
    assert awaiting_rollup["counts"]["apply_rehearsal_required_fields"] == 1
    assert awaiting_rollup["counts"]["apply_rehearsal_missing_required_fields"] == 0
    assert awaiting_rollup["next_actions"][0]["id"] == "execute_real_run_apply_with_confirmations"
    assert awaiting_rollup["next_actions"][0]["post_endpoint"].endswith("/repair-real-run-apply-execution/execute")
    assert awaiting_rollup["next_actions"][0]["required_confirmations"] == [
        "confirm_real_run_diff_review",
        "confirm_real_run_file_set_write",
        "confirm_post_apply_replay_required",
    ]
    assert "dashboard 页面刷新都不会写目标文件" in awaiting_rollup["next_actions"][0]["safety_note"]
    assert awaiting_rollup["approval_packet"]["available"] is True
    assert awaiting_rollup["approval_packet"]["status"] == "ready_for_decision"
    assert awaiting_rollup["approval_packet"]["post_endpoint"].endswith("/repair-real-run-apply-execution/execute")
    assert awaiting_rollup["approval_packet"]["payload_template"]["apply_item_id"] == "real_run_apply_gate:0"
    assert awaiting_rollup["approval_packet"]["decision_dossier"]["decision_question"].startswith(
        "是否批准把 material_usage_mapper 的真实失败 run 修复写入"
    )
    assert "没有 POST apply" in awaiting_rollup["approval_packet"]["decision_dossier"]["do_not_use_as_completion"]
    assert awaiting_rollup["approval_packet"]["decision_dossier"]["post_approval_sequence"][1].startswith("POST 应用后回放验证")
    preflight = awaiting_rollup["approval_packet"]["post_preflight"]
    assert preflight["status"] == "ready_to_post"
    assert preflight["blockers"] == []
    assert {condition["id"]: condition["status"] for condition in preflight["conditions"]}["current_matches_before"] == "pass"
    assert {condition["id"]: condition["status"] for condition in preflight["conditions"]}["rollback_snapshot_verified"] == "pass"
    assert {condition["id"]: condition["status"] for condition in preflight["conditions"]}["semantic_rehearsal_passed"] == "pass"
    auto_policy = awaiting_rollup["approval_packet"]["auto_apply_policy"]
    assert auto_policy["verdict"] == "eligible"
    assert auto_policy["eligible"] is True
    assert auto_policy["counts"]["candidate_items"] == 1
    assert auto_policy["counts"]["total_changed_files"] == 1
    assert auto_policy["counts"]["missing_required_fields"] == 0
    assert auto_policy["required_confirmation"] == "confirm_team_builder_low_risk_auto_apply"
    assert awaiting_rollup["approval_packet"]["apply_rehearsal"]["verdict"] == "pass"
    assert awaiting_rollup["approval_packet"]["apply_rehearsal"]["counts"]["passed"] == 1
    assert awaiting_rollup["approval_packet"]["apply_rehearsal"]["counts"]["real_repo_writes"] == 0
    assert awaiting_rollup["approval_packet"]["apply_rehearsal"]["counts"]["required_field_checks"] == 1
    assert awaiting_rollup["approval_packet"]["apply_rehearsal"]["counts"]["missing_required_fields"] == 0
    playbook = awaiting_rollup["approval_packet"]["execution_playbook"]
    assert playbook["status"] == "awaiting_explicit_approval"
    assert [step["id"] for step in playbook["steps"]] == [
        "apply_real_run_patch",
        "verify_after_apply",
        "review_reconciliation",
        "rollback_if_needed",
        "verify_after_rollback",
    ]
    assert playbook["steps"][0]["writes_target_files"] is True
    assert playbook["steps"][0]["can_execute_now"] is True
    assert playbook["steps"][1]["writes_target_files"] is False
    assert playbook["steps"][3]["payload_template"]["apply_item_id"] == "real_run_apply_gate:0"
    assert awaiting_rollup["approval_packet"]["items"][0]["changed_files"] == [
        "_scratch/team_builder_real_material_validation/20260517-010000-failed/code_package_files/workers/material_usage_mapper.py"
    ]
    assert awaiting_rollup["approval_packet"]["items"][0]["required_input_fields"] == ["files"]
    assert "Worker did not read required field files" in awaiting_rollup["approval_packet"]["items"][0]["problem_statement"]
    assert awaiting_rollup["approval_packet"]["items"][0]["evidence_links"][0]["target"].endswith("/repair-real-run-candidate-scan/latest")
    assert awaiting_rollup["approval_packet"]["items"][0]["evidence_links"][4]["kind"] == "file"
    assert awaiting_rollup["approval_packet"]["items"][0]["post_apply_verification"][0].startswith("重新执行 generated package code review")
    assert "before sha" in awaiting_rollup["approval_packet"]["items"][0]["rollback_requirement"]
    assert any(gate["id"] == "real_run_apply_rehearsal_passed" and gate["status"] == "pass" for gate in awaiting_rollup["quality_gates"])
    assert any(gate["id"] == "real_run_writes_are_explicit" and gate["status"] == "pass" for gate in awaiting_rollup["quality_gates"])

    rehearsal = catalogue._team_builder_real_run_apply_rehearsal_report()
    assert rehearsal["verdict"] == "pass"
    assert rehearsal["counts"]["ready"] == 1
    assert rehearsal["counts"]["passed"] == 1
    assert rehearsal["counts"]["real_repo_writes"] == 0
    assert rehearsal["counts"]["required_field_checks"] == 1
    assert rehearsal["counts"]["missing_required_fields"] == 0
    assert any(gate["id"] == "rehearsal_required_fields_replayed" and gate["status"] == "pass" for gate in rehearsal["quality_gates"])
    assert rehearsal["rehearsal_items"][0]["file_checks"][0]["applied_matches_after"] is True
    assert rehearsal["rehearsal_items"][0]["file_checks"][0]["rollback_matches_before"] is True
    assert rehearsal["rehearsal_items"][0]["file_checks"][0]["required_fields"] == ["files"]
    assert rehearsal["rehearsal_items"][0]["file_checks"][0]["required_fields_replayed"] == ["files"]
    assert rehearsal["rehearsal_items"][0]["file_checks"][0]["missing_fields"] == []
    assert rehearsal["rehearsal_items"][0]["file_checks"][0]["semantic_check_status"] == "pass"
    assert (tmp_path / rehearsal["source"]["apply_rehearsal_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")

    with pytest.raises(catalogue.HTTPException) as excinfo:
        catalogue._team_builder_execute_real_run_apply({
            "apply_item_id": "real_run_apply_gate:0",
            "apply": True,
            "applied_by": "unit-test",
            "reason": "missing tokens",
            "confirmations": ["confirm_real_run_diff_review"],
        })
    assert excinfo.value.status_code == 400
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")

    report = catalogue._team_builder_execute_real_run_apply({
        "apply_item_id": "real_run_apply_gate:0",
        "apply": True,
        "applied_by": "unit-test",
        "reason": "apply real run scratch generated package",
        "confirmations": [
            "confirm_real_run_diff_review",
            "confirm_real_run_file_set_write",
            "confirm_post_apply_replay_required",
        ],
    })

    assert report["verdict"] == "applied"
    assert report["counts"]["applied"] == 1
    assert report["counts"]["real_writes"] == 1
    assert report["apply_items"][0]["status"] == "applied"
    assert len(report["records"][0]["file_records"]) == 1
    assert (tmp_path / report["source"]["apply_execution_records_material"]).is_file()
    assert 'bundle.get("files", [])' in source_path.read_text(encoding="utf-8")

    rollback_readiness = catalogue._team_builder_real_run_rollback_readiness_report()
    assert rollback_readiness["verdict"] == "ready_for_explicit_rollback"
    assert rollback_readiness["counts"]["applied"] == 1
    assert rollback_readiness["counts"]["rollback_ready"] == 1
    assert rollback_readiness["counts"]["real_repo_writes"] == 1
    assert rollback_readiness["rollback_items"][0]["status"] == "ready_for_explicit_rollback"
    assert rollback_readiness["rollback_items"][0]["file_records"][0]["current_matches_after"] is True
    assert rollback_readiness["quality_gates"][0]["id"] == "real_run_explicit_rollback_only"
    assert (tmp_path / rollback_readiness["source"]["real_run_rollback_readiness_material"]).is_file()

    pending = catalogue._team_builder_real_run_post_apply_verification_report()
    assert pending["verdict"] == "awaiting_replay_verification"
    assert pending["counts"]["pending"] == 1

    with pytest.raises(catalogue.HTTPException) as verify_exc:
        catalogue._team_builder_execute_real_run_post_apply_verification({
            "verify": True,
            "verified_by": "unit-test",
            "reason": "missing token",
            "confirmations": [],
        })
    assert verify_exc.value.status_code == 400

    verification = catalogue._team_builder_execute_real_run_post_apply_verification({
        "verify": True,
        "verified_by": "unit-test",
        "reason": "verify after real run apply",
        "confirmations": ["confirm_real_run_post_apply_replay"],
    })
    assert verification["verdict"] == "warning"
    assert verification["counts"]["verified"] == 1
    assert verification["counts"]["missing_required_fields"] == 0
    assert verification["quality_gates"][1]["id"] == "required_fields_replayed"
    assert verification["quality_gates"][1]["status"] == "pass"
    assert (tmp_path / verification["source"]["post_apply_verification_material"]).is_file()

    outcome = catalogue._team_builder_real_run_outcome_reconciliation_report()
    assert outcome["verdict"] == "warning"
    assert outcome["counts"]["applied"] == 1
    assert outcome["counts"]["reconciled"] == 1
    assert outcome["counts"]["resolved_findings"] == 1
    assert outcome["counts"]["introduced_findings"] == 0
    assert outcome["counts"]["persistent_findings"] == 0
    assert outcome["reconciliation_items"][0]["status"] == "reconciled_with_warnings"
    assert outcome["quality_gates"][4]["id"] == "real_run_reconciliation_is_read_only"
    assert (tmp_path / outcome["source"]["outcome_reconciliation_material"]).is_file()

    rollback_execution = catalogue._team_builder_real_run_rollback_execution_report()
    assert rollback_execution["verdict"] == "ready_for_explicit_rollback"
    assert rollback_execution["counts"]["ready"] == 1
    assert rollback_execution["counts"]["rolled_back"] == 0
    with pytest.raises(catalogue.HTTPException) as rollback_exc:
        catalogue._team_builder_execute_real_run_rollback({
            "rollback": True,
            "apply_item_id": "real_run_apply_gate:0",
            "rolled_back_by": "unit-test",
            "reason": "missing rollback token",
            "confirmations": [],
        })
    assert rollback_exc.value.status_code == 400

    rolled_back = catalogue._team_builder_execute_real_run_rollback({
        "rollback": True,
        "apply_item_id": "real_run_apply_gate:0",
        "rolled_back_by": "unit-test",
        "reason": "rollback after verification",
        "confirmations": ["confirm_real_run_file_rollback"],
    })
    assert rolled_back["verdict"] == "rolled_back"
    assert rolled_back["counts"]["rolled_back"] == 1
    assert rolled_back["counts"]["real_repo_writes"] == 1
    assert rolled_back["rollback_items"][0]["status"] == "rolled_back"
    assert (tmp_path / rolled_back["source"]["rollback_execution_records_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")

    rollback_post_pending = catalogue._team_builder_real_run_rollback_post_verification_report()
    assert rollback_post_pending["verdict"] == "awaiting_verification"
    assert rollback_post_pending["counts"]["pending"] == 1
    with pytest.raises(catalogue.HTTPException) as rollback_post_exc:
        catalogue._team_builder_execute_real_run_rollback_post_verification({
            "verify": True,
            "verified_by": "unit-test",
            "reason": "missing rollback post token",
            "confirmations": [],
        })
    assert rollback_post_exc.value.status_code == 400

    rollback_post = catalogue._team_builder_execute_real_run_rollback_post_verification({
        "verify": True,
        "verified_by": "unit-test",
        "reason": "verify rollback restored before content",
        "confirmations": ["confirm_real_run_post_rollback_verification"],
    })
    assert rollback_post["verdict"] == "pass"
    assert rollback_post["counts"]["verified"] == 1
    assert rollback_post["counts"]["real_repo_writes"] == 0
    assert rollback_post["verification_items"][0]["file_checks"][0]["matches_before"] is True
    assert (tmp_path / rollback_post["source"]["rollback_post_verification_material"]).is_file()

    closed_rollup = catalogue._team_builder_real_run_closure_rollup_report()
    assert closed_rollup["counts"]["rolled_back"] == 1
    assert closed_rollup["counts"]["rollback_verified"] == 1
    assert closed_rollup["counts"]["rollback_real_writes"] == 1
    assert closed_rollup["source"]["real_run_closure_rollup_material"].endswith("team_repair_real_run_closure_rollup.json")
    assert (tmp_path / closed_rollup["source"]["real_run_closure_rollup_material"]).is_file()


def test_team_builder_real_run_low_risk_auto_apply_executes_verify_and_reconcile(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "20260517-030000-auto-apply"
    source_path = run_dir / "code_package_files" / "workers" / "material_usage_mapper.py"
    source_path.parent.mkdir(parents=True)
    (run_dir / "materials").mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")
    source_path.write_text(
        "\n".join([
            "class MaterialUsageMapperWorker:",
            "    def run(self, input_data):",
            "        bundle = input_data",
            "        events: list[dict] = bundle.get(\"events\", [])",
            "        workspace_roots: list[str] = bundle.get(\"workspace_roots\", [])",
            "        nodes = []",
            "        for root in workspace_roots:",
            "            nodes.append({\"id\": f\"ws:{root}\"})",
            "        return nodes",
            "",
        ]),
        encoding="utf-8",
    )
    (run_dir / "materials" / "code_review_report.json").write_text(
        json.dumps({
            "verdict": "fail",
            "critical_count": 1,
            "issues": [
                {
                    "category": "input_key_not_read",
                    "format_in": ["team_observer.material.run_artifact_bundle"],
                    "issue": "Worker did not read required field files",
                    "required_not_read": ["files"],
                    "severity": "critical",
                    "worker_id": "material_usage_mapper",
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    assert catalogue._team_builder_repair_real_run_apply_preview_report()["verdict"] == "preview_ready"
    policy = catalogue._team_builder_real_run_auto_apply_policy_report()
    assert policy["verdict"] == "eligible"
    assert policy["eligible"] is True
    assert policy["counts"]["total_changed_files"] == 1
    assert policy["counts"]["missing_required_fields"] == 0
    assert (tmp_path / policy["source"]["auto_apply_policy_material"]).is_file()
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")

    with pytest.raises(catalogue.HTTPException) as auto_exc:
        catalogue._team_builder_execute_real_run_auto_apply({
            "auto_apply": True,
            "executed_by": "unit-test",
            "reason": "missing auto token",
            "confirmations": [],
        })
    assert auto_exc.value.status_code == 400
    assert 'bundle.get("files", [])' not in source_path.read_text(encoding="utf-8")

    result = catalogue._team_builder_execute_real_run_auto_apply({
        "auto_apply": True,
        "executed_by": "unit-test",
        "reason": "low risk generated package repair",
        "confirmations": ["confirm_team_builder_low_risk_auto_apply"],
    })
    assert result["verdict"] in {"auto_applied", "auto_applied_with_warnings"}
    assert result["counts"]["applied"] == 1
    assert result["counts"]["real_writes"] == 1
    assert result["counts"]["verified"] == 1
    assert result["counts"]["resolved_findings"] == 1
    assert result["counts"]["introduced_findings"] == 0
    assert result["counts"]["persistent_findings"] == 0
    assert result["counts"]["rollback_ready"] == 1
    assert result["quality_gates"][3]["id"] == "auto_apply_outcome_reconciled"
    assert result["quality_gates"][3]["status"] == "pass"
    assert (tmp_path / result["source"]["auto_apply_execution_material"]).is_file()
    assert 'bundle.get("files", [])' in source_path.read_text(encoding="utf-8")

    repeated_policy = catalogue._team_builder_real_run_auto_apply_policy_report()
    assert repeated_policy["verdict"] == "already_applied"
    assert repeated_policy["eligible"] is False


def test_team_builder_high_standard_audit_refuses_completion_before_real_apply(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(catalogue, "_material_attribution_report", lambda: {
        "available": True,
        "run_id": "audit-run",
        "team_name": "team_observer_material_trial",
        "verdict": "warning",
        "summary": "仍有读取线索待确认。",
        "counts": {"confirmed_reads": 10, "read_clues": 12, "unconfirmed_read_clues": 2},
    })
    monkeypatch.setattr(catalogue, "_team_builder_test_report", lambda: {
        "available": True,
        "run_id": "audit-run",
        "team_name": "team_observer_material_trial",
        "counts": {"files": 10, "worker_files": 3, "executed_workers": 3, "failed_workers": 0},
    })
    monkeypatch.setattr(catalogue, "_team_builder_latest_doctor_findings_report", lambda: {
        "available": True,
        "counts": {"total": 0, "blocking": 0, "advisory": 0},
    })
    monkeypatch.setattr(catalogue, "_team_builder_latest_repair_plan", lambda: {
        "available": True,
        "verdict": "clean",
        "summary": "当前没有普通 repair action。",
        "counts": {"repair_required": 0, "validation_gap": 0},
    })
    monkeypatch.setattr(catalogue, "_team_builder_latest_closure_status", lambda: {
        "available": True,
        "run_id": "audit-run",
        "team_name": "team_observer_material_trial",
        "verdict": "pass",
        "stages": [
            {"name": "建立 team", "status": "pass", "summary": "结构通过。"},
            {"name": "测试 team", "status": "pass", "summary": "测试通过。"},
            {"name": "诊断分析", "status": "pass", "summary": "doctor 通过。"},
            {"name": "修复准备", "status": "pass", "summary": "repair clean。"},
        ],
        "missing": [],
    })
    monkeypatch.setattr(catalogue, "_team_builder_repair_closure_rollup_report", lambda: {
        "available": True,
        "verdict": "clean",
    })
    monkeypatch.setattr(catalogue, "_team_builder_repair_generalization_trial_report", lambda: {
        "available": True,
        "verdict": "guarded_trial_ready",
        "counts": {"candidate_count": 3, "multi_file_candidate_count": 1},
    })
    monkeypatch.setattr(catalogue, "_team_builder_real_generated_file_set_trial_report", lambda: {
        "available": True,
        "verdict": "pass",
        "counts": {"changed_files": 2},
    })
    monkeypatch.setattr(catalogue, "_team_builder_real_run_closure_rollup_report", lambda: {
        "available": True,
        "run_id": "audit-run",
        "team_name": "team_observer_material_trial",
        "summary": "真实失败 run 等待显式应用。",
        "counts": {"ready_to_apply": 1, "applied": 0, "rolled_back": 0},
        "next_actions": [{"id": "execute_real_run_apply_with_confirmations"}],
    })
    monkeypatch.setattr(catalogue, "_team_builder_latest_llm_replay_result", lambda: {
        "available": True,
        "verdict": "pass",
    })
    monkeypatch.setattr(catalogue, "_team_builder_provider_coverage_audit_report", lambda: {
        "available": True,
        "verdict": "needs_more_evidence",
        "missing": ["尚未形成 Claude Code 与 Codex 在同一 TeamBuilder 输入、同一权限、同一验证命令下的 codegen 质量对比。"],
    })

    report = catalogue._team_builder_high_standard_audit_report()

    assert report["available"] is True
    assert report["verdict"] == "in_progress"
    assert report["completion_ready"] is False
    assert any(item["id"] == "repair_real_failed_run" and item["status"] == "warning" for item in report["deliverables"])
    assert any("显式 apply 审批前" in item for item in report["missing"])
    checklist = report["prompt_to_artifact_checklist"]
    assert checklist["status"] == "not_complete"
    assert checklist["completion_rule"].startswith("只有全部 checklist status 为 pass")
    assert any(item["id"] == "objective_repair_team" and item["status"] == "warning" for item in checklist["items"])
    robustness_item = next(item for item in checklist["items"] if item["id"] == "quality_robustness")
    assert "真实 apply 前必须保持 in_progress" in robustness_item["gap"]
    assert "tests/dashboard/test_catalogue_material_attribution.py" in robustness_item["covered_by_tests"]
    assert report["quality_gates"][0]["id"] == "genericity"
    assert report["next_actions"][0]["id"] == "review_real_run_apply_decision"
    assert report["source"]["high_standard_audit_material"].endswith("team_builder_high_standard_audit.json")
    assert (tmp_path / report["source"]["high_standard_audit_material"]).is_file()


def test_team_builder_provider_coverage_audit_separates_external_provider_and_qwen_role(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "provider-run"
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(json.dumps({
        "provider": "claude-code",
        "started_at_local": "2026-05-18T00:00:00+08:00",
        "team_name": "team_observer_material_trial",
        "verification": {
            "worker_success_count": 3,
            "worker_fail_count": 0,
            "compile_fail_count": 0,
            "external_agent_runs": [
                {"worker_id": "run_artifact_collector", "provider": "claude-code", "status": "succeeded"},
                {"worker_id": "material_usage_mapper", "provider": "claude-code", "status": "succeeded"},
            ],
        },
        "materials": {
            "worker_code_files_bundle": {"success_count": 3, "fail_count": 0},
            "code_review_report": {"kind": "pass", "critical_count": 0, "warning_count": 0},
        },
    }, ensure_ascii=False), encoding="utf-8")
    (materials_dir / "team_test_report.json").write_text(json.dumps({
        "worker_run_smoke": {
            "llm_stub_calls": [
                {"model": "ide_agent", "expected_output_keys": ["summary_cn", "risks", "next_checks"]},
            ],
        },
    }, ensure_ascii=False), encoding="utf-8")

    report = catalogue._team_builder_provider_coverage_audit_report()

    assert report["available"] is True
    assert report["verdict"] == "needs_more_evidence"
    assert report["counts"]["external_providers_with_real_runs"] == 1
    assert any(item["provider"] == "claude-code" and item["status"] == "pass" for item in report["providers"])
    assert any(item["provider"] == "codex" and item["status"] == "missing" for item in report["providers"])
    assert report["internal_models"][0]["provider"] == "qwen-3.6-plus"
    assert "qwen-3.6-plus" in report["boundary_notes"][0]
    assert "不是 WorkerCodeOrchestrator external provider" in report["internal_models"][0]["role"]
    assert any("Claude Code 与 Codex" in item for item in report["missing"])
    assert report["source"]["provider_coverage_material"].endswith("team_builder_provider_coverage_audit.json")
    assert (tmp_path / report["source"]["provider_coverage_material"]).is_file()


def test_team_builder_provider_coverage_audit_includes_codex_same_input_trial_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "provider-run"
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(json.dumps({
        "provider": "claude-code",
        "team_name": "team_observer_material_trial",
        "verification": {
            "worker_success_count": 3,
            "worker_fail_count": 0,
            "compile_fail_count": 0,
            "external_agent_runs": [
                {"worker_id": "collector", "provider": "claude-code", "status": "succeeded"},
            ],
        },
        "materials": {
            "worker_code_files_bundle": {"success_count": 3, "fail_count": 0},
            "code_review_report": {"kind": "pass", "critical_count": 0},
        },
    }, ensure_ascii=False), encoding="utf-8")
    (materials_dir / "team_test_report.json").write_text(json.dumps({
        "worker_run_smoke": {"llm_stub_calls": []},
    }, ensure_ascii=False), encoding="utf-8")

    trial_dir = tmp_path / "_scratch" / "team_builder_provider_trials" / "trial-codex"
    trial_dir.mkdir(parents=True)
    (trial_dir / "summary.json").write_text(json.dumps({
        "mode": "executed",
        "baseline_run_id": "provider-run",
        "provider": "codex",
        "permission": "readonly",
        "model_policy": "cheap",
        "verdict_kind": "partial",
        "output": {
            "success_count": 0,
            "fail_count": 1,
            "external_agent_runs": [
                {
                    "worker_id": "collector",
                    "provider": "codex",
                    "status": "succeeded",
                    "parse_status": "no_worker_source",
                },
            ],
        },
    }, ensure_ascii=False), encoding="utf-8")

    report = catalogue._team_builder_provider_coverage_audit_report()

    assert report["counts"]["same_input_trials_scanned"] == 1
    assert report["counts"]["external_providers_with_evidence"] == 2
    codex = next(item for item in report["providers"] if item["provider"] == "codex")
    assert codex["status"] == "warning"
    assert codex["same_input_trials"] == 1
    assert codex["trial_failed_workers"] == 1
    assert codex["trial_parse_failures"] == 1
    assert codex["latest_trial_id"] == "trial-codex"
    assert report["recent_same_input_trials"][0]["parse_statuses"] == {"no_worker_source": 1}
    assert any("没有解析成可用 worker 源码" in item for item in report["missing"])
    assert report["next_actions"][0]["id"] == "fix_codex_worker_output_contract"
    assert report["quality_gates"][2]["id"] == "codex_same_path_evidence"
    assert "没有解析成可用 worker 源码" in report["quality_gates"][2]["summary"]


def test_team_builder_provider_coverage_marks_codex_pass_after_successful_same_input_trial(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "provider-run"
    materials_dir = run_dir / "materials"
    materials_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(json.dumps({
        "provider": "claude-code",
        "team_name": "team_observer_material_trial",
        "verification": {
            "worker_success_count": 1,
            "worker_fail_count": 0,
            "compile_fail_count": 0,
            "external_agent_runs": [
                {"worker_id": "collector", "provider": "claude-code", "status": "succeeded"},
            ],
        },
        "materials": {
            "worker_code_files_bundle": {"success_count": 1, "fail_count": 0},
            "code_review_report": {"kind": "pass", "critical_count": 0},
        },
    }, ensure_ascii=False), encoding="utf-8")
    (materials_dir / "team_test_report.json").write_text(json.dumps({
        "worker_run_smoke": {"llm_stub_calls": []},
    }, ensure_ascii=False), encoding="utf-8")

    trial_dir = tmp_path / "_scratch" / "team_builder_provider_trials" / "trial-codex-pass"
    trial_dir.mkdir(parents=True)
    (trial_dir / "summary.json").write_text(json.dumps({
        "mode": "executed",
        "baseline_run_id": "provider-run",
        "provider": "codex",
        "permission": "readonly",
        "model_policy": "cheap",
        "verdict_kind": "pass",
        "output": {
            "success_count": 1,
            "fail_count": 0,
            "external_agent_runs": [
                {
                    "worker_id": "collector",
                    "provider": "codex",
                    "status": "succeeded",
                    "parse_status": "worker_source",
                },
            ],
        },
    }, ensure_ascii=False), encoding="utf-8")

    report = catalogue._team_builder_provider_coverage_audit_report()

    codex = next(item for item in report["providers"] if item["provider"] == "codex")
    assert codex["status"] == "pass"
    assert codex["passing_evidence"] == 1
    assert report["counts"]["external_providers_with_evidence"] == 2
    assert report["next_actions"][0]["id"] == "add_second_team_type_provider_sample"
    assert not any(item.startswith("qwen-3.6-plus") for item in report["missing"])
    assert "qwen-3.6-plus" in report["boundary_notes"][0]


def test_team_builder_provider_coverage_requires_both_providers_on_second_team_type(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    root = tmp_path / "_scratch" / "team_builder_real_material_validation"
    observer_run = root / "observer-run"
    observer_run.mkdir(parents=True)
    (observer_run / "summary.json").write_text(json.dumps({
        "provider": "claude-code",
        "team_name": "team_observer_material_trial",
        "verification": {
            "worker_success_count": 1,
            "worker_fail_count": 0,
            "compile_fail_count": 0,
            "external_agent_runs": [{"worker_id": "collector", "provider": "claude-code", "status": "succeeded"}],
        },
        "materials": {"worker_code_files_bundle": {"success_count": 1, "fail_count": 0}, "code_review_report": {"critical_count": 0}},
    }, ensure_ascii=False), encoding="utf-8")
    repo_baseline = root / "repo-baseline"
    repo_baseline.mkdir(parents=True)
    (repo_baseline / "summary.json").write_text(json.dumps({
        "mode": "snapshot_provider_baseline",
        "provider": "claude-code",
        "team_name": "repo_absorption",
        "verification": {
            "worker_success_count": 4,
            "worker_fail_count": 1,
            "compile_fail_count": 0,
            "external_agent_runs": [{"worker_id": "scanner", "provider": "claude-code", "status": "succeeded"}],
        },
        "materials": {"worker_code_files_bundle": {"success_count": 4, "fail_count": 1}, "code_review_report": {"critical_count": 0}},
    }, ensure_ascii=False), encoding="utf-8")

    assert catalogue._team_builder_latest_run_dir()[0] == observer_run

    trial_root = tmp_path / "_scratch" / "team_builder_provider_trials"
    for trial_name, team_name, success_count in [
        ("observer-codex", "team_observer_material_trial", 1),
        ("repo-codex", "repo_absorption", 5),
    ]:
        trial_dir = trial_root / trial_name
        trial_dir.mkdir(parents=True)
        (trial_dir / "summary.json").write_text(json.dumps({
            "mode": "executed",
            "baseline_run_id": "observer-run" if team_name == "team_observer_material_trial" else "repo-baseline",
            "provider": "codex",
            "permission": "readonly",
            "model_policy": "cheap",
            "verdict_kind": "pass",
            "plan": {"team_name": team_name},
            "output": {
                "success_count": success_count,
                "fail_count": 0,
                "external_agent_runs": [{"worker_id": "worker", "provider": "codex", "status": "succeeded", "parse_status": "worker_source"}],
            },
        }, ensure_ascii=False), encoding="utf-8")

    report = catalogue._team_builder_provider_coverage_audit_report()

    assert report["verdict"] == "comparison_ready"
    assert report["counts"]["provider_team_type_counts"] == {"claude-code": 2, "codex": 2}
    assert report["missing"] == []
    assert report["next_actions"][0]["id"] == "provider_matrix_ready"


def test_team_builder_provider_same_input_trial_plan_uses_saved_design_materials(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "same-input-run"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text(json.dumps({
        "provider": "claude-code",
        "team_name": "team_observer_material_trial",
        "verification": {
            "worker_success_count": 1,
            "worker_fail_count": 0,
            "compile_fail_count": 0,
            "external_agent_runs": [
                {
                    "worker_id": "collector",
                    "provider": "claude-code",
                    "status": "succeeded",
                    "prompt_chars": 1234,
                    "rel_path": "workers/collector.py",
                },
            ],
        },
        "materials": {
            "team_design": {"team_name": "team_observer_material_trial"},
            "worker_design_detailed": {
                "details": [
                    {
                        "worker_id": "collector",
                        "cn_name": "收集器",
                        "impl_type": "HARD",
                        "format_in": "demo.input",
                        "format_out": "demo.output",
                    },
                ],
            },
            "material_design_detailed": {
                "details": [
                    {"material_id": "demo.input", "json_schema": {"required": ["path"]}},
                    {"material_id": "demo.output", "json_schema": {"required": ["rows"]}},
                ],
            },
            "worker_code_files_bundle": {"success_count": 1, "fail_count": 0},
            "code_review_report": {"kind": "pass", "critical_count": 0},
        },
    }, ensure_ascii=False), encoding="utf-8")

    report = catalogue._team_builder_provider_same_input_trial_plan_report()

    assert report["available"] is True
    assert report["verdict"] == "ready_for_explicit_trial"
    assert report["ready"] is True
    assert report["baseline_run_id"] == "same-input-run"
    assert report["target_provider"] == "codex"
    assert report["permission"] == "readonly"
    assert report["model_policy"] == "cheap"
    assert report["workers"][0]["worker_id"] == "collector"
    assert report["workers"][0]["baseline_provider"] == "claude-code"
    assert "provider_same_input_trial" in report["command"]
    assert "--provider codex" in report["command"]
    assert report["source"]["same_input_trial_plan_material"].endswith("team_builder_provider_same_input_trial_plan.json")
    assert (tmp_path / report["source"]["same_input_trial_plan_material"]).is_file()


def test_team_builder_doctor_verdict_passes_when_findings_are_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "warning",
            "summary": "test warning from covered llm gap",
            "doctor_findings": [],
            "worker_run_smoke": {"skipped_workers": [{"worker_id": "soft", "reason": "requires_llm"}]},
            "source": {},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_result",
        lambda: {
            "available": True,
            "verdict": "pass",
            "counts": {"executed_llm_workers": [{"worker_id": "soft", "kind": "pass"}]},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {"available": True, "read_groups": []},
    )

    report = catalogue._team_builder_latest_doctor_findings_report()

    assert report["verdict"] == "pass"
    assert report["counts"]["total"] == 0
    assert "没有发现" in report["summary"]


def test_team_builder_repair_safety_policy_is_explicit(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    run_dir = tmp_path / "_scratch" / "team_builder_real_material_validation" / "unit-run"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("{}", encoding="utf-8")

    policy = catalogue._team_builder_latest_repair_safety_policy()

    assert policy["available"] is True
    assert policy["counts"]["rules"] >= 4
    assert policy["counts"]["auto_safe_rules"] == 0
    assert any(rule["id"] == "validation_gap_no_code_change" for rule in policy["rules"])
    assert policy["source"]["repair_safety_policy_material"].endswith("team_repair_safety_policy.json")


def test_team_builder_llm_replay_plan_uses_stub_contract(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.delenv("OMNI_ALLOW_TEAM_BUILDER_LLM_REPLAY", raising=False)
    monkeypatch.delenv("THE_COMPANY_API_KEY", raising=False)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "worker_run_smoke": {
                "stubbed_workers": [
                    {
                        "worker_id": "health_report_writer",
                        "llm_stub_calls": [
                            {
                                "model": "qwen-3.6-plus",
                                "max_tokens": 4096,
                                "system_chars": 43,
                                "user_chars": 681,
                                "system_preview": "你是 team 运行健康观察助手",
                                "user_preview": "请输出 JSON 和中文结论",
                                "expected_output_keys": ["summary_cn", "risks", "next_checks"],
                                "stub_response_keys": ["summary_cn", "risks", "next_checks"],
                                "has_json_instruction": True,
                                "has_chinese_instruction": True,
                            }
                        ],
                    }
                ],
            },
            "source": {},
        },
    )

    plan = catalogue._team_builder_latest_llm_replay_plan()

    assert plan["verdict"] == "ready_for_controlled_replay"
    assert plan["counts"] == {"calls": 1, "ready": 1, "blocked": 0}
    assert plan["actions"][0]["worker_id"] == "health_report_writer"
    assert plan["actions"][0]["model"] == "qwen-3.6-plus"
    assert plan["actions"][0]["expected_output_keys"] == ["summary_cn", "risks", "next_checks"]
    assert plan["quality_gates"][1]["status"] == "pass"
    assert plan["execution_preflight"]["status"] == "blocked_by_switch"
    assert plan["execution_preflight"]["can_execute"] is False
    assert "OMNI_ALLOW_TEAM_BUILDER_LLM_REPLAY" in plan["execution_preflight"]["next_action"]
    assert plan["source"]["llm_replay_plan_material"].endswith("team_llm_replay_plan.json")


def test_team_builder_execute_llm_replay_blocks_without_switch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_plan",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "ready_for_controlled_replay",
            "summary": "ready",
            "counts": {"calls": 1, "ready": 1, "blocked": 0},
            "actions": [{"id": "llm_replay:soft:0", "worker_id": "soft"}],
            "execution_preflight": {
                "status": "blocked_by_switch",
                "enabled": False,
                "can_execute": False,
                "summary": "真实 LLM 回放开关未打开。",
            },
            "source": {"test_package_dir": "_scratch/team_builder_test_reports/unit-run/unit_team"},
        },
    )

    report = catalogue._team_builder_execute_llm_replay()

    assert report["verdict"] == "blocked_by_switch"
    assert report["counts"]["planned_calls"] == 1
    assert report["counts"]["executed_workers"] == 0
    assert report["source"]["llm_replay_result_material"].endswith("team_llm_replay_result.json")
    assert (tmp_path / report["source"]["llm_replay_result_material"]).is_file()


def test_team_builder_closure_treats_passing_llm_replay_as_test_coverage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "material pass",
            "counts": {"confirmed_reads": 2, "read_clues": 2, "unconfirmed_read_clues": 0},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_read_clue_resolution_plan",
        lambda report=None: {"available": True, "counts": {"unresolved": 0}},
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "warning",
            "summary": "test warning",
            "quality_gates": [
                {"id": "package_manifest", "status": "pass"},
                {"id": "worker_run_smoke", "status": "warning"},
            ],
            "counts": {
                "files": 10,
                "worker_files": 3,
                "executed_workers": 2,
                "stubbed_workers": 1,
                "skipped_workers": 1,
                "failed_workers": 0,
            },
            "worker_run_smoke": {"skipped_workers": [{"worker_id": "soft", "reason": "requires_llm"}]},
            "contract_coverage": {
                "available": True,
                "counts": {"matching_contracts": 1, "executed_contracts": 1},
            },
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {"available": True, "counts": {"total": 0, "blocking": 0, "advisory": 0}},
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "verdict": "clean",
            "summary": "clean",
            "counts": {"actions": 0, "repair_required": 0, "validation_gap": 0, "auto_safe": 0},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_plan",
        lambda: {
            "available": True,
            "verdict": "ready_for_controlled_replay",
            "counts": {"calls": 1, "ready": 1, "blocked": 0},
            "execution_preflight": {"can_execute": True},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_result",
        lambda: {
            "available": True,
            "verdict": "pass",
            "counts": {"executed_llm_workers": [{"worker_id": "soft", "kind": "pass"}]},
        },
    )

    status = catalogue._team_builder_latest_closure_status()

    test_stage = next(stage for stage in status["stages"] if stage["id"] == "测试 team")
    assert test_stage["status"] == "pass"
    assert not any("真实 LLM 调用尚未回放" in item for item in status["missing"])
    assert not any("smoke test 等同于 acceptance" in item for item in status["missing"])


def test_team_builder_closure_lists_missing_contract_coverage(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "material pass",
            "counts": {"confirmed_reads": 2, "read_clues": 2, "unconfirmed_read_clues": 0},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_read_clue_resolution_plan",
        lambda report=None: {"available": True, "counts": {"unresolved": 0}},
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "pass",
            "summary": "test pass",
            "quality_gates": [
                {"id": "package_manifest", "status": "pass"},
                {"id": "worker_run_smoke", "status": "pass"},
            ],
            "counts": {
                "files": 10,
                "worker_files": 3,
                "executed_workers": 3,
                "stubbed_workers": 0,
                "skipped_workers": 0,
                "failed_workers": 0,
            },
            "worker_run_smoke": {"skipped_workers": []},
            "contract_coverage": {
                "available": True,
                "status": "missing_contract",
                "counts": {"matching_contracts": 0, "executed_contracts": 0},
            },
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {"available": True, "counts": {"total": 0, "blocking": 0, "advisory": 0}},
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "verdict": "clean",
            "summary": "clean",
            "counts": {"actions": 0, "repair_required": 0, "validation_gap": 0, "auto_safe": 0},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_plan",
        lambda: {"available": True, "verdict": "no_llm_call", "counts": {"calls": 0, "ready": 0, "blocked": 0}},
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_result",
        lambda: {"available": True, "verdict": "no_llm_call", "counts": {"executed_llm_workers": []}},
    )

    status = catalogue._team_builder_latest_closure_status()

    test_stage = next(stage for stage in status["stages"] if stage["id"] == "测试 team")
    assert status["verdict"] == "warning"
    assert test_stage["status"] == "warning"
    assert "contract_matching=0" in test_stage["evidence"]
    assert any("不能把 smoke test 等同于 acceptance" in item for item in status["missing"])


def test_team_builder_closure_status_lists_validation_gaps(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(catalogue, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        catalogue,
        "_material_attribution_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "warning",
            "summary": "material warning",
            "counts": {"confirmed_reads": 2, "read_clues": 3, "unconfirmed_read_clues": 1},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_test_report",
        lambda: {
            "available": True,
            "run_id": "unit-run",
            "team_name": "unit_team",
            "verdict": "warning",
            "summary": "test warning",
            "quality_gates": [
                {"id": "package_manifest", "status": "pass"},
                {"id": "worker_run_smoke", "status": "warning"},
            ],
            "counts": {
                "files": 10,
                "worker_files": 3,
                "executed_workers": 2,
                "stubbed_workers": 1,
                "skipped_workers": 1,
                "failed_workers": 0,
            },
            "worker_run_smoke": {"skipped_workers": [{"worker_id": "soft", "reason": "requires_llm"}]},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_doctor_findings_report",
        lambda: {"available": True, "counts": {"total": 2, "blocking": 0, "advisory": 2}},
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_repair_plan",
        lambda: {
            "available": True,
            "verdict": "validation_gap",
            "summary": "repair gap",
            "counts": {"actions": 2, "repair_required": 0, "validation_gap": 2, "auto_safe": 0},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_plan",
        lambda: {
            "available": True,
            "verdict": "ready_for_controlled_replay",
            "counts": {"calls": 1, "ready": 1, "blocked": 0},
        },
    )
    monkeypatch.setattr(
        catalogue,
        "_team_builder_latest_llm_replay_result",
        lambda: {"available": False, "verdict": "not_run", "counts": {"executed_llm_workers": []}},
    )

    status = catalogue._team_builder_latest_closure_status()

    assert status["verdict"] == "warning"
    assert len(status["stages"]) == 5
    assert any("读取线索消解计划已生成" in item for item in status["missing"])
    assert any("回放计划已生成" in item for item in status["missing"])
    assert any("不满足自动改代码条件" in item for item in status["missing"])
    assert status["source"]["read_clue_resolution_endpoint"].endswith("/read-clue-resolution/latest")
    assert status["source"]["closure_status_material"].endswith("team_closure_status.json")
