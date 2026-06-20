# [OMNI] origin=ai-ide domain=services/_diagnosis/doctor/agents ts=2026-05-05T20:50:00Z type=router status=skeleton agent=ai-ide-current
# [OMNI] summary="SpecDiagnosticAgent V0 骨架 — 拿现有规范文档原文 + 待诊断对象, LLM 自然语言判合不合规. 不抽硬规则 (硬规则归 guardian)"
# [OMNI] why="诊断重制阶段 2 落第一个诊断方法. 用户 5 条铁律: 规范是引用不是抽取, 软规则在 doctor 自然语言判, 硬规则在 guardian"
# [OMNI] tags=agent,configurable,doctor,spec,skeleton,phase-2-step-2
# [OMNI] material_id="material:diagnosis.doctor.agents.spec_diagnostic.skeleton.py"
"""SpecDiagnosticAgent · 规范型诊断 (V0 骨架)

落 plan §5.6 通用 doctor agent 设计原则的第一份实现. 这是诊断重制阶段 2 的第一份
诊断器, 也是后续 Hypothesis / Exemplar / Plan 三种诊断 agent 的形态参考.

设计:
- 输入: doctor.spec_diagnosis.request (待诊断对象路径 + 适用规范文档清单)
- 工作: agent 用 read_file / glob / grep / list_dir 工具读对象代码 + 读规范文档原文,
        自然语言判 "对象有没有违反规范的地方"
- 输出: doctor.spec_diagnosis.verdict (含 list[doctor.health_finding] + LLM 总评)

不做硬规则枚举. 不抽 30-50 条 SpecChecker. 整篇规范原文进 LLM, LLM 自己读自己判.
硬规则归 guardian (规则引擎层).

工具集 (5 个起步, 留 5 个余量到 10 上限):
- read_file / glob / grep / list_dir — framework 自带读型工具
- write_finding — doctor 业务工具 (V0 step 5 已实现, 落 yaml + 待 bus 事件)

## 待做 (V0 骨架 → V1 可跑路径)

[x] **write_finding 工具实现 + 注册** — 2026-05-05 step 5 完成 (doctor/tools/write_finding.py)
[ ] **prompt 内容充实**: 当前 spec_diagnostic_prompt.md 只是模板占位.
    需要写真"如何判规范" 的指导 (但保持自然语言, 不写规则枚举)
[ ] **bus 事件**: write_finding 当前只 yaml 落盘. 加 SQLiteBus.publish 发 doctor.health_finding 事件
[ ] **registry HealthArchive 接口对接**: registry 提供 ingest_finding API 后, write_finding 改走 API
[ ] **跑一次真 dogfood**: 用本 agent 诊断 doctor 自己某个 worker, 看产出 finding 质量
[ ] **测试基线 red/green 样本填实**: 当前 () 占位, 至少 1 红 + 1 绿
[ ] **gates / context_triggers**: 当前 () 占位. 看实跑暴露什么需要再加
[ ] **加入 doctor team.py 拓扑**: 当前没接入 dispatcher, 不会被激活 — step 6 处理
[ ] **更 doctor/DESIGN.md §架构决策**: 加诊断方法层 (规范/样例/假设/计划) 决策记录

跟 plan 关联: docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/plan.md §5.6 + §六 阶段 2.
"""
from __future__ import annotations

# 保险: 直接 import 自己加载就触发 doctor.tools 业务工具注册到 TOOL_REGISTRY,
# 避免 SPEC.tools 引用 "write_finding" 时 __init_subclass__ 找不到.
# 通过 doctor.agents 包 __init__.py 进入也走得通 (注册顺序约定).
from omnicompany.packages.services._diagnosis.doctor import tools  # noqa: F401

from omnicompany.packages.services._core.agent import (
    AgentSpec,
    ConfigurableAgent,
)


