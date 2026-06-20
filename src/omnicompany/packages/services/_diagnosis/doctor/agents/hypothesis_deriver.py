# [OMNI] origin=ai-ide domain=services/_diagnosis/doctor/agents ts=2026-05-06T00:35:00Z type=router status=skeleton agent=ai-ide-current
# [OMNI] summary="HypothesisDeriverAgent V0 骨架 — 拿规范/计划/代码源派生健康性假设入库. 不是诊断, 是供给假设给 HypothesisDiagnosticAgent"
# [OMNI] why="阶段 2 后续 3: 解决 '假设从哪来' 瓶颈. 跟 4 个诊断 agent 互补 — 派生 agent 产假设, 诊断 agent 用假设"
# [OMNI] tags=agent,configurable,doctor,hypothesis-derivation,skeleton,phase-2-step-12
# [OMNI] material_id="material:diagnosis.doctor.agents.hypothesis_deriver.skeleton.py"
"""HypothesisDeriverAgent · 假设派生 (V0 骨架)

跟 4 个诊断 agent (Spec/Hypothesis/Exemplar/Plan) 不同的是产物形态:
- 4 个诊断 agent: 输入 → verdict + finding (健康判定)
- HypothesisDeriverAgent: 输入 → doctor.hypothesis.statement 实例 yaml (生成假设入库)

业务逻辑:
- 输入: doctor.hypothesis_derivation.request (含 source_paths + derivation_focus + max_hypotheses)
- 工作: agent 用 read_file / glob / grep 读规范文档 / plan / 代码源, LLM 派生'应满足什么'类的健康假设
- 输出 1: 一组 doctor.hypothesis.statement 实例 yaml (走 write_hypothesis 工具落 data/services/doctor/hypotheses/)
- 输出 2: doctor.hypothesis_derivation.report 派生过程报告 (走 submit_derivation_report 出口)

派生原则:
- 找规范里'必须 / 应 / 不得 / 一律'这类硬性表述, 每条独立成假设
- 拿 plan 的需求清单 / 验收标准, 派生 plan 特定的应满足项
- 拿代码 (例 现 worker 实现) 反推'应有'结构假设
- hard rule 候选 (ast 能查的) 标 evidence_query 提示可转 guardian
- 软语义 (LLM 才能判的) 留 doctor 用

工具集 (跟诊断 agent 同 + 派生专属):
- read_file / glob / grep / list_dir — framework 自带
- write_hypothesis — 落假设 yaml (派生专属业务工具)
- submit_derivation_report — 出口检查 (派生专属业务工具)

## 待做 (V0 骨架 → V1)

[ ] **dogfood**: 拿 worker.md 跑派生, 看产 ≥3 条新假设 (跳过已有 H-2026-05-05-001 重复)
[ ] **跨源派生**: 当前一次跑只考虑同类源, V1 加跨规范+plan+代码同时考虑
[ ] **假设升级**: 当 LLM 找到比现有假设更好的版本时, 写'升级假设' 类 finding 提示
[ ] **测试基线**: 现 () 占位, 至少 1 红 1 绿
[ ] **DESIGN.md 更**: doctor/DESIGN.md 加 HypothesisDeriverAgent 段
"""
from __future__ import annotations

# 保险: import 触发 doctor.tools 注册业务工具到 TOOL_REGISTRY
from omnicompany.packages.services._diagnosis.doctor import tools  # noqa: F401

from omnicompany.packages.services._core.agent import (
    AgentSpec,
    ConfigurableAgent,
)


