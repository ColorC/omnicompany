# [OMNI] origin=codex domain=tests/cli ts=2026-05-17 type=test
"""Tests for `omni worker` external-agent CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from omnicompany.packages.services._core.agent.external_workers import (
    ExternalAgentResult,
    ExternalAgentStatus,
)
from omnicompany.packages.services._core.agent.spawn_surface import (
    AGENT_SPAWN_SURFACE_VERSION,
    ENTRY_EXTERNAL_WORKER_RUN,
)


def test_worker_providers_lists_codex_and_claude() -> None:
    from omnicompany.cli.commands.worker import cmd_worker

    result = CliRunner().invoke(cmd_worker, ["providers", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    providers = {item["provider"]: item for item in payload["items"]}
    assert "codex" in providers
    assert "claude-code" in providers
    assert providers["codex"]["cheap_readonly_model"] == "gpt-5.3-codex-spark"
    assert providers["claude-code"]["cheap_readonly_model"] is None
    assert "readonly" in payload["permission_modes"]


def test_worker_run_builds_request_from_spec_context_and_metadata(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omnicompany.cli.commands import worker as worker_mod
    from omnicompany.cli.commands.worker import cmd_worker

    spec = tmp_path / "spec.md"
    spec.write_text("# Build Spec\n\nGenerate the worker body.", encoding="utf-8")
    context = tmp_path / "context.md"
    context.write_text("Existing API: use VerdictKind.PASS.", encoding="utf-8")
    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return ExternalAgentResult(
            run_id="external-cli-test",
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="worker done",
            changed_files=[],
            raw={"ok": True},
        )

    monkeypatch.setattr(worker_mod, "run_external_agent_request", fake_run)

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--spec",
            str(spec),
            "--context",
            str(context),
            "--context-text",
            "Review surface: unit tests only.",
            "--metadata",
            "role=codegen",
            "--env",
            "OMNI_TEST=1",
            "--watch-path",
            "data/ontologies/competitive_event_activity_sample_a",
            "--cwd",
            str(tmp_path),
            "--permission",
            "readonly",
            "--timeout",
            "30",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["run_id"] == "external-cli-test"
    assert payload["status"] == "succeeded"
    request = captured["request"]
    assert request.provider == "claude-code"
    assert "Generate the worker body" in request.prompt
    assert str(spec.resolve()) in request.prompt
    assert request.cwd == tmp_path.resolve()
    assert request.permission_mode.value == "readonly"
    assert request.timeout_s == 30
    assert len(request.attached_context) == 2
    assert "Existing API" in request.attached_context[0]
    assert "Review surface" in request.attached_context[1]
    assert request.metadata["agent_spawn_surface"] == AGENT_SPAWN_SURFACE_VERSION
    assert request.metadata["agent_spawn_entry"] == ENTRY_EXTERNAL_WORKER_RUN
    assert request.metadata["agent_spawn_kind"] == "external-worker"
    assert request.metadata["cli_entrypoint"] == "omni_worker_run"
    assert request.metadata["role"] == "codegen"
    assert request.env["OMNI_TEST"] == "1"
    assert request.env["OMNI_EXTERNAL_WORKER_PROVIDER"] == "claude-code"
    assert request.env["OMNI_EXTERNAL_WORKER_RUN_ID"].startswith("external-cli-")
    assert [path.as_posix() for path in request.watch_paths] == [
        "data/ontologies/competitive_event_activity_sample_a"
    ]


def test_worker_run_reads_stdin(tmp_path: Path, monkeypatch) -> None:
    from omnicompany.cli.commands import worker as worker_mod
    from omnicompany.cli.commands.worker import cmd_worker

    captured = {}

    async def fake_run(request):
        captured["prompt"] = request.prompt
        return ExternalAgentResult(
            run_id="external-stdin",
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="ok",
        )

    monkeypatch.setattr(worker_mod, "run_external_agent_request", fake_run)

    result = CliRunner().invoke(
        cmd_worker,
        ["run", "claude-code", "--stdin", "--cwd", str(tmp_path), "--json"],
        input="stdin spec body",
    )

    assert result.exit_code == 0, result.output
    assert captured["prompt"] == "stdin spec body"


def test_worker_run_writes_utf8_run_record(tmp_path: Path, monkeypatch) -> None:
    from omnicompany.cli.commands import worker as worker_mod
    from omnicompany.cli.commands.worker import cmd_worker

    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return ExternalAgentResult(
            run_id=request.run_id,
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="结构化返回正常",
        )

    monkeypatch.setattr(worker_mod, "run_external_agent_request", fake_run)
    run_root = tmp_path / "worker-runs"

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--prompt",
            "请读取白膜文档并输出中文结论。",
            "--context-text",
            "上下文：白膜文档是协作平台 wiki 文档，不是本地 Markdown。",
            "--cwd",
            str(tmp_path),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    run_dir = run_root / request.run_id
    assert run_dir.is_dir()
    assert (run_dir / "prompt.md").read_text(encoding="utf-8") == "请读取白膜文档并输出中文结论。"
    assert "协作平台 wiki" in (run_dir / "context_01.md").read_text(encoding="utf-8")
    assert (run_dir / "prompt.md").read_bytes()[:3] != b"\xef\xbb\xbf"
    request_record = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    result_record = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
    assert request_record["provider"] == "claude-code"
    assert request_record["attached_context_count"] == 1
    assert result_record["run_id"] == request.run_id
    assert result_record["run_record_dir"] == str(run_dir)


def test_worker_run_replaces_invalid_surrogates_before_writing_run_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omnicompany.cli.commands import worker as worker_mod
    from omnicompany.cli.commands.worker import cmd_worker

    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return ExternalAgentResult(
            run_id=request.run_id,
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="ok",
        )

    monkeypatch.setattr(worker_mod, "run_external_agent_request", fake_run)
    run_root = tmp_path / "worker-runs"

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--prompt",
            "bad\udcbftext",
            "--context-text",
            "ctx\udcbftext",
            "--cwd",
            str(tmp_path),
            "--run-root",
            str(run_root),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    run_dir = run_root / request.run_id
    assert "\udcbf" not in request.prompt
    assert "\udcbf" not in request.attached_context[0]
    assert (run_dir / "prompt.md").read_text(encoding="utf-8") == "bad?text"
    assert (run_dir / "context_01.md").read_text(encoding="utf-8") == "ctx?text"


def test_worker_run_attaches_chinese_context_with_ascii_alias(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omnicompany.cli.commands import worker as worker_mod
    from omnicompany.cli.commands.worker import cmd_worker

    context = tmp_path / "核心差距与后续Spec补充.md"
    context.write_text("中文路径上下文正文", encoding="utf-8")
    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return ExternalAgentResult(
            run_id="external-context-alias",
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="ok",
        )

    monkeypatch.setattr(worker_mod, "run_external_agent_request", fake_run)

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--prompt",
            "Use attached alias gap_doc. Do not re-read the Chinese path.",
            "--context-alias",
            f"gap_doc={context}",
            "--cwd",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    request = captured["request"]
    assert len(request.attached_context) == 1
    attached = request.attached_context[0]
    assert "# Attached context alias: gap_doc" in attached
    assert "核心差距与后续Spec补充.md" in attached
    assert "中文路径上下文正文" in attached


def test_worker_run_resolves_context_alias_relative_to_worker_cwd(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from omnicompany.cli.commands import worker as worker_mod
    from omnicompany.cli.commands.worker import cmd_worker

    context_dir = tmp_path / "docs"
    context_dir.mkdir()
    context = context_dir / "guide.md"
    context.write_text("相对 worker cwd 的上下文", encoding="utf-8")
    captured = {}

    async def fake_run(request):
        captured["request"] = request
        return ExternalAgentResult(
            run_id=request.run_id,
            provider=request.provider,
            status=ExternalAgentStatus.SUCCEEDED,
            final_text="ok",
        )

    monkeypatch.setattr(worker_mod, "run_external_agent_request", fake_run)

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--prompt",
            "inspect",
            "--context-alias",
            "guide=docs/guide.md",
            "--cwd",
            str(tmp_path),
            "--json",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
    assert "相对 worker cwd 的上下文" in captured["request"].attached_context[0]


def test_worker_run_rejects_non_ascii_context_alias(tmp_path: Path) -> None:
    from omnicompany.cli.commands.worker import cmd_worker

    context = tmp_path / "ctx.md"
    context.write_text("context", encoding="utf-8")

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--prompt",
            "inspect",
            "--context-alias",
            f"中文={context}",
            "--cwd",
            str(tmp_path),
            "--json",
        ],
    )

    assert result.exit_code != 0
    assert "ASCII" in result.output


def test_worker_run_rejects_unconfirmed_trusted_bypass(tmp_path: Path) -> None:
    from omnicompany.cli.commands.worker import cmd_worker

    result = CliRunner().invoke(
        cmd_worker,
        [
            "run",
            "claude-code",
            "--prompt",
            "dangerous task",
            "--cwd",
            str(tmp_path),
            "--permission",
            "trusted-bypass",
        ],
    )

    assert result.exit_code != 0
    assert "--allow-trusted-bypass" in result.output


def test_worker_run_requires_task(tmp_path: Path) -> None:
    from omnicompany.cli.commands.worker import cmd_worker

    result = CliRunner().invoke(
        cmd_worker,
        ["run", "claude-code", "--cwd", str(tmp_path), "--json"],
    )

    assert result.exit_code != 0
    assert "--spec, --stdin, or --prompt" in result.output


def test_worker_trace_reads_external_worker_events_db(tmp_path: Path, monkeypatch) -> None:
    from omnicompany.cli.commands.worker import cmd_worker
    from omnicompany.packages.services._core.agent.external_workers import ExternalAgentRunSpec
    from omnicompany.packages.services._core.agent.external_workers.trace import ExternalWorkerTraceMirror

    monkeypatch.setenv("OMNICOMPANY_DB_DIR", str(tmp_path / "omni-db"))
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt="inspect",
        cwd=tmp_path,
        run_id="external-cli-trace-cli-test",
    )
    mirror = ExternalWorkerTraceMirror(spec)
    mirror.emit("agent.tool.call", {"tool": "Bash", "args": {"command": "pwd"}})

    result = CliRunner().invoke(
        cmd_worker,
        ["trace", "external-cli-trace-cli-test", "--db", "events", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["trace_id"] == "external-cli-trace-cli-test"
    assert payload["total"] == 1
    assert payload["items"][0]["event_type"] == "agent.tool.call"
    assert payload["items"][0]["payload"]["tool"] == "Bash"
