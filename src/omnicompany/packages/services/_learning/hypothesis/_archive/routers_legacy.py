# [OMNI] origin=claude-code domain=services/hypothesis/_archive/routers_legacy.py ts=2026-04-20T00:00:00Z type=router status=active
# [OMNI] material_id="material:learning.hypothesis.agent_node_loops.router_definitions.py"
# OMNI-024 ALLOW: _archive/ 归档文件，Router 类不在标准位置属预期 (Phase D Diamond shortcut)
"""hypothesis.routers — 两个 agent 节点（v4：Routerization Phase C 迁移版）。

ExperimenterRouter (AgentNodeLoop):
  主 agent — 自由用 bash/read_file/glob/grep 探索，输出行为轨迹。

LockstepExperimenterRouter (extends ExperimenterRouter):
  双脑 lockstep 模式 — 每 turn 末同步等反思脑完成（on_turn_end_async），
  反思脑的 context_substitution 作为 user message 注入下一轮对话。

ReflectorRouter (AgentNodeLoop):
  总结 agent — 读 Experimenter 行为轨迹 + 当前假设文档；
  直接用 IDE 工具（read_file/edit/write_file/glob/grep）编辑 markdown + 格式校验。

2026-04-18 晚 Routerization Phase C 迁移：
  - 基类：runtime.agent.agent_node_loop.AgentNodeLoop（旧）→ packages.services.agent.AgentNodeLoop（新）
  - TOOLS → TOOL_ROUTERS（SingleToolRouter 子类）
  - SYSTEM_PROMPT → NODE_PROMPT（保留常量名别名便于理解）
  - build_initial_messages() → PromptBuilderRouter 子类 via build_prompt_builder()
  - extract_result() → ExtractResultRouter 子类 via build_extract_result()
  - LockstepExperimenterRouter.on_turn_end_async 签名对齐新基类 keyword-only
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, ClassVar

from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.agent.agent_loop_config import (
    CompactConfig,
    LoopConfig,
    PermissionConfig,
)
from omnicompany.runtime.agent.agent_loop_tools import ToolContext
from omnicompany.packages.services._core.agent import (
    AgentNodeLoop,
    ExtractResultRouter,
    GlobRouter,
    GrepRouter,
    PromptBuilderRouter,
    ReadFileRouter,
    SingleToolRouter,
    ToolExecutionError,
)

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════════════════
# hypothesis 域专用工具 Router（Phase C 迁移新增）
# ════════════════════════════════════════════════════════════════════════════

class BashRouter(SingleToolRouter):
    """bash 命令执行（复用 ToolExecutor.execute('bash', ...)）."""

    TOOL_NAME: ClassVar[str] = "bash"
    DESCRIPTION: ClassVar[str] = (
        "Executes a given bash command and returns its output.\n\n"
        "IMPORTANT: Avoid using this tool to run find, grep, cat, head, tail, sed, awk, or echo commands. "
        "Use the appropriate dedicated tool instead:\n"
        " - File search: Use glob (NOT find or ls)\n"
        " - Content search: Use grep (NOT grep or rg)\n"
        " - Read files: Use read_file (NOT cat/head/tail)\n"
        " - Edit files: Use edit (NOT sed/awk)\n"
        " - Write files: Use write_file (NOT echo >/cat <<EOF)\n\n"
        "Reserve bash for system commands and terminal operations (env checks, Python scripts, HTTP requests, etc.)."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "The command to execute"},
            "description": {"type": "string", "description": "Clear description of what this command does"},
            "timeout": {"type": "number", "description": "Optional timeout in milliseconds (max 600000)"},
            "run_in_background": {"type": "boolean", "description": "Set to true to run in background"},
        },
        "required": ["command"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = False

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        return self._executor.execute("bash", args)


class EditRouter(SingleToolRouter):
    """edit 精准字符串替换。走 guarded_write 审计层（replace_all 分支）
    或 ToolExecutor.str_replace_editor（单次替换）."""

    TOOL_NAME: ClassVar[str] = "edit"
    DESCRIPTION: ClassVar[str] = (
        "Performs exact string replacements in files.\n\n"
        "Usage:\n"
        "- You must use read_file at least once in the conversation before editing.\n"
        "- Preserve the exact indentation (tabs/spaces) as it appears in the file.\n"
        "- The edit will FAIL if old_string is not unique. Provide more surrounding context, or use replace_all.\n"
        "- Use replace_all for renaming strings across the file."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path to the file to modify"},
            "old_string": {"type": "string", "description": "The text to replace"},
            "new_string": {"type": "string", "description": "The text to replace it with (must be different)"},
            "replace_all": {"type": "boolean", "description": "Replace all occurrences (default false)", "default": False},
        },
        "required": ["file_path", "old_string", "new_string"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = False

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        path = args.get("file_path", args.get("path", ""))
        old_str = args.get("old_string", args.get("old_str", ""))
        new_str = args.get("new_string", args.get("new_str", ""))
        replace_all = args.get("replace_all", False)
        if not path:
            raise ToolExecutionError("file_path 必填")

        if replace_all:
            try:
                content = Path(path).read_text(encoding="utf-8")
            except Exception as exc:
                raise ToolExecutionError(f"读取文件失败：{exc}") from exc
            count = content.count(old_str)
            if count == 0:
                raise ToolExecutionError(f"old_string not found in {path}")
            from omnicompany.core.guarded_write import write_file
            try:
                write_file(
                    path, content.replace(old_str, new_str),
                    origin=ctx.origin or "claude-code",
                    domain=ctx.domain,
                    trace=ctx.trace_id,
                    node=ctx.node_id,
                    agent_name=ctx.agent_name,
                    purpose="edit replace_all",
                )
            except Exception as exc:
                raise ToolExecutionError(f"写入失败：{exc}") from exc
            return f"Replaced {count} occurrence(s) in {path}"

        # 单次替换走 ToolExecutor 的 str_replace_editor
        return self._executor.execute("str_replace_editor", {
            "command": "str_replace", "path": path,
            "old_str": old_str, "new_str": new_str,
        })


class WriteFileRouter(SingleToolRouter):
    """write_file 整份重写。走 guarded_write 审计层."""

    TOOL_NAME: ClassVar[str] = "write_file"
    DESCRIPTION: ClassVar[str] = (
        "Writes a file to the local filesystem.\n\n"
        "Usage:\n"
        "- Overwrites existing file at the provided path.\n"
        "- If editing an existing file, you MUST read_file first.\n"
        "- Prefer edit for modifying existing files — it only sends the diff."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "file_path": {"type": "string", "description": "Absolute path (must be absolute)"},
            "content": {"type": "string", "description": "The content to write to the file"},
        },
        "required": ["file_path", "content"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = False

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        path = args.get("file_path", args.get("path", ""))
        content = args.get("content", "")
        if not path:
            raise ToolExecutionError("file_path 必填")
        from omnicompany.core.guarded_write import write_file
        try:
            write_file(
                path, content,
                origin=ctx.origin or "claude-code",
                domain=ctx.domain,
                trace=ctx.trace_id,
                node=ctx.node_id,
                agent_name=ctx.agent_name,
                purpose=args.get("purpose", ""),
            )
        except Exception as exc:
            raise ToolExecutionError(f"写入失败：{exc}") from exc
        return f"Successfully wrote {len(content)} characters to {path}"


class FindSimilarFormatsRouter(SingleToolRouter):
    """find_similar_formats — 反哺工具（2026-04-19 §16）。

    给一段自然语言描述（如新写好的 format_in/out summary），在系统现有 FormatRegistry
    中找语义相似的 format，供 LLM 评估"是否语境充分相同 → 引用 / 合并 / 保持独立"。

    **使用时机**：**写完 format_in/out 之后**（不是之前！避免锚定偏差）。
    """

    TOOL_NAME: ClassVar[str] = "find_similar_formats"
    DESCRIPTION: ClassVar[str] = (
        "【反哺工具】在已注册 format 体系里找语义相关的候选。\n"
        "\n"
        "**使用时机**：你必须**先独立写完** format_in 或 format_out 描述，**再用本工具**找候选。\n"
        "先查再写会产生锚定偏差，导致你写的描述被现存 format 污染。\n"
        "\n"
        "输入：\n"
        "- `description`: 你刚写好的 format_in/out 的自然语言描述（一段话，越完整越准）\n"
        "- `top_k`: 可选，最多返回几个候选（默认 5）\n"
        "\n"
        "返回：JSON 数组，每个候选含 `id` / `name` / `description` / `relationship`。\n"
        "`relationship` 是自然语言描述——LLM 评估者用一段话说清"
        "**这个候选 format 和你的描述到底是什么关系**，包含：共同点 / 区别点 / 是否可替代等。\n"
        "**没有分数、没有标签**——自由描述，你自己读完判断如何影响下一步行为。\n"
        "返回空数组意味着系统判定无相关——你的假设很可能是全新的。\n"
        "\n"
        "【这个工具的目的】：给你提供 awareness——让你知道系统里有没有类似的东西，\n"
        "**以此影响你后续的判断和行为**（是否新建假设 / 是否调整粒度 / 是否继续探索）。\n"
        "\n"
        "**你的判断留在推理上下文里即可**。不需要在 markdown 里写 '相关于 X' 之类的标注——\n"
        "系统目前不做自动合并/链接（接受冗余原则，§3.9）。工具价值在于改变你的下一步决策，\n"
        "不在于产出字符串。"
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "刚写好的 format_in/out 自然语言描述（一段话）",
            },
            "top_k": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "description": "返回 Top K 候选，默认 5",
                "default": 5,
            },
        },
        "required": ["description"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        description = args.get("description", "").strip()
        top_k = int(args.get("top_k", 5))
        if not description:
            raise ToolExecutionError("description 必填（写一段完整描述再查询）")
        if len(description) < 20:
            raise ToolExecutionError(
                "description 太短（<20 字符）。先独立写完详细的 format_in/out 描述再来查询。"
            )
        try:
            result = find_similar_formats_core(description=description, top_k=top_k)
        except ValueError as exc:
            raise ToolExecutionError(str(exc)) from exc
        return json.dumps(result, ensure_ascii=False, indent=2)


def find_similar_formats_core(description: str, top_k: int = 5) -> dict:
    """纯函数：给定描述，返回 Top K 相似候选 dict。

    供两处复用：
    1. FindSimilarFormatsRouter（旧工具，可能保留或废弃）
    2. ReflectorRouter.on_turn_end_async 的自动反哺逻辑

    JSON 解析失败或返回非 list 时 raise ValueError。
    """
    formats = _load_all_registered_formats()
    if not formats:
        return {"candidates": [], "total_formats_searched": 0, "note": "format 体系尚无注册项"}

    from omnicompany.runtime.llm.llm import LLMClient
    candidates_payload = [
        {
            "id": f.id,
            "name": f.name,
            "description": f.description,
            "parent": f.parent,
            "tags": list(f.tags) if f.tags else [],
        }
        for f in formats
    ]
    system = (
        "你是 format 相似性评估助手。用户给你一段刚写好的 format 描述，你要从一个"
        "已注册 format 列表里挑出与之**有实际语义关联**的候选，并**自由描述每个候选"
        "和用户描述之间的关系**。\n\n"
        "输出要求：严格 JSON 数组，不要解释不要代码块。\n"
        "每个元素：{\"id\": \"format id\", \"relationship\": \"自由描述这个候选与用户描述的关系\"}\n\n"
        "**不要打分，不要用 equivalent/related 这类预设标签**。直接用自然语言写清：\n"
        "- 它们的共同点是什么\n"
        "- 它们的区别点是什么（粒度/上下文/场景/用途差异）\n"
        "- 是否可以互相替代、是否可以组合、是否完全是同一个东西\n"
        "让用户自己读 relationship 文字后判断下一步行为。\n\n"
        "排序按你认为的 relationship 显著程度，最重要的在前。最多返回 top_k 个。\n"
        "\n"
        "**保守优先**——宁可漏推，不要误推。不要因为两个 format 都涉及某关键词就硬把"
        "它们列为相关。如果你真的找不到任何语义关联，返回空数组 []。"
    )
    user = (
        f"## 用户刚写好的 format 描述\n{description}\n\n"
        f"## 已注册 format 列表（共 {len(candidates_payload)} 条）\n"
        f"```json\n{json.dumps(candidates_payload, ensure_ascii=False)}\n```\n\n"
        f"请返回最多 {top_k} 条相似候选的 JSON 数组。"
    )
    client = LLMClient(role="runtime_main")
    resp = client.call(
        messages=[{"role": "user", "content": user}],
        system=system,
        caller="hypothesis.find_similar_formats_core",
        info_audit=False,
    )
    text = _extract_response_text(resp).strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
    try:
        rankings = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM 相似性评估返回非合法 JSON：{exc}\n原文前 500 字：{text[:500]}"
        ) from exc
    if not isinstance(rankings, list):
        raise ValueError(f"LLM 相似性评估返回不是 list：{type(rankings).__name__}")

    format_by_id = {f.id: f for f in formats}
    enriched = []
    for r in rankings[:top_k]:
        fid = r.get("id", "")
        fmt = format_by_id.get(fid)
        enriched.append({
            "id": fid,
            "name": fmt.name if fmt else "<未找到>",
            "description": fmt.description if fmt else "",
            "relationship": r.get("relationship", ""),
        })
    return {
        "candidates": enriched,
        "total_formats_searched": len(formats),
    }


# find_similar_formats 的辅助函数（封装 scripts/retrieve_format.py 里的加载逻辑）

def _load_all_registered_formats() -> list:
    """加载全部可发现的 Format。复用 scripts/retrieve_format.py 的机型。"""
    from omnicompany.protocol.format import create_builtin_registry
    import importlib

    _SERVICE_FORMAT_MODULES = [
        "omnicompany.packages.services._learning.absorption.formats",
        "omnicompany.packages.services._core.agent.formats",
        "omnicompany.packages.services._diagnosis.doctor.formats",
        "omnicompany.packages.services._core.guardian.formats",
        "omnicompany.packages.services._learning.hypothesis.formats",
        "omnicompany.packages.services._core.pattern_discovery.formats",
        "omnicompany.packages.services._diagnosis.pipeline_ci.formats",
        "omnicompany.packages.services._core.repair.formats",
        "omnicompany.packages.services._learning.repo.architect.formats",
        "omnicompany.packages.services._learning.repo.learner.formats",
        "omnicompany.packages.services._core.selftest.formats",
        "omnicompany.packages.services._utility.skill_importer.formats",
        "omnicompany.packages.services._learning.trace_induction.formats",
        "omnicompany.packages.services._core.workflow_factory.formats",
        "omnicompany.packages.domains.voxel_engine.formats",
    ]
    registry = create_builtin_registry()
    for mod_path in _SERVICE_FORMAT_MODULES:
        try:
            mod = importlib.import_module(mod_path)
            fn = getattr(mod, "register_formats", None)
            if fn:
                fn(registry)
        except Exception:
            continue  # 某个 service 加载失败不阻塞整体
    return list(registry._formats.values())


def _extract_response_text(resp: Any) -> str:
    """从 LLMClient.call 返回值里抽出 text（兼容 Anthropic / OpenAI 不同响应类型）。"""
    if hasattr(resp, "content"):
        content = resp.content
        if isinstance(content, list):
            out = ""
            for block in content:
                if hasattr(block, "text"):
                    out += block.text
                elif isinstance(block, dict) and block.get("type") == "text":
                    out += block.get("text", "")
            return out
        if isinstance(content, str):
            return content
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        return resp.get("text", "") or resp.get("content", "")
    return ""


class ValidateHypothesisDocRouter(SingleToolRouter):
    """validate_hypothesis_doc — 校验 khyp 文档格式."""

    TOOL_NAME: ClassVar[str] = "validate_hypothesis_doc"
    DESCRIPTION: ClassVar[str] = (
        "校验一份 khyp 假设主题文档的格式合法性。\n"
        "返回 JSON：{ok: bool, errors: list[str], warnings: list[str], stats: {...}}\n"
        "每次编辑假设文档后必须调用本工具自查；errors 非空时继续修直到通过。"
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the khyp doc"},
        },
        "required": ["path"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        from omnicompany.packages.services._learning.hypothesis.validator import validate_hypothesis_doc
        path = args.get("path", "")
        if not path:
            raise ToolExecutionError("path 必填")
        result = validate_hypothesis_doc(path)
        return json.dumps(result, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════════════════════
# ExperimenterRouter — 主 agent（自由探索）
# ════════════════════════════════════════════════════════════════════════════

_EXPERIMENTER_SYSTEM_PROMPT = """\
你是一个假设探索 agent。通过运行命令和读取文件，探索目标系统的行为规律并验证假设。

