# [OMNI] origin=claude-code domain=services/repo_learner ts=2026-04-09T12:00:00Z
# [OMNI] migrated 2026-05-03: 旧 omnicompany.runtime.agent.agent_node_loop.AgentNodeLoop 已 deprecate, 现用 packages.services._core.agent.AgentNodeLoop (router 化新基础设施). 5 个原闭包工具 → 5 个 SingleToolRouter, 通过 ToolContext.learner_state 共享 agent state.
# [OMNI] material_id="material:learning.repo.learner.router_implementation.py"
"""repo_learner routers — 3 个新节点 (LearnDimensionsLoader + MainLearnerAgent + ModuleReaderAgent)。

- `LearnDimensionsLoaderRouter`: 确定性, 注入观察维度参考清单 (非 OmniCompany 自画像)
- `MainLearnerAgent`: AgentNodeLoop 主 agent, 带 ledger + spawn_module_reader + finalize_report
- `ModuleReaderAgent`: AgentNodeLoop 子 agent, 深度限 1, 不能再 spawn

共享节点 (input_validator / repo_acquirer / repo_identity_anchor / scale_surveyor)
直接在 run.py 的 bindings 里 `from ...repo_architect.routers import` 复用, 不在这里重写。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from omnicompany.core.config import resolve_domain_data_dir
from omnicompany.core.guarded_write import write_file
from omnicompany.protocol.anchor import Verdict, VerdictKind
from omnicompany.runtime.agent.agent_loop_config import (
    CompactConfig,
    LoopConfig,
    PermissionConfig,
)
from omnicompany.runtime.routing.router import Router

# 2026-05-03: 迁到新 router 化 AgentNodeLoop. 标准只读工具 routers 替代 ToolDefinition.
# 5 个原闭包工具 (return_findings / ledger_record / ledger_list / spawn_module_reader /
# finalize_report) 重写为 SingleToolRouter, 通过 ToolContext.learner_state 共享状态.
from omnicompany.packages.services._core.agent import (
    AgentNodeLoop,
    GlobRouter,
    GrepRouter,
    ListDirRouter,
    ReadFileRouter,
)
from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    SingleToolRouter,
    ToolContext,
    ToolExecutionError,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 1. LearnDimensionsLoaderRouter — 确定性观察维度注入
# ═══════════════════════════════════════════════════════════


class LearnDimensionsLoaderRouter(Router):
    """把观察维度参考清单灌进 ctx, 给主 agent 作 SYSTEM 视角参考。

    **铁律**: 这份清单只列维度名称 + 一句话解释, **不**声明 OmniCompany 自己在各维度的
    状态 / 做法 / 立场。agent 若需了解 OmniCompany 做法, 应读真实 src/ + SKILL.md。
    """

    FORMAT_IN = "repo-architect.scaled-survey"
    FORMAT_OUT = "repo-learner.learn-dimensions"
    DESCRIPTION = (
        "注入观察维度参考清单 (19 个 AI 项目观察视角)。"
        "agent 可以按这些维度组织报告, 也可以发现新维度, 不强制分段。"
    )

    # 19 条观察维度 — 给 agent 的视角, 不是 OmniCompany 自画像
    _DIMENSIONS: ClassVar[list[dict]] = [
        {"name": "AI 框架",            "one_liner": "核心抽象与执行模型"},
        {"name": "AI 调用",            "one_liner": "与模型交互的封装、重试、流式、多后端"},
        {"name": "上下文管理",         "one_liner": "消息裁剪、压缩、记忆、session 切分"},
        {"name": "知识管理",           "one_liner": "外部知识存储、检索、更新、引用"},
        {"name": "AI 流水线与工作流",  "one_liner": "节点编排、状态、条件分支、DAG"},
        {"name": "AI harness",         "one_liner": "给 agent 工具和执行权限的脚手架"},
        {"name": "工具处理",           "one_liner": "工具注册、权限、并发、结果回传"},
        {"name": "错误处理",           "one_liner": "重试、降级、回滚、告警"},
        {"name": "自稳定软件",         "one_liner": "系统自我纠错、健康度、规则守护"},
        {"name": "安全防护",           "one_liner": "输入校验、注入防护、沙箱、权限边界"},
        {"name": "元操作",             "one_liner": "系统对自身的改写、插拔、反射"},
        {"name": "测试与验证",         "one_liner": "测试框架、断言风格、回归保护"},
        {"name": "数据与持久化",       "one_liner": "存储抽象、序列化、迁移"},
        {"name": "可观测",             "one_liner": "trace、metrics、log、debug 信号"},
        {"name": "UI / DX",            "one_liner": "命令行体验、网页、可视化"},
        {"name": "并发与异步",         "one_liner": "调度、锁、队列、协程"},
        {"name": "扩展机制",           "one_liner": "插件、hook、配置驱动"},
        {"name": "文档与 onboarding",  "one_liner": "如何让新人和模型快速上手"},
        {"name": "工程治理",           "one_liner": "CI、风格、release、依赖管理"},
    ]

    _NOTE: ClassVar[str] = (
        "(以上是观察视角列表 · 不是 OmniCompany 自画像 · "
        "agent 若想了解 OmniCompany 自己怎么做, 用 read_file 读真实 src/ 或 SKILL.md)"
    )

    async def run(self, input_data: Any) -> Verdict:
        if not isinstance(input_data, dict):
            input_data = {}
        out = dict(input_data)
        out["learn_dimensions"] = list(self._DIMENSIONS)
        out["learn_dimensions_note"] = self._NOTE
        return Verdict(
            kind=VerdictKind.PASS,
            output=out,
            diagnosis=f"注入 {len(self._DIMENSIONS)} 条观察维度",
        )


# ═══════════════════════════════════════════════════════════
# 2. _LearnerState — agent 实例共享给工具 routers 的状态容器
# ═══════════════════════════════════════════════════════════


@dataclass
class _ModuleReaderState:
    findings: dict | None = None


@dataclass
class _MainLearnerState:
    canonical_name: str = "unknown"
    working_path: str = ""
    ledger: dict = field(default_factory=lambda: {
        "files": [],
        "modules": [],
        "subagent_reports": [],
    })
    final_report: dict | None = None
    budget_tracker: dict = field(default_factory=lambda: {
        "main_steps": 0,
        "sub_steps_total": 0,
        "sub_agents_spawned": 0,
    })
    dimensions: list[dict] = field(default_factory=list)
    dimensions_note: str = ""


# ═══════════════════════════════════════════════════════════
# 3. ModuleReaderAgent — 子 agent (深度 1, 不能再 spawn)
# ═══════════════════════════════════════════════════════════


_MODULE_READER_PROMPT = """\
你是 repo_learner 的**子 agent**, 专注深读一个模块。母 agent 已决定这个模块值得深挖
并给了你 focus_hint。你的任务:

