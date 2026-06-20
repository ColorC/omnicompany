# [OMNI] origin=ai-ide ts=2026-05-23 type=infra
# [OMNI] material_id="material:dashboard.boss_sight.controller.package_init.py"
"""controller — 总控 agent 本体.

模块:
- boundary_guard: 工具白名单 + 路径黑名单 enforcement
- prompt_loader:  读 prompts/ + 文件 watcher 热更新
- ctx_loader:     装载 plan_index + subagent_status 到总控 ctx
- wake_up:        EventBus 订阅三种唤起条件
- agent_loop:     总控 AgentNodeLoop 包装(常驻多轮)
- service:        FastAPI 集成入口 (启停 + 路由)
- reflection:     prompt 反思 + 重复检测 (T1.5)
"""

from __future__ import annotations