全部用简体中文思考和记录。

你拥有以下工具：
- bash: 执行任意 shell 命令。典型用途：列目录、查环境变量、跑 Python 脚本、发 HTTP 请求。
- read_file: 读取文件完整内容。
- glob: 按模式查找文件路径。
- grep: 在文件或目录内搜关键词。
- finish: 结束本轮探索。不需要输出内容。

工作原则：
- 每 2-3 步自问：这条路径是否在逼近 goal？如果连续没进展，主动换方向。
- 不要重复跑完全相同的命令。
- 优先走可能直接触达 goal 的路径，不要只做表面 CLI 探索。
- 可以自由写 Python 脚本、查注册表、读配置、发 HTTP 请求——任何你觉得能推进 goal 的手段。
- 观察到显著现象时，在自己的推理里标注"这可能是一条规律"，但不要硬塞工具调用去"记录"——总结 agent 会从你的行为轨迹里归纳。
"""


class _ExperimenterPromptBuilder(PromptBuilderRouter):
    """Experimenter 首轮 prompt 装配。"""

    def build_initial_messages(self, input_data: dict) -> list[dict]:
        store = input_data.get("store", {}) or {}
        session = input_data.get("session", {}) or {}

        goal = session.get("goal", "(未指定目标)")
        tools_hint = session.get("tools", [])
        iteration = store.get("iteration", 0)
        entries = store.get("entries", [])

        lines = [
            f"## 探索目标",
            goal,
            "",
            f"## 建议工具（参考）",
            f"{tools_hint}",
            "",
            f"## 当前假设库（第 {iteration} 轮，共 {len(entries)} 条）",
        ]
        if entries:
            for e in entries:
                label = {"living": "验证中", "stable": "已证实",
                         "deprecated": "已证伪"}.get(e.get("state", ""), "待验证")
                lines.append(
                    f"- [{label}] {e.get('id','')}: {e.get('predicted','') or e.get('trigger','')}"
                )
        else:
            lines.append("（暂无假设）")
        lines.append("")
        lines.append("请开始探索。所有工具调用的记录会自动传给总结 agent，你不需要格外记录。")
        lines.append("认为本轮探索已积累足够观察时调用 finish。")
        return [{"role": "user", "content": "\n".join(lines)}]


class _ExperimenterExtractResult(ExtractResultRouter):
    """从 messages 提取 tool_use + tool_result 对，输出 trace。"""

    def __init__(self, *, bus: Any, iteration_ref: dict):
        super().__init__(bus=bus)
        self._iteration_ref = iteration_ref  # 由 Experimenter.run 注入 iteration

    def extract(
        self, *, final_text: str, messages: list[dict], turn_count: int, stop_reason: str,
    ) -> Verdict:
        trace: list[dict] = []
        tool_use_by_id: dict[str, dict] = {}
        for msg in messages:
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "tool_use":
                    tool_use_by_id[block.get("id", "")] = {
                        "tool": block.get("name", ""),
                        "args": block.get("input", {}),
                    }
                elif btype == "tool_result":
                    tool_use_id = block.get("tool_use_id", "")
                    entry = tool_use_by_id.get(tool_use_id, {})
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_content = "\n".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in result_content
                        )
                    trace.append({
                        "tool": entry.get("tool", ""),
                        "args": entry.get("args", {}),
                        "result": result_content,
                    })
        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "iteration": self._iteration_ref.get("iteration", 0),
                "trace": trace,
                "turn_count": turn_count,
                "stop_reason": stop_reason,
            },
        )


class ExperimenterRouter(AgentNodeLoop):
    """主 agent：自由探索，输出行为轨迹。

    2026-04-18 Phase C 迁移到 packages.services.agent.AgentNodeLoop。
    """

    DESCRIPTION: ClassVar[str] = "假设探索 AgentNodeLoop：自由探索，输出行为轨迹"
    FORMAT_IN: ClassVar[str] = "hypothesis.store"
    FORMAT_OUT: ClassVar[str] = "hypothesis.factlog"

    NODE_PROMPT: ClassVar[str] = _EXPERIMENTER_SYSTEM_PROMPT
    LOOP_CONFIG: ClassVar[LoopConfig] = LoopConfig(
        max_turns=200,  # 铁律 B 死循环安全网
        compact=CompactConfig(auto_compact_enabled=False),
        permission=PermissionConfig(mode="default"),
    )
    TOOL_ROUTERS: ClassVar[list[type[SingleToolRouter]]] = [
        BashRouter, ReadFileRouter, GlobRouter, GrepRouter,
        # FinishRouter 会被基类自动追加
    ]

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("role", "runtime_main")
        # iteration 在 run(input_data) 时从 store 读；先预留可变引用给 ExtractResult 读
        self._iteration_ref: dict = {"iteration": 0}
        super().__init__(**kwargs)

    def build_prompt_builder(self, *, bus: Any) -> PromptBuilderRouter:
        return _ExperimenterPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ExtractResultRouter:
        return _ExperimenterExtractResult(bus=bus, iteration_ref=self._iteration_ref)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["origin"] = input_data.get("origin", "internal-engine")
        ctx["domain"] = input_data.get("domain", "services/hypothesis")
        ctx["agent_name"] = input_data.get("agent_name", "ExperimenterRouter")
        return ctx

    async def run(self, input_data: Any) -> Verdict:
        # 把 iteration 推进 ref，供 ExtractResult 读
        if isinstance(input_data, dict):
            store = input_data.get("store", {}) or {}
            self._iteration_ref["iteration"] = store.get("iteration", 0)
        return await super().run(input_data)


# ════════════════════════════════════════════════════════════════════════════
# LockstepExperimenterRouter — 双脑 lockstep 模式
# ════════════════════════════════════════════════════════════════════════════
#
# 每 turn 末同步等反思脑完成 (on_turn_end_async)；
# 反思脑的 context_substitution 作为 user message 注入到下一轮对话。


class LockstepExperimenterRouter(ExperimenterRouter):
    """双脑 lockstep 模式的主脑。

    构造时必须传 daemon (ReflectorDaemon)。每 turn 末把本步观察提交给 daemon
    并 block 等它完成；daemon 返回的 substitutions 追加为下轮用户消息。

    2026-04-18 晚 Phase C 迁移：on_turn_end_async 签名对齐新基类
    keyword-only (turn, messages, trace_id)。
    """

    DESCRIPTION: ClassVar[str] = "假设探索 AgentNodeLoop（双脑 lockstep）"

    def __init__(self, *, daemon: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._daemon = daemon

    async def on_turn_end_async(
        self, *, turn: int, messages: list[dict], trace_id: str,
    ) -> None:
        """每 turn 末：抽取本步观察 → submit daemon → block 等 → 注入代换。"""
        obs = self._extract_latest_observation(turn, messages)
        if obs is None:
            return  # 本轮 LLM 没调工具，跳过反思

        log.info("[lockstep] turn %d → daemon submit (tool=%s)", turn, obs.tool)
        result = await self._daemon.submit_and_wait(obs)
        log.info(
            "[lockstep] turn %d ← daemon done: %s (subs=%d)",
            turn, result.summary, len(result.substitutions),
        )

        if result.substitutions:
            lines = [f"### 🧠 反思脑观察 (turn {turn} 后)"]
            for s in sorted(result.substitutions, key=lambda x: -x.priority):
                lines.append(f"- [{s.kind} · priority {s.priority}] {s.content}")
            messages.append({
                "role": "user",
                "content": "\n".join(lines),
            })

    def _extract_latest_observation(self, turn: int, messages: list[dict]) -> Any:
        """从 messages 末尾抽一对最新的 tool_use + tool_result，构造 StepObservation。

        找不到就返回 None（某 turn 可能只是文本对话没调工具）。
        """
        from omnicompany.packages.services._learning.hypothesis.reflector_daemon import StepObservation

        tool_use: dict | None = None
        tool_result: str = ""
        tool_use_id: str = ""

        for msg in reversed(messages):
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for block in reversed(content):
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")
                if btype == "tool_result" and not tool_use_id:
                    tool_use_id = block.get("tool_use_id", "")
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        result_content = "\n".join(
                            c.get("text", "") if isinstance(c, dict) else str(c)
                            for c in result_content
                        )
                    tool_result = result_content if isinstance(result_content, str) else str(result_content)
                elif btype == "tool_use" and tool_use_id and block.get("id", "") == tool_use_id:
                    tool_use = {
                        "tool": block.get("name", ""),
                        "args": block.get("input", {}),
                    }
                    break
            if tool_use:
                break

        if not tool_use:
            return None

        # doc 快照（简版：hypotheses ids）
        doc_snapshot: dict = {}
        try:
            import yaml
            import re
            doc_path = getattr(self._daemon, "_doc_path", "")
            if doc_path:
                text = Path(doc_path).read_text(encoding="utf-8")
                m = re.search(r"^---\s*\n(.*?)\n---", text, re.DOTALL | re.MULTILINE)
                if m:
                    fm = yaml.safe_load(m.group(1)) or {}
                    hyps = fm.get("hypotheses", []) or []
                    doc_snapshot = {
                        "hyp_count": len(hyps),
                        "ids": [h.get("id", "") for h in hyps if isinstance(h, dict)],
                    }
        except Exception:
            pass

        session_id = getattr(self._daemon, "_session_id", "")
        return StepObservation(
            session_id=session_id,
            turn=turn,
            tool=tool_use.get("tool", ""),
            args=tool_use.get("args", {}),
            result=tool_result,
            doc_snapshot=doc_snapshot,
        )


# ════════════════════════════════════════════════════════════════════════════
# ReflectorRouter — 总结 agent（编辑假设文档 + 校验）
# ════════════════════════════════════════════════════════════════════════════

_REFLECTOR_SYSTEM_PROMPT = """\
你是一个假设库编辑 agent，同时担任"史官"角色。你通过**直接编辑 markdown 文件**维护主题假设文档。

