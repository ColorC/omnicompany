# [OMNI] origin=claude-code domain=omnicompany/omnicompany ts=2026-04-20T00:00:00Z type=config
# [OMNI] material_id="material:omnicompany.module_aggregate.exports.py"
"""omnicompany — Worker / Material / Stock 激活驱动层 (L1 黑板架构 Phase 1 pilot).

核心认知（用户 2026-04-20 洞察）:
  stock = EventBus（已有的 SQLiteBus / MemoryBus, 不需新造）
  material = FactoryEvent（payload + event_type + trace_id 完整映射）
  worker = Router 子类（FORMAT_IN 订阅 → 激活产 FORMAT_OUT）

本目录提供**激活驱动 dispatcher**, 让 Worker 在 EventBus 上订阅激活,
而非通过 pipeline.edges 显式指定下游。

用户洞察落地路径:
  "大部分是重命名 + 设计思维调整 + 原本不严谨的内容清除,
   转成 bus 驱动如果有问题, 通常意味着之前就不严谨, 而不是有新需求."

所以本模块的意义是**暴露不严谨**, 而非引入新需求。
"""
from .worker import Worker, Material, Team
from .material_dispatcher import MaterialDispatcher
from .material_events import publish_material_event, query_material_events
from .llm_client import call_llm_json
from .agent_team_demo import (
    AgentContextScriptWorker,
    AgentLLMWorker,
    AgentToolWorker,
    AgentFinalizerWorker,
    AGENT_TEAM_WORKERS,
)


__all__ = [
    # Core shapes (2026-04-20 用户洞察: 让 import 直接看到 omnicompany 词汇)
    "Worker",       # protocol 层 Router 的 omnicompany 层基类
    "Material",     # protocol 层 Format 的 alias
    "Team",         # protocol 层 TeamSpec 的 alias
    # Runtime
    "MaterialDispatcher",
    "publish_material_event",
    "query_material_events",
    # Shared LLM helper (2026-04-23 提到共享层)
    "call_llm_json",
    # Agent Team demo workers (金标样本)
    "AgentContextScriptWorker",
    "AgentLLMWorker",
    "AgentToolWorker",
    "AgentFinalizerWorker",
    "AGENT_TEAM_WORKERS",
]
