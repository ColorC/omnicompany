"""Team 2 selftest 通过 MaterialDispatcher 的端到端验证.

场景:
- 4 Worker (RegistryChecker / FunctionalTester / SelftestGate / LLMReporter)
- FunctionalTester 产 selftest.selftest-report
- SelftestGate + LLMReporter 都订阅 selftest-report (Q3 多订阅验证)
- LLMReporter 在 LLM 不可用时降级 PASS (DESIGN 局限 #1)

用户洞察检验: 若 dispatcher 跑通, 说明 selftest Stage 1 合规真;
跑不通则暴露不严谨 (如多订阅冲突 / Anchor 形式透传等).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from omnicompany.packages.services.omnicompany import MaterialDispatcher


def _build_selftest_workers():
    from omnicompany.packages.services.selftest.routers import (
        RegistryCheckerRouter,
        FunctionalTesterRouter,
        SelftestGateRouter,
        LLMReporterRouter,
    )
    return [
        RegistryCheckerRouter(),
        FunctionalTesterRouter(),
        SelftestGateRouter(),
        LLMReporterRouter(),
    ]


class TestSelftestDispatcher:
    @pytest.mark.asyncio
    async def test_scan_through_dispatcher(self):
        """selftest 4 Worker 通过 dispatcher 订阅激活, 全链路跑通."""
        workers = _build_selftest_workers()
        dispatcher = MaterialDispatcher(workers, max_iterations=30)
        events = await dispatcher.run_job(
            initial_material_id="selftest.request",
            initial_payload={
                "project_root": "/workspace/omnicompany",
            },
        )

        event_types = [e.event_type for e in events]
        # 应该至少看到 registry-report, selftest-report, 还可能有 health-report (LLM 降级时也发)
        assert "selftest.request" in event_types
        assert "selftest.registry-report" in event_types, f"RegistryChecker 未激活: {event_types}"
        assert "selftest.selftest-report" in event_types, f"FunctionalTester 未激活: {event_types}"

    @pytest.mark.asyncio
    async def test_q1_single_activation_on_multi_subscribe(self):
        """Q3 验证: SelftestGate + LLMReporter 都订阅 selftest-report,
        Q1 单次激活保证两者各激活一次, 不重复."""
        workers = _build_selftest_workers()
        dispatcher = MaterialDispatcher(workers, max_iterations=30)
        events = await dispatcher.run_job(
            initial_material_id="selftest.request",
            initial_payload={
                "project_root": "/workspace/omnicompany",
            },
        )

        # 统计各 worker 来源
        source_counts: dict[str, int] = {}
        for e in events:
            source_counts[e.source] = source_counts.get(e.source, 0) + 1

        # 每个 worker.<Class> 只应出现一次 (Q1)
        for source, count in source_counts.items():
            if source.startswith("worker."):
                assert count == 1, f"Q1 违反: {source} 激活 {count} 次"

    @pytest.mark.asyncio
    async def test_diagnostics_expose_imperfection(self):
        """诊断辅助应能识别 selftest 架构的不严谨点 (若有).

        已知候选: SelftestGate 的 FORMAT_OUT 与 FORMAT_IN 同 id,
        黑板模型下是 '形式透传 Anchor', 产出同类 material 可能冗余
        (但被 LLMReporter 订阅, 可能也合理). 这个测试允许任意结果, 只记录.
        """
        workers = _build_selftest_workers()
        dispatcher = MaterialDispatcher(workers, max_iterations=30)
        events = await dispatcher.run_job(
            initial_material_id="selftest.request",
            initial_payload={"project_root": "/workspace/omnicompany"},
        )

        orphans = dispatcher.orphan_workers(events)
        redundant = dispatcher.unconsumed_materials(events)

        print(f"\n=== selftest 诊断 ===")
        print(f"  orphans: {[type(w).__name__ for w in orphans]}")
        print(f"  unconsumed internal: {[e.event_type for e in redundant]}")
        # 不强断言 — 让结果反映实情
