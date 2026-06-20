# [OMNI] origin=claude-code domain=doctor/tests ts=2026-04-11
"""单元测试 + E2E 测试: Router 诊断管线

运行（仅单元测试，无需 API key）:
    pytest tests/test_doctor_router_diagnosis.py -v

运行（含 E2E，需 THE_COMPANY_API_KEY）:
    pytest tests/test_doctor_router_diagnosis.py -v -m e2e
"""
from __future__ import annotations

import ast
import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from omnicompany.packages.services.doctor.routers import (
    RouterExtractorRouter,
    RouterSignatureRouter,
    RouterContextCollectorRouter,
    RouterDeterministicCheckRouter,
    RouterHealthWriterRouter,
    RouterContextualAuditRouter,
    _classify_self_assignment,
    _extract_verdict_pattern,
    _classify_except_handling,
    _get_call_repr,
)
from omnicompany.protocol.anchor import VerdictKind

# 项目绝对路径
_PROJECT_ROOT = Path("/workspace/omnicompany").resolve()
_SOURCE_ROOT = _PROJECT_ROOT / "src" / "omnicompany"
# 2026-04-20 Clean Migration: routers.py 已降级为 compat shim, 实际类定义归档到
# _archive/routers_legacy.py (见 doctor DESIGN.md)。测试需要真实的类定义源文件。
_REAL_ROUTER_FILE = _SOURCE_ROOT / "packages" / "services" / "doctor" / "_archive" / "routers_legacy.py"


# ════════════════════════════════════════════════════════════════
# 辅助工具函数测试
# ════════════════════════════════════════════════════════════════

class TestClassifySelfAssignment:
    def test_logger_is_info(self):
        assert _classify_self_assignment("_logger", "") == "INFO"

    def test_last_token_count_is_info(self):
        assert _classify_self_assignment("last_token_count", "") == "INFO"

    def test_model_is_info(self):
        assert _classify_self_assignment("_model", "") == "INFO"

    def test_cache_is_violation(self):
        assert _classify_self_assignment("cache", "") == "LIKELY_VIOLATION"

    def test_history_is_violation(self):
        assert _classify_self_assignment("session_history", "") == "LIKELY_VIOLATION"

    def test_counter_is_violation(self):
        assert _classify_self_assignment("counter", "") == "LIKELY_VIOLATION"

    def test_unknown_is_suspicious(self):
        assert _classify_self_assignment("my_custom_field", "") == "SUSPICIOUS"

    def test_last_result_is_violation(self):
        assert _classify_self_assignment("last_result", "") == "LIKELY_VIOLATION"


class TestGetCallRepr:
    def test_name_node(self):
        node = ast.parse("Verdict()").body[0].value.func
        assert _get_call_repr(node) == "Verdict"

    def test_attribute_node(self):
        node = ast.parse("self.client.call()").body[0].value.func
        assert _get_call_repr(node) == "self.client.call"

    def test_nested_attribute(self):
        node = ast.parse("a.b.c()").body[0].value.func
        assert _get_call_repr(node) == "a.b.c"


class TestExtractVerdictPattern:
    def test_extracts_pass_verdict(self):
        code = "Verdict(kind=VerdictKind.PASS, confidence=1.0, diagnosis='ok')"
        call_node = ast.parse(code).body[0].value
        result = _extract_verdict_pattern(call_node)
        assert result["kind"] == "PASS"
        assert result["confidence"] == 1.0
        assert result["diagnosis"] == "ok"

    def test_extracts_fail_verdict(self):
        code = "Verdict(kind=VerdictKind.FAIL, confidence=1.0, diagnosis='fail reason')"
        call_node = ast.parse(code).body[0].value
        result = _extract_verdict_pattern(call_node)
        assert result["kind"] == "FAIL"
        assert result["confidence"] == 1.0

    def test_extracts_granted_tags(self):
        code = "Verdict(kind=VerdictKind.PASS, confidence=0.9, granted_tags=['syntax-valid'])"
        call_node = ast.parse(code).body[0].value
        result = _extract_verdict_pattern(call_node)
        assert result["granted_tags"] == ["syntax-valid"]

    def test_fstring_diagnosis_marked(self):
        code = textwrap.dedent("""\
            def run(self):
                return Verdict(kind=VerdictKind.PASS, confidence=1.0, diagnosis=f"found {n}")
        """)
        func = ast.parse(code).body[0]
        ret_node = func.body[0]
        result = _extract_verdict_pattern(ret_node.value)
        assert result["diagnosis"] == "(f-string or expr)"


class TestClassifyExceptHandling:
    def _make_handler(self, body_src: str) -> ast.ExceptHandler:
        code = f"try:\n    pass\nexcept Exception:\n{textwrap.indent(body_src, '    ')}"
        tree = ast.parse(code)
        return tree.body[0].handlers[0]

    def test_return_pass(self):
        handler = self._make_handler("return Verdict(kind=VerdictKind.PASS, confidence=1.0)")
        assert _classify_except_handling(handler) == "return_pass"

    def test_return_fail(self):
        handler = self._make_handler("return Verdict(kind=VerdictKind.FAIL, confidence=1.0)")
        assert _classify_except_handling(handler) == "return_fail"

    def test_raise(self):
        handler = self._make_handler("raise RuntimeError('oops')")
        assert _classify_except_handling(handler) == "raise"

    def test_log_only(self):
        handler = self._make_handler("logger.warning('error: %s', e)")
        assert _classify_except_handling(handler) == "log_only"


# ════════════════════════════════════════════════════════════════
# RouterExtractorRouter
# ════════════════════════════════════════════════════════════════

