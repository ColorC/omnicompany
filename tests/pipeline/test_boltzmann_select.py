"""验证 BoltzmannSelectRouter 真正执行概率选路。

测试场景:
1. 无候选路由 — 透传，route_selected=False
2. 有候选路由（无 route_graph）— 基于 similarity 的 graceful degrade
3. 有候选路由 + 痛觉差异 — 低痛觉路由更容易被选中
4. β 退火效应 — β 越大越贪婪
"""
import sys
sys.path.insert(0, "src")

from omnicompany.runtime.nodes.semantic import BoltzmannSelectRouter


def _make_input(route_candidates: list[dict]) -> dict:
    return {
        "system_prompt": "test",
        "messages": [],
        "tool_calls": [{"tool_name": "bash", "tool_args": {"command": "echo hello"}}],
        "route_candidates": route_candidates,
    }


class TestBoltzmannSelect:

    def test_no_candidates_passthrough(self):
        router = BoltzmannSelectRouter()
        v = router.run(_make_input([]))
        assert v.output["route_selected"] is False
        assert v.output["selected_route"] is None

    def test_single_candidate_selected(self):
        router = BoltzmannSelectRouter()
        v = router.run(_make_input([
            {"steps": ["user_request", "bash_result"], "node_ids": ["n1"],
             "total_weight": 5, "similarity": 0.8},
        ]))
        assert v.output["route_selected"] is True
        assert v.output["selected_route"]["node_id"] == "n1"
        assert len(v.output["selection_probabilities"]) == 1
        assert v.output["selection_probabilities"][0]["prob"] == 1.0

    def test_low_pain_preferred(self):
        """高 β 下，低痛觉路由应更频繁被选中。"""
        from collections import Counter
        from unittest.mock import MagicMock

        mock_rg = MagicMock()

        node_a = MagicMock()
        node_a.pain_score = 0.0
        node_a.success_rate = 0.8
        node_a.hit_count = 10
        node_a.deprecated = False
        node_a.hard_eliminated = False

        node_b = MagicMock()
        node_b.pain_score = 0.9
        node_b.success_rate = 0.3
        node_b.hit_count = 5
        node_b.deprecated = False
        node_b.hard_eliminated = False

        mock_rg.get_node = lambda nid: {"n_low": node_a, "n_high": node_b}.get(nid)

        router = BoltzmannSelectRouter(route_graph=mock_rg, beta=5.0)
        counts = Counter()
        for _ in range(200):
            v = router.run(_make_input([
                {"steps": ["a"], "node_ids": ["n_low"], "total_weight": 10, "similarity": 0.7},
                {"steps": ["b"], "node_ids": ["n_high"], "total_weight": 5, "similarity": 0.7},
            ]))
            if v.output["selected_route"]:
                counts[v.output["selected_route"]["node_id"]] += 1

        assert counts["n_low"] > counts["n_high"], (
            f"Low-pain route should be selected more often: {dict(counts)}"
        )

    def test_probabilities_sum_to_one(self):
        router = BoltzmannSelectRouter()
        v = router.run(_make_input([
            {"steps": ["a"], "node_ids": ["n1"], "total_weight": 10, "similarity": 0.9},
            {"steps": ["b"], "node_ids": ["n2"], "total_weight": 5, "similarity": 0.6},
            {"steps": ["c"], "node_ids": ["n3"], "total_weight": 3, "similarity": 0.3},
        ]))
        probs = [p["prob"] for p in v.output["selection_probabilities"]]
        assert abs(sum(probs) - 1.0) < 0.01, f"Probabilities should sum to 1: {probs}"

    def test_beta_affects_greediness(self):
        """高 β 应更集中地选择低痛觉候选。"""
        from collections import Counter
        from unittest.mock import MagicMock

        mock_rg = MagicMock()

        nodes = {
            "n_best": MagicMock(pain_score=0.0, success_rate=0.9, hit_count=20,
                                deprecated=False, hard_eliminated=False),
            "n_mid": MagicMock(pain_score=0.4, success_rate=0.5, hit_count=10,
                               deprecated=False, hard_eliminated=False),
            "n_bad": MagicMock(pain_score=0.8, success_rate=0.2, hit_count=3,
                               deprecated=False, hard_eliminated=False),
        }
        mock_rg.get_node = lambda nid: nodes.get(nid)

        candidates = [
            {"steps": ["best"], "node_ids": ["n_best"], "total_weight": 20, "similarity": 0.9},
            {"steps": ["mid"], "node_ids": ["n_mid"], "total_weight": 10, "similarity": 0.9},
            {"steps": ["bad"], "node_ids": ["n_bad"], "total_weight": 3, "similarity": 0.9},
        ]

        counts_low = Counter()
        router_low = BoltzmannSelectRouter(route_graph=mock_rg, beta=0.5)
        for _ in range(500):
            v = router_low.run(_make_input(candidates))
            if v.output["selected_route"]:
                counts_low[v.output["selected_route"]["node_id"]] += 1

        counts_high = Counter()
        router_high = BoltzmannSelectRouter(route_graph=mock_rg, beta=6.0)
        for _ in range(500):
            v = router_high.run(_make_input(candidates))
            if v.output["selected_route"]:
                counts_high[v.output["selected_route"]["node_id"]] += 1

        best_ratio_low = counts_low.get("n_best", 0) / 500
        best_ratio_high = counts_high.get("n_best", 0) / 500

        assert best_ratio_high > best_ratio_low, (
            f"High β should be greedier: β=0.5 best_ratio={best_ratio_low:.2f}, "
            f"β=6.0 best_ratio={best_ratio_high:.2f}"
        )
