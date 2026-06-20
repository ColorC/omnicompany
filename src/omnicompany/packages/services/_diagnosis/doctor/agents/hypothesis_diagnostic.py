# [OMNI] origin=ai-ide domain=services/_diagnosis/doctor/agents ts=2026-05-05T22:45:00Z type=router status=skeleton agent=ai-ide-current
# [OMNI] summary="HypothesisDiagnosticAgent V0 骨架 — 拿假设库的一组 yaml 假设 + 待诊断对象, LLM 自然语言判对象违反/满足哪些假设"
# [OMNI] why="step 9.4 复用 SpecDiagnosticAgent 模式立第二种诊断方法. 验证 'submit_verdict 通用工具 + 自然语言评论' 模式跨方法可复制"
# [OMNI] tags=agent,configurable,doctor,hypothesis,skeleton,phase-2-step-9-4
# [OMNI] material_id="material:diagnosis.doctor.agents.hypothesis_diagnostic.skeleton.py"
"""HypothesisDiagnosticAgent · 假设型诊断 (V0 骨架)

跟 SpecDiagnosticAgent 同形态, 区别在判定来源:
- spec 型: 拿规范文档原文 (docs/standards/concepts/) 让 LLM 读规范 + 对象 → 判
- hypothesis 型: 拿一组假设 yaml 实例 (data/services/doctor/hypotheses/) → 每条假设独立判对象违反/满足

设计:
- 输入: doctor.hypothesis_diagnosis.request (含 target_entity_path / target_entity_kind / applicable_hypothesis_paths 假设 yaml 路径列表)
- 工作: agent 用 read_file 读每条假设 yaml + 待诊断对象代码, 自然语言判
- 输出: doctor.hypothesis_diagnosis.verdict (含 list[finding with finding_kind=hypothesis] + narrative)

工具集 = SpecDiagnosticAgent 同 (read_file/glob/grep/list_dir/write_finding/submit_verdict).
共用 submit_verdict 通用工具 (consulted_references 字段填假设 yaml path).

## 待做 (V0 骨架 → V1)

[ ] **dogfood**: 拿 sample_hypothesis_H-2026-05-05-001.yaml 跑诊断 doctor 一个 worker, 看产 finding 质量
[ ] **假设库管理**: 当前从外部传 paths, 后续应从 data/services/doctor/hypotheses/ 自动 enumerate
[ ] **HypothesisDeriverAgent (新立)**: 拿 standards/plan/code 派生新假设 (假设增量库)
[ ] **测试基线**: 现 () 占位, 至少 1 红 1 绿
[ ] **DESIGN.md 更**: doctor/DESIGN.md 加 HypothesisDiagnosticAgent 段
"""
from __future__ import annotations

# 保险: import 触发 doctor.tools 注册业务工具到 TOOL_REGISTRY
from omnicompany.packages.services._diagnosis.doctor import tools  # noqa: F401

from omnicompany.packages.services._core.agent import (
    AgentSpec,
    ConfigurableAgent,
)
from omnicompany.packages.services._diagnosis.doctor.agents.spec_diagnostic import (
    _build_spec_verdict_extractor,
)


