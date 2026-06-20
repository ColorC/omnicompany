from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.external_workers.base import (
    ExternalAgentEvent,
    ExternalAgentResult,
    ExternalAgentRunSpec,
    ExternalAgentStatus,
    ExternalAgentWorker,
    ExternalAgentWorkerRegistry,
)
from omnicompany.packages.services._core.team_builder.workers.code_gen_soft import (
    WorkerCodeOrchestrator,
)
from omnicompany.protocol.anchor import VerdictKind


class _RecordingCodeWorker(ExternalAgentWorker):
    provider_name = "fake-code"

    def __init__(
        self,
        *,
        calls: list[ExternalAgentRunSpec],
        status: ExternalAgentStatus = ExternalAgentStatus.SUCCEEDED,
        final_text: str = "",
        error: str = "",
        events: list[ExternalAgentEvent] | None = None,
        bus: Any | None = None,
    ) -> None:
        super().__init__(bus=bus)
        self._calls = calls
        self._status = status
        self._final_text = final_text
        self._error = error
        self._events = events or []

    async def _run_impl(self, spec: ExternalAgentRunSpec) -> ExternalAgentResult:
        self._calls.append(spec)
        return ExternalAgentResult(
            run_id=spec.run_id,
            provider=self.provider_name,
            status=self._status,
            final_text=self._final_text,
            error=self._error,
            events=self._events,
        )