## 工具箱

- read_file: 读文档或源码
- edit: 精准字符串替换（首选，不丢信息）
- write_file: 整份重写（只在大改结构时用）
- glob / grep: 导航、搜索
- validate_hypothesis_doc: 校验文档合法性。**每次改完文档必须调它自查**
- finish: 结束

> **反哺 awareness 自动注入**：你**新增**（非精化）一个 format_in/out 描述后，
> 系统会在下一 turn 的 user message 里自动推送"现有相似 format"供你参考。
> 你不需要主动调工具；读到参考后**自主判断**是否调整本假设（如发现荒谬冗余则
> 精化/合并；否则保留独立）。判断留在推理上下文即可，**不要**在 markdown 写
> "相关于 X" 这类标注——系统接受冗余（§3.9），不做自动合并/链接。

## 文档结构

主题文档：YAML frontmatter（机器解析）+ markdown body（人类可读）。

frontmatter 核心字段：
```yaml
omnikb_type: khyp        # 必须
id: kb.hyp.<domain>      # 必须
name: ...
hypotheses:              # 活跃假设列表（每条 = 一个"虚 Router"：X 经过操作变成 Y）
  - id: <文档内唯一短id>
    summary: 一句话描述本虚 Router 做什么
    maturity: draft | living | stable | deprecated
    kind: state | transition | policy | invariant
    # format_in: "什么东西/状态"（虚 Router 的输入契约）
    # 单入：dict；多入（fan-in）：list[dict]
    format_in: {summary: "触发条件/输入格式简述", ...其他自由字段}
    # format_out: "经过本虚 Router 后变成什么东西/状态"（输出契约）
    # 单出：dict；多出（fan-out）：list[dict]
    format_out: {summary: "预测产出/新状态简述", ...其他自由字段}
    evidence:
      - {描述: "...", 出处: "...", 时间: ISO, session: ...}
    counterexamples: [... 同上]
    # 关系（如"从 X 精化而来"/"矛盾于 Y"/"X 的前提"）用自然语言写进 summary 或 evidence，
    # 不再用 depends_on / derived_from / contradicts 硬字段表达——关系类型远多于 3 种
    state_log:
      - {从: X, 到: Y, 理由: "...", 时间: ISO}
    created_at: ISO
    created_in_session: ...
deleted_hypotheses:       # 已删除假设归档（不能直接丢弃）
  - {id, summary, 删除理由, 删除时间, session}
```

