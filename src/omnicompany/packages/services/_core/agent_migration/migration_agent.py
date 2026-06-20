# [OMNI] origin=ai-ide domain=services/_core/agent_migration ts=2026-05-02T13:00:00Z type=agent status=active agent=ai-ide-current
# [OMNI] summary="LegacyAgnlMigrationAgent - 单 agent 自动改造旧 AgentNodeLoop 子类到新 router 化基础设施"
# [OMNI] why="2026-04-18 router 化重构剩 10 个 P1 子类待迁, AI IDE 手干 5-15 小时, 改用 ConfigurableAgent dogfood + 跟 batch_work_use_omnicompany_agent 对齐. team_builder 不是金标 (用户 5-2 反馈), 默认 1 agent 干完整, HARD 校验/拆分按需加."
# [OMNI] tags=agent,migration,configurable,dogfood,phase-d
# [OMNI] material_id="material:core.agent_migration.legacy_agent_migrator.implementation.py"
"""LegacyAgnlMigrationAgent - 单 agent 改造旧 AgentNodeLoop 子类.

设计原则 (用户 2026-05-02 立):
- 默认 1 个 agent 干完整 (read_file → analyze → write_file → bash smoke 验)
- 不预先拆 worker / team / HARD validator
- 跑 1-2 次后, 不稳/绕圈/注意力散 → 升级多 agent

工具: read_file / grep / write_file / bash / finish (现有 TOOL_REGISTRY 全够)

调用形态:
    agent = LegacyAgnlMigrationAgent(bus=bus)
    await agent.run({"task": "迁移 src/omnicompany/.../judge_agent.py"})

实际就是把 target_path 塞 task 字段, agent 从 prompt 知道流程然后跑.
"""

from __future__ import annotations

import os
import platform as _platform
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.agent import (
    AgentSpec,
    ConfigurableAgent,
    DevBashRouter,  # noqa: F401  (确保 import 触发 SingleToolRouter 子类登记)
    auto_register_singletool_subclasses,
)
from omnicompany.runtime.agent.agent_loop_config import (
    CompactConfig,
    LoopConfig,
    PermissionConfig,
    RetryConfig,
)


# 触发自动注册 (DevBashRouter 等不是 configurable.py _register_builtin_tools 内建的)
auto_register_singletool_subclasses()


_PROMPT_PATH = "src/omnicompany/packages/services/_core/agent_migration/migration_prompt.md"
_DEFAULT_MODEL_ID = "qwen3.6-max-preview"


def _build_substitutions(cwd: str) -> dict[str, str]:
    return {
        "cwd": cwd,
        "platform": _platform.system().lower(),
        "model_id": _DEFAULT_MODEL_ID,
    }


_LOOP_CONFIG = LoopConfig(
    max_turns=50,
    context_window=200_000,
    retry=RetryConfig(
        max_retries=10,
        base_delay_ms=500,
        max_delay_ms=32_000,
        jitter_factor=0.25,
        retry_on_overload=True,
        fallback_model=None,
        fallback_after_attempts=5,
    ),
    compact=CompactConfig(
        aging_threshold=5,
        max_tool_output=20_000,
        truncation_strategy="head_tail",
        max_messages=120,
        auto_compact_enabled=True,
        auto_compact_threshold=0.85,
        auto_compact_max_failures=3,
        compact_preserve_turns=3,
        enable_compression_summary=True,
    ),
    permission=PermissionConfig(
        mode="default",
        always_allow=["finish", "read_file", "grep"],
        always_deny=[],
        ai_classifier_enabled=False,
    ),
    enable_tool_concurrency=True,
    max_concurrent_tools=10,
    budget_warning_threshold=0.9,
)


class LegacyAgnlMigrationAgent(ConfigurableAgent):
    """改造旧 AgentNodeLoop 子类到新 router 化基础设施.

    入参 (run 时传):
        {"task": "迁移 <target_path>"}  或  {"target_path": "...", "task": "..."}

    出参:
        Verdict.output.text — finish 的 result 字符串 (含 MIGRATED/PARTIAL + 类清单 + dropped tools)
    """

    SPEC = AgentSpec(
        id="services._core.agent_migration",
        name="LegacyAgnlMigrationAgent",
        domain="services._core",
        parent_worker_kind="agent",
        registry_namespace="services.agent.instances",
        llm_model="qwen3.6-max-preview",
        llm_temperature=0.2,           # 偏低: 机械迁移, 不要 LLM 加戏
        llm_max_tokens=8000,           # 大输出 — 一次写整个文件
        llm_max_turns=50,              # 50 turn 够单文件 (read 几次 + write 1 次 + bash 1-3 次 + finish)
        llm_timeout_seconds=600,
        prompt_path=_PROMPT_PATH,
        prompt_substitutions={},  # 留空, 避免类级 __init_subclass__ 报错 (prompt 含 JSON 字面 {} 跟 placeholder 冲突). 实例级 _reload_with_cwd 走 PermissiveDict 跑替换.
        tools=("read_file", "grep", "write_file", "bash"),
        allow_custom_code=True,        # build_tool_context override (注 allowed_bash_roots)
    )

    LOOP_CONFIG = _LOOP_CONFIG

    def __init__(
        self,
        *,
        cwd: str | None = None,
        bus: Any | None = None,
        config: LoopConfig | None = None,
    ):
        self._cwd = cwd or os.getcwd()
        # 实例 cwd 重跑 prompt 替换 (类级 SPEC 是构建时一次性, 这里实例级覆盖)
        self._instance_prompt = self._reload_with_cwd(self._cwd)
        super().__init__(
            role="ide_agent",  # 走 ModelRegistry override → qwen3.6-max-preview
            bus=bus,
            config=config or _LOOP_CONFIG,
        )
        from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
        self._prompt_builder = PromptBuilderRouter(template=self._instance_prompt, bus=bus)

    def build_tool_context(self, *, input_data: dict, turn: int, trace_id: str) -> dict:
        """注入 cwd / allowed_bash_roots (DevBashRouter 安全 guard 要求)."""
        return {
            "cwd": self._cwd,
            "project_root": self._cwd,
            "trace_id": trace_id,
            "turn_number": turn,
            "permission_mode": "default",
            "origin": "ai-ide",
            "agent_name": "LegacyAgnlMigrationAgent",
            "domain": "services._core.agent_migration",
            "allowed_bash_roots": (self._cwd,),
            # WriteFileRouter 沙盒: 允许写 cwd 树下任意路径 (跟 bash 同范围)
            "allowed_write_roots": (self._cwd,),
        }

    @classmethod
    def _reload_with_cwd(cls, cwd: str) -> str:
        """读 prompt + str.replace 跑替换 (不走 format, 因 prompt 含 JSON 字面 {...} 跟 format 冲突)."""
        path = Path(_PROMPT_PATH)
        if not path.is_absolute():
            import omnicompany
            project_root = Path(omnicompany.__file__).resolve().parents[2]
            path = project_root / _PROMPT_PATH
        text = path.read_text(encoding="utf-8")
        subs = _build_substitutions(cwd)
        for k, v in subs.items():
            text = text.replace("{" + k + "}", str(v))
        return text


__all__ = ["LegacyAgnlMigrationAgent"]
