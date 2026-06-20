# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T08:10:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest 单元测 PromptPatchPileScanner — 红绿对比验真有判别力 + 真 dogfood 跑 6 doctor agent prompt"
# [OMNI] why="AP-024 V1 留议. detection_strategy 客观可测部分立 scanner 后必走红绿对比 (用户铁律: 接通必带判别力)"
# [OMNI] tags=test,pytest,scanner,prompt-patch-pile,red-green,dogfood,AP-024
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_prompt_patch_pile_scanner.py"
"""pytest 单元测 PromptPatchPileScanner.

测 case:
- 边界: 空 list / 不存在文件 / 非文件
- 信号 3 类: enumeration / specific_reference / patch_marker 各分别命中
- 红绿对比: 红 prompt 信号数 >> 绿 prompt (真有判别力)
- 真 dogfood: 跑 6 个 doctor agent prompt 看分布合理 (不裁决, 只确保不报错)
- summary 字符串包含统计
"""
from __future__ import annotations

from pathlib import Path

import pytest

from omnicompany.packages.services._diagnosis.doctor.scanners.prompt_patch_pile_scanner import (
    PromptPatchPileScanner,
    scan_prompt_patch_pile,
)


# 红 prompt: 故意含大量 patch-pile 信号 (枚举 / specific 引用 / 补丁标)
_RED_PROMPT_CONTENT = """\
# 假诊断 agent 系统 prompt (故意 patch-pile)

## 反例 1: 不要在 prompt 里堆 todo

TODO: 这是个补丁标, 应该清掉.
FIXME: 这是另一个补丁标.
HACK: 这是个 hack, 应该重写.
XXX: 还要再调.
TODO: 还有一个 todo.

## 反例 2: 不要笨拙枚举

例 1: 不应该这样写
例 2: 也不应该这样
例 3: 这个错
例 4: 这个也错
反例 1: 错了
反例 2: 错了
反例 3: 错了

❌ 反例: 不应该这样
❌ 反例: 也不应该
❌ 反例: 也不
✗ 错误示例
✗ 又一个错误

## 反例 3: 不要塞具体引用

调用 src/omnicompany/packages/services/agent.py 的 ConfigurableAgent.run() 方法,
使用 SubmitVerdictRouter 跟 WriteFindingTool. 配 SpecDiagnosticAgent 跑.

跑 docs/standards/concepts/worker.md 跟 docs/standards/_global/llm_first.md.

调 PytestSkeletonBuilder + HypothesisAgentPromptBuilder + HypothesisV1Upgrader.

## 补丁标 (要修)

补丁: 这是补丁段
修补: 这是修补段
"""

# 绿 prompt: 干净的, 几乎 0 信号
_GREEN_PROMPT_CONTENT = """\
# 干净诊断 agent 系统 prompt

## 你的角色

你是诊断 agent. 拿待诊断对象跟规范对照, 输出 finding.

## 你做什么

- 拿对象跟规范对照
- 自然语言判: 满足 / 违反 / 无法判断
- 给具体证据
- 通过提交工具出口

## 你不做什么

- 不修复, 只诊断
- 不打分, 用自然语言

## finding 三字段

- evidence: 引代码/文档具体位置 (一句话)
- commentary: 引规范说明 (一两段)
- concern: 来龙去脉 — 为什么是问题, 不修会怎样

## 提交

通过提交工具出口提交 finding 跟 verdict.
"""


@pytest.fixture
def scanner():
    return PromptPatchPileScanner()


@pytest.fixture
def red_prompt(tmp_path):
    p = tmp_path / "red_prompt.md"
    p.write_text(_RED_PROMPT_CONTENT, encoding="utf-8")
    return p


@pytest.fixture
def green_prompt(tmp_path):
    p = tmp_path / "green_prompt.md"
    p.write_text(_GREEN_PROMPT_CONTENT, encoding="utf-8")
    return p


# ── 边界 ──

def test_scan_empty_list(scanner):
    result = scanner.scan_files([])
    assert result.scanned_count == 0
    assert result.signals == []


def test_scan_nonexistent_file(scanner, tmp_path):
    result = scanner.scan_files([tmp_path / "no_such.md"])
    assert result.scanned_count == 0
    assert len(result.skipped) == 1
    assert "文件不存在" in result.skipped[0][1]


