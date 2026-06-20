# [OMNI] origin=ai-ide domain=services/_core/agent_migration ts=2026-05-02T13:00:00Z type=service status=active agent=ai-ide-current
# [OMNI] summary="agent_migration service - 单 agent 自动迁移旧 AgentNodeLoop 子类到新 router 化架构"
# [OMNI] why="2026-04-18 router 化重构剩 10 个 P1 子类待迁, AI IDE 手干 5-15 小时, 用 agent dogfood + 跟 batch_work_use_omnicompany_agent 对齐"
# [OMNI] material_id="material:core.agent_migration.service_aggregator.exports.py"
"""agent_migration service - 单 agent 迁移旧 AgentNodeLoop 子类.

公开:
    LegacyAgnlMigrationAgent  - ConfigurableAgent 子类, 用 read_file/write_file/bash/grep
                                自动改造旧 runtime.agent.agent_node_loop.AgentNodeLoop
                                继承的子类到新 packages.services._core.agent.AgentNodeLoop
"""

# 显式加载项目根 .env (THE_COMPANY_API_KEY sk-... 等), 跟 dashboard/app.py / cli/main.py 一致
# 直接跑 Python 脚本时 shell 可能没继承 sk- key, 用 .env 覆盖
try:
    from pathlib import Path as _Path
    from dotenv import load_dotenv as _load_dotenv
    import omnicompany as _o
    _load_dotenv(_Path(_o.__file__).resolve().parents[2] / ".env", override=True)
except ImportError:
    pass

from omnicompany.packages.services._core.agent_migration.migration_agent import (
    LegacyAgnlMigrationAgent,
)

__all__ = ["LegacyAgnlMigrationAgent"]
