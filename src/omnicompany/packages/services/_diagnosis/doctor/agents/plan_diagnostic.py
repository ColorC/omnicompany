# [OMNI] origin=ai-ide domain=services/_diagnosis/doctor/agents ts=2026-05-06T00:05:00Z type=router status=skeleton agent=ai-ide-current
# [OMNI] summary="PlanDiagnosticAgent V0 骨架 — 拿 plan_template 模板 + 实际 plan.md, LLM 自然语言判 plan 完成度 (结构合规 + 静态产物存在性). 动态验收 V1 接"
# [OMNI] why="阶段 2 后续 2: 第四种诊断方法. 验证 'submit_verdict 通用工具 + 自然语言评论' 跨 spec/hypothesis/exemplar/plan 四方法可复制"
# [OMNI] tags=agent,configurable,doctor,plan,skeleton,phase-2-step-11
# [OMNI] material_id="material:diagnosis.doctor.agents.plan_diagnostic.skeleton.py"
"""PlanDiagnosticAgent · 计划型诊断 (V0 骨架)

跟 spec / hypothesis / exemplar 同形态. 任务: 看一份 plan.md 是否按 plan_template 写, 产物清单
里的 path 是否真存在, 验收标准能否复现.

V0 范围:
- 静态: 结构合规 (按 plan_template 一-七节) + 产物清单 path 真实存在
- 动态: 验收标准能否跑 — V0 跳过, V1 加 (需 agent 能跑命令 + 跑入口看真产出)

设计:
- 输入: doctor.plan_diagnosis.request (含 target_plan_path / applicable_template_paths / check_modes)
- 工作: agent 用 read_file 读 plan.md + plan_template.md, 用 glob/grep 查产物清单 path 实在性
- 输出: doctor.plan_diagnosis.verdict (含 list[finding finding_kind=plan] + creative_content)

工具集 = SpecDiagnosticAgent / HypothesisDiagnosticAgent / ExemplarDiagnosticAgent 同
(read_file/glob/grep/list_dir/write_finding/submit_verdict).

## 待做 (V0 骨架 → V1)

[ ] **dogfood**: 拿本计划自己 plan.md 跑诊断, 看产 finding 质量
[ ] **动态验收 (V1)**: 让 agent 按 plan.md 三节描述的入口跑, 抓真产出. 需框架支持 sandboxed bash/python 跑入口
[ ] **plan template 演化**: dogfood 后看 LLM 误判模式补模板 (但保持原则化, 不堆枚举)
[ ] **不达标处置接 tech_debt**: V0 仅产 finding, V1 加产 doctor.tech_debt.entry 接 tech_debt 服务
[ ] **测试基线**: 现 () 占位, 至少 1 红 1 绿
[ ] **DESIGN.md 更**: doctor/DESIGN.md 加 PlanDiagnosticAgent 段
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


PLAN_DIAGNOSTIC_SPEC = AgentSpec(

    # ── 1. 注册信息 ─────────────────────────────────────
    id="doctor.plan_diagnostic",
    name="PlanDiagnosticAgent",
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
        "doctor.plan_diagnosis.verdict",
        "doctor.health_finding",
    ),
    primary_output="doctor.plan_diagnosis.verdict",

    # ── 4. 触发 material ─────────────────────────────────
    trigger_materials=(
        "doctor.plan_diagnosis.request",
    ),
    trigger_mode="any",

    # ── 5. 响应范围 ─────────────────────────────────────
    accepted_input_materials=(
        "doctor.plan_diagnosis.request",
    ),
    forbidden_input_materials=(
        "doctor.plan_diagnosis.verdict",
        "doctor.health_finding",
    ),

    # ── 6. 用户输入 ─────────────────────────────────────
    user_input_template=(
        "请诊断计划 {target_plan_path} 的完成度跟结构合规度.\n\n"
        "参考模板: {applicable_template_paths}\n"
        "检查模式: {check_modes} (V0 一般填 ['static'])\n\n"
        "做法:\n"
        "1. 用 read_file 读 plan_template.md 知道'plan.md 应长什么样'\n"
        "2. 用 read_file 读 target_plan_path 实际 plan.md\n"
        "3. 自然语言判结构合规 (一-七节是否齐, OMNI 头是否齐)\n"
        "4. 用 glob / read_file 查 plan.md '产物清单' 节列的每条 path 是否真存在\n"
        "5. 每条不合规或缺失走 write_finding (finding_kind=plan, applied_standards=[模板路径:节])\n"
        "6. 调 submit_verdict 提交完整 verdict (consulted_references 填模板 path + plan.md path)"
    ),
    user_input_required_fields=(
        "target_plan_path",
        "applicable_template_paths",
        "check_modes",
    ),

    # ── 7. 系统 prompt ─────────────────────────────────
    prompt_path="src/omnicompany/packages/services/_diagnosis/doctor/agents/plan_diagnostic_prompt.md",
    prompt_substitutions={
        "agent_role": "计划型诊断 agent",
        "primary_output": "doctor.plan_diagnosis.verdict",
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
        "name": "doctor.plan_diagnostic",
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

    # ── 12. 含自定义代码 (override hooks 跟其他诊断 agent 同) ──
    allow_custom_code=True,

    # ── 13. 测试基线 ─ 2026-05-06 self_audit §B-2 修复 ─────────
    test_baseline={
        # 绿: 合规样本 (一-七节齐 + OMNI 头齐 + P-1~P-6 全产)
        "green_samples": (
            "docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/samples/sample_compliant_plan_exemplar_library.md",
        ),
        # 红: red_minimal_plan fixture (缺需求/产物/验收/不达标处置 4 节)
        "red_samples": (
            "src/omnicompany/packages/services/_diagnosis/doctor/_test_fixtures/red_plans/red_minimal_plan.md",
        ),
        "gradient_samples": (),
        # 红绿对比脚本: _scratch/dogfood_red_green_plan.py
        # 实测 (2026-05-06): green creative_content 主调合规, red creative_content 主调缺失阻断, 双向区分
        # 注: PlanDiagnosticAgent 合规 plan 也产 N 个"正面发现" finding, finding 数不是判别力 metric. 真判别力在 creative_content
        "_baseline_validated_at": "2026-05-06",
        "_baseline_overall": "PASS",
    },
)


class PlanDiagnosticAgent(ConfigurableAgent):
    """计划型诊断 agent — 拿 plan_template + 实际 plan.md, LLM 判完成度跟结构合规.

    复用 SpecDiagnosticAgent 的 verdict 提取逻辑 (_build_spec_verdict_extractor),
    因为 spec/hypothesis/exemplar/plan 共用 submit_verdict 通用工具 + 同 verdict 形态.
    """

    SPEC = PLAN_DIAGNOSTIC_SPEC

    def build_tool_context(self, *, input_data, turn, trace_id):
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["current_task_id"] = trace_id
        ctx["agent_id"] = self.SPEC.id
        ctx["scratch"] = ctx.get("scratch", {})
        return ctx

    def build_extract_result(self, *, bus):
        return _build_spec_verdict_extractor(bus=bus)
