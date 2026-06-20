# [OMNI] origin=claude-code domain=tests/teams ts=2026-04-24T00:00:00Z type=test
"""Shared fixtures for team-level contract tests (TEAM-BUILDER-REAL-PASS).

Tests here verify **the team's contract**, not its internal structure.
A team passes if: given input → produces output matching the requirement spec.

Two fixture modes:
- `programmatic`: import team + run dispatcher in-process (fast · for P3 E2E)
- `subprocess`: shell out to `omni run` (slow but true black-box · for P5)

Select via `pytest --team-mode=programmatic|subprocess`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--team-mode",
        action="store",
        default="subprocess",
        choices=["programmatic", "subprocess"],
        help="Team test mode: programmatic (fast · in-process dispatch) or subprocess (true black-box · omni run)",
    )


@pytest.fixture(scope="session")
def team_mode(request) -> str:
    return request.config.getoption("--team-mode")


def _build_subprocess_runner(pipeline_name: str) -> Callable[[dict], Any]:
    """Build a `run(input_dict) -> Verdict-like` callable that shells out to `omni run`."""
    def _run(input_dict: dict) -> Any:
        import tempfile
        out_fd, out_path = tempfile.mkstemp(suffix=".out", prefix=f"{pipeline_name}_")
        os.close(out_fd)
        try:
            cmd = [
                "omni", "run", pipeline_name,
                "-j", json.dumps(input_dict, ensure_ascii=False),
                "-o", out_path,
            ]
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=900,
                encoding="utf-8", errors="replace", env=env,
            )
            rc = proc.returncode

            # Parse output file (str or JSON)
            output_text = Path(out_path).read_text(encoding="utf-8", errors="replace") if Path(out_path).exists() else ""
            try:
                output = json.loads(output_text) if output_text.lstrip().startswith(("{", "[")) else output_text
            except json.JSONDecodeError:
                output = output_text

            # Map exit code to Verdict kind
            kind_val = "pass" if rc == 0 else "fail"
            # 捕 stderr + stdout 全部 (诊断可能在任一路径)
            combined = (proc.stderr or "") + "\n" + (proc.stdout or "")
            diag = combined[-1500:]
            return SimpleNamespace(
                kind=SimpleNamespace(value=kind_val),
                output=output,
                diagnosis=diag,
                _stdout=proc.stdout,
                _stderr=proc.stderr,
                _rc=rc,
            )
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
    return _run


def _build_programmatic_runner(pipeline_name: str) -> Callable[[dict], Any]:
    """Build an in-process runner that uses dispatch() directly. Faster but not black-box."""
    def _run(input_dict: dict) -> Any:
        import asyncio
        from omnicompany.core.registry import discover
        from omnicompany.core.dispatch import dispatch
        discover()
        try:
            result = asyncio.run(dispatch(pipeline_name, input_dict, max_steps=1000))
            # Normalize to Verdict-like
            if hasattr(result, "kind"):
                return result
            return SimpleNamespace(
                kind=SimpleNamespace(value="pass"),
                output=result,
                diagnosis="",
            )
        except Exception as e:
            return SimpleNamespace(
                kind=SimpleNamespace(value="fail"),
                output=None,
                diagnosis=f"{type(e).__name__}: {e}",
            )
    return _run


@pytest.fixture(scope="module")
def make_runner(team_mode) -> Callable[[str], Callable[[dict], Any]]:
    """Factory: given pipeline_name → returns a run_team(input_dict) callable."""
    def _factory(pipeline_name: str):
        if team_mode == "subprocess":
            return _build_subprocess_runner(pipeline_name)
        return _build_programmatic_runner(pipeline_name)
    return _factory
