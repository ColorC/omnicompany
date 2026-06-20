"""
Full DAG regression test — the gatekeeper suite.

Every change to the graph builder, runner, or node bindings
must pass this suite before merge.

Tests:
1. Graph structure validity (node count, edge count, entry)
2. All nodes have bindings
3. All edges connect valid nodes
4. Three path scenarios: mature/hypothetical/unknown
5. NodeMaturity fields present on all nodes
6. PipelineSpec has parallel_groups field
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


class TestGraphStructure:
    """Validate the structure of the runtime DAG."""

    def test_graph_builds_without_error(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        assert graph is not None
        assert graph.id == "runtime-dag-v3"

    def test_node_count(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        assert len(graph.nodes) >= 17, f"Expected >=17 nodes, got {len(graph.nodes)}"

    def test_edge_count(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        assert len(graph.edges) >= 18, f"Expected >=18 edges, got {len(graph.edges)}"

    def test_entry_is_task_intent_parse(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        assert graph.entry == "task_intent_parse"

    def test_all_edges_connect_valid_nodes(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        node_ids = {n.id for n in graph.nodes}

        for edge in graph.edges:
            assert edge.source in node_ids, f"Edge source '{edge.source}' not in nodes"
            assert edge.target in node_ids, f"Edge target '{edge.target}' not in nodes"

    def test_entry_node_exists(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        node_ids = {n.id for n in graph.nodes}
        assert graph.entry in node_ids

    def test_no_self_loops(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        for edge in graph.edges:
            assert edge.source != edge.target, f"Self-loop on '{edge.source}'"


class TestNodeBindings:
    """Verify all graph nodes have corresponding bindings."""

    def test_all_nodes_have_bindings(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_bindings, build_runtime_graph
        graph = build_runtime_graph()
        bindings = build_runtime_bindings()

        for node in graph.nodes:
            assert node.id in bindings, f"Node '{node.id}' has no binding"

    def test_no_extra_bindings(self):
        from omnicompany.runtime.exec.graph_builder import build_runtime_bindings, build_runtime_graph
        graph = build_runtime_graph()
        bindings = build_runtime_bindings()
        node_ids = {n.id for n in graph.nodes}

        for binding_id in bindings:
            assert binding_id in node_ids, (
                f"Binding '{binding_id}' has no corresponding node in the graph"
            )


class TestNodeMaturityFields:
    """Verify NodeMaturity fields are present on all pipeline nodes."""

    def test_all_nodes_have_maturity(self):
        from omnicompany.protocol.pipeline import NodeMaturity
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()

        for node in graph.nodes:
            assert hasattr(node, "maturity")
            assert isinstance(node.maturity, NodeMaturity)

    def test_new_nodes_are_hypothetical(self):
        from omnicompany.protocol.pipeline import NodeMaturity
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()

        hypothetical_nodes = [n for n in graph.nodes if n.maturity == NodeMaturity.HYPOTHETICAL]
        assert len(hypothetical_nodes) >= 2, (
            f"Expected at least 2 hypothetical nodes, got {len(hypothetical_nodes)}"
        )

    def test_legacy_nodes_are_mature(self):
        from omnicompany.protocol.pipeline import NodeMaturity
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()

        legacy_ids = {"context", "truth_inject", "llm", "death_zone", "tool_dispatch"}
        for node in graph.nodes:
            if node.id in legacy_ids:
                assert node.maturity == NodeMaturity.MATURE, (
                    f"Legacy node '{node.id}' should be MATURE, got {node.maturity}"
                )


class TestSemanticRoutingPaths:
    """Verify the three routing paths exist in the graph."""

    def test_known_type_path(self):
        """task_intent_parse → semantic_classify → specialized_dispatch → context"""
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        edges = {(e.source, e.target): e for e in graph.edges}

        assert ("task_intent_parse", "semantic_classify") in edges
        assert ("semantic_classify", "specialized_dispatch") in edges
        assert ("specialized_dispatch", "context") in edges

    def test_unknown_type_path(self):
        """task_intent_parse → semantic_classify → context (fallback)"""
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        from omnicompany.protocol.anchor import VerdictKind
        graph = build_runtime_graph()

        fail_edges = [
            e for e in graph.edges
            if e.source == "semantic_classify" and e.target == "context"
            and e.condition == VerdictKind.FAIL
        ]
        assert len(fail_edges) >= 1

    def test_main_loop_path_intact(self):
        """context → truth_inject → llm → death_zone → ... still works"""
        from omnicompany.runtime.exec.graph_builder import build_runtime_graph
        graph = build_runtime_graph()
        edges = {(e.source, e.target) for e in graph.edges}

        assert ("context", "truth_inject") in edges
        assert ("truth_inject", "llm") in edges


class TestPipelineSpecExtensions:
    """Verify PipelineSpec has the new fields."""

    def test_parallel_groups_field_exists(self):
        from omnicompany.protocol.pipeline import PipelineSpec
        spec = PipelineSpec(
            id="test", name="test", description="test",
            nodes=[], edges=[], entry="x",
            parallel_groups=[["pain_classify", "reward_compute"]],
        )
        assert spec.parallel_groups == [["pain_classify", "reward_compute"]]

    def test_parallel_groups_default_empty(self):
        from omnicompany.protocol.pipeline import PipelineSpec
        spec = PipelineSpec(
            id="test", name="test", description="test",
            nodes=[], edges=[], entry="x",
        )
        assert spec.parallel_groups == []