class _RecordingSchemaCodexWorker(_RecordingCodeWorker):
    provider_name = "codex"

    def __init__(self, *, schema_snapshots: list[dict[str, Any]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._schema_snapshots = schema_snapshots

    async def _run_impl(self, spec: ExternalAgentRunSpec) -> ExternalAgentResult:
        if spec.output_schema_path:
            self._schema_snapshots.append(json.loads(Path(spec.output_schema_path).read_text(encoding="utf-8")))
        return await super()._run_impl(spec)


def _registry(
    *,
    calls: list[ExternalAgentRunSpec],
    final_text: str = "",
    status: ExternalAgentStatus = ExternalAgentStatus.SUCCEEDED,
    error: str = "",
    events: list[ExternalAgentEvent] | None = None,
) -> ExternalAgentWorkerRegistry:
    registry = ExternalAgentWorkerRegistry()
    registry.register(
        "fake-code",
        lambda **kw: _RecordingCodeWorker(
            calls=calls,
            final_text=final_text,
            status=status,
            error=error,
            events=events,
            **kw,
        ),
    )
    return registry


def _input_payload() -> dict[str, Any]:
    return {
        "_from_team_architect": {"team_name": "demo_team"},
        "_from_worker_designer": {
            "details": [
                {
                    "worker_id": "csv_reader",
                    "impl_type": "HARD",
                    "format_in": "demo.input",
                    "format_out": "demo.rows",
                    "rule_spec": {"steps": ["read path", "emit rows"]},
                }
            ]
        },
        "_from_material_designer": {
            "details": [
                {
                    "material_id": "demo.input",
                    "json_schema": {
                        "type": "object",
                        "required": ["path", "files"],
                        "properties": {
                            "path": {"type": "string"},
                            "files": {"type": "array", "items": {"type": "object"}},
                        },
                    },
                },
                {
                    "material_id": "demo.rows",
                    "json_schema": {
                        "type": "object",
                        "required": ["rows", "source_path"],
                        "properties": {
                            "rows": {"type": "array"},
                            "source_path": {"type": "string"},
                        },
                    },
                },
            ]
        },
    }


_GOOD_WORKER_SOURCE = """```python
from __future__ import annotations

from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


class CsvReaderWorker(Worker):
    DESCRIPTION = "Read CSV metadata into rows"
    FORMAT_IN = "demo.input"
    FORMAT_OUT = "demo.rows"

    def run(self, input_data: Any) -> Verdict:
        payload = input_data.get(self.FORMAT_IN, input_data) if isinstance(input_data, dict) else {}
        path = payload.get("path", "") if isinstance(payload, dict) else ""
        files = payload.get("files", []) if isinstance(payload, dict) else []
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rows": [], "source_path": path, "file_count": len(files)},
            diagnosis="csv rows collected",
        )
```"""


@pytest.mark.asyncio
async def test_worker_code_orchestrator_uses_external_agent_success(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=_GOOD_WORKER_SOURCE),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PASS
    assert verdict.output["success_count"] == 1
    assert verdict.output["fail_count"] == 0
    source = verdict.output["files"]["workers/csv_reader.py"]
    assert source.startswith("# [OMNI]")
    assert "class CsvReaderWorker(Worker)" in source
    assert calls
    assert calls[0].provider == "fake-code"
    assert calls[0].permission_mode == "readonly"
    assert calls[0].model is None
    assert "Return contract" in calls[0].prompt
    assert "pure text code-generation task" in calls[0].prompt
    assert "not an existing repo file to edit" in calls[0].prompt
    assert "The only valid worker class name is CsvReaderWorker" in calls[0].prompt
    assert "Do not inspect `src/omnicompany/packages/services/_core/team_builder/workers/`" in calls[0].prompt
    assert "Do not return diffs" in calls[0].prompt
    assert "csv_reader" in calls[0].prompt
    assert "Required input fields to access in source" in calls[0].prompt
    assert "payload_demo_input.get('path'" in calls[0].prompt
    assert "payload_demo_input.get('files'" in calls[0].prompt
    run_meta = verdict.output["external_agent_runs"][0]
    assert run_meta["provider"] == "fake-code"
    assert run_meta["status"] == "succeeded"
    assert run_meta["parse_status"] == "worker_source"
    assert run_meta["input_material_ids"] == ["demo.input"]
    assert run_meta["output_material_id"] == "demo.rows"
    assert {
        "material_id": "demo.input",
        "direction": "read",
        "confidence": "high",
        "basis": "FORMAT_IN declaration",
        "evidence": ["worker.format_in"],
    } in run_meta["material_io_links"]
    assert {
        "material_id": "demo.rows",
        "direction": "write",
        "confidence": "high",
        "basis": "FORMAT_OUT declaration",
        "evidence": ["worker.format_out"],
    } in run_meta["material_io_links"]
    assert run_meta["static_field_access"]["input_field_reads"]["demo.input"] == ["files", "path"]
    assert run_meta["static_field_access"]["missing_input_required"] == {}
    assert run_meta["static_field_access"]["output_field_writes"] == ["rows", "source_path"]
    assert run_meta["static_field_access"]["missing_output_required"] == []
    produced = run_meta["produced_content_materials"][0]
    assert produced["material_id"] == "team_builder.generated_file.demo_team.workers_csv_reader_py"
    assert produced["direction"] == "write"
    assert produced["registration_status"] == "generated-candidate"
    assert produced["rel_path"] == "workers/csv_reader.py"
    assert produced in run_meta["material_io_links"]


@pytest.mark.asyncio
async def test_worker_code_orchestrator_uses_output_schema_for_codex_provider(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    schema_snapshots: list[dict[str, Any]] = []
    registry = ExternalAgentWorkerRegistry()
    registry.register(
        "codex",
        lambda **kw: _RecordingSchemaCodexWorker(
            calls=calls,
            final_text=_GOOD_WORKER_SOURCE,
            schema_snapshots=schema_snapshots,
            **kw,
        ),
    )
    orchestrator = WorkerCodeOrchestrator(
        external_provider="codex",
        external_worker_registry=registry,
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PASS
    assert calls[0].output_schema_path is not None
    assert not Path(calls[0].output_schema_path).exists()
    assert schema_snapshots[0]["properties"]["files"]["required"] == ["workers/csv_reader.py"]
    assert "CsvReaderWorker" in schema_snapshots[0]["description"]


@pytest.mark.asyncio
async def test_worker_code_orchestrator_materializes_external_read_events(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    declared_material_file = tmp_path / "declared_material.md"
    declared_material_file.write_text(
        '<!-- [OMNI] material_id="material:demo.workspace_doc" -->\n# workspace doc\n',
        encoding="utf-8",
    )
    grep_hit_file = tmp_path / "grep_hit.py"
    grep_hit_file.write_text(
        '# [OMNI] material_id="material:demo.grep_hit"\nclass GrepHitWorker:\n    pass\n',
        encoding="utf-8",
    )
    events = [
        ExternalAgentEvent(
            type="assistant.tool_use",
            payload={
                "content": [
                    {
                        "type": "tool_use",
                        "name": "read_file",
                        "input": {"path": "src/omnicompany/packages/services/_diagnosis/doctor/team.py"},
                    }
                ]
            },
        ),
        ExternalAgentEvent(
            type="assistant.tool_use",
            payload={
                "content": [
                    {
                        "type": "tool_use",
                        "name": "read_file",
                        "input": {"path": str(declared_material_file)},
                    }
                ]
            },
        ),
        ExternalAgentEvent(
            type="exec",
            payload={"command": "rg -n \"demo.input|class .*Worker\" src/omnicompany/packages/services/_diagnosis/doctor"},
        ),
        ExternalAgentEvent(
            type="assistant.tool_use",
            payload={
                "content": [
                    {
                        "type": "tool_use",
                        "id": "grep-1",
                        "name": "Grep",
                        "input": {"pattern": "material_id", "path": str(tmp_path)},
                    }
                ]
            },
        ),
        ExternalAgentEvent(
            type="assistant.tool_result",
            payload={
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "grep-1",
                        "content": f"{grep_hit_file}:1:# [OMNI] material_id=\"material:demo.grep_hit\"",
                    }
                ]
            },
        ),
    ]
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=_GOOD_WORKER_SOURCE, events=events),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PASS
    run_meta = verdict.output["external_agent_runs"][0]
    assert run_meta["event_count"] == 5
    assert run_meta["tool_event_count"] >= 2
    assert any("doctor/team.py" in target for target in run_meta["observed_read_targets"])
    assert any("rg -n" in target for target in run_meta["observed_read_targets"])
    assert any("grep_hit.py" in target for target in run_meta["observed_read_targets"])
    grep_event = next(event for event in run_meta["tool_events"] if event.get("tool_use_id") == "grep-1")
    assert grep_event["result_paths"] == [str(grep_hit_file)]
    assert grep_event["result_path_evidence_kind"] == "search_hit_path"
    assert "material:demo.grep_hit" in grep_event["result_excerpt"]
    assert any(link["resource_kind"] == "workspace" and link["material_id"] for link in run_meta["resource_read_links"])
    assert any(link["registration_status"] == "candidate" for link in run_meta["resource_material_links"])
    assert any("doctor_team_py" in link["material_id"] for link in run_meta["resource_material_links"])
    assert any(link["candidate_kind"] == "file" and link["candidate_reason"] for link in run_meta["resource_material_links"])
    assert any("material:demo.workspace_doc" in link["matched_material_ids"] for link in run_meta["resource_material_links"])
    assert any(link["material_id"] == "demo.input" for link in run_meta["inferred_material_read_links"])
    assert any(
        link["material_id"] == "material:demo.workspace_doc"
        and link["registration_status"] == "declared-in-file"
        for link in run_meta["inferred_material_read_links"]
    )
    assert any(
        link["material_id"] == "material:demo.grep_hit"
        and link["registration_status"] == "declared-in-file"
        for link in run_meta["inferred_material_read_links"]
    )


@pytest.mark.asyncio
async def test_worker_code_orchestrator_rejects_garbage_sized_prompt_before_agent(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=_GOOD_WORKER_SOURCE),
        external_cwd=tmp_path,
        max_external_prompt_chars=200,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PARTIAL
    assert verdict.output["success_count"] == 0
    assert verdict.output["fail_count"] == 1
    assert calls == []
    run_meta = verdict.output["external_agent_runs"][0]
    assert run_meta["status"] == "prompt_rejected"
    assert any("prompt too large" in issue for issue in run_meta["prompt_quality_issues"])


@pytest.mark.asyncio
async def test_worker_code_orchestrator_falls_back_to_skeleton_on_external_failure(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(
            calls=calls,
            status=ExternalAgentStatus.FAILED,
            error="synthetic failure",
        ),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PARTIAL
    assert verdict.output["success_count"] == 0
    assert verdict.output["fail_count"] == 1
    assert calls
    assert "workers/csv_reader.py" in verdict.output["files"]
    assert verdict.output["external_agent_runs"][0]["status"] == "failed"
    assert any("synthetic failure" in issue for issue in verdict.output["lint_summary"])


@pytest.mark.asyncio
async def test_worker_code_orchestrator_records_excerpt_when_external_output_has_no_worker_source(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    final_text = "I inspected the repo and found the worker should read CSV rows, but I am only returning a summary."
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=final_text),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PARTIAL
    assert verdict.output["success_count"] == 0
    assert verdict.output["fail_count"] == 1
    run_meta = verdict.output["external_agent_runs"][0]
    assert run_meta["parse_status"] == "no_worker_source"
    assert run_meta["source_text_origin"] == "final_text"
    assert run_meta["source_text_chars"] == len(final_text)
    assert run_meta["final_text_excerpt"] == final_text
    assert run_meta["source_text_excerpt"] == final_text
    assert run_meta["parse_diagnostics"]["expected_class_name"] == "CsvReaderWorker"
    assert run_meta["parse_diagnostics"]["likely_issue"] == "no_python_worker_candidate"
    assert any("no parseable worker source" in issue for issue in verdict.output["lint_summary"])


@pytest.mark.asyncio
async def test_worker_code_orchestrator_diagnoses_patch_instead_of_requested_worker(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    final_text = """I cannot write files in read-only mode, so here is a patch.

```diff
*** Begin Patch
*** Update File: src/omnicompany/packages/services/_core/team_builder/workers/reference_scout.py
@@
+class ReferenceScoutWorker(Worker):
+    def run(self, input_data):
+        return Verdict(kind=VerdictKind.PASS, output={}, diagnosis="ok")
*** End Patch
```"""
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=final_text),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    run_meta = verdict.output["external_agent_runs"][0]
    diagnostics = run_meta["parse_diagnostics"]
    assert run_meta["parse_status"] == "no_worker_source"
    assert diagnostics["returned_patch"] is True
    assert diagnostics["mentions_readonly_block"] is True
    assert diagnostics["likely_issue"] == "returned_patch_instead_of_worker_file"
    assert diagnostics["candidate_class_names"] == ["ReferenceScoutWorker"]


@pytest.mark.asyncio
async def test_worker_code_orchestrator_rejects_invalid_python_from_external_agent(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    bad_source = """```python
from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


class CsvReaderWorker(Worker):
    DESCRIPTION = "bad syntax"
    FORMAT_IN = "demo.input"
    FORMAT_OUT = "demo.rows"

    def run(self, input_data)
        return Verdict(kind=VerdictKind.PASS, output={}, diagnosis="bad")
```"""
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=bad_source),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PARTIAL
    assert verdict.output["success_count"] == 0
    assert verdict.output["fail_count"] == 1
    run_meta = verdict.output["external_agent_runs"][0]
    assert run_meta["parse_status"] == "syntax_error"
    assert "syntax error" in run_meta["compile_issue"]
    assert any("invalid python" in issue for issue in verdict.output["lint_summary"])


@pytest.mark.asyncio
async def test_worker_code_orchestrator_rejects_invalid_verdict_kind_from_external_agent(tmp_path: Path):
    calls: list[ExternalAgentRunSpec] = []
    bad_source = """```python
from typing import Any
from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


class CsvReaderWorker(Worker):
    DESCRIPTION = "invalid verdict kind"
    FORMAT_IN = "demo.input"
    FORMAT_OUT = "demo.rows"

    def run(self, input_data: Any) -> Verdict:
        return Verdict(kind=VerdictKind.OK, output={"rows": [], "source_path": ""}, diagnosis="bad")
```"""
    orchestrator = WorkerCodeOrchestrator(
        external_provider="fake-code",
        external_worker_registry=_registry(calls=calls, final_text=bad_source),
        external_cwd=tmp_path,
    )

    verdict = await orchestrator.run(_input_payload())

    assert verdict.kind == VerdictKind.PARTIAL
    assert verdict.output["success_count"] == 0
    assert verdict.output["fail_count"] == 1
    run_meta = verdict.output["external_agent_runs"][0]
    assert run_meta["parse_status"] == "invalid_verdict_kind"
    assert "OK" in run_meta["verdict_kind_issue"]
    assert any("invalid VerdictKind" in issue for issue in verdict.output["lint_summary"])
