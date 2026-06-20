# [OMNI] origin=ai-ide domain=services/_diagnosis/doctor/agents ts=2026-05-07T01:10:00Z type=router status=skeleton agent=ai-ide
# [OMNI] summary="MetaDiagnosticAgent V0 骨架 — 元诊断 agent. 走用户 10 问 + 7 假设, 看一个 team 整体健康. 跟现 5 agent 不同层 — 看 team 整体不看单一对象"
# [OMNI] why="meta_diagnosis_pipeline_plan §阶段 5. 用户 5/6 立元诊断 framework: 一个 team 健康度的 10 问 + 7 假设. 现 5 agent 是单对象诊断器, 缺 team 整体看的层"
# [OMNI] tags=agent,configurable,doctor,meta-diagnosis,team-health,skeleton
# [OMNI] material_id="material:diagnosis.doctor.agents.meta_diagnostic.skeleton.py"
"""MetaDiagnosticAgent · 元诊断 (V0 骨架)

跟现 5 agent (Spec/Hypothesis/Exemplar/Plan + Deriver) 不同层:
- 现 5 agent: 单一对象诊断器 (拿规范判一个 worker / 拿假设判一个对象)
- MetaDiagnosticAgent: 看 **一个 team 整体**, 走 10 问 + 7 假设

输入: doctor.meta_diagnosis.request (team_path / focus_questions 列表 / depth)
工作: agent 用 read_file / glob / grep / list_dir / bash (git log) 工具
- 扫 team 现有验证设施 (tests/ dogfood/ .omni/)
- 看 team 输出哪些 material
- 跑 git log 看修复历史 / 工作模式
- 拿反模式临床参照书 (anti_patterns/archetypes.yaml) 对照命中
- 拿正确锚点表 (canonical_anchors/standards_authority_map.yaml) 标权威度
输出: doctor.meta_diagnosis.verdict (10 问回答 + team 健康报告 + 推荐验证设施清单)

设计原则 (跟用户铁律一致):
- 拒打分: 10 问回答自然语言, 不打 critical/major/minor
- 走总线: 通过 SQLiteBus + dispatcher
- 复用 submit_verdict: 但加扩展字段 (10 问每问回答, 推荐设施清单)
"""
from __future__ import annotations

# 保险 import doctor.tools 注册
from omnicompany.packages.services._diagnosis.doctor import tools  # noqa: F401

from omnicompany.packages.services._core.agent import (
    AgentSpec,
    ConfigurableAgent,
)
from omnicompany.packages.services._diagnosis.doctor.agents.spec_diagnostic import (
    _build_spec_verdict_extractor,
)


