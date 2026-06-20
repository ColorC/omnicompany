# [OMNI] origin=claude-code domain=runtime/info_audit/fallback ts=2026-04-09T00:00:00Z
# [OMNI] material_id="material:runtime.info_audit.fallback.universal_loop.py"
# [OMNI] migrated 2026-05-02: 旧 omnicompany.runtime.agent.agent_node_loop.AgentNodeLoop 已 deprecate, 现用 packages.services._core.agent.AgentNodeLoop
"""UniversalFallbackLoop — 信息审计兜底执行器。

设计上下文 (2026-04-09):

  Phase 3 runner 在节点执行完毕后, 若 info_audit 报 missing_critical 非空且
  全局开关打开, 会记录一条 `fallback_trigger`。Phase 4 是**真正消费** 这些
  trigger 的地方: 用 AgentNodeLoop + 严格受限的只读工具 + 单一输出文件约束,
  去捞缺失的信息或给出补救产出。

用户约束 (2026-04-09 反馈):

  1. **安全网按调用点灵活制定**。默认: 只允许阅读/检索, 拒绝一切写入。
     Bash 只允许只读/查找命令。同时只允许一个输出文件。
  2. **guarded_write 不走 LLM**, 规则判定是否破坏自身。
  3. **无周告警**(只做单次拒绝反馈)。

核心原则:

  - fallback 不是"修复节点产出" —— 它是"把缺失的信息整理到一个 scratch 文件,
    供人类或下一次重跑参考"。不碰原节点产出, 不碰仓库真代码。
  - 单次 fallback 只有**一个输出文件**, 强制规则引擎级单通道。
  - 所有 LLM 调用依然走 LLMClient → audit 链条, 自动写入 llm_audit jsonl。

典型调用:

    config = FallbackConfig(
        trigger={
            "node_id": "req_analyzer",
            "missing_critical": ["目标 Excel config_table的完整 Schema 定义"],
            "sufficiency": "partial",
        },
        scratch_dir=Path("data/scratch/fallback/trace_X"),
    )
    loop = UniversalFallbackLoop()
    result = await loop.handle(config)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from omnicompany.core.config import _project_root, resolve_runtime_data_dir
from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.agent.agent_loop_config import LoopConfig, PRESET_STANDARD
from omnicompany.packages.services._core.agent import AgentNodeLoop
from omnicompany.packages.services._core.agent import GrepRouter, ReadFileRouter, ListDirRouter, GlobRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    SingleToolRouter,
    ToolContext,
    ToolExecutionError,
)
from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
from omnicompany.packages.services._core.agent.routers.dev_bash import _matches_danger
from omnicompany.runtime.info_audit.guarded_write import (
    GuardedWriteResult,
    guarded_write,
    validate_readonly_bash,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# 配置 / 结果
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class FallbackConfig:
    """单次 fallback 运行的完整配置。

    必填:
      trigger        — runner 的 fallback_trigger dict (含 node_id, missing_critical, ...)

    可选 (有合理默认):
      scratch_dir           — 本次 fallback 的工作目录 (内含唯一输出文件)
      max_turns             — AgentNodeLoop 单次上限 (默认 30)
      wall_clock_s          — 总时长上限 (默认 300s / 5min)
      scratch_max_bytes     — 输出文件字节上限 (默认 100KB)
      extra_read_roots      — 额外允许只读访问的目录 (默认 = 项目根下所有)
      custom_tools          — 追加的自定义工具 (默认空)
      model                 — LLM 模型 (默认 None, 用 runtime_main role)
      description_hint      — 给 Agent 的任务说明补充
    """

    trigger: dict
    scratch_dir: Path | None = None
    max_turns: int = 30
    wall_clock_s: float = 300.0
    scratch_max_bytes: int = 100 * 1024
    custom_tools: list = field(default_factory=list)
    """追加的自定义工具 (默认空)。迁移后不再使用 ToolDefinition, 此字段保留兼容。"""
    model: str | None = None
    description_hint: str = ""


@dataclass
class FallbackResult:
    status: str  # "found" / "not_found" / "error" / "timeout"
    output_path: str
    summary: str
    turns_used: int = 0
    elapsed_s: float = 0.0
    reject_log: list[str] = field(default_factory=list)
    """记录 agent 被 guarded_write 或 bash 校验拒绝的历史 (供诊断/审计)。"""


# ─────────────────────────────────────────────────────────────────────────────
# AgentNodeLoop 子类 - 受限只读探索器 (迁移后)
# ─────────────────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = """\
你是一个严格受限的"信息缺口探索员"。

