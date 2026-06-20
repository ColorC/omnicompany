from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.bus.memory import MemoryBus
from omnicompany.packages.services._core.agent.external_workers import (
    ClaudeCodeSdkWorker,
    CodexExecWorker,
    ExternalAgentResult,
    ExternalAgentPermissionMode,
    ExternalAgentRunRequest,
    ExternalAgentRunSpec,
    ExternalAgentStatus,
    ExternalAgentSubAgent,
    ExternalAgentWorker,
    ExternalAgentWorkerNode,
    ExternalAgentWorkerRegistry,
    FakeExternalAgentWorker,
    build_external_agent_subagent_registry,
    build_default_external_agent_worker_registry,
    resolve_external_agent_model,
    run_external_agent_request,
)
from omnicompany.protocol.anchor import AnchorSpec, Route, RouteAction, ValidatorKind, ValidatorSpec, VerdictKind
from omnicompany.protocol.pipeline import NodeKind, NodeMaturity, PipelineNode, PipelineSpec
from omnicompany.runtime.exec.runner import PipelineRunner
from omnicompany.packages.services._core.agent.external_workers.codex import (
    _build_env,
    _diff_watch_snapshots,
    _format_diff_summary,
    _parse_json_lines,
    _parse_structured_final_text,
    _parse_git_status_paths,
    _resolve_executable_for_subprocess,
    _rollback_new_changes,
    _snapshot_watch_paths,
)
from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter
from omnicompany.packages.services._core.agent.routers.single_tool import ToolContext
from omnicompany.packages.services._core.agent.spawn_surface import (
    AGENT_SPAWN_SURFACE_VERSION,
    ENTRY_EXTERNAL_WORKER_AS_AGENT,
    ENTRY_EXTERNAL_WORKER_RUN,
    ENTRY_TEAMRUNNER_NODE,
)

# noqa-OMNI-080: this file parses worker audit/database JSON and prompt
# fixtures; it does not parse LLM finish-tool text.


@pytest.mark.asyncio
async def test_fake_worker_emits_audit_events(tmp_path: Path):
    bus = MemoryBus()
    spec = ExternalAgentRunSpec(
        provider="fake",
        prompt="summarize the repo",
        cwd=tmp_path,
        trace_id="trace.external.fake",
        attached_context=["context A"],
    )

    result = await FakeExternalAgentWorker(bus=bus).run(spec)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    assert "context A" in result.final_text
    events = await bus.read_trace("trace.external.fake")
    assert [e.event_type for e in events] == [
        "external_agent.started",
        "external_agent.completed",
    ]
    assert events[0].payload["permission_mode"] == "readonly"
    assert "prompt" not in events[0].payload


def test_worker_registry_creates_registered_provider():
    registry = ExternalAgentWorkerRegistry()
    registry.register("fake", FakeExternalAgentWorker)

    worker = registry.create("fake")

    assert isinstance(worker, FakeExternalAgentWorker)
    assert registry.list_providers() == ["fake"]


class _SlowExternalAgentWorker(ExternalAgentWorker):
    provider_name = "slow"

    async def _run_impl(self, spec: ExternalAgentRunSpec) -> ExternalAgentResult:
        await asyncio.sleep(1)
        return ExternalAgentResult(
            run_id=spec.run_id,
            provider=spec.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="too late",
        )


class _CapturingExternalAgentWorker(ExternalAgentWorker):
    provider_name = "capturing"

    def __init__(self, captured: dict[str, ExternalAgentRunSpec], *, bus=None):
        super().__init__(bus=bus)
        self._captured = captured

    async def _run_impl(self, spec: ExternalAgentRunSpec) -> ExternalAgentResult:
        self._captured["spec"] = spec
        return ExternalAgentResult(
            run_id=spec.run_id,
            provider=spec.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="captured spec",
        )


@pytest.mark.asyncio
async def test_worker_base_enforces_timeout(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="slow",
        prompt="wait",
        cwd=tmp_path,
        timeout_s=0.01,
    )

    result = await _SlowExternalAgentWorker().run(spec)

    assert result.status == ExternalAgentStatus.TIMED_OUT
    assert "timed out" in result.error


