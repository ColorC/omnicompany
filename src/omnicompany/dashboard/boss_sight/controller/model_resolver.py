# [OMNI] origin=ai-ide ts=2026-05-29 type=infra
# [OMNI] material_id="material:dashboard.boss_sight.controller.model_resolver.py"
"""BOSS SIGHT 控制器的【模型选择唯一权威】.

收敛原先散在两处的"控制器选 model"决策:
- tools.py `_MODEL_BY_HINT`: 控制器 spawn subagent 时按难度 hint × provider 选 model
- worker.py `DEFAULT_MODEL`: 控制器自身默认 model (= high 档 claude_code)

后续 judge 路由 (升级计划 P3-b) 产出难度 hint, 经本模块 `resolve_model()`
落到真 model 名 — judge 只决"难度档", 真名永远只在这里一处。

【边界 — 不在本模块, 是不同的轴, 切勿合并】:
external_workers/runner.py 的 `resolve_external_agent_model()` 是【外部一次性
worker 的成本策略】(none/cheap × readonly/write), 用的是另一套 model 名
(gpt-5.4-mini / gpt-5.3-codex-spark)。那是"省钱跑只读/写"的轴, 跟控制器
"按任务难度选执行者"是两件事, 合并会造成错位抽象, 故保持独立。
"""

from __future__ import annotations

from .worker_contract import (
    PROVIDER_CLAUDE_CODE,
    PROVIDER_CODEX,
    PROVIDER_OMNI_AGENT,
)

# 控制器自身默认 model (用户 U-034: 总控调度判断对智能要求高, 走 claude 旗舰)
CONTROLLER_DEFAULT_MODEL = "claude-opus-4-7"

# 难度 hint(high/low/default) × provider → 真 model 名 (None = 让 provider 走自己默认)
# 用户原话 §2.12: 切换分配执行者, 部分任务用非高智能模型
_MODEL_BY_HINT: dict[str, dict[str, str | None]] = {
    "high": {
        PROVIDER_CLAUDE_CODE: CONTROLLER_DEFAULT_MODEL,
        PROVIDER_CODEX: "gpt-5.4",
        PROVIDER_OMNI_AGENT: "qwen3.6-plus",
    },
    "low": {
        PROVIDER_CLAUDE_CODE: "claude-sonnet-4-6",
        PROVIDER_CODEX: "gpt-5.3-codex",
        PROVIDER_OMNI_AGENT: "qwen3.6-plus",
    },
    "default": {  # None = 让 provider 走自己默认
        PROVIDER_CLAUDE_CODE: None,
        PROVIDER_CODEX: None,
        PROVIDER_OMNI_AGENT: None,
    },
}

# ctx 上限 cap (用户原话 §2.2: 默认 400k, codex 拉满 256k)
CTX_CAP_BY_PROVIDER: dict[str, int] = {
    PROVIDER_CLAUDE_CODE: 400_000,
    PROVIDER_CODEX: 256_000,
    PROVIDER_OMNI_AGENT: 200_000,
}

VALID_HINTS: tuple[str, ...] = ("high", "low", "default")


def resolve_model(provider: str, hint: str = "default") -> str | None:
    """按 (provider, 难度 hint) 解析控制器要给 subagent 用的 model 名.

    hint 不在 {high, low, default} 时回落到 'default' (= None, provider 自决)。
    """
    return _MODEL_BY_HINT.get(hint, _MODEL_BY_HINT["default"]).get(provider)


__all__ = [
    "CONTROLLER_DEFAULT_MODEL",
    "CTX_CAP_BY_PROVIDER",
    "VALID_HINTS",
    "resolve_model",
]
