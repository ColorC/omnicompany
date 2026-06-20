# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-15T00:00:00Z type=format status=active
# [OMNI] material_id="material:services.learning.hypothesis.format_definitions.py"
"""hypothesis.formats — Hypothesis Service 的语义类型定义（4 个 Format）。

数据流:

  hypothesis.session                    ← 入口：探索目标 + 工具配置
       │  SessionInitNode (HARD)
       ▼
  hypothesis.store (空)
       │
  ┌─────────────────────────── 循环 ──────────────────────────────┐
  │                                                                │
  │  hypothesis.store ──┐                                         │
  │                     │  ExperimenterRouter (SOFT · AgentNodeLoop)
  │  hypothesis.session ┘  内部用 tool 跑命令、提取事实            │
  │                     出: hypothesis.factlog                     │
  │                         │                                      │
  │             ┌───────────┴────────────┐                        │
  │  hypothesis.factlog        hypothesis.store                    │
  │             └───────────┬────────────┘                        │
  │                         │  ReflectorRouter (SOFT)             │
  │                         出: hypothesis.store_diff              │
  │                             │                                  │
  │             ┌───────────────┴────────────┐                    │
  │  hypothesis.store          hypothesis.store_diff               │
  │             └───────────────┬────────────┘                    │
  │                             │  StoreUpdateNode (HARD)         │
  │                             出: hypothesis.store (更新) ───────┘
  └────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

from omnicompany.protocol.format import Format, FormatRegistry


# ════════════════════════════════════════════════════════════════
# 1. hypothesis.session — 会话配置
# ════════════════════════════════════════════════════════════════

HYPOTHESIS_SESSION = Format(
    id="hypothesis.session",
    name="HypothesisSession",
    description=(
        "假设探索会话的配置，是整条循环的入口。"
        "`session_id` 为 uuid，用于落盘路径和跨轮恢复；"
        "`domain` 为探索域（如 'chat_platform-api-exploration'），决定 data/hypothesis/sessions/<domain>/ 子目录；"
        "`goal` 为自然语言目标，ExperimenterRouter 读此生成第一条 probe；"
        "`tools` 枚举可用工具（shell / chat_platform-cli / curl），ShellProbeNode 按此白名单校验；"
        "`max_iterations` 防止无限循环，典型值 20-50；"
        "`env` 注入环境变量，如 {'MSYS_NO_PATHCONV': '1'}。"
        "上游承诺：无（入口）。"
        "下游：SessionInitNode 据此创建空 store；ExperimenterRouter 读 goal/tools/max_iterations 做决策。"
        "样例：{session_id:'uuid-xxx', domain:'chat_platform-api-exploration', "
        "goal:'搞清楚 chat_platform REST API 如何认证', tools:['chat_platform-cli'], max_iterations:20, "
        "env:{'MSYS_NO_PATHCONV':'1'}}"
    ),
    parent="requirement",
    tags=["domain.hypothesis", "stage.config", "kind.source"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "domain": {"type": "string"},
            "goal": {"type": "string", "minLength": 10},
            "tools": {
                "type": "array",
                "items": {"type": "string", "enum": ["shell", "chat_platform-cli", "curl", "python"]},
                "minItems": 1,
            },
            "max_iterations": {"type": "integer", "minimum": 1},
            "env": {"type": "object", "additionalProperties": {"type": "string"}},
        },
        "required": ["session_id", "domain", "goal", "tools", "max_iterations"],
    },
)


# ════════════════════════════════════════════════════════════════
# 2. hypothesis.factlog — 本轮探索积累的事实记录
# ════════════════════════════════════════════════════════════════

HYPOTHESIS_FACTLOG = Format(
    id="hypothesis.factlog",
    name="HypothesisFactlog",
    description=(
        "ExperimenterRouter 一轮内跑完所有 probe 后输出的事实记录，"
        "是 Reflector 的核心输入之一。"
        "`session_id`/`iteration` 标识来源；"
        "`facts` 为 ObservationFact 列表，每条含："
        "  `cmd`（执行的命令字符串，便于追溯）、"
        "  `action`（做了什么，不含因果）、"
        "  `result`（可观测结果）、"
        "  `verbatim`（stdout/stderr 原文直引）。"
        "关键约束：verbatim 必须是命令输出的逐字引用，禁止解释或摘要。"
        "Reflector 只靠 verbatim 产生假设——verbatim 不准，假设就是幻觉。"
        "上游承诺：ExperimenterRouter 内部 ObserverNode 已过滤解释性内容。"
        "下游：ReflectorRouter 读 facts 提取候选假设；facts 为空时 Reflector 应输出空 diff。"
        "样例：{session_id:'uuid-xxx', iteration:1, facts:["
        "{cmd:'chat_platform-cli login', action:'执行 chat_platform-cli login', "
        "result:'返回 unknown command', verbatim:'Error: unknown command login'}]}"
    ),
    parent="tool-observation",
    tags=["domain.hypothesis", "stage.observe", "structured", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "iteration": {"type": "integer", "minimum": 0},
            "facts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "cmd": {"type": "string"},
                        "action": {"type": "string"},
                        "result": {"type": "string"},
                        "verbatim": {"type": "string"},
                    },
                    "required": ["cmd", "action", "result", "verbatim"],
                },
            },
        },
        "required": ["session_id", "iteration", "facts"],
    },
)


# ════════════════════════════════════════════════════════════════
# 3. hypothesis.store — 当前假设库状态
# ════════════════════════════════════════════════════════════════

HYPOTHESIS_STORE = Format(
    id="hypothesis.store",
    name="HypothesisStore",
    description=(
        "循环内流动的假设库，每轮 StoreUpdateNode 产出新版本。"
        "`session_id`/`domain`/`iteration` 标识版本；"
        "`entries` 为全量 HypothesisEntry，每条含："
        "  `id`(uuid) / `kind`(state|transition|policy|invariant) / "
        "  `trigger`(触发条件) / `predicted`(原假设预期) / `actual`(已观察到的，可为 null) / "
        "  `evidence_count`(支持次数) / `counterexample_count`(反例次数) / "
        "  `state`(candidate|active|solidified|falsified|archived) / "
        "  `depends_on`(上游假设 id 列表，用于 JTMS 依赖回溯)；"
        "`tainted_ids` 为因上游假设被证伪而需要降级的 id 列表（JTMS 待处理队列）；"
        "`continue_session` 由 ExperimenterRouter 写入，False 时循环终止。"
        "上游承诺：depends_on 中的 id 均存在于 entries，无悬空引用（StoreUpdateNode 保证）。"
        "下游：ExperimenterRouter 读 entries 决定下一条 probe（F-14：必须看全量才能判断不确定性）；"
        "  ReflectorRouter 读 entries 做去重（F-14：防止重复发现已知假设）。"
        "落盘：data/hypothesis/sessions/<domain>/<session_id>/iter_<N>.json。"
        "样例：{session_id:'uuid-xxx', domain:'chat_platform-api', iteration:2, "
        "entries:[{id:'H1', kind:'policy', trigger:'调用 chat_platform-cli login', "
        "predicted:'命令存在', actual:'unknown command', "
        "evidence_count:0, counterexample_count:1, state:'falsified', depends_on:[]}], "
        "tainted_ids:[], continue_session:true}"
    ),
    parent="spec",
    tags=["domain.hypothesis", "stage.store", "structured", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "domain": {"type": "string"},
            "iteration": {"type": "integer", "minimum": 0},
            "entries": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "kind": {"type": "string", "enum": ["state", "transition", "policy", "invariant"]},
                        "trigger": {"type": "string"},
                        "predicted": {"type": "string"},
                        "actual": {"type": ["string", "null"]},
                        "evidence_count": {"type": "integer", "minimum": 0},
                        "counterexample_count": {"type": "integer", "minimum": 0},
                        "state": {"type": "string", "enum": ["candidate", "active", "solidified", "falsified", "archived"]},
                        "depends_on": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["id", "kind", "trigger", "predicted", "state",
                                 "evidence_count", "counterexample_count", "depends_on"],
                },
            },
            "tainted_ids": {"type": "array", "items": {"type": "string"}},
            "continue_session": {"type": "boolean"},
        },
        "required": ["session_id", "domain", "iteration", "entries", "tainted_ids", "continue_session"],
    },
)


# ════════════════════════════════════════════════════════════════
# 4. hypothesis.store_diff — Reflector 对 store 的变更申请
# ════════════════════════════════════════════════════════════════

HYPOTHESIS_STORE_DIFF = Format(
    id="hypothesis.store_diff",
    name="HypothesisStoreDiff",
    description=(
        "ReflectorRouter 输出的 store 变更申请，由 StoreUpdateNode 应用到当前 store。"
        "只包含变化量，不是全量 store。"
        "`new_entries` 为本轮新发现的候选假设，最多 3 条；"
        "  每条必须有 kind / trigger / predicted / verbatim_evidence（从 factlog 直接引用）；"
        "  verbatim_evidence 为空则 StoreUpdateNode 拒绝（没有证据不能创建假设）。"
        "`state_changes` 为现有假设的状态变更，每条含 hypothesis_id / new_state / verbatim_evidence；"
        "`continue_session` 由 Reflector 判断：False 表示认为探索已充分，循环可终止；"
        "`summary` 为简短说明（≤100 字），给人看的摘要，不是 CoT。"
        "上游承诺：Reflector 同时读了 factlog 和当前 store，new_entries 不含 store 中已有的等价假设。"
        "下游：StoreUpdateNode 校验 verbatim_evidence 非空后 apply；"
        "  StoreUpdateNode 读 continue_session 写入新 store。"
        "样例：{session_id:'uuid-xxx', iteration:1, "
        "new_entries:[{kind:'policy', trigger:'chat_platform-cli 无 login 子命令', "
        "predicted:'正确命令是 auth login', verbatim_evidence:'Error: unknown command login'}], "
        "state_changes:[{hypothesis_id:'H1', new_state:'falsified', "
        "verbatim_evidence:'unknown command login'}], "
        "continue_session:true, summary:'H1 证伪，发现新假设 auth login'}"
    ),
    parent="spec",
    tags=["domain.hypothesis", "stage.reflect", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "iteration": {"type": "integer", "minimum": 0},
            "new_entries": {
                "type": "array",
                "maxItems": 3,
                "items": {
                    "type": "object",
                    "properties": {
                        "kind": {"type": "string", "enum": ["state", "transition", "policy", "invariant"]},
                        "trigger": {"type": "string", "minLength": 5},
                        "predicted": {"type": "string", "minLength": 5},
                        "verbatim_evidence": {"type": "string", "minLength": 1},
                    },
                    "required": ["kind", "trigger", "predicted", "verbatim_evidence"],
                },
            },
            "state_changes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "hypothesis_id": {"type": "string"},
                        "new_state": {"type": "string",
                                      "enum": ["active", "solidified", "falsified", "archived"]},
                        "verbatim_evidence": {"type": "string", "minLength": 1},
                    },
                    "required": ["hypothesis_id", "new_state", "verbatim_evidence"],
                },
            },
            "continue_session": {"type": "boolean"},
            "summary": {"type": "string", "maxLength": 100},
        },
        "required": ["session_id", "iteration", "new_entries", "state_changes", "continue_session"],
    },
)


# ════════════════════════════════════════════════════════════════
# 5-7. 双脑 lockstep 三 Format（2026-04-18 新增）
# ════════════════════════════════════════════════════════════════
#
# 使用场景：主脑 (Experimenter) 每执行一步 (一次 tool_call + tool_result)，
# 即 emit 一个 step_observation；反思脑 (Reflector daemon) 消费后 emit 一个
# reflection_result（可能带 context_substitution），主脑下一步前消费 substitution。
# 事件总线走持久化+可回放；in-process asyncio 通道走严格同步的 gate。

HYPOTHESIS_STEP_OBSERVATION = Format(
    id="hypothesis.step_observation",
    name="HypothesisStepObservation",
    description=(
        "主脑 (Experimenter) 一个执行步的完整可观察单元：一次 tool_call + tool_result + "
        "当时的假设库快照 + turn 编号 + session_id。"
        "脱离 hypothesis 场景也成立——描述'主 agent 某一步发生了什么'的通用合约。"
        "上游承诺：Experimenter 在 on_turn_end_async 阶段即时 emit。"
        "下游消费：ReflectorDaemon 的订阅回调。"
        "样例：{session_id:'uuid', turn:3, tool:'bash', args:{'cmd':'curl ...'}, "
        "result:'{\"token\":\"...\"}', doc_snapshot:{hyp_count:6, ids:[...]}}"
    ),
    parent="tool-observation",
    tags=["domain.hypothesis", "stage.observation", "lockstep", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "turn": {"type": "integer"},
            "tool": {"type": "string"},
            "args": {"type": "object"},
            "result": {"type": "string"},
            "doc_snapshot": {"type": "object"},
        },
        "required": ["session_id", "turn", "tool", "result"],
    },
)


HYPOTHESIS_REFLECTION_RESULT = Format(
    id="hypothesis.reflection_result",
    name="HypothesisReflectionResult",
    description=(
        "反思脑对某一 step_observation 的反思产物：对应 observation 的 session_id+turn，"
        "做了哪些 doc 编辑 (added/modified/deleted hypothesis ids)，"
        "validator 在本次反思后的通过状态，以及是否提出上下文代换。"
        "独立业务意义：每条 reflection_result 就是一次反思周期的结论，可独立回放、独立审计。"
        "上游承诺：ReflectorDaemon 在一个小 agent loop (~3-4 turns) 完成后 emit。"
        "下游消费：Experimenter 在下一 turn 前据此决策 (context_substitution 通常随附)，"
        "以及外部审计/监控。"
        "样例：{session_id:'uuid', observation_turn:3, added:['new-hyp-id'], "
        "modified:['hyp-xxx'], validator_ok:true, emitted_substitution:true}"
    ),
    parent="spec",
    tags=["domain.hypothesis", "stage.reflection", "lockstep", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "observation_turn": {"type": "integer"},
            "added": {"type": "array", "items": {"type": "string"}},
            "modified": {"type": "array", "items": {"type": "string"}},
            "deleted": {"type": "array", "items": {"type": "string"}},
            "validator_ok": {"type": "boolean"},
            "validator_errors": {"type": "integer"},
            "emitted_substitution": {"type": "boolean"},
            "summary": {"type": "string"},
        },
        "required": ["session_id", "observation_turn"],
    },
)


HYPOTHESIS_CONTEXT_SUBSTITUTION = Format(
    id="hypothesis.context_substitution",
    name="HypothesisContextSubstitution",
    description=(
        "反思脑反哺主脑的上下文代换候选：要注入到主脑下一轮 prompt 的文本片段，"
        "带 observation_turn (针对哪一步反思的产物)、kind (fact/warning/hint/hypothesis_ref)、"
        "priority (urgency 决定被丢弃的顺序)、content (实际文本)。"
        "独立业务意义：meta-reasoning agent → 其他 agent 的通用注入合约，"
        "不局限于 hypothesis 场景 —— 未来跨域上下文代换也可用同 Format。"
        "上游承诺：反思脑在 reflection_result 之后可选 emit。"
        "下游消费：下一轮 Experimenter 在 build_initial_messages 或 system_prompt 拼装时拉取。"
        "样例：{session_id:'uuid', observation_turn:3, kind:'warning', priority:8, "
        "content:'上一步的 curl 返回含 session 而非 token，DPAPI 方向可能错'}"
    ),
    parent="spec",
    tags=["domain.hypothesis", "stage.substitution", "lockstep", "kind.internal"],
    json_schema={
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "observation_turn": {"type": "integer"},
            "kind": {"type": "string",
                     "enum": ["fact", "warning", "hint", "hypothesis_ref", "redirect"]},
            "priority": {"type": "integer", "minimum": 0, "maximum": 10},
            "content": {"type": "string", "minLength": 1},
        },
        "required": ["session_id", "observation_turn", "kind", "content"],
    },
)


# ════════════════════════════════════════════════════════════════
# 注册
# ════════════════════════════════════════════════════════════════

ALL_FORMATS = [
    HYPOTHESIS_SESSION,
    HYPOTHESIS_FACTLOG,
    HYPOTHESIS_STORE,
    HYPOTHESIS_STORE_DIFF,
    HYPOTHESIS_STEP_OBSERVATION,
    HYPOTHESIS_REFLECTION_RESULT,
    HYPOTHESIS_CONTEXT_SUBSTITUTION,
]


def register_formats(registry: FormatRegistry) -> None:
    """注册 hypothesis 服务的 4 个 Format 到指定 registry。

    使用 is_registered 防重复（跨 session 重入安全）。
    """
    for fmt in ALL_FORMATS:
        if not registry.is_registered(fmt.id):
            registry.register(fmt)
