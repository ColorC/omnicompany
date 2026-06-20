"""Tests for the current OmniSentinel daemon/shim contract.

The old in-process thread sentinel was retired. The live implementation exposes
module-level daemon helpers and keeps ``OmniSentinel`` only as a compatibility
shim, so these tests avoid thread-only fields and never spawn a real daemon.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from omnicompany.packages.services._core.guardian import sentinel
from omnicompany.packages.services._core.guardian.sentinel import OmniSentinel


@pytest.fixture(autouse=True)
def reset_singleton():
    OmniSentinel._instance = None
    yield
    OmniSentinel._instance = None


class TestStateFiles:
    def test_pid_file_roundtrip(self, tmp_path: Path):
        sentinel.write_pid_file(tmp_path, pid=12345)
        assert sentinel.read_pid_file(tmp_path) == 12345

        sentinel.clear_pid_file(tmp_path)
        assert sentinel.read_pid_file(tmp_path) is None

    def test_activity_ts_written(self, tmp_path: Path):
        sentinel.write_activity_ts(tmp_path, source="unit-test")

        data = sentinel._read_json(tmp_path / ".omni" / "core_activity_ts.json")
        assert data["source"] == "unit-test"
        assert sentinel.read_activity_ts(tmp_path) is not None

    def test_sentinel_state_defaults_and_roundtrip(self, tmp_path: Path):
        initial = sentinel.read_sentinel_state(tmp_path)
        assert initial["last_patrol_ts"] == ""
        assert initial["patrol_count"] == 0

        sentinel.write_sentinel_state(
            tmp_path,
            {"last_patrol_ts": "2026-01-01T00:00:00+00:00", "patrol_count": 7},
        )
        loaded = sentinel.read_sentinel_state(tmp_path)
        assert loaded["last_patrol_ts"] == "2026-01-01T00:00:00+00:00"
        assert loaded["patrol_count"] == 7

    def test_daemon_status_dead_without_pid(self, tmp_path: Path):
        status = sentinel.daemon_status(tmp_path)
        assert status["alive"] is False
        assert status["pid"] is None
        assert status["version"] == sentinel.__version__


class TestDaemonControl:
    def test_recursion_guard_prevents_spawn(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv(sentinel._RECURSION_GUARD_ENV, "1")

        with patch.object(sentinel.subprocess, "Popen") as popen:
            assert sentinel.ensure_daemon_running(tmp_path) is True
            popen.assert_not_called()

    def test_ensure_noops_when_daemon_alive(self, tmp_path: Path):
        with (
            patch.object(sentinel, "is_daemon_alive", return_value=True),
            patch.object(sentinel.subprocess, "Popen") as popen,
        ):
            assert sentinel.ensure_daemon_running(tmp_path) is True
            popen.assert_not_called()

    def test_stop_without_pid_is_safe(self, tmp_path: Path):
        assert sentinel.stop_daemon(tmp_path) is True
        assert sentinel.read_pid_file(tmp_path) is None


class TestShim:
    def test_get_instance_returns_same_object(self, tmp_path: Path):
        a = OmniSentinel.get_instance(project_root=tmp_path)
        b = OmniSentinel.get_instance(project_root=tmp_path)
        assert a is b

    def test_is_alive_delegates_to_daemon_state(self, tmp_path: Path):
        shim = OmniSentinel.get_instance(project_root=tmp_path)
        with patch.object(sentinel, "is_daemon_alive", return_value=True) as alive:
            assert shim.is_alive() is True
            alive.assert_called_once_with(tmp_path)

    def test_start_delegates_to_ensure_daemon_running(self, tmp_path: Path):
        shim = OmniSentinel.get_instance(project_root=tmp_path)
        with patch.object(sentinel, "ensure_daemon_running", return_value=True) as ensure:
            shim.start(daemon=True, interval_seconds=3600)
            ensure.assert_called_once_with(tmp_path)

    def test_stop_delegates_to_stop_daemon(self, tmp_path: Path):
        shim = OmniSentinel.get_instance(project_root=tmp_path)
        with patch.object(sentinel, "stop_daemon", return_value=True) as stop:
            shim.stop()
            stop.assert_called_once_with(tmp_path)

    def test_refresh_stops_daemon(self, tmp_path: Path):
        shim = OmniSentinel.get_instance(project_root=tmp_path)
        with patch.object(sentinel, "stop_daemon", return_value=True) as stop:
            shim.refresh()
            stop.assert_called_once_with(tmp_path)

    def test_needs_refresh_is_false_for_process_daemon_model(self, tmp_path: Path):
        shim = OmniSentinel.get_instance(project_root=tmp_path)
        assert shim.needs_refresh() is False

    def test_status_delegates_to_daemon_status(self, tmp_path: Path):
        shim = OmniSentinel.get_instance(project_root=tmp_path)
        expected = {"alive": False, "version": sentinel.__version__}
        with patch.object(sentinel, "daemon_status", return_value=expected) as status:
            assert shim.status() == expected
            status.assert_called_once_with(tmp_path)


class TestRunnerIntegration:
    def test_runner_pings_activity_without_spawning_daemon(self):
        from omnicompany.runtime.exec.runner import _ensure_guardian_running

        with (
            patch.object(sentinel, "write_activity_ts") as write_activity,
            patch.object(sentinel, "ensure_daemon_running") as ensure,
        ):
            _ensure_guardian_running()

        write_activity.assert_called_once_with(source="pipeline-runner")
        ensure.assert_not_called()

    def test_runner_swallows_sentinel_errors(self):
        from omnicompany.runtime.exec.runner import _ensure_guardian_running

        with patch.object(sentinel, "write_activity_ts", side_effect=RuntimeError("boom")):
            _ensure_guardian_running()
