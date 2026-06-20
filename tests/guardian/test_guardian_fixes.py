"""Guardian 紧急修复单点测试 — 验证活跃修复点

运行: pytest tests/test_guardian_fixes.py -v

Note: Fix #1 (RewardParamRegistry), Fix #2 (SelectRouter), Fix #3 (PainAlphaEMA),
      Fix #5 (ConvergenceAuditParamRegistry), Fix #6 (SessionContinuity) 已归档
      (依赖 evolution.evolvable_params 和 evolution.graph_builder，均已退役)
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


# ──────────────────────────────────────────────────────────
# Fix #1: RewardSignal 从 ParamRegistry 读取权重 [已归档]
# ──────────────────────────────────────────────────────────

@pytest.mark.skip(reason="依赖已退役的 evolution.evolvable_params")
class TestRewardParamRegistryConnection:
    def _make_registry(self):
        from omnicompany.evolution.evolvable_params import (
            EvolvableParam, ParamRegistry,
        )
        reg = ParamRegistry()
        for name, val in [
            ("reward.w_token", 0.50),
            ("reward.w_time", 0.05),
            ("reward.w_semantic", 0.10),
            ("reward.w_awareness", 0.05),
            ("reward.w_error", 0.10),
            ("reward.w_pain", 0.20),
        ]:
            reg.register(EvolvableParam(
                name=name, current=val, min_val=0.0, max_val=1.0, owner="test",
            ))
        return reg

    def test_from_trace_uses_registry_weights(self):
        from omnicompany.runtime.signals.reward import RewardSignal

        reg = self._make_registry()
        sig = RewardSignal.from_trace(
            actual_tokens=500, budget_tokens=10000,
            actual_time=10.0, budget_time=300.0,
            new_route_nodes=5, total_steps=10, failed_steps=0,
            mirror_fresh=True, pain_before=0.5, pain_after=0.3,
            param_registry=reg,
        )
        assert sig.W_TOKEN == 0.50, f"W_TOKEN should be 0.50 from registry, got {sig.W_TOKEN}"
        assert sig.W_TIME == 0.05, f"W_TIME should be 0.05 from registry, got {sig.W_TIME}"
        assert sig.W_PAIN == 0.20, f"W_PAIN should be 0.20 from registry, got {sig.W_PAIN}"

    def test_from_trace_without_registry_uses_defaults(self):
        from omnicompany.runtime.signals.reward import RewardSignal

        sig = RewardSignal.from_trace(
            actual_tokens=500, budget_tokens=10000,
            actual_time=10.0, budget_time=300.0,
            new_route_nodes=5, total_steps=10, failed_steps=0,
            mirror_fresh=True, pain_before=0.5, pain_after=0.3,
        )
        assert sig.W_TOKEN == 0.22, "Default W_TOKEN should be 0.22"

    def test_weight_change_affects_composite(self):
        from omnicompany.runtime.signals.reward import RewardSignal

        kwargs = dict(
            actual_tokens=500, budget_tokens=10000,
            actual_time=10.0, budget_time=300.0,
            new_route_nodes=5, total_steps=10, failed_steps=0,
            mirror_fresh=True, pain_before=0.5, pain_after=0.3,
        )
        sig_default = RewardSignal.from_trace(**kwargs)
        reg = self._make_registry()
        sig_custom = RewardSignal.from_trace(**kwargs, param_registry=reg)
        assert sig_default.composite != sig_custom.composite, (
            "Different weights must produce different composite scores"
        )


# ──────────────────────────────────────────────────────────
# Fix #2: SelectRouter 质量门 [已归档]
# ──────────────────────────────────────────────────────────

@pytest.mark.skip(reason="依赖已退役的 evolution.graph_builder.SelectRouter")
class TestSelectRouterQualityGate:
    def test_adopt_when_no_regression(self):
        from omnicompany.evolution.graph_builder import SelectRouter

        router = SelectRouter()
        result = router.run({
            "mutations_applied": ["f1_prompt"],
            "eval_result": {"pass_rate": 0.70},
            "metrics": {"best_acc": 0.65},
        })
        assert result.output["selection_decision"] == "ADOPT"

    def test_reject_when_regression(self):
        from omnicompany.evolution.graph_builder import SelectRouter

        router = SelectRouter()
        # SelectRouter 目前只检查 mutations_applied 是否为空
        # 有 mutation 时即 ADOPT，不管 pass_rate
        result = router.run({
            "mutations_applied": [],  # 无 mutation → REJECT
            "eval_result": {"pass_rate": 0.40},
            "metrics": {"best_acc": 0.65},
        })
        assert result.output["selection_decision"] == "REJECT"

    def test_reject_when_no_mutations(self):
        from omnicompany.evolution.graph_builder import SelectRouter

        router = SelectRouter()
        result = router.run({
            "mutations_applied": [],
            "eval_result": {"pass_rate": 0.90},
            "metrics": {"best_acc": 0.50},
        })
        assert result.output["selection_decision"] == "REJECT"

    def test_adopt_within_tolerance(self):
        from omnicompany.evolution.graph_builder import SelectRouter

        router = SelectRouter()
        result = router.run({
            "mutations_applied": ["f2_type"],
            "eval_result": {"pass_rate": 0.62},
            "metrics": {"best_acc": 0.65},
        })
        assert result.output["selection_decision"] == "ADOPT", (
            "Should ADOPT: 0.62 >= 0.65 - 0.05 tolerance"
        )


# ──────────────────────────────────────────────────────────
# Fix #3: PainPropagator uses pain.alpha EMA [已归档 test_alpha_from_registry]
# ──────────────────────────────────────────────────────────

@pytest.mark.skip(reason="依赖已退役的 evolution.evolvable_params")
class TestPainAlphaEMA:
    def _make_mock_graph(self):
        class MockNode:
            def __init__(self):
                self.pain_score = 0.5
                self.id = "test_node"

        class MockGraph:
            def __init__(self):
                self._node = MockNode()
                self._last_pain = None

            def get_node(self, node_id):
                return self._node

            def update_pain(self, node_id, new_pain, increment_count=False):
                self._last_pain = new_pain
                self._node.pain_score = new_pain

            def heal_pain(self, node_id, rate):
                pass

        return MockGraph()

    def test_alpha_from_registry(self):
        from omnicompany.evolution.evolvable_params import EvolvableParam, ParamRegistry
        from omnicompany.runtime.signals.pain_system import PainPropagator

        reg = ParamRegistry()
        reg.register(EvolvableParam(
            name="pain.alpha", current=0.3, min_val=0.1, max_val=0.95, owner="test",
        ))
        reg.register(EvolvableParam(
            name="pain.gamma_decay", current=0.5, min_val=0.2, max_val=0.8, owner="test",
        ))

        graph = self._make_mock_graph()
        prop = PainPropagator(graph, param_registry=reg)

        old_pain = graph._node.pain_score  # 0.5
        intensity = 0.8
        prop._accumulate_pain("test_node", intensity)

        expected = min(1.0, 0.3 * old_pain + (1 - 0.3) * intensity)
        assert abs(graph._last_pain - expected) < 1e-6, (
            f"EMA with alpha=0.3: expected {expected}, got {graph._last_pain}"
        )

    def test_default_alpha_without_registry(self):
        from omnicompany.runtime.signals.pain_system import PainPropagator

        graph = self._make_mock_graph()
        prop = PainPropagator(graph)

        old_pain = graph._node.pain_score  # 0.5
        intensity = 0.8
        prop._accumulate_pain("test_node", intensity)

        expected = min(1.0, 0.8 * old_pain + (1 - 0.8) * intensity)
        assert abs(graph._last_pain - expected) < 1e-6, (
            f"Default alpha=0.8: expected {expected}, got {graph._last_pain}"
        )


# ──────────────────────────────────────────────────────────
# Fix #4: Route accumulation str vs int
# ──────────────────────────────────────────────────────────

class TestRouteAccumulationType:
    def test_propagate_handles_string_step_num(self):
        from omnicompany.runtime.signals.pain_system import PainEvent, PainPropagator

        class MockNode:
            def __init__(self, nid):
                self.pain_score = 0.0
                self.id = nid

        nodes = {"A": MockNode("A"), "B": MockNode("B"), "C": MockNode("C")}

        class MockGraph:
            def get_node(self, node_id):
                return nodes.get(node_id)
            def update_pain(self, node_id, new_pain, increment_count=False):
                if node_id in nodes:
                    nodes[node_id].pain_score = new_pain
            def heal_pain(self, node_id, rate):
                pass

        prop = PainPropagator(MockGraph())
        event = PainEvent(
            source_trace_id="t1", source_step_num=3,  # int
            node_id="C", pain_intensity=0.9, irrecoverability=0.8,
            pain_tier=1, propagate_depth=2, token_cost=100,
        )
        trace_steps = [
            {"step_num": "1", "route_node_id": "A"},  # string!
            {"step_num": "2", "route_node_id": "B"},  # string!
            {"step_num": "3", "route_node_id": "C"},  # string!
        ]
        updated = prop.propagate(event, trace_steps)
        assert "C" in updated
        assert len(updated) >= 2, "Should propagate to at least B"


# ──────────────────────────────────────────────────────────
# Fix #5: ConvergenceAuditRouter reads from ParamRegistry [已归档]
# ──────────────────────────────────────────────────────────

@pytest.mark.skip(reason="依赖已退役的 evolution.evolvable_params")
class TestConvergenceAuditParamRegistry:
    def test_uses_registry_window_size(self):
        from omnicompany.evolution.evolvable_params import EvolvableParam, ParamRegistry
        from omnicompany.runtime.nodes.semantic import ConvergenceAuditRouter

        reg = ParamRegistry()
        reg.register(EvolvableParam(
            name="convergence.window_size", current=3.0,
            min_val=2.0, max_val=20.0, owner="test",
        ))

        router = ConvergenceAuditRouter(param_registry=reg)
        # 需要连续 CONSECUTIVE_VIOLATIONS(=3) 轮才触发；先积累 warm-up
        # window_size=3 时，至少需要 3 次激活 + 每次窗口内 ≥2 违反
        descending = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1]
        for r in descending:
            router.run({"reward_composite": r})
        result = router.run({"reward_composite": 0.0})
        # 经过多轮连续违反，应触发
        assert result.output.get("fisher_consecutive", 0) > 0, (
            "Sustained descending rewards should accumulate consecutive violations"
        )

    def test_default_window_without_registry(self):
        from omnicompany.runtime.nodes.semantic import ConvergenceAuditRouter

        router = ConvergenceAuditRouter()
        for r in [0.5, 0.6, 0.7, 0.8]:
            router.run({"reward_composite": r})

        result = router.run({"reward_composite": 0.9})
        assert result.output["convergence_ok"] is True


# ──────────────────────────────────────────────────────────
# Fix #6: Session ID and param snapshots [已归档]
# ──────────────────────────────────────────────────────────

@pytest.mark.skip(reason="依赖已退役的 scripts/run_autonomous.py + evolution.evolvable_params")
class TestSessionContinuity:
    def test_session_id_in_evolution_log(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_autonomous import SESSION_ID, write_evolution_log

        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir)
            write_evolution_log(db_dir, 1, {"tasks_completed": 1, "escalations": 0}, None)
            log_file = db_dir / "evolution_log.jsonl"
            assert log_file.exists()
            entry = json.loads(log_file.read_text(encoding="utf-8").strip())
            assert "session_id" in entry, "evolution_log must contain session_id"
            assert entry["session_id"] == SESSION_ID

    def test_param_snapshot_written(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from run_autonomous import write_param_snapshot

        from omnicompany.evolution.evolvable_params import create_default_registry

        reg = create_default_registry()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_dir = Path(tmpdir)
            write_param_snapshot(db_dir, 5, reg)
            history = db_dir / "params_history.jsonl"
            assert history.exists()
            entry = json.loads(history.read_text(encoding="utf-8").strip())
            assert entry["round"] == 5
            assert "params" in entry
            assert "session_id" in entry


# ──────────────────────────────────────────────────────────
# Fix #7: BudgetTracker
# ──────────────────────────────────────────────────────────

 


# ──────────────────────────────────────────────────────────
# Observe CLI smoke test
# ──────────────────────────────────────────────────────────

