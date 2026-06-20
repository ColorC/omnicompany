# [OMNI] origin=claude-code domain=services/agent ts=2026-04-18
# [OMNI] material_id="material:core.agent.node_loop_scheduler.implementation.py"
"""AgentNodeLoop — 薄调度器 Router

承诺（plan §0.1 + §10.5.1 E7）：
- 本类**不含** LLMClient 直调 / ToolDefinition.call 直调 / compact 函数直调
- 主循环方法 < 100 行
- 所有数据流走 Format + bus
- trace_id 贯穿所有 Router 的 input / output 事件

每轮循环依次 `await`：
  1. context_compact   (agent.context-request → agent.context-compacted)
  2. llm_call          (agent.llm-request     → agent.llm-response)
  3. 无 tool_uses 或 finish → extract_result (退出循环)
  4. 有 tool_uses → tool_dispatch.run() × N  (agent.tool-request → agent.tool-response)
  5. 把 tool_result 拼进 messages，回到第 1 步

首轮（循环前）：
  0. prompt_builder    (agent.prompt-request  → agent.prompt-built)

预算耗尽：
  * 发 agent.budget_exhaust 信号，调用 extract_result 返回 PARTIAL
"""

from __future__ import annotations

import logging
import threading
import uuid
from typing import Any, ClassVar

from omnicompany.protocol.anchor import Verdict
from omnicompany.runtime.routing.router import Router
from omnicompany.runtime.agent.agent_loop_config import LoopConfig, PRESET_STANDARD
from omnicompany.packages.services._core.agent._bus import emit_agent_signal
from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
from omnicompany.packages.services._core.agent.routers.context_compact import ContextCompactRouter
from omnicompany.packages.services._core.agent.routers.llm_call import LLMCallRouter
from omnicompany.packages.services._core.agent.routers.tool_dispatch import ToolDispatchRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    SingleToolRouter,
    FinishRouter,
)
from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter

logger = logging.getLogger(__name__)