def test_run_spec_rejects_unknown_permission(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="fake",
        prompt="x",
        cwd=tmp_path,
        permission_mode="root-all-the-things",
    )

    with pytest.raises(ValueError):
        spec.normalized_permission_mode()


def test_codex_command_maps_permissions_and_prompt_context(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="codex",
        prompt="make a plan",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
        model="gpt-5.3-codex",
        profile="omni",
        attached_context=["file A says hello"],
    )
    worker = CodexExecWorker(codex_executable="codex-test")

    cmd = worker.build_command(spec, last_message_path=tmp_path / "last.md")

    assert cmd[:2] == ["codex-test", "exec"]
    assert "--ephemeral" in cmd
    assert "--json" in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write"
    assert cmd[cmd.index("--cd") + 1] == str(tmp_path.resolve())
    assert cmd[cmd.index("--model") + 1] == "gpt-5.3-codex"
    assert cmd[cmd.index("--profile") + 1] == "omni"
    assert cmd[-1] == "-"


def test_codex_command_resolves_windows_cmd_shim_for_subprocess(monkeypatch):
    monkeypatch.setattr(
        "omnicompany.packages.services._core.agent.external_workers.codex.shutil.which",
        lambda name: r"C:\Users\test\AppData\Roaming\npm\codex.cmd" if name == "codex" else None,
    )

    assert _resolve_executable_for_subprocess("codex").endswith(r"npm\codex.cmd")
    assert _resolve_executable_for_subprocess("missing-codex") == "missing-codex"


def test_codex_command_passes_output_schema_path(tmp_path: Path):
    schema = tmp_path / "schema.json"
    schema.write_text('{"type":"object"}', encoding="utf-8")
    spec = ExternalAgentRunSpec(
        provider="codex",
        prompt="return structured output",
        cwd=tmp_path,
        output_schema_path=schema,
    )

    cmd = CodexExecWorker().build_command(spec, last_message_path=tmp_path / "last.md")

    assert cmd[cmd.index("--output-schema") + 1] == str(schema.resolve())


def test_external_worker_env_defaults_to_utf8():
    env = _build_env({"OMNI_CUSTOM": "ok"})

    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["PYTHONUNBUFFERED"] == "1"
    assert env["NO_COLOR"] == "1"
    assert env["FORCE_COLOR"] == "0"
    assert env["OMNI_CUSTOM"] == "ok"


def test_codex_readonly_maps_to_read_only_sandbox(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="codex",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )
    cmd = CodexExecWorker().build_command(spec, last_message_path=tmp_path / "last.md")

    assert cmd[cmd.index("--sandbox") + 1] == "read-only"


def test_codex_json_line_parser_keeps_raw_stdout():
    events = _parse_json_lines('{"type":"message","message":"hi"}\nnot-json\n')

    assert events[0].type == "message"
    assert events[0].message == "hi"
    assert events[1].type == "stdout"
    assert events[1].message == "not-json"


def test_codex_structured_final_text_parser_accepts_schema_json():
    data = _parse_structured_final_text(
        '```json\n{"files":{"workers/demo.py":"from x import y\\nclass DemoWorker: pass\\n"}}\n```'
    )

    assert data == {"files": {"workers/demo.py": "from x import y\nclass DemoWorker: pass\n"}}


def test_codex_git_status_parser_includes_untracked_and_renames():
    paths = _parse_git_status_paths(
        " M src/changed.py\n"
        "?? docs/new.md\n"
        "R  old/name.py -> new/name.py\n"
    )

    assert paths == ["src/changed.py", "docs/new.md", "new/name.py"]


def test_codex_diff_summary_mentions_newly_changed_files():
    summary = _format_diff_summary("src/a.py | 1 +", ["docs/new.md"])

    assert "src/a.py | 1 +" in summary
    assert "Newly changed files" in summary
    assert "docs/new.md" in summary