## 你的处境

上游节点刚跑完, 但它报告了一些**关键信息缺失**。你的任务**不是修复它的产出**,
而是**调查这些缺失项**, 把找到的资料整理到一个指定的输出文件里, 供人类或
下一次重跑参考。

## 你拥有的工具 (都是只读的)

- read_file   : 读取一个文件
- grep        : 跨文件内容搜索
- glob        : 文件路径模式匹配
- list_dir    : 列出目录内容
- bash        : 只能运行只读命令 (ls/find/grep/cat/git log 等), 任何写入命令会被拒绝
- save_scratch: 将你的调查结论写入**唯一的**输出文件 (调用一次即可, 覆盖写入)
- think       : 把复杂推理写下来 (不执行任何操作)
- finish      : 完成任务, 返回你的摘要

## 硬性约束

1. **你只有一个输出文件**, 必须通过 `save_scratch` 写入, 不能写任何其他位置
2. `save_scratch` 每次覆盖写入, 所以一定要把所有结论整理好再一次性写
3. 禁止任何有副作用的操作: 不改代码, 不改配置, 不执行修复
4. 禁止网络操作: 不 curl, 不 wget, 不 ssh
5. 最多 30 轮对话; 超过会强制终止
6. 发现无法找到缺失信息时, 诚实在输出文件里写 "未找到", 然后 finish

## 输出文件格式建议 (markdown)

```
# Fallback Report

## Trigger
- node: <上游节点 id>
- missing: <上游标记的 critical 缺失>

## Investigation
- 查了哪些路径 / 搜了什么关键词 / 发现了什么

## Findings
- 每个 missing 项的调查结论 (找到 / 未找到 / 部分)

## Next Steps (给人类的建议)
- 下一步怎么用这份报告
```

## 开始