SPEC_DIAGNOSTIC_SPEC = AgentSpec(

    # ── 1. omnicompany 注册信息 ──────────────────────────────────
    id="doctor.spec_diagnostic",
    name="SpecDiagnosticAgent",
    domain="doctor",
    parent_worker_kind="agent",
    registry_namespace="services.agent.instances",

    # ── 2. LLM 及其配置 ───────────────────────────────────────
    llm_model="qwen-3.6-plus",
    llm_temperature=0.2,                 # 诊断要稳, 不要发散
    llm_max_tokens=16000,
    llm_max_turns=1000,                   # 铁律 B
    llm_timeout_seconds=600,

    # ── 3. 产出的 material 列表 ─────────────────────────────────
    output_materials=(
        "doctor.spec_diagnosis.verdict",
        "doctor.health_finding",
    ),
    primary_output="doctor.spec_diagnosis.verdict",

    # ── 4. 触发性 material ────────────────────────────────────
    trigger_materials=(
        "doctor.spec_diagnosis.request",
    ),
    trigger_mode="any",

    # ── 5. 响应范围 ──────────────────────────────────────────
    accepted_input_materials=(
        "doctor.spec_diagnosis.request",
        # 规范文档 / 待诊断对象都靠工具读, 不预订阅 material
    ),
    forbidden_input_materials=(
        "doctor.spec_diagnosis.verdict",   # 不订阅自家产出
        "doctor.health_finding",
    ),

    # ── 6. 用户输入 ─────────────────────────────────────────
    user_input_template=(
        "请诊断对象 {target_entity_path} (类型 {target_entity_kind}) 跟以下规范的合规度.\n\n"
        "适用规范: {applicable_standards}\n\n"
        "做法:\n"
        "1. 用 read_file 读规范文档原文 + 待诊断对象代码\n"
        "2. 用 glob/grep 找相关上下文\n"
        "3. 自然语言判合不合规, 给具体证据\n"
        "4. 每条违规走 write_finding 落 doctor.health_finding\n"
        "5. 返回 doctor.spec_diagnosis.verdict 包含全部 finding + 你的总评"
    ),
    user_input_required_fields=(
        "target_entity_path",
        "target_entity_kind",
        "applicable_standards",
    ),

    # ── 7. 系统 prompt (走外部 .md) ────────────────────────────
    prompt_path="src/omnicompany/packages/services/_diagnosis/doctor/agents/spec_diagnostic_prompt.md",
    prompt_substitutions={
        "agent_role": "规范型诊断 agent",
        "primary_output": "doctor.spec_diagnosis.verdict",
    },

    # ── 8. 工具列表 ─────────────────────────────────────────
    tools=(
        # framework 自带 (TOOL_REGISTRY 已登记)
        "read_file",
        "glob",
        "grep",
        "list_dir",
        # 业务工具 (doctor/tools/ 注册)
        "write_finding",       # 可选: 单条 finding 落 yaml (允许预先调多次, 也允许跳过都 inline 进 submit_verdict)
        "submit_verdict",      # 必调出口: 调它通过 schema 校验才算合法结束
    ),

    # ── 9. 工作区 ─────────────────────────────────────────
    workspace={
        "name": "doctor.spec_diagnostic",
        "write_prefixes": (
            "data/services/doctor/findings/{task_id}/",
            "data/services/doctor/_notes/{task_id}/",
        ),
        "read_prefixes": "READ_ANY",       # 诊断要读广 (规范 + 任意 service 代码)
        "bash_cwd_prefixes": ("",),
    },

    # ── 10. 门禁列表 ─ V0 空, 看实跑加 ─────────────────────────
    gates=(),

    # ── 11. 上下文触发器 ─ V0 空 ────────────────────────────
    context_triggers=(),

    # ── 12. 配置驱动, 含自定义代码 (override build_tool_context + build_extract_result) ─────────────────────────
    allow_custom_code=True,

    # ── 13. 红绿测试基线 ─ 2026-05-06 self_audit §B-2 修复 ─────────
    test_baseline={
        # 绿: csv_reader (worker 类合规标杆). dogfood 实测 2 finding 全正面 (不引 R-XX 阻断), narrative 总结"职责清晰单一, 协议正确"
        "green_samples": (
            "src/omnicompany/packages/services/_utility/csv_to_md/workers/csv_reader.py",
        ),
        # 红: red_minimal_worker fixture (故意违反 R-01/R-02/R-04/R-14 4 条). dogfood 实测 5 finding, applied_standards 含 R-01/R-02/R-04/R-05/R-14, 命中我故意违反的 4 条 + 多识别一条
        "red_samples": (
            "src/omnicompany/packages/services/_diagnosis/doctor/_test_fixtures/red_workers/red_minimal_worker.py",
        ),
        "gradient_samples": (),
        # 红绿对比脚本: _scratch/dogfood_red_green_baseline.py
        # 实测结果: 2026-05-06 跑过 OVERALL PASS (red>green count + red 引 ≥3 R-XX + 红 finding evidence ≥20 字)
        "_baseline_validated_at": "2026-05-06",
        "_baseline_overall": "PASS",
    },
)


class _SpecVerdictExtractor:
    """SpecDiagnostic 用的 verdict 提取器 — 扫 messages 找 last 成功 submit_verdict.

    跟 default ExtractResultRouter 行为对比:
    - default: verdict.output = {text, turn_count, stop_reason} (raw LLM final text)
    - 本类: verdict.output = submit_verdict 的 args 本体 (含 findings/narrative/applied_standards)

    fallback: 没找到成功 submit_verdict 时, 回退默认 (含 final_text), 让管线不静默失败.
    """

    @staticmethod
    def find_last_submit_verdict(messages: list[dict]) -> dict | None:
        """扫 messages 找最后一个 submit_verdict tool_use 且对应 tool_result 成功的.

        messages 形态 (Anthropic API):
          {"role": "assistant", "content": [{"type": "tool_use", "name": ..., "input": ..., "id": ...}, ...]}
          {"role": "user", "content": [{"type": "tool_result", "tool_use_id": ..., "is_error": ..., ...}]}

        返成功调用的 input dict, 没找到返 None.
        """
        # 先收所有 submit_verdict tool_use {use_id: input}
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
                if block.get("type") == "tool_use" and block.get("name") == "submit_verdict":
                    uid = block.get("id")
                    if uid:
                        uses[uid] = block.get("input") or {}
        if not uses:
            return None

        # 再扫 tool_result, 找成功的 (is_error=False)
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
                successful_input = uses[uid]   # 后续覆盖前面, 拿 last successful
        return successful_input