class TestRouterExtractorRouter:
    def setup_method(self):
        self.r = RouterExtractorRouter()

    # ── 基本提取 ──

    def test_extracts_real_router(self):
        """对项目中已有的 Router 做真实提取，验证核心字段。"""
        result = self.r.run({
            "router_class": "FormatExtractorRouter",
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
        })
        assert result.kind == VerdictKind.PASS
        out = result.output
        assert out["found"] is True
        assert out["format_in"] == "doctor.fmt.request"
        assert out["format_out"] == "doctor.fmt.extracted"
        assert out["run_line_count"] > 0
        assert "RULE" == out["ast_signals"]["router_kind"]

    def test_extracts_verdict_patterns(self):
        """FormatExtractorRouter 返回 PASS Verdict，verdict_patterns 应包含 PASS。"""
        result = self.r.run({
            "router_class": "FormatExtractorRouter",
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
        })
        kinds = {vp["kind"] for vp in result.output["ast_signals"]["verdict_patterns"]}
        assert "PASS" in kinds

    def test_extracts_input_keys_accessed(self):
        """FormatExtractorRouter 读 format_id 和 source_root，应出现在 input_keys_accessed。"""
        result = self.r.run({
            "router_class": "FormatExtractorRouter",
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
        })
        keys = result.output["ast_signals"]["input_keys_accessed"]
        assert "format_id" in keys

    def test_router_not_found_returns_pass_with_found_false(self, tmp_path):
        """目标文件存在但类不在里面: found=False, 仍 PASS。"""
        py_file = tmp_path / "routers.py"
        py_file.write_text("class OtherRouter:\n    pass\n")
        result = self.r.run({
            "router_class": "NonExistentRouter",
            "source_file": str(py_file),
            "source_root": str(tmp_path),
        })
        assert result.kind == VerdictKind.PASS
        assert result.output["found"] is False

    def test_missing_file_returns_fail(self):
        """source_file 不存在: FAIL。"""
        result = self.r.run({
            "router_class": "SomeRouter",
            "source_file": "/nonexistent/path/routers.py",
            "source_root": str(_SOURCE_ROOT),
        })
        assert result.kind == VerdictKind.FAIL
        assert result.output["found"] is False

    def test_syntax_error_returns_fail(self, tmp_path):
        """AST 语法错误: FAIL。"""
        py_file = tmp_path / "routers.py"
        py_file.write_text("class Broken(\n    def run: pass\n")
        result = self.r.run({
            "router_class": "Broken",
            "source_file": str(py_file),
            "source_root": str(tmp_path),
        })
        assert result.kind == VerdictKind.FAIL

    def test_extracts_llm_router(self, tmp_path):
        """LLM Router 应识别为 router_kind='LLM'。"""
        src = textwrap.dedent("""\
            from omnicompany.runtime.routing.router import Router
            from omnicompany.runtime.llm.llm import LLMClient
            from omnicompany.protocol.anchor import Verdict, VerdictKind

            class MyLLMRouter(Router):
                DESCRIPTION = "An LLM Router that calls the language model"
                FORMAT_IN = "test.input"
                FORMAT_OUT = "test.output"

                def run(self, input_data):
                    client = LLMClient(model="qwen3.6-plus")
                    resp = client.call(messages=[{"role": "user", "content": "hello"}])
                    return Verdict(kind=VerdictKind.PASS, confidence=0.9, diagnosis="done")
        """)
        py_file = tmp_path / "routers.py"
        py_file.write_text(src)
        result = self.r.run({
            "router_class": "MyLLMRouter",
            "source_file": str(py_file),
            "source_root": str(tmp_path),
        })
        assert result.kind == VerdictKind.PASS
        assert result.output["found"] is True
        assert result.output["ast_signals"]["router_kind"] == "LLM"
        assert len(result.output["ast_signals"]["llm_calls"]) >= 1

    def test_detects_self_assignments(self, tmp_path):
        """self.cache = ... 应被检测到并分类为 LIKELY_VIOLATION。"""
        src = textwrap.dedent("""\
            from omnicompany.runtime.routing.router import Router
            from omnicompany.protocol.anchor import Verdict, VerdictKind

            class StatefulRouter(Router):
                DESCRIPTION = "A router that has state"
                FORMAT_IN = "test.input"
                FORMAT_OUT = "test.output"

                def run(self, input_data):
                    self.cache = {}
                    self.cache["key"] = "value"
                    return Verdict(kind=VerdictKind.PASS, confidence=1.0, diagnosis="ok",
                                   output={"result": "done"})
        """)
        py_file = tmp_path / "routers.py"
        py_file.write_text(src)
        result = self.r.run({
            "router_class": "StatefulRouter",
            "source_file": str(py_file),
            "source_root": str(tmp_path),
        })
        assignments = result.output["ast_signals"]["self_assignments"]
        violations = [a for a in assignments if a["classification"] == "LIKELY_VIOLATION"]
        assert len(violations) >= 1
        assert any(a["var"] == "cache" for a in violations)

    def test_extracts_exception_patterns(self, tmp_path):
        """except 块中 return Verdict(PASS) 应被检测为 return_pass。"""
        src = textwrap.dedent("""\
            from omnicompany.runtime.routing.router import Router
            from omnicompany.protocol.anchor import Verdict, VerdictKind
            import json

            class GulpRouter(Router):
                DESCRIPTION = "Router that swallows exceptions"
                FORMAT_IN = "test.input"
                FORMAT_OUT = "test.output"

                def run(self, input_data):
                    try:
                        data = json.loads(input_data["text"])
                    except json.JSONDecodeError:
                        return Verdict(kind=VerdictKind.PASS, confidence=1.0,
                                       diagnosis="ok", output={})
                    return Verdict(kind=VerdictKind.FAIL, confidence=1.0,
                                   diagnosis="no", output={})
        """)
        py_file = tmp_path / "routers.py"
        py_file.write_text(src)
        result = self.r.run({
            "router_class": "GulpRouter",
            "source_file": str(py_file),
            "source_root": str(tmp_path),
        })
        exc_patterns = result.output["ast_signals"]["exception_patterns"]
        assert len(exc_patterns) >= 1
        assert exc_patterns[0]["handling"] == "return_pass"

    def test_directory_source_file(self, tmp_path):
        """source_file 为目录时，遍历所有 .py 文件。"""
        routers_dir = tmp_path / "routers"
        routers_dir.mkdir()
        src = textwrap.dedent("""\
            from omnicompany.runtime.routing.router import Router
            from omnicompany.protocol.anchor import Verdict, VerdictKind

            class DirRouter(Router):
                DESCRIPTION = "Router defined in a directory"
                FORMAT_IN = "dir.input"
                FORMAT_OUT = "dir.output"

                def run(self, input_data):
                    return Verdict(kind=VerdictKind.PASS, confidence=1.0,
                                   diagnosis="ok", output={})
        """)
        (routers_dir / "sub.py").write_text(src)
        result = self.r.run({
            "router_class": "DirRouter",
            "source_file": str(routers_dir),
            "source_root": str(tmp_path),
        })
        assert result.kind == VerdictKind.PASS
        assert result.output["found"] is True
        assert result.output["format_in"] == "dir.input"


# ════════════════════════════════════════════════════════════════
# RouterSignatureRouter
# ════════════════════════════════════════════════════════════════

