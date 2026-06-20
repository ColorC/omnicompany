# [OMNI] origin=claude-code domain=tests/packages/services ts=2026-04-25T05:10:00Z type=test status=active
"""color_spectrum 核心组件 + 元色谱 单测.

立题: B 块 · 测试质量本身可被测试. 本文件验证:
1. ColorSpectrumChecker 基本能力 (跑色谱, 报 monotone)
2. setup/teardown 钩子
3. 异常容错 (probe 抛异常, setup 错)
4. **元色谱 PASS**: ColorSpectrumChecker 自己是有判别力的 (核心断言)
"""
from __future__ import annotations

import pytest

from omnicompany.packages.services.color_spectrum import (
    ColorStage,
    SpectrumReport,
    run_color_spectrum,
    run_meta_spectrum,
)


# ══════════════════════════════════════════════════════════════════
# 基础: run_color_spectrum
# ══════════════════════════════════════════════════════════════════


def test_empty_stages():
    report = run_color_spectrum([], probe_runner=lambda s: "pass")
    assert report.total == 0
    assert report.monotone_count == 0
    assert report.fully_monotone is False  # 空也不算 fully (语义)
    assert report.monotone_score == 0.0


def test_all_pass():
    stages = [
        ColorStage("a", "x", expected_verdict="ok"),
        ColorStage("b", "y", expected_verdict="ok"),
    ]
    report = run_color_spectrum(stages, probe_runner=lambda s: "ok")
    assert report.total == 2
    assert report.monotone_count == 2
    assert report.fully_monotone is True
    assert report.monotone_score == 1.0
    assert len(report.misordered) == 0


def test_partial_pass():
    stages = [
        ColorStage("a", "x", expected_verdict="ok"),
        ColorStage("b", "y", expected_verdict="fail"),
        ColorStage("c", "z", expected_verdict="ok"),
    ]
    report = run_color_spectrum(stages, probe_runner=lambda s: "ok")  # 永远 ok
    assert report.monotone_count == 2
    assert report.total == 3
    assert report.monotone_score == pytest.approx(2 / 3)
    assert len(report.misordered) == 1
    assert report.misordered[0].stage == "b"
    assert report.misordered[0].actual == "ok"
    assert report.misordered[0].expected == "fail"


def test_probe_exception_caught():
    stages = [ColorStage("a", "x", expected_verdict="ok")]

    def boom(stage):
        raise ValueError("boom")

    report = run_color_spectrum(stages, probe_runner=boom)
    assert report.total == 1
    assert report.monotone_count == 0
    assert "probe_exception" in report.stages[0].actual
    assert "boom" in report.stages[0].actual


def test_setup_teardown_called():
    calls = []
    stages = [
        ColorStage(
            "a", "x", expected_verdict="ok",
            setup=lambda s: calls.append(f"setup_{s.name}"),
            teardown=lambda s: calls.append(f"teardown_{s.name}"),
        ),
    ]
    run_color_spectrum(stages, probe_runner=lambda s: "ok")
    assert calls == ["setup_a", "teardown_a"]


def test_setup_error_records_failure():
    def bad_setup(s):
        raise RuntimeError("setup boom")
    stages = [ColorStage("a", "x", expected_verdict="ok", setup=bad_setup)]
    report = run_color_spectrum(stages, probe_runner=lambda s: "ok")
    assert report.monotone_count == 0
    assert "setup_error" in report.stages[0].actual


def test_stop_on_fail():
    stages = [
        ColorStage("a", "x", expected_verdict="ok"),
        ColorStage("b", "y", expected_verdict="ok"),
        ColorStage("c", "z", expected_verdict="ok"),
    ]
    # probe 第二档返 fail, stop_on_fail 应该截断
    counter = {"i": 0}
    def probe(s):
        counter["i"] += 1
        return "ok" if s.name != "b" else "fail"
    report = run_color_spectrum(stages, probe_runner=probe, stop_on_fail=True)
    assert counter["i"] == 2  # 只跑了 a 和 b, c 没跑
    assert report.total == 2


# ══════════════════════════════════════════════════════════════════
# 元色谱 (核心断言)
# ══════════════════════════════════════════════════════════════════


def test_meta_spectrum_default_probes_pass():
    """默认 3 种 probe (good/always_pass/always_fail), 元色谱应判 meta_passed=True.

    这是**关键测试**: 它证明 ColorSpectrumChecker 自己有判别力 —
    能分清"正确判别 probe" vs "色谱崩塌的 probe".
    """
    result = run_meta_spectrum()
    assert result["meta_passed"] is True, f"元色谱崩塌: {result}"

    details = result["details"]
    # good 应全过
    assert details["good"]["fully_monotone"] is True
    assert details["good"]["misordered_count"] == 0
    # always_pass 应有 1 misordered (red 期望 fail 实际 pass)
    assert details["always_pass"]["fully_monotone"] is False
    assert details["always_pass"]["misordered_count"] == 1
    # always_fail 同理 (green 期望 pass 实际 fail)
    assert details["always_fail"]["fully_monotone"] is False
    assert details["always_fail"]["misordered_count"] == 1


def test_meta_spectrum_custom_probes():
    """自定义 probe quality 也可工作."""
    custom = {
        "all_random": lambda s: "random_xyz",
        "good_too": lambda s: "fail" if s.expected_verdict == "fail" else "pass",
    }
    result = run_meta_spectrum(probe_factories=custom)
    # all_random: 总不匹配 expected
    assert result["details"]["all_random"]["fully_monotone"] is False
    # good_too: 应全过
    assert result["details"]["good_too"]["fully_monotone"] is True
    # meta_passed 默认期望键有 good/always_pass/always_fail, 自定义里没, 不测 meta_passed
