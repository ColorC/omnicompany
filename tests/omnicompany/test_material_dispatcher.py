"""MaterialDispatcher E2E 测试 — 合成 Worker 链通过 EventBus 激活.

验证用户 2026-04-20 洞察:
  "stock 就是 eventbus, 转 bus 驱动如果有问题, 通常意味着之前就不严谨"

2026-06-13 重写: 旧版用 guardian 4 Worker 真链, 但 LLMJudgeWorker 已于 2026-05-05
诊断重制时移除 (shim 直接桥接), 旧链不复存在导致测试漂移失效。改用合成 Worker 链,
专测调度器机制本身 (链式激活 / AND fan-in / 单次激活 / sink 收集),
不再与任何业务团队的演进耦合。MaterialDispatcher 已转正为材料黑板执行器
(见 docs/plans/format-material/[2026-06-13]MATERIAL-UNIFICATION/plan.md §一)。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from omnicompany.packages.services._core.omnicompany import MaterialDispatcher, Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


class _SplitWorker(Worker):
    DESCRIPTION = "合成测试 Worker: 把源文本拆成单词列表"
    FORMAT_IN = "synth.text"
    FORMAT_OUT = "synth.words"

    def run(self, input_data: dict) -> Verdict:
        text = input_data.get("synth.text", {}).get("text", "")
        return Verdict(kind=VerdictKind.PASS, output={"words": text.split()})


class _CountWorker(Worker):
    DESCRIPTION = "合成测试 Worker: 统计源文本的字符数"
    FORMAT_IN = "synth.text"
    FORMAT_OUT = "synth.chars"

    def run(self, input_data: dict) -> Verdict:
        text = input_data.get("synth.text", {}).get("text", "")
        return Verdict(kind=VerdictKind.PASS, output={"chars": len(text)})


class _MergeWorker(Worker):
    DESCRIPTION = "合成测试 Worker: AND fan-in 汇聚单词与字符统计"
    FORMAT_IN = ["synth.words", "synth.chars"]
    FORMAT_IN_MODE = "and"
    FORMAT_OUT = "synth.report"

    def run(self, input_data: dict) -> Verdict:
        words = input_data.get("synth.words", {}).get("words", [])
        chars = input_data.get("synth.chars", {}).get("chars", 0)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"word_count": len(words), "char_count": chars},
        )


def _build_dispatcher() -> MaterialDispatcher:
    return MaterialDispatcher([_SplitWorker(), _CountWorker(), _MergeWorker()])


class TestDispatcherE2E:
    @pytest.mark.asyncio
    async def test_chain_and_fanin_end_to_end(self):
        """source → 两路并行 → AND fan-in sink, 全链路应产 4 个事件."""
        dispatcher = _build_dispatcher()
        events = await dispatcher.run_job(
            initial_material_id="synth.text",
            initial_payload={"text": "hello material world"},
        )

        event_types = [e.event_type for e in events]
        assert "synth.text" in event_types, f"缺 source material: {event_types}"
        assert "synth.words" in event_types
        assert "synth.chars" in event_types
        assert "synth.report" in event_types, "AND fan-in 未激活"

        report = next(e for e in events if e.event_type == "synth.report")
        assert report.payload["word_count"] == 3
        assert report.payload["char_count"] == len("hello material world")

    @pytest.mark.asyncio
    async def test_single_activation_per_job(self):
        """同一 job 内每个 Worker 只激活一次 (Q1), 事件数固定为 4."""
        dispatcher = _build_dispatcher()
        events = await dispatcher.run_job(
            initial_material_id="synth.text",
            initial_payload={"text": "a b"},
        )
        assert len(events) == 4, [e.event_type for e in events]

    @pytest.mark.asyncio
    async def test_trace_id_consistent(self):
        """无子 job 时全链路共享同一 trace_id."""
        dispatcher = _build_dispatcher()
        events = await dispatcher.run_job(
            initial_material_id="synth.text",
            initial_payload={"text": "x"},
        )
        assert len({e.trace_id for e in events}) == 1