上游的原始 fallback trigger 和缺失清单已在下一条 user message 里。
开始调查, 最后用 `save_scratch` + `finish` 结束。
"""


# ═══════════════════════════════════════════════════════════
# 动态工具 Router — save_scratch
# ═══════════════════════════════════════════════════════════


class _SaveScratchRouter(SingleToolRouter):
    """动态 save_scratch 工具 Router。

    每次 fallback 调用时，从 ToolContext 的 __dict__ 读取:
      - allowed_output: 唯一允许写入的路径
      - scratch_max_bytes: 输出文件字节上限
      - reject_log: list[str] 记录拒绝事件
      - trace_id: 审计 trace ID
    """

    TOOL_NAME: ClassVar[str] = "save_scratch"
    DESCRIPTION: ClassVar[str] = (
        "把本次调查结论写入唯一的输出文件. "
        "每次调用会覆盖之前的内容, 所以建议收集完所有信息后再一次性写. "
        "其他路径会被拒绝。"
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "Markdown 格式的完整调查报告",
            },
        },
        "required": ["content"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = False

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        content = args.get("content", "")
        if not isinstance(content, str):
            return "save_scratch rejected: content 必须是字符串"

        allowed_output = getattr(ctx, "allowed_output", None)
        scratch_max_bytes: int = getattr(ctx, "scratch_max_bytes", 100 * 1024)
        reject_log: list[str] = getattr(ctx, "reject_log", [])
        trace_id = getattr(ctx, "trace_id", "")

        if not allowed_output:
            raise ToolExecutionError(
                "save_scratch: allowed_output not set in tool context. "
                "This is an internal error — contact the framework maintainer."
            )

        r: GuardedWriteResult = guarded_write(
            target_path=allowed_output,
            content=content,
            allowed_output=allowed_output,
            trace_id=trace_id,
            max_bytes=scratch_max_bytes,
        )

        if r.status == "ok":
            return f"save_scratch OK: {r.bytes_written} bytes 写入 {allowed_output}"

        reject_log.append(r.reason)
        return f"save_scratch REJECTED: {r.reason}"


# ═══════════════════════════════════════════════════════════
# 动态工具 Router — bash (只读)
# ═══════════════════════════════════════════════════════════


class _ReadonlyBashRouter(SingleToolRouter):
    """动态 bash 工具 Router — 只读模式。

    复用 DevBashRouter 的 cwd 白名单 + 命令黑名单守卫，
    额外增加 validate_readonly_bash 只读校验。
    从 ToolContext 读取 allowed_bash_roots / reject_log。
    """

    TOOL_NAME: ClassVar[str] = "bash"
    DESCRIPTION: ClassVar[str] = (
        "执行只读 shell 命令 (ls/find/grep/cat/git log/head/tail/wc 等). "
        "禁止任何写入/删除/执行/网络操作。尝试执行这些操作会被拒绝。"
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "要执行的只读命令",
            },
            "description": {
                "type": "string",
                "description": "简短说明这条命令在做什么",
            },
        },
        "required": ["command"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        command = args.get("command", "")
        reject_log: list[str] = getattr(ctx, "reject_log", [])

        # 1. 只读校验
        ok, why = validate_readonly_bash(command)
        if not ok:
            reject_log.append(why)
            return f"bash REJECTED: {why}"

        # 2. 危险模式黑名单
        danger = _matches_danger(command)
        if danger:
            return f"bash REFUSED: command matches dangerous pattern `{danger}`."

        # 3. cwd 白名单校验
        allowed_bash_roots = getattr(ctx, "allowed_bash_roots", None) or ()
        if not allowed_bash_roots:
            raise ToolExecutionError(
                "bash REFUSED: no allowed_bash_roots declared in tool context."
            )

        cwd_abs = Path(_project_root()).resolve()
        root_ok = False
        for r in allowed_bash_roots:
            try:
                rr = Path(r).resolve()
                cwd_abs.relative_to(rr)
                root_ok = True
                break
            except (ValueError, Exception):
                continue

        if not root_ok:
            raise ToolExecutionError(
                f"bash REFUSED: cwd `{cwd_abs}` is outside allowed_bash_roots."
            )

        # 4. 执行 (复用 DevBashRouter 的 subprocess 逻辑)
        import os as _os
        import shutil as _shutil
        import subprocess as _subprocess

        bash_path = _shutil.which("bash") or "/usr/bin/bash"
        timeout = 120
        try:
            popen_kwargs = dict(
                cwd=str(cwd_abs),
                stdout=_subprocess.PIPE,
                stderr=_subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if _os.name == "nt":
                popen_kwargs["creationflags"] = _subprocess.CREATE_NEW_PROCESS_GROUP
            else:
                popen_kwargs["start_new_session"] = True
            proc = _subprocess.Popen([bash_path, "-c", command], **popen_kwargs)
        except Exception as e:
            raise ToolExecutionError(f"Popen failed: {e}")

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            returncode = proc.returncode
            timed_out = False
        except _subprocess.TimeoutExpired:
            try:
                if _os.name == "nt":
                    _subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                        capture_output=True, timeout=10,
                    )
                else:
                    _os.killpg(_os.getpgid(proc.pid), 9)
            except Exception:
                pass
            try:
                stdout, stderr = proc.communicate(timeout=2)
            except _subprocess.TimeoutExpired:
                stdout, stderr = "", ""
                try:
                    proc.kill()
                except Exception:
                    pass
            returncode = -9
            timed_out = True

        stdout = (stdout or "").rstrip("\n")
        stderr = (stderr or "").rstrip("\n")

        _MAX_STREAM = 5 * 1024 * 1024

        def _truncate(s: str, label: str) -> str:
            if len(s) <= _MAX_STREAM:
                return s
            cut = len(s) - _MAX_STREAM
            return s[:_MAX_STREAM] + f"\n\n[TRUNCATED · {label} 截断 {cut} bytes (上限 5 MiB)]"

        stdout = _truncate(stdout, "stdout")
        stderr = _truncate(stderr, "stderr")

        if timed_out:
            raise ToolExecutionError(
                f"bash TIMEOUT after {timeout}s (killed). Command: `{command[:120]}...`"
            )

        parts = []
        if stdout:
            parts.append(stdout)
        if stderr:
            parts.append(f"[stderr]\n{stderr}")
        parts.append(f"[exit={returncode}]")
        return "\n".join(parts)


# ═══════════════════════════════════════════════════════════
# _FallbackExplorerLoop — 迁移后的 AgentNodeLoop 子类
# ═══════════════════════════════════════════════════════════


class _FallbackExplorerLoop(AgentNodeLoop):
    """内部用的 AgentNodeLoop 子类 - 组装受限工具集。

    迁移变更 (2026-05-02):
    - 基类: AgentNodeLoop (packages.services._core.agent)
    - TOOLS → TOOL_ROUTERS: [ReadFileRouter, GrepRouter, GlobRouter,
      ListDirRouter, _SaveScratchRouter, _ReadonlyBashRouter]
    - ThinkTool: 已移除 (新架构无对应 Router, Agent 内部思考)
    - SYSTEM_PROMPT → NODE_PROMPT (内容逐字保留)
    - build_initial_messages: 使用默认 PromptBuilderRouter (原逻辑等价)
    - extract_result → 默认 ExtractResultRouter (原逻辑只返回 PASS, 详细 status 由外层填)
    - build_tool_context: 注入 allowed_output / reject_log / allowed_bash_roots 等动态状态
    """

    NODE_PROMPT: ClassVar[str] = _SYSTEM_PROMPT
    TOOL_ROUTERS: ClassVar[list[type[SingleToolRouter]]] = [
        ReadFileRouter,
        GrepRouter,
        GlobRouter,
        ListDirRouter,
        _SaveScratchRouter,
        _ReadonlyBashRouter,
    ]
    LOOP_CONFIG: ClassVar[LoopConfig] = PRESET_STANDARD
    DESCRIPTION: ClassVar[str] = "UniversalFallbackLoop 内部受限探索器"
    FORMAT_IN: ClassVar[str] = "fallback.trigger"
    FORMAT_OUT: ClassVar[str] = "fallback.scratch_report"

    def __init__(
        self,
        *,
        allowed_output: Path,
        scratch_max_bytes: int,
        trace_id: str,
        reject_log: list[str],
        model: str | None = None,
        bus: Any | None = None,
        config: LoopConfig | None = None,
    ):
        super().__init__(model=model, bus=bus, config=config)
        # 动态工具状态 — 通过 build_tool_context 注入到 ToolContext.__dict__
        self._allowed_output = str(allowed_output)
        self._scratch_max_bytes = scratch_max_bytes
        self._trace_id = trace_id
        self._reject_log = reject_log

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        """注入动态工具需要的 per-invocation 状态。

        新架构下 ToolContext 由 SingleToolRouter._build_ctx() 从 dict 构造，
        未知字段透传到 __dict__。这里注入:
        - allowed_output: _SaveScratchRouter 用
        - scratch_max_bytes: _SaveScratchRouter 用
        - reject_log: _SaveScratchRouter / _ReadonlyBashRouter 用 (同一 list 引用)
        - trace_id: guarded_write 日志用
        - allowed_bash_roots: _ReadonlyBashRouter 用
        """
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["allowed_output"] = self._allowed_output
        ctx["scratch_max_bytes"] = self._scratch_max_bytes
        ctx["reject_log"] = self._reject_log
        ctx["trace_id"] = self._trace_id
        # bash cwd 白名单: 项目根 + /tmp/
        ctx["allowed_bash_roots"] = (
            str(_project_root()),
            "/tmp",
        )
        return ctx


# ─────────────────────────────────────────────────────────────────────────────
# UniversalFallbackLoop — 对外入口
# ─────────────────────────────────────────────────────────────────────────────


class UniversalFallbackLoop:
    """信息审计兜底执行器的对外入口。

    用法:
        loop = UniversalFallbackLoop()
        result = await loop.handle(FallbackConfig(trigger=..., ...))
    """

    def __init__(self) -> None:
        pass

    async def handle(self, config: FallbackConfig) -> FallbackResult:
        """执行一次 fallback, 返回 scratch 报告路径。

        永不抛异常 — 所有失败转为 FallbackResult(status=error/timeout/...)。
        """
        t0 = time.time()
        trace_id = config.trigger.get("trace_id", "no-trace")
        node_id = config.trigger.get("node_id", "unknown")

        # 1. 解析 scratch_dir 和唯一输出文件路径
        # 2026-04-21 B4: data/scratch_fallback/ → data/_runtime/scratch_fallback/
        # 原 resolve_db_dir 会生成 data/<name>/ 违反 archmap.yaml forbid_new_subdirs
        scratch_dir = config.scratch_dir or (
            resolve_runtime_data_dir("scratch_fallback") / trace_id
        )
        scratch_dir.mkdir(parents=True, exist_ok=True)
        allowed_output = scratch_dir / f"{node_id}.md"

        reject_log: list[str] = []

        # 2. 构造 loop_config (max_turns + wall_clock)
        loop_cfg = LoopConfig(
            max_turns=config.max_turns,
            budget_warning_threshold=PRESET_STANDARD.budget_warning_threshold,
        )

        # 3. 构造 AgentNodeLoop + 用户 prompt
        user_prompt = _build_user_prompt(config)

        try:
            loop = _FallbackExplorerLoop(
                allowed_output=allowed_output,
                scratch_max_bytes=config.scratch_max_bytes,
                trace_id=trace_id,
                reject_log=reject_log,
                model=config.model,
                bus=None,  # fallback 场景不需要事件总线
                config=loop_cfg,
            )
        except Exception as e:
            return FallbackResult(
                status="error",
                output_path=str(allowed_output),
                summary=f"fallback loop 构造失败: {e}",
                elapsed_s=time.time() - t0,
                reject_log=reject_log,
            )

        # 4. 执行, 带 wall-clock 超时
        try:
            verdict = await asyncio.wait_for(
                loop.run({"user_prompt": user_prompt}),
                timeout=config.wall_clock_s,
            )
        except asyncio.TimeoutError:
            return FallbackResult(
                status="timeout",
                output_path=str(allowed_output) if allowed_output.exists() else "",
                summary=f"fallback 超时 (wall_clock={config.wall_clock_s}s)",
                elapsed_s=time.time() - t0,
                reject_log=reject_log,
            )
        except Exception as e:
            return FallbackResult(
                status="error",
                output_path=str(allowed_output) if allowed_output.exists() else "",
                summary=f"fallback loop 执行异常: {e}",
                elapsed_s=time.time() - t0,
                reject_log=reject_log,
            )

        elapsed = time.time() - t0

        # 5. 判定 status: 输出文件是否有内容
        if allowed_output.exists() and allowed_output.stat().st_size > 0:
            status = "found"
            summary_text = f"scratch 报告已写入 {allowed_output}"
        else:
            status = "not_found"
            summary_text = "fallback 完成但未产出 scratch 报告 (agent 没调用 save_scratch)"

        return FallbackResult(
            status=status,
            output_path=str(allowed_output),
            summary=summary_text,
            elapsed_s=elapsed,
            reject_log=reject_log,
        )


def _build_user_prompt(config: FallbackConfig) -> str:
    trigger = config.trigger
    node_id = trigger.get("node_id", "?")
    missing = trigger.get("missing_critical") or []
    sufficiency = trigger.get("sufficiency", "?")

    lines = [
        "# Fallback Task",
        "",
        f"上游节点 **{node_id}** 刚跑完, 它的信息审计报告为 `sufficiency={sufficiency}`, ",
        f"并标记了 {len(missing)} 条**关键缺失**。你的任务是调查这些缺失项, 整理到 scratch 输出文件。",
        "",
        "## 关键缺失清单",
    ]
    for i, m in enumerate(missing, 1):
        lines.append(f"{i}. {m}")
    if config.description_hint:
        lines.append("")
        lines.append("## 额外说明")
        lines.append(config.description_hint)
    lines.append("")
    lines.append(
        "请用上述只读工具调查这些缺失项, 然后用 `save_scratch` 把调查结论写入唯一的输出文件, "
        "最后调用 `finish` 结束。发现无法找到的项请在输出文件里老实标注 '未找到'。"
    )
    return "\n".join(lines)
