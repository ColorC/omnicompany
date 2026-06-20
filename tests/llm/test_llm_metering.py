"""LLM metering and routerized agent loop integration tests."""

from __future__ import annotations

import asyncio

import pytest

from omnicompany.runtime.llm.llm import (
    LLMMeter,
    LLMCallRecord,
    _MODEL_PRICING,
    _estimate_cost,
)


class TestLLMMeterCore:
    def _fresh_meter(self) -> LLMMeter:
        meter = LLMMeter()
        meter.reset()
        return meter

    def test_record_preserves_all_fields(self):
        meter = self._fresh_meter()
        record = LLMCallRecord(
            model="claude-sonnet-4-6",
            role="ide_agent",
            caller="pipeline.test.node_a.step_1.turn_0",
            input_tokens=1500,
            output_tokens=800,
            cost_usd=0.0165,
            latency_ms=1200,
            stop_reason="end_turn",
        )
        meter.record(record)
        stored = meter.get_records()[0]
        assert stored.model == "claude-sonnet-4-6"
        assert stored.caller == "pipeline.test.node_a.step_1.turn_0"
        assert stored.input_tokens == 1500
        assert stored.output_tokens == 800
        assert stored.stop_reason == "end_turn"

    def test_caller_prefix_query(self):
        meter = self._fresh_meter()
        for node in ["node_a", "node_b"]:
            for turn in range(3):
                meter.record(
                    LLMCallRecord(
                        model="glm-5",
                        role="runtime_main",
                        caller=f"pipeline.gameplay_system_qa.{node}.step_1.turn_{turn}",
                        input_tokens=500,
                        output_tokens=200,
                        cost_usd=0.001,
                        latency_ms=100,
                        stop_reason="end_turn",
                    )
                )
        meter.record(
            LLMCallRecord(
                model="glm-5",
                role="runtime_main",
                caller="pipeline.other.node_x.step_1.turn_0",
                input_tokens=100,
                output_tokens=50,
                cost_usd=0.0001,
                latency_ms=50,
                stop_reason="end_turn",
            )
        )

        assert len(meter.get_records(caller="pipeline.gameplay_system_qa.node_a.step_1.turn_0")) == 1
        assert len(meter.get_records(caller_prefix="pipeline.gameplay_system_qa")) == 6
        assert len(meter.get_records(caller_prefix="pipeline.gameplay_system_qa.node_a")) == 3
        assert len(meter.get_records(caller_prefix="pipeline.other")) == 1

    def test_summary_with_prefix(self):
        meter = self._fresh_meter()
        for turn in range(5):
            meter.record(
                LLMCallRecord(
                    model="claude-sonnet-4-6",
                    role="ide_agent",
                    caller=f"NativeIdeAgent.turn_{turn}",
                    input_tokens=2000,
                    output_tokens=1000,
                    cost_usd=_estimate_cost("claude-sonnet-4-6", 2000, 1000),
                    latency_ms=1500,
                    stop_reason="end_turn",
                )
            )
        summary = meter.summary(caller_prefix="NativeIdeAgent")
        assert summary["call_count"] == 5
        assert summary["total_input_tokens"] == 10000
        assert summary["total_output_tokens"] == 5000
        assert summary["total_cost_usd"] > 0

    def test_breakdown_groups_by_node(self):
        meter = self._fresh_meter()
        for node in ["node_a", "node_b"]:
            for turn in range(2):
                meter.record(
                    LLMCallRecord(
                        model="glm-5",
                        role="runtime_main",
                        caller=f"pipeline.test.{node}.step_1.turn_{turn}",
                        input_tokens=1000,
                        output_tokens=500,
                        cost_usd=0.002,
                        latency_ms=100,
                        stop_reason="end_turn",
                    )
                )

        breakdown = meter.breakdown(caller_prefix="pipeline.test")
        assert "pipeline.test.node_a.step_1" in breakdown
        assert "pipeline.test.node_b.step_1" in breakdown
        assert breakdown["pipeline.test.node_a.step_1"]["call_count"] == 2


