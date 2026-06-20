"""OmniPatrol 规则引擎单元测试

七条规则逐一覆盖，重点在边界条件和豁免逻辑。

覆盖：
  OMNI-001  missing-omnimark          (packages/ 下缺头，多个豁免路径)
  OMNI-002  business-in-framework     (runtime/ 散落，合法文件集豁免)
  OMNI-003  bypass-llm-client         (直接 import，注释行/字符串/归档豁免)
  OMNI-004  async-router-run          (假 async，有 await 不报，framework 豁免)
  OMNI-005  db-outside-data           (.db 路径规则)
  OMNI-006  temp-script-in-src        (多种前缀，tests/ 豁免)
  OMNI-007  stray-config-in-src       (扩展名，允许文件集)
  RuleEngine.evaluate()               (批量、异常隔离)
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian import (
    FileContext,
    RuleEngine,
    RULES,
)
from omnicompany.packages.services._core.guardian.rules.omnimark import _check_missing_omnimark
from omnicompany.packages.services._core.guardian.rules.boundaries import (
    _check_business_in_framework,
    _check_direct_llm_import,
    _check_async_router_run,
    _check_temp_in_src,
)
from omnicompany.packages.services._core.guardian.rules.data_storage import _check_db_outside_data
from omnicompany.packages.services._core.guardian.rules.archmap import _check_stray_config_in_src
from omnicompany.packages.services._core.guardian.rules.manual_evidence_parse import (
    _check_manual_evidence_parse,
)
from omnicompany.packages.services._core.guardian.rules.naming import _check_versioned_filename


# ─── 辅助 ────────────────────────────────────────────────────────

def make_ctx(
    path: str,
    content: str | None = "# placeholder\n",
    change_type: str = "M",
    omnimark: dict | None = None,
) -> FileContext:
    return FileContext(
        path=path,
        abs_path=f"e:/fake/{path}",
        change_type=change_type,
        content=content,
        omnimark=omnimark,
    )


def ctx_with_omnimark(path: str, content: str = "# placeholder\n") -> FileContext:
    """有 OmniMark 头的文件。"""
    mark = {"origin": "human", "domain": "test", "ts": "2026-04-05T00:00:00Z"}
    return make_ctx(path, content=content, omnimark=mark)


# ════════════════════════════════════════════════════════════════
# OMNI-001: missing-omnimark
# ════════════════════════════════════════════════════════════════

class TestOMNI001:
    """缺少 OmniMark 头（packages/ 下的 .py 文件）。"""

    def test_triggers_in_packages_without_mark(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py", omnimark=None)
        assert _check_missing_omnimark(ctx)

    def test_no_trigger_with_mark(self):
        ctx = ctx_with_omnimark("src/omnicompany/packages/domains/gameplay_system/foo.py")
        assert not _check_missing_omnimark(ctx)

    def test_no_trigger_outside_packages(self):
        """runtime/ 下的文件不受 OMNI-001 约束。"""
        ctx = make_ctx("src/omnicompany/runtime/runner.py", omnimark=None)
        assert not _check_missing_omnimark(ctx)

    def test_exempt_init_py(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/__init__.py", omnimark=None)
        assert not _check_missing_omnimark(ctx)

    def test_exempt_graveyard(self):
        ctx = make_ctx("src/omnicompany/packages/_graveyard/old.py", omnimark=None)
        assert not _check_missing_omnimark(ctx)

    def test_exempt_vendored(self):
        ctx = make_ctx("src/omnicompany/packages/vendors/some_vendor/vendor.py", omnimark=None)
        assert not _check_missing_omnimark(ctx)

    def test_no_trigger_non_python(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/config.yaml",
                       content="key: value\n", omnimark=None)
        assert not _check_missing_omnimark(ctx)

    def test_no_trigger_empty_content(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content="", omnimark=None)
        assert not _check_missing_omnimark(ctx)

    def test_no_trigger_none_content(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content=None, omnimark=None)
        assert not _check_missing_omnimark(ctx)


# ════════════════════════════════════════════════════════════════
# OMNI-002: business-in-framework
# ════════════════════════════════════════════════════════════════

class TestOMNI002:
    """业务代码散落在 runtime/ 框架层根目录。"""

    def test_triggers_for_unknown_runtime_file(self):
        ctx = make_ctx("src/omnicompany/runtime/my_business.py")
        assert _check_business_in_framework(ctx)

    def test_exempt_legal_runtime_files(self):
        # agent_v2.py 已移除: 违反 2026-04-18 命名铁律 "文件名不得挂版本后缀"
        legal = [
            "runner.py", "router.py", "llm.py", "session.py",
            "agent_loop.py", "hooks.py", "db_access.py",
            "tools.py", "nodes.py", "__init__.py",
        ]
        for fname in legal:
            ctx = make_ctx(f"src/omnicompany/runtime/{fname}")
            assert not _check_business_in_framework(ctx), \
                f"{fname} 应该被豁免"

    def test_no_trigger_in_packages(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py")
        assert not _check_business_in_framework(ctx)

    def test_no_trigger_in_runtime_subdir(self):
        """runtime/ 子目录（非根目录）不触发。"""
        ctx = make_ctx("src/omnicompany/runtime/nodes/pain.py")
        assert not _check_business_in_framework(ctx)

    def test_no_trigger_non_python(self):
        ctx = make_ctx("src/omnicompany/runtime/my_file.yaml",
                       content="key: value\n")
        assert not _check_business_in_framework(ctx)


# ════════════════════════════════════════════════════════════════
# OMNI-003: bypass-llm-client
# ════════════════════════════════════════════════════════════════

class TestOMNI003:
    """直接 import anthropic/openai，绕过 LLMClient。"""

    def test_triggers_on_import_anthropic(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content="import anthropic\nclient = anthropic.Anthropic()\n")
        assert _check_direct_llm_import(ctx)

    def test_triggers_on_from_anthropic(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content="from anthropic import Anthropic\n")
        assert _check_direct_llm_import(ctx)

    def test_triggers_on_import_openai(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content="import openai\n")
        assert _check_direct_llm_import(ctx)

    def test_triggers_on_from_openai(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content="from openai import OpenAI\n")
        assert _check_direct_llm_import(ctx)

    @pytest.mark.parametrize("content", [
        "import openai_codex_sdk\n",
        "from openai_codex_sdk import Codex\n",
    ])
    def test_no_trigger_on_openai_prefixed_package(self, content):
        ctx = make_ctx("src/omnicompany/dashboard/ccdaemon/providers/codex.py",
                       content=content)
        assert not _check_direct_llm_import(ctx)

    def test_no_trigger_in_comment(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content="# import anthropic  # 不要这样做\nx = 1\n")
        assert not _check_direct_llm_import(ctx)

    def test_no_trigger_in_docstring(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py",
                       content='"""示例: import anthropic"""\nx = 1\n')
        assert not _check_direct_llm_import(ctx)

    def test_exempt_runtime_llm(self):
        """runtime/llm.py 自身被豁免。"""
        ctx = make_ctx("src/omnicompany/runtime/llm.py",
                       content="import anthropic\nclient = anthropic.Anthropic()\n")
        assert not _check_direct_llm_import(ctx)

    def test_exempt_tests(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/tests/test_foo.py",
                       content="import anthropic\n")
        assert not _check_direct_llm_import(ctx)

    def test_exempt_graveyard(self):
        ctx = make_ctx("src/omnicompany/_graveyard/old.py",
                       content="import anthropic\n")
        assert not _check_direct_llm_import(ctx)

    def test_exempt_archive(self):
        ctx = make_ctx("scripts/_archive_agent_loop/old_script.py",
                       content="import anthropic\n")
        assert not _check_direct_llm_import(ctx)

    def test_exempt_self_patrol(self):
        """patrol.py 源码本身含有检测字符串（作为 Python 字面量），应被豁免。"""
        ctx = make_ctx("src/omnicompany/packages/services/_core/guardian/patrol.py",
                       content='"import anthropic" in content\n')
        assert not _check_direct_llm_import(ctx)

    def test_no_trigger_none_content(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py", content=None)
        assert not _check_direct_llm_import(ctx)


# ════════════════════════════════════════════════════════════════
# OMNI-004: async-router-run
# ════════════════════════════════════════════════════════════════

class TestOMNI004:
    """Router.run() 定义为 async（违反同步协议）。"""

    _ASYNC_RUN = "async def " + "run"
    _FAKE_ASYNC = f"""\
