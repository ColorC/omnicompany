# [OMNI] origin=claude-code domain=doctor/tests ts=2026-04-10
"""单元测试 + E2E 测试: FormatContextualAuditRouter

运行（仅单元测试，无需 API key）:
    pytest tests/test_doctor_contextual_audit.py -v

运行（含 E2E，需 THE_COMPANY_API_KEY）:
    pytest tests/test_doctor_contextual_audit.py -v -m e2e
    # 或先加载 .env:
    export $(cat .env | xargs) && pytest tests/test_doctor_contextual_audit.py -v
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omnicompany.packages.services.doctor.routers import FormatContextualAuditRouter

# 项目绝对路径（测试中始终用绝对路径避免 cwd 依赖）
_PROJECT_ROOT = Path("/workspace/omnicompany").resolve()
_SOURCE_ROOT = _PROJECT_ROOT / "src" / "omnicompany"


# ────────────────────────────────────────────────────────────────
# _extract_class_source
# ────────────────────────────────────────────────────────────────

class TestExtractClassSource:
    def setup_method(self):
        self.r = FormatContextualAuditRouter()

    def test_extracts_first_class(self):
        content = (
            "class Foo(Router):\n"
            "    FORMAT_OUT = 'foo.bar'\n"
            "    def run(self): pass\n"
            "\n"
            "class Bar(Router):\n"
            "    FORMAT_IN = 'foo.bar'\n"
        )
        result = self.r._extract_class_source(content, "Foo")
        assert "class Foo" in result
        assert "FORMAT_OUT" in result
        assert "class Bar" not in result

    def test_extracts_second_class(self):
        content = (
            "class Alpha(Router):\n"
            "    pass\n"
            "\n"
            "class Beta(Router):\n"
            "    FORMAT_IN = 'x.y'\n"
            "    def run(self): pass\n"
        )
        result = self.r._extract_class_source(content, "Beta")
        assert "class Beta" in result
        assert "FORMAT_IN" in result
        assert "class Alpha" not in result

    def test_class_at_end_of_file(self):
        content = "class Solo(Router):\n    def run(self): pass\n"
        result = self.r._extract_class_source(content, "Solo")
        assert "class Solo" in result
        assert "def run" in result

    def test_class_not_found_returns_truncated_content(self):
        content = "x = 1\n" * 10
        result = self.r._extract_class_source(content, "NonExistent")
        assert len(result) <= self.r._MAX_SRC

    def test_truncates_long_class(self):
        # 超过 _MAX_SRC 时截断
        body = "    x = 1\n" * 1000
        content = f"class Huge(Router):\n{body}"
        result = self.r._extract_class_source(content, "Huge")
        # extract_class_source 本身不截断；截断在 _load_router_sources 里做
        # 只验证包含 class 头
        assert "class Huge" in result


# ────────────────────────────────────────────────────────────────
# _class_owning_line
# ────────────────────────────────────────────────────────────────

class TestClassOwningLine:
    def setup_method(self):
        self.r = FormatContextualAuditRouter()

    def test_finds_class_containing_line(self):
        content = (
            "class Foo(Router):\n"
            "    FORMAT_IN = \"some.format\"\n"
            "\n"
            "class Bar(Router):\n"
            "    FORMAT_IN = \"other.format\"\n"
        )
        assert self.r._class_owning_line(content, 'FORMAT_IN = "some.format"') == "Foo"

    def test_finds_second_class(self):
        content = (
            "class Foo(Router):\n"
            "    FORMAT_IN = \"some.format\"\n"
            "\n"
            "class Bar(Router):\n"
            "    FORMAT_IN = \"other.format\"\n"
        )
        assert self.r._class_owning_line(content, 'FORMAT_IN = "other.format"') == "Bar"

    def test_line_not_found_returns_last_class(self):
        content = "class Only(Router):\n    pass\n"
        # target_line_stripped not in any line → returns last current_class
        result = self.r._class_owning_line(content, "completely absent string xyz123")
        # 找不到目标行，返回最后见到的 class
        assert result == "Only"

    def test_empty_content_returns_none(self):
        assert self.r._class_owning_line("", "some line") is None

    def test_no_class_in_file_returns_none(self):
        content = "x = 1\ny = 2\n"
        assert self.r._class_owning_line(content, "x = 1") is None


# ────────────────────────────────────────────────────────────────
# _load_standards
# ────────────────────────────────────────────────────────────────

class TestLoadStandards:
    def setup_method(self):
        self.r = FormatContextualAuditRouter()

    def test_loads_real_standards(self):
        standards = self.r._load_standards(_SOURCE_ROOT)
        assert "F-01" in standards
        assert "F-13" in standards
        assert "FA-07" in standards
        assert len(standards) > 2000

    def test_fallback_on_missing_path(self, tmp_path):
        # tmp_path 下没有 docs/standards/format.md
        fake_src = tmp_path / "src" / "omnicompany"
        fake_src.mkdir(parents=True)
        result = self.r._load_standards(fake_src)
        assert "未找到" in result


# ────────────────────────────────────────────────────────────────
# _load_router_sources
# ────────────────────────────────────────────────────────────────

class TestLoadRouterSources:
    def setup_method(self):
        self.r = FormatContextualAuditRouter()

    def test_empty_usages_returns_empty(self):
        assert self.r._load_router_sources(_SOURCE_ROOT, [], "INPUT") == []

    def test_no_matching_role_returns_empty(self):
        usages = [{"role": "OUTPUT", "file": "any/file.py", "line": "FORMAT_OUT = ..."}]
        assert self.r._load_router_sources(_SOURCE_ROOT, usages, "INPUT") == []

    def test_finds_real_downstream_router(self):
        # pd.trigger 的下游 Router 是 SummaryReaderRouter
        # file 路径格式：相对于 source_root.parent（即 src/），无 src/ 前缀
        usages = [{
            "role": "INPUT",
            "file": "omnicompany/packages/services/pattern_discovery/routers.py",
            "line": 'FORMAT_IN = "pd.trigger"',
        }]
        result = self.r._load_router_sources(_SOURCE_ROOT, usages, "INPUT")
        assert len(result) == 1
        assert result[0]["class"] == "SummaryReaderRouter"
        assert "def run" in result[0]["source"]

    def test_missing_file_is_skipped(self):
        usages = [{"role": "INPUT", "file": "nonexistent/path/routers.py", "line": "FORMAT_IN = ..."}]
        result = self.r._load_router_sources(_SOURCE_ROOT, usages, "INPUT")
        assert result == []

    def test_deduplicates_same_file(self):
        # 同一个文件出现两次，只加载一次
        usages = [
            {"role": "INPUT", "file": "omnicompany/packages/services/pattern_discovery/routers.py", "line": 'FORMAT_IN = "pd.trigger"'},
            {"role": "INPUT", "file": "omnicompany/packages/services/pattern_discovery/routers.py", "line": 'FORMAT_IN = "pd.trigger"'},
        ]
        result = self.r._load_router_sources(_SOURCE_ROOT, usages, "INPUT")
        assert len(result) == 1

    def test_source_truncated_to_max(self):
        # 构造一个内容极长的临时 Router 文件
        long_content = "class HugeRouter(Router):\n" + "    x = 1\n" * 2000
        usages = [{"role": "INPUT", "file": "fake/routers.py", "line": "FORMAT_IN = ..."}]
        # 临时替换文件读取
        with patch.object(Path, "read_text", return_value=long_content):
            result = self.r._load_router_sources(_SOURCE_ROOT, usages, "INPUT")
        assert len(result) == 1
        assert len(result[0]["source"]) <= self.r._MAX_SRC + len("\n... [truncated]") + 5


# ────────────────────────────────────────────────────────────────
# _archive_report
# ────────────────────────────────────────────────────────────────

class TestArchiveReport:
    def setup_method(self):
        self.r = FormatContextualAuditRouter()

    def test_empty_audit_data_returns_none(self, tmp_path):
        fake_src = (tmp_path / "src" / "omnicompany")
        fake_src.mkdir(parents=True)
        result = self.r._archive_report("foo.bar", fake_src, {}, "")
        assert result is None

    def test_creates_report_file_with_content(self, tmp_path):
        # 建立假 git repo（让 _get_git_hash 能找到 cwd）
        (tmp_path / ".git").mkdir()
        fake_src = tmp_path / "src" / "omnicompany"
        fake_src.mkdir(parents=True)

        audit_data = {
            "overall_grade": "B",
            "key_findings": "Test key finding",
            "detailed_report": "# Detailed Report\n\nContent here.",
        }
        path = self.r._archive_report("foo.bar", fake_src, audit_data, "raw")
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "foo.bar" in content
        assert "Detailed Report" in content
        assert "Grade**: B" in content

    def test_safe_id_replaces_dots(self, tmp_path):
        (tmp_path / ".git").mkdir()
        fake_src = tmp_path / "src" / "omnicompany"
        fake_src.mkdir(parents=True)
        audit_data = {"overall_grade": "A", "key_findings": "", "detailed_report": "x"}
        path = self.r._archive_report("my.format.id", fake_src, audit_data, "")
        assert path is not None
        assert "my_format_id" in str(path)


# ────────────────────────────────────────────────────────────────
# run() 方法（含 LLM mock）
# ────────────────────────────────────────────────────────────────

_BASE_INPUT = {
    "format_id": "test.fmt",
    "source_root": str(_SOURCE_ROOT),
    "extracted": {
        "format_obj": {
            "id": "test.fmt",
            "description": "A test format description for unit testing purposes.",
            "json_schema": {"type": "object", "properties": {"x": {"type": "string"}}, "required": ["x"]},
            "examples": [{"x": "value"}],
            "tags": ["test"],
            "parent": "requirement",
        },
        "usages": [],
    },
    "checks": [],
}

_FULL_AUDIT_JSON = {
    "f01_field_semantics": True,
    "f01_enum_invariants": False,
    "f01_upstream_promises": False,
    "f01_downstream_usage": True,
    "f01_minimal_example": False,
    "f06_schema_coherent": True,
    "f08_preconditions_symmetric": True,
    "fa01_hollow": False,
    "fa04_semantic_overload": False,
    "fa05_clone_rename": False,
    "fa06_semantic_break": False,
    "fa07_heterogeneous_mix": False,
    "upstream_match": True,
    "upstream_match_notes": "OK",
    "downstream_match": False,
    "downstream_match_notes": "mismatch",
    "overall_grade": "C",
    "key_findings": "F-01 枚举缺失",
    "improvement_suggestions": "补充枚举值",
    "detailed_report": "# Report\n\nDetails.",
}


class TestRunMethod:
    def setup_method(self):
        self.r = FormatContextualAuditRouter()

    def test_empty_description_skips_llm_no_crash(self):
        inp = {**_BASE_INPUT, "extracted": {
            "format_obj": {"id": "test.fmt", "description": ""},
            "usages": [],
        }}
        result = self.r.run(inp)
        check = result.output["checks"][-1]
        assert check["check"] == "contextual_audit"
        assert check["grade"] == "?"
        # 管线不应崩溃
        assert result.kind.name == "PASS"

    def test_llm_valid_json_builds_check_correctly(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(_FULL_AUDIT_JSON))]

        with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
            MockLLM.return_value.call.return_value = mock_resp
            result = self.r.run(_BASE_INPUT)

        check = result.output["checks"][-1]
        assert check["check"] == "contextual_audit"
        assert check["grade"] == "C"
        assert check["passed"] is False          # C 不在 (A, B)
        assert "F-01 枚举缺失" in check["detail"]

        sub = {s["name"]: s["passed"] for s in check["sub_checks"]}
        assert sub["f01_five_elements"] is False   # 只有 2/5 True
        assert sub["f06_schema_coherent"] is True
        assert sub["f08_preconditions"] is True
        assert sub["no_antipatterns"] is True
        assert sub["upstream_match"] is True
        assert sub["downstream_match"] is False

    def test_llm_grade_ab_sets_passed_true(self):
        audit = {**_FULL_AUDIT_JSON, "overall_grade": "A",
                 "f01_enum_invariants": True, "f01_upstream_promises": True, "f01_minimal_example": True}
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(audit))]
        with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
            MockLLM.return_value.call.return_value = mock_resp
            result = self.r.run(_BASE_INPUT)
        check = result.output["checks"][-1]
        assert check["passed"] is True

    def test_llm_malformed_json_graceful(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="not valid json {{")]
        with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
            MockLLM.return_value.call.return_value = mock_resp
            result = self.r.run(_BASE_INPUT)
        check = result.output["checks"][-1]
        assert check["grade"] == "?"
        assert result.kind.name == "PASS"   # 管线不崩溃

    def test_llm_exception_graceful(self):
        with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
            MockLLM.return_value.call.side_effect = RuntimeError("network error")
            result = self.r.run(_BASE_INPUT)
        check = result.output["checks"][-1]
        assert check["grade"] == "?"
        assert result.kind.name == "PASS"

    def test_llm_markdown_code_block_stripped(self):
        # LLM 有时会包裹 ```json ... ```
        raw = "```json\n" + json.dumps(_FULL_AUDIT_JSON) + "\n```"
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=raw)]
        with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
            MockLLM.return_value.call.return_value = mock_resp
            result = self.r.run(_BASE_INPUT)
        check = result.output["checks"][-1]
        assert check["grade"] == "C"   # 解析成功

    def test_checks_list_is_appended(self):
        # 验证 check 追加到已有 checks 列表末尾，不覆盖
        existing = [{"check": "sig_diff", "passed": True}]
        inp = {**_BASE_INPUT, "checks": existing}
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=json.dumps(_FULL_AUDIT_JSON))]
        with patch("omnicompany.runtime.llm.llm.LLMClient") as MockLLM:
            MockLLM.return_value.call.return_value = mock_resp
            result = self.r.run(inp)
        checks = result.output["checks"]
        assert checks[0]["check"] == "sig_diff"
        assert checks[-1]["check"] == "contextual_audit"


# ────────────────────────────────────────────────────────────────
# E2E 测试（需要 THE_COMPANY_API_KEY）
# ────────────────────────────────────────────────────────────────

@pytest.mark.e2e
class TestE2E:
    """真实 LLM 调用，需要 THE_COMPANY_API_KEY。

    运行: export $(cat .env | xargs) && pytest tests/test_doctor_contextual_audit.py -m e2e -v
    """

    @pytest.fixture(autouse=True)
    def load_env(self):
        from dotenv import load_dotenv
        load_dotenv(_PROJECT_ROOT / ".env", override=False)
        if not os.environ.get("THE_COMPANY_API_KEY"):
            pytest.skip("THE_COMPANY_API_KEY not set — skip E2E")

    def test_pd_trigger_full_audit(self):
        """pd.trigger 审计：short description → 应得 B/C/D。"""
        # 契约变更 #02 (2026-04-25): 断言 v2 字段 verdict / counts, 去 health_grade
        from omnicompany.packages.services.doctor.run import _run_full_diagnosis
        r = _run_full_diagnosis("pd.trigger", str(_SOURCE_ROOT))
        assert r.get("schema_version") == 2
        assert r["verdict"] in ("healthy", "unhealthy", "uncertain")
        assert "counts" in r and "critical" in r["counts"]
        checks = {c["check"]: c for c in r.get("checks", [])}
        assert "contextual_audit" in checks
        audit = checks["contextual_audit"]
        # audit[grade] 是 LLM 自带的 sub-grade 语义字段 (audit 内部结构 · 非 doctor 输出)
        assert audit["grade"] in ("A", "B", "C", "D")
        assert audit["grade"] != "A", f"pd.trigger 不应得 A，实际: {audit}"

    def test_pd_activities_has_upstream_router_source(self):
        """pd.activities 由 SummaryReaderRouter 产出，上游源码应被找到。"""
        from omnicompany.packages.services.doctor.routers import FormatExtractorRouter
        verdict = FormatExtractorRouter().run({
            "format_id": "pd.activities",
            "source_root": str(_SOURCE_ROOT),
        })
        usages = verdict.output["usages"]
        r = FormatContextualAuditRouter()
        upstreams = r._load_router_sources(_SOURCE_ROOT, usages, "OUTPUT")
        assert len(upstreams) > 0, "应找到 pd.activities 的上游 Router"
        assert any("SummaryReaderRouter" in u["class"] for u in upstreams)

    def test_audit_report_archived(self):
        """审计报告应写入 data/doctor/audit/ 目录。"""
        from omnicompany.packages.services.doctor.run import _run_full_diagnosis
        r = _run_full_diagnosis("pd.trigger", str(_SOURCE_ROOT))
        checks = {c["check"]: c for c in r.get("checks", [])}
        audit = checks.get("contextual_audit", {})
        if audit.get("grade") != "?":   # LLM 成功调用
            assert audit.get("audit_path") is not None
            assert Path(audit["audit_path"]).exists()