HYPOTHESIS_DIAGNOSTIC_SPEC = AgentSpec(

    # ── 1. 注册信息 ─────────────────────────────────────
    id="doctor.hypothesis_diagnostic",
    name="HypothesisDiagnosticAgent",
    domain="doctor",
    parent_worker_kind="agent",
    registry_namespace="services.agent.instances",

    # ── 2. LLM 配置 ────────────────────────────────────
    llm_model="qwen-3.6-plus",
    llm_temperature=0.2,
    llm_max_tokens=16000,
    llm_max_turns=1000,
    llm_timeout_seconds=600,

    # ── 3. 产出 material ─────────────────────────────────
    output_materials=(
        "doctor.hypothesis_diagnosis.verdict",
        "doctor.health_finding",
    ),
    primary_output="doctor.hypothesis_diagnosis.verdict",

    # ── 4. 触发 material ─────────────────────────────────
    trigger_materials=(
        "doctor.hypothesis_diagnosis.request",
    ),
    trigger_mode="any",

    # ── 5. 响应范围 ─────────────────────────────────────
    accepted_input_materials=(
        "doctor.hypothesis_diagnosis.request",
    ),
    forbidden_input_materials=(
        "doctor.hypothesis_diagnosis.verdict",
        "doctor.health_finding",
    ),

    # ── 6. 用户输入 ─────────────────────────────────────
    user_input_template=(
        "请用以下假设诊断对象 {target_entity_path} (类型 {target_entity_kind}).\n\n"
        "假设 yaml 路径 (一组): {applicable_hypothesis_paths}\n\n"
        "做法:\n"
        "1. 用 read_file 读每条假设 yaml (含 statement / motivation / evidence_query)\n"
        "2. 用 read_file / glob / grep 读待诊断对象代码\n"
        "3. 自然语言判对象是否违反/满足每条假设, 给具体证据\n"
        "4. 每条违规或值得记的合规 case 走 write_finding (finding_kind=hypothesis, applied_hypotheses=[假设 id])\n"
        "5. 调 submit_verdict 提交完整 verdict (consulted_references 填实际查的假设 yaml path)"
    ),
    user_input_required_fields=(
        "target_entity_path",
        "target_entity_kind",
        "applicable_hypothesis_paths",
    ),

    # ── 7. 系统 prompt ─────────────────────────────────
    prompt_path="src/omnicompany/packages/services/_diagnosis/doctor/agents/hypothesis_diagnostic_prompt.md",
    prompt_substitutions={
        "agent_role": "假设型诊断 agent",
        "primary_output": "doctor.hypothesis_diagnosis.verdict",
    },

    # ── 8. 工具列表 ────────────────────────────────────
    tools=(
        "read_file",
        "glob",
        "grep",
        "list_dir",
        "write_finding",
        "submit_verdict",
    ),

    # ── 9. 工作区 ─────────────────────────────────────
    workspace={
        "name": "doctor.hypothesis_diagnostic",
        "write_prefixes": (
            "data/services/doctor/findings/{task_id}/",
            "data/services/doctor/_notes/{task_id}/",
        ),
        "read_prefixes": "READ_ANY",
        "bash_cwd_prefixes": ("",),
    },

    # ── 10-11. gates / context_triggers ─ V0 空 ─────────
    gates=(),
    context_triggers=(),

    # ── 12. 含自定义代码 (override hooks 跟 SpecDiagnosticAgent 同) ──
    allow_custom_code=True,

    # ── 13. 测试基线 ─ 2026-05-06 self_audit §B-2 修复 ─────────
    test_baseline={
        "green_samples": (
            "src/omnicompany/packages/services/_utility/csv_to_md/workers/csv_reader.py",
        ),
        "red_samples": (
            "src/omnicompany/packages/services/_diagnosis/doctor/_test_fixtures/red_workers/red_minimal_worker.py",
        ),
        "gradient_samples": (),
        # 红绿对比脚本: _scratch/dogfood_red_green_hypothesis.py
        # 实测 (2026-05-06): GREEN/RED narrative 双向区分 (满足/违反). H-2026-05-05-001 在 red applied 命中
        "_baseline_validated_at": "2026-05-06",
        "_baseline_overall": "PASS",
    },
)


class HypothesisDiagnosticAgent(ConfigurableAgent):
    """假设型诊断 agent — 拿假设 yaml + 待诊断对象, LLM 判违反/满足.

    复用 SpecDiagnosticAgent 的 verdict 提取逻辑 (_build_spec_verdict_extractor),
    因为 spec 跟 hypothesis 共用 submit_verdict 通用工具 + 同 verdict 形态.
    """

    SPEC = HYPOTHESIS_DIAGNOSTIC_SPEC

    def build_tool_context(self, *, input_data, turn, trace_id):
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["current_task_id"] = trace_id
        ctx["agent_id"] = self.SPEC.id
        ctx["scratch"] = ctx.get("scratch", {})
        return ctx

    def build_extract_result(self, *, bus):
        # 共用 spec 的 verdict 提取 (扫 messages 找 submit_verdict)
        return _build_spec_verdict_extractor(bus=bus)