class TestRouterSignatureRouter:
    def setup_method(self):
        self.r = RouterSignatureRouter()
        self.base = {
            "router_class": "TestRouter",
            "source_file": "/some/path/routers.py",
            "source_root": str(_SOURCE_ROOT),
            "found": True,
            "description": "A well-described router that does something useful",
            "format_in": "test.input",
            "format_out": "test.output",
            "ast_signals": {"router_kind": "RULE"},
        }

    def test_pass_with_all_present(self):
        result = self.r.run(self.base)
        assert result.kind == VerdictKind.PASS
        assert result.output["sig_ok"] is True
        checks = result.output["checks"]
        assert len(checks) == 1
        assert checks[0]["check"] == "signature"
        assert checks[0]["passed"] is True
        assert checks[0]["severity"] == "CRITICAL"

    def test_pass_includes_description_length(self):
        result = self.r.run(self.base)
        obs = result.output["checks"][0]["observation"]
        assert "chars" in obs
        assert "FORMAT_IN" in obs

    def test_fail_class_not_found(self):
        data = dict(self.base, found=False)
        result = self.r.run(data)
        assert result.kind == VerdictKind.FAIL
        assert result.output["sig_ok"] is False
        obs = result.output["checks"][0]["observation"]
        assert "不存在" in obs

    def test_fail_missing_description(self):
        data = dict(self.base, description=None)
        result = self.r.run(data)
        assert result.kind == VerdictKind.FAIL
        detail = result.output["checks"][0]["detail"]
        assert "DESCRIPTION_empty" in detail["missing"]

    def test_fail_missing_format_in(self):
        data = dict(self.base, format_in=None)
        result = self.r.run(data)
        assert result.kind == VerdictKind.FAIL
        detail = result.output["checks"][0]["detail"]
        assert "FORMAT_IN_empty" in detail["missing"]

    def test_fail_missing_format_out(self):
        data = dict(self.base, format_out="")
        result = self.r.run(data)
        assert result.kind == VerdictKind.FAIL
        detail = result.output["checks"][0]["detail"]
        assert "FORMAT_OUT_empty" in detail["missing"]

    def test_fail_carries_extracted_data(self):
        """FAIL 输出仍然携带 extracted 字段（供 health_writer 使用）。"""
        data = dict(self.base, found=False)
        result = self.r.run(data)
        assert "extracted" in result.output

    def test_pass_carries_full_extracted(self):
        """PASS 输出的 extracted 包含原始 input_data。"""
        result = self.r.run(self.base)
        assert result.output["extracted"]["format_in"] == "test.input"


# ════════════════════════════════════════════════════════════════
# RouterContextCollectorRouter
# ════════════════════════════════════════════════════════════════

class TestRouterContextCollectorRouter:
    def setup_method(self):
        self.r = RouterContextCollectorRouter()

    def _make_acc(self, format_in: str, format_out: str, router_class: str = "TestRouter") -> dict:
        return {
            "router_class": router_class,
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
            "extracted": {
                "found": True,
                "format_in": format_in,
                "format_out": format_out,
                "ast_signals": {"router_kind": "RULE"},
            },
            "sig_ok": True,
            "checks": [],
        }

    def test_always_returns_pass(self):
        acc = self._make_acc("nonexistent.format.xyz", "nonexistent.format.abc")
        result = self.r.run(acc)
        assert result.kind == VerdictKind.PASS

    def test_records_context_gaps_for_unknown_format(self):
        acc = self._make_acc("totally.unknown.format.xyz123", "totally.unknown.format.abc456")
        result = self.r.run(acc)
        gaps = result.output["context"]["context_gaps"]
        assert any("FORMAT_IN" in g for g in gaps)
        assert any("FORMAT_OUT" in g for g in gaps)

    def test_finds_real_format_definition(self):
        """doctor.fmt.request 应能在 formats.py 中找到。"""
        acc = self._make_acc("doctor.fmt.request", "doctor.fmt.extracted",
                             "FormatExtractorRouter")
        result = self.r.run(acc)
        ctx = result.output["context"]
        assert ctx["format_in_def"] is not None
        assert ctx["format_in_def"]["id"] == "doctor.fmt.request"
        assert ctx["format_in_def"]["description"]  # 有描述

    def test_finds_downstream_router(self):
        """FORMAT_OUT=doctor.fmt.extracted 的下游是 SignatureDiffRouter。"""
        acc = self._make_acc("doctor.fmt.request", "doctor.fmt.extracted",
                             "FormatExtractorRouter")
        result = self.r.run(acc)
        ctx = result.output["context"]
        downstream_classes = [r["class"] for r in ctx["downstream_routers"]]
        assert "SignatureDiffRouter" in downstream_classes

    def test_context_gaps_for_orphan_router(self):
        """FORMAT_IN 无人生产时，context_gaps 应提示无上游。"""
        acc = self._make_acc("unique.orphan.format.zyx987", "doctor.fmt.extracted",
                             "OrphanRouter")
        result = self.r.run(acc)
        gaps = result.output["context"]["context_gaps"]
        assert any("上游" in g for g in gaps)

    def test_pipeline_not_found_recorded_in_gaps(self):
        """pipeline.py 不引用 router_class 时，context_gaps 应有提示。"""
        acc = self._make_acc("doctor.fmt.request", "doctor.fmt.extracted",
                             "NonExistentRouterXYZ9999")
        result = self.r.run(acc)
        gaps = result.output["context"]["context_gaps"]
        assert any("pipeline" in g.lower() or "未在" in g for g in gaps)

    def test_output_retains_input_fields(self):
        """context_collector 追加 context 字段，原有 checks 等字段不丢失。"""
        acc = self._make_acc("doctor.fmt.request", "doctor.fmt.extracted")
        acc["checks"] = [{"check": "signature", "passed": True}]
        result = self.r.run(acc)
        assert result.output["checks"] == [{"check": "signature", "passed": True}]
        assert "context" in result.output


# ════════════════════════════════════════════════════════════════
# RouterDeterministicCheckRouter
# ════════════════════════════════════════════════════════════════

