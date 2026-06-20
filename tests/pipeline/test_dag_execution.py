"""Tests for DAG execution support in PipelineRunner.

验证：
1. 线性管线向后兼容
2. Fan-out（一对多并发）
3. Fan-in / Join barrier（多对一合并）
4. 钻石 DAG（fan-out + fan-in）
5. 反馈循环兼容
6. 自动 back-edge 检测
7. 预算跨并发分支共享
8. 输入合并策略
"""

import asyncio
from typing import Any

import pytest

from omnicompany.bus.memory import MemoryBus
from omnicompany.protocol.anchor import (
    AnchorSpec, Route, RouteAction, ValidatorKind, ValidatorSpec, VerdictKind,
    TransformerSpec, TransformMethod,
    Verdict,
)
from omnicompany.protocol.pipeline import (
    NodeKind, NodeMaturity, PipelineEdge, PipelineNode, PipelineSpec,
)
from omnicompany.runtime.routing.router import Router
from omnicompany.runtime.exec.runner import PipelineRunner


# ── 测试用 Router 实现 ──────────────────────────────────────────────────────

class PassthroughRouter(Router):
    """直传 Router: 原样返回输入，PASS verdict。"""
    FORMAT_IN = "test"
    FORMAT_OUT = "test"
    DESCRIPTION = "passthrough"

    def run(self, input_data):
        return Verdict(kind=VerdictKind.PASS, output=input_data, diagnosis="pass")


class AppendRouter(Router):
    """追加标记 Router: 在 dict 中追加 node_id，证明自己被执行过。"""
    FORMAT_IN = "test"
    FORMAT_OUT = "test"
    DESCRIPTION = "append marker"

    def __init__(self, marker: str):
        self._marker = marker

    def run(self, input_data):
        out = dict(input_data) if isinstance(input_data, dict) else {}
        visited = out.get("_visited", [])
        out["_visited"] = visited + [self._marker]
        out[f"_result_{self._marker}"] = f"done_by_{self._marker}"
        return Verdict(kind=VerdictKind.PASS, output=out, diagnosis=f"{self._marker} done")


class SlowRouter(Router):
    """模拟耗时 Router，用于验证并发执行。"""
    FORMAT_IN = "test"
    FORMAT_OUT = "test"
    DESCRIPTION = "slow"

    def __init__(self, marker: str, delay: float = 0.1):
        self._marker = marker
        self._delay = delay

    async def run(self, input_data):
        await asyncio.sleep(self._delay)
        out = dict(input_data) if isinstance(input_data, dict) else {}
        visited = out.get("_visited", [])
        out["_visited"] = visited + [self._marker]
        return Verdict(kind=VerdictKind.PASS, output=out, diagnosis=f"{self._marker} done")


class CountingDecisionRouter(Router):
    """模拟 LLM decision 节点，用于验证预算共享。"""
    FORMAT_IN = "test"
    FORMAT_OUT = "test"
    DESCRIPTION = "decision"

    def __init__(self, marker: str):
        self._marker = marker

    def run(self, input_data):
        out = dict(input_data) if isinstance(input_data, dict) else {}
        out[f"_decision_{self._marker}"] = True
        return Verdict(kind=VerdictKind.PASS, output=out, diagnosis=f"decision {self._marker}")


class FailOnceRouter(Router):
    """第一次 FAIL，之后 PASS。用于测试 RETRY。"""
    FORMAT_IN = "test"
    FORMAT_OUT = "test"
    DESCRIPTION = "fail-once"

    def __init__(self):
        self._call_count = 0

    def run(self, input_data):
        self._call_count += 1
        if self._call_count == 1:
            return Verdict(kind=VerdictKind.FAIL, output=input_data, diagnosis="first fail")
        return Verdict(kind=VerdictKind.PASS, output=input_data, diagnosis="now pass")


# ── 辅助函数 ────────────────────────────────────────────────────────────────

