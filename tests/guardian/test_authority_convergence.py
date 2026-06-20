from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.guardian import FileContext, RULES
from omnicompany.packages.services._core.guardian.rules.authority_convergence import (
    _check_authority_confirmation_not_active,
    _check_autonomous_rules_not_bound,
    _check_required_surface_missing_authority,
)


AUTHORITY_PATH = (
    "docs/plans/agent-framework/[2026-06-13]LLM-CALL-UNIFICATION/"
    "authority-confirmation.md"
)
AUTONOMOUS_PATH = (
    "docs/plans/agent-framework/[2026-06-13]LLM-CALL-UNIFICATION/"
    "autonomous-execution-rules.md"
)


def _ctx(path: str, content: str) -> FileContext:
    return FileContext(
        path=path,
        abs_path=f"E:/fake/{path}",
        change_type="M",
        content=content,
        omnimark=None,
    )


def test_authority_confirmation_pending_is_violation():
    content = '<!-- [OMNI] status=pending-confirmation -->\n# 唯一权威集中确认表\n'
    assert _check_authority_confirmation_not_active(_ctx(AUTHORITY_PATH, content))


def test_authority_confirmation_active_with_required_decisions_passes():
    content = """
本表是本批设施统一工作的最高决断表
MaterialDispatcher 转正
protocol.Format + FormatRegistry.register
runtime/llm/structured.py::call_json
runtime/llm/batch.py
EventBus 是 agent 事件权威记录面
AuditTowWorker
"""
    assert not _check_authority_confirmation_not_active(_ctx(AUTHORITY_PATH, content))


def test_autonomous_rules_must_bind_authority_and_guard():
    bad = "同一时刻只允许一个实施块\n真实路径测试\n"
    assert _check_autonomous_rules_not_bound(_ctx(AUTONOMOUS_PATH, bad))

    good = (
        "authority-confirmation.md\nautonomous-execution-rules.md\n"
        "同一时刻只允许一个实施块\n真实路径测试\n"
        "omni guardian patrol --rules=OMNI-093a,OMNI-093b\nOMNI-093\n"
    )
    assert not _check_autonomous_rules_not_bound(_ctx(AUTONOMOUS_PATH, good))


def test_required_distributed_surfaces_must_anchor_both_files():
    bad = "# LLM 基础设施\n唯一权威: runtime/llm/structured.py\n"
    assert _check_required_surface_missing_authority(
        _ctx("docs/standards/cli/llm_infrastructure.md", bad)
    )

    good = (
        "# LLM 基础设施\n"
        "见 authority-confirmation.md 与 autonomous-execution-rules.md。\n"
    )
    assert not _check_required_surface_missing_authority(
        _ctx("docs/standards/cli/llm_infrastructure.md", good)
    )


def test_content_none_never_false_fires():
    """full_scan 对 src/ 下 .md 不读 content(=None)→ 不能凭空判违规(此前 093c 误报 HIGH)。"""
    none_ctx = lambda path: FileContext(  # noqa: E731
        path=path, abs_path=f"E:/fake/{path}", change_type="M", content=None, omnimark=None
    )
    assert not _check_authority_confirmation_not_active(none_ctx(AUTHORITY_PATH))
    assert not _check_autonomous_rules_not_bound(none_ctx(AUTONOMOUS_PATH))
    assert not _check_required_surface_missing_authority(
        none_ctx("src/omnicompany/packages/services/_core/guardian/README.md")
    )


def test_omni_093_deterministic_rules_registered_093d_demoted():
    """093a/b/c 是确定性兜底, 仍注册并阻断; 093d(语义判断)已下沉 doc_steward, 不再是阻断规则。"""
    ids = {rule.id for rule in RULES}
    from omnicompany.packages.services._core.guardian.hook_installer import PRE_COMMIT_TEMPLATE

    for rule_id in ("OMNI-093a", "OMNI-093b", "OMNI-093c"):
        assert rule_id in ids
        assert rule_id in PRE_COMMIT_TEMPLATE

    assert "OMNI-093d" not in ids  # 已摘除: 语义"另立权威"判断改由 doc_steward 承担
    assert "OMNI-093d" not in PRE_COMMIT_TEMPLATE
