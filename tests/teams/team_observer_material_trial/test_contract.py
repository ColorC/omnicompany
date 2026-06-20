# [OMNI] origin=codex domain=tests/teams/team_observer_material_trial ts=2026-05-18T00:00:00+08:00 type=test
"""team_observer_material_trial 的 team contract。

这个 contract 验证 TeamBuilder 生成的 team 不是脚本级样本：
- 拓扑必须包含观察请求、证据包、血缘图、健康报告四类 material。
- HARD worker 必须能读取真实工作区文件并保留事件线索。
- 血缘 worker 必须能表达 worker、material、workspace 三类节点和边。
- SOFT worker 必须在受控 LLM 桩下输出中文健康报告契约。
"""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


PIPELINE_NAME = "team-observer-material-trial"
TEAM_NAME = "team_observer_material_trial"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _latest_generated_package() -> Path:
    scratch_root = _repo_root() / "_scratch" / "team_builder_real_material_validation"
    candidates: list[Path] = []
    if scratch_root.is_dir():
        for run_dir in scratch_root.iterdir():
            code_root = run_dir / "code_package_files"
            code_package = run_dir / "materials" / "code_package.json"
            if not code_root.is_dir() or not code_package.is_file():
                continue
            try:
                payload = json.loads(code_package.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("team_name") == TEAM_NAME:
                candidates.append(run_dir)
    if not candidates:
        raise AssertionError(f"没有找到 {TEAM_NAME} 的 TeamBuilder 生成包")
    latest = max(candidates, key=lambda path: ((path / "summary.json").stat().st_mtime, path.name))
    return latest / "code_package_files"


@pytest.fixture(scope="module")
def generated_package() -> Any:
    code_root = _latest_generated_package()
    sys.path.insert(0, str(code_root.parent))
    try:
        team_mod = importlib.import_module("code_package_files.team")
        run_mod = importlib.import_module("code_package_files.run")
        health_mod = importlib.import_module("code_package_files.workers.health_report_writer")
        yield SimpleNamespace(code_root=code_root, team=team_mod, run=run_mod, health=health_mod)
    finally:
        try:
            sys.path.remove(str(code_root.parent))
        except ValueError:
            pass


def _kind_value(verdict: Any) -> str:
    return str(getattr(getattr(verdict, "kind", None), "value", getattr(verdict, "kind", "")))


def _fake_llm_client(summary: str = "当前 team 读取了工作区文件并生成了可审阅的物料血缘图。"):
    class FakeResponse:
        content = [
            SimpleNamespace(
                text=json.dumps(
                    {
                        "summary_cn": summary,
                        "risks": ["部分 workspace 读取仍需工具事件二次确认"],
                        "next_checks": ["在 dashboard 中核对 worker、material 和 workspace 边"],
                    },
                    ensure_ascii=False,
                )
            )
        ]

    class FakeLLMClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def call(self, *args, **kwargs):
            return FakeResponse()

    return FakeLLMClient


def test_topology_declares_observer_materials(generated_package) -> None:
    spec = generated_package.team.build_team()

    assert spec.id == TEAM_NAME
    assert spec.entry == "run_artifact_collector"
    assert [node.id for node in spec.nodes] == [
        "run_artifact_collector",
        "material_usage_mapper",
        "health_report_writer",
    ]
    assert [edge.source for edge in spec.edges] == ["run_artifact_collector", "material_usage_mapper"]
    assert [edge.target for edge in spec.edges] == ["material_usage_mapper", "health_report_writer"]

    formats = {node.id: node.anchor.format_out for node in spec.nodes}
    assert formats["run_artifact_collector"] == "team_observer.material.run_artifact_bundle"
    assert formats["material_usage_mapper"] == "team_observer.material.material_lineage_graph"
    assert formats["health_report_writer"] == "team_observer.material.health_report"


def test_success_reads_workspace_builds_lineage_and_writes_health_report(tmp_path, monkeypatch, generated_package) -> None:
    workspace = tmp_path / "workspace"
    source_dir = workspace / "materials"
    source_dir.mkdir(parents=True)
    source_file = source_dir / "source_material.py"
    source_file.write_text(
        '# [OMNI] material_id="material:contract.source"\n'
        "class Demo:\n"
        "    pass\n",
        encoding="utf-8",
    )
    bindings = generated_package.run.build_bindings({})

    observation = {
        "team_id": TEAM_NAME,
        "workspace_root": str(workspace),
        "event_sources": ["materials/source_material.py", "missing_event.jsonl"],
        "question": "这个 team 是否能把 workspace 文件和 material 关系表达清楚？",
    }
    collector = bindings["run_artifact_collector"].run({
        "team_observer.input.observation_request": observation,
    })
    assert _kind_value(collector) == "pass"
    assert collector.output["team_id"] == TEAM_NAME
    assert len(collector.output["files"]) == 1
    assert len(collector.output["events"]) == 1
    assert collector.output["files"][0]["source"] == "materials/source_material.py"
    assert "material:contract.source" in collector.output["files"][0]["preview"]

    mapper = bindings["material_usage_mapper"].run({
        "team_observer.material.run_artifact_bundle": collector.output,
    })
    assert _kind_value(mapper) == "pass"
    graph = mapper.output
    assert any(node["type"] == "workspace" for node in graph["nodes"])
    assert any(node["type"] == "material" and "source_material.py" in node["label"] for node in graph["nodes"])
    assert any(edge["relation"] == "contains" for edge in graph["edges"])
    assert any("summary:" in note for note in graph["confidence_notes"])

    monkeypatch.setattr(generated_package.health, "LLMClient", _fake_llm_client())
    health = bindings["health_report_writer"].run({
        "team_observer.input.observation_request": observation,
        "team_observer.material.material_lineage_graph": graph,
    })
    assert _kind_value(health) == "pass"
    assert len(health.output["summary_cn"]) >= 20
    assert "工作区" in health.output["summary_cn"] or "物料血缘图" in health.output["summary_cn"]
    assert isinstance(health.output["risks"], list)
    assert isinstance(health.output["next_checks"], list)


def test_mapper_exposes_worker_material_and_workspace_edges(generated_package, tmp_path) -> None:
    workspace = tmp_path / "repo"
    workspace.mkdir()
    src_path = str(workspace / "team.py")
    bundle = {
        "team_id": TEAM_NAME,
        "workspace_roots": [str(workspace)],
        "files": [
            {
                "path": src_path,
                "material_id": "team_observer.material.run_artifact_bundle",
                "producer_worker_id": "run_artifact_collector",
                "consumer_worker_id": "material_usage_mapper",
            }
        ],
        "events": [
            {
                "worker_id": "material_usage_mapper",
                "tool": "Read",
                "path": src_path,
                "material_id": "team_observer.material.run_artifact_bundle",
            }
        ],
    }
    mapper = generated_package.run.build_bindings({})["material_usage_mapper"].run({
        "team_observer.material.run_artifact_bundle": bundle,
    })

    assert _kind_value(mapper) == "pass"
    nodes = mapper.output["nodes"]
    edges = mapper.output["edges"]
    assert {"id": "w:run_artifact_collector", "type": "worker", "label": "run_artifact_collector"} in nodes
    assert {"id": "w:material_usage_mapper", "type": "worker", "label": "material_usage_mapper"} in nodes
    assert any(node["id"] == "mat:team_observer.material.run_artifact_bundle" for node in nodes)
    assert any(edge["relation"] == "produces" and edge["confidence"] == "direct_field" for edge in edges)
    assert any(edge["relation"] == "consumed_by" and edge["confidence"] == "direct_field" for edge in edges)
    assert any(edge["relation"] == "tool_event:Read" and edge["confidence"] == "direct_field" for edge in edges)
    assert any(edge["relation"] == "contains" and edge["confidence"] == "path_inference" for edge in edges)


def test_error_missing_observation_fields(generated_package) -> None:
    collector = generated_package.run.build_bindings({})["run_artifact_collector"].run({
        "team_observer.input.observation_request": {
            "team_id": TEAM_NAME,
            "workspace_root": "",
            "event_sources": [],
            "question": "",
        }
    })

    assert _kind_value(collector) == "fail"
    assert "missing workspace_root" in collector.diagnosis
    assert "event_sources" in collector.diagnosis
    assert "missing question" in collector.diagnosis