def _make_transformer_node(node_id: str) -> PipelineNode:
    return PipelineNode(
        id=node_id,
        kind=NodeKind.TRANSFORMER,
        transformer=TransformerSpec(
            id=f"t-{node_id}",
            name=node_id,
            from_format="test",
            to_format="test",
            method=TransformMethod.RULE,
            description=node_id,
        ),
        maturity=NodeMaturity.CRYSTALLIZED,
    )


def _make_anchor_node(node_id: str, routes: dict | None = None, kind: str = "hard") -> PipelineNode:
    if routes is None:
        routes = {
            VerdictKind.PASS: Route(action=RouteAction.NEXT),
            VerdictKind.FAIL: Route(action=RouteAction.NEXT),
        }
    return PipelineNode(
        id=node_id,
        kind=NodeKind.ANCHOR,
        anchor=AnchorSpec(
            id=f"a-{node_id}",
            name=node_id,
            format_in="test",
            format_out="test",
            validator=ValidatorSpec(id=f"v-{node_id}", kind=ValidatorKind(kind), description=node_id),
            routes=routes,
        ),
        maturity=NodeMaturity.CRYSTALLIZED,
    )


async def _run_pipeline(spec: PipelineSpec, bindings: dict[str, Router], initial_input: dict) -> Any:
    bus = MemoryBus()
    await bus.connect()
    runner = PipelineRunner(pipeline=spec, bindings=bindings, bus=bus, max_steps=50)
    result = await runner.run(initial_input)
    await bus.close()
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 1. 线性管线向后兼容
# ═══════════════════════════════════════════════════════════════════════════════

