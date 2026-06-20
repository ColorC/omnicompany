# [OMNI] origin=claude-code domain=services/agent/routers ts=2026-05-04T00:00:00Z type=infrastructure
"""SkillRouter / DiscoverSkillsRouter / ToolSearchRouter · 能力发现/调用工具.

参考: claude-code SkillTool / DiscoverSkillsTool / ToolSearchTool

omnicompany 实现思路:
  - skills 在 .claude/skills/<name>/SKILL.md (与 claude code 一致约定)
  - DiscoverSkills: 扫工作区 + 用户 ~/.claude/skills/ 列出可用 skills
  - Skill: 调一个 skill 的入口 — 这里是"加载 SKILL.md 内容供 LLM 跟随"
    (omnicompany 没 claude.ai 那种 skill 运行时, 但可以加载 instructions)
  - ToolSearch: 列已注册工具 (从 Worker 的 ctx.tool_registry 取)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import ClassVar

from omnicompany.packages.services._core.agent.routers.single_tool import (
    SingleToolRouter,
    ToolContext,
    ToolExecutionError,
)

logger = logging.getLogger(__name__)


def _skills_search_paths(ctx: ToolContext) -> list[Path]:
    """合法 skills 搜索路径: 项目 .claude/skills/ + 用户 ~/.claude/skills/"""
    paths: list[Path] = []
    base = Path(ctx.project_root or ctx.cwd or Path.cwd())
    paths.append(base / ".claude" / "skills")
    home = Path.home() / ".claude" / "skills"
    paths.append(home)
    return [p for p in paths if p.exists() and p.is_dir()]


# ─── DiscoverSkillsRouter ─────────────────────────────────────────


class DiscoverSkillsRouter(SingleToolRouter):
    """List available skills (from .claude/skills/ project + user dirs)."""

    CONSUMED_META_IO: ClassVar[tuple[str, ...]] = ("meta_io.fs.read_file",)
    PRODUCED_META_IO: ClassVar[tuple[str, ...]] = ()

    TOOL_NAME: ClassVar[str] = "DiscoverSkills"
    DESCRIPTION: ClassVar[str] = (
        "List skills available in this project + user's global skills.\n"
        "\n"
        "Skills are .claude/skills/<name>/SKILL.md files. Returns:\n"
        "- name + first-line description per skill\n"
        "- path (so caller can pass to Skill tool)"
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        skills: list[dict] = []
        for sp in _skills_search_paths(ctx):
            for child in sorted(sp.iterdir()):
                if not child.is_dir():
                    continue
                skill_md = child / "SKILL.md"
                if not skill_md.exists():
                    continue
                try:
                    head = skill_md.read_text(encoding="utf-8", errors="replace").splitlines()
                except Exception:
                    continue
                # 提取首行非空非注释作 description
                desc = ""
                for line in head[:30]:
                    s = line.strip()
                    if s and not s.startswith("#") and not s.startswith("---"):
                        desc = s[:120]
                        break
                skills.append({
                    "name": child.name,
                    "path": str(skill_md),
                    "description": desc,
                })

        if not skills:
            return "No skills found."
        lines = []
        for sk in skills:
            lines.append(f"- {sk['name']}: {sk['description'] or '(no description)'}")
            lines.append(f"  path: {sk['path']}")
        return "\n".join(lines)


# ─── SkillRouter ──────────────────────────────────────────────────


class SkillRouter(SingleToolRouter):
    """Load a skill's SKILL.md content into the agent context (for LLM to follow)."""

    CONSUMED_META_IO: ClassVar[tuple[str, ...]] = ("meta_io.fs.read_file",)
    PRODUCED_META_IO: ClassVar[tuple[str, ...]] = ()

    TOOL_NAME: ClassVar[str] = "Skill"
    # DESCRIPTION 1:1 复刻 cc SkillTool/prompt.ts::getPrompt 静态部分 (Wave 5 续, 2026-05-05)
    # 适配:
    #   - omnicompany 没 slash command 概念 (claude.ai 特有), 跳过 "/<something>" 段
    #   - omnicompany 没 plugin: namespace, 但保留 fully qualified name 提及 (兼容未来)
    #   - 工具引用名用 "Skill" (omnicompany TOOL_NAME 一致)
    DESCRIPTION: ClassVar[str] = (
        "Execute a skill within the main conversation\n"
        "\n"
        "When users ask you to perform tasks, check if any of the available skills match. Skills provide specialized capabilities and domain knowledge.\n"
        "\n"
        "When users reference a \"slash command\" or \"/<something>\", they are referring to a skill. Use this tool to invoke it.\n"
        "\n"
        "How to invoke:\n"
        "- Set `skill` to the exact name of an available skill (no leading slash). For plugin-namespaced skills use the fully qualified `plugin:skill` form.\n"
        "- Set `args` to pass optional arguments.\n"
        "\n"
        "Important:\n"
        "- Available skills are listed in system-reminder messages in the conversation\n"
        "- Only invoke a skill that appears in that list, or one the user explicitly typed as `/<name>` in their message. Never guess or invent a skill name from training data; otherwise do not call this tool\n"
        "- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: invoke the relevant Skill tool BEFORE generating any other response about the task\n"
        "- NEVER mention a skill without actually calling this tool\n"
        "- Do not invoke a skill that is already running\n"
        "- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)\n"
        "- If you see a <command-name> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling this tool again"
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Skill name (dir under .claude/skills/)"},
            "args": {"type": "string", "description": "Optional argument string"},
        },
        "required": ["name"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        name = (args.get("name") or "").strip()
        if not name:
            raise ToolExecutionError("name is required")
        if any(c in name for c in r' /\:*?"<>|'):
            raise ToolExecutionError(f"name must be filesystem-safe: {name!r}")

        # 找 skill
        for sp in _skills_search_paths(ctx):
            skill_md = sp / name / "SKILL.md"
            if skill_md.exists():
                try:
                    content = skill_md.read_text(encoding="utf-8")
                except Exception as e:
                    raise ToolExecutionError(f"failed to read {skill_md}: {e}")
                hdr = f"=== Skill: {name} (from {skill_md}) ==="
                arg_str = (args.get("args") or "").strip()
                if arg_str:
                    hdr += f"\n=== Arguments: {arg_str} ==="
                return hdr + "\n\n" + content

        searched = [str(p) for p in _skills_search_paths(ctx)]
        raise ToolExecutionError(
            f"skill {name!r} not found. Searched: {searched}. Use DiscoverSkills to list."
        )


# ─── ToolSearchRouter ─────────────────────────────────────────────


class ToolSearchRouter(SingleToolRouter):
    """Fetches schemas for deferred tools by name or keyword search.

    对齐 claude code ToolSearchTool: deferred 工具 (TOOL_NAME 由 system-reminder 告知,
    schema 不加载) 只有通过本工具才能拉到完整 INPUT_SCHEMA, 之后才能调用.

    注: 之前一版用 ctx.tool_registry 模式 (dict 索引), 与 claude code deferred 机制
    不一致. 2026-05-04 改为真 deferred 拉取实现 (跟 omnicompany 工具注册表对接).
    """

    CONSUMED_META_IO: ClassVar[tuple[str, ...]] = ()
    PRODUCED_META_IO: ClassVar[tuple[str, ...]] = ()

    TOOL_NAME: ClassVar[str] = "ToolSearch"
    DESCRIPTION: ClassVar[str] = (
        "Fetches full schema definitions for deferred tools so they can be called.\n"
        "\n"
        "Deferred tools appear by name in <system-reminder> messages. Until fetched, only the name "
        "is known — there is no parameter schema, so the tool cannot be invoked. This tool takes a "
        "query, matches it against the deferred tool list, and returns the matched tools' complete "
        "JSONSchema definitions inside a <functions> block. Once a tool's schema appears in that "
        "result, it is callable exactly like any tool defined at the top of the prompt.\n"
        "\n"
        "Result format: each matched tool appears as one "
        '<function>{"description": "...", "name": "...", "parameters": {...}}</function> '
        "line inside the <functions> block — the same encoding as the tool list at the top of this prompt.\n"
        "\n"
        "Query forms:\n"
        '- "select:Read,Edit,Grep" — fetch these exact tools by name\n'
        '- "notebook jupyter" — keyword search, up to max_results best matches\n'
        '- "+slack send" — require "slack" in the name, rank by remaining terms'
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": (
                    'Query to find deferred tools. Use "select:<tool_name>" for direct selection, '
                    "or keywords to search."
                ),
            },
            "max_results": {
                "type": "integer",
                "default": 5,
                "description": "Maximum number of results to return (default: 5)",
            },
        },
        "required": ["query"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        query = (args.get("query") or "").strip()
        if not query:
            raise ToolExecutionError("query is required")
        max_results = int(args.get("max_results", 5))
        if max_results < 1:
            raise ToolExecutionError("max_results must be >= 1")

        # 拉 deferred 工具列表. 优先用 ctx.deferred_tools (Worker 注入更精细的子集),
        # fallback 到全局 DEFERRED_TOOL_ROUTERS (本服务 _core/agent/routers/__init__.py 定义).
        candidates = self._collect_deferred_candidates(ctx)
        if not candidates:
            raise ToolExecutionError(
                "No deferred tools available. Either inject ctx.deferred_tools "
                "or import _core.agent.routers (default deferred set will be used)."
            )

        # 解析 query
        # 形式 1: "select:A,B,C" — 精确选取
        # 形式 2: "+keyword keyword" — 必须含 +keyword, 其余排序
        # 形式 3: "keyword keyword" — 全关键词搜索 (substring)
        if query.lower().startswith("select:"):
            names = [n.strip() for n in query[len("select:"):].split(",") if n.strip()]
            matched = []
            for n in names:
                cls = candidates.get(n)
                if cls is not None:
                    matched.append(cls)
        else:
            terms = [t.strip().lower() for t in query.split() if t.strip()]
            required = [t[1:] for t in terms if t.startswith("+")]
            optional = [t for t in terms if not t.startswith("+")]
            scored: list[tuple[int, type[SingleToolRouter]]] = []
            for cls in candidates.values():
                hay = (cls.TOOL_NAME + "\n" + (cls.DESCRIPTION or "")).lower()
                if not all(req in hay for req in required):
                    continue
                if not optional and not required:
                    score = 0
                else:
                    score = sum(1 for t in optional if t in hay)
                    # required 词命中已是必要条件, 不重复打分
                if score == 0 and not required:
                    continue
                scored.append((score, cls))
            # 按 score 倒序, 同分按 TOOL_NAME 字典序
            scored.sort(key=lambda x: (-x[0], x[1].TOOL_NAME))
            matched = [cls for _, cls in scored[:max_results]]

        if not matched:
            return f"<functions>\n</functions>\n(No deferred tools matched query: {query!r})"

        # 构造 <functions> 块, 每条工具一行 JSON spec (跟 claude code 输出格式对齐)
        lines = ["<functions>"]
        for cls in matched[:max_results]:
            spec = {
                "description": cls.DESCRIPTION,
                "name": cls.TOOL_NAME,
                "parameters": cls.INPUT_SCHEMA,
            }
            lines.append(f"<function>{json.dumps(spec, ensure_ascii=False)}</function>")
        lines.append("</functions>")
        return "\n".join(lines)

    @staticmethod
    def _collect_deferred_candidates(ctx: ToolContext) -> dict:
        """收集 deferred 候选: 优先 ctx 注入, fallback 全局 DEFERRED_TOOLS_BY_NAME."""
        injected = getattr(ctx, "deferred_tools", None)
        if injected:
            # ctx.deferred_tools 可以是 dict[name → cls] 或 list[cls]
            if isinstance(injected, dict):
                return {k: v for k, v in injected.items()}
            try:
                return {cls.TOOL_NAME: cls for cls in injected}
            except Exception:
                pass
        # fallback: 全局 deferred 集
        try:
            from omnicompany.packages.services._core.agent.routers import (
                DEFERRED_TOOLS_BY_NAME,
            )
            return dict(DEFERRED_TOOLS_BY_NAME)
        except ImportError:
            return {}
