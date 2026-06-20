# [OMNI] origin=claude-code domain=tests/guardian ts=2026-04-24T00:00:00Z type=test
"""OMNI-070~073 合规预防 (compliance_prevention) 粗筛回归.

验证粗筛准确度 (粗筛只负责"宁多报候选, 让 LLM 筛", 但不应误判合法入口本身).
"""
from __future__ import annotations

from omnicompany.packages.services._core.guardian.rules._base import FileContext
from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
    _check_direct_llmclient_in_class,
    _check_old_agent_node_loop_inherit,
    _check_packages_flow_outside_worker,
    _check_orphan_module,
    _check_scripts_business_logic,
    _FLOW_OUTSIDE_WORKER_EXEMPTIONS,
    _ORPHAN_MODULE_EXEMPTIONS,
    _PATH_EXEMPTIONS,
)
from omnicompany.packages.services._core.guardian.rules.observability import (
    _check_router_bypass_bus,
)


def _ctx(path: str, content: str) -> FileContext:
    return FileContext(path=path, abs_path=path, change_type="M", content=content)


# ── OMNI-070 · LLMClient in class ───────────────────────────


def test_omni070_class_with_llmclient_hit():
    src = """\
from omnicompany.runtime.llm.llm import LLMClient

class FooRouter:
    def run(self, x):
        client = LLMClient(role="runtime_main")
        return client.call(messages=[])
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/routers.py", src)
    assert _check_direct_llmclient_in_class(ctx) is True


def test_omni070_no_class_no_hit():
    """模块级 LLMClient 调用 (非 class 内) 不报 OMNI-070, 由 OMNI-072 管."""
    src = """\
from omnicompany.runtime.llm.llm import LLMClient
client = LLMClient(role="x")
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/util.py", src)
    assert _check_direct_llmclient_in_class(ctx) is False


def test_omni070_no_llmclient_no_hit():
    src = "class Foo: pass\n"
    ctx = _ctx("src/omnicompany/packages/domains/foo/bar.py", src)
    assert _check_direct_llmclient_in_class(ctx) is False


def test_omni070_exempts_runtime():
    """runtime/ 整层是基础设施, 豁免."""
    src = "class X:\n    def foo(self):\n        return LLMClient()\n"
    ctx = _ctx("src/omnicompany/runtime/llm/llm.py", src)
    assert _check_direct_llmclient_in_class(ctx) is False


def test_omni070_exempts_services_agent():
    src = "class X:\n    def foo(self):\n        return LLMClient()\n"
    ctx = _ctx(
        "src/omnicompany/packages/services/agent/routers/llm_call.py", src
    )
    assert _check_direct_llmclient_in_class(ctx) is False


def test_omni070_exempts_core_agent_service_home():
    src = "class X:\n    def foo(self):\n        return LLMClient()\n"
    ctx = _ctx(
        "src/omnicompany/packages/services/_core/agent/routers/llm_call.py", src
    )
    assert _check_direct_llmclient_in_class(ctx) is False


def test_t13_exempts_eventbus_observable_evolution_orchestration():
    src = """\
from omnicompany.runtime.llm.llm import LLMClient

class EvolutionOrchestrator:
    def __init__(self):
        self._llm = LLMClient()

    async def run(self):
        return await self._diagnosis_agent.run({})
"""
    for path in (
        "src/omnicompany/packages/services/_core/evolution/workflow/orchestrator.py",
        "src/omnicompany/packages/services/_core/evolution/workflow/experiment_runner.py",
    ):
        ctx = _ctx(path, src)
        assert path in _PATH_EXEMPTIONS
        assert _check_direct_llmclient_in_class(ctx) is False
        assert _check_packages_flow_outside_worker(ctx) is False
        assert _check_orphan_module(ctx) is False