def test_codex_readonly_rollback_restores_new_tracked_and_untracked_changes(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("before\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)

    tracked.write_text("after\n", encoding="utf-8")
    untracked = tmp_path / "new.txt"
    untracked.write_text("new\n", encoding="utf-8")

    rollback = _rollback_new_changes(tmp_path, ["tracked.txt", "new.txt"])

    assert rollback == {"rolled_back": ["tracked.txt", "new.txt"], "failed": []}
    assert tracked.read_text(encoding="utf-8") == "before\n"
    assert not untracked.exists()


def test_claude_code_options_do_not_default_to_bypass(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    kwargs = ClaudeCodeSdkWorker().build_options_kwargs(spec)
    prompt = ClaudeCodeSdkWorker().build_prompt(spec)

    assert kwargs["permission_mode"] == "default"
    assert kwargs["tools"] == ["Glob", "Grep", "LS", "Read"]
    assert kwargs["setting_sources"] == []
    assert kwargs["cwd"] == str(tmp_path.resolve())
    assert set(kwargs["disallowed_tools"]) >= {"Write", "Edit", "MultiEdit", "NotebookEdit", "Bash"}
    assert callable(kwargs["can_use_tool"])
    assert asyncio.run(kwargs["can_use_tool"]("Read", {}, None)).behavior == "allow"
    denied = asyncio.run(kwargs["can_use_tool"]("Write", {}, None))
    assert denied.behavior == "deny"
    assert denied.interrupt is True
    assert "Readonly external-worker run" in prompt


def test_claude_code_workspace_write_maps_to_accept_edits(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="implement the spec",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
    )

    kwargs = ClaudeCodeSdkWorker().build_options_kwargs(spec)

    assert kwargs["permission_mode"] == "acceptEdits"
    assert callable(kwargs["can_use_tool"])


def test_claude_code_workspace_write_allows_narrow_validation_bash(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="validate the spec output",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
    )

    can_use_tool = ClaudeCodeSdkWorker().build_options_kwargs(spec)["can_use_tool"]
    allowed = asyncio.run(
        can_use_tool(
            "Bash",
            {
                "command": (
                    'python "/scm/main/AIWorkSpace/app/tool/prefab-workstation/scripts/'
                    'lint_batch_research_outputs.py" data/out.json --strict'
                )
            },
            None,
        )
    )
    denied = asyncio.run(can_use_tool("Bash", {"command": "git reset --hard"}, None))
    non_bash = asyncio.run(can_use_tool("Read", {}, None))

    assert allowed.behavior == "allow"
    assert denied.behavior == "deny"
    assert denied.interrupt is True
    assert non_bash.behavior == "allow"


def test_claude_code_workspace_write_allows_readonly_probe_bash(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect evidence",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
    )

    can_use_tool = ClaudeCodeSdkWorker().build_options_kwargs(spec)["can_use_tool"]
    loop_probe = """for d in "战术实验室" "大富翁棋盘"; do
  echo "=== $d ==="
  ls "/scm/main/AIWorkSpace/app/tool/prefab-workstation/data/gameplay_system_ux/ontologies/$d/" 2>/dev/null
done"""
    wc_probe = (
        "wc -l data/gameplay_system_ux/ontologies/大富翁棋盘/*.yaml "
        "data/gameplay_system_ux/figma_data/战术实验室/areas.yaml"
    )
    fallback_probe = (
        'ls C:/Users/user/.claude/projects/D--scm-main-AIWorkSpace/memory/ '
        '2>/dev/null || echo "memory dir empty/missing"'
    )
    validation_with_stderr_probe = (
        "cd /d/scm/main/AIWorkSpace/app/tool/prefab-workstation && "
        "python scripts/prefab_workstation_cli.py encoding-check "
        "data/gameplay_system_ux/batch_research/component_semantics/out.json --json 2>&1"
    )
    inspect_with_head_probe = (
        "cd /d/scm/main/AIWorkSpace/app/tool/prefab-workstation && "
        "python scripts/prefab_workstation_cli.py inspect-business 战斗周边系统__characters --json 2>&1 "
        "| head -200"
    )

    assert asyncio.run(can_use_tool("Bash", {"command": loop_probe}, None)).behavior == "allow"
    assert asyncio.run(can_use_tool("Bash", {"command": wc_probe}, None)).behavior == "allow"
    assert asyncio.run(can_use_tool("Bash", {"command": fallback_probe}, None)).behavior == "allow"
    assert (
        asyncio.run(can_use_tool("Bash", {"command": validation_with_stderr_probe}, None)).behavior
        == "allow"
    )
    assert (
        asyncio.run(can_use_tool("Bash", {"command": inspect_with_head_probe}, None)).behavior
        == "allow"
    )
    denied = asyncio.run(can_use_tool("Bash", {"command": "ls data | rm -rf temp"}, None))
    assert denied.behavior == "deny"


def test_claude_code_bypass_requires_trusted_mode(tmp_path: Path):
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="trusted maintenance",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.TRUSTED_BYPASS,
    )

    kwargs = ClaudeCodeSdkWorker().build_options_kwargs(spec)

    assert kwargs["permission_mode"] == "bypassPermissions"


class _FakeClaudeOptions:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeClaudeTextMessage:
    kind = "AssistantMessage"
    content = [{"type": "text", "text": "claude fake done"}]


class _FakeClaudeResultMessage:
    kind = "ResultMessage"
    error = None


class _FakeClaudeToolUseMessage:
    def __init__(self):
        self.kind = "AssistantMessage"
        self.content = [
            {
                "id": "toolu_test_1",
                "name": "Bash",
                "input": {"command": "git status --short"},
            }
        ]


class _FakeClaudeToolResultMessage:
    def __init__(self):
        self.kind = "UserMessage"
        self.content = [
            {
                "tool_use_id": "toolu_test_1",
                "content": " M src/demo.py\n",
            }
        ]


class _FakeClaudeApiErrorResultMessage:
    def __init__(self):
        self.kind = "ResultMessage"
        self.subtype = "success"
        self.is_error = True
        self.result = "API Error: 400 invalid_request_error"
        self.error = None


class _FakeClaudeToolUseStopResultMessage:
    def __init__(self):
        self.kind = "ResultMessage"
        self.subtype = "error_during_execution"
        self.is_error = False
        self.stop_reason = "tool_use"
        self.result = None
        self.error = None


class _WritingClaudeClient:
    def __init__(self, options):
        self.options = options

    async def connect(self):
        return None

    async def query(self, prompt: str, session_id: str):
        Path(self.options.kwargs["cwd"], "claude-new.txt").write_text("new\n", encoding="utf-8")

    async def receive_response(self):
        yield _FakeClaudeTextMessage()
        yield _FakeClaudeResultMessage()

    async def disconnect(self):
        return None


class _WritingClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _WritingClaudeClient


class _EnvCapturingClaudeClient(_WritingClaudeClient):
    captured_env: dict[str, str | None] = {}

    async def query(self, prompt: str, session_id: str):
        type(self).captured_env = {
            "PYTHONUTF8": os.environ.get("PYTHONUTF8"),
            "PYTHONIOENCODING": os.environ.get("PYTHONIOENCODING"),
            "OMNI_EXTERNAL_WORKER_RUN_ID": os.environ.get("OMNI_EXTERNAL_WORKER_RUN_ID"),
        }


class _EnvCapturingClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _EnvCapturingClaudeClient


class _ApiErrorClaudeClient(_WritingClaudeClient):
    async def query(self, prompt: str, session_id: str):
        return None

    async def receive_response(self):
        yield _FakeClaudeApiErrorResultMessage()


class _ApiErrorClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _ApiErrorClaudeClient


class _ToolUseStopClaudeClient(_WritingClaudeClient):
    async def query(self, prompt: str, session_id: str):
        return None

    async def receive_response(self):
        yield _FakeClaudeToolUseStopResultMessage()


class _ToolUseStopClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _ToolUseStopClaudeClient


class _ToolTraceClaudeClient(_WritingClaudeClient):
    async def query(self, prompt: str, session_id: str):
        return None

    async def receive_response(self):
        yield _FakeClaudeToolUseMessage()
        yield _FakeClaudeToolResultMessage()
        yield _FakeClaudeTextMessage()
        yield _FakeClaudeResultMessage()


class _ToolTraceClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _ToolTraceClaudeClient


class _SessionWritingClaudeClient(_WritingClaudeClient):
    async def query(self, prompt: str, session_id: str):
        session_dir = Path(self.options.kwargs["cwd"], ".omni", "sessions")
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "claude-session.json").write_text("{}\n", encoding="utf-8")


class _SessionWritingClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _SessionWritingClaudeClient


class _IgnoredSessionWritingClaudeClient(_WritingClaudeClient):
    async def query(self, prompt: str, session_id: str):
        session_dir = Path(self.options.kwargs["cwd"], ".omni", "sessions")
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "claude-session.json").write_text("{}\n", encoding="utf-8")
        (session_dir / "_current.txt").write_text("new-session-id", encoding="utf-8")


