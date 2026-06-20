# [OMNI] origin=codex domain=scripts ts=2026-05-10 type=smoke
# OMNI-PERSISTENT-SCRIPT owner=agent-framework purpose="Run real local smoke checks for external agent workers."
"""Real smoke runner for external agent workers.

This script intentionally calls local external agents. It is not a unit test:
Codex/Claude Code must be installed and authenticated in the local machine.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from omnicompany.packages.services._core.agent.external_workers import (  # noqa: E402
    ClaudeCodeSdkWorker,
    CodexExecWorker,
    ExternalAgentPermissionMode,
    ExternalAgentRunRequest,
    ExternalAgentRunSpec,
    run_external_agent_request,
)


def _repo_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


async def run_codex_readonly(timeout_s: float) -> int:
    spec = ExternalAgentRunSpec(
        provider="codex",
        prompt=(
            "Readonly smoke test. Do not edit, write, delete, move, or create files. "
            "Read pyproject.toml and answer in one short sentence: what is the project name?"
        ),
        cwd=REPO_ROOT,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        timeout_s=timeout_s,
        trace_id="trace.smoke.codex.readonly",
    )
    result = await CodexExecWorker().run(spec)
    _print_result(result)
    if result.normalized_status().value != "succeeded":
        return 1
    if result.changed_files:
        print(f"readonly smoke produced changed_files: {result.changed_files}", file=sys.stderr)
        return 2
    if "omnicompany" not in result.final_text.lower():
        print(f"readonly smoke returned unexpected final_text: {result.final_text!r}", file=sys.stderr)
        return 3
    return 0


async def run_codex_workspace_write(target: Path, timeout_s: float) -> int:
    target = target.resolve()
    try:
        relative_target = target.relative_to(REPO_ROOT)
    except ValueError:
        print(f"write target must be inside repo: {target}", file=sys.stderr)
        return 2
    if target.exists():
        print(f"write target already exists: {relative_target}", file=sys.stderr)
        return 3

    prompt = f"""
Workspace-write smoke test for omnicompany external agent worker.
You are allowed to create exactly one file and no other files: {relative_target.as_posix()}
Do not modify any existing file.
Create that file with exactly these three lines:
# Codex workspace-write smoke

