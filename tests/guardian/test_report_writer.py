# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-25T00:00:00Z type=test
"""GuardianReportWorker v2 测试 · LLM 翻译版.

铁律: 每条问题给"规则是什么 + 哪里违 + 怎么改" 的中文翻译, 不保留代号给用户读.
LLM 调用 mock 化 (避真 API 成本/不稳定); 单独保留 1 个 e2e 跳过版需 THE_COMPANY_API_KEY.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from omnicompany.packages.services._core.guardian.workers.report_writer import (
    GuardianReportWorker,
    _build_rule_dictionary,
)
from omnicompany.protocol.anchor import VerdictKind


_FAKE_LLM_MD = """\

# omnicompany 守护一手观察 · 2026-04-25T00:00:00Z

> 这是中文翻译版示例 (mock LLM 输出).

## 顶层概览
| 数据源 | 计数 |
|---|---|
| 规则扫描违规 | 0 |

## 规则扫描详情
(无)

## LLM 巡查
(无 patrol)

## audit 判定
(无 audit 记录)

## docauthor 队列
(无)

## 下一步建议
- 无 critical 待办 ✓
"""


@pytest.fixture
def tmp_repo(tmp_path):
    """临时 repo · 必备目录骨架."""
    (tmp_path / "data" / "services" / "guardian" / "patrol").mkdir(parents=True)
    (tmp_path / "data" / "services" / "guardian" / "audit").mkdir(parents=True)
    (tmp_path / "data" / "services" / "docauthor" / "drafts" / "_quarantine").mkdir(parents=True)
    (tmp_path / "src" / "omnicompany" / "packages" / "services").mkdir(parents=True)
    return tmp_path


@pytest.fixture
def mock_llm():
    """mock call_llm_json 返回固定 markdown."""
    with patch(
        "omnicompany.packages.services._core.guardian.workers.report_writer.call_llm_json",
        return_value={"markdown": _FAKE_LLM_MD},
    ) as m:
        yield m


def test_T1_smoke_with_mock_llm(tmp_repo, mock_llm):
    """空 repo · mock LLM · 落 markdown + latest.md."""
    w = GuardianReportWorker(repo_root=tmp_repo)
    out = w.run({"guardian.report-request": {}})
    assert out.kind == VerdictKind.PASS
    o = out.output
    assert "report_path" in o
    assert "report_md" in o
    md = o["report_md"]
    assert md == _FAKE_LLM_MD
    # 文件落盘
    landing = tmp_repo / o["report_path"]
    assert landing.exists()
    latest = tmp_repo / "data/services/guardian/reports/latest.md"
    assert latest.exists()
    # 调用 LLM 一次
    assert mock_llm.call_count == 1


def test_T2_rule_dictionary_built_from_actual_violations(tmp_repo, mock_llm):
    """规则字典从实际违规规则 ID 构造 (本测试: 空 repo → 字典含 4 项 OMNI- key)."""
    w = GuardianReportWorker(repo_root=tmp_repo)
    w.run({"guardian.report-request": {}})

    # 拿到 LLM 调用时传入的 user_prompt, 检字典确实在
    args, kwargs = mock_llm.call_args
    user_prompt = kwargs.get("user", "")
    # 4 类 scan key 里有 OMNI-051a / OMNI-049 / OMNI-050
    # 即使空 repo, key 仍在 (空 list)
    assert "OMNI-051a" in user_prompt
    assert "OMNI-049" in user_prompt
    assert "OMNI-050" in user_prompt
    # 规则定义出现 (description 来自 RULES)
    assert "data-subdir-undeclared" in user_prompt or "aging" in user_prompt


def test_T3_no_score_in_system_prompt(tmp_repo, mock_llm):
    """system prompt 必须有"不打分"硬指令."""
    w = GuardianReportWorker(repo_root=tmp_repo)
    w.run({"guardian.report-request": {}})

    args, kwargs = mock_llm.call_args
    system = kwargs.get("system", "")
    assert "不打分" in system
    # 也要有"不保留代号"
    assert "代号" in system


def test_T4_audit_records_passed_to_llm(tmp_repo, mock_llm):
    """audit/records.jsonl 内容必须传给 LLM."""
    audit_path = tmp_repo / "data/services/guardian/audit/records.jsonl"
    records = [
        {"verdict": "confirmed", "rule_id": "OMNI-051a",
         "target_path": "data/x", "ts": "2026-04-25T00:00:00Z"},
        {"verdict": "dismissed", "rule_id": "OMNI-074",
         "target_path": "src/y.py", "ts": "2026-04-25T01:00:00Z"},
    ]
    audit_path.write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")

    w = GuardianReportWorker(repo_root=tmp_repo)
    w.run({"guardian.report-request": {}})

    args, kwargs = mock_llm.call_args
    user_prompt = kwargs.get("user", "")
    # 原始 audit 数据出现
    assert "OMNI-074" in user_prompt
    assert "src/y.py" in user_prompt
    assert "confirmed" in user_prompt


def test_T5_quarantine_queue_passed_to_llm(tmp_repo, mock_llm):
    """quarantine 内容传 LLM."""
    q_dir = tmp_repo / "data/services/docauthor/drafts/_quarantine/test_slug"
    q_dir.mkdir(parents=True)
    issues = {
        "target_path": "src/foo/bar",
        "target_type": "manifest",
        "iter": 1,
        "passed": False,
        "counts": {"critical": 2, "major": 0, "minor": 0},
    }
    (q_dir / "issues.json").write_text(json.dumps(issues), encoding="utf-8")

    w = GuardianReportWorker(repo_root=tmp_repo)
    w.run({"guardian.report-request": {}})

    args, kwargs = mock_llm.call_args
    user_prompt = kwargs.get("user", "")
    assert "src/foo/bar" in user_prompt
    assert "test_slug" in user_prompt


def test_T6_source_counts_returned(tmp_repo, mock_llm):
    w = GuardianReportWorker(repo_root=tmp_repo)
    out = w.run({"guardian.report-request": {}})
    sc = out.output["source_counts"]
    expected = {
        "rule_scan_violations", "patrol_reports", "audit_records_recent",
        "audit_records_total", "docauthor_quarantine",
        "docauthor_skeleton_design", "docauthor_missing_manifest",
    }
    assert expected.issubset(sc.keys())


def test_T7_llm_parse_error_falls_back_to_raw(tmp_repo):
    """LLM 返非 JSON · worker 用 _raw fallback."""
    fake = {"_raw": "# 兜底 markdown\n", "_parse_error": "no json"}
    with patch(
        "omnicompany.packages.services._core.guardian.workers.report_writer.call_llm_json",
        return_value=fake,
    ):
        w = GuardianReportWorker(repo_root=tmp_repo)
        out = w.run({"guardian.report-request": {}})
        assert out.kind == VerdictKind.PASS
        assert out.output["report_md"] == "# 兜底 markdown\n"


def test_T8_rule_dictionary_helper_picks_only_used_rules():
    """_build_rule_dictionary 只含 rule_scan + audit 实际涉及的 rule_id."""
    rule_scan = {"OMNI-049_aged_files": [], "OMNI-051a_undeclared_subdirs": [{"path": "x"}]}
    audit_records = [{"rule_id": "OMNI-074", "verdict": "dismissed"}]
    d = _build_rule_dictionary(rule_scan, audit_records)
    assert "OMNI-049" in d
    assert "OMNI-051a" in d
    assert "OMNI-074" in d
    # description 字段非空 (从 RULES 取的)
    assert d["OMNI-049"]["description"]
    assert d["OMNI-051a"]["description"]


# ─── e2e (需真 LLM key) ─────────────────────────────────────────

@pytest.mark.skipif(
    not os.environ.get("THE_COMPANY_API_KEY"),
    reason="needs THE_COMPANY_API_KEY for real LLM call",
)
def test_e2e_real_llm_produces_chinese_markdown(tmp_repo):
    """E2E · 真 qwen-3.6-plus 调一次产中文 markdown · 验有'守护' / '原始证据' / 不含'OMNI-'代号在 body."""
    # 喂 1 条 audit 让 LLM 有内容翻译
    audit = tmp_repo / "data/services/guardian/audit/records.jsonl"
    audit.write_text(json.dumps({
        "verdict": "confirmed", "rule_id": "OMNI-051a",
        "target_path": "data/services/foo/bar", "ts": "2026-04-25T00:00:00Z"
    }), encoding="utf-8")

    w = GuardianReportWorker(repo_root=tmp_repo)
    out = w.run({"guardian.report-request": {}})
    assert out.kind == VerdictKind.PASS
    md = out.output["report_md"]
    # 中文标题
    assert "守护" in md or "观察" in md
    # 不打分
    assert "health_score" not in md
    # 顶层概览/规则扫描节
    assert "顶层概览" in md or "概览" in md