## 史官原则（写叙事和证据描述时）

- 只描述 Experimenter 的**可观察行为**——调了什么工具、参数、返回什么
- **不推测**动机或内心独白（你看不到那些）
- 叙事用第三人称："Experimenter 调用 bash 执行 ..."，不用"它想..."或"我..."
- 没有证据的归纳不要写

## 状态判定原则（语义判断，不是计数）

- draft → living：有至少一条明确支持的观察
- living → stable：多次独立场景反复印证、无反例、你主观认为可信
- 任何 → deprecated：有明确反例、或场景已不适用
- 不要按"证据数 ≥3"这种机械规则——看内容质量

## 铁律（validator 不强制但你必须遵守）

1. **state_log 只能追加**——不要修改或删除旧条目。每次改 maturity 都在 state_log 末尾追加一条 `{从, 到, 理由, 时间}`
2. **删除假设必须归档**——不能从 hypotheses 直接删条目。正确做法：把整条移到 deleted_hypotheses 并补 `删除理由`/`删除时间`
3. **evidence/counterexamples 要带"描述"**——不要只写"出处"
4. **body 叙事第三人称** —— 在 body 的 `## 探索过程` 段落追加，不覆盖历史
5. **假设即虚 Router** —— 每条假设必须描述"**什么 → 经过操作 → 变成什么**"。format_in 写"什么东西/状态"（触发条件或输入契约），format_out 写"变成什么东西/状态"（预测产出）。fan-in/fan-out 用 list[dict] 表达多输入或多输出场景。
6. **关系走自然语言，不造硬字段** —— 假设间的关系（精化/前提/矛盾/对偶/边界/替代……）远多于三类，请在 summary 或 evidence 里自然描述，**不使用** depends_on / derived_from / contradicts 这类硬字段。相同 format_in/out 或 tag 的假设会自然聚类。