def test_scan_directory_not_file(scanner, tmp_path):
    """传 dir 路径返跳过."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    result = scanner.scan_files([sub])
    assert result.scanned_count == 0
    assert len(result.skipped) == 1
    assert "非文件" in result.skipped[0][1]


# ── 信号 3 类各命中 ──

def test_enumeration_signal_hits(scanner, red_prompt):
    result = scanner.scan_files([red_prompt])
    sig = result.signals[0]
    # red 含 例1-4 + 反例1-3 + ❌反例×3 + ✗×2 = >= 12
    assert sig.enumeration_count >= 10
    assert len(sig.enumeration_hits) <= scanner.HIT_SAMPLE_CAP
    # 命中 sample 应含 line_number
    for hit in sig.enumeration_hits:
        assert hit.line_number > 0
        assert hit.line_text  # 非空


def test_specific_reference_signal_hits(scanner, red_prompt):
    result = scanner.scan_files([red_prompt])
    sig = result.signals[0]
    # red 含 .py 路径 + .md 路径 + 多个 PascalCase + 后缀
    assert sig.specific_reference_count >= 5


def test_patch_marker_signal_hits(scanner, red_prompt):
    result = scanner.scan_files([red_prompt])
    sig = result.signals[0]
    # red 含 TODO×2 + FIXME + HACK + XXX + 补丁 + 修补 = >= 7
    assert sig.patch_marker_count >= 5


def test_xxx_does_not_match_ap_placeholder(scanner, tmp_path):
    """XXX 关键词应当避开 AP-XXX / -XXX 等反模式占位符 (2026-05-07 真 dogfood 发现的假阳性).

    在 doctor agent prompt 里 "AP-XXX" 是反模式 archetype 占位符, 不是 patch marker.
    旧 \\bXXX\\b 会误命中 — 改 (?<![\\w-])XXX(?![\\w-]) 后应当不命中.
    """
    p = tmp_path / "ap_placeholder.md"
    p.write_text(
        "# 元诊断 prompt\n"
        "命中即引 AP-XXX 在 finding.applied_standards.\n"
        "拿反模式 archetypes (AP-001 / AP-XXX / AP-024) 跟 team 对照.\n"
        "看是否含 -XXX- 之类占位符.\n",
        encoding="utf-8"
    )
    result = scanner.scan_files([p])
    sig = result.signals[0]
    # 这 4 行内 AP-XXX 出现 ≥3 次, 旧逻辑会全部命中 patch_marker.
    # 修 后应当 patch_marker_count == 0
    assert sig.patch_marker_count == 0


def test_xxx_still_matches_standalone(scanner, tmp_path):
    """独立的 XXX 仍应命中 (例 'XXX 待补' / '-> XXX 这里要修')."""
    p = tmp_path / "standalone_xxx.md"
    p.write_text(
        "看这里 XXX 待补\n"
        "另一行 XXX 是补丁标\n",
        encoding="utf-8"
    )
    result = scanner.scan_files([p])
    sig = result.signals[0]
    # 独立 XXX (前后空格) 应命中. + 第 2 行 "补丁" 单独命中.
    assert sig.patch_marker_count >= 2


def test_green_prompt_minimal_signals(scanner, green_prompt):
    result = scanner.scan_files([green_prompt])
    sig = result.signals[0]
    # green 不含 例 N: / 反例 / ❌ / TODO / FIXME / 具体路径
    assert sig.enumeration_count == 0
    assert sig.patch_marker_count == 0
    # specific_reference 应当很少 (绿 prompt 不引具体符号)
    assert sig.specific_reference_count <= 2  # 留一点容错 (例如"诊断 agent" 可能命中)


# ── 红绿对比真有判别力 (用户铁律 connected_is_not_discriminating) ──

def test_red_green_discrimination(scanner, red_prompt, green_prompt):
    """红 prompt 信号数 >> 绿 prompt — 红绿对比真有判别力."""
    result = scanner.scan_files([red_prompt, green_prompt])
    assert len(result.signals) == 2
    red_sig, green_sig = result.signals[0], result.signals[1]
    assert red_sig.total_signals >= 20
    assert green_sig.total_signals < 5
    # 比例至少 5x (敏感度阈值, 真有判别力)
    assert red_sig.total_signals >= 5 * max(green_sig.total_signals, 1)


# ── 真 dogfood 跑 6 doctor agent prompt ──

_DOCTOR_AGENTS_DIR = Path(__file__).resolve().parents[4] / "src" / "omnicompany" / "packages" / "services" / "_diagnosis" / "doctor" / "agents"


def test_dogfood_doctor_agents(scanner):
    """真 dogfood — 跑现 6 个 doctor agent prompt 看分布合理.

    不裁决好坏 (调用方决定阈值), 只确保 scanner 跑得通 + 6 份都扫到 + 信号在合理范围.
    若某 prompt 信号 > 50 应该看一眼是不是真 patch pile 还是合理 (例 meta_diagnostic 含
    few-shot 例 + 大量字段引用是合理的 — 元诊断 prompt 本身就需要解释 7 假设跟 10 问).
    """
    if not _DOCTOR_AGENTS_DIR.exists():
        pytest.skip(f"doctor agents dir 不存在: {_DOCTOR_AGENTS_DIR}")
    prompts = sorted(_DOCTOR_AGENTS_DIR.glob("*_prompt.md"))
    if not prompts:
        pytest.skip("doctor agents/ 无 prompt md")
    result = scanner.scan_files(prompts)
    assert result.scanned_count == len(prompts)
    # 每份都应该扫到 (不被跳过)
    assert result.skipped == []
    # 6 份 prompt 都该有 signals 记录
    assert len(result.signals) == len(prompts)
    # 不出 None — line_count > 0
    for sig in result.signals:
        assert sig.line_count > 0


# ── summary 字符串 ──

def test_summary_with_signals(scanner, red_prompt, green_prompt):
    result = scanner.scan_files([red_prompt, green_prompt])
    s = result.summary
    assert "scanned 2" in s
    assert "avg" in s


def test_summary_no_files(scanner):
    s = scanner.scan_files([]).summary
    assert "no signals" in s


# ── 便捷入口 ──

def test_helper_function(red_prompt):
    result = scan_prompt_patch_pile([red_prompt])
    assert result.scanned_count == 1
    assert result.signals[0].total_signals > 0