def test_t13_evolution_orchestrator_router_run_is_eventbus_observable():
    src = """\
class EvolutionOrchestrator:
    def run(self):
        self._diagnosis_agent.run({})
        self._experiment_runner.run({})
"""
    path = "src/omnicompany/packages/services/_core/evolution/workflow/orchestrator.py"
    assert _check_router_bypass_bus(_ctx(path, src)) is False

    sibling = "src/omnicompany/packages/services/_core/evolution/workflow/new_orchestrator.py"
    assert _check_router_bypass_bus(_ctx(sibling, src)) is True


def test_router_bypass_rule_does_not_report_its_own_scanner_source():
    src = """\
_DIRECT_RUN_RE = r"self._router.run({})"
def check():
    return "self._other.run({})"
"""
    path = "src/omnicompany/packages/services/_core/guardian/rules/observability.py"
    assert _check_router_bypass_bus(_ctx(path, src)) is False


def test_omni070_skips_archive():
    src = "class X:\n    def f(self): LLMClient()\n"
    ctx = _ctx(
        "src/omnicompany/packages/services/foo/_archive/old.py", src
    )
    assert _check_direct_llmclient_in_class(ctx) is False


def test_omni070_only_packages_path():
    """非 packages/ 路径不报 (scripts/ 由 073 管)."""
    src = "class X:\n    def f(self): LLMClient()\n"
    ctx = _ctx("scripts/foo.py", src)
    assert _check_direct_llmclient_in_class(ctx) is False


# ── OMNI-071 · 旧 AgentNodeLoop 继承 ───────────────────────


def test_omni071_old_inherit_hit():
    src = """\
from omnicompany.runtime.agent.agent_node_loop import AgentNodeLoop

class FooAgent(AgentNodeLoop):
    pass
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/agent.py", src)
    assert _check_old_agent_node_loop_inherit(ctx) is True


def test_omni071_old_inherit_with_alias():
    src = """\
from omnicompany.runtime.agent.agent_node_loop import AgentNodeLoop as ANL

class FooAgent(ANL):
    pass
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/agent.py", src)
    assert _check_old_agent_node_loop_inherit(ctx) is True


def test_omni071_new_path_not_hit():
    src = """\
from omnicompany.packages.services.agent import AgentNodeLoop

class FooAgent(AgentNodeLoop):
    pass
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/agent.py", src)
    assert _check_old_agent_node_loop_inherit(ctx) is False


def test_omni071_import_no_inherit_no_hit():
    """import 但不继承也不报 (可能只是 type hint)."""
    src = """\
from omnicompany.runtime.agent.agent_node_loop import AgentNodeLoop

def factory() -> AgentNodeLoop:
    pass
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/factory.py", src)
    assert _check_old_agent_node_loop_inherit(ctx) is False


def test_omni071_exempts_guardian_judge_agent():
    src = """\
from omnicompany.runtime.agent.agent_node_loop import AgentNodeLoop

class GuardianAgent(AgentNodeLoop):
    pass
"""
    ctx = _ctx(
        "src/omnicompany/packages/services/guardian/judge_agent.py", src
    )
    assert _check_old_agent_node_loop_inherit(ctx) is False


def test_omni071_exempts_runtime():
    src = """\
from omnicompany.runtime.agent.agent_node_loop import AgentNodeLoop

class RuntimeFallback(AgentNodeLoop):
    pass
"""
    ctx = _ctx("src/omnicompany/runtime/info_audit/fallback.py", src)
    assert _check_old_agent_node_loop_inherit(ctx) is False


# ── OMNI-072 · packages 流程不走 Worker ─────────────────────


def test_omni072_module_with_llmclient_no_class_hit():
    src = """\
from omnicompany.runtime.llm.llm import LLMClient

def my_flow():
    c = LLMClient(role="x")
    return c.call(messages=[])
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/flow.py", src)
    assert _check_packages_flow_outside_worker(ctx) is True


def test_omni072_with_worker_class_no_hit():
    """文件含 Worker 子类, LLMClient 用法属类内部 (OMNI-070 管), 本规则不报."""
    src = """\
from omnicompany.runtime.llm.llm import LLMClient
from omnicompany.packages.services.omnicompany import Worker

class FooWorker(Worker):
    def run(self, x):
        return LLMClient(role="x").call(messages=[])