class _IgnoredSessionWritingClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _IgnoredSessionWritingClaudeClient


class _IgnoredOutputWritingClaudeClient(_WritingClaudeClient):
    async def query(self, prompt: str, session_id: str):
        out_dir = Path(self.options.kwargs["cwd"], "data", "ontologies", "competitive_event_activity_sample_a")
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "prefab_truth.md").write_text("# readable ontology\n", encoding="utf-8")


class _IgnoredOutputWritingClaudeSdk:
    ClaudeAgentOptions = _FakeClaudeOptions
    ClaudeSDKClient = _IgnoredOutputWritingClaudeClient


@pytest.mark.asyncio
async def test_claude_code_result_is_error_marks_run_failed(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_ApiErrorClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.FAILED
    assert "API Error: 400" in result.error
    assert "API Error: 400" in result.final_text
    assert result.changed_files == []


@pytest.mark.asyncio
async def test_claude_code_error_during_tool_use_marks_run_failed(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_ToolUseStopClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.FAILED
    assert "error_during_execution" in result.error
    assert result.changed_files == []


@pytest.mark.asyncio
async def test_claude_code_readonly_guard_rolls_back_new_files(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_WritingClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.PERMISSION_VIOLATION
    assert result.changed_files == ["claude-new.txt"]
    assert "claude-new.txt" in result.diff_summary
    assert result.raw["readonly_rollback"]["rolled_back"] == ["claude-new.txt"]
    assert not (tmp_path / "claude-new.txt").exists()


@pytest.mark.asyncio
async def test_claude_code_sdk_run_temporarily_sets_utf8_env(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        env={"OMNI_EXTERNAL_WORKER_RUN_ID": "external-cli-env-test"},
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_EnvCapturingClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    env = _EnvCapturingClaudeClient.captured_env
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"
    assert env["OMNI_EXTERNAL_WORKER_RUN_ID"] == "external-cli-env-test"


@pytest.mark.asyncio
async def test_claude_code_sdk_run_mirrors_tool_events_to_events_db(tmp_path: Path, monkeypatch):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    monkeypatch.setenv("OMNICOMPANY_DB_DIR", str(tmp_path.with_name(f"{tmp_path.name}-omni-db")))
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        run_id="external-cli-trace-test",
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_ToolTraceClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    trace = result.raw["external_worker_trace"]
    assert trace["trace_id"] == "external-cli-trace-test"
    db_path = Path(trace["db_path"])
    assert db_path.name == "events.db"
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT event_type, parent_id, data FROM events WHERE trace_id=? ORDER BY timestamp",
            ("external-cli-trace-test",),
        ).fetchall()
    finally:
        conn.close()
    event_types = [row[0] for row in rows]
    assert event_types == [
        "external_agent.started",
        "agent.tool.call",
        "agent.tool.result",
        "external_agent.completed",
    ]
    call_payload = json.loads(rows[1][2])["payload"]
    result_payload = json.loads(rows[2][2])["payload"]
    assert call_payload["tool"] == "Bash"
    assert call_payload["args"]["command"] == "git status --short"
    assert result_payload["tool"] == "Bash"
    assert "src/demo.py" in result_payload["result"]
    assert rows[2][1] is not None


@pytest.mark.asyncio
async def test_claude_code_readonly_allows_and_rolls_back_session_metadata(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_SessionWritingClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    assert result.changed_files == [".omni/sessions/claude-session.json"]
    assert result.raw["readonly_allowed_changed_files"] == [".omni/sessions/claude-session.json"]
    assert not (tmp_path / ".omni" / "sessions" / "claude-session.json").exists()


@pytest.mark.asyncio
async def test_claude_code_readonly_cleans_ignored_session_metadata(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text(".omni/\n", encoding="utf-8")
    session_dir = tmp_path / ".omni" / "sessions"
    session_dir.mkdir(parents=True)
    (session_dir / "existing.json").write_text("{}\n", encoding="utf-8")
    (session_dir / "_current.txt").write_text("previous-session-id", encoding="utf-8")
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_IgnoredSessionWritingClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    assert result.changed_files == []
    cleanup = result.raw["readonly_ignored_session_cleanup"]
    assert cleanup["removed"] == [".omni/sessions/claude-session.json"]
    assert cleanup["restored"] == [".omni/sessions/_current.txt"]
    assert cleanup["failed"] == []
    assert (session_dir / "existing.json").exists()
    assert not (session_dir / "claude-session.json").exists()
    assert (session_dir / "_current.txt").read_text(encoding="utf-8") == "previous-session-id"


@pytest.mark.asyncio
async def test_claude_code_workspace_write_reports_watched_ignored_outputs(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    watch_path = Path("data/ontologies/competitive_event_activity_sample_a")
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="write ontology",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
        watch_paths=[watch_path],
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_IgnoredOutputWritingClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    assert result.changed_files == []
    assert result.raw["watch_paths"] == [watch_path.as_posix()]
    changes = result.raw["watched_path_changes"]
    assert changes["has_changes"] is True
    assert "data/ontologies/competitive_event_activity_sample_a" in changes["created"]
    assert "data/ontologies/competitive_event_activity_sample_a/prefab_truth.md" in changes["created"]
    assert "Watched path changes detected" in result.diff_summary


@pytest.mark.asyncio
async def test_claude_code_readonly_rolls_back_watched_ignored_outputs(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / ".gitignore").write_text("data/\n", encoding="utf-8")
    watch_path = Path("data/ontologies/competitive_event_activity_sample_a")
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect only",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        watch_paths=[watch_path],
    )

    result = await ClaudeCodeSdkWorker(sdk_module=_IgnoredOutputWritingClaudeSdk).run(spec)

    assert result.status == ExternalAgentStatus.PERMISSION_VIOLATION
    assert result.raw["watched_path_changes"]["has_changes"] is True
    assert not (tmp_path / watch_path).exists()


def test_watch_path_snapshot_reports_modified_ignored_file(tmp_path: Path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    watch_dir = tmp_path / "data"
    watch_dir.mkdir()
    target = watch_dir / "existing.md"
    target.write_text("before\n", encoding="utf-8")

    before = _snapshot_watch_paths(tmp_path, [watch_dir])
    target.write_text("after\n", encoding="utf-8")
    after = _snapshot_watch_paths(tmp_path, [watch_dir])
    changes = _diff_watch_snapshots(before, after)

    assert changes["created"] == []
    assert changes["deleted"] == []
    assert changes["modified"] == ["data/existing.md"]


def test_default_external_worker_registry_is_explicit():
    registry = build_default_external_agent_worker_registry()

    assert registry.list_providers() == ["claude-code", "codex"]
    assert isinstance(registry.create("codex"), CodexExecWorker)
    assert isinstance(registry.create("claude-code"), ClaudeCodeSdkWorker)


def test_external_agent_runner_resolves_cheap_models():
    assert (
        resolve_external_agent_model(
            provider="codex",
            permission_mode=ExternalAgentPermissionMode.READONLY,
        )
        == "gpt-5.3-codex-spark"
    )
    assert (
        resolve_external_agent_model(
            provider="codex",
            permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
        )
        == "gpt-5.4-mini"
    )
    assert resolve_external_agent_model(provider="claude-code", permission_mode="readonly") is None
    assert (
        resolve_external_agent_model(
            provider="codex",
            permission_mode="readonly",
            model_policy="none",
        )
        is None
    )


@pytest.mark.asyncio
async def test_external_agent_runner_uses_request_contract(tmp_path: Path):
    captured: dict[str, ExternalAgentRunSpec] = {}
    registry = ExternalAgentWorkerRegistry()
    registry.register("capturing", lambda **kw: _CapturingExternalAgentWorker(captured, **kw))
    request = ExternalAgentRunRequest(
        provider="capturing",
        prompt="run through entrypoint",
        cwd=tmp_path,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        attached_context=["context from workflow"],
        metadata={"caller": "unit-test"},
    )

    result = await run_external_agent_request(request, worker_registry=registry)

    assert result.status == ExternalAgentStatus.SUCCEEDED
    assert result.provider == "capturing"
    spec = captured["spec"]
    assert "context from workflow" in spec.attached_context
    assert spec.prompt == "run through entrypoint"
    assert spec.metadata["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert spec.metadata["agent_spawn_entry"] == ENTRY_EXTERNAL_WORKER_RUN
    assert spec.metadata["agent_spawn_kind"] == "external-worker"
    assert spec.metadata["entrypoint"] == "external_agent_runner"
    assert spec.metadata["runner_entrypoint"] == "external_agent_runner"
    assert spec.metadata["caller"] == "unit-test"


@pytest.mark.asyncio
async def test_external_agent_worker_node_runs_fake_worker(tmp_path: Path):
    captured: dict[str, ExternalAgentRunSpec] = {}
    registry = ExternalAgentWorkerRegistry()
    registry.register("capturing", lambda **kw: _CapturingExternalAgentWorker(captured, **kw))
    node = ExternalAgentWorkerNode(
        provider="capturing",
        cwd=tmp_path,
        worker_registry=registry,
        permission_mode=ExternalAgentPermissionMode.READONLY,
    )

    verdict = node.run({"prompt": "workflow node task", "attached_context": ["node ctx"]})

    assert verdict.kind == VerdictKind.PASS
    assert verdict.output["external_agent"]["provider"] == "capturing"
    assert verdict.output["external_agent"]["status"] == "succeeded"
    spec = captured["spec"]
    assert spec.prompt == "workflow node task"
    assert spec.attached_context == ["node ctx"]
    assert spec.metadata["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert spec.metadata["agent_spawn_entry"] == ENTRY_TEAMRUNNER_NODE
    assert spec.metadata["agent_spawn_launch_surface"] is False
    assert spec.metadata["entrypoint"] == "teamrunner_workflow_node"
    assert spec.metadata["runner_entrypoint"] == "external_agent_runner"


@pytest.mark.asyncio
async def test_external_agent_worker_node_is_teamrunner_binding(tmp_path: Path):
    registry = ExternalAgentWorkerRegistry()
    registry.register("fake", lambda **kw: FakeExternalAgentWorker())
    pipeline = PipelineSpec(
        id="external-agent-node-test",
        name="External Agent Node Test",
        description="Verify external worker node can run in TeamRunner.",
        nodes=[
            PipelineNode(
                id="external_worker",
                kind=NodeKind.ANCHOR,
                anchor=AnchorSpec(
                    id="external_worker",
                    name="ExternalWorker",
                    format_in="external_agent.request",
                    format_out="external_agent.result",
                    validator=ValidatorSpec(
                        id="external_worker_validator",
                        kind=ValidatorKind.HARD,
                        description="external worker completed",
                    ),
                    routes={VerdictKind.PASS: Route(action=RouteAction.EMIT)},
                ),
                maturity=NodeMaturity.CRYSTALLIZED,
            )
        ],
        edges=[],
        entry="external_worker",
    )
    bus = MemoryBus()
    await bus.connect()
    try:
        runner = PipelineRunner(
            pipeline=pipeline,
            bindings={
                "external_worker": ExternalAgentWorkerNode(
                    provider="fake",
                    cwd=tmp_path,
                    worker_registry=registry,
                )
            },
            bus=bus,
            max_steps=5,
        )

        result = await runner.run({"prompt": "from TeamRunner"})
    finally:
        await bus.close()

    assert result["external_agent"]["provider"] == "fake"
    assert result["external_agent"]["status"] == "succeeded"
    assert "from TeamRunner" in result["text"]


class PermissionViolationWorker(ExternalAgentWorker):
    provider_name = "violating"

    async def _run_impl(self, spec: ExternalAgentRunSpec) -> ExternalAgentResult:
        return ExternalAgentResult(
            run_id=spec.run_id,
            provider=self.provider_name,
            status=ExternalAgentStatus.PERMISSION_VIOLATION,
            final_text="looked but should not have written",
            changed_files=["unexpected.txt"],
            error="readonly permission violation",
        )


@pytest.mark.asyncio
async def test_external_agent_subagent_wraps_worker_result(tmp_path: Path):
    captured: dict[str, ExternalAgentRunSpec] = {}
    registry = ExternalAgentWorkerRegistry()
    registry.register("capturing", lambda **kw: _CapturingExternalAgentWorker(captured, **kw))
    subagent = ExternalAgentSubAgent(
        provider="capturing",
        cwd=tmp_path,
        worker_registry=registry,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        model="gpt-test",
    )

    verdict = await subagent.run({
        "task": "inspect this",
        "trace_id": "trace.parent.spawn.fake",
        "description": "fake external",
    })

    assert verdict.kind.value == "pass"
    assert verdict.output["provider"] == "capturing"
    assert verdict.details["external_agent"] is True
    spec = captured["spec"]
    assert spec.prompt == "inspect this"
    assert spec.metadata["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert spec.metadata["agent_spawn_entry"] == ENTRY_EXTERNAL_WORKER_AS_AGENT
    assert spec.metadata["agent_spawn_launch_surface"] is False
    assert spec.metadata["subagent_type"] == "capturing"


@pytest.mark.asyncio
async def test_external_agent_subagent_permission_violation_is_partial(tmp_path: Path):
    registry = ExternalAgentWorkerRegistry()
    registry.register("violating", lambda **kw: PermissionViolationWorker())
    subagent = ExternalAgentSubAgent(
        provider="violating",
        cwd=tmp_path,
        worker_registry=registry,
    )

    verdict = await subagent.run({"task": "readonly task"})

    assert verdict.kind.value == "partial"
    assert "permission violation" in verdict.diagnosis
    assert verdict.output["changed_files"] == ["unexpected.txt"]


def test_external_agent_subagent_registry_can_feed_agent_router(tmp_path: Path):
    registry = ExternalAgentWorkerRegistry()
    registry.register("fake", lambda **kw: FakeExternalAgentWorker())
    ctx = ToolContext(cwd=str(tmp_path), project_root=str(tmp_path), trace_id="trace.parent")
    ctx.subagent_registry = build_external_agent_subagent_registry(
        cwd=tmp_path,
        worker_registry=registry,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        model_by_provider={"fake": "gpt-test"},
    )
    router = AgentRouter.__new__(AgentRouter)

    out = router._execute(
        {
            "description": "external fake",
            "prompt": "answer through fake worker",
            "subagent_type": "fake",
        },
        ctx,
    )

    assert "fake external agent received" in out
    assert "answer through fake worker" in out
