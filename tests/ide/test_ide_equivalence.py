"""Native IDE agent equivalence checks for the routerized AgentNodeLoop stack.

These tests intentionally target dashboard.native_agent.NativeIdeAgent. The
legacy runtime.agent.ide_agent_loop module is retired by the T9 convergence
block and must not be imported here.
"""

from __future__ import annotations

import os
from pathlib import Path

from omnicompany.dashboard.native_agent import (
    NativeIdeAgent,
    _NATIVE_LOOP_CONFIG,
    _build_substitutions,
)
from omnicompany.packages.services._core.agent.configurable import TOOL_REGISTRY
from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.llm_call import LLMCallRouter
from omnicompany.packages.services._core.agent.routers.single_tool import FinishRouter
from omnicompany.runtime.llm.llm import LLMMeter, LLMCallRecord, _estimate_cost, _MODEL_PRICING


IDE_LOOP_CONFIG = _NATIVE_LOOP_CONFIG
SYSTEM_PROMPT_STATIC = NativeIdeAgent._reload_with_cwd(str(Path.cwd()))


def _build_environment_section(cwd: str, model_id: str, knowledge_cutoff: str) -> str:
    subs = _build_substitutions(cwd, model_id)
    return "\n".join(
        [
            f"Primary working directory: {cwd}",
            f"Platform: {subs['platform']}",
            f"Shell: {subs['shell']}",
            f"OS Version: {subs['os_version']}",
            f"You are powered by {model_id}.",
            f"Assistant knowledge cutoff is {knowledge_cutoff}.",
        ]
    )


def _ide_tool_classes() -> dict[str, type]:
    tool_classes = [TOOL_REGISTRY[name] for name in NativeIdeAgent.SPEC.tools]
    tool_classes.append(FinishRouter)
    return {tool.TOOL_NAME: tool for tool in tool_classes}


class TestSystemPromptCoverage:
    prompt = SYSTEM_PROMPT_STATIC

    def test_identity_section(self):
        assert "interactive agent" in self.prompt
        assert "software engineering tasks" in self.prompt

    def test_core_safety_guidance(self):
        assert "destructive techniques" in self.prompt
        assert "prompt injection" in self.prompt
        assert "permission mode" in self.prompt

    def test_task_style_guidance(self):
        assert "Don't add features, refactor code" in self.prompt
        assert "do not propose changes to code you haven't read" in self.prompt
        assert "prefer editing an existing file" in self.prompt

    def test_tool_preference_guidance(self):
        assert "read_file for reading" in self.prompt
        assert "edit for changing existing files" in self.prompt
        assert "glob for filename patterns" in self.prompt
        assert "grep for content search" in self.prompt

    def test_environment_section_builds(self):
        env = _build_environment_section("/tmp/test", "claude-sonnet-4-6", "May 2025")
        assert "Primary working directory: /tmp/test" in env
        assert "Platform:" in env
        assert "Shell:" in env
        assert "claude-sonnet-4-6" in env


class TestToolSchemaAlignment:
    tool_map = _ide_tool_classes()

    def test_tool_count(self):
        assert len(self.tool_map) >= 10

    def test_tool_names_cover_core(self):
        required = {"read_file", "edit", "write_file", "bash", "glob", "grep", "think", "finish", "todo_write"}
        assert not (required - set(self.tool_map))

    def test_read_schema(self):
        tool = self.tool_map["read_file"]
        props = tool.INPUT_SCHEMA["properties"]
        assert "path" in props or "file_path" in props
        assert "offset" in props
        assert "limit" in props
        assert tool.IS_READONLY
        assert tool.IS_CONCURRENCY_SAFE

    def test_edit_schema(self):
        tool = self.tool_map["edit"]
        props = tool.INPUT_SCHEMA["properties"]
        assert "old_string" in props
        assert "new_string" in props
        assert "replace_all" in props
        assert not tool.IS_READONLY

    def test_write_schema(self):
        tool = self.tool_map["write_file"]
        props = tool.INPUT_SCHEMA["properties"]
        assert "file_path" in props or "path" in props
        assert "content" in props

    def test_bash_schema(self):
        tool = self.tool_map["bash"]
        props = tool.INPUT_SCHEMA["properties"]
        assert "command" in props
        assert "cwd" in props
        assert "timeout" in props or "timeout_sec" in props
        assert not tool.IS_CONCURRENCY_SAFE

    def test_search_tools_schema(self):
        assert "pattern" in self.tool_map["glob"].INPUT_SCHEMA["properties"]
        grep_props = self.tool_map["grep"].INPUT_SCHEMA["properties"]
        assert "pattern" in grep_props
        assert set(grep_props["output_mode"]["enum"]) == {"content", "files_with_matches", "count"}

    def test_todo_and_think_schema(self):
        todo_props = self.tool_map["todo_write"].INPUT_SCHEMA["properties"]
        assert "todos" in todo_props
        assert "thought" in self.tool_map["think"].INPUT_SCHEMA["properties"]

    def test_finish_schema(self):
        assert "result" in self.tool_map["finish"].INPUT_SCHEMA["properties"]

    def test_all_tools_generate_api_spec(self):
        for tool in self.tool_map.values():
            spec = tool.to_api_spec()
            assert spec["name"] == tool.TOOL_NAME
            assert "description" in spec
            assert "input_schema" in spec


