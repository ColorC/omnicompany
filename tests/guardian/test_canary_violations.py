"""系统健康 canary: 已知违规样本必须持续被检测 (2026-04-28 立).

哲学:
  不测 `path.endswith('.py') == True` 这种 Python 内置 — 复述代码无意义, 写错跑一次就挂.
  而是断言"系统作为整体"对一组已知违规样本仍能命中.

任一 canary FAIL 意味着系统级回归之一:
  - 规则被错误注册掉 (import 漏 / RULES 列表漏)
  - RuleEngine 评估逻辑改坏
  - 豁免名单错误吞了真违规
  - FileContext 字段被悄悄改但规则未跟上
  - 其他链路上"看似无关"的改动把 patrol 整个打哑

跑端到端: FileContext → RuleEngine.evaluate (含全 RULES) → 期望命中规则集.

不污染真 docs/: 全部用 tmp_path / 虚构 abs_path 构造.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian import FileContext, RuleEngine


def _ctx(path: str, abs_path: str | None = None, content: str | None = None) -> FileContext:
    return FileContext(
        path=path,
        abs_path=abs_path or f"e:/fake/{path}",
        change_type="A",
        content=content,
        omnimark=None,
    )


def _rule_ids(violations) -> set[str]:
    return {v.rule_id for v in violations}


# ─── OMNI-035 系列 canary ─────────────────────────────────────────


class TestCanaryDistributedDocs:
    """每条 035 规则一个 canary. FAIL 意味着该规则失效 (注册掉/逻辑坏/被错豁免)."""

    def test_canary_035a_docs_root_stray(self):
        """canary OMNI-035a: docs/ 根级出现非白名单文件必须命中.

        FAIL 意味着: docs/ 根闭集失效, 任何人可在 docs/ 根创建散文 .md 不被告警.
        """
        v = RuleEngine().evaluate([_ctx("docs/random_doc.md", content="x")])
        assert "OMNI-035a" in _rule_ids(v), f"OMNI-035a 失效, 命中规则={_rule_ids(v)}"

    def test_canary_035b_plans_loose_md(self):
        """canary OMNI-035b: docs/plans/ 根下散文 .md 必须命中.

        FAIL 意味着: 计划必须目录化的规范失效.
        """
        v = RuleEngine().evaluate([_ctx("docs/plans/STRAY_PLAN.md", content="x")])
        assert "OMNI-035b" in _rule_ids(v)

    def test_canary_035c_nonstandard_plan_name(self):
        """canary OMNI-035c: plans/<不带日期前缀的名字>/ 必须命中.

        FAIL 意味着: 计划目录必须 [YYYY-MM-DD]TOPIC 命名的规范失效.
        """
        v = RuleEngine().evaluate([_ctx("docs/plans/random_name/foo.md", content="x")])
        assert "OMNI-035c" in _rule_ids(v)

    def test_canary_035d_undated_report(self):
        """canary OMNI-035d: reports/ 直接 .md 缺日期前缀必须命中.

        FAIL 意味着: 报告日期前缀规范失效.
        """
        v = RuleEngine().evaluate([_ctx("docs/reports/NO_DATE_REPORT.md", content="x")])
        assert "OMNI-035d" in _rule_ids(v)

    def test_canary_035e_stray_progress(self):
        """canary OMNI-035e: 非 docs/PROGRESS.md 的 PROGRESS.md 必须命中.

        FAIL 意味着: PROGRESS 唯一性铁律失效, 任何包/目录可立 PROGRESS.md 不告警.
        """
        v = RuleEngine().evaluate([_ctx(
            "src/omnicompany/packages/some_pkg/PROGRESS.md",
            content="# stray progress\n",
        )])
        assert "OMNI-035e" in _rule_ids(v)

    def test_canary_035f_plans_topic_subitem(self):
        """canary OMNI-035f: 当前主题区计划目录根级非 .md 散件命中.

        FAIL 意味着: 计划目录根级散件闭集失效, yaml/json/脚本等可再次堆在 plan 根。
        """
        v = RuleEngine().evaluate([_ctx(
            "docs/plans/agent-framework/[2026-04-28]CANARY/raw_payload.yaml",
            content="x: 1\n",
        )])
        assert "OMNI-035f" in _rule_ids(v)

    def test_canary_035g_python_in_docs(self):
        """canary OMNI-035g: docs/ 子目录的 .py 必须命中.

        FAIL 意味着: docs/ 内 Python 代码守护失效.
        本会话的核心动机. 这条挂了 = 整个扩展白做.
        """
        v = RuleEngine().evaluate([_ctx(
            "docs/plans/[2026-04-28]CANARY/script.py",
            content="import os",
        )])
        assert "OMNI-035g" in _rule_ids(v)

    def test_canary_035h_data_artifact(self):
        """canary OMNI-035h: docs/ 子目录的 .json 数据产物必须命中.

        FAIL 意味着: 数据产物可再次进 docs/ 不告警.
        """
        v = RuleEngine().evaluate([_ctx(
            "docs/plans/[2026-04-28]CANARY/data.json",
            content='{"x": 1}',
        )])
        assert "OMNI-035h" in _rule_ids(v)

    def test_canary_035i_runtime_residue(self):
        """canary OMNI-035i: docs/ 内 .log / .prefab 等运行时残留必须命中.

        FAIL 意味着: 运行时残留守护失效.
        """
        v = RuleEngine().evaluate([_ctx(
            "docs/plans/[2026-04-28]CANARY/run.log",
            content="ERROR ...",
        )])
        assert "OMNI-035i" in _rule_ids(v)

    def test_canary_035j_large_file_needs_judgment(self, tmp_path):
        """canary OMNI-035j: docs/ 下 > 1 MB 文件必须进 needs_judgment 流.

        FAIL 意味着: 大文件 LLM 复核入口失效, 大数据/缓存可悄悄进 docs/.
        """
        f = tmp_path / "big.json"
        f.write_bytes(b"x" * (1 * 1024 * 1024 + 1))

        # 用 evaluate_split 看 needs_judgment 分流
        from omnicompany.packages.services._core.guardian import RuleEngine
        engine = RuleEngine()
        result = engine.evaluate_split([_ctx(
            "docs/plans/[2026-04-28]CANARY/big.json",
            abs_path=str(f),
        )])
        nj_ids = {v.rule_id for v in result["needs_judgment"]}
        assert "OMNI-035j" in nj_ids, (
            f"OMNI-035j 应进 needs_judgment 流, 实际 confirmed={[v.rule_id for v in result['confirmed']]} "
            f"needs_judgment={nj_ids}"
        )


# ─── 反向 canary: 合规样本不应误报 ─────────────────────────────────


class TestCanaryFalseAlarmGuard:
    """合规样本必须不被误报. FAIL 意味着规则过宽, 把合法内容当违规."""

    def test_canary_compliant_plan_md_passes(self):
        """合规计划目录的 plan.md 不应触发 035 系列任何 HIGH 规则."""
        v = RuleEngine().evaluate([_ctx(
            "docs/plans/[2026-04-28]GUARDIAN-DOCS-CONFISCATION/plan.md",
            content="# plan",
        )])
        ids = _rule_ids(v)
        # 035 全系列都不应命中
        for rid in ("OMNI-035a", "OMNI-035b", "OMNI-035c", "OMNI-035d",
                    "OMNI-035e", "OMNI-035f", "OMNI-035g", "OMNI-035h", "OMNI-035i"):
            assert rid not in ids, f"误报: 合规 plan.md 不应触发 {rid}, 实际命中={ids}"

    def test_canary_spikes_subdir_anything_passes(self):
        """spikes/ 子目录内任意文件 (含 .py) 是规范允许的, 不应触发 035f/g/h/i."""
        v = RuleEngine().evaluate([_ctx(
            "docs/plans/[2026-04-28]GUARDIAN-DOCS-CONFISCATION/spikes/probe.py",
            content="# spike",
        )])
        ids = _rule_ids(v)
        assert "OMNI-035f" not in ids, f"spikes/ 内 .py 是合规 (调研笔记), 不应触发 035f. 实际={ids}"
        # 注: 035g (docs/.py) 当前实现仍会命中 spikes/ 内 .py.
        # 这是一个已知的"严宽边界"判断 — 留给本测试作记录, 若 L1 决定让 spikes/ 完全豁免则改本断言.

    def test_canary_docs_root_whitelist_passes(self):
        """docs/ 根白名单内的文件不应触发 035a."""
        for name in ("README.md", "PROGRESS.md", "ARCHITECTURE.md", "ARCH-CHANGES.jsonl"):
            v = RuleEngine().evaluate([_ctx(f"docs/{name}", content="x")])
            assert "OMNI-035a" not in _rule_ids(v), (
                f"docs/{name} 在闭集白名单, 不应触发 035a. 实际={_rule_ids(v)}"
            )


# ─── canary: 全 RULES 注册检查 ──────────────────────────────────


class TestCanaryRulesRegistration:
    """RULES 列表完整性 canary. FAIL 意味着规则被漏注册 (rules/__init__.py import 漏)."""

    def test_canary_all_035_rules_in_RULES(self):
        """OMNI-035a~j 全部 10 条必须在 RULES 列表里 (跨家族注册检查)."""
        from omnicompany.packages.services._core.guardian import RULES
        ids = {r.id for r in RULES}
        for suffix in "abcdefghij":
            rid = f"OMNI-035{suffix}"
            assert rid in ids, f"{rid} 未注册到 RULES (检查 rules/__init__.py + distributed_docs.py)"

    def test_canary_disposition_progression_intact(self):
        """OMNI-035 disposition 进阶必须保持: a~e 含 stamp, f~j 含 relocate.

        FAIL 意味着: 阶段三 disposition 升级被回滚或未生效.
        """
        from omnicompany.packages.services._core.guardian import RULES
        rules_by_id = {r.id: r for r in RULES}
        for suffix in "abcde":
            r = rules_by_id[f"OMNI-035{suffix}"]
            assert "stamp" in r.disposition, f"OMNI-035{suffix} 缺 stamp"
        for suffix in "fghij":
            r = rules_by_id[f"OMNI-035{suffix}"]
            assert "relocate" in r.disposition, f"OMNI-035{suffix} 缺 relocate"