## 工作流程（每次被调用）

1. read_file 读主题文档（路径在 user message 里给出）
2. **优先补齐 format_in / format_out**（validator 强制报 error 的字段）：
   - 每个假设 = 一个虚 Router："什么 → 经过操作 → 变成什么"
   - `format_in` = 触发条件/输入契约（单入用 dict，多入用 list[dict]）
   - `format_out` = 预测产出/新状态（单出用 dict，多出用 list[dict]）
   - 至少含 `summary` 字段；None、空 dict `{}`、空 list `[]` 都不合法
   - **独立写作！不要先查现有 format——那会产生锚定偏差，让你的描述被污染**
3. 对照 Experimenter 本轮行为轨迹：
   - 哪些已有假设被观察支持 → edit 添加 evidence 条目
   - 哪些被反驳 → edit 添加 counterexamples + 考虑改 maturity（同时 append state_log）
   - 有新规律 → edit 在 hypotheses 末尾加新条目
   - 要删假设 → edit 把它从 hypotheses 移到 deleted_hypotheses
   - 在 body 的 `## 探索过程` 追加一段史官笔记
4. **反哺 awareness（被动）**：每当你新增一个 format_in 或 format_out 描述后，
   系统会在**下一 turn 的 user message 里自动推送现有相似 format**供你参考。
   读到时：
     - 如果你看到某候选和你刚写的本质是同一个 format（用途+粒度都对齐）→ 考虑
       精化本假设让它显式区分，或干脆合并到已有 format 之下
     - 如果只是相关/可组合 → 通常保留独立即可
     - 如果推送是空候选 → 你的假设可能是新规律，放心保留
   **判断留在你的推理上下文里即可，不需要在 markdown 写标注**。
