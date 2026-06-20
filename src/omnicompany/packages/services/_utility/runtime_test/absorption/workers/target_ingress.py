# [OMNI] origin=claude-code domain=services/absorption_runtime_test/workers ts=2026-04-27T00:00:00Z type=worker
# [OMNI] material_id="material:utility.runtime_test.absorption.target_ingress_implementation.py"
"""TargetIngressWorker — Worker #1 (HARD).

校 target_team_id 在 PipelineRegistry 注册 · 推 target 包目录 · 透传 sample_input/run_count.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

logger = logging.getLogger(__name__)


_PROJECT_ROOT = Path(__file__).resolve().parents[6]
_SERVICES_ROOT = _PROJECT_ROOT / "src" / "omnicompany" / "packages" / "services"


def _slug_to_pkg(target_team_id: str) -> str:
    return target_team_id.replace("-", "_")


class TargetIngressWorker(Worker):
    DESCRIPTION = (
        "校 target_team_id 在 PipelineRegistry 注册, 推 target 包目录, 透传 sample_input/run_count/spot_impl_count."
    )
    FORMAT_IN = "absorption_runtime_test.target_spec"
    FORMAT_OUT = "absorption_runtime_test.target_metadata"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        target_team_id = input_data.get("target_team_id")
        sample_input = input_data.get("sample_input")

        if not target_team_id or not isinstance(target_team_id, str):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="target_team_id 缺失或非法")
        if not isinstance(sample_input, dict):
            return Verdict(kind=VerdictKind.FAIL, diagnosis="sample_input 必须是 dict")

        # 校注册
        from omnicompany.core.registry import discover, get
        discover()
        if get(target_team_id) is None:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"target_team_id '{target_team_id}' 未在 PipelineRegistry 注册",
            )

        # 推包目录
        pkg_name = _slug_to_pkg(target_team_id)
        team_code_dir = _SERVICES_ROOT / pkg_name
        if not team_code_dir.is_dir():
            alt = _SERVICES_ROOT / target_team_id
            if alt.is_dir():
                team_code_dir = alt
            else:
                return Verdict(
                    kind=VerdictKind.FAIL,
                    diagnosis=f"target 包目录不存在: 试过 {team_code_dir} 与 {alt}",
                )

        run_count = input_data.get("run_count", 2)
        if not isinstance(run_count, int) or run_count < 2:
            run_count = 2

        spot_impl_count = input_data.get("spot_impl_count", 2)
        if not isinstance(spot_impl_count, int) or spot_impl_count < 1:
            spot_impl_count = 2

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "target_team_id": target_team_id,
                "team_code_dir": str(team_code_dir),
                "sample_input": sample_input,
                "run_count": run_count,
                "spot_impl_count": spot_impl_count,
            },
            diagnosis=f"装载完成: target={target_team_id} · run_count={run_count}",
            confidence=1.0,
        )
