from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from omnicompany.packages.services._core.agent.external_workers import (
    ExternalAgentResult,
    ExternalAgentStatus,
)
from omnicompany.packages.services._core.agent.spawn_surface import (
    AGENT_SPAWN_SURFACE_VERSION,
    ENTRY_EXTERNAL_WORKER_RUN,
)


def _client() -> TestClient:
    from omnicompany.dashboard.controlplane.external_agents import external_agents_router

    app = FastAPI()
    app.include_router(external_agents_router, prefix="/api/v2")
    return TestClient(app)


def test_external_agent_providers_lists_codex_and_claude():
    client = _client()

    response = client.get("/api/v2/external-agents/providers")

    assert response.status_code == 200
    payload = response.json()
    providers = {item["provider"]: item for item in payload["items"]}
    assert "codex" in providers
    assert "claude-code" in providers
    assert providers["codex"]["cheap_readonly_model"] == "gpt-5.3-codex-spark"
    assert providers["codex"]["cheap_write_model"] == "gpt-5.4-mini"
    assert "readonly" in payload["permission_modes"]


def test_external_agent_run_api_uses_runner_contract(monkeypatch, tmp_path):
    from omnicompany.dashboard.controlplane import external_agents

    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return ExternalAgentResult(
            run_id="external-test",
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="fake result",
            changed_files=[],
            raw={"ok": True},
        )

    monkeypatch.setattr(external_agents, "run_external_agent_request", fake_run)
    client = _client()

    response = client.post(
        "/api/v2/external-agents/runs",
        json={
            "provider": "codex",
            "prompt": "read only please",
            "cwd": str(tmp_path),
            "permission_mode": "readonly",
            "attached_context": ["ctx"],
            "metadata": {"caller": "test"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "external-test"
    assert payload["status"] == "succeeded"
    assert payload["final_text"] == "fake result"
    request = captured["request"]
    assert request.provider == "codex"
    assert request.prompt == "read only please"
    assert request.cwd == tmp_path.resolve()
    assert request.attached_context == ["ctx"]
    assert request.metadata["caller"] == "test"
    assert request.metadata["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert request.metadata["agent_spawn_entry"] == ENTRY_EXTERNAL_WORKER_RUN
    assert request.metadata["agent_spawn_kind"] == "external-worker"
    assert request.metadata["entrypoint"] == "dashboard_controlplane"


def test_external_agent_run_rejects_unconfirmed_trusted_bypass(tmp_path):
    client = _client()

    response = client.post(
        "/api/v2/external-agents/runs",
        json={
            "provider": "codex",
            "prompt": "dangerous task",
            "cwd": str(tmp_path),
            "permission_mode": "trusted-bypass",
        },
    )

    assert response.status_code == 400
    assert "allow_trusted_bypass" in response.json()["detail"]


def test_external_agent_run_rejects_missing_cwd():
    client = _client()

    response = client.post(
        "/api/v2/external-agents/runs",
        json={
            "provider": "codex",
            "prompt": "read",
            "cwd": "does-not-exist-for-external-agent-test",
        },
    )

    assert response.status_code == 400
    assert "cwd must be an existing directory" in response.json()["detail"]


def test_codex_provider_maps_dashboard_permission_modes():
    from omnicompany.dashboard.ccdaemon.providers.codex import _codex_thread_permission_options

    assert _codex_thread_permission_options("default") == {
        "sandbox_mode": "workspace-write",
        "approval_policy": "untrusted",
    }
    assert _codex_thread_permission_options("acceptEdits") == {
        "sandbox_mode": "workspace-write",
        "approval_policy": "never",
    }
    assert _codex_thread_permission_options("bypassPermissions") == {
        "sandbox_mode": "danger-full-access",
        "approval_policy": "never",
    }


def test_codex_provider_accepts_file_change_in_progress_events():
    from omnicompany.dashboard.ccdaemon.providers.codex import CodexProvider, _patch_codex_sdk_parser
    import openai_codex_sdk.thread as sdk_thread

    _patch_codex_sdk_parser()
    line = (
        '{"type":"item.updated","item":{"id":"fc_1","type":"file_change",'
        '"changes":[{"path":"README.md","kind":"update"}],"status":"in_progress"}}'
    )
    event = sdk_thread.parse_thread_event_line(line)
    provider = CodexProvider({"cwd": "."})

    out = provider._event_to_normalized(event, "chat-test")

    assert out == [{
        "kind": "tool_use",
        "toolId": "fc_1",
        "toolName": "edit",
        "input": {
            "changes": [{"path": "README.md", "kind": "update"}],
            "status": "in_progress",
        },
        "sessionId": "chat-test",
    }]


def test_codex_provider_accepts_command_declined_events():
    from omnicompany.dashboard.ccdaemon.providers.codex import CodexProvider, _patch_codex_sdk_parser
    import openai_codex_sdk.thread as sdk_thread

    _patch_codex_sdk_parser()
    line = (
        '{"type":"item.completed","item":{"id":"cmd_1","type":"command_execution",'
        '"command":"Remove-Item codex_temp_restate_test.md",'
        '"aggregated_output":"","exit_code":null,"status":"declined"}}'
    )
    event = sdk_thread.parse_thread_event_line(line)
    provider = CodexProvider({"cwd": "."})

    out = provider._event_to_normalized(event, "chat-test")

    assert out == [
        {
            "kind": "tool_use",
            "toolId": "cmd_1",
            "toolName": "Bash",
            "input": {"command": "Remove-Item codex_temp_restate_test.md"},
            "sessionId": "chat-test",
        },
        {
            "kind": "tool_result",
            "toolId": "cmd_1",
            "result": "",
            "isError": False,
            "exitCode": 0,
            "sessionId": "chat-test",
        },
    ]


def test_codex_sdk_stdout_reader_accepts_large_json_lines(monkeypatch):
    from omnicompany.dashboard.ccdaemon.providers.codex import _patch_codex_sdk_stdout_reader
    import openai_codex_sdk.exec as sdk_exec

    class FakeStdin:
        def write(self, _data):
            pass

        async def drain(self):
            pass

        def close(self):
            pass

    class FakeStdout:
        def __init__(self):
            self._chunks = [b'{"type":"item.completed","payload":"', b"x" * 80_000, b'"}\n', b""]

        async def read(self, _size):
            return self._chunks.pop(0)

    class FakeStderr:
        async def read(self, _size):
            return b""

    class FakeProc:
        def __init__(self):
            self.stdin = FakeStdin()
            self.stdout = FakeStdout()
            self.stderr = FakeStderr()
            self.returncode = None

        async def wait(self):
            self.returncode = 0
            return 0

        def kill(self):
            self.returncode = -9

    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    _patch_codex_sdk_stdout_reader()

    async def collect():
        runner = sdk_exec.CodexExec(executable_path="codex")
        args = sdk_exec.CodexExecArgs(input="hi")
        return [line async for line in runner.run(args)]

    lines = asyncio.run(collect())

    assert len(lines) == 1
    assert len(lines[0]) > 80_000