HYPOTHESIS_DERIVER_SPEC = AgentSpec(

    # ── 1. 注册信息 ─────────────────────────────────────
    id="doctor.hypothesis_deriver",
    name="HypothesisDeriverAgent",
    domain="doctor",
    parent_worker_kind="agent",
    registry_namespace="services.agent.instances",

    # ── 2. LLM 配置 ────────────────────────────────────
    llm_model="qwen-3.6-plus",
    llm_temperature=0.3,                  # 派生需要点发散, 比诊断稍高
    llm_max_tokens=16000,
    llm_max_turns=1000,
    llm_timeout_seconds=600,

    # ── 3. 产出 material ─────────────────────────────────
    output_materials=(
        "doctor.hypothesis_derivation.report",
        "doctor.hypothesis.statement",   # 派生的假设实例 (走 write_hypothesis 落 yaml)
    ),
    primary_output="doctor.hypothesis_derivation.report",

    # ── 4. 触发 material ─────────────────────────────────
    trigger_materials=(
        "doctor.hypothesis_derivation.request",
    ),
    trigger_mode="any",

    # ── 5. 响应范围 ─────────────────────────────────────
    accepted_input_materials=(
        "doctor.hypothesis_derivation.request",
    ),
    forbidden_input_materials=(
        "doctor.hypothesis_derivation.report",
        "doctor.hypothesis.statement",
    ),

    # ── 6. 用户输入 ─────────────────────────────────────
    user_input_template=(
        "请从以下源派生健康性假设入库.\n\n"
        "源路径 (一组): {source_paths}\n"
        "派生焦点: {derivation_focus} (worker / material / team / agent / hook / tool / plan)\n"
        "上限: 最多派 {max_hypotheses} 条假设\n"
        "已 falsified 假设 (V23 加, 应作升级信号读 challenge_log + resolution): {falsified_hypothesis_paths}\n\n"
        "做法:\n"
        "1. 用 read_file 读每个源 (规范文档 / plan / 代码)\n"
        "2. 若 falsified_hypothesis_paths 非空, **必先 read_file 读这些 yaml 看 challenge_log "
        "    跟 resolution.falsifying_evidence**, 学 ChallengeAgent 真识别的盲区 + 真升级方向, "
        "    优先派升级版假设 (statement 含 falsifying_evidence 暴露的多模式 + tags 含 'upgraded-from-<id>')\n"
        "3. 找'必须 / 应 / 不得 / 一律'类硬性表述, 或代码隐含的应有结构\n"
        "4. 每条独立成假设, 走 write_hypothesis 工具落 yaml (id 用 'H-<YYYY-MM-DD>-<NNN>' 序号格式)\n"
        "5. hard rule 候选在 evidence_query 注明 'ast 解析能查, 可转 guardian'\n"
        "6. 调 submit_derivation_report 出口提交派生总结 (含跟 falsified 假设关系说明)"
    ),
    user_input_required_fields=(
        "source_paths",
        "derivation_focus",
        "max_hypotheses",
    ),
    # V23 加 falsified_hypothesis_paths 作可选输入字段 — 通过
    # run_hypothesis_derivation helper 传, deriver prompt 真识别后派升级版假设

    # ── 7. 系统 prompt ─────────────────────────────────
    prompt_path="src/omnicompany/packages/services/_diagnosis/doctor/agents/hypothesis_deriver_prompt.md",
    prompt_substitutions={
        "agent_role": "假设派生 agent",
        "primary_output": "doctor.hypothesis_derivation.report",
    },

    # ── 8. 工具列表 ────────────────────────────────────
    tools=(
        "read_file",
        "glob",
        "grep",
        "list_dir",
        "write_hypothesis",         # 派生专属
        "submit_derivation_report", # 派生专属
    ),

    # ── 9. 工作区 ─────────────────────────────────────
    workspace={
        "name": "doctor.hypothesis_deriver",
        "write_prefixes": (
            "data/services/doctor/hypotheses/",
            "data/services/doctor/_notes/{task_id}/",
        ),
        "read_prefixes": "READ_ANY",
        "bash_cwd_prefixes": ("",),
    },

    # ── 10-11. gates / context_triggers ─ V0 空 ─────────
    gates=(),
    context_triggers=(),

    # ── 12. 含自定义代码 (override hooks 跟其他 agent 同) ──
    allow_custom_code=True,

    # ── 13. 测试基线 ─ 2026-05-06 self_audit §B-2 修复 ─────────
    test_baseline={
        # 绿: worker.md (强制词富, 实测派 5 条 H-021..025 覆盖未派过的 R-XX)
        "green_samples": (
            "docs/standards/concepts/worker.md",
        ),
        # 红: random_readme (0 强制词的软介绍, 实测派 0 条, LLM 自律识别"无强制语义")
        "red_samples": (
            "src/omnicompany/packages/services/_diagnosis/doctor/_test_fixtures/red_sources/random_readme.md",
        ),
        "gradient_samples": (),
        # 红绿对比脚本: _scratch/dogfood_red_green_deriver.py
        # 实测 (2026-05-06): GREEN 派 5, RED 派 0, 极强判别力 (LLM 真自律)
        "_baseline_validated_at": "2026-05-06",
        "_baseline_overall": "PASS",
    },
)


def _build_derivation_extractor(bus):
    """构造 HypothesisDeriver 用的 report 提取 Router (扫 messages 找 last 成功 submit_derivation_report)."""
    from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
    from omnicompany.protocol.anchor import Verdict, VerdictKind

    class _DerivationReportRouter(ExtractResultRouter):
        ROUTER_NAME = "hypothesis_deriver_extract_result"

        def extract(self, *, final_text, messages, turn_count, stop_reason):
            submitted = _find_last_submit(messages, "submit_derivation_report")
            if submitted is None:
                return Verdict(
                    kind=VerdictKind.FAIL,
                    output={
                        "text": final_text,
                        "turn_count": turn_count,
                        "stop_reason": stop_reason,
                        "derivation_protocol_breach": (
                            "agent finished without successful submit_derivation_report call. "
                            "report event NOT published to bus (dispatcher skips on FAIL)."
                        ),
                    },
                    diagnosis=(
                        "派生协议违反: agent 跳过 submit_derivation_report 出口检查. "
                        f"raw text 长度 {len(final_text)}, turns {turn_count}, stop {stop_reason!r}."
                    ),
                )

            kind = VerdictKind.PASS
            if stop_reason == "max_turns":
                kind = VerdictKind.PARTIAL
            return Verdict(
                kind=kind,
                output={
                    **submitted,
                    "turn_count": turn_count,
                    "stop_reason": stop_reason,
                },
                diagnosis="" if kind == VerdictKind.PASS else f"Budget exhausted: {turn_count} turns",
            )

    return _DerivationReportRouter(bus=bus)


def _find_last_submit(messages: list[dict], tool_name: str) -> dict | None:
    """扫 messages 找 last 成功的指定工具 tool_use input. 跟 spec_diagnostic 同思路, 通用化."""
    uses: dict[str, dict] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                uid = block.get("id")
                if uid:
                    uses[uid] = block.get("input") or {}
    if not uses:
        return None

    successful_input: dict | None = None
    for msg in messages:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            uid = block.get("tool_use_id")
            if uid not in uses:
                continue
            if block.get("is_error"):
                continue
            successful_input = uses[uid]
    return successful_input


class HypothesisDeriverAgent(ConfigurableAgent):
    """假设派生 agent — 拿规范/计划/代码源派生健康性假设入库."""

    SPEC = HYPOTHESIS_DERIVER_SPEC

    def build_tool_context(self, *, input_data, turn, trace_id):
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["current_task_id"] = trace_id
        ctx["agent_id"] = self.SPEC.id
        ctx["scratch"] = ctx.get("scratch", {})
        return ctx

    def build_extract_result(self, *, bus):
        return _build_derivation_extractor(bus=bus)