class FooRouter(Router):
    {_ASYNC_RUN}(self, input_data):
        result = do_sync_thing()
        return result
"""

    _REAL_ASYNC = f"""\
class FooRouter(Router):
    {_ASYNC_RUN}(self, input_data):
        result = await some_async_call()
        return result
"""

    def test_triggers_on_fake_async(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/routers/foo.py",
                       content=self._FAKE_ASYNC)
        assert _check_async_router_run(ctx)

    def test_triggers_on_real_async_with_await(self):
        """异步 run 一律报告（无论体内是否有 await）。

        2026-04-18 铁律更新: async run 导致 Doctor AST 信号提取失效，
        违反 LAP 同步协议 — 不再区分真/假异步，全部触发。
        (实现: boundaries.py _check_async_router_run line 104-106)
        """
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/routers/foo.py",
                       content=self._REAL_ASYNC)
        assert _check_async_router_run(ctx)

    def test_no_trigger_sync_run(self):
        content = "class FooRouter(Router):\n    def run(self, input_data):\n        pass\n"
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/routers/foo.py", content=content)
        assert not _check_async_router_run(ctx)

    def test_exempt_runtime_framework(self):
        """runtime/ 里的 Router 基类定义合法，不报。"""
        ctx = make_ctx("src/omnicompany/runtime/router.py",
                       content=self._FAKE_ASYNC)
        assert not _check_async_router_run(ctx)

    def test_exempt_graveyard(self):
        ctx = make_ctx("src/omnicompany/_graveyard/old_router.py",
                       content=self._FAKE_ASYNC)
        assert not _check_async_router_run(ctx)

    def test_no_trigger_without_router_class(self):
        """文件里没有继承 Router 的类，即使有 异步 run 也不报。"""
        content = f"class Foo:\n    {self._ASYNC_RUN}(self):\n        pass\n"
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py", content=content)
        assert not _check_async_router_run(ctx)

    def test_no_trigger_none_content(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py", content=None)
        assert not _check_async_router_run(ctx)


# ════════════════════════════════════════════════════════════════
# OMNI-005: db-outside-data
# ════════════════════════════════════════════════════════════════

class TestOMNI005:
    """.db 文件出现在 data/ 之外。"""

    def test_triggers_on_db_in_root(self):
        ctx = make_ctx("events.db", content=None)
        assert _check_db_outside_data(ctx)

    def test_triggers_on_db_in_src(self):
        ctx = make_ctx("src/omnicompany/semantic_network.db", content=None)
        assert _check_db_outside_data(ctx)

    def test_no_trigger_in_data_dir(self):
        ctx = make_ctx("data/events.db", content=None)
        assert not _check_db_outside_data(ctx)

    def test_no_trigger_in_logs_dir(self):
        """logs/ 目录允许（guardian 日志等）。"""
        ctx = make_ctx("logs/patrol/session.db", content=None)
        assert not _check_db_outside_data(ctx)

    def test_no_trigger_non_db_extension(self):
        ctx = make_ctx("src/omnicompany/config.json", content="{}")
        assert not _check_db_outside_data(ctx)

    def test_triggers_on_nested_db_outside_data(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/game.db", content=None)
        assert _check_db_outside_data(ctx)


# ════════════════════════════════════════════════════════════════
# OMNI-006: temp-script-in-src
# ════════════════════════════════════════════════════════════════

class TestOMNI006:
    """临时脚本混入 src/ 目录。"""

    @pytest.mark.parametrize("filename", [
        "test_foo.py", "scratch_bar.py", "tmp_analysis.py",
        "debug_db.py", "check_db.py", "restore_data.py", "update_schema.py",
    ])
    def test_triggers_on_temp_prefixes(self, filename):
        ctx = make_ctx(f"src/omnicompany/packages/domains/gameplay_system/{filename}")
        assert _check_temp_in_src(ctx), f"{filename} 应触发 OMNI-006"

    def test_no_trigger_outside_src(self):
        ctx = make_ctx("scripts/check_db.py")
        assert not _check_temp_in_src(ctx)

    def test_no_trigger_in_tests_dir(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/tests/test_foo.py")
        assert not _check_temp_in_src(ctx)

    def test_no_trigger_in_graveyard(self):
        ctx = make_ctx("src/omnicompany/_graveyard/test_old.py")
        assert not _check_temp_in_src(ctx)

    def test_no_trigger_normal_name(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/router.py")
        assert not _check_temp_in_src(ctx)

    def test_no_trigger_non_python(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/test_data.json",
                       content="{}")
        assert not _check_temp_in_src(ctx)


# ════════════════════════════════════════════════════════════════
# OMNI-007: stray-config-in-src
# ════════════════════════════════════════════════════════════════

class TestOMNI007:
    """src/ 下非预期的配置/文档文件。"""

    @pytest.mark.parametrize("path", [
        "src/omnicompany/packages/domains/gameplay_system/config.json",
        "src/omnicompany/packages/domains/gameplay_system/spec.yaml",
        "src/omnicompany/packages/domains/gameplay_system/spec.yml",
        "src/omnicompany/packages/domains/gameplay_system/NOTES.md",
    ])
    def test_triggers_on_stray_config(self, path):
        ctx = make_ctx(path, content="")
        assert _check_stray_config_in_src(ctx), f"{path} 应触发 OMNI-007"

    @pytest.mark.parametrize("filename", ["README.md", "CHANGELOG.md", "py.typed"])
    def test_exempt_allowed_files(self, filename):
        ctx = make_ctx(f"src/omnicompany/packages/domains/gameplay_system/{filename}", content="")
        assert not _check_stray_config_in_src(ctx)

    def test_no_trigger_outside_src(self):
        ctx = make_ctx("docs/design.md", content="")
        assert not _check_stray_config_in_src(ctx)

    def test_no_trigger_python_file(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/foo.py")
        assert not _check_stray_config_in_src(ctx)

    @pytest.mark.parametrize("filename", ["package.json", "package-lock.json", "tsconfig.json"])
    def test_exempt_dashboard_extension_node_project_files(self, filename):
        ctx = make_ctx(
            f"src/omnicompany/dashboard/extensions/vscode-chat-sidebar/{filename}",
            content="{}",
        )
        assert not _check_stray_config_in_src(ctx)


# ════════════════════════════════════════════════════════════════
# RuleEngine.evaluate()
# ════════════════════════════════════════════════════════════════

class TestRuleEngine:
    """规则引擎集成测试。"""

    def test_no_violations_on_clean_file(self):
        # routers.py 路径合规（OMNI-024），需含 DESCRIPTION + FORMAT_IN/OUT（OMNI-020）
        content = (
            "class FooRouter(Router):\n"
            '    DESCRIPTION = "Takes input data and returns processed output for downstream"\n'
            '    FORMAT_IN = "SomeInputFormat"\n'
            '    FORMAT_OUT = "SomeOutputFormat"\n'
            "    def run(self, ctx):\n"
            "        return ctx\n"
        )
        ctx = ctx_with_omnimark("src/omnicompany/packages/domains/gameplay_system/routers.py", content=content)
        engine = RuleEngine()
        violations = engine.evaluate([ctx])
        assert violations == [], f"预期无违规，实际: {[v.rule_id for v in violations]}"

    def test_multiple_violations_on_single_file(self):
        """单个文件可触发多条规则。"""
        content = "import anthropic\n"  # OMNI-003
        # + 这个文件在 runtime/ 根目录（OMNI-002）
        ctx = make_ctx("src/omnicompany/runtime/my_biz.py", content=content)
        engine = RuleEngine()
        violations = engine.evaluate([ctx])
        rule_ids = {v.rule_id for v in violations}
        assert "OMNI-002" in rule_ids
        assert "OMNI-003" in rule_ids

    def test_multiple_files(self):
        files = [
            make_ctx("src/omnicompany/packages/domains/gameplay_system/scratch_foo.py"),  # OMNI-006
            make_ctx("src/omnicompany/runtime/biz_logic.py"),           # OMNI-002
            make_ctx("events.db", content=None),                        # OMNI-005
        ]
        engine = RuleEngine()
        violations = engine.evaluate(files)
        rule_ids = {v.rule_id for v in violations}
        assert "OMNI-006" in rule_ids
        assert "OMNI-002" in rule_ids
        assert "OMNI-005" in rule_ids

    def test_ticket_ids_are_unique(self):
        files = [
            make_ctx("src/omnicompany/packages/domains/gameplay_system/scratch_a.py"),
            make_ctx("src/omnicompany/packages/domains/gameplay_system/scratch_b.py"),
            make_ctx("src/omnicompany/runtime/biz_a.py"),
        ]
        engine = RuleEngine()
        violations = engine.evaluate(files)
        ticket_ids = [v.ticket_id for v in violations]
        assert len(ticket_ids) == len(set(ticket_ids)), "Ticket ID 应全局唯一"

    def test_counter_increments_across_calls(self):
        """多次调用 evaluate()，ticket 计数器不重置。"""
        engine = RuleEngine()
        v1 = engine.evaluate([make_ctx("src/omnicompany/runtime/biz_a.py")])
        v2 = engine.evaluate([make_ctx("src/omnicompany/runtime/biz_b.py")])
        assert v1[0].ticket_id != v2[0].ticket_id

    def test_rule_exception_does_not_abort_others(self):
        """单条规则抛异常，其他规则仍运行。"""
        from omnicompany.packages.services._core.guardian import GuardianRule, RuleEngine

        def bad_rule(ctx):
            raise RuntimeError("boom")

        broken = GuardianRule(
            id="TEST-BAD",
            name="bad",
            severity="HIGH",
            description="always crashes",
            check=bad_rule,
            disposition=["warn"],
            message_template="{path}",
        )
        omni006 = next(r for r in RULES if r.id == "OMNI-006")
        engine = RuleEngine(rules=[broken, omni006])  # broken + OMNI-006
        files = [make_ctx("src/omnicompany/packages/domains/gameplay_system/scratch_test.py")]
        violations = engine.evaluate(files)
        # broken 崩了，OMNI-006 应该还报
        assert any(v.rule_id == "OMNI-006" for v in violations)

    def test_violation_message_contains_path(self):
        ctx = make_ctx("src/omnicompany/packages/domains/gameplay_system/scratch_foo.py")
        engine = RuleEngine()
        violations = engine.evaluate([ctx])
        v = next(v for v in violations if v.rule_id == "OMNI-006")
        assert "src/omnicompany/packages/domains/gameplay_system/scratch_foo.py" in v.message

    def test_violation_severity_matches_rule(self):
        ctx = make_ctx("src/omnicompany/runtime/biz.py")
        engine = RuleEngine()
        violations = engine.evaluate([ctx])
        v = next(v for v in violations if v.rule_id == "OMNI-002")
        assert v.severity == "CRITICAL"

    def test_deleted_file_skips_content_rules(self):
        """change_type=D 的文件内容为 None，内容相关规则不应报。"""
        ctx = make_ctx(
            "src/omnicompany/packages/domains/gameplay_system/foo.py",
            content=None,
            change_type="D",
        )
        engine = RuleEngine()
        violations = engine.evaluate([ctx])
        # OMNI-001/003/004 都需要 content，不应触发
        assert not any(v.rule_id in {"OMNI-001", "OMNI-003", "OMNI-004"}
                       for v in violations)

    def test_deleted_versioned_filename_is_remediation_not_violation(self):
        ctx = make_ctx(
            "tests/dashboard/test_boss_sight_v2_10_material_registry.py",
            content=None,
            change_type="D",
        )

        assert not _check_versioned_filename(ctx)

    def test_manual_evidence_parse_noqa_exempts_external_json(self):
        ctx = make_ctx(
            "tests/agent_tools/test_external_agent_workers.py",
            content=(
                "# noqa-OMNI-080: parses external JSON fixtures, not LLM output\n"
                "import json\n"
                "PROMPT = '```json\\n{}\\n```'\n"
                "def f(text):\n"
                "    return json.loads(text)\n"
            ),
        )

        assert not _check_manual_evidence_parse(ctx)