def _build_spec_verdict_extractor(bus):
    """构造 SpecDiagnostic 用的 verdict 提取 Router (运行时构造避免 import circular)."""
    from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
    from omnicompany.protocol.anchor import Verdict, VerdictKind

    class _SpecVerdictRouter(ExtractResultRouter):
        ROUTER_NAME = "spec_diagnostic_extract_result"

        def extract(self, *, final_text, messages, turn_count, stop_reason):
            submitted = _SpecVerdictExtractor.find_last_submit_verdict(messages)
            if submitted is None:
                # 没成功调 submit_verdict 出口检查 — 诊断协议未满足.
                # 返 FAIL 让 dispatcher 不 publish verdict event, 下游消费方收不到 = 诊断不算数.
                # 这是 step 9.3 loop 守卫的隐含实现: 不强阻 LLM finish, 但 verdict 不传播.
                return Verdict(
                    kind=VerdictKind.FAIL,
                    output={
                        "text": final_text,
                        "turn_count": turn_count,
                        "stop_reason": stop_reason,
                        "verdict_protocol_breach": (
                            "agent finished without successful submit_verdict call. "
                            "verdict event NOT published to bus (dispatcher skips on FAIL). "
                            "下游 (run_spec_diagnosis 调用方) 看 events 没 verdict 事件 = 知道这次诊断未完成."
                        ),
                    },
                    diagnosis=(
                        "诊断协议违反: agent 跳过 submit_verdict 出口检查 (用户铁律: 未调用通过不能退出). "
                        f"raw text 长度 {len(final_text)}, turns {turn_count}, stop {stop_reason!r}. "
                        "调用方应回流 LLM 重试或人审."
                    ),
                )

            # 成功路径: 用 submit_verdict args 作 verdict.output
            kind = VerdictKind.PASS
            if stop_reason == "max_turns":
                kind = VerdictKind.PARTIAL
            return Verdict(
                kind=kind,
                output={
                    **submitted,                   # findings / narrative / applied_standards / target_*
                    "turn_count": turn_count,
                    "stop_reason": stop_reason,
                },
                diagnosis="" if kind == VerdictKind.PASS else f"Budget exhausted: {turn_count} turns",
            )

    return _SpecVerdictRouter(bus=bus)


class SpecDiagnosticAgent(ConfigurableAgent):
    """规范型诊断 agent — 拿规范文档原文 + 待诊断对象, LLM 自然语言判合规度.

    跟 guardian 边界: guardian 跑硬规则 (50 行 Python ast 能写完的). doctor SpecDiagnostic
    跑软语义判 (规范文档自然语言要求, LLM 读了判). 互补, 不重叠.

    跟现 doctor workers/format/format_contextual_audit.py 等 LLM 审计 worker 边界:
    那些是按特定规范 (F-01 / F-06) 硬编码的; 本 agent 是通用的, 拿任意 standards/concepts/*.md
    都能跑. 现有 LLM 审计 worker 长远会重写为本 agent 的特化实例 (待 step 4-6 重构).

    Override 钩子 (SPEC.allow_custom_code=True):
    - build_tool_context: 注入 current_task_id (= trace_id) / agent_id / scratch dict.
      让 write_finding 落盘走真 task_id 不是 'unknown'. submit_verdict 用 scratch 写入提交记录.
    - build_extract_result: verdict event payload 走 submit_verdict 工具 args 而非 raw final_text.
      让下游 worker 订阅 verdict 时能 type-safely 读 findings/narrative.
    """

    SPEC = SPEC_DIAGNOSTIC_SPEC

    # ── 9.1 注入 task_id / agent_id / scratch ──
    def build_tool_context(self, *, input_data, turn, trace_id):
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["current_task_id"] = trace_id          # write_finding 落 findings/<task_id>/ 用
        ctx["agent_id"] = self.SPEC.id             # write_finding 字段填
        ctx["scratch"] = ctx.get("scratch", {})    # submit_verdict 写 submitted_verdict 用
        return ctx

    # ── 9.2 verdict payload 走 submit_verdict args ──
    def build_extract_result(self, *, bus):
        return _build_spec_verdict_extractor(bus=bus)