1. 用 read_file / grep / glob / list_dir 深读这个模块 (相对 working_path)
2. 围绕 focus_hint 回答问题, 找出具体的设计亮点 / 做法 / 代码位置
3. 所有引用必须带真实的 file:line (相对 working_path 的路径)
4. 预算 50 轮, 接近上限时立即调 return_findings 并 finish
5. **不能 spawn 孙 agent**, 你没有 spawn 工具。
6. **不能写任何文件**, 所有产出只通过 return_findings 回给母 agent。

【return_findings 期望的结构】
{
  "summary": "一段话总结这个模块的设计 (中英皆可)",
  "learning_points": [
    {
      "point": "一句话学到了什么",
      "file": "packages/core/src/foo/bar.ts",
      "lines": "12-34",
      "why_worth": "为什么值得记 — 解决了什么问题 / 用了什么巧思",
      "dimension": "agent 循环结构"  (可选, 从母 agent 的维度清单里挑一个或自拟)
    }
  ],
  "key_files": ["packages/core/src/foo/bar.ts", ...]
}

【铁律】
- 所有 file:line 引用必须真实存在 (你刚读过的才能写)
- 禁止使用训练语料里同名项目的知识
- summary + learning_points 齐全后立即 return_findings + finish, 不要磨蹭
"""


class _ReturnFindingsRouter(SingleToolRouter):
    """ModuleReaderAgent 的 return_findings 工具 — 写 ctx.learner_state.findings."""

    TOOL_NAME: ClassVar[str] = "return_findings"
    DESCRIPTION: ClassVar[str] = (
        "Return your module findings to the parent agent. "
        "Call this exactly once when you are done, then immediately call finish."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-paragraph summary of the module's design",
            },
            "learning_points": {
                "type": "array",
                "description": "List of concrete learning points with file:line evidence",
                "items": {
                    "type": "object",
                    "properties": {
                        "point": {"type": "string"},
                        "file": {"type": "string"},
                        "lines": {"type": "string"},
                        "why_worth": {"type": "string"},
                        "dimension": {"type": "string"},
                    },
                    "required": ["point", "file", "lines", "why_worth"],
                },
            },
            "key_files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of key file paths (relative to working_path)",
            },
        },
        "required": ["summary", "learning_points"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        state: _ModuleReaderState | None = getattr(ctx, "learner_state", None)
        if state is None:
            raise ToolExecutionError("learner_state missing from tool context")
        state.findings = {
            "summary": str(args.get("summary", ""))[:3000],
            "learning_points": args.get("learning_points", []) or [],
            "key_files": args.get("key_files", []) or [],
        }
        return "findings 已缓存, 请立即调 finish 工具结束。"


class _ModuleReaderPromptBuilder(PromptBuilderRouter):
    """ModuleReaderAgent 自定义首条 user 消息."""

    def build_initial_messages(self, input_data: dict) -> list[dict]:
        module_path = input_data.get("module_path", "?")
        working_path = input_data.get("working_path", "")
        focus_hint = input_data.get("focus_hint", "")
        why = input_data.get("why", "未说明")
        return [{
            "role": "user",
            "content": (
                f"【target 模块】{module_path}\n"
                f"【working_path 根 (绝对路径)】{working_path}\n"
                f"   读文件时的完整路径示例: {working_path}/{module_path}/<file>\n\n"
                f"【母 agent 给的 focus_hint】{focus_hint}\n"
                f"【为什么读它】{why}\n\n"
                f"请按 SYSTEM 的工作流深读, 最后 return_findings + finish。"
            ),
        }]


class _ModuleReaderExtractResult(ExtractResultRouter):
    """ModuleReaderAgent 自定义产物提取 — 读 state.findings, 兜底用 final_text."""

    def __init__(self, state: _ModuleReaderState, *, bus: Any | None = None):
        super().__init__(bus=bus)
        self._state = state

    def extract(
        self,
        *,
        final_text: str,
        messages: list[dict],
        turn_count: int,
        stop_reason: str,
    ) -> Verdict:
        findings = self._state.findings or {
            "summary": (final_text or "(no findings)")[:1000],
            "learning_points": [],
            "key_files": [],
            "warning": "agent 未调用 return_findings, 使用 final_text 兜底",
        }
        return Verdict(kind=VerdictKind.PASS, output=findings)


class ModuleReaderAgent(AgentNodeLoop):
    """子学习 agent: 深度读一个模块 + 返回 findings (router 化, 2026-05-03 迁).

    **深度约束**: 只有只读文件工具 + return_findings, 没有 spawn 工具。
    不能再起孙 agent。
    """

    LOOP_CONFIG: ClassVar[LoopConfig] = LoopConfig(
        max_turns=300,
        compact=CompactConfig(auto_compact_enabled=True, auto_compact_threshold=0.9),
        permission=PermissionConfig(mode="readonly"),
    )

    DESCRIPTION = "AgentNodeLoop 子 agent: 深读单个模块 + 返回结构化 findings (不能 spawn 孙 agent)"

    NODE_PROMPT: ClassVar[str] = _MODULE_READER_PROMPT
    TOOL_ROUTERS: ClassVar[list] = [
        ReadFileRouter, GrepRouter, GlobRouter, ListDirRouter, _ReturnFindingsRouter,
    ]

    def __init__(
        self,
        *,
        model: str | None = None,
        bus: Any | None = None,
        config: LoopConfig | None = None,
    ):
        self._state = _ModuleReaderState()
        super().__init__(model=model, bus=bus, config=config or self.LOOP_CONFIG)

    def build_prompt_builder(self, *, bus: Any) -> PromptBuilderRouter:
        return _ModuleReaderPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ExtractResultRouter:
        return _ModuleReaderExtractResult(self._state, bus=bus)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        return {
            "trace_id": trace_id,
            "turn_number": turn,
            "learner_state": self._state,
        }


# ═══════════════════════════════════════════════════════════
# 4. MainLearnerAgent — 主学习 agent, 5 个工具 routers
# ═══════════════════════════════════════════════════════════


_MAIN_LEARNER_PROMPT = """\
你是一个带着目的读开源仓库的学习 agent。你的目的是回答两个问题:

  (A) 这个项目里有哪些设计 / 做法值得借鉴 (**学习价值**)?
  (B) 这些值得记住的点在代码的哪里 (**学习位置**, file:line)?

