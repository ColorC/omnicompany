# [OMNI] origin=ai-ide domain=services/_diagnosis/doctor/agents ts=2026-05-05T23:35:00Z type=router status=skeleton agent=ai-ide-current
# [OMNI] summary="ExemplarDiagnosticAgent V0 骨架 — 拿样例库的一组 yaml 样例 + 待诊断对象, LLM 自然语言判对象跟样例差在哪"
# [OMNI] why="阶段 2 后续 1: 第三种诊断方法. 验证 'submit_verdict 通用工具 + 自然语言评论' 模式跨 spec/hypothesis/exemplar 三种方法可复制"
# [OMNI] tags=agent,configurable,doctor,exemplar,skeleton,phase-2-step-10
# [OMNI] material_id="material:diagnosis.doctor.agents.exemplar_diagnostic.skeleton.py"
"""ExemplarDiagnosticAgent · 样例型诊断 (V0 骨架)

跟 SpecDiagnosticAgent / HypothesisDiagnosticAgent 同形态, 区别在判定来源:
- spec 型: 拿规范文档 (docs/standards/concepts/) 整篇规范文档让 LLM 判合规度
- hypothesis 型: 拿一组假设 yaml 实例 (一句话+motivation), LLM 逐条判违反/满足
- exemplar 型: 拿一组样例 yaml 实例 (指向标杆代码 path + qualified_reason), LLM 比对待诊断对象跟样例差在哪

样例 vs 规范的关键区别:
- 规范说"应满足什么", 样例展示"已知合规且高质量长什么样"
- 规范是抽象, 样例是具象. 比对样例帮 LLM 看到具体面跟具体差异
- 都不是判合规, 跟样例比是 "学到什么 / 差在哪 / 能不能借鉴"

设计:
- 输入: doctor.exemplar_diagnosis.request (target_entity_path / target_entity_kind / applicable_exemplar_paths)
- 工作: agent 用 read_file 读样例 yaml + 读样例指向的代码 + 读待诊断对象代码, 自然语言对照
- 输出: doctor.exemplar_diagnosis.verdict (含 list[finding finding_kind=exemplar] + narrative)

工具集 = SpecDiagnosticAgent / HypothesisDiagnosticAgent 同 (read_file/glob/grep/list_dir/write_finding/submit_verdict).
共用 submit_verdict 通用工具 (consulted_references 字段填样例 yaml path + 样例指向的代码 path).

## 待做 (V0 骨架 → V1)

[ ] **dogfood**: 拿 sample_exemplar_E-worker-csv_reader-2026-05-05.yaml 跑诊断 doctor 一个 worker, 看产 finding 质量
[ ] **样例库管理**: 当前从外部传 paths, 后续应从 data/services/doctor/exemplars/<kind>/ 自动 enumerate
[ ] **多样例 vs 单样例**: 当前一次跑可传多份样例并行对照, 看是否要分"主样例 + 辅样例"
[ ] **测试基线**: 现 () 占位, 至少 1 红 1 绿
[ ] **DESIGN.md 更**: doctor/DESIGN.md 加 ExemplarDiagnosticAgent 段
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


EXEMPLAR_DIAGNOSTIC_SPEC = AgentSpec(

    # ── 1. 注册信息 ─────────────────────────────────────
    id="doctor.exemplar_diagnostic",
    name="ExemplarDiagnosticAgent",
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
        "doctor.exemplar_diagnosis.verdict",
        "doctor.health_finding",
    ),
    primary_output="doctor.exemplar_diagnosis.verdict",

    # ── 4. 触发 material ─────────────────────────────────
    trigger_materials=(
        "doctor.exemplar_diagnosis.request",
    ),
    trigger_mode="any",

    # ── 5. 响应范围 ─────────────────────────────────────
    accepted_input_materials=(
        "doctor.exemplar_diagnosis.request",
    ),
    forbidden_input_materials=(
        "doctor.exemplar_diagnosis.verdict",
        "doctor.health_finding",
    ),

    # ── 6. 用户输入 ─────────────────────────────────────
    user_input_template=(
        "请用以下样例跟对象 {target_entity_path} (类型 {target_entity_kind}) 比对, 看差在哪.\n\n"
        "样例 yaml 路径 (一组): {applicable_exemplar_paths}\n\n"
        "做法:\n"
        "1. 用 read_file 读每条样例 yaml (含 exemplar_path / qualified_reason / tags / notes)\n"
        "2. 用 read_file 读样例指向的标杆代码 (yaml 里 exemplar_path 字段)\n"
        "3. 用 read_file / glob / grep 读待诊断对象代码\n"
        "4. 自然语言比对: 待诊断对象在哪些面比标杆差 / 哪些面相当 / 能从样例学到什么\n"
        "5. 每条值得记的差异或借鉴点走 write_finding (finding_kind=exemplar, applied_exemplars=[样例 id])\n"
        "6. 调 submit_verdict 提交完整 verdict (consulted_references 填实际查的样例 yaml path + 样例指向的代码 path)"
    ),
    user_input_required_fields=(
        "target_entity_path",
        "target_entity_kind",
        "applicable_exemplar_paths",
    ),

    # ── 7. 系统 prompt ─────────────────────────────────
    prompt_path="src/omnicompany/packages/services/_diagnosis/doctor/agents/exemplar_diagnostic_prompt.md",
    prompt_substitutions={
        "agent_role": "样例型诊断 agent",
        "primary_output": "doctor.exemplar_diagnosis.verdict",
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
        "name": "doctor.exemplar_diagnostic",
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
        # 绿: csv_reader 比 csv_reader 自己 (parity case)
        "green_samples": (
            "src/omnicompany/packages/services/_utility/csv_to_md/workers/csv_reader.py",
        ),
        # 红: csv_reader 比 red_minimal_worker (gap case, finding 4 vs 1)
        "red_samples": (
            "src/omnicompany/packages/services/_diagnosis/doctor/_test_fixtures/red_workers/red_minimal_worker.py",
        ),
        "gradient_samples": (),
        # 红绿对比脚本: _scratch/dogfood_red_green_exemplar.py
        # 实测 (2026-05-06): GREEN finding 1 (parity), RED finding 4 (gap), narrative 双向区分
        "_baseline_validated_at": "2026-05-06",
        "_baseline_overall": "PASS",
    },
)


class ExemplarDiagnosticAgent(ConfigurableAgent):
    """样例型诊断 agent — 拿样例 yaml + 待诊断对象, LLM 比对差在哪.

    复用 SpecDiagnosticAgent 的 verdict 提取逻辑 (_build_spec_verdict_extractor),
    因为 spec/hypothesis/exemplar 共用 submit_verdict 通用工具 + 同 verdict 形态.
    """

    SPEC = EXEMPLAR_DIAGNOSTIC_SPEC

    def build_tool_context(self, *, input_data, turn, trace_id):
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["current_task_id"] = trace_id
        ctx["agent_id"] = self.SPEC.id
        ctx["scratch"] = ctx.get("scratch", {})
        return ctx

    def build_extract_result(self, *, bus):
        return _build_spec_verdict_extractor(bus=bus)
