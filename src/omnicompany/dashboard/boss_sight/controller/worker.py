# [OMNI] origin=ai-ide ts=2026-05-24 type=worker
# [OMNI] material_id="material:dashboard.boss_sight.controller.worker.py"
"""BossSightControllerWorker — BOSS SIGHT 块 1 总控 Worker.

跟 team_supervisor / team_builder 的 SOFT worker 同套抽象 (用户原话 U-032
"跟已有 agent 保持统一抽象"). 继承 AgentNodeLoop, 由 omni-chat 的 OmniAgentProvider
驱动 (agent_class=BossSightControllerWorker, 不需要写自家 ControllerProvider).

Worker 协议:
- FORMAT_IN  = boss_sight.controller_wake_up (含 event_kind / event_payload /
              plan_index_material / subagent_status_material / workflow_summary_material)
- FORMAT_OUT = boss_sight.controller_response (submit_response tool_use input)
- 工具白名单 = 4 个自家 (submit_response / spawn_subagent / emit_event /
             propose_change) + 4 个 omnicompany 只读 (read_file / glob / grep / list_dir)
- 系统 prompt 由外部维护会话维护 (用户原话 §3.1), module load 时读 prompts/system.md.
  改文件后下次 ccdaemon 启动生效 (块 1 阶段不做 mid-session 热更新).

落实 master_roadmap.md 块 1 任务 T1.1 ~ T1.6.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, ClassVar

from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.single_tool import (
    EditRouter,
    GlobRouter,
    GrepRouter,
    ListDirRouter,
    ReadFileRouter,
)
from omnicompany.packages.services._core.agent.routers.write_file import WriteFileRouter

from .extract_result import ControllerExtractResult
from .model_resolver import CONTROLLER_DEFAULT_MODEL
from .omni_cli_router import OmniCliRouter
from .prompt_builder import ControllerPromptBuilder
from .tools import SubmitResponseRouter

# 2026-05-25 范式校正 (用户原话): 17 个总控特有 function call tool 已全部迁移到 omni cli
# 子命令 (omni worker spawn/fork/signal/bind/unbind/bindings/audit-traces/archive,
# omni plan complete/audit/binder, omni review *, omni prompt list, omni propose change).
# Router 类保留在 tools.py 作为内部 handler (cli 命令通过 _invoke_router 调它们的 _execute),
# 但 BossSightControllerWorker.TOOL_ROUTERS 不再 include — 总控只用 Bash 调 cli.
# 例外: SubmitResponseRouter 保留 — 这是 LLM 末步协议本身, 无法 cli 化.

_log = logging.getLogger(__name__)


# ── 系统 prompt: module load 时读. 用户改 system.md 后重启 ccdaemon 生效 ──
_PROMPTS_DIR = Path(__file__).parent / "prompts"


def _load_system_prompt() -> str:
    path = _PROMPTS_DIR / "system.md"
    if not path.is_file():
        _log.error("controller system.md not found at %s", path)
        return ""
    return path.read_text(encoding="utf-8")


_SYSTEM_PROMPT = _load_system_prompt()


# ── Worker ─────────────────────────────────────────────────────────────


class BossSightControllerWorker(AgentNodeLoop):
    """BOSS SIGHT 总控. 三种事件唤起统一进 run(input_data)."""

    DESCRIPTION: ClassVar[str] = (
        "BOSS SIGHT 总控 agent worker. 行政秘书角色, 接收 user.message / "
        "subagent.completed / subagent.blocked 三种唤起, 调度 subagent / 提议改设施 / "
        "回复用户. 不直接执行任务, 不修代码, 不修核心层, 不汇报."
    )
    FORMAT_IN: ClassVar[list[str]] = ["boss_sight.controller_wake_up"]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "boss_sight.controller_response"
    ALLOW_NO_BUS: ClassVar[bool] = True
    # 块 4 修复: submit_response 是末步必调工具, 调到就结束 loop. 否则 LLM 会被
    # AgentNodeLoop 反复唤醒"再说一轮", 18 轮 submit_response 后还不停.
    TERMINATING_TOOLS: ClassVar[tuple[str, ...]] = ("submit_response",)
    TOOL_ROUTERS: ClassVar[list] = [
        # **总控特有 function call 仅 1 个** (2026-05-25 范式校正):
        # submit_response 是 LLM 末步协议本身, 无法 cli 化, 保留 function call.
        SubmitResponseRouter,
        # 其余所有调度/提议/审阅/绑定/审计操作 → 通过 OmniCliRouter 调 omni cli 子命令:
        #   omni worker  {spawn,fork,signal,bind,unbind,bindings,audit-traces,archive}
        #   omni plan    {complete,audit,binder}
        #   omni review  {submit,list,annotate,push}
        #   omni prompt  list
        #   omni propose change
        # 总控 / 用户 / 外部脚本 共用一套接口, 工具集瘦身, LLM 选择负担降低.
        # OmniCliRouter 自动注入 OMNI_CLI_CALLER=controller, 受 cli 装饰器 access 限制.
        OmniCliRouter,
        # omnicompany 标准只读 4 个 (查 plan / standards / template / guard 等)
        ReadFileRouter,
        GlobRouter,
        GrepRouter,
        ListDirRouter,
        # omnicompany 标准写工具 (路径白名单由 build_tool_context 注入)
        # 用户原话 §2.1/§2.3/§2.5/§2.9/§2.11/§2.16: 总控直接调 plan / standards /
        # template / guard / prompt-archive / worker-archive 这些 omnicompany 内容,
        # 通过 ctx.allowed_write_roots 限定路径, 写不了代码 (.py/.ts) 也写不了核心层.
        WriteFileRouter,
        EditRouter,
    ]
    NODE_PROMPT: ClassVar[str] = _SYSTEM_PROMPT

    # ── workspace_root 推导 (跟 prompt_builder 一致) ────────────────────
    # 用来构造 allowed_write_roots 的绝对路径
    @staticmethod
    def _workspace_root() -> str:
        # 委托到唯一权威 core.config.omni_workspace_root(), 不再硬编码 parents[N]
        from omnicompany.core.config import omni_workspace_root
        return str(omni_workspace_root())

    # 默认 LLM 模型 → 收敛到 model_resolver 单一权威 (用户 U-034: 总控走 claude 旗舰).
    DEFAULT_MODEL: ClassVar[str] = CONTROLLER_DEFAULT_MODEL

    def __init__(self, *, bus: Any = None, model: str | None = None) -> None:
        """OmniAgentProvider 在 connect 时调 agent_class(bus=bus, model=opts.get('model')).

        bus / model 都可为 None (兜底建 MemoryBus + DEFAULT_MODEL).

        model 优先级:
        - 用户在前端选了 model (e.g. 'gpt-5.4') → 用 LLMClient(model=...)
          直接走 the_company 聚合 API 对应那个模型
        - 没指定 model → 走 DEFAULT_MODEL = 'claude-opus-4-7' (the_company 聚合 API 也走 claude opus)

        AgentNodeLoop 内部见到 role 会优先 role 忽略 model, 所以这里只用 model 不用 role.
        """
        from omnicompany.bus.memory import MemoryBus

        kwargs: dict[str, Any] = {
            "bus": bus or MemoryBus(),
            "model": model or self.DEFAULT_MODEL,
        }
        super().__init__(**kwargs)

    # ── Router 装配 (AgentNodeLoop 抽象方法) ─────────────────────────

    def build_prompt_builder(self, *, bus: Any) -> ControllerPromptBuilder:
        return ControllerPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ControllerExtractResult:
        return ControllerExtractResult(bus=bus)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        """块 2 落实: 给总控的 write_file / edit 工具注入 allowed_write_roots 白名单.

        用户原话 §2.1/§2.3/§2.5/§2.9/§2.11/§2.16:
        - 总控**直接**起草修改 plan + todo + project (§2.1)
        - 总控**直接**调整 template + standards (§2.3)
        - 总控**直接**调整 guard (§2.5; 含自己的 guard)
        - 总控**直接**记录 plan 完成情况 (§2.9)
        - 总控**直接**记录整理 prompt + worker 内容 (§2.11)
        - 总控**直接**更新 plan 进度 todo (§2.16)

        用户原话 §2.14/§2.17:
        - 总控**不**直接修代码 (subagent 的活)
        - 总控**不**直接修 omnicompany 核心层 (稳定 subagent 的活)

        白名单覆盖前者; 后者通过排除路径 + 不暴露 Bash/NotebookEdit 工具落实.
        """
        ctx_data = super().build_tool_context(
            input_data=input_data, turn=turn, trace_id=trace_id,
        )
        ws = Path(self._workspace_root())
        ctx_data["allowed_write_roots"] = (
            # plan / project (§2.1, §2.16)
            str(ws / "docs" / "plans"),
            # standards (§2.3)
            str(ws / "docs" / "standards"),
            # template (§2.3) — omnicompany 自带 templates/ 目录
            str(ws / "templates"),
            # 总控自家 archive (data/boss_sight/)
            #   - proposals/    (propose_change 持久化, 块 1 设计)
            #   - prompt_archive/ + worker_archive/ (§2.11 管理 prompt + worker 内容)
            #   - plan_completion_log/ (§2.9 记录 plan 完成情况)
            #   - state/       (总控运行状态)
            str(ws / "data" / "boss_sight"),
            # 自己 prompts/ 写不写? 用户原话 §3.1 prompt 由外部维护会话维护 →
            # 不能自改. 不放入白名单.
        )
        return ctx_data


__all__ = ["BossSightControllerWorker"]
