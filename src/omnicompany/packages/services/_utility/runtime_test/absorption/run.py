# [OMNI] origin=claude-code domain=services/absorption_runtime_test/run ts=2026-04-27T00:00:00Z type=config
# [OMNI] material_id="material:utility.runtime_test.absorption.binding_composer.config.py"
"""absorption_runtime_test Team · build_bindings."""
from __future__ import annotations

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.format import create_builtin_registry

from .formats import register_formats

from .workers.target_ingress import TargetIngressWorker
from .workers.sample_runs_executor import SampleRunsExecutorWorker
from .workers.cross_run_verifier import CrossRunStabilityVerifierWorker
from .workers.spot_impl_verifier import SpotImplVerifierWorker
from .workers.source_coverage_verifier import SourceCoverageVerifierWorker
from .workers.portrait_assembler import PortraitAssemblerWorker


def build_bindings(input_dict: dict | None = None) -> dict[str, Worker]:
    registry = create_builtin_registry()
    register_formats(registry)
    return {
        "TargetIngressWorker": TargetIngressWorker(),
        "SampleRunsExecutorWorker": SampleRunsExecutorWorker(),
        "CrossRunStabilityVerifierWorker": CrossRunStabilityVerifierWorker(),
        "SpotImplVerifierWorker": SpotImplVerifierWorker(),
        "SourceCoverageVerifierWorker": SourceCoverageVerifierWorker(),
        "PortraitAssemblerWorker": PortraitAssemblerWorker(),
    }