你**不是**在写架构文档, 也不是在画覆盖率图。你的最终产物是一份自由格式的 markdown,
**必须含两段**:
  - `## Learning Value` — 若干条 "学到了什么", 每条写清楚为什么值得记
  - `## Learning Locations` — 每条 `file:line` + 一句话定位为什么记录

其余组织方式你自己决定: 按维度分、按模块分、按 "值得偷" / "值得警惕" 分, 都允许。

【观察维度参考 (非强制分段, 可新增)】
{dimensions_block}

{dimensions_note}

【铁律】
1. 所有代码引用必须带真实的 `file:line` (相对 working_path)。不允许凭空描述。
2. 禁止声明 "我们 OmniCompany 和他们相似度 XX%" 这类数值判断。只描述具体点。
3. 禁止使用训练语料里同名或类似项目的知识。只看 working_path 下的真实内容。
4. 需要对照 OmniCompany 自己做法时, 你可以用 read_file / grep 读
   `/workspace/omnicompany/` 下的真实代码或
   `/workspace/omnicompany/.claude/skills/omnicompany-dev/SKILL.md`。
   不要依赖我在 prompt 里给你任何 OmniCompany 自画像 (我没给)。

【工作流程建议 (可调整)】
1. 先 read_file 读 README / 顶层 manifest (pyproject.toml / package.json 等) 建立印象
2. 用 glob / grep / list_dir 摸清关键包/目录的分布
3. 每读一个非平凡文件就 ledger_record (一句话摘要 + 重要度 key/base/edge + 维度 tag)
4. 识别出 2-3 个值得深读的模块, 每个调 spawn_module_reader 起子 agent 拉深 findings
5. 拿到所有子 agent findings 后综合主 ledger 和你自己读到的材料, 调 finalize_report
   写 markdown (Learning Value + Learning Locations 两段必含, 其他自由发挥)
