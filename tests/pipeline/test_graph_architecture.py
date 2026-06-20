"""测试新 Graph 架构 (Phase A-C)

验证：
1. GraphSpec 别名正常工作
2. 工具节点（BashRouter, EditorRouter 等）独立可用
3. 语义节点（DeathZone, PainClassify 等）独立可用
4. 运行时 DAG 构建正确
5. run_agent_v2 端到端可用（mock LLM）
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from omnicompany.protocol.anchor import Verdict, VerdictKind


# ── Phase A: GraphSpec 别名 ──


class TestGraphAliases:
    def test_graph_node_is_pipeline_node(self):
        from omnicompany.protocol.pipeline import GraphNode, PipelineNode
        assert GraphNode is PipelineNode

    def test_graph_edge_is_pipeline_edge(self):
        from omnicompany.protocol.pipeline import GraphEdge, PipelineEdge
        assert GraphEdge is PipelineEdge

    def test_graph_spec_is_pipeline_spec(self):
        from omnicompany.protocol.pipeline import GraphSpec, PipelineSpec
        assert GraphSpec is PipelineSpec

    def test_subgraph_id_field_exists(self):
        from omnicompany.protocol.pipeline import GraphNode, NodeKind
        node = GraphNode(id="test", kind=NodeKind.ANCHOR, subgraph_id="sub-1")
        assert node.subgraph_id == "sub-1"

    def test_condition_expr_field_exists(self):
        from omnicompany.protocol.pipeline import GraphEdge
        edge = GraphEdge(source="a", target="b", condition_expr="pain > 0.5")
        assert edge.condition_expr == "pain > 0.5"


# ── Phase B: 工具节点 ──


class TestToolNodes:
    def test_bash_router_success(self):
        from omnicompany.runtime.nodes.tools import BashRouter
        mock_executor = MagicMock()
        mock_executor.execute_shell.return_value = "hello\n[returncode: 0]"
        router = BashRouter(mock_executor)
        v = router.run({"command": "echo hello"})
        assert v.kind == VerdictKind.PASS
        assert v.output["exit_code"] == 0

    def test_bash_router_failure(self):
        from omnicompany.runtime.nodes.tools import BashRouter
        mock_executor = MagicMock()
        mock_executor.execute_shell.return_value = "error\n[returncode: 1]"
        router = BashRouter(mock_executor)
        v = router.run({"command": "bad_cmd"})
        assert v.kind == VerdictKind.FAIL
        assert v.output["exit_code"] == 1

    def test_editor_router(self):
        from omnicompany.runtime.nodes.tools import EditorRouter
        mock_executor = MagicMock()
        mock_executor.execute_editor.return_value = "File content here..."
        router = EditorRouter(mock_executor)
        v = router.run({"command": "view", "path": "/test"})
        assert v.kind == VerdictKind.PASS

    def test_think_router(self):
        from omnicompany.runtime.nodes.tools import ThinkRouter
        router = ThinkRouter()
        v = router.run({"thought": "I should try X"})
        assert v.kind == VerdictKind.PASS
        assert "thought" in v.output

    def test_finish_router(self):
        from omnicompany.runtime.nodes.tools import FinishRouter
        router = FinishRouter()
        v = router.run({"message": "Done!"})
        assert v.kind == VerdictKind.PASS
        assert v.output["finished"] is True

    def test_tool_dispatch_routes_correctly(self):
        from omnicompany.runtime.nodes.tools import ToolDispatchRouter
        mock_executor = MagicMock()
        mock_executor.execute_shell.return_value = "ok\n[returncode: 0]"
        router = ToolDispatchRouter(mock_executor)

        v_bash = router.run({"tool_name": "bash", "tool_args": {"command": "ls"}})
        assert v_bash.kind == VerdictKind.PASS

        v_think = router.run({"tool_name": "think", "tool_args": {"thought": "hmm"}})
        assert v_think.kind == VerdictKind.PASS

        v_finish = router.run({"tool_name": "finish", "tool_args": {"message": "done"}})
        assert v_finish.kind == VerdictKind.PASS

        v_unknown = router.run({"tool_name": "unknown_tool", "tool_args": {}})
        assert v_unknown.kind == VerdictKind.FAIL


# ── Phase C: 语义节点 ──


class TestSemanticNodes:
    def test_death_zone_passes_safe_call(self):
        from omnicompany.runtime.nodes.semantic import DeathZoneCheckRouter
        router = DeathZoneCheckRouter()
        v = router.run({"tool_name": "bash", "tool_args": {"command": "echo hi"}})
        assert v.kind == VerdictKind.PASS

    def test_death_zone_blocks_dangerous_call(self):
        from omnicompany.runtime.nodes.semantic import DeathZoneCheckRouter
        router = DeathZoneCheckRouter()
        v = router.run({"tool_name": "bash", "tool_args": {"command": "rm -rf omnicompany"}})
        assert v.kind == VerdictKind.FAIL
        assert "DEATH ZONE" in v.output.get("result", "")

    def test_truth_inject_without_mirror(self):
        from omnicompany.runtime.nodes.semantic import TruthInjectRouter
        router = TruthInjectRouter(mirror=None)
        v = router.run({"system_prompt": "base prompt"})
        assert v.kind == VerdictKind.PASS
        # mirror=None 时不注入自我认知，但仍附加工作区规范
        assert v.output["system_prompt"].startswith("base prompt")
        assert "base prompt" in v.output["system_prompt"]

    def test_truth_inject_with_mirror(self):
        from omnicompany.runtime.nodes.semantic import TruthInjectRouter
        mock_mirror = MagicMock()
        mock_mirror.get_current_concept.return_value = "I am omnicompany."
        router = TruthInjectRouter(mirror=mock_mirror)
        v = router.run({"system_prompt": "base prompt"})
        assert v.kind == VerdictKind.PASS
        assert "I am omnicompany" in v.output["system_prompt"]
        assert v.output.get("truth_injected") is True

    def test_pain_classify_no_pain(self):
        from omnicompany.runtime.nodes.semantic import PainClassifyRouter
        router = PainClassifyRouter()
        v = router.run({
            "trace_step": {
                "trace_id": "t1", "step_num": 0, "node_id": "n1",
                "exit_code": 0, "token_cost": 100, "violations": 0,
                "is_success": True, "steps_budget": 50,
            }
        })
        assert v.kind == VerdictKind.PASS

    def test_reward_compute(self):
        from omnicompany.runtime.nodes.semantic import RewardComputeRouter
        router = RewardComputeRouter()
        v = router.run({
            "actual_tokens": 500,
            "budget_tokens": 10000,
            "actual_time": 10.0,
            "budget_time": 300.0,
            "new_route_nodes": 3,
            "total_steps": 5,
            "failed_steps": 1,
        })
        assert v.kind == VerdictKind.PASS
        assert "reward_composite" in v.output
        assert isinstance(v.output["reward_composite"], float)

    def test_escalation_check_no_escalate(self):
        from omnicompany.runtime.nodes.semantic import EscalationCheckRouter
        router = EscalationCheckRouter()
        v = router.run({"avg_pain": 0.2})
        assert v.kind == VerdictKind.PASS
        assert v.output["escalate"] is False

    def test_escalation_check_escalate(self):
        from omnicompany.runtime.nodes.semantic import EscalationCheckRouter
        router = EscalationCheckRouter()
        v = router.run({"avg_pain": 0.8})
        assert v.kind == VerdictKind.FAIL
        assert v.output["escalate"] is True

    def test_mutation_judge_router(self):
        from omnicompany.runtime.nodes.semantic import MutationJudgeRouter
        router = MutationJudgeRouter()
        v = router.run({
            "acc_history": [0.3, 0.5, 0.6],
            "info_gap": 0.5,
            "eta": 1.0,
        })
        assert v.kind == VerdictKind.PASS
        jd = v.output["judge_decision"]
        assert "category" in jd
        assert "level" in jd


# ── Runtime DAG 构建 ──


class TestRuntimeGraph:
    def test_build_runtime_graph(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        assert graph.id == "runtime-dag-v3"
        node_ids = {n.id for n in graph.nodes}
        expected = {
            "context", "truth_inject", "llm", "death_zone",
            "intent_parse", "route_retrieve", "boltzmann_select",
            "tool_dispatch", "pain_classify", "pain_propagate",
            "reward_compute", "escalation_check", "convergence_audit",
            "guardian_check",
        }
        for nid in expected:
            assert nid in node_ids, f"Missing node: {nid}"
        assert len(graph.nodes) >= 14

    def test_build_runtime_bindings(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_bindings
        bindings = build_runtime_bindings()
        expected = {
            "context", "truth_inject", "llm", "death_zone",
            "intent_parse", "route_retrieve", "boltzmann_select",
            "tool_dispatch", "pain_classify", "pain_propagate",
            "reward_compute", "escalation_check", "convergence_audit",
            "guardian_check",
        }
        for nid in expected:
            assert nid in bindings, f"Missing binding: {nid}"

    def test_graph_has_valid_structure(self):
        """验证运行时图结构：所有边引用的节点都存在"""
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()

        node_ids = {n.id for n in graph.nodes}
        for edge in graph.edges:
            assert edge.source in node_ids, f"Edge source '{edge.source}' not in nodes"
            assert edge.target in node_ids, f"Edge target '{edge.target}' not in nodes"

        assert graph.entry in node_ids, "Entry node not in graph"

    def test_forward_path_is_acyclic(self):
        """验证单步前向路径（context→llm→...→terminal）无环

        回到 context 的边是 GraphRunner 的"下一步"入口，不算单步内的环。
        """
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()

        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for e in graph.edges:
            if e.target == "context" and e.source != "context":
                continue
            adj[e.source].append(e.target)

        visited: set[str] = set()
        path: set[str] = set()

        def has_cycle(node: str) -> bool:
            if node in path:
                return True
            if node in visited:
                return False
            visited.add(node)
            path.add(node)
            for neighbor in adj.get(node, []):
                if has_cycle(neighbor):
                    return True
            path.discard(node)
            return False

        for node in adj:
            if has_cycle(node):
                pytest.fail(f"Forward path has cycle at '{node}'")


# ── Phase C: Death Zone 适配器 ──


class TestDeathZoneAdapter:
    def test_passes_safe_calls(self):
        from omnicompany.runtime.exec.graph_builder import _DeathZoneAdapter
        adapter = _DeathZoneAdapter()
        result = adapter.run({
            "tool_calls": [
                {"tool_name": "bash", "tool_args": {"command": "echo hi"}, "tool_use_id": "t1"},
            ],
            "system_prompt": "test",
            "messages": [],
        })
        assert result.kind == VerdictKind.PASS

    def test_blocks_dangerous_calls(self):
        from omnicompany.runtime.exec.graph_builder import _DeathZoneAdapter
        adapter = _DeathZoneAdapter()
        result = adapter.run({
            "tool_calls": [
                {"tool_name": "bash", "tool_args": {"command": "rm -rf omnicompany"}, "tool_use_id": "t1"},
            ],
            "system_prompt": "test",
            "messages": [],
        })
        assert result.kind == VerdictKind.FAIL
        assert "DEATH ZONE" in result.output.get("tool_results", [{}])[0].get("content", "")


# ── run_agent_v2 端到端 (mock LLM) ──


class TestRunAgentV2:
    @pytest.mark.asyncio
    async def test_v2_finish_immediately(self, tmp_path):
        """LLM 直接返回文本 → finish"""
        mock_response = MagicMock()
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Task done."
        mock_response.content = [text_block]

        with patch("omnicompany.runtime.llm.llm.LLMClient.call", return_value=mock_response):
            from omnicompany.runtime.agent.agent_loop import run_agent_v2
            result = await run_agent_v2(
                task="Say hello",
                db_path=str(tmp_path / "events.db"),
                intent_db_path=str(tmp_path / "intent.db"),
                max_steps=10,
            )
            assert "Task done" in result

    @pytest.mark.asyncio
    async def test_v2_tool_then_finish(self, tmp_path):
        """LLM 先调 bash → 再 finish"""
        call_count = [0]

        def mock_call(messages, system="", **kw):
            call_count[0] += 1
            resp = MagicMock()

            if call_count[0] == 1:
                tool_block = MagicMock()
                tool_block.type = "tool_use"
                tool_block.id = "tu1"
                tool_block.name = "bash"
                tool_block.input = {"command": "echo hello"}
                resp.content = [tool_block]
            else:
                text_block = MagicMock()
                text_block.type = "text"
                text_block.text = "All done."
                resp.content = [text_block]

            return resp

        with patch("omnicompany.runtime.llm.llm.LLMClient.call", side_effect=mock_call):
            from omnicompany.runtime.agent.agent_loop import run_agent_v2
            result = await run_agent_v2(
                task="Run echo",
                db_path=str(tmp_path / "events.db"),
                intent_db_path=str(tmp_path / "intent.db"),
                max_steps=30,
            )
            assert "done" in result.lower() or "All done" in result