class AgentNodeLoop(Router):
    """薄调度器 Router（<100 行主循环）。

    子类通常只需声明 NODE_PROMPT / TOOL_ROUTERS，override build_prompt_builder /
    build_extract_result 就能跑起来。
    """

    # ── 子类可覆盖的元数据 ──
    NODE_PROMPT: ClassVar[str] = ""
    TOOL_ROUTERS: ClassVar[list[type[SingleToolRouter]]] = []
    LOOP_CONFIG: ClassVar[LoopConfig] = PRESET_STANDARD
    ALLOW_NO_BUS: ClassVar[bool] = False

    # BD.6e 跨厂 LLM 容错扩展（CC 原生无此机制，因 Claude 会从 is_error 自愈；
    # qwen/DeepSeek 等跨厂 LLM 可能忽视 <tool_use_error> + is_error 反复原样重试）：
    # 同一工具连续 N 次 is_error=True → 强制退出到 extract_result 让 final_text fallback 救
    MAX_CONSECUTIVE_TOOL_ERRORS: ClassVar[int] = 3

    # BOSS SIGHT 块 4 引入: 子类可声明额外的"末步工具" — 调到就跟 finish 一样结束 loop.
    # 用途: 总控的 submit_response / team_supervisor 的 submit_health_criteria 等.
    # tool 仍正常执行 (返结果给 LLM 看), 但本轮结束不再调下一轮 LLM.
    # 默认空 tuple = 只 finish 终结 (旧行为, 不影响现有 worker).
    TERMINATING_TOOLS: ClassVar[tuple[str, ...]] = ()

    # ── Router 元数据 ──
    DESCRIPTION: ClassVar[str] = "AgentNodeLoop: Router 化后的薄调度器"

    def __init__(
        self,
        *,
        model: str | None = None,
        role: str | None = None,
        bus: Any | None = None,
        config: LoopConfig | None = None,
    ):
        if bus is None and not self.ALLOW_NO_BUS:
            raise RuntimeError(
                f"{type(self).__name__} requires an EventBus (bus=...). "
                f"Set ALLOW_NO_BUS=True on your subclass only for truly isolated smoke tests."
            )
        self._bus = bus
        self._config = config or self.LOOP_CONFIG
        # L5 协议状态: Read→Edit 状态机用. FileReadRouter 成功后 add abs_path,
        # FileEditRouter 检查 abs_path 必在该 set, 不在 → 报错指引"先 Read".
        # 同一 AgentNodeLoop 实例的所有工具调用共享这个 set.
        self._read_files: set[str] = set()
        # L7 abort/cancel 协议 (Wave 8 P3, 2026-05-05): 外部 (主 agent owner / 监督) 调
        # `agent.abort()` 设这个 event. 主循环每 turn 头检查; 长跑工具 (DevBashRouter
        # PersistentShellSession 等) 通过 ctx.abort_event 周期检查, 命中 → 杀子进程 + raise.
        # 用 threading.Event (不是 asyncio.Event) — _execute 跑在 to_thread worker 线程,
        # threading.Event.is_set() 跨线程安全; asyncio loop 也能 .is_set() 检查.
        self._abort_event: threading.Event = threading.Event()
        # L7 trace_id 跨工具串联 (P1.2, 2026-05-05): AgentRouter 派 sub-agent 时
        # 把子 trace_id append 进来, 主 agent extract_result 时 Verdict.output
        # 含 spawned_traces 字段, owner / 监督可按 trace 回溯子 agent 事件流.
        # bus 里事件已带 trace_id, 这个列表只是给上游拿到层级关系的索引.
        self._spawned_traces: list[str] = []

        # 工具 Router 实例（始终含 Finish）
        tool_classes = list(self.TOOL_ROUTERS)
        if not any(r.TOOL_NAME == "finish" for r in tool_classes):
            tool_classes.append(FinishRouter)
        tool_router_instances = [R(bus=bus) for R in tool_classes]

        # 子 Router 装配
        self._tool_dispatch = ToolDispatchRouter(tool_routers=tool_router_instances, bus=bus)
        self._prompt_builder = self.build_prompt_builder(bus=bus)
        self._context_compact = ContextCompactRouter(
            compact_cfg=self._config.compact, bus=bus,
        )
        self._llm_call = LLMCallRouter(
            model=model,
            role=role,
            tools_spec=self._tool_dispatch.tools_spec(),
            retry=self._config.retry,
            bus=bus,
            caller_prefix=type(self).__name__,
        )
        self._extract_result = self.build_extract_result(bus=bus)

    # ── 子类 override 点 ──

    def build_prompt_builder(self, *, bus: Any) -> PromptBuilderRouter:
        return PromptBuilderRouter(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ExtractResultRouter:
        return ExtractResultRouter(bus=bus)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        """构造每次 tool-request 的 context 字段。子类可 override 注入业务字段
        （如 prefab_name），业务 Router 从 ToolContext 读取用于 trace / allowlist / 分目录落盘等。

        默认含 read_files set 实例 (跨工具共享, FileRead/Edit 状态机用).
        子类 override 时若不调 super(), Read→Edit 协议在该子 agent 失效 — 是 OK 的,
        子类可自管或显式忽略.
        """
        return {
            "trace_id": trace_id,
            "turn_number": turn,
            "read_files": self._read_files,  # L5 协议: Read→Edit 状态机
            "abort_event": self._abort_event,  # L7 协议: 长跑工具 abort/cancel
            "spawned_traces": self._spawned_traces,  # L7 协议: 跨 sub-agent trace 收集
        }

    # ── L7 abort/cancel 公开接口 ───────────────────────────────────

    def abort(self) -> None:
        """从外部触发 abort. 当前 turn 的工具调用 + 后续 turn 都会接收到信号.

        长跑工具 (DevBashRouter / PersistentShellSession 等) 周期检查 ctx.abort_event,
        命中 → 杀子进程 + raise ToolExecutionError("aborted").

        主循环每 turn 头检查, 命中 → break + extract_result PARTIAL.

        线程安全: threading.Event 跨 thread + asyncio loop 都 OK.
        """
        self._abort_event.set()

    def is_aborted(self) -> bool:
        return self._abort_event.is_set()

    def reset_abort(self) -> None:
        """清 abort flag, 准备下一轮调用. 通常 owner 调 abort 后 wait extract 出来,
        再调 reset_abort 才能下次 .run()."""
        self._abort_event.clear()

    async def on_turn_end_async(
        self, *, turn: int, messages: list[dict], trace_id: str,
    ) -> None:
        """每轮末尾 async 钩子（2026-04-18 晚为双脑 lockstep 架构新加）。

        调用时机：tool_result 已拼回 messages、agent.turn.end 信号已发、熔断检查之前。
        默认空操作；子类可 override 做"后轮注入"，典型场景：
          - lockstep 子类提交本轮观察给反思脑 daemon，拿到 substitutions 注入 messages
          - 审计子类把本轮 messages 快照外发给监督 agent

        约定：允许原位修改 messages（新追加的 user message 会进下一轮 context_compact）。
        """
        return

    async def on_tool_dispatch_start(
        self, *, tool_name: str, tool_args: dict, tool_use_id: str, turn: int, trace_id: str,
    ) -> None:
        """工具调用**前**钩子（2026-04-24 新增 · for 实时 UI 更新 · 默认空）.

        用途: 子类 override 把 (tool_name, tool_args) 推给外部 UI (如collab platform流式卡片),
        同事能看到 "agent 正在调 grep ...".
        """
        return

    async def on_tool_dispatch_end(
        self, *, tool_name: str, tool_use_id: str, result: str, is_error: bool,
        turn: int, trace_id: str,
    ) -> None:
        """工具调用**后**钩子（2026-04-24 新增）.

        result 是 tool 返回的文本 (可能很长 · UI 侧自己截断展示).
        """
        return

    # ── Router 入口 ──

    async def _signal(self, trace_id: str, event_type: str, payload: dict) -> None:
        await emit_agent_signal(
            self._bus, trace_id=trace_id, event_type=event_type,
            source=f"agent.{type(self).__name__}", payload=payload,
        )

    async def run(self, input_data: Any) -> Verdict:
        if not isinstance(input_data, dict):
            input_data = {}
        trace_id = input_data.get("trace_id") or input_data.get("session_id") or str(uuid.uuid4())
        cfg = self._config
        await self._signal(trace_id, "agent.loop.start", {"max_turns": cfg.max_turns})

        # 2026-04-18 晚：同步写入身份到每个 tool Router 的 executor。
        # 旧 AgentNodeLoop 在 run() 设 self._executor.origin/domain/agent_name，
        # 这些值被 tool_executor 内部写入（str_replace_editor/create 等）传给 guarded_write。
        # 新薄调度器下工具是独立 Router 实例，各自持有 executor，必须逐一同步。
        _origin = input_data.get("origin", "claude-code")
        _domain = input_data.get("domain", "")
        _agent_name = input_data.get("agent_name", type(self).__name__)
        for tr in self._tool_dispatch.routers:
            ex = getattr(tr, "_executor", None)
            if ex is not None:
                ex.origin = _origin
                ex.domain = _domain
                ex.agent_name = _agent_name

        # 0. Prompt 构造
        prompt_v = await self._prompt_builder.run({
            "input_data": input_data, "node_prompt_template": self.NODE_PROMPT, "trace_id": trace_id,
        })
        messages: list[dict] = list(prompt_v.output["initial_messages"])
        system: str = prompt_v.output["system_prompt"]
        # BD.6e 熔断状态：同一工具连续 is_error 计数
        consecutive_errors_by_tool: dict[str, int] = {}

        async def _finish(final_text: str, turn_count: int, reason: str) -> Verdict:
            await self._signal(trace_id, "agent.loop.finish", {"turn_count": turn_count, "reason": reason})
            verdict = await self._extract_result.run({
                "messages": messages, "final_text": final_text,
                "turn_count": turn_count, "stop_reason": reason, "trace_id": trace_id,
            })
            # P1.2 (2026-05-05): 把派生的 sub-agent trace_id 列表暴露在 Verdict.output,
            # owner / 监督拿到主 trace 后能按 trace 回溯所有 sub-agent 事件流.
            if isinstance(verdict.output, dict) and self._spawned_traces:
                verdict.output.setdefault("spawned_traces", list(self._spawned_traces))
            return verdict

        for turn in range(cfg.max_turns):
            # L7 abort 检查 (Wave 8): 每 turn 头检查 abort, 命中 → 走 PARTIAL extract
            if self._abort_event.is_set():
                await self._signal(trace_id, "agent.aborted", {"turn": turn})
                final_text = _extract_last_assistant_text(messages)
                return await _finish(final_text, turn, "aborted")
            await self._signal(trace_id, "agent.turn.start", {"turn": turn})
            # 1. Context 压缩
            ctx_v = await self._context_compact.run({
                "messages": messages, "compact_cfg": cfg.compact,
                "context_window": cfg.context_window, "turn": turn, "trace_id": trace_id,
            })
            messages = list(ctx_v.output["messages"])
            # 2. LLM 调用
            llm_v = await self._llm_call.run({
                "messages": messages, "system_prompt": system,
                "tools_spec": self._tool_dispatch.tools_spec(),
                "turn": turn, "trace_id": trace_id,
            })
            tool_uses: list[dict] = llm_v.output.get("tool_uses", [])
            messages.append(llm_v.output["assistant_message"])
            text: str = llm_v.output.get("text", "")
            # 3. 收尾：无 tool_uses 或 finish
            finish_call = next((tu for tu in tool_uses if tu["tool_name"] == "finish"), None)
            # BD: no_tool_calls 在前 3 轮时给一次重试机会 (LLM 偶发不调工具直接 finish 是常见 bug)
            # 只对 turn < 3 重试, 后期 finish 应被尊重 (agent 真完成了)
            if not tool_uses and not finish_call and turn < 3 and text and len(text) < 500:
                logger.warning(f"agent 第 {turn+1} 轮未调任何工具且 text 仅 {len(text)} 字节 — 注入提示重试")
                messages.append({
                    "role": "user",
                    "content": (
                        f"[SYSTEM_RETRY] 你这一轮没调任何工具就停了, 输出只 {len(text)} 字节. "
                        f"按 NODE_PROMPT 流程, 你必须先调工具 (cat / ls / grep / lark-cli / write_file 等). "
                        f"不要直接给文字回答. 重新决定下一步该调什么工具."
                    ),
                })
                continue
            if not tool_uses or finish_call:
                final_text = finish_call["tool_args"].get("result", text) if finish_call else text
                return await _finish(final_text, turn + 1, "finish_tool" if finish_call else "no_tool_calls")
            # BOSS SIGHT 块 4: 子类声明的 TERMINATING_TOOLS 命中也结束 loop. 工具结果仍要
            # 执行 (让 LLM 看到 tool_result), 但工具调完后不再喂回 LLM 让它"再想一轮".
            # 处理顺序: 先正常跑工具 (落 tool_result), 然后跳出 loop 让 extract_result 收割.
            terminating_tu = None
            if self.TERMINATING_TOOLS:
                terminating_tu = next(
                    (tu for tu in tool_uses if tu["tool_name"] in self.TERMINATING_TOOLS),
                    None,
                )
            # 4. 工具调用
            tool_result_blocks = []
            tool_ctx = self.build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
            fused_tool: str | None = None   # BD.6e 熔断触发的工具名
            for tu in tool_uses:
                tname = tu["tool_name"]
                args = tu["tool_args"]
                # BD.6c: OpenAI function.arguments JSON 解析失败 → args 含 __parse_error
                # 不走真 tool dispatch（参数本身就错了），直接生成指导 LLM 修的错误 tool_result
                if isinstance(args, dict) and args.get("__parse_error"):
                    parse_err = args.get("__parse_error", "")
                    raw_args = args.get("__raw_args", "")
                    raw_len = len(raw_args) if isinstance(raw_args, str) else 0
                    err_content = (
                        f"[TOOL_ERROR] 你的 tool call arguments JSON 解析失败，工具**未被调用**。\n\n"
                        f"解析错误：{parse_err}\n"
                        f"原始 arguments 字符串长度：{raw_len} chars\n\n"
                        f"**常见原因**：\n"
                        f"1. 你生成的 JSON 被 max_tokens 截断（当前 output 可能 >8K tokens）\n"
                        f"2. 字符串里有未转义的 \\n / \" / \\\\ 等特殊字符\n"
                        f"3. Markdown 的代码块 ``` 需要转义\n\n"
                        f"**修复建议**：\n"
                        f"- 如果是长内容 tool (submit_findings/write_file)：压缩字符串（去掉过长段落、用简短 evidence）\n"
                        f"- 分多次小调用替代一次大调用\n"
                        f"- 确保 string 字段里所有 \" 和 \\ 都正确转义"
                    )
                    tool_result_blocks.append({
                        "type": "tool_result",
                        "tool_use_id": tu["tool_use_id"],
                        "content": err_content,
                        "is_error": True,
                    })
                    consecutive_errors_by_tool[tname] = consecutive_errors_by_tool.get(tname, 0) + 1
                    if consecutive_errors_by_tool[tname] >= self.MAX_CONSECUTIVE_TOOL_ERRORS:
                        fused_tool = tname
                    continue

                # 钩子: tool 调用前 (子类 override 可推 UI)
                try:
                    await self.on_tool_dispatch_start(
                        tool_name=tname, tool_args=args,
                        tool_use_id=tu["tool_use_id"], turn=turn, trace_id=trace_id,
                    )
                except Exception:
                    logger.exception("on_tool_dispatch_start hook crashed (non-fatal)")

                tr_v = await self._tool_dispatch.run({
                    "tool_name": tname, "tool_args": args,
                    "tool_use_id": tu["tool_use_id"], "turn": turn,
                    "context": tool_ctx,
                    "trace_id": trace_id,
                })
                block: dict[str, Any] = {
                    "type": "tool_result",
                    "tool_use_id": tr_v.output["tool_use_id"],
                    "content": tr_v.output["result"],
                }
                is_err = bool(tr_v.output.get("is_error"))
                if is_err:
                    block["is_error"] = True
                    consecutive_errors_by_tool[tname] = consecutive_errors_by_tool.get(tname, 0) + 1
                    if consecutive_errors_by_tool[tname] >= self.MAX_CONSECUTIVE_TOOL_ERRORS:
                        fused_tool = tname
                else:
                    consecutive_errors_by_tool[tname] = 0  # 成功重置
                tool_result_blocks.append(block)

                # 钩子: tool 调用后 (子类 override 可推 UI)
                try:
                    await self.on_tool_dispatch_end(
                        tool_name=tname, tool_use_id=tu["tool_use_id"],
                        result=str(tr_v.output.get("result", "")),
                        is_error=is_err, turn=turn, trace_id=trace_id,
                    )
                except Exception:
                    logger.exception("on_tool_dispatch_end hook crashed (non-fatal)")
            # 5. 拼回 messages
            messages.append({"role": "user", "content": tool_result_blocks})

            # 5.1 read_image 多模态: tool 把图挂到 ctx.pending_image_attachments,
            # 这里追加一条 user message 含 Anthropic image block, 让多模态主 agent
            # (qwen3.6-plus) 下一轮直接看图. LLMClient._anthropic_msgs_to_openai 会
            # 自动转成 OpenAI image_url 协议. tool_result message 本身不能含 image
            # (OpenAI tool message content 必须 string), 所以独立成一条 user message.
            pending_imgs = getattr(tool_ctx, "pending_image_attachments", None) or []
            if pending_imgs:
                img_content: list[dict[str, Any]] = []
                names_summary: list[str] = []
                for att in pending_imgs:
                    label = f"[图: {att.get('name', '?')}]"
                    if att.get("note"):
                        label = f"{label} {att['note']}"
                    img_content.append({"type": "text", "text": label})
                    img_content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": att.get("mime", "image/png"),
                            "data": att.get("base64", ""),
                        },
                    })
                    names_summary.append(att.get("name", "?"))
                messages.append({"role": "user", "content": img_content})
                await self._signal(
                    trace_id, "agent.read_image_attached",
                    {"turn": turn, "count": len(pending_imgs), "names": names_summary},
                )
                # 清空, 防下一轮重复挂
                pending_imgs.clear()

            await self._signal(trace_id, "agent.turn.end", {"turn": turn, "tool_calls": len(tool_uses)})

            # 5.5 on_turn_end_async 钩子（双脑 lockstep 等后轮注入场景）
            # 默认空；子类 override 后可向 messages 追加 user 消息（下一轮 compact 会看到）
            await self.on_turn_end_async(turn=turn, messages=messages, trace_id=trace_id)

            # BOSS SIGHT 块 4: TERMINATING_TOOLS 命中, 工具已正常跑完落 tool_result, 跳出 loop
            # 让 extract_result 收割 (它会扫 messages 找最后一个 submit_response tool_use input).
            if terminating_tu is not None:
                await self._signal(
                    trace_id, "agent.terminating_tool",
                    {"turn": turn, "tool_name": terminating_tu["tool_name"]},
                )
                final_text = _extract_last_assistant_text(messages)
                return await _finish(
                    final_text, turn + 1,
                    f"terminating_tool:{terminating_tu['tool_name']}",
                )

            # BD.6e 熔断：同一工具连续 is_error=True 达阈值 → 强制进 extract_result
            # 避免 LLM (qwen 等跨厂) 反复原样调错工具耗光预算
            if fused_tool is not None:
                await self._signal(
                    trace_id, "agent.tool_fuse",
                    {"turn": turn, "tool_name": fused_tool,
                     "consecutive_errors": consecutive_errors_by_tool[fused_tool]},
                )
                final_text = _extract_last_assistant_text(messages)
                return await _finish(
                    final_text,
                    turn + 1,
                    f"tool_fuse:{fused_tool}:consecutive_errors={consecutive_errors_by_tool[fused_tool]}",
                )

        # 6. 预算耗尽
        await self._signal(trace_id, "agent.budget_exhaust", {"max_turns": cfg.max_turns})
        return await _finish(_extract_last_assistant_text(messages), cfg.max_turns, "max_turns")


def _extract_last_assistant_text(messages: list[dict]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            content = msg.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                texts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                return "\n".join(texts)
    return ""