status: pass
After writing it, report the file path and stop.
""".strip()
    spec = ExternalAgentRunSpec(
        provider="codex",
        prompt=prompt,
        cwd=REPO_ROOT,
        permission_mode=ExternalAgentPermissionMode.WORKSPACE_WRITE,
        timeout_s=timeout_s,
        trace_id="trace.smoke.codex.workspace_write",
    )
    result = await CodexExecWorker().run(spec)
    _print_result(result)
    rel = relative_target.as_posix()
    if result.normalized_status().value != "succeeded":
        return 1
    if not target.exists():
        print(f"workspace-write smoke did not create target: {rel}", file=sys.stderr)
        return 4
    if rel not in result.changed_files:
        print(
            f"workspace-write smoke did not report target in changed_files: {result.changed_files}",
            file=sys.stderr,
        )
        return 5
    expected = "# Codex workspace-write smoke\n\nstatus: pass\n"
    actual = target.read_text(encoding="utf-8")
    if actual != expected:
        print(f"workspace-write target content mismatch: {actual!r}", file=sys.stderr)
        return 6
    return 0


async def run_claude_readonly(timeout_s: float) -> int:
    spec = ExternalAgentRunSpec(
        provider="claude-code",
        prompt=(
            "Readonly smoke test. Do not edit, write, delete, move, or create files. "
            "Read pyproject.toml and answer in one short sentence: what is the project name?"
        ),
        cwd=REPO_ROOT,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        timeout_s=timeout_s,
        trace_id="trace.smoke.claude_code.readonly",
    )
    result = await ClaudeCodeSdkWorker().run(spec)
    _print_result(result)
    if result.normalized_status().value != "succeeded":
        return 1
    allowed = set(result.raw.get("readonly_allowed_changed_files") or [])
    unexpected = [path for path in result.changed_files if path not in allowed]
    if unexpected:
        print(f"readonly smoke produced unexpected changed_files: {unexpected}", file=sys.stderr)
        return 2
    rollback_failed = (result.raw.get("readonly_rollback") or {}).get("failed") or []
    if rollback_failed:
        print(f"readonly smoke rollback failed: {rollback_failed}", file=sys.stderr)
        print(f"readonly smoke produced changed_files: {result.changed_files}", file=sys.stderr)
        return 2
    if "omnicompany" not in result.final_text.lower():
        print(f"readonly smoke returned unexpected final_text: {result.final_text!r}", file=sys.stderr)
        return 3
    return 0


async def run_workflow_readonly(provider: str, model: str | None, timeout_s: float) -> int:
    request = ExternalAgentRunRequest(
        provider=provider,
        prompt=(
            "Readonly workflow-entry smoke test. Do not edit, write, delete, move, "
            "or create files. Read pyproject.toml and answer in one short sentence: "
            "what is the project name?"
        ),
        cwd=REPO_ROOT,
        permission_mode=ExternalAgentPermissionMode.READONLY,
        model=model,
        model_policy="cheap",
        timeout_s=timeout_s,
        trace_id=f"trace.smoke.workflow_readonly.{provider}",
        metadata={"smoke": "workflow-readonly"},
    )
    result = await run_external_agent_request(request)
    _print_result(result)
    if result.normalized_status().value != "succeeded":
        return 1
    allowed = set(result.raw.get("readonly_allowed_changed_files") or [])
    unexpected = [path for path in result.changed_files if path not in allowed]
    if unexpected:
        print(f"workflow readonly smoke produced unexpected changed_files: {unexpected}", file=sys.stderr)
        return 2
    rollback_failed = (result.raw.get("readonly_rollback") or {}).get("failed") or []
    if rollback_failed:
        print(f"workflow readonly smoke rollback failed: {rollback_failed}", file=sys.stderr)
        return 2
    if "omnicompany" not in result.final_text.lower():
        print(f"workflow readonly smoke returned unexpected final_text: {result.final_text!r}", file=sys.stderr)
        return 3
    return 0


def _print_result(result) -> None:
    changed_files = list(result.changed_files or [])
    rollback = result.raw.get("readonly_rollback") or {}
    rolled_back = rollback.get("rolled_back") or []
    rollback_failed = rollback.get("failed") or []
    print(json.dumps({
        "run_id": result.run_id,
        "provider": result.provider,
        "status": result.normalized_status().value,
        "exit_code": result.exit_code,
        "final_text": result.final_text.strip(),
        "changed_files_count": len(changed_files),
        "changed_files_sample": changed_files[:20],
        "diff_summary_tail": result.diff_summary[-4000:],
        "event_count": len(result.events),
        "duration_ms": result.duration_ms,
        "error": result.error,
        "raw": {
            "preexisting_changed_files_count": result.raw.get("preexisting_changed_files_count"),
            "after_changed_files_count": result.raw.get("after_changed_files_count"),
            "after_rollback_changed_files_count": result.raw.get("after_rollback_changed_files_count"),
            "readonly_rollback_count": len(rolled_back),
            "readonly_rollback_failed": rollback_failed,
        },
    }, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "smoke",
        choices=["codex-readonly", "codex-workspace-write", "claude-readonly", "workflow-readonly"],
        help="Which real smoke to run.",
    )
    parser.add_argument(
        "--provider",
        choices=["codex", "claude-code"],
        default="codex",
        help="Provider for workflow-readonly smoke.",
    )
    parser.add_argument("--model", help="Optional model override for workflow-readonly smoke.")
    parser.add_argument(
        "--target",
        help="Required for codex-workspace-write. Must be a repo-relative path that does not exist.",
    )
    parser.add_argument("--timeout-s", type=float, default=240.0)
    args = parser.parse_args(argv)

    if args.smoke == "codex-readonly":
        return asyncio.run(run_codex_readonly(args.timeout_s))
    if args.smoke == "claude-readonly":
        return asyncio.run(run_claude_readonly(args.timeout_s))
    if args.smoke == "workflow-readonly":
        return asyncio.run(run_workflow_readonly(args.provider, args.model, args.timeout_s))
    if not args.target:
        parser.error("--target is required for codex-workspace-write")
    return asyncio.run(run_codex_workspace_write(_repo_path(args.target), args.timeout_s))


if __name__ == "__main__":
    raise SystemExit(main())
