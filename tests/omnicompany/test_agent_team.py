"""Agent Team 纯 bus 驱动验证 (Phase 1 pilot · 2026-04-20 用户洞察).

场景:
  agent.request (user 输入) → ContextScript → prompt_context
  → LLM (tool_call) → Tool → tool_result [新子 job]
  → ContextScript (新 job 里再激活) → prompt_context (round 2)
  → LLM (finish) → Finalizer → final_output (sink)

验证:
1. 每轮循环 = 一个 job (parent_job_id 链完整)
2. Q1 worker 单 job 单次激活 (子 job 独立 trace_id 允许 ContextScript/LLM 再激活)
3. FORMAT_IN_MODE="or" 正确 (AgentContextScript 订阅两种 material 任一激活)
4. 多 worker 订阅同 material (Q3: Tool + Finalizer 都订 llm_response, 各激活一次, kind 不符的 FAIL 跳过)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from omnicompany.packages.services.omnicompany import (
    MaterialDispatcher,
    AgentContextScriptWorker,
    AgentLLMWorker,
    AgentToolWorker,
    AgentFinalizerWorker,
)


def _agent_team():
    return [
        AgentContextScriptWorker(),
        AgentLLMWorker(),
        AgentToolWorker(),
        AgentFinalizerWorker(),
    ]


class TestAgentTeamBusDriven:
    @pytest.mark.asyncio
    async def test_two_round_agent_loop(self):
        """完整跑通 2 轮: request → tool_call (J0) → tool_result (J1) → finish (J1) → sink."""
        workers = _agent_team()
        dispatcher = MaterialDispatcher(workers, max_iterations=50)
        events = await dispatcher.run_job(
            initial_material_id="agent.request",
            initial_payload={"content": "hello agent"},
            job_id="J_ROOT",
        )

        event_types = [e.event_type for e in events]

        # 应包含所有阶段的 material
        assert "agent.request" in event_types, f"源缺失: {event_types}"
        assert "agent.prompt_context" in event_types
        assert "agent.llm_response" in event_types
        assert "agent.tool_result" in event_types
        assert "agent.final_output" in event_types, f"终止 sink 缺失: {event_types}"

    @pytest.mark.asyncio
    async def test_child_job_created_on_tool_result(self):
        """验证 tool_result 产生新子 job (trace_id != root job_id)."""
        workers = _agent_team()
        dispatcher = MaterialDispatcher(workers, max_iterations=50)
        events = await dispatcher.run_job(
            initial_material_id="agent.request",
            initial_payload={"content": "hello"},
            job_id="J_ROOT",
        )

        trace_ids = {e.trace_id for e in events}
        # 应该至少两个 job: J_ROOT (首轮) + 某子 job (tool_result 触发)
        assert len(trace_ids) >= 2, f"未创建子 job, trace_ids={trace_ids}"
        assert "J_ROOT" in trace_ids

    @pytest.mark.asyncio
    async def test_parent_job_id_chain(self):
        """子 job 的 tool_result event 的 payload 应带 _parent_job_id 指向 root."""
        workers = _agent_team()
        dispatcher = MaterialDispatcher(workers, max_iterations=50)
        events = await dispatcher.run_job(
            initial_material_id="agent.request",
            initial_payload={"content": "hello"},
            job_id="J_ROOT",
        )

        # 找到 tool_result event (由 AgentToolWorker 产, 带 _emit_as_new_job)
        tool_results = [e for e in events if e.event_type == "agent.tool_result"]
        assert len(tool_results) == 1
        tr = tool_results[0]
        # trace_id 必须是子 job (不是 J_ROOT)
        assert tr.trace_id != "J_ROOT", "tool_result 未用新 trace_id"
        # payload 应带 _parent_job_id
        assert tr.payload.get("_parent_job_id") == "J_ROOT", (
            f"parent_job_id 链断: {tr.payload}"
        )

    @pytest.mark.asyncio
    async def test_q1_single_activation_per_job(self):
        """Q1 验证: 每个 (job, worker) 激活一次.
        子 job 独立 → ContextScript/LLM 能在根 job 和子 job 各激活一次."""
        workers = _agent_team()
        dispatcher = MaterialDispatcher(workers, max_iterations=50)
        events = await dispatcher.run_job(
            initial_material_id="agent.request",
            initial_payload={"content": "hello"},
            job_id="J_ROOT",
        )

        # 统计每 (trace_id, source) 出现次数 — 每个 worker 每个 job 最多 1 次产出
        from collections import Counter
        per_job_source = Counter(
            (e.trace_id, e.source) for e in events
            if e.source.startswith("worker.")
        )
        for (trace, source), cnt in per_job_source.items():
            assert cnt == 1, f"Q1 违反: {source} 在 trace={trace} 激活 {cnt} 次"

    @pytest.mark.asyncio
    async def test_multi_subscribe_same_material(self):
        """Q3 验证: AgentToolWorker + AgentFinalizerWorker 都订 agent.llm_response,
        各激活一次, 按 kind 分岔(Tool 对 tool_call / Finalizer 对 finish), 不符的 FAIL 不 publish."""
        workers = _agent_team()
        dispatcher = MaterialDispatcher(workers, max_iterations=50)
        events = await dispatcher.run_job(
            initial_material_id="agent.request",
            initial_payload={"content": "hello"},
            job_id="J_ROOT",
        )

        # 期望: 2 次 agent.llm_response (J_ROOT tool_call + 子 job finish)
        # 每轮 Tool/Finalizer 都激活, 只有对应 kind 的 publish output
        llm_responses = [e for e in events if e.event_type == "agent.llm_response"]
        assert len(llm_responses) == 2, f"应有 2 次 LLM response, 实际 {len(llm_responses)}"

        # 一个应是 tool_call (J_ROOT), 一个 finish (子 job)
        kinds = {e.payload.get("kind") for e in llm_responses}
        assert kinds == {"tool_call", "finish"}, f"两种 kind 都应该有: {kinds}"

    @pytest.mark.asyncio
    async def test_final_output_is_sink(self):
        """验证 final_output 是 sink: 无 worker 订阅 agent.final_output."""
        workers = _agent_team()
        subscribed = set()
        for w in workers:
            from omnicompany.packages.services.omnicompany.material_dispatcher import _format_in_set
            s = _format_in_set(w) or set()
            subscribed |= s
        assert "agent.final_output" not in subscribed, (
            f"agent.final_output 应是 sink 无订阅者: {subscribed}"
        )