class TestConfigEquivalence:
    cfg = IDE_LOOP_CONFIG

    def test_turns_and_context(self):
        assert self.cfg.max_turns == 100
        assert self.cfg.context_window == 200_000

    def test_retry_config(self):
        assert self.cfg.retry.max_retries == 10
        assert self.cfg.retry.base_delay_ms == 500
        assert self.cfg.retry.jitter_factor == 0.25

    def test_compaction_config(self):
        assert self.cfg.compact.auto_compact_enabled
        assert self.cfg.compact.max_messages == 120
        assert self.cfg.compact.max_tool_output == 20_000
        assert self.cfg.compact.truncation_strategy == "head_tail"

    def test_concurrency_config(self):
        assert self.cfg.enable_tool_concurrency
        assert self.cfg.max_concurrent_tools == 10
        assert self.cfg.budget_warning_threshold == 0.9


class TestLoopStructureEquivalence:
    def test_subclass_of_routerized_agent_node_loop(self):
        assert issubclass(NativeIdeAgent, AgentNodeLoop)

    def test_loop_hooks_exist(self):
        assert hasattr(NativeIdeAgent, "run")
        assert hasattr(NativeIdeAgent, "build_prompt_builder")
        assert hasattr(NativeIdeAgent, "build_extract_result")
        assert hasattr(NativeIdeAgent, "build_tool_context")

    def test_spec_drives_tools(self):
        assert NativeIdeAgent.SPEC.name == "NativeIdeAgent"
        assert "edit" in NativeIdeAgent.SPEC.tools
        assert len(NativeIdeAgent.SPEC.tools) >= 9

    def test_no_llm_override_in_init(self):
        import inspect

        source = inspect.getsource(NativeIdeAgent.__init__)
        assert "self._llm =" not in source
        assert "self._llm_no_tools =" not in source


class TestCompressionEquivalence:
    def test_compaction_helpers_exist(self):
        from omnicompany.runtime.agent.agent_loop_compact import (
            apply_microcompact,
            apply_truncation,
            apply_sliding_window,
            auto_compact,
        )

        assert callable(apply_microcompact)
        assert callable(apply_truncation)
        assert callable(apply_sliding_window)
        assert callable(auto_compact)

    def test_truncation_strategy_executes(self):
        from omnicompany.runtime.agent.agent_loop_compact import truncate_content

        result = truncate_content("line\n" * 5000, max_chars=1000, strategy="head_tail")
        assert len(result) <= 1100
        assert "truncated" in result.lower() or "..." in result


class TestStopReasonHandling:
    def test_stop_reason_check_in_llm_call_router(self):
        import inspect

        source = inspect.getsource(LLMCallRouter.run)
        assert 'stop_reason == "max_tokens"' in source
        assert "tool_use_blocks = []" in source


class TestLLMMetering:
    def test_meter_singleton(self):
        assert LLMMeter.get_instance() is LLMMeter.get_instance()

    def test_record_and_query(self):
        meter = LLMMeter()
        meter.reset()
        rec = LLMCallRecord(
            model="claude-sonnet-4-6",
            role="ide_agent",
            caller="test.unit",
            input_tokens=1000,
            output_tokens=500,
            cost_usd=0.0105,
            latency_ms=1200,
            stop_reason="end_turn",
        )
        meter.record(rec)
        assert meter.get_records(caller="test.unit")[0].model == "claude-sonnet-4-6"
        assert meter.get_records(caller="nonexistent") == []

    def test_pricing_table_completeness(self):
        for model in ["claude-sonnet-4-6", "glm-5", "qwen3.5-plus"]:
            assert model in _MODEL_PRICING

    def test_estimate_cost_accuracy(self):
        assert abs(_estimate_cost("claude-sonnet-4-6", 1_000_000, 0) - 3.00) < 0.01
        assert abs(_estimate_cost("claude-sonnet-4-6", 0, 1_000_000) - 15.00) < 0.01

    def test_unknown_model_has_fallback_pricing(self):
        assert _estimate_cost("unknown-model-xyz", 1000, 500) > 0