6. 立即调 finish 结束 loop

【预算】
300 主循环 turns (硬上限, 不是目标), 子 agent 同样 300。最多 spawn 3 次。
预算敞开, 你可以大量读、反复对比、慢慢思考; 目标是学到有价值的东西, 不是赶着收口。
只有在觉得材料已够写报告时, 才开始 finalize_report + finish。
"""


_MAX_SPAWNS = 3


class _LedgerRecordRouter(SingleToolRouter):
    TOOL_NAME: ClassVar[str] = "ledger_record"
    DESCRIPTION: ClassVar[str] = (
        "Record that you have read a file. Write a one-line summary, mark its importance "
        "(key/base/edge), and optionally tag which observation dimension it relates to. "
        "Call this every time you finish reading a non-trivial file so the final report "
        "can cite evidence later."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "file": {"type": "string", "description": "Path relative to working_path"},
            "importance": {
                "type": "string",
                "enum": ["key", "base", "edge"],
                "description": "key=核心设计源 / base=支撑实现 / edge=辅助文件",
            },
            "summary": {"type": "string", "description": "One-line summary (<=500 chars)"},
            "relevant_to_dimension": {
                "type": "string",
                "description": "One of the 19 observation dimensions, or a new one you invent",
            },
        },
        "required": ["file", "summary"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        state: _MainLearnerState | None = getattr(ctx, "learner_state", None)
        if state is None:
            raise ToolExecutionError("learner_state missing from tool context")
        file_path = str(args.get("file", "")).strip()
        if not file_path:
            return json.dumps({"error": "file 字段必填"})
        entry = {
            "file": file_path,
            "importance": str(args.get("importance", "base")),
            "summary": str(args.get("summary", ""))[:500],
            "relevant_to_dimension": str(args.get("relevant_to_dimension", "")),
        }
        state.ledger["files"].append(entry)
        return json.dumps({"ok": True, "ledger_files_count": len(state.ledger["files"])})


class _LedgerListRouter(SingleToolRouter):
    TOOL_NAME: ClassVar[str] = "ledger_list"
    DESCRIPTION: ClassVar[str] = (
        "List your current ledger (files you have recorded + subagent reports + "
        "budget usage). Use this when you want to review what you have learned so far "
        "before deciding what to read next or when to finalize the report."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "importance": {
                "type": "string",
                "enum": ["key", "base", "edge"],
                "description": "Filter by importance (optional)",
            },
        },
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        state: _MainLearnerState | None = getattr(ctx, "learner_state", None)
        if state is None:
            raise ToolExecutionError("learner_state missing from tool context")
        filter_importance = str(args.get("importance", "")).strip()
        files = state.ledger["files"]
        if filter_importance:
            files = [f for f in files if f.get("importance") == filter_importance]
        return json.dumps({
            "files_count": len(files),
            "files": files[:50],
            "subagent_reports_count": len(state.ledger["subagent_reports"]),
            "budget_tracker": state.budget_tracker,
        }, ensure_ascii=False)


class _SpawnModuleReaderRouter(SingleToolRouter):
    TOOL_NAME: ClassVar[str] = "spawn_module_reader"
    DESCRIPTION: ClassVar[str] = (
        "Spawn a sub-agent to deep-read a specific module. The sub-agent has 50 turns to "
        "explore and will return structured findings (summary + learning_points + key_files). "
        "You can spawn up to 3 sub-agents total. Use this when you've identified a module "
        "that deserves deeper investigation than what you can do yourself. "
        "Provide a clear focus_hint telling the sub-agent what specifically to look for."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "module_path": {
                "type": "string",
                "description": "Path relative to working_path (e.g. 'packages/core/src/agents')",
            },
            "focus_hint": {
                "type": "string",
                "description": (
                    "What specifically should the sub-agent look for? "
                    "e.g. 'how the tool_use loop is structured + retry logic'"
                ),
            },
            "why": {
                "type": "string",
                "description": "Why is this module worth a sub-agent investment?",
            },
        },
        "required": ["module_path", "focus_hint"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        state: _MainLearnerState | None = getattr(ctx, "learner_state", None)
        if state is None:
            raise ToolExecutionError("learner_state missing from tool context")

        module_path = str(args.get("module_path", "")).strip()
        focus_hint = str(args.get("focus_hint", "")).strip()
        why = str(args.get("why", "")).strip()
        if not module_path:
            return json.dumps({"error": "module_path 必填"})
        if not focus_hint:
            return json.dumps({"error": "focus_hint 必填"})

        spawned_count = state.budget_tracker["sub_agents_spawned"]
        if spawned_count >= _MAX_SPAWNS:
            return json.dumps({
                "error": f"已达最大 sub-agent 数量 ({_MAX_SPAWNS}), 请用当前材料收口",
            })

        logger.info(
            "[MainLearnerAgent] spawning ModuleReaderAgent for '%s' (spawn #%d)",
            module_path, spawned_count + 1,
        )

        # 在当前线程内新开 event loop 跑子 agent (因为 _execute 在 asyncio.to_thread 里跑,
        # 当前线程没有 event loop). 子 agent 复用主 agent 的 bus.
        loop = asyncio.new_event_loop()
        try:
            sub = ModuleReaderAgent(bus=self._bus)
            result = loop.run_until_complete(sub.run({
                "module_path": module_path,
                "working_path": state.working_path,
                "focus_hint": focus_hint,
                "why": why or "(未说明)",
                "project_root": state.working_path,
                "cwd": state.working_path,
            }))
        except Exception as e:
            logger.warning("[MainLearnerAgent] sub-agent 异常: %s", e, exc_info=True)
            return json.dumps({
                "error": f"sub-agent 异常: {e}",
                "module": module_path,
            })
        finally:
            loop.close()

        state.budget_tracker["sub_agents_spawned"] += 1
        # turns 实际用量按 max_turns 保守记
        state.budget_tracker["sub_steps_total"] += sub._config.max_turns

        sub_findings = result.output if isinstance(result.output, dict) else {}
        state.ledger["subagent_reports"].append({
            "module": module_path,
            "focus_hint": focus_hint,
            "why": why,
            "findings": sub_findings,
        })
        return json.dumps({
            "ok": True,
            "module": module_path,
            "findings": sub_findings,
            "spawned_count": state.budget_tracker["sub_agents_spawned"],
            "remaining_spawns": _MAX_SPAWNS - state.budget_tracker["sub_agents_spawned"],
        }, ensure_ascii=False)


class _FinalizeReportRouter(SingleToolRouter):
    TOOL_NAME: ClassVar[str] = "finalize_report"
    DESCRIPTION: ClassVar[str] = (
        "Cache your final learning report markdown. The markdown MUST contain both:\n"
        "  - '## Learning Value' section (what you learned + why it's worth remembering)\n"
        "  - '## Learning Locations' section (every entry has file:line + one-liner why)\n"
        "Other sections are your choice. After this tool returns ok, IMMEDIATELY call finish."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "markdown": {
                "type": "string",
                "description": "Full report markdown, must contain both required sections",
            },
            "notable_locations": {
                "type": "array",
                "description": "Structured duplicate of the Learning Locations section",
                "items": {
                    "type": "object",
                    "properties": {
                        "file": {"type": "string"},
                        "lines": {"type": "string"},
                        "one_line_why": {"type": "string"},
                    },
                    "required": ["file", "lines", "one_line_why"],
                },
            },
        },
        "required": ["markdown"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = False
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        state: _MainLearnerState | None = getattr(ctx, "learner_state", None)
        if state is None:
            raise ToolExecutionError("learner_state missing from tool context")

        markdown = str(args.get("markdown", "")).strip()
        notable_locations = args.get("notable_locations") or []
        if not markdown:
            return json.dumps({"error": "markdown 必填"})

        if "Learning Value" not in markdown:
            return json.dumps({
                "error": "markdown 缺少 'Learning Value' 段。请加上 `## Learning Value` 段。",
            })
        if "Learning Locations" not in markdown:
            return json.dumps({
                "error": "markdown 缺少 'Learning Locations' 段。请加上 `## Learning Locations` 段。",
            })

        state.final_report = {
            "markdown": markdown,
            "notable_locations": [
                loc for loc in notable_locations if isinstance(loc, dict)
            ],
        }
        return json.dumps({
            "ok": True,
            "message": "报告已缓存, 请立即调 finish 结束 loop。",
            "report_chars": len(markdown),
            "notable_locations_count": len(state.final_report["notable_locations"]),
        })


class _MainLearnerPromptBuilder(PromptBuilderRouter):
    """MainLearnerAgent 自定义 system prompt (动态填 dimensions) + 首条 user 消息."""

    def __init__(self, state: _MainLearnerState, *, template: str, bus: Any | None = None):
        super().__init__(template=template, bus=bus)
        self._state = state

    def render_system_prompt(self, input_data: dict) -> str:
        # 把 dimensions 写进 state, 同时填模板
        self._state.dimensions = input_data.get("learn_dimensions") or []
        self._state.dimensions_note = input_data.get("learn_dimensions_note") or ""
        if self._state.dimensions:
            lines = [
                f"  {i:2}. {d['name']} — {d['one_liner']}"
                for i, d in enumerate(self._state.dimensions, 1)
            ]
            dimensions_block = "\n".join(lines)
        else:
            dimensions_block = "(维度清单未注入 — LearnDimensionsLoader 可能未执行)"
        return self._template.format(
            dimensions_block=dimensions_block,
            dimensions_note=self._state.dimensions_note or "(no note)",
        )

    def build_initial_messages(self, input_data: dict) -> list[dict]:
        canonical_name = input_data.get("canonical_name", "unknown")
        canonical_desc = input_data.get("canonical_description", "")
        ecosystem = input_data.get("ecosystem", "unknown")
        disambiguation_hint = input_data.get("disambiguation_hint", "")
        working_path = input_data.get("working_path", self._state.working_path)
        code_modules = input_data.get("code_modules") or []

        # 同步 state
        self._state.working_path = working_path
        if canonical_name and canonical_name != "unknown":
            self._state.canonical_name = canonical_name

        # 精简 code_modules
        mods_brief = [
            {
                "path": m.get("path"),
                "kind": m.get("kind"),
                "file_count": m.get("file_count"),
                "sub_packages": (m.get("sub_packages") or [])[:6],
                "discovered_via": m.get("discovered_via"),
            }
            for m in code_modules[:25]
            if isinstance(m, dict)
        ]

        content = [
            f"【target 仓库】",
            f"  canonical_name: {canonical_name}",
            f"  canonical_description: {canonical_desc}",
            f"  ecosystem: {ecosystem}",
            f"  working_path (绝对): {working_path}",
            "",
            f"【身份锚 (防幻觉)】",
            f"  {disambiguation_hint}",
            "",
            f"【scale_surveyor 已扫出的真实代码模块 ({len(code_modules)} 个, 展示前 25)】",
            json.dumps(mods_brief, ensure_ascii=False, indent=2),
            "",
            "开始工作。先用 read_file 读 README 建立印象, 然后按 SYSTEM 的工作流推进。",
            "记得每读一个文件就 ledger_record, 识别出值得深读的模块就 spawn_module_reader,",
            "最后 finalize_report + finish。",
        ]
        return [{"role": "user", "content": "\n".join(content)}]


class _MainLearnerExtractResult(ExtractResultRouter):
    """MainLearnerAgent 自定义产物提取 — 落 report+ledger 到磁盘, 返回 path metadata."""

    def __init__(self, state: _MainLearnerState, *, max_turns: int, bus: Any | None = None):
        super().__init__(bus=bus)
        self._state = state
        self._max_turns = max_turns

    def extract(
        self,
        *,
        final_text: str,
        messages: list[dict],
        turn_count: int,
        stop_reason: str,
    ) -> Verdict:
        report = self._state.final_report or {
            "markdown": (final_text or "(no report produced)").strip() or "(empty)",
            "notable_locations": [],
        }
        # 兜底: 若 agent 忘记 finalize_report, 强制补两段保证格式
        if not self._state.final_report:
            md = report["markdown"]
            if "## Learning Value" not in md:
                md = "## Learning Value\n\n(agent 未调用 finalize_report, 以下是 final_text 兜底)\n\n" + md
            if "## Learning Locations" not in md:
                md += "\n\n## Learning Locations\n\n(none — agent 未提供结构化位置清单)\n"
            report = {"markdown": md, "notable_locations": []}

        # 落盘 report + ledger
        try:
            data_root = resolve_domain_data_dir("absorption")
        except Exception as e:
            logger.warning("[MainLearnerAgent] resolve_domain_data_dir 失败: %s", e)
            data_root = Path("data/domains/absorption")

        report_dir = data_root / "learning_reports"
        ledger_dir = data_root / "ledger"
        report_dir.mkdir(parents=True, exist_ok=True)
        ledger_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r'[^\w\-.]', '_', self._state.canonical_name)[:80] or "unknown"
        report_path = report_dir / f"{safe_name}.md"
        ledger_path = ledger_dir / f"{safe_name}.json"

        ledger_payload = {
            "canonical_name": self._state.canonical_name,
            "working_path": self._state.working_path,
            "budget_tracker": self._state.budget_tracker,
            "files": self._state.ledger["files"],
            "modules": self._state.ledger["modules"],
            "subagent_reports": self._state.ledger["subagent_reports"],
            "notable_locations": report["notable_locations"],
        }

        try:
            write_file(
                str(report_path), report["markdown"],
                origin="internal-engine",
                domain="services/repo_learner",
                purpose=f"learning report for {self._state.canonical_name}",
            )
            write_file(
                str(ledger_path),
                json.dumps(ledger_payload, ensure_ascii=False, indent=2),
                origin="internal-engine",
                domain="services/repo_learner",
                purpose=f"learning ledger for {self._state.canonical_name}",
            )
        except Exception as e:
            logger.warning("[MainLearnerAgent] 落盘失败: %s", e, exc_info=True)

        return Verdict(kind=VerdictKind.PASS, output={
            "report_path": str(report_path),
            "report_chars": len(report["markdown"]),
            "ledger_path": str(ledger_path),
            "files_read_count": len(self._state.ledger["files"]),
            "spawned_subagents_count": self._state.budget_tracker["sub_agents_spawned"],
            "budget_used": self._state.budget_tracker["sub_steps_total"] + self._max_turns,
            "notable_locations": report["notable_locations"],
            "canonical_name": self._state.canonical_name,
        })


class MainLearnerAgent(AgentNodeLoop):
    """主学习 agent — 自由读仓库 + 维护 ledger + 可 spawn 子 agent + 产出自由格式 learning report.

    Router 化迁移 (2026-05-03): 5 个原闭包工具 (ledger_record / ledger_list /
    spawn_module_reader / finalize_report / + ModuleReader 的 return_findings) 重写为
    SingleToolRouter, 通过 build_tool_context 注入的 _MainLearnerState 共享状态.

    旧 should_force_finish hook 在新架构通过 on_turn_end_async 实现 — agent 调过
    finalize_report 后下一轮 inject 一条提示让它收口.

    **单实例**: 状态对象一对一绑 agent 实例, 同进程不支持并发两个实例.
    """

    LOOP_CONFIG: ClassVar[LoopConfig] = LoopConfig(
        max_turns=300,
        compact=CompactConfig(auto_compact_enabled=True, auto_compact_threshold=0.9),
        permission=PermissionConfig(mode="readonly"),
    )

    DESCRIPTION = (
        "AgentNodeLoop 主学习 agent: 自由读仓库, 维护 ledger, 可 spawn 最多 3 个子 agent, "
        "产出自由格式 learning report (Learning Value + Learning Locations 两段必含)。"
    )

    FORMAT_IN = "repo-learner.learn-dimensions"
    FORMAT_OUT = "repo-learner.learning-report"

    NODE_PROMPT: ClassVar[str] = _MAIN_LEARNER_PROMPT
    TOOL_ROUTERS: ClassVar[list] = [
        ReadFileRouter, GrepRouter, GlobRouter, ListDirRouter,
        _LedgerRecordRouter, _LedgerListRouter, _SpawnModuleReaderRouter, _FinalizeReportRouter,
    ]

    def __init__(
        self,
        *,
        canonical_name: str = "unknown",
        working_path: str = "",
        model: str | None = None,
        bus: Any | None = None,
        config: LoopConfig | None = None,
    ):
        self._state = _MainLearnerState(
            canonical_name=canonical_name,
            working_path=working_path,
        )
        super().__init__(model=model, bus=bus, config=config or self.LOOP_CONFIG)

    def build_prompt_builder(self, *, bus: Any) -> PromptBuilderRouter:
        return _MainLearnerPromptBuilder(self._state, template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> ExtractResultRouter:
        return _MainLearnerExtractResult(
            self._state, max_turns=self._config.max_turns, bus=bus,
        )

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        return {
            "trace_id": trace_id,
            "turn_number": turn,
            "learner_state": self._state,
        }

    async def on_turn_end_async(
        self, *, turn: int, messages: list[dict], trace_id: str,
    ) -> None:
        # 旧 should_force_finish 等价: agent 调过 finalize_report 后但还没 finish, 提醒它收口
        if self._state.final_report is not None and turn > 2:
            messages.append({
                "role": "user",
                "content": "已检测到 finalize_report 被调用, 请立即 finish。",
            })