class TestLinearPipeline:
    """验证线性管线（A → B → C → EMIT）在 DAG 执行器下行为不变。"""

    @pytest.mark.asyncio
    async def test_linear_three_nodes(self):
        """A → B → C → EMIT"""
        spec = PipelineSpec(
            id="linear-test",
            name="Linear Test",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_transformer_node("B"),
                _make_anchor_node("C", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="B", target="C"),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": AppendRouter("B"),
            "C": AppendRouter("C"),
        }
        result = await _run_pipeline(spec, bindings, {"start": True})
        assert result["_visited"] == ["A", "B", "C"]
        assert result["start"] is True

    @pytest.mark.asyncio
    async def test_conditional_branch(self):
        """A →[PASS] B, A →[FAIL] C — 只走 PASS 路径。"""
        spec = PipelineSpec(
            id="cond-test",
            name="Conditional Test",
            description="",
            nodes=[
                _make_anchor_node("A"),
                _make_anchor_node("B", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
                _make_anchor_node("C", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B", condition=VerdictKind.PASS),
                PipelineEdge(source="A", target="C", condition=VerdictKind.FAIL),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": AppendRouter("B"),
            "C": AppendRouter("C"),
        }
        result = await _run_pipeline(spec, bindings, {})
        # A 返回 PASS，所以走 B 不走 C
        assert result["_visited"] == ["A", "B"]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Fan-out
# ═══════════════════════════════════════════════════════════════════════════════

class TestFanOut:
    """验证一个节点输出触发多个下游并发执行。"""

    @pytest.mark.asyncio
    async def test_fan_out_two_branches(self):
        """A → B, A → C — B 和 C 都应执行。"""
        spec = PipelineSpec(
            id="fanout-test",
            name="Fan-out Test",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_anchor_node("B", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
                _make_anchor_node("C", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="A", target="C"),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": AppendRouter("B"),
            "C": AppendRouter("C"),
        }
        bus = MemoryBus()
        await bus.connect()
        runner = PipelineRunner(pipeline=spec, bindings=bindings, bus=bus, max_steps=50)
        result = await runner.run({})
        await bus.close()

        # 两个分支都 EMIT，第一个 EMIT 的结果被采纳
        # 无论哪个先完成，A 都被访问过
        assert "A" in (result.get("_visited", []))

    @pytest.mark.asyncio
    async def test_fan_out_concurrent_execution(self):
        """验证 fan-out 分支确实并发执行（总耗时 ≈ max(branch) 而非 sum）。"""
        spec = PipelineSpec(
            id="fanout-concurrent",
            name="Fan-out Concurrent",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_transformer_node("B"),
                _make_transformer_node("C"),
                _make_anchor_node("D", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="A", target="C"),
                PipelineEdge(source="B", target="D"),
                PipelineEdge(source="C", target="D"),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": SlowRouter("B", delay=0.15),
            "C": SlowRouter("C", delay=0.15),
            "D": AppendRouter("D"),
        }
        bus = MemoryBus()
        await bus.connect()
        runner = PipelineRunner(pipeline=spec, bindings=bindings, bus=bus, max_steps=50)

        t0 = asyncio.get_event_loop().time()
        result = await runner.run({})
        elapsed = asyncio.get_event_loop().time() - t0
        await bus.close()

        # 如果并发：elapsed ≈ 0.15s；如果顺序：elapsed ≈ 0.30s
        assert elapsed < 0.25, f"Expected concurrent execution, but took {elapsed:.2f}s"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Fan-in / Join barrier
# ═══════════════════════════════════════════════════════════════════════════════

class TestFanInJoin:
    """验证 join barrier: 多上游全部完成后合并输入。"""

    @pytest.mark.asyncio
    async def test_diamond_dag(self):
        """A → B, A → C, B → D, C → D — D 应收到 B+C 的合并结果。"""
        spec = PipelineSpec(
            id="diamond-test",
            name="Diamond DAG",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_transformer_node("B"),
                _make_transformer_node("C"),
                _make_anchor_node("D", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="A", target="C"),
                PipelineEdge(source="B", target="D"),
                PipelineEdge(source="C", target="D"),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": AppendRouter("B"),
            "C": AppendRouter("C"),
            "D": AppendRouter("D"),
        }
        result = await _run_pipeline(spec, bindings, {"origin": "test"})

        # D 的输入应包含 B 和 C 的结果
        assert "_result_B" in result
        assert "_result_C" in result
        assert "_result_D" in result
        # D 自己也被访问
        assert "D" in result["_visited"]
        # 命名空间存在
        assert "_from_B" in result
        assert "_from_C" in result

    @pytest.mark.asyncio
    async def test_join_waits_all_upstreams(self):
        """验证 join 节点确实等待所有上游（慢分支不被跳过）。"""
        spec = PipelineSpec(
            id="join-wait",
            name="Join Wait All",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_transformer_node("fast"),
                _make_transformer_node("slow"),
                _make_anchor_node("join", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="fast"),
                PipelineEdge(source="A", target="slow"),
                PipelineEdge(source="fast", target="join"),
                PipelineEdge(source="slow", target="join"),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "fast": SlowRouter("fast", delay=0.05),
            "slow": SlowRouter("slow", delay=0.2),
            "join": AppendRouter("join"),
        }
        result = await _run_pipeline(spec, bindings, {})

        # join 节点收到了两路的 _visited
        assert "_from_fast" in result
        assert "_from_slow" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 4. 反馈循环兼容
# ═══════════════════════════════════════════════════════════════════════════════

class TestFeedbackLoop:
    """验证带 feedback 边的循环管线正常工作。"""

    @pytest.mark.asyncio
    async def test_explicit_feedback_edge(self):
        """A → B → A (feedback) → B → EMIT — 循环一次后退出。"""
        spec = PipelineSpec(
            id="feedback-test",
            name="Feedback Loop",
            description="",
            nodes=[
                _make_anchor_node("A", routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="B"),
                    VerdictKind.FAIL: Route(action=RouteAction.NEXT, target="B"),
                }),
                _make_anchor_node("B", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="B", target="A", feedback=True),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": AppendRouter("B"),
        }
        result = await _run_pipeline(spec, bindings, {})
        # B 的 EMIT 直接返回
        assert "B" in result["_visited"]

    @pytest.mark.asyncio
    async def test_auto_back_edge_detection(self):
        """未标记 feedback 的循环：自动检测 back-edge。"""
        spec = PipelineSpec(
            id="auto-back-edge",
            name="Auto Back Edge",
            description="",
            nodes=[
                _make_anchor_node("A", routes={
                    VerdictKind.PASS: Route(action=RouteAction.NEXT, target="B"),
                }),
                _make_anchor_node("B", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="B", target="A"),  # 未标记 feedback
            ],
            entry="A",
        )
        bus = MemoryBus()
        await bus.connect()
        runner = PipelineRunner(pipeline=spec, bindings={
            "A": AppendRouter("A"),
            "B": AppendRouter("B"),
        }, bus=bus, max_steps=50)

        # 自动检测到 B→A 是 back-edge
        assert ("B", "A") in runner._feedback_pairs
        # A 的 in-degree 不因 feedback 边增加
        assert runner._in_degree["A"] == 0  # entry 节点，只有 feedback 入边

        result = await runner.run({})
        await bus.close()
        assert "B" in result["_visited"]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. 预算跨分支共享
# ═══════════════════════════════════════════════════════════════════════════════

class TestBudgetSharing:
    """验证并发分支共享 decision_count。"""

    @pytest.mark.asyncio
    async def test_budget_shared_across_branches(self):
        """fan-out 到两个 decision 节点，预算 +2。"""
        spec = PipelineSpec(
            id="budget-test",
            name="Budget Sharing",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_anchor_node("B", kind="soft", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
                _make_anchor_node("C", kind="soft", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="A", target="C"),
            ],
            entry="A",
        )
        bindings = {
            "A": AppendRouter("A"),
            "B": CountingDecisionRouter("B"),
            "C": CountingDecisionRouter("C"),
        }
        bus = MemoryBus()
        await bus.connect()
        runner = PipelineRunner(pipeline=spec, bindings=bindings, bus=bus, max_steps=50)
        await runner.run({})
        await bus.close()

        # B 和 C 都是 soft anchor (decision nodes)，各消耗 1 次预算
        assert runner.decision_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 6. 输入合并策略
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeInputs:
    """单元测试 _merge_inputs 方法。"""

    def test_single_upstream_passthrough(self):
        bus = MemoryBus()
        spec = PipelineSpec(
            id="t", name="t", description="", nodes=[], edges=[], entry="x",
        )
        runner = PipelineRunner(pipeline=spec, bindings={}, bus=bus, max_steps=1)

        result = runner._merge_inputs("target", {
            "src": Verdict(kind=VerdictKind.PASS, output={"foo": 1}),
        })
        assert result == {"foo": 1}

    def test_multi_upstream_merge(self):
        bus = MemoryBus()
        spec = PipelineSpec(
            id="t", name="t", description="", nodes=[], edges=[], entry="x",
        )
        runner = PipelineRunner(pipeline=spec, bindings={}, bus=bus, max_steps=1)

        result = runner._merge_inputs("target", {
            "B": Verdict(kind=VerdictKind.PASS, output={"from_b": 1, "shared": "b"}),
            "C": Verdict(kind=VerdictKind.PASS, output={"from_c": 2, "shared": "c"}),
        })
        # 扁平 merge (last-write-wins)
        assert result["from_b"] == 1
        assert result["from_c"] == 2
        # 命名空间
        assert result["_from_B"]["from_b"] == 1
        assert result["_from_C"]["from_c"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 7. 三路汇入（模拟翻译管线场景）
# ═══════════════════════════════════════════════════════════════════════════════

class TestThreeWayJoin:
    """模拟 demand + supply + source 三路汇入 translator。"""

    @pytest.mark.asyncio
    async def test_three_way_fan_in(self):
        """
        source_analyzer → demand_extractor ──→ ┐
               │                                │
               ├──→ supply_scanner ─────────→  ├──→ translator (EMIT)
               │                                │
               └──→ source_passthrough ─────→  ┘
        """
        spec = PipelineSpec(
            id="three-way",
            name="Three Way Join",
            description="",
            nodes=[
                _make_transformer_node("analyzer"),
                _make_transformer_node("demand"),
                _make_transformer_node("supply"),
                _make_transformer_node("passthrough"),
                _make_anchor_node("translator", routes={
                    VerdictKind.PASS: Route(action=RouteAction.EMIT),
                }),
            ],
            edges=[
                PipelineEdge(source="analyzer", target="demand"),
                PipelineEdge(source="analyzer", target="supply"),
                PipelineEdge(source="analyzer", target="passthrough"),
                PipelineEdge(source="demand", target="translator"),
                PipelineEdge(source="supply", target="translator"),
                PipelineEdge(source="passthrough", target="translator"),
            ],
            entry="analyzer",
        )
        bindings = {
            "analyzer": AppendRouter("analyzer"),
            "demand": AppendRouter("demand"),
            "supply": AppendRouter("supply"),
            "passthrough": AppendRouter("passthrough"),
            "translator": AppendRouter("translator"),
        }
        result = await _run_pipeline(spec, bindings, {"source_code": "def foo(): pass"})

        # translator 应收到三路结果
        assert "_from_demand" in result
        assert "_from_supply" in result
        assert "_from_passthrough" in result
        assert "_result_translator" in result
        # 原始数据透传
        assert result.get("source_code") == "def foo(): pass"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. 向后兼容：现有管线声明验证
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackwardCompat:
    """验证现有管线定义可被正确初始化。"""

    def test_agent_loop_pipeline(self):
        """agent-loop (3 节点循环) — 自动检测 back-edge。"""
        from omnicompany.protocol.pipeline import describe_agent_loop
        spec = describe_agent_loop()
        bus = MemoryBus()
        runner = PipelineRunner(
            pipeline=spec,
            bindings={n.id: PassthroughRouter() for n in spec.nodes},
            bus=bus,
            max_steps=10,
        )
        # obs_to_state → anchor_llm 应被检测为 back-edge
        assert ("obs_to_state", "anchor_llm") in runner._feedback_pairs

    def test_lang_rewrite_pipeline(self):
        """lang-rewrite (9 节点) — 多个 cycle。"""
        from omnicompany.primitives_impl.lang_rewrite.pipeline import build_pipeline
        spec = build_pipeline()
        bus = MemoryBus()
        runner = PipelineRunner(
            pipeline=spec,
            bindings={n.id: PassthroughRouter() for n in spec.nodes},
            bus=bus,
            max_steps=10,
        )
        # 应检测到回路边
        assert len(runner._feedback_pairs) > 0
        # 没有 join 节点的 in-degree 应合理
        for node_id, deg in runner._in_degree.items():
            assert deg >= 0

    def test_topology_checker(self):
        """PipelineChecker 拓扑校验。"""
        from omnicompany.protocol.format import FormatRegistry, Format
        registry = FormatRegistry()
        registry.register(Format(id="test", name="test", description="test"))

        from omnicompany.protocol.pipeline import PipelineChecker
        checker = PipelineChecker(registry)

        # 构建有未标记 feedback 的循环
        spec = PipelineSpec(
            id="topo-test",
            name="Topo Test",
            description="",
            nodes=[
                _make_transformer_node("A"),
                _make_transformer_node("B"),
            ],
            edges=[
                PipelineEdge(source="A", target="B"),
                PipelineEdge(source="B", target="A"),  # 未标记 feedback
            ],
            entry="A",
        )
        result = checker.check(spec)
        # 应该有 warning 建议标记 feedback
        assert any("feedback" in w for w in result.warnings)
