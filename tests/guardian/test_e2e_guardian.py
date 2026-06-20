"""OmniGuardian E2E coverage against the current project layout.

These tests intentionally exercise the real project root for patrol, OmniMark,
tow tickets, archmap/guarded-write policy, and the current sentinel shim.
They avoid retired APIs and do not start a real long-lived daemon.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@pytest.fixture(scope="module")
def patrol_result() -> dict:
    from omnicompany.packages.services._core.guardian import run_patrol

    return run_patrol(
        project_root=str(PROJECT_ROOT),
        n_commits=0,
        auto_tow=False,
    )


class TestPatrolE2E:
    def test_patrol_scans_real_files(self, patrol_result: dict):
        assert patrol_result["files_scanned"] > 100
        assert "violations" in patrol_result
        assert "violations_found" in patrol_result

    def test_patrol_finds_known_omni002_violations(self, patrol_result: dict):
        omni002_paths = {
            v["path"]
            for v in patrol_result["violations"]
            if v["rule_id"] == "OMNI-002"
        }
        known_violations = {
            "src/omnicompany/runtime/swe_prompts.py",
            "src/omnicompany/runtime/budget_tracker.py",
        }
        for path in known_violations:
            if (PROJECT_ROOT / path).exists():
                assert path in omni002_paths

    def test_patrol_does_not_false_positive_on_legal_runtime(self, patrol_result: dict):
        omni002_paths = {
            v["path"]
            for v in patrol_result["violations"]
            if v["rule_id"] == "OMNI-002"
        }
        legal_files = [
            "runner.py",
            "router.py",
            "llm.py",
            "stuck.py",
            "tool_executor.py",
            "agent_loop_compact.py",
        ]
        for filename in legal_files:
            path = f"src/omnicompany/runtime/{filename}"
            assert path not in omni002_paths

    def test_patrol_violation_fields_are_complete(self, patrol_result: dict):
        if not patrol_result["violations"]:
            pytest.skip("No real violations in current checkout")
        violation = patrol_result["violations"][0]
        for key in (
            "ticket_id",
            "rule_id",
            "severity",
            "path",
            "message",
            "disposition",
            "confidence",
        ):
            assert key in violation

    def test_patrol_ticket_ids_are_unique(self, patrol_result: dict):
        ids = [v["ticket_id"] for v in patrol_result["violations"]]
        assert len(ids) == len(set(ids))


class TestOmniMarkE2E:
    def test_parse_patrol_shim_has_omnimark(self):
        from omnicompany.core.omnimark import parse_omnimark

        path = PROJECT_ROOT / "src/omnicompany/packages/services/_core/guardian/_patrol_shim.py"
        mark = parse_omnimark(path)
        assert mark is not None
        assert mark.origin == "claude-code"

    def test_parse_omnimark_py_has_omnimark(self):
        from omnicompany.core.omnimark import parse_omnimark

        path = PROJECT_ROOT / "src/omnicompany/core/omnimark.py"
        mark = parse_omnimark(path)
        assert mark is not None
        assert mark.domain == "omnicompany/core"

    def test_parse_sentinel_py_has_omnimark(self):
        from omnicompany.core.omnimark import parse_omnimark

        path = PROJECT_ROOT / "src/omnicompany/packages/services/_core/guardian/sentinel.py"
        assert parse_omnimark(path) is not None

    def test_infer_domain_on_real_paths(self):
        from omnicompany.core.omnimark import _infer_domain

        assert (
            _infer_domain(
                Path("src/omnicompany/packages/domains/gameplay_system/benchmark/flows/foo.py")
            )
            == "domains/gameplay_system"
        )
        assert _infer_domain(Path("src/omnicompany/runtime/runner.py")) == "omnicompany/runtime"
        assert _infer_domain(Path("src/omnicompany/core/omnimark.py")) == "omnicompany/core"


class TestTowE2E:
    def test_patrol_then_tow_creates_tickets(self, tmp_path: Path, patrol_result: dict):
        from omnicompany.packages.services._core.guardian.tow_truck import OmniTow

        violations = patrol_result.get("violations", [])
        if not violations:
            pytest.skip("No real violations, so no tow tickets can be created")

        tow = OmniTow(project_root=tmp_path)
        tickets = tow.process_all(violations[:5])

        assert len(tickets) >= 1
        assert all(t.status == "open" for t in tickets)
        assert len(tow.list_tickets()) >= 1

    def test_tow_resolve_ticket_works(self, tmp_path: Path):
        from omnicompany.packages.services._core.guardian.tow_truck import OmniTow

        tow = OmniTow(project_root=tmp_path)
        tow.process(
            {
                "ticket_id": "E2E-001",
                "rule_id": "OMNI-002",
                "severity": "CRITICAL",
                "path": "src/omnicompany/runtime/swe_prompts.py",
                "message": "e2e test",
                "disposition": ["warn"],
                "confidence": 1.0,
            }
        )

        assert tow.resolve_ticket("E2E-001") is True
        assert tow.get_ticket("E2E-001")["status"] == "resolved"


class TestGuardedWriteE2E:
    def test_real_packages_file_is_allowed(self):
        from omnicompany.core.archmap import load_archmap

        archmap = load_archmap(force_reload=True)
        permit = archmap.is_writable(
            "src/omnicompany/packages/domains/gameplay_system/router.py",
            "claude-code",
            has_purpose=True,
        )
        assert permit.allowed is True

    def test_real_runtime_framework_file_is_allowed(self):
        from omnicompany.core.archmap import load_archmap

        archmap = load_archmap(force_reload=True)
        permit = archmap.is_writable(
            "src/omnicompany/runtime/exec/runner.py",
            "claude-code",
            has_purpose=True,
        )
        assert permit.allowed is True
        assert permit.always_green is True

    def test_real_test_file_is_allowed(self):
        from omnicompany.core.archmap import load_archmap

        archmap = load_archmap(force_reload=True)
        permit = archmap.is_writable(
            "tests/guardian/test_new.py",
            "claude-code",
            has_purpose=True,
        )
        assert permit.allowed is True

    def test_root_scratch_file_is_blocked(self):
        from omnicompany.core.archmap import load_archmap

        archmap = load_archmap(force_reload=True)
        permit = archmap.is_writable(
            "scratch_guardian_e2e.py",
            "claude-code",
            has_purpose=True,
        )
        assert permit.allowed is False
        assert permit.drawer == "(root forbidden)"

    def test_guarded_write_status_uses_enforce_mode(self):
        from omnicompany.core.guarded_write import shield_status

        status = shield_status()
        assert status["mode"] == "enforce"
        assert status["enforce_mode"] is True


class TestSentinelE2E:
    def test_sentinel_shim_start_status_and_stop(self):
        from omnicompany.packages.services._core.guardian import sentinel
        from omnicompany.packages.services._core.guardian.sentinel import OmniSentinel

        OmniSentinel._instance = None
        alive = {"value": True}

        def fake_is_alive(root: Path) -> bool:
            return alive["value"]

        def fake_stop(root: Path) -> bool:
            alive["value"] = False
            return True

        with (
            patch.object(sentinel, "ensure_daemon_running", return_value=True) as start,
            patch.object(sentinel, "is_daemon_alive", side_effect=fake_is_alive),
            patch.object(sentinel, "stop_daemon", side_effect=fake_stop) as stop,
            patch.object(
                sentinel,
                "daemon_status",
                return_value={"alive": True, "version": OmniSentinel.__version__},
            ),
        ):
            shim = OmniSentinel.get_instance(project_root=str(PROJECT_ROOT))
            shim.start(daemon=True, interval_seconds=3600)
            assert shim.is_alive() is True

            status = shim.status()
            assert status["alive"] is True
            assert status["version"] == OmniSentinel.__version__

            shim.stop()
            assert shim.is_alive() is False
            start.assert_called_once()
            stop.assert_called_once()

        OmniSentinel._instance = None