class TestPipelineCallerInjection:
    def test_pipeline_runner_injects_caller(self):
        import inspect

        from omnicompany.runtime.exec.runner import PipelineRunner

        source = inspect.getsource(PipelineRunner)
        assert "_llm_caller" in source

    def test_agent_node_loop_passes_class_caller_prefix(self):
        import inspect

        from omnicompany.packages.services._core.agent.loop import AgentNodeLoop

        source = inspect.getsource(AgentNodeLoop.__init__)
        assert "caller_prefix=type(self).__name__" in source

    def test_caller_format(self):
        caller = "pipeline.gameplay_system_qa.schema_gen.step_3.turn_2"
        parts = caller.split(".")
        assert parts[0] == "pipeline"
        assert parts[1] == "gameplay_system_qa"
        assert parts[2] == "schema_gen"
        assert parts[3].startswith("step_")
        assert parts[4].startswith("turn_")


class TestPricing:
    def test_all_the_company_models_have_pricing(self):
        required = [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "gpt-5.4",
            "glm-5",
            "qwen3.5-plus",
            "deepseek-v3-2-251201",
            "kimi-k2.5",
            "qwen3-max",
        ]
        for model in required:
            assert model in _MODEL_PRICING
            input_price, output_price = _MODEL_PRICING[model]
            assert input_price > 0
            assert output_price > 0

    def test_cost_scaling(self):
        cost_1k = _estimate_cost("glm-5", 1000, 0)
        cost_10k = _estimate_cost("glm-5", 10000, 0)
        assert abs(cost_10k / cost_1k - 10.0) < 0.01

    def test_sonnet_is_more_expensive_than_glm(self):
        cost_sonnet = _estimate_cost("claude-sonnet-4-6", 1000, 1000)
        cost_glm = _estimate_cost("glm-5", 1000, 1000)
        assert cost_sonnet > cost_glm * 3


class TestStopReasonSafety:
    def test_max_tokens_discards_tool_uses_in_llm_call_router(self):
        import inspect

        from omnicompany.packages.services._core.agent.routers.llm_call import LLMCallRouter

        source = inspect.getsource(LLMCallRouter.run)
        assert 'stop_reason == "max_tokens"' in source
        assert "tool_use_blocks = []" in source

    def test_max_tokens_logs_warning(self):
        import inspect

        from omnicompany.packages.services._core.agent.routers.llm_call import LLMCallRouter

        source = inspect.getsource(LLMCallRouter.run)
        assert "logger.warning" in source
        assert "discarding" in source

    def test_usage_is_emitted_in_router_output(self):
        import inspect

        from omnicompany.packages.services._core.agent.routers.llm_call import LLMCallRouter

        source = inspect.getsource(LLMCallRouter.run)
        assert '"usage": usage_dict' in source
        assert "emit_router_output" in source


class TestAgentMeteringIntegration:
    def test_native_agent_uses_router_metering_prefix(self):
        import inspect

        from omnicompany.dashboard.native_agent import NativeIdeAgent
        from omnicompany.packages.services._core.agent.loop import AgentNodeLoop

        assert NativeIdeAgent.SPEC.name == "NativeIdeAgent"
        source = inspect.getsource(AgentNodeLoop.__init__)
        assert "caller_prefix=type(self).__name__" in source

    @pytest.mark.asyncio
    async def test_meter_records_after_mock_session(self):
        import tempfile

        from omnicompany.bus.sqlite import SQLiteBus
        from omnicompany.dashboard.controlplane.ide_session import IDESession

        with tempfile.TemporaryDirectory() as tmp:
            bus = SQLiteBus(f"{tmp}/test.db")
            await bus.connect()
            try:
                session = IDESession("meter-test", bus, use_mock=True)
                await session.submit("test task")
                await session.run_agent("test task")
                await asyncio.sleep(2.0)

                events = await bus.read_trace("meter-test")
                event_types = [event.event_type for event in events]
                assert "task.finish" in event_types
            finally:
                await bus.close()
