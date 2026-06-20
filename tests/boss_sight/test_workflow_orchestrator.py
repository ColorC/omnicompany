# [OMNI] origin=ai-ide ts=2026-06-06 type=test
"""N2d WorkflowOrchestrator 确定性引擎单测 (mock spawn + materials, 喂合成事件)。

不起真 subagent: 注入假 spawn_fn(返回确定 id) + 假 materials_fn, 直接调 _advance
模拟 subagent.completed 推进, 断言 fan-out 全完成 → 自动综合 → done。
"""
from __future__ import annotations

import pytest

from omnicompany.dashboard.boss_sight.services.workflow_orchestrator import (
    WorkflowOrchestrator,
)


def _make_orch(tmp_path, spawned):
    counter = {"n": 0}

    async def fake_spawn(*, prompt, plan_id, cwd, provider, model):
        counter["n"] += 1
        sid = f"sub-{counter['n']}"
        spawned.append((sid, prompt, plan_id))
        return sid

    def fake_materials(sid):
        return [f"mat-{sid}"]

    return WorkflowOrchestrator(store_root=tmp_path, spawn_fn=fake_spawn, materials_fn=fake_materials)


@pytest.mark.asyncio
async def test_fanout_then_synth(tmp_path):
    spawned: list = []
    orch = _make_orch(tmp_path, spawned)
    wf = await orch.create_and_run({
        "plan_id": "p/x", "tasks": ["任务1", "任务2"], "synthesize": "综合两者",
    })
    wf_id = wf["id"]
    assert wf["fanout_total"] == 2
    assert wf["status"] == "running"
    assert len(spawned) == 2  # 两个 fan-out subagent 起了

    # 第一个 fan-out 完成 → 还没全完成, 不综合
    await orch._advance("sub-1", "子任务1产出")
    v = orch.get(wf_id)
    assert v["status"] == "running"
    assert v["fanout_done"] == 1
    assert not v["synth_spawned"]

    # 第二个 fan-out 完成 → 全完成 → 自动 spawn 综合 subagent
    await orch._advance("sub-2", "子任务2产出")
    v = orch.get(wf_id)
    assert v["status"] == "synthesizing"
    assert v["synth_spawned"] is True
    assert len(spawned) == 3  # 综合 subagent 起了
    # fan-out 子任务收集到了材料
    ft = [t for t in v["tasks"] if t["role"] == "fanout"]
    assert ft[0]["material_ids"] == ["mat-sub-1"]
    assert ft[1]["material_ids"] == ["mat-sub-2"]
    # 综合 prompt 带上了 fan-out 的材料清单
    synth_prompt = spawned[2][1]
    assert "mat-sub-1" in synth_prompt and "mat-sub-2" in synth_prompt
    assert "综合两者" in synth_prompt

    # 综合 subagent 完成 → workflow done
    synth_sid = spawned[2][0]
    await orch._advance(synth_sid, "综合完成")
    assert orch.get(wf_id)["status"] == "done"


@pytest.mark.asyncio
async def test_no_synth_completes_after_fanout(tmp_path):
    spawned: list = []
    orch = _make_orch(tmp_path, spawned)
    wf = await orch.create_and_run({"plan_id": "p/y", "tasks": ["a", "b"]})  # 无 synthesize
    wf_id = wf["id"]
    await orch._advance("sub-1", "")
    assert orch.get(wf_id)["status"] == "running"
    await orch._advance("sub-2", "")
    v = orch.get(wf_id)
    assert v["status"] == "done"
    assert not v["synth_spawned"]
    assert len(spawned) == 2  # 没多起综合


@pytest.mark.asyncio
async def test_double_completion_no_double_synth(tmp_path):
    """同一 fan-out 完成事件来两次, 不能重复推进/重复 spawn 综合。"""
    spawned: list = []
    orch = _make_orch(tmp_path, spawned)
    wf = await orch.create_and_run({"plan_id": "p/z", "tasks": ["only"], "synthesize": "s"})
    wf_id = wf["id"]
    await orch._advance("sub-1", "x")
    await orch._advance("sub-1", "x")  # 重复事件
    v = orch.get(wf_id)
    assert v["status"] == "synthesizing"
    # 1 fan-out + 1 synth = 2, 不能因重复事件多 spawn
    assert len(spawned) == 2


@pytest.mark.asyncio
async def test_persistence_reload(tmp_path):
    spawned: list = []
    orch = _make_orch(tmp_path, spawned)
    wf = await orch.create_and_run({"plan_id": "p/p", "tasks": ["t"], "synthesize": "s"})
    wf_id = wf["id"]
    await orch._advance("sub-1", "done")  # 触发综合 spawn
    # 新引擎从同一盘加载, 应重建实例 + subagent 索引
    orch2 = WorkflowOrchestrator(store_root=tmp_path, spawn_fn=orch._spawn_fn, materials_fn=orch._materials_fn)
    v = orch2.get(wf_id)
    assert v is not None
    assert v["status"] == "synthesizing"
    assert v["synth_spawned"] is True
    # 索引重建: 综合 subagent 完成能被 orch2 推进到 done
    synth_sid = spawned[1][0]
    await orch2._advance(synth_sid, "ok")
    assert orch2.get(wf_id)["status"] == "done"


@pytest.mark.asyncio
async def test_validation(tmp_path):
    orch = _make_orch(tmp_path, [])
    with pytest.raises(ValueError):
        await orch.create_and_run({"plan_id": "", "tasks": ["t"]})  # 缺 plan
    with pytest.raises(ValueError):
        await orch.create_and_run({"plan_id": "p", "tasks": []})  # 无任务


@pytest.mark.asyncio
async def test_on_event_ignores_unrelated(tmp_path):
    """on_event 对非 subagent.completed / 非本工作流 subagent 不调度推进。"""
    spawned: list = []
    orch = _make_orch(tmp_path, spawned)
    calls: list = []

    async def spy(sid, preview):
        calls.append(sid)

    orch._advance = spy  # type: ignore[assignment]
    # 未知 subagent → 不调度
    orch.on_event(None, "subagent.completed", {"subagent_id": "stranger"}, [])
    # 非完成事件 → 不调度
    orch.on_event(None, "subagent.spawned", {"subagent_id": "x"}, [])
    import asyncio
    await asyncio.sleep(0)
    assert calls == []