"""
    ctx = _ctx("src/omnicompany/packages/domains/foo/workers/foo.py", src)
    assert _check_packages_flow_outside_worker(ctx) is False


def test_omni072_no_llmclient_no_hit():
    src = "def helper(): pass\n"
    ctx = _ctx("src/omnicompany/packages/domains/foo/util.py", src)
    assert _check_packages_flow_outside_worker(ctx) is False


def test_omni072_skip_structural_files():
    src = """\
from omnicompany.runtime.llm.llm import LLMClient
LLMClient()
"""
    for fname in ("__init__.py", "formats.py", "team.py", "materials.py"):
        ctx = _ctx(f"src/omnicompany/packages/domains/foo/{fname}", src)
        assert _check_packages_flow_outside_worker(ctx) is False, f"{fname} should skip"


def test_omni072_exempts_only_t4_structured_chat_adapter_path():
    src = """\
from omnicompany.runtime.llm.llm import LLMClient

def llm_structured_chat():
    return LLMClient.for_role("runtime_main")
"""
    path = "src/omnicompany/packages/domains/voxel_engine/item/_llm_helpers.py"
    assert _FLOW_OUTSIDE_WORKER_EXEMPTIONS == (path,)
    assert _check_packages_flow_outside_worker(_ctx(path, src)) is False

    sibling = "src/omnicompany/packages/domains/voxel_engine/item/_llm_helper_probe.py"
    assert _check_packages_flow_outside_worker(_ctx(sibling, src)) is True


# ── OMNI-073 · scripts 业务逻辑 ─────────────────────────────


def test_omni073_scripts_with_llmclient_hit():
    src = "from omnicompany.runtime.llm.llm import LLMClient\nLLMClient()\n"
    ctx = _ctx("scripts/run_evolution.py", src)
    assert _check_scripts_business_logic(ctx) is True


def test_omni073_scripts_with_domain_import_hit():
    src = "from omnicompany.packages.domains.gameplay_system.foo import bar\n"
    ctx = _ctx("scripts/run_gameplay_system.py", src)
    assert _check_scripts_business_logic(ctx) is True


def test_omni073_scripts_default_send_to_llm():
    """2026-04-24 plan §十二 收紧: scripts/ 下任何 .py 默认送 LLM 复核,
    不再"无 LLM 调用就豁免" — 一次性垃圾不该堆积."""
    src = "import os\nprint('hello')\n"
    ctx = _ctx("scripts/hello.py", src)
    assert _check_scripts_business_logic(ctx) is True


def test_omni073_persistent_script_marker_exempts():
    """脚本头含 `# OMNI-PERSISTENT-SCRIPT` 明示长期存在 → 不送 LLM 复核."""
    src = "# OMNI-PERSISTENT-SCRIPT owner=foo purpose=ci-check\nprint('ok')\n"
    ctx = _ctx("scripts/ci_check.py", src)
    assert _check_scripts_business_logic(ctx) is False


def test_omni073_non_scripts_no_hit():
    src = "from omnicompany.runtime.llm.llm import LLMClient\nLLMClient()\n"
    ctx = _ctx("src/omnicompany/packages/domains/foo/x.py", src)
    assert _check_scripts_business_logic(ctx) is False


# ── OMNI-074 · 死代码/孤儿模块 ─────────────────────────────


def test_omni074_worker_file_default_send_to_llm():
    """packages/ 下非协议 .py 默认送 LLM 复核."""
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
        _check_orphan_module,
    )
    src = "def some_helper(): pass\n"
    ctx = _ctx("src/omnicompany/packages/domains/foo/helper.py", src)
    assert _check_orphan_module(ctx) is True


def test_omni074_protocol_file_skipped():
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
        _check_orphan_module,
    )
    for fname in ("__init__.py", "formats.py", "team.py", "materials.py",
                  "pipeline.py", "run.py", "routers.py"):
        ctx = _ctx(f"src/omnicompany/packages/domains/foo/{fname}", "content\n")
        assert _check_orphan_module(ctx) is False, f"{fname} 应作为协议文件跳过"


def test_omni074_skips_non_packages_path():
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
        _check_orphan_module,
    )
    ctx = _ctx("src/omnicompany/runtime/foo.py", "x = 1\n")
    assert _check_orphan_module(ctx) is False


def test_omni074_skips_archive_vendors():
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
        _check_orphan_module,
    )
    ctx = _ctx("src/omnicompany/packages/services/foo/_archive/old.py", "x = 1\n")
    assert _check_orphan_module(ctx) is False


def test_omni074_exempts_guardian_rule_plugins():
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
        _check_orphan_module,
    )

    ctx = _ctx(
        "src/omnicompany/packages/services/_core/guardian/rules/authority_convergence.py",
        "RULES = []\n",
    )
    assert _check_orphan_module(ctx) is False


def test_omni074_exempts_omnicompany_material_blackboard_core():
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import (
        _check_orphan_module,
    )

    for path in (
        "src/omnicompany/packages/services/_core/omnicompany/material_dispatcher.py",
        "src/omnicompany/packages/services/_core/omnicompany/material_events.py",
    ):
        ctx = _ctx(path, "def active_entrypoint(): pass\n")
        assert _check_orphan_module(ctx) is False, path


# ── 元: 规则注册到聚合 RULES ────────────────────────────────


def test_omni074_exempts_core_agent_spawn_surface():
    path = "src/omnicompany/packages/services/_core/agent/spawn_surface.py"
    assert path.startswith(_PATH_EXEMPTIONS)
    ctx = _ctx(path, "def active_entrypoint(): pass\n")
    assert _check_orphan_module(ctx) is False


def test_omni074_exempts_t4_structured_llm_active_entrypoints():
    for path in _ORPHAN_MODULE_EXEMPTIONS:
        ctx = _ctx(path, "def active_entrypoint(): pass\n")
        assert _check_orphan_module(ctx) is False, path


def test_omni074_exempts_t6_publish_pipeline_article_author():
    path = "src/omnicompany/packages/services/_authoring/publish_pipeline/workers/article_author.py"
    assert path in _ORPHAN_MODULE_EXEMPTIONS
    ctx = _ctx(path, "def active_entrypoint(): pass\n")
    assert _check_orphan_module(ctx) is False


def test_t13_exempts_event_bridge_and_seven_tuple_batch_tool_from_orphan_review():
    for path in (
        "src/omnicompany/packages/services/_core/evolution/workflow/events.py",
        "src/omnicompany/packages/domains/gameplay_system/ux/seven_tuple/runners/batch_runner.py",
    ):
        assert path in _ORPHAN_MODULE_EXEMPTIONS
        ctx = _ctx(path, "def active_entrypoint(): pass\n")
        assert _check_orphan_module(ctx) is False


def test_omni074_t4_exemption_is_not_directory_wide():
    for path in (
        "src/omnicompany/packages/domains/voxel_engine/routers/new_probe.py",
        "src/omnicompany/packages/domains/creative_content/routers/new_probe.py",
        "src/omnicompany/packages/services/_governance/new_probe.py",
    ):
        ctx = _ctx(path, "def unregistered_module(): pass\n")
        assert _check_orphan_module(ctx) is True, path


def test_rules_registered_in_main_aggregate():
    from omnicompany.packages.services._core.guardian.rules import RULES as ALL_RULES
    ids = {r.id for r in ALL_RULES}
    for expected in ("OMNI-070", "OMNI-071", "OMNI-072", "OMNI-073", "OMNI-074"):
        assert expected in ids, f"{expected} 未注册到主 RULES 聚合"


def test_all_compliance_rules_are_needs_judgment():
    """plan §三.1: 100% 违规才 absolute. 本族容易错杀, 必须全 needs_judgment."""
    from omnicompany.packages.services._core.guardian.rules.compliance_prevention import RULES
    for r in RULES:
        assert r.certainty == "needs_judgment", (
            f"{r.id} 应该是 needs_judgment, 不是 absolute"
        )
