"""Wave 5 续 — Bash / Glob / Grep prompt 1:1 cc 复刻验证 (2026-05-05 立).

验收点 (七层 checklist L1):
  - DESCRIPTION 含 cc 原文关键句
  - omnicompany 适配的项 (跳过段 / 数值 / 命名) 一致
  - omnicompany 独有约束 (find 禁令 / 反斜杠拒) 在 prompt 里告知 LLM

不验收 (Wave 5b 真 LLM smoke 留下次):
  - 真启 LLM 看 prompt 实际效果
  - cc 动态分支 (sandbox / undercover / git option flag) 复刻
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "src"))

from omnicompany.packages.services._core.agent.routers.bash import BashRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    GlobRouter,
    GrepRouter,
)
from omnicompany.packages.services._core.agent.routers.shell_alt_tools import (
    PowerShellRouter,
)
from omnicompany.packages.services._core.agent.routers.skill_tools import SkillRouter
from omnicompany.packages.services._core.agent.routers.agent_spawn import AgentRouter


# ═══════════════════════════════════════════════════════════════════════
# Bash prompt — 关键句来自 cc BashTool/prompt.ts::getSimplePrompt 静态部分
# ═══════════════════════════════════════════════════════════════════════


class TestBashPromptCoreSentences:
    def test_opening_line(self):
        d = BashRouter.DESCRIPTION
        assert "Executes a given bash command and returns its output." in d

    def test_shell_state_warning(self):
        d = BashRouter.DESCRIPTION
        assert "working directory persists between commands, but shell state does not" in d

    def test_avoid_command_list(self):
        d = BashRouter.DESCRIPTION
        # cc 让 LLM 不用 find/grep/cat/head/tail/sed/awk/echo
        assert "find" in d
        assert "grep" in d
        assert "sed" in d
        assert "awk" in d
        assert "Avoid using this tool to run" in d

    def test_tool_replacement_recommendations(self):
        d = BashRouter.DESCRIPTION
        # File / Content / Read / Edit / Write / Communication 替代项
        assert "Use Glob (NOT find or ls)" in d
        assert "Use Grep (NOT grep or rg)" in d
        assert "Use Read (NOT cat/head/tail)" in d
        assert "Use Edit (NOT sed/awk)" in d
        assert "Use Write (NOT echo >/cat <<EOF)" in d
        assert "NOT echo/printf" in d

    def test_quote_paths_with_spaces(self):
        d = BashRouter.DESCRIPTION
        assert "Always quote file paths that contain spaces" in d

    def test_avoid_cd_advice(self):
        d = BashRouter.DESCRIPTION
        assert "absolute paths and avoiding usage of `cd`" in d

    def test_timeout_advisory(self):
        d = BashRouter.DESCRIPTION
        # omnicompany: 60s 默认 / 600s 上限 (跟 BashRouter INPUT_SCHEMA 对齐)
        assert "600s" in d or "10 minutes" in d
        assert "60s" in d

    def test_parallel_command_guidance(self):
        d = BashRouter.DESCRIPTION
        assert "parallel" in d
        assert "&&" in d
        assert "DO NOT use newlines" in d

    def test_git_safety_protocol(self):
        d = BashRouter.DESCRIPTION
        assert "Git Safety Protocol" in d
        assert "force push" in d.lower() or "push --force" in d
        assert "NEVER skip hooks" in d
        assert "Always create NEW commits rather than amending" in d

    def test_git_commit_workflow(self):
        d = BashRouter.DESCRIPTION
        assert "git status" in d
        assert "git diff" in d
        assert "HEREDOC" in d

    def test_sleep_advisory(self):
        d = BashRouter.DESCRIPTION
        assert "Avoid unnecessary `sleep`" in d
        assert "diagnose the root cause" in d


class TestBashPromptOmnicompanySpecific:
    """omnicompany 独有 prompt 约束 — 跟 BashBus 防御层语义一致."""

    def test_find_forbidden_warning(self):
        d = BashRouter.DESCRIPTION
        assert "`find` command is REJECTED" in d
        assert "Glob" in d
        assert "Grep" in d
        # 明确 357 zombie 事故引用
        assert "357 zombie" in d.lower() or "zombie" in d.lower()

    def test_backslash_path_warning(self):
        d = BashRouter.DESCRIPTION
        assert "backslash" in d.lower()
        assert "REJECTED" in d

    def test_dash_p_quoted_warning(self):
        d = BashRouter.DESCRIPTION
        # mkdir "-p" 引号化检测在 prompt
        assert 'mkdir "-p"' in d or "option as quoted directory name" in d

    def test_double_drive_warning(self):
        d = BashRouter.DESCRIPTION
        assert "Mixed POSIX/Windows path drive" in d or "double drive" in d.lower()

    def test_workspace_cwd_warning(self):
        d = BashRouter.DESCRIPTION
        assert "workspace" in d.lower()
        assert "bash_cwd_prefixes" in d


class TestBashPromptSkippedSections:
    """omnicompany 故意跳过的 cc 段 (sandbox / undercover / background) — 不在 prompt."""

    def test_no_sandbox_section(self):
        # claude.ai 沙盒特有, omnicompany 走 BashBus + workspace, 不该有 cc 沙盒段引用
        d = BashRouter.DESCRIPTION
        assert "## Command sandbox" not in d
        assert "dangerouslyDisableSandbox" not in d

    def test_no_background_task_section(self):
        # omnicompany 没 BackgroundTasks 设施, 不该误导 LLM 有 run_in_background
        d = BashRouter.DESCRIPTION
        assert "run_in_background" not in d

    def test_no_undercover_section(self):
        # cc 内部"undercover"段是 USER_TYPE=ant 特有
        d = BashRouter.DESCRIPTION
        assert "undercover" not in d.lower()

    def test_no_pr_creation_section(self):
        # cc 有大段 gh pr create 工作流 — 自动化管线不一定建 PR, 跳
        d = BashRouter.DESCRIPTION
        # 如果未来加, 这测试需更新; 现在保持简短
        assert "Test plan" not in d  # gh pr create body template 关键字


# ═══════════════════════════════════════════════════════════════════════
# Glob prompt — 5 行 cc 原文几乎一致, 验最后一行已修正回 Agent 引用
# ═══════════════════════════════════════════════════════════════════════


class TestGlobPromptCC:
    def test_all_five_lines(self):
        d = GlobRouter.DESCRIPTION
        assert "Fast file pattern matching tool that works with any codebase size" in d
        assert '"**/*.js"' in d
        assert "sorted by modification time" in d
        assert "find files by name patterns" in d
        # Wave 5 续修: "use the Agent tool instead" (原占位 multi-step)
        assert "use the Agent tool instead" in d
        assert "multi-step exploration" not in d  # 原占位已删


# ═══════════════════════════════════════════════════════════════════════
# Grep prompt — 跟 cc 原文几乎一致
# ═══════════════════════════════════════════════════════════════════════


class TestGrepPromptCC:
    def test_ripgrep_intro(self):
        d = GrepRouter.DESCRIPTION
        assert "powerful search tool built on ripgrep" in d

    def test_always_use_grep(self):
        d = GrepRouter.DESCRIPTION
        assert "ALWAYS use grep" in d
        assert "NEVER invoke `grep` or `rg`" in d

    def test_glob_and_type_filter(self):
        d = GrepRouter.DESCRIPTION
        assert "glob parameter" in d
        assert "type parameter" in d

    def test_output_modes(self):
        d = GrepRouter.DESCRIPTION
        assert '"content"' in d
        assert '"files_with_matches"' in d
        assert '"count"' in d

    def test_agent_for_open_ended(self):
        d = GrepRouter.DESCRIPTION
        # Wave 5 续修: cc 原文 "Use Agent tool" — 原 omnicompany 加了 "(or multi-step exploration)" 兜底
        assert "Use Agent tool for open-ended" in d
        assert "(or multi-step exploration)" not in d

    def test_multiline_advice(self):
        d = GrepRouter.DESCRIPTION
        assert "Multiline matching" in d
        assert "multiline: true" in d

    def test_ripgrep_brace_escape_note(self):
        d = GrepRouter.DESCRIPTION
        assert "literal braces need escaping" in d
        assert "interface\\{\\}" in d  # Go code 例子


# ═══════════════════════════════════════════════════════════════════════
# 综合: 三 prompt 给 LLM 的工具引用一致 (Glob/Grep 在 Bash prompt 里被推荐)
# ═══════════════════════════════════════════════════════════════════════


class TestCrossToolConsistency:
    def test_bash_recommends_glob_grep(self):
        """Bash prompt 让 LLM 不用 find/grep, 改 Glob/Grep — 跟 Glob/Grep prompt 一致."""
        d = BashRouter.DESCRIPTION
        assert "Use Glob" in d
        assert "Use Grep" in d

    def test_glob_grep_redirect_to_agent(self):
        """Glob/Grep prompt 大查询时让 LLM 转 Agent — 跟 AgentRouter 真 spawn (Wave 3) 一致."""
        gd = GlobRouter.DESCRIPTION
        rd = GrepRouter.DESCRIPTION
        assert "Agent" in gd
        assert "Agent" in rd


# ═══════════════════════════════════════════════════════════════════════
# PowerShell prompt — cc PowerShellTool/prompt.ts 静态部分 + edition 5.1 兼容
# ═══════════════════════════════════════════════════════════════════════


class TestPowerShellPromptCC:
    def test_opening_line(self):
        d = PowerShellRouter.DESCRIPTION
        assert "Executes a given PowerShell command" in d
        assert "Working directory persists between commands" in d
        assert "shell state (variables, functions) does not" in d

    def test_dont_use_for_file_ops(self):
        d = PowerShellRouter.DESCRIPTION
        assert "DO NOT use it for file operations" in d
        assert "specialized tools for this instead" in d

    def test_edition_5_1_compatibility(self):
        d = PowerShellRouter.DESCRIPTION
        # cc edition 未知时用 5.1 兼容版
        assert "Windows PowerShell 5.1" in d
        assert "&&" in d  # 提到 && 是 7+ only
        assert "PowerShell 7+" in d
        assert "if ($?)" in d  # 5.1 替代写法

    def test_syntax_notes(self):
        d = PowerShellRouter.DESCRIPTION
        assert "Verb-Noun cmdlet naming" in d
        assert "Get-ChildItem" in d
        assert "$env:NAME" in d  # env var 读法
        assert "PSDrive prefixes" in d  # registry 访问
        assert "HKLM:" in d

    def test_interactive_warnings(self):
        d = PowerShellRouter.DESCRIPTION
        assert "Read-Host" in d
        assert "Get-Credential" in d
        assert "NEVER use" in d
        assert "Confirm:$false" in d  # 破坏命令的处理

    def test_heredoc_for_multiline(self):
        d = PowerShellRouter.DESCRIPTION
        assert "here-string" in d
        assert "@'" in d
        assert "'@" in d

    def test_avoid_dedicated_tool_redundancy(self):
        d = PowerShellRouter.DESCRIPTION
        assert "Use Glob" in d
        assert "Get-ChildItem -Recurse" in d  # 反例
        assert "Use Grep" in d
        assert "Select-String" in d  # 反例
        assert "Use Read" in d
        assert "Get-Content" in d  # 反例

    def test_no_cd_prefix(self):
        d = PowerShellRouter.DESCRIPTION
        assert "Do NOT prefix commands with `cd` or `Set-Location`" in d

    def test_timeout_advisory(self):
        d = PowerShellRouter.DESCRIPTION
        assert "60s" in d
        assert "600s" in d or "10 minutes" in d


class TestPowerShellSkippedSections:
    def test_no_background_task(self):
        d = PowerShellRouter.DESCRIPTION
        assert "run_in_background" not in d


# ═══════════════════════════════════════════════════════════════════════
# Skill prompt — cc SkillTool/prompt.ts 静态部分
# ═══════════════════════════════════════════════════════════════════════


class TestSkillPromptCC:
    def test_opening_line(self):
        d = SkillRouter.DESCRIPTION
        assert "Execute a skill within the main conversation" in d

    def test_specialized_capabilities(self):
        d = SkillRouter.DESCRIPTION
        assert "specialized capabilities and domain knowledge" in d

    def test_slash_command_concept(self):
        d = SkillRouter.DESCRIPTION
        assert "slash command" in d
        assert "/<something>" in d

    def test_blocking_requirement(self):
        d = SkillRouter.DESCRIPTION
        assert "BLOCKING REQUIREMENT" in d
        assert "BEFORE generating any other response" in d

    def test_never_mention_without_calling(self):
        d = SkillRouter.DESCRIPTION
        assert "NEVER mention a skill without actually calling this tool" in d

    def test_no_built_in_cli(self):
        d = SkillRouter.DESCRIPTION
        assert "/help" in d
        assert "/clear" in d

    def test_already_loaded_check(self):
        d = SkillRouter.DESCRIPTION
        assert "<command-name>" in d
        assert "ALREADY been loaded" in d


# ═══════════════════════════════════════════════════════════════════════
# Agent prompt — cc AgentTool/prompt.ts 静态部分
# ═══════════════════════════════════════════════════════════════════════


class TestAgentPromptCC:
    def test_opening_line(self):
        d = AgentRouter.DESCRIPTION
        assert "Launch a new agent to handle complex, multi-step tasks" in d

    def test_subagent_types_listed(self):
        d = AgentRouter.DESCRIPTION
        # omnicompany 默认 registry 含三种
        assert "general-purpose" in d
        assert "Explore" in d
        assert "Plan" in d

    def test_when_not_to_use(self):
        d = AgentRouter.DESCRIPTION
        assert "When not to use" in d
        assert "If the target is already known" in d

    def test_brief_like_smart_colleague(self):
        d = AgentRouter.DESCRIPTION
        assert "Brief the agent like a smart colleague" in d
        assert "hasn't seen this conversation" in d

    def test_never_delegate_understanding(self):
        d = AgentRouter.DESCRIPTION
        assert "Never delegate understanding" in d
        assert "based on your findings" in d  # 反例

    def test_starts_fresh_warning(self):
        d = AgentRouter.DESCRIPTION
        assert "starts fresh" in d
        assert "complete task description" in d

    def test_trust_but_verify(self):
        d = AgentRouter.DESCRIPTION
        assert "Trust but verify" in d
        assert "describes what it intended to do, not necessarily what it did" in d

    def test_parallel_invocation(self):
        d = AgentRouter.DESCRIPTION
        assert "in parallel" in d
        assert "multiple Agent tool use content blocks" in d

    def test_subagent_type_param(self):
        d = AgentRouter.DESCRIPTION
        assert "subagent_type" in d
        assert "general-purpose" in d


class TestAgentSkippedSections:
    def test_no_fork_section(self):
        d = AgentRouter.DESCRIPTION
        # cc forkSubagent 是 cc 特性, omnicompany 没
        assert "## When to fork" not in d

    def test_no_remote_isolation(self):
        d = AgentRouter.DESCRIPTION
        # claude.ai CCR 特有
        assert 'isolation: "remote"' not in d