5. **调 validate_hypothesis_doc 自查**。errors 非空就继续修，直到通过
6. 调 finish 结束

全部中文输出。
"""


class _ReflectorPromptBuilder(PromptBuilderRouter):
    """Reflector 首轮 prompt 装配。"""

    def build_initial_messages(self, input_data: dict) -> list[dict]:
        trace = input_data.get("trace", []) or []
        doc_path = input_data["doc_path"]
        iteration = input_data.get("iteration", 0)
        session_id = input_data.get("session_id", "")

        lines = [
            f"## 主题文档位置",
            f"`{doc_path}`",
            "",
            f"## 当前 session: {session_id[:8]} 第 {iteration} 轮",
            "",
            f"## Experimenter 本轮行为轨迹",
        ]
        if trace:
            for i, t in enumerate(trace):
                lines.append(f"### [{i+1}] 调用 `{t.get('tool','?')}`")
                args = t.get("args", {})
                if args:
                    lines.append(f"参数: {json.dumps(args, ensure_ascii=False)}")
                result = t.get("result", "")
                if result:
                    lines.append(f"返回:\n```\n{result}\n```")
                lines.append("")
        else:
            lines.append("（本轮无工具调用）")

        lines.extend([
            "",
            "## 步骤建议",
            "1. 先 read_file 读主题文档了解当前假设",
            "2. **优先** 检查每个假设的 format_in / format_out："
            "   若为 None 或空 dict {} → 必须补填（至少含 summary 字段描述触发条件/预测结果）",
            "3. 对照行为轨迹 edit 修改文档（加证据、改状态、加新假设、归档删除的假设、追加史官笔记）",
            "4. 调 validate_hypothesis_doc 自查",
            "5. 有 error 继续修；通过就 finish",
        ])
        return [{"role": "user", "content": "\n".join(lines)}]


class _ReflectorExtractResult(ExtractResultRouter):
    """Reflector 收尾：跑最终 validator，返回文件路径 + validation 结果。"""

    def __init__(self, *, bus: Any, doc_path_ref: dict):
        super().__init__(bus=bus)
        self._doc_path_ref = doc_path_ref  # {"doc_path": "..."}

    def extract(
        self, *, final_text: str, messages: list[dict], turn_count: int, stop_reason: str,
    ) -> Verdict:
        from omnicompany.packages.services._learning.hypothesis.validator import validate_hypothesis_doc
        doc_path = self._doc_path_ref.get("doc_path")
        result: dict[str, Any] = {"doc_path": doc_path}
        if doc_path:
            result["validation"] = validate_hypothesis_doc(doc_path)
        return Verdict(kind=VerdictKind.PASS, output=result)


class ReflectorRouter(AgentNodeLoop):
    """总结 agent。挂 IDE 工具（read_file/edit/write_file/glob/grep）+ validator。

    不再有 8 个专项工具，Reflector 直接编辑 markdown 文件，
    validator 作为格式安全门随时可被调用。
    """

    DESCRIPTION: ClassVar[str] = "总结 AgentNodeLoop：编辑假设文档 + 校验"
    FORMAT_IN: ClassVar[str] = "hypothesis.factlog"
    FORMAT_OUT: ClassVar[str] = "hypothesis.store_diff"

    NODE_PROMPT: ClassVar[str] = _REFLECTOR_SYSTEM_PROMPT
    LOOP_CONFIG: ClassVar[LoopConfig] = LoopConfig(
        max_turns=100,
        compact=CompactConfig(auto_compact_enabled=False),
        permission=PermissionConfig(mode="default"),
    )
    TOOL_ROUTERS: ClassVar[list[type[SingleToolRouter]]] = [
        ReadFileRouter, EditRouter, WriteFileRouter, GlobRouter, GrepRouter,
        ValidateHypothesisDocRouter,
        # FindSimilarFormatsRouter 2026-04-19 移除：LLM 选择性调用不可靠，
        # 改由 on_turn_end_async 自动触发 + 注入下一 turn。
        # FinishRouter 由基类自动追加
    ]

    # 反哺 awareness 限频：一次反思里最多自动触发 N 次（避免预算爆炸）
    MAX_AUTO_SIMILAR_PER_REFLECTION: ClassVar[int] = 3

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("role", "runtime_main")
        self._doc_path_ref: dict = {"doc_path": None}
        self._auto_similar_triggered: int = 0  # 本次反思已触发次数
        self._auto_similar_seen_descriptions: set[str] = set()  # 去重
        super().__init__(**kwargs)

    def build_prompt_builder(self, *, bus: Any) -> PromptBuilderRouter:
        return _ReflectorPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ExtractResultRouter:
        return _ReflectorExtractResult(bus=bus, doc_path_ref=self._doc_path_ref)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        ctx = super().build_tool_context(input_data=input_data, turn=turn, trace_id=trace_id)
        ctx["origin"] = input_data.get("origin", "internal-engine")
        ctx["domain"] = input_data.get("domain", "services/hypothesis")
        ctx["agent_name"] = input_data.get("agent_name", "ReflectorRouter")
        return ctx

    async def run(self, input_data: Any) -> Verdict:
        if isinstance(input_data, dict):
            self._doc_path_ref["doc_path"] = input_data.get("doc_path")
        # 每次 Reflector 调用都重置反哺限频计数器（daemon 下每 observation 一轮）
        self._auto_similar_triggered = 0
        self._auto_similar_seen_descriptions = set()
        return await super().run(input_data)

    async def on_turn_end_async(
        self, *, turn: int, messages: list[dict], trace_id: str,
    ) -> None:
        """反哺 awareness 自动触发：
        1. 扫本 turn 的 edit 工具调用
        2. 若 edit 新增（非精化）了 format_in/out → 抽 description
        3. 调 find_similar_formats_core → 结果作为 user message 注入下一 turn
        """
        if self._auto_similar_triggered >= self.MAX_AUTO_SIMILAR_PER_REFLECTION:
            return
        new_descriptions = _extract_new_format_descriptions(messages)
        if not new_descriptions:
            return
        for desc in new_descriptions:
            if self._auto_similar_triggered >= self.MAX_AUTO_SIMILAR_PER_REFLECTION:
                break
            # 去重（同一 description 在本次反思不重复查）
            key = desc[:200]
            if key in self._auto_similar_seen_descriptions:
                continue
            self._auto_similar_seen_descriptions.add(key)
            self._auto_similar_triggered += 1
            try:
                import asyncio
                result = await asyncio.to_thread(find_similar_formats_core, desc, 5)
            except Exception as exc:
                log.warning("[reflector] 反哺自动查询失败 desc=%r err=%s", desc[:80], exc)
                continue

            candidates = result.get("candidates", [])
            if candidates:
                lines = [
                    f"### 🔎 系统反哺 awareness（针对你刚写的新 format 描述，已检索 "
                    f"{result.get('total_formats_searched', 0)} 个注册 format）",
                    "",
                    f"**你刚写的描述（前 200 字）**: {desc[:200]}",
                    "",
                    "**现有相似 format**：",
                ]
                for c in candidates:
                    lines.append(f"- `{c['id']}` ({c.get('name', '')})")
                    rel = c.get('relationship', '').strip()
                    if rel:
                        lines.append(f"  - 关系: {rel}")
                lines.extend([
                    "",
                    "读完判断：你的新内容和上述候选是否是**同一个 format**（用途+粒度都对齐）？",
                    "- 是 → 考虑精化本假设让区分显式，或合并到现有 format 下",
                    "- 否 → 保留独立即可（系统接受冗余，不要写标注）",
                ])
            else:
                lines = [
                    f"### 🔎 系统反哺 awareness（针对你刚写的新 format 描述）",
                    "",
                    f"**你刚写的描述（前 200 字）**: {desc[:200]}",
                    "",
                    "已检索 {total} 个注册 format，**无语义相关候选**——你的假设可能是新规律，放心保留。".format(
                        total=result.get("total_formats_searched", 0),
                    ),
                ]
            messages.append({
                "role": "user",
                "content": "\n".join(lines),
            })


def _extract_new_format_descriptions(messages: list[dict]) -> list[str]:
    """扫 messages 中**最近一条 assistant 消息**的 edit 工具调用。

    只返回"新增"的 format_in/out 描述（排除精化已有）。
    "新增" 判据：edit 的 old_string 中对应字段为空/null/{}/[]，而 new_string 里有实质 summary。

    返回的 description 是新 summary 文本（用于查询）。
    """
    if not messages:
        return []

    last_assistant = None
    for msg in reversed(messages):
        if msg.get("role") == "assistant":
            last_assistant = msg
            break
    if not last_assistant:
        return []

    content = last_assistant.get("content", [])
    if not isinstance(content, list):
        return []

    import re
    descriptions: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") != "edit":
            continue
        args = block.get("input", {}) or {}
        old_str = args.get("old_string", "") or ""
        new_str = args.get("new_string", "") or ""

        for field in ("format_in", "format_out"):
            # old 里该字段是否存在 + 是否为空值
            old_pat = re.compile(rf"{field}:\s*([^\n]*)")
            old_m = old_pat.search(old_str)
            if old_m:
                old_val = old_m.group(1).strip()
                # 空值判定：null / {} / [] / 空字符串 / '~'
                if old_val and old_val not in ("null", "{}", "[]", "~", "None"):
                    continue  # 已有实质内容，属于精化，跳过
            # new 里必须有实质 summary
            # 提取该字段的 summary 值（单入单出 dict 格式为主）
            new_pat = re.compile(
                rf"{field}:\s*(?:\{{[^\}}]*?summary:\s*['\"]?([^'\"\n]+))",
            )
            new_m = new_pat.search(new_str)
            if new_m:
                summary_text = new_m.group(1).strip()
                if summary_text and len(summary_text) >= 20:
                    descriptions.append(summary_text)
                continue
            # 备选：field: 后跟多行 block，取其中的 summary
            block_pat = re.compile(
                rf"{field}:\s*\n\s+summary:\s*['\"]?([^'\"\n]+)",
            )
            block_m = block_pat.search(new_str)
            if block_m:
                summary_text = block_m.group(1).strip()
                if summary_text and len(summary_text) >= 20:
                    descriptions.append(summary_text)
    return descriptions