class TestRouterDeterministicCheckRouter:
    def setup_method(self):
        self.r = RouterDeterministicCheckRouter()

    def _make_acc(self, extracted: dict, source_file: str | None = None) -> dict:
        return {
            "router_class": "TestRouter",
            "source_file": source_file or str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
            "extracted": extracted,
            "sig_ok": True,
            "checks": [{"check": "signature", "passed": True, "severity": "CRITICAL"}],
        }

    def _make_extracted(
        self,
        description: str = "A sufficiently long description for the router",
        run_source: str = "",
        run_line_count: int = 40,
        router_kind: str = "RULE",
        verdict_patterns: list | None = None,
        exception_patterns: list | None = None,
        self_assignments: list | None = None,
        llm_calls: list | None = None,
    ) -> dict:
        return {
            "found": True,
            "description": description,
            "format_in": "test.input",
            "format_out": "test.output",
            "run_source": run_source,
            "run_line_count": run_line_count,
            "ast_signals": {
                "router_kind": router_kind,
                "llm_calls": llm_calls or [],
                "self_assignments": self_assignments or [],
                "input_keys_accessed": [],
                "output_keys_produced": [],
                "verdict_patterns": verdict_patterns if verdict_patterns is not None else [
                    {"kind": "PASS", "confidence": 1.0, "diagnosis": "ok", "granted_tags": []},
                    {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
                ],
                "exception_patterns": exception_patterns or [],
            },
        }

    # ── 永远 PASS ──

    def test_always_returns_pass(self):
        acc = self._make_acc(self._make_extracted())
        result = self.r.run(acc)
        assert result.kind == VerdictKind.PASS

    def test_appends_checks_to_existing(self):
        acc = self._make_acc(self._make_extracted())
        result = self.r.run(acc)
        # 原有 signature check + 新增的 det checks
        assert len(result.output["checks"]) > 1

    # ── R-01: DESCRIPTION 长度 ──

    def test_r01_pass_long_enough(self):
        extracted = self._make_extracted(description="A" * 60)
        result = self.r.run(self._make_acc(extracted))
        r01 = next(c for c in result.output["checks"] if c["check"] == "R-01")
        assert r01["passed"] is True

    def test_r01_fail_too_short(self):
        extracted = self._make_extracted(description="Short")
        result = self.r.run(self._make_acc(extracted))
        r01 = next(c for c in result.output["checks"] if c["check"] == "R-01")
        assert r01["passed"] is False
        assert r01["severity"] == "HIGH"

    def test_r01_observation_contains_length(self):
        extracted = self._make_extracted(description="A" * 60)
        result = self.r.run(self._make_acc(extracted))
        r01 = next(c for c in result.output["checks"] if c["check"] == "R-01")
        assert "60" in r01["observation"]

    # ── R-04: 统一 LLMClient ──

    def test_r04_pass_no_direct_import(self):
        """实际 doctor/routers.py 没有直接 import openai/anthropic。"""
        extracted = self._make_extracted()
        acc = self._make_acc(extracted, source_file=str(_REAL_ROUTER_FILE))
        result = self.r.run(acc)
        r04 = next(c for c in result.output["checks"] if c["check"] == "R-04")
        assert r04["passed"] is True

    def test_r04_fail_direct_openai_import(self, tmp_path):
        py_file = tmp_path / "routers.py"
        py_file.write_text("import openai\nclass X: pass\n")
        extracted = self._make_extracted()
        acc = self._make_acc(extracted, source_file=str(py_file))
        result = self.r.run(acc)
        r04 = next(c for c in result.output["checks"] if c["check"] == "R-04")
        assert r04["passed"] is False
        assert r04["severity"] == "CRITICAL"

    # ── R-05: PASS + FAIL 双覆盖 ──

    def test_r05_pass_both_present(self):
        extracted = self._make_extracted(verdict_patterns=[
            {"kind": "PASS", "confidence": 1.0, "diagnosis": "ok", "granted_tags": []},
            {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
        ])
        result = self.r.run(self._make_acc(extracted))
        r05 = next(c for c in result.output["checks"] if c["check"] == "R-05")
        assert r05["passed"] is True

    def test_r05_fail_only_pass(self):
        extracted = self._make_extracted(verdict_patterns=[
            {"kind": "PASS", "confidence": 1.0, "diagnosis": "ok", "granted_tags": []},
        ])
        result = self.r.run(self._make_acc(extracted))
        r05 = next(c for c in result.output["checks"] if c["check"] == "R-05")
        assert r05["passed"] is False
        assert r05["severity"] == "HIGH"

    def test_r05_fail_only_fail(self):
        extracted = self._make_extracted(verdict_patterns=[
            {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
        ])
        result = self.r.run(self._make_acc(extracted))
        r05 = next(c for c in result.output["checks"] if c["check"] == "R-05")
        assert r05["passed"] is False

    def test_r05_fail_empty_patterns(self):
        extracted = self._make_extracted(verdict_patterns=[])
        result = self.r.run(self._make_acc(extracted))
        r05 = next(c for c in result.output["checks"] if c["check"] == "R-05")
        assert r05["passed"] is False

    # ── R-06: 不直接写文件 ──

    def test_r06_pass_no_writes(self):
        extracted = self._make_extracted(run_source="    data = {}\n    return data\n")
        result = self.r.run(self._make_acc(extracted))
        r06 = next(c for c in result.output["checks"] if c["check"] == "R-06")
        assert r06["passed"] is True

    def test_r06_fail_write_text(self):
        extracted = self._make_extracted(run_source="    path.write_text('content')\n")
        result = self.r.run(self._make_acc(extracted))
        r06 = next(c for c in result.output["checks"] if c["check"] == "R-06")
        assert r06["passed"] is False
        assert r06["severity"] == "HIGH"

    def test_r06_pass_open_read_mode(self):
        """open(..., 'r') 是读操作，不应触发 R-06。"""
        extracted = self._make_extracted(run_source="    f = open(path, 'r')\n")
        result = self.r.run(self._make_acc(extracted))
        r06 = next(c for c in result.output["checks"] if c["check"] == "R-06")
        assert r06["passed"] is True

    def test_r06_fail_open_write_mode(self):
        extracted = self._make_extracted(run_source='    f = open(path, "w")\n    f.write("x")\n')
        result = self.r.run(self._make_acc(extracted))
        r06 = next(c for c in result.output["checks"] if c["check"] == "R-06")
        assert r06["passed"] is False

    # ── R-10: run() 行数 ──

    def test_r10_pass_under_limit(self):
        extracted = self._make_extracted(run_line_count=60)
        result = self.r.run(self._make_acc(extracted))
        r10 = next(c for c in result.output["checks"] if c["check"] == "R-10")
        assert r10["passed"] is True

    def test_r10_pass_exactly_80(self):
        extracted = self._make_extracted(run_line_count=80)
        result = self.r.run(self._make_acc(extracted))
        r10 = next(c for c in result.output["checks"] if c["check"] == "R-10")
        assert r10["passed"] is True

    def test_r10_fail_over_limit(self):
        extracted = self._make_extracted(run_line_count=95)
        result = self.r.run(self._make_acc(extracted))
        r10 = next(c for c in result.output["checks"] if c["check"] == "R-10")
        assert r10["passed"] is False
        assert r10["severity"] == "MEDIUM"
        assert "95" in r10["observation"]

    # ── R-11: 无硬编模型名 ──

    def test_r11_pass_no_model_name(self):
        extracted = self._make_extracted(run_source="    client.call(messages=[])\n")
        result = self.r.run(self._make_acc(extracted))
        r11 = next(c for c in result.output["checks"] if c["check"] == "R-11")
        assert r11["passed"] is True

    def test_r11_fail_gpt4_in_string(self):
        extracted = self._make_extracted(run_source='    model = "gpt-4-turbo"\n')
        result = self.r.run(self._make_acc(extracted))
        r11 = next(c for c in result.output["checks"] if c["check"] == "R-11")
        assert r11["passed"] is False
        assert r11["severity"] == "MEDIUM"

    def test_r11_fail_claude_in_string(self):
        extracted = self._make_extracted(run_source='    m = "claude-3-opus"\n')
        result = self.r.run(self._make_acc(extracted))
        r11 = next(c for c in result.output["checks"] if c["check"] == "R-11")
        assert r11["passed"] is False

    def test_r11_pass_model_in_comment(self):
        """注释行中出现模型名不应触发（注释行以 # 开头的行）。"""
        extracted = self._make_extracted(run_source='    # model gpt-4 is not allowed\n    pass\n')
        result = self.r.run(self._make_acc(extracted))
        r11 = next(c for c in result.output["checks"] if c["check"] == "R-11")
        assert r11["passed"] is True

    # ── R-12: 无 LLM 协议泄漏 ──

    def test_r12_pass_no_protocol_leak(self):
        extracted = self._make_extracted(run_source="    data = resp.content\n")
        result = self.r.run(self._make_acc(extracted))
        r12 = next(c for c in result.output["checks"] if c["check"] == "R-12")
        assert r12["passed"] is True

    def test_r12_fail_choices_access(self):
        extracted = self._make_extracted(run_source='    text = response.choices[0].message.content\n')
        result = self.r.run(self._make_acc(extracted))
        r12 = next(c for c in result.output["checks"] if c["check"] == "R-12")
        assert r12["passed"] is False
        assert r12["severity"] == "MEDIUM"

    def test_r12_fail_tool_use_type_check(self):
        extracted = self._make_extracted(
            run_source='    if block.type == "tool_use":\n        pass\n'
        )
        result = self.r.run(self._make_acc(extracted))
        r12 = next(c for c in result.output["checks"] if c["check"] == "R-12")
        assert r12["passed"] is False

    # ── R-13: RULE Router confidence = 1.0 ──

    def test_r13_pass_rule_router_all_1_0(self):
        extracted = self._make_extracted(
            router_kind="RULE",
            verdict_patterns=[
                {"kind": "PASS", "confidence": 1.0, "diagnosis": "ok", "granted_tags": []},
                {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
            ],
        )
        result = self.r.run(self._make_acc(extracted))
        r13 = next(c for c in result.output["checks"] if c["check"] == "R-13")
        assert r13["passed"] is True

    def test_r13_fail_rule_router_non_1_0(self):
        extracted = self._make_extracted(
            router_kind="RULE",
            verdict_patterns=[
                {"kind": "PASS", "confidence": 0.8, "diagnosis": "ok", "granted_tags": []},
                {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
            ],
        )
        result = self.r.run(self._make_acc(extracted))
        r13 = next(c for c in result.output["checks"] if c["check"] == "R-13")
        assert r13["passed"] is False

    def test_r13_skipped_for_llm_router(self):
        """LLM Router 不检查 R-13。"""
        extracted = self._make_extracted(
            router_kind="LLM",
            verdict_patterns=[
                {"kind": "PASS", "confidence": 0.7, "diagnosis": "ok", "granted_tags": []},
                {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
            ],
        )
        result = self.r.run(self._make_acc(extracted))
        r13_checks = [c for c in result.output["checks"] if c["check"] == "R-13"]
        assert len(r13_checks) == 0  # LLM Router 不产出 R-13

    # ── R-17: 异常不假通过 ──

    def test_r17_pass_no_except_pass(self):
        extracted = self._make_extracted(exception_patterns=[
            {"exception_type": "Exception", "handling": "return_fail", "context": ""},
        ])
        result = self.r.run(self._make_acc(extracted))
        r17 = next(c for c in result.output["checks"] if c["check"] == "R-17")
        assert r17["passed"] is True

    def test_r17_fail_except_returns_pass(self):
        extracted = self._make_extracted(exception_patterns=[
            {"exception_type": "json.JSONDecodeError", "handling": "return_pass", "context": ""},
        ])
        result = self.r.run(self._make_acc(extracted))
        r17 = next(c for c in result.output["checks"] if c["check"] == "R-17")
        assert r17["passed"] is False
        assert r17["severity"] == "HIGH"

    def test_r17_pass_empty_patterns(self):
        extracted = self._make_extracted(exception_patterns=[])
        result = self.r.run(self._make_acc(extracted))
        r17 = next(c for c in result.output["checks"] if c["check"] == "R-17")
        assert r17["passed"] is True

    # ── R-07 信号 ──

    def test_r07_signal_emitted_for_suspicious(self):
        extracted = self._make_extracted(self_assignments=[
            {"var": "my_field", "line": 42, "classification": "SUSPICIOUS", "context": "self.my_field = x"},
        ])
        result = self.r.run(self._make_acc(extracted))
        signals = [c for c in result.output["checks"] if c["check"] == "R-07-signal"]
        assert len(signals) == 1
        assert signals[0]["passed"] is None  # 不判定对错

    def test_r07_signal_emitted_for_violation(self):
        extracted = self._make_extracted(self_assignments=[
            {"var": "cache", "line": 10, "classification": "LIKELY_VIOLATION", "context": ""},
        ])
        result = self.r.run(self._make_acc(extracted))
        signals = [c for c in result.output["checks"] if c["check"] == "R-07-signal"]
        assert len(signals) == 1
        assert signals[0]["severity"] == "HIGH"

    def test_r07_info_not_emitted(self):
        """INFO 级别的 self 赋值不产出 check 记录。"""
        extracted = self._make_extracted(self_assignments=[
            {"var": "_logger", "line": 5, "classification": "INFO", "context": ""},
        ])
        result = self.r.run(self._make_acc(extracted))
        signals = [c for c in result.output["checks"] if c["check"] == "R-07-signal"]
        assert len(signals) == 0


# ════════════════════════════════════════════════════════════════
# RouterHealthWriterRouter
# ════════════════════════════════════════════════════════════════

class TestRouterHealthWriterRouter:
    def setup_method(self):
        self.r = RouterHealthWriterRouter()

    def _make_acc(self, checks: list[dict], sig_ok: bool = True,
                  context: dict | None = None, audit_path: str = "") -> dict:
        return {
            "router_class": "TestRouter",
            "source_file": "/some/routers.py",
            "source_root": str(_SOURCE_ROOT),
            "extracted": {"found": True},
            "sig_ok": sig_ok,
            "checks": checks,
            "context": context or {"context_gaps": []},
            "audit_path": audit_path,
        }

    # ── 评分计算 ──

    def test_all_pass_gives_perfect_score(self):
        checks = [
            {"check": "signature", "severity": "CRITICAL", "passed": True},
            {"check": "R-01", "severity": "HIGH", "passed": True},
            {"check": "R-10", "severity": "MEDIUM", "passed": True},
        ]
        result = self.r.run(self._make_acc(checks))
        assert result.output["health_score"] == 1.0

    def test_critical_fail_lowers_score_most(self):
        checks = [
            {"check": "signature", "severity": "CRITICAL", "passed": False},  # weight 4
            {"check": "R-01", "severity": "HIGH", "passed": True},            # weight 3
            {"check": "R-10", "severity": "MEDIUM", "passed": True},          # weight 2
        ]
        result = self.r.run(self._make_acc(checks))
        # score = (3+2)/(4+3+2) = 5/9 ≈ 0.556
        score = result.output["health_score"]
        assert abs(score - 5 / 9) < 0.01

    def test_null_passed_not_counted(self):
        """passed=null 的 check（信号类）不计入分母。"""
        checks = [
            {"check": "R-07-signal", "severity": "MEDIUM", "passed": None},
            {"check": "signature", "severity": "CRITICAL", "passed": True},
        ]
        result = self.r.run(self._make_acc(checks))
        # 只有 signature (CRITICAL=4) 计入，score = 4/4 = 1.0
        assert result.output["health_score"] == 1.0

    def test_info_checks_not_counted(self):
        """severity=INFO 的 check 不计入分母（weight=0）。"""
        checks = [
            {"check": "contextual_audit", "severity": "INFO", "passed": True},
            {"check": "R-01", "severity": "HIGH", "passed": False},
        ]
        result = self.r.run(self._make_acc(checks))
        # 只有 R-01 (HIGH=3) 计入，分子 0，score = 0/3 = 0.0
        assert result.output["health_score"] == 0.0

    # ── 评级 ──

    def test_grade_from_llm_audit_takes_priority(self):
        """contextual_audit check 中的 overall_grade 优先于分数评级。"""
        checks = [
            {"check": "signature", "severity": "CRITICAL", "passed": True},
            {
                "check": "contextual_audit", "severity": "INFO", "passed": True,
                "detail": {"overall_grade": "C"},  # LLM 说 C
            },
        ]
        result = self.r.run(self._make_acc(checks))
        assert result.output["health_grade"] == "C"

    def test_grade_fallback_to_score_when_no_audit(self):
        """无 contextual_audit 时按分数映射。"""
        checks = [
            {"check": "signature", "severity": "CRITICAL", "passed": True},
            {"check": "R-01", "severity": "HIGH", "passed": True},
        ]
        result = self.r.run(self._make_acc(checks))
        assert result.output["health_grade"] == "A"

    def test_grade_d_for_low_score(self):
        checks = [
            {"check": "signature", "severity": "CRITICAL", "passed": False},
            {"check": "R-04", "severity": "CRITICAL", "passed": False},
            {"check": "R-05", "severity": "HIGH", "passed": False},
        ]
        result = self.r.run(self._make_acc(checks))
        assert result.output["health_grade"] == "D"

    # ── 失败分组 ──

    def test_critical_failures_grouped(self):
        checks = [
            {"check": "R-04", "severity": "CRITICAL", "passed": False,
             "observation": "发现直接 LLM import"},
        ]
        result = self.r.run(self._make_acc(checks))
        assert len(result.output["critical_failures"]) == 1
        assert "R-04" in result.output["critical_failures"][0]

    def test_high_failures_grouped(self):
        checks = [
            {"check": "R-05", "severity": "HIGH", "passed": False,
             "observation": "FAIL 缺失"},
        ]
        result = self.r.run(self._make_acc(checks))
        assert len(result.output["high_failures"]) == 1

    def test_medium_failures_grouped(self):
        checks = [
            {"check": "R-10", "severity": "MEDIUM", "passed": False,
             "observation": "94 行 > 80 行"},
        ]
        result = self.r.run(self._make_acc(checks))
        assert len(result.output["medium_failures"]) == 1

    # ── 孤立 Router 检测 ──

    def test_is_isolated_when_not_in_pipeline(self):
        acc = self._make_acc(
            checks=[],
            context={"context_gaps": ["未在任何 pipeline.py 中使用"]},
        )
        result = self.r.run(acc)
        assert result.output["is_isolated"] is True
        assert "孤立" in result.output["summary"]

    def test_not_isolated_when_in_pipeline(self):
        acc = self._make_acc(
            checks=[],
            context={"context_gaps": ["FORMAT_IN 定义未找到"]},
        )
        result = self.r.run(acc)
        assert result.output["is_isolated"] is False

    # ── 输出结构 ──

    def test_output_contains_required_fields(self):
        result = self.r.run(self._make_acc([]))
        out = result.output
        for field in ("router_class", "source_file", "source_root", "sig_ok", "health_score",
                      "health_grade", "is_isolated", "checks", "critical_failures",
                      "high_failures", "medium_failures", "audit_path", "summary"):
            assert field in out, f"missing field: {field}"

    def test_always_returns_pass(self):
        result = self.r.run(self._make_acc([]))
        assert result.kind == VerdictKind.PASS

    def test_audit_path_forwarded(self):
        acc = self._make_acc(checks=[], audit_path="/some/path/audit.md")
        result = self.r.run(acc)
        assert result.output["audit_path"] == "/some/path/audit.md"


# ════════════════════════════════════════════════════════════════
# RouterContextualAuditRouter（mock LLM）
# ════════════════════════════════════════════════════════════════

class TestRouterContextualAuditRouterMocked:
    def setup_method(self):
        self.r = RouterContextualAuditRouter()

    def _make_full_acc(self, router_kind: str = "RULE") -> dict:
        return {
            "router_class": "TestRouter",
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
            "extracted": {
                "found": True,
                "description": "A test router",
                "format_in": "test.input",
                "format_out": "test.output",
                "run_source": "    def run(self, input_data):\n        return Verdict(...)",
                "run_line_count": 30,
                "ast_signals": {
                    "router_kind": router_kind,
                    "llm_calls": [{"line": 10, "context": "client.call(...)"}] if router_kind == "LLM" else [],
                    "self_assignments": [],
                    "input_keys_accessed": ["key1"],
                    "output_keys_produced": ["result"],
                    "verdict_patterns": [
                        {"kind": "PASS", "confidence": 1.0 if router_kind == "RULE" else 0.9,
                         "diagnosis": "ok", "granted_tags": []},
                        {"kind": "FAIL", "confidence": 1.0, "diagnosis": "fail", "granted_tags": []},
                    ],
                    "exception_patterns": [],
                },
            },
            "sig_ok": True,
            "checks": [
                {"check": "signature", "severity": "CRITICAL", "passed": True,
                 "observation": "all ok"},
            ],
            "context": {
                "format_in_def": {"id": "test.input", "description": "test", "tags": []},
                "format_out_def": {"id": "test.output", "description": "test", "tags": []},
                "upstream_routers": [],
                "downstream_routers": [],
                "pipeline_brief": None,
                "context_gaps": ["未在任何 pipeline.py 中使用"],
            },
        }

    def _make_llm_response(self, grade: str = "B", router_kind: str = "RULE") -> dict:
        base = {
            "a_info_sufficient": "true",
            "a_info_gaps": "none",
            "a_implicit_assumptions": "none",
            "a_budget_feasible": "true",
            "a_budget_notes": "no LLM calls",
            "b_r08_intermediates_ok": "true",
            "b_r08_candidates": "none",
            "b_r16_generic_extracted": "true",
            "b_r16_candidates": "none",
            "b_error_paths_complete": "true",
            "b_error_notes": "all paths handled",
            "c_r14_diagnosis_quality": "true",
            "c_r14_notes": "diagnosis is specific",
            "c_r15_tags_accurate": "N/A",
            "c_r15_notes": "no granted_tags",
            "c_format_out_aligned": "true",
            "c_format_out_notes": "aligned",
            "c_confidence_calibrated": "true",
            "c_confidence_notes": "1.0 for RULE",
            "d_rule_boundary_complete": "true",
            "d_rule_boundary_notes": "all boundaries handled",
            "d_rule_output_precise": "true",
            "d_rule_output_notes": "output matches FORMAT_OUT",
            "p_should_split": "false",
            "p_split_reason": "none",
            "p_could_merge": "false",
            "p_merge_notes": "none",
            "overall_grade": grade,
            "key_findings": ["Finding 1"],
            "improvement_suggestions": ["Suggestion 1"],
            "detailed_report": "## Report\nDetails here.",
        }
        if router_kind == "LLM":
            base.update({
                "b_r03_homogeneous": "true",
                "b_r03_notes": "single LLM call",
                "b_hallucination_risk": "low",
                "b_hallucination_notes": "grounded in deterministic data",
                "d_honesty": "true",
                "d_honesty_notes": "prompt allows uncertain",
                "d_precision": "true",
                "d_precision_notes": "schema matches FORMAT_OUT",
                "d_efficiency": "true",
                "d_efficiency_notes": "no redundant LLM tasks",
                "d_judgment": "true",
                "d_judgment_notes": "rubric provided",
            })
            # Remove RULE-specific fields
            del base["d_rule_boundary_complete"]
            del base["d_rule_boundary_notes"]
            del base["d_rule_output_precise"]
            del base["d_rule_output_notes"]
        return base

    def test_llm_success_appends_audit_check(self):
        """LLM 调用成功时，追加 contextual_audit check。"""
        acc = self._make_full_acc(router_kind="RULE")
        mock_resp = self._make_llm_response("B", "RULE")

        with patch.object(self.r, "_audit", return_value=(mock_resp, json.dumps(mock_resp))):
            with patch.object(self.r, "_archive_report", return_value=Path("/tmp/audit.md")):
                result = self.r.run(acc)

        assert result.kind == VerdictKind.PASS
        audit_checks = [c for c in result.output["checks"] if c["check"] == "contextual_audit"]
        assert len(audit_checks) == 1
        assert audit_checks[0]["passed"] is True
        assert audit_checks[0]["detail"]["overall_grade"] == "B"

    def test_llm_failure_appends_null_check(self):
        """LLM 调用失败时，追加 passed=None 的 check，不阻断。"""
        acc = self._make_full_acc()

        with patch.object(self.r, "_audit", return_value=({}, "(LLM error)")):
            result = self.r.run(acc)

        assert result.kind == VerdictKind.PASS
        audit_checks = [c for c in result.output["checks"] if c["check"] == "contextual_audit"]
        assert len(audit_checks) == 1
        assert audit_checks[0]["passed"] is None

    def test_selects_schema_b_for_rule_router(self):
        """RULE Router 使用 Schema B（包含 d_rule_boundary_complete）。"""
        acc = self._make_full_acc(router_kind="RULE")
        captured_msg = []

        def capture_audit(user_msg, schema_template):
            captured_msg.append(schema_template)
            return ({}, "")

        with patch.object(self.r, "_audit", side_effect=capture_audit):
            self.r.run(acc)

        assert captured_msg
        # Schema B 应包含 d_rule_boundary_complete
        assert "d_rule_boundary_complete" in captured_msg[0]
        # Schema B 不应包含 d_honesty（LLM Router 专用）
        assert "d_honesty" not in captured_msg[0]

    def test_selects_schema_a_for_llm_router(self):
        """LLM Router 使用 Schema A（包含 d_honesty）。"""
        acc = self._make_full_acc(router_kind="LLM")
        captured_msg = []

        def capture_audit(user_msg, schema_template):
            captured_msg.append(schema_template)
            return ({}, "")

        with patch.object(self.r, "_audit", side_effect=capture_audit):
            self.r.run(acc)

        assert captured_msg
        assert "d_honesty" in captured_msg[0]
        assert "d_rule_boundary_complete" not in captured_msg[0]

    def test_audit_path_set_on_success(self):
        """LLM 成功时 audit_path 字段被设置。"""
        acc = self._make_full_acc()
        mock_resp = self._make_llm_response("A", "RULE")

        with patch.object(self.r, "_audit", return_value=(mock_resp, "")):
            with patch.object(self.r, "_archive_report",
                             return_value=Path("/tmp/rtr_TestRouter/abc1234.md")):
                result = self.r.run(acc)

        assert "audit_path" in result.output
        assert "TestRouter" in result.output["audit_path"]

    def test_retries_on_invalid_response(self):
        """LLM 返回无效 JSON 时重试；最多 3 次后放弃。"""
        acc = self._make_full_acc()
        call_count = [0]

        def bad_audit(user_msg, schema):
            call_count[0] += 1
            return ({}, "(bad response)")

        with patch.object(self.r, "_audit", side_effect=bad_audit):
            result = self.r.run(acc)

        assert call_count[0] == 3  # 3 次尝试
        audit_checks = [c for c in result.output["checks"] if c["check"] == "contextual_audit"]
        assert audit_checks[0]["passed"] is None

    def test_user_msg_contains_router_source(self):
        """user message 应包含 Router 源码。"""
        acc = self._make_full_acc()
        captured = []

        def capture(user_msg, schema):
            captured.append(user_msg)
            return ({}, "")

        with patch.object(self.r, "_audit", side_effect=capture):
            self.r.run(acc)

        assert captured
        assert "TestRouter" in captured[0]
        assert "FORMAT_IN" in captured[0]

    def test_failed_checks_included_in_user_msg(self):
        """确定性失败项应出现在 user message 中。"""
        acc = self._make_full_acc()
        acc["checks"].append({
            "check": "R-10", "severity": "MEDIUM", "passed": False,
            "observation": "94 lines > 80",
        })
        captured = []

        def capture(user_msg, schema):
            captured.append(user_msg)
            return ({}, "")

        with patch.object(self.r, "_audit", side_effect=capture):
            self.r.run(acc)

        assert "R-10" in captured[0]


# ════════════════════════════════════════════════════════════════
# _filter_standards（标准节选）
# ════════════════════════════════════════════════════════════════

class TestFilterStandards:
    def setup_method(self):
        self.r = RouterContextualAuditRouter()

    def test_removes_deterministic_standards(self):
        """R-01/04/05 等确定性标准应被过滤掉。"""
        mock_content = (
            "## 原则 1\n\nsome text\n\n"
            "**R-01** description\n\n"
            "**R-03** call homogeneity\n\n"
            "**R-04** must use LLMClient\n\n"
            "**R-08** intermediate products\n\n"
        )
        result = self.r._filter_standards(mock_content)
        assert "R-03" in result
        assert "R-08" in result
        assert "R-01" not in result
        assert "R-04" not in result

    def test_loads_real_standards(self):
        """真实 router.md 应能加载且包含非过滤内容。"""
        standards = self.r._load_standards(_SOURCE_ROOT)
        assert "router.md 未找到" not in standards
        assert "R-03" in standards or "原则" in standards


# ════════════════════════════════════════════════════════════════
# E2E 集成测试（需要真实 API key）
# ════════════════════════════════════════════════════════════════

@pytest.mark.e2e
class TestRouterDiagnosisE2E:
    """端到端测试：对真实 Router 运行完整诊断链（除 LLM 审计）。"""

    def _run_pipeline(self, router_class: str, source_file: Path) -> dict:
        """运行 extractor → signature → context_collector → det_checker → health_writer。"""
        extractor = RouterExtractorRouter()
        sig_router = RouterSignatureRouter()
        ctx_collector = RouterContextCollectorRouter()
        det_checker = RouterDeterministicCheckRouter()
        health_writer = RouterHealthWriterRouter()

        extracted = extractor.run({
            "router_class": router_class,
            "source_file": str(source_file),
            "source_root": str(_SOURCE_ROOT),
        })
        assert extracted.kind == VerdictKind.PASS

        acc = sig_router.run(extracted.output)
        assert acc.kind == VerdictKind.PASS, f"Signature FAIL for {router_class}"

        acc2 = ctx_collector.run(acc.output)
        assert acc2.kind == VerdictKind.PASS

        acc3 = det_checker.run(acc2.output)
        assert acc3.kind == VerdictKind.PASS

        health = health_writer.run(acc3.output)
        assert health.kind == VerdictKind.PASS
        return health.output

    def test_e2e_format_extractor_router(self):
        """FormatExtractorRouter: RULE Router，应识别 R-05 缺 FAIL 路径。"""
        health = self._run_pipeline("FormatExtractorRouter", _REAL_ROUTER_FILE)
        # FormatExtractorRouter 只有 PASS，应 R-05 FAIL
        high_failures = health["high_failures"]
        assert any("R-05" in f for f in high_failures), \
            f"Expected R-05 in high_failures, got: {high_failures}"
        assert health["health_grade"] in ("A", "B", "C", "D")

    def test_e2e_health_writer_router(self):
        """HealthWriterRouter: RULE Router，应通过大部分检查。"""
        health = self._run_pipeline("HealthWriterRouter", _REAL_ROUTER_FILE)
        assert health["health_score"] > 0.5
        assert health["health_grade"] in ("A", "B")

    def test_e2e_signature_router_shortcircuit(self):
        """目标类不存在时，signature 应 FAIL → 输出 sig_ok=False。"""
        extractor = RouterExtractorRouter()
        sig_router = RouterSignatureRouter()
        health_writer = RouterHealthWriterRouter()

        extracted = extractor.run({
            "router_class": "NonExistentRouter999",
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
        })
        assert extracted.kind == VerdictKind.PASS  # extractor 总是 PASS

        acc = sig_router.run(extracted.output)
        assert acc.kind == VerdictKind.FAIL
        assert acc.output["sig_ok"] is False

        # FAIL 路径：直接给 health_writer（EMIT 语义）
        health = health_writer.run(acc.output)
        assert health.kind == VerdictKind.PASS
        assert health.output["sig_ok"] is False

    def test_e2e_llm_router_detection(self):
        """RouterContextualAuditRouter 是 LLM Router，应识别为 LLM kind。"""
        health = self._run_pipeline(
            "RouterContextualAuditRouter", _REAL_ROUTER_FILE
        )
        # 验证 extracted 中 router_kind 正确识别为 LLM
        checks = health["checks"]
        # det_checker 不应输出 R-13（LLM Router 跳过）
        r13_checks = [c for c in checks if c.get("check") == "R-13"]
        assert len(r13_checks) == 0, "LLM Router should skip R-13"

    def test_e2e_context_collector_finds_neighbors(self):
        """SignatureDiffRouter: FORMAT_IN=doctor.fmt.extracted，应找到上游 FormatExtractorRouter。"""
        extractor = RouterExtractorRouter()
        sig_router = RouterSignatureRouter()
        ctx_collector = RouterContextCollectorRouter()

        extracted = extractor.run({
            "router_class": "SignatureDiffRouter",
            "source_file": str(_REAL_ROUTER_FILE),
            "source_root": str(_SOURCE_ROOT),
        })
        acc = sig_router.run(extracted.output)
        assert acc.kind == VerdictKind.PASS

        ctx_result = ctx_collector.run(acc.output)
        ctx = ctx_result.output["context"]

        # FORMAT_IN = doctor.fmt.extracted → 上游应是 FormatExtractorRouter
        upstream_classes = [r["class"] for r in ctx["upstream_routers"]]
        assert "FormatExtractorRouter" in upstream_classes, \
            f"Expected FormatExtractorRouter in upstream, got: {upstream_classes}"
