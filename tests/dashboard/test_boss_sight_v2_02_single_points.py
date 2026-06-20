"""BOSS SIGHT v2-02: single-authority contracts."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner


def test_caller_identity_is_access_control_authority(monkeypatch) -> None:
    from omnicompany.cli import _access
    from omnicompany.core import caller_identity

    assert _access.CALLER_ENV is caller_identity.CALLER_ENV
    assert _access.KNOWN_CALLERS is caller_identity.KNOWN_CALLERS
    assert _access.DEFAULT_CALLER is caller_identity.DEFAULT_CALLER

    monkeypatch.setenv(caller_identity.CALLER_ENV, caller_identity.CALLER_SUBAGENT)
    assert _access.current_caller() == caller_identity.CALLER_SUBAGENT

    monkeypatch.setenv(caller_identity.CALLER_ENV, "unknown")
    assert _access.current_caller() == caller_identity.CALLER_EXTERNAL


def test_worker_contract_drives_router_and_cli_choices() -> None:
    from omnicompany.cli.main import cli
    from omnicompany.dashboard.boss_sight.controller.tools import SpawnSubagentRouter
    from omnicompany.dashboard.boss_sight.controller.worker_contract import (
        PROVIDER_CLAUDE_CODE,
        STANDALONE_WORKER_PROVIDERS,
        WORKER_KIND_STANDALONE,
        WORKER_KINDS,
    )

    schema = SpawnSubagentRouter.INPUT_SCHEMA["properties"]
    assert schema["worker_kind"]["enum"] == list(WORKER_KINDS)
    assert schema["provider"]["enum"] == list(STANDALONE_WORKER_PROVIDERS)

    worker = cli.commands["worker"]
    spawn = worker.commands["spawn"]
    params = {param.name: param for param in spawn.params}
    assert tuple(params["worker_kind"].type.choices) == WORKER_KINDS
    assert params["worker_kind"].default == WORKER_KIND_STANDALONE
    assert tuple(params["provider"].type.choices) == STANDALONE_WORKER_PROVIDERS
    assert params["provider"].default == PROVIDER_CLAUDE_CODE

    result = CliRunner().invoke(cli, ["worker", "spawn", "--help"])
    assert result.exit_code == 0, result.output


def test_model_resolver_is_controller_model_authority() -> None:
    from omnicompany.dashboard.boss_sight.controller import model_resolver
    from omnicompany.dashboard.boss_sight.controller.worker import BossSightControllerWorker
    from omnicompany.dashboard.boss_sight.controller.worker_contract import (
        PROVIDER_CLAUDE_CODE,
        PROVIDER_CODEX,
        STANDALONE_WORKER_PROVIDERS,
    )

    assert BossSightControllerWorker.DEFAULT_MODEL == model_resolver.CONTROLLER_DEFAULT_MODEL
    assert model_resolver.resolve_model(PROVIDER_CLAUDE_CODE, "high") == (
        model_resolver.CONTROLLER_DEFAULT_MODEL
    )
    assert model_resolver.resolve_model(PROVIDER_CODEX, "low") == "gpt-5.3-codex"
    assert model_resolver.resolve_model(PROVIDER_CODEX, "default") is None
    assert model_resolver.resolve_model(PROVIDER_CODEX, "invalid") is None
    assert set(model_resolver.CTX_CAP_BY_PROVIDER) == set(STANDALONE_WORKER_PROVIDERS)


def test_workspace_root_single_authority_for_dashboard_modules(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    monkeypatch.setenv("OMNI_WORKSPACE_ROOT", str(root))
    monkeypatch.delenv("OMNI_CC_DAEMON_STATE_DIR", raising=False)

    from omnicompany.dashboard.boss_sight.controller import prompt_builder
    from omnicompany.dashboard.ccdaemon import context_progressive
    from omnicompany.dashboard.ccdaemon import lifecycle
    from omnicompany.dashboard.ccdaemon import pty
    from omnicompany.dashboard.ccdaemon import write_scope
    from omnicompany.dashboard.controlplane import plans

    assert write_scope.repo_root() == root
    assert context_progressive.repo_root() == root
    assert lifecycle._data_dir() == root / "data"
    assert pty._meta_store_path() == root / "data" / "cc_sessions.json"
    assert plans._project_root() == root
    assert prompt_builder._default_workspace_root() == str(root)