META_DIAGNOSTIC_SPEC = AgentSpec(
    # 1. 注册
    id="doctor.meta_diagnostic",
    name="MetaDiagnosticAgent",
    domain="doctor",
    parent_worker_kind="agent",
    registry_namespace="services.agent.instances",

    # 2. LLM 配置
    llm_model="qwen-3.6-plus",
    llm_temperature=0.25,        # 元诊断需稳定推理 + 适度发散提其他猜想
    llm_max_tokens=24000,        # 元诊断扫面广, token 多
    llm_max_turns=1500,          # 铁律 B 宽松
    llm_timeout_seconds=900,

    # 3. 产出
    output_materials=(
        "doctor.meta_diagnosis.verdict",
        "doctor.health_finding",
    ),
    primary_output="doctor.meta_diagnosis.verdict",

    # 4. 触发
    trigger_materials=("doctor.meta_diagnosis.request",),
    trigger_mode="any",

    # 5. 响应范围
    accepted_input_materials=("doctor.meta_diagnosis.request",),
    forbidden_input_materials=(
        "doctor.meta_diagnosis.verdict",
        "doctor.health_finding",
    ),

    # 6. 用户输入
    user_input_template=(
        "请对 team {team_path} 做元诊断.\n\n"
        "焦点问题 (子集 of 10 问): {focus_questions}\n"
        "诊断深度: {depth}\n\n"
        "做法:\n"
        "1. 用 list_dir + glob 扫 team 整体结构\n"
        "2. 用 read_file 读 team 关键文件 (DESIGN.md / formats.py / workers/ / tests/ / dogfood/)\n"
        "3. 用 bash 跑 git log 看 team 修复历史\n"
        "4. 拿反模式临床参照书对照 (read docs/plans/diagnosis/.../anti_patterns/archetypes.yaml)\n"
        "5. 拿正确锚点表对照 (read .../canonical_anchors/standards_authority_map.yaml)\n"
        "6. 走 10 问 + 7 假设逐条回答, 自然语言\n"
        "7. 通过 submit_verdict 提交 (含 10 问回答 + 推荐验证设施清单)"
    ),
    user_input_required_fields=("team_path", "focus_questions", "depth"),

    # 7. prompt
    prompt_path="src/omnicompany/packages/services/_diagnosis/doctor/agents/meta_diagnostic_prompt.md",
    prompt_substitutions={
        "agent_role": "元诊断 agent",
        "primary_output": "doctor.meta_diagnosis.verdict",
    },

    # 8. 工具
    # 修 4hr 拷问真问题 1+5 (2026-05-07 立 git_log 结构化工具):
    # - 跟 agent_tools.md 原则 1 一致 (不开通用 bash)
    # - 跟 agent_first.md §8.5 一致 (有 git/时间维度访问能力)
    tools=(
        "read_file",
        "glob",
        "grep",
        "list_dir",
        "write_finding",
        "submit_verdict",
        "git_log",  # 结构化 git log (修真问题 1+5)
        "rank_hypothesis_challenge_queue",  # V4-2 2026-05-07: 死局时按 a/b/c 优先级排假设
    ),

    # 9. workspace
    # 修 4hr 拷问真问题 6 (违反 agent_first.md §8.5 第 6 条 'agent 产物落规范子目录 read_tools/external_pulls/notes')
    workspace={
        "name": "doctor.meta_diagnostic",
        "write_prefixes": (
            "data/services/doctor/findings/{task_id}/",        # finding 落档 (主产物)
            "data/services/doctor/_notes/{task_id}/",          # 中间笔记
            "data/services/doctor/team_health/{task_id}/",     # team 健康整体报告 (元诊断主产物)
            "data/services/doctor/recommendations/{task_id}/", # 推荐验证设施清单
            "data/services/doctor/external_pulls/{task_id}/",  # 外部拉取 (git log / 跨 team 数据等)
        ),
        "read_prefixes": "READ_ANY",
        "bash_cwd_prefixes": ("",),
    },

    # 10-11. gates / triggers V0 空
    gates=(),
    context_triggers=(),

    # 12. allow_custom_code
    allow_custom_code=True,

    # 13. test_baseline ─ 2026-05-07 阶段 9 红绿对比验证 OVERALL PASS 后填
    test_baseline={
        "green_samples": (
            "src/omnicompany/packages/services/_utility/csv_to_md/",
        ),
        "red_samples": (
            "src/omnicompany/packages/services/_diagnosis/doctor/_test_fixtures/red_teams/red_minimal_team/",
        ),
        "gradient_samples": (),
        # 红绿对比脚本: _scratch/dogfood_meta_red_green.py
        # 实测 (2026-05-07): GREEN csv_to_md 4 finding 引 P-05/P-12/P-13/distributed-docs (规范引用),
        #                   RED red_minimal_team 5 applied 含 4 AP-XXX (AP-001/004/012/014) + test-pyramid
        #                   judgement: 红 archetype 命中 4 vs 绿 0, 红 creative_content 含'客观扫描' (修 prompt 后), OVERALL PASS
        # 修 prompt 历史: 第一次跑发现 agent 见 fixture 自述就偷懒 (red applied 空), 加'客观对待铁律' 后第二次 PASS
        # 落档: meta_red_green_finding_2026-05-07.md
        "_baseline_validated_at": "2026-05-07",
        "_baseline_overall": "PASS",
    },
)


class MetaDiagnosticAgent(ConfigurableAgent):
    """元诊断 agent — 走 10 问 + 7 假设看 team 整体健康.

    跟现 5 agent 区别:
    - 5 agent: 单一对象诊断器 (target_entity_path 是单文件)
    - MetaDiagnosticAgent: target 是 team 整体目录 + 时间维度 (git log)

    复用 _build_spec_verdict_extractor (同样扫 messages 找 last 成功 submit_verdict).
    """

    SPEC = META_DIAGNOSTIC_SPEC

    def build_tool_context(self, *, input_data, turn, trace_id):
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["current_task_id"] = trace_id
        ctx["agent_id"] = self.SPEC.id
        ctx["scratch"] = ctx.get("scratch", {})
        return ctx

    def build_extract_result(self, *, bus):
        return _build_spec_verdict_extractor(bus=bus)
