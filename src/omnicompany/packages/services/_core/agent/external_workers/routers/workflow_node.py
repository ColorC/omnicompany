# [OMNI] origin=codex domain=services/agent ts=2026-05-11 type=infrastructure
"""TeamRunner workflow node for external agent workers."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Coroutine

from omnicompany.packages.services._core.agent.external_workers.base import (
    ExternalAgentPermissionMode,
    ExternalAgentStatus,
    ExternalAgentWorkerRegistry,
)
from omnicompany.packages.services._core.agent.external_workers.runner import (
    ExternalAgentModelPolicy,
    ExternalAgentRunRequest,
    run_external_agent_request,
)
from omnicompany.packages.services._core.agent.spawn_surface import (
    ENTRY_TEAMRUNNER_NODE,
    ensure_agent_spawn_metadata,
)
from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.routing.router import Router


class ExternalAgentWorkerNode(Router):
    """Run Codex/Claude Code as a first-class TeamRunner workflow node.

    This node is the DAG-level integration point. It does not depend on the
    Agent tool or dashboard API: a TeamSpec binding can instantiate this Router
    directly and place it in a workflow. It remains an adapter over
    ExternalAgentRunRequest, not a new provider launch surface.
    """

    DESCRIPTION = (
        "Run an audited external agent worker such as Codex or Claude Code from "
        "a TeamRunner workflow node. Defaults to readonly and returns normalized "
        "run metadata plus the final text."
    )
    FORMAT_IN = "external_agent.request"
    FORMAT_OUT = "external_agent.result"

    def __init__(
        self,
        *,
        provider: str | None = None,
        cwd: Path | str | None = None,
        permission_mode: ExternalAgentPermissionMode | str = ExternalAgentPermissionMode.READONLY,
        model: str | None = None,
        model_policy: ExternalAgentModelPolicy = "cheap",
        profile: str | None = None,
        timeout_s: float = 600.0,
        attached_context: list[str] | None = None,
        worker_registry: ExternalAgentWorkerRegistry | None = None,
        allow_trusted_bypass: bool = False,
    ):
        self.provider = provider
        self.cwd = Path(cwd).expanduser().resolve() if cwd is not None else None
        self.permission_mode = permission_mode
        self.model = model
        self.model_policy = model_policy
        self.profile = profile
        self.timeout_s = timeout_s
        self.attached_context = list(attached_context or [])
        self.worker_registry = worker_registry
        self.allow_trusted_bypass = allow_trusted_bypass

    def run(self, input_data: Any) -> Verdict:
        data = input_data if isinstance(input_data, dict) else {"prompt": str(input_data)}
        provider = str(data.get("provider") or self.provider or "").strip()
        prompt = str(data.get("prompt") or data.get("task") or "").strip()
        permission_mode = data.get("permission_mode") or self.permission_mode

        if not provider:
            return self._fail(data, "external agent provider is required")
        if not prompt:
            return self._fail(data, "external agent prompt is required")

        try:
            normalized_permission = (
                permission_mode
                if isinstance(permission_mode, ExternalAgentPermissionMode)
                else ExternalAgentPermissionMode(str(permission_mode))
            )
        except ValueError:
            return self._fail(
                data,
                "permission_mode must be one of: readonly, workspace-write, trusted-bypass",
            )

        allow_bypass = bool(data.get("allow_trusted_bypass") or self.allow_trusted_bypass)
        if normalized_permission == ExternalAgentPermissionMode.TRUSTED_BYPASS and not allow_bypass:
            return self._fail(data, "trusted-bypass requires allow_trusted_bypass=true")

        try:
            cwd = self._resolve_cwd(data.get("cwd"))
        except ValueError as exc:
            return self._fail(data, str(exc))

        attached_context = list(self.attached_context)
        extra_context = data.get("attached_context") or []
        if not isinstance(extra_context, list) or not all(isinstance(item, str) for item in extra_context):
            return self._fail(data, "attached_context must be a list of strings")
        attached_context.extend(extra_context)

        request = ExternalAgentRunRequest(
            provider=provider,
            prompt=prompt,
            cwd=cwd,
            permission_mode=normalized_permission,
            model=data.get("model") or self.model,
            model_policy=data.get("model_policy") or self.model_policy,
            profile=data.get("profile") or self.profile,
            timeout_s=float(data.get("timeout_s") or self.timeout_s),
            attached_context=attached_context,
            output_schema_path=data.get("output_schema_path"),
            env=dict(data.get("env") or {}),
            watch_paths=list(data.get("watch_paths") or []),
            trace_id=str(getattr(self, "_trace_id", "") or data.get("trace_id") or ""),
            metadata=ensure_agent_spawn_metadata(
                ENTRY_TEAMRUNNER_NODE,
                dict(data.get("metadata") or {}),
                entrypoint="teamrunner_workflow_node",
                node_id=str(getattr(self, "_node_id", "") or ""),
            ),
        )

        result = _run_coro_sync(
            run_external_agent_request(
                request,
                bus=getattr(self, "_bus", None),
                worker_registry=self.worker_registry,
            )
        )
        status = result.normalized_status()
        output = {
            **data,
            "text": result.final_text,
            "external_agent": {
                "run_id": result.run_id,
                "provider": result.provider,
                "status": status.value,
                "final_text": result.final_text,
                "structured_output": result.structured_output,
                "exit_code": result.exit_code,
                "changed_files": result.changed_files,
                "diff_summary": result.diff_summary,
                "error": result.error,
                "duration_ms": result.duration_ms,
                "event_count": len(result.events or []),
                "raw": result.raw,
            },
        }
        kind = _verdict_kind_for_status(status)
        diagnosis = "external agent completed"
        if kind != VerdictKind.PASS:
            diagnosis = result.error or f"external agent {provider!r} ended with {status.value}"
        return Verdict(kind=kind, output=output, diagnosis=diagnosis)

    def _resolve_cwd(self, value: Any) -> Path:
        cwd = Path(value).expanduser() if value else self.cwd
        if cwd is None:
            cwd = Path.cwd()
        cwd = cwd.resolve()
        if not cwd.exists() or not cwd.is_dir():
            raise ValueError(f"cwd must be an existing directory: {cwd}")
        return cwd

    @staticmethod
    def _fail(input_data: dict[str, Any], diagnosis: str) -> Verdict:
        return Verdict(
            kind=VerdictKind.FAIL,
            output={**input_data, "external_agent_error": diagnosis},
            diagnosis=diagnosis,
        )


def _run_coro_sync(coro: Coroutine[Any, Any, Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(asyncio.run, coro)
        return future.result()


def _verdict_kind_for_status(status: ExternalAgentStatus) -> VerdictKind:
    if status == ExternalAgentStatus.SUCCEEDED:
        return VerdictKind.PASS
    if status == ExternalAgentStatus.PERMISSION_VIOLATION:
        return VerdictKind.PARTIAL
    return VerdictKind.FAIL


__all__ = ["ExternalAgentWorkerNode"]
