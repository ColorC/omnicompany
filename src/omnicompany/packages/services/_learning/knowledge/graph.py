# [OMNI] origin=claude-code domain=services/knowledge/graph.py ts=2026-04-18T00:00:00Z
# [OMNI] material_id="material:learning.knowledge.hypothesis_graph.traversal.py"
"""omnikb.graph — 假设图的只读查询操作。

所有函数操作 KBIndex（只读）。假设条目类型为 khyp (KHypothesisEntry)。

当前保留的操作（都是纯查询，无副作用）:
  - walk_upstream     : BFS 沿 depends_on 向上遍历
  - walk_downstream   : 沿 depends_on 反向找所有依赖者
  - walk_derivations  : 沿 derived_from 找所有精化子代
  - find_contradictions: 返回所有 contradicts 对
  - find_roots        : 找没有 depends_on 的根假设
  - find_leaves       : 找没有被任何假设 depends_on 的叶假设
  - hypothesis_summary: 图全景摘要

已删除（v2/v3 架构残留）:
  - auto_transition   : v2 的"证据计数驱动状态转移"。违反新架构的语义判断原则。
                        新架构：状态转移是 Reflector 的语义判断，代码不驱动。
  - backpropagate     : v2 的 JTMS 回溯。同样违反新架构。
                        未来若需要结构化 JTMS，应走 Reflector 读取 event stream
                        主动级联降级，而非代码旁路。
"""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from omnicompany.packages.services._learning.knowledge.index import KBIndex
    from omnicompany.packages.services._learning.knowledge.schema import KHypothesisEntry
    from omnicompany.packages.services._learning.knowledge.store import KBStore

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 遍历
# ═══════════════════════════════════════════════════════════

def walk_upstream(index: "KBIndex", root_id: str) -> list[str]:
    """BFS 沿 depends_on 向上遍历，返回所有上游假设 id（不含 root_id 自身）。"""
    visited: set[str] = set()
    queue: deque[str] = deque()

    entry = index.get(root_id)
    if entry is None or entry.omnikb_type != "khyp":
        return []

    for dep_id in getattr(entry, "depends_on", []) or []:
        if dep_id not in visited:
            visited.add(dep_id)
            queue.append(dep_id)

    while queue:
        current_id = queue.popleft()
        current = index.get(current_id)
        if current is None or current.omnikb_type != "khyp":
            continue
        for dep_id in getattr(current, "depends_on", []) or []:
            if dep_id not in visited:
                visited.add(dep_id)
                queue.append(dep_id)

    return sorted(visited)


def walk_downstream(index: "KBIndex", target_id: str) -> list[str]:
    """找所有 depends_on 包含 target_id 的假设（直接 + 传递）。"""
    # 先建反向索引
    reverse: dict[str, list[str]] = {}
    for kh in index.all_khypotheses():
        for dep in kh.depends_on or []:
            reverse.setdefault(dep, []).append(kh.id)

    visited: set[str] = set()
    queue: deque[str] = deque()

    for child_id in reverse.get(target_id, []):
        if child_id not in visited:
            visited.add(child_id)
            queue.append(child_id)

    while queue:
        current_id = queue.popleft()
        for child_id in reverse.get(current_id, []):
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)

    return sorted(visited)


def walk_derivations(index: "KBIndex", parent_id: str) -> list[str]:
    """找所有 derived_from == parent_id 的精化子代（直接 + 传递）。"""
    # 建 derived_from 反向索引
    reverse: dict[str, list[str]] = {}
    for kh in index.all_khypotheses():
        if kh.derived_from:
            reverse.setdefault(kh.derived_from, []).append(kh.id)

    visited: set[str] = set()
    queue: deque[str] = deque()

    for child_id in reverse.get(parent_id, []):
        if child_id not in visited:
            visited.add(child_id)
            queue.append(child_id)

    while queue:
        current_id = queue.popleft()
        for child_id in reverse.get(current_id, []):
            if child_id not in visited:
                visited.add(child_id)
                queue.append(child_id)

    return sorted(visited)


def find_contradictions(index: "KBIndex") -> list[tuple[str, str]]:
    """返回所有 contradicts 对（去重，每对只出现一次）。"""
    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for kh in index.all_khypotheses():
        for ref in kh.contradicts or []:
            pair = tuple(sorted([kh.id, ref]))
            if pair not in seen:
                seen.add(pair)
                pairs.append(pair)
    return pairs


def find_roots(index: "KBIndex") -> list[str]:
    """找没有 depends_on 的根假设。"""
    return [kh.id for kh in index.all_khypotheses()
            if not kh.depends_on]


def find_leaves(index: "KBIndex") -> list[str]:
    """找没有被任何假设 depends_on 的叶假设。"""
    all_depended: set[str] = set()
    all_ids: set[str] = set()
    for kh in index.all_khypotheses():
        all_ids.add(kh.id)
        for dep in kh.depends_on or []:
            all_depended.add(dep)
    return sorted(all_ids - all_depended)


# ═══════════════════════════════════════════════════════════
# 图摘要（黑板视图）
# ═══════════════════════════════════════════════════════════

def hypothesis_summary(index: "KBIndex") -> dict:
    """返回假设图的结构化摘要。

    返回:
      {
        "total": int,
        "by_maturity": {"draft": N, "living": N, "stable": N, "deprecated": N},
        "by_kind": {"state": N, "transition": N, "policy": N, "invariant": N},
        "roots": [id, ...],
        "leaves": [id, ...],
        "contradictions": [(id, id), ...],
        "chains": int,  # 连通分量数
      }
    """
    all_hyps = index.all_khypotheses()

    by_maturity: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    for kh in all_hyps:
        by_maturity[kh.maturity] = by_maturity.get(kh.maturity, 0) + 1
        by_kind[kh.kind] = by_kind.get(kh.kind, 0) + 1

    # 连通分量数（undirected view of depends_on + derived_from）
    adj: dict[str, set[str]] = {kh.id: set() for kh in all_hyps}
    for kh in all_hyps:
        for dep in kh.depends_on or []:
            if dep in adj:
                adj[kh.id].add(dep)
                adj[dep].add(kh.id)
        if kh.derived_from and kh.derived_from in adj:
            adj[kh.id].add(kh.derived_from)
            adj[kh.derived_from].add(kh.id)

    visited: set[str] = set()
    components = 0
    for node in adj:
        if node not in visited:
            components += 1
            stack = [node]
            while stack:
                n = stack.pop()
                if n in visited:
                    continue
                visited.add(n)
                stack.extend(adj[n] - visited)

    return {
        "total": len(all_hyps),
        "by_maturity": by_maturity,
        "by_kind": by_kind,
        "roots": find_roots(index),
        "leaves": find_leaves(index),
        "contradictions": find_contradictions(index),
        "chains": components,
    }
