# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T15:30:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest run_challenge_pipeline V9 — Queue 排序 → top N → ChallengeAgent. 用 mock 验形态合规 + dry_run 模式跑通"
# [OMNI] why="V9 一条龙 helper. 用 monkeypatch mock run_challenge_diagnosis 避真 LLM 调用 — 验 pipeline 形态接通 + dry_run 不跑 agent"
# [OMNI] tags=test,pytest,doctor,pipeline,V9,mock
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_run_challenge_pipeline.py"
"""pytest run_challenge_pipeline.

测 case:
- hypotheses_dir 不存在 → FileNotFoundError
- hypotheses_dir 空 → 返 ranked=[]
- dry_run=True → 只 ranked 不调 agent
- 真用 (mock agent): focus_count=1 → 跑 1 次 mock agent
- focus_count=0 + dry_run → ranked 也 = 0
- skip_frozen 透传到 Queue
- 多 yaml + applies_to 触发 b 类
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml


def _make_yaml_dir(tmp_path: Path, count: int = 3, applies_to: str = "worker"):
    """造 N 个假设 yaml."""
    d = tmp_path / "hyps"
    d.mkdir()
    for i in range(count):
        (d / f"H-{i:03d}.yaml").write_text(yaml.safe_dump({
            "id": f"H-{i:03d}",
            "statement": f"假设 {i} 必须 X",
            "applies_to": applies_to,
            "confidence_level": "low",
            "risk_if_wrong": "high",
            "verification_status": "untested",
        }, allow_unicode=True), encoding="utf-8")
    return d


@pytest.fixture
def patch_project_root(tmp_path, monkeypatch):
    """让 run_challenge_pipeline 用 tmp_path 作项目根 (含 src/omnicompany + docs)."""
    (tmp_path / "src" / "omnicompany").mkdir(parents=True)
    (tmp_path / "docs").mkdir()
    return tmp_path


# ── 边界 ──

def test_pipeline_dir_not_exists_raises(patch_project_root, monkeypatch):
    """hypotheses_dir 不存在 → FileNotFoundError."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    # patch __file__ 让 _project_root() 找 tmp_path
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    try:
        async def go():
            await agents_module.run_challenge_pipeline(
                hypotheses_dir="no_such_dir",
                dry_run=True,
            )
        with pytest.raises(FileNotFoundError):
            asyncio.run(go())
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


def test_pipeline_empty_dir_returns_empty(patch_project_root, monkeypatch):
    """hypotheses_dir 空 → 返 ranked=[]."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    empty = patch_project_root / "empty"
    empty.mkdir()
    try:
        async def go():
            return await agents_module.run_challenge_pipeline(
                hypotheses_dir="empty",
                dry_run=True,
            )
        result = asyncio.run(go())
        assert result["ranked"] == []
        assert "无 yaml" in result["summary"]
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


# ── dry_run 不调 agent ──

def test_pipeline_dry_run_does_not_call_agent(patch_project_root, monkeypatch):
    """dry_run=True 只 ranked, agent_runs=[]."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    _make_yaml_dir(patch_project_root, count=3)

    # mock agent — 应不被调
    agent_called = {"count": 0}
    async def fake_run_challenge_diagnosis(**kwargs):
        agent_called["count"] += 1
        return []
    monkeypatch.setattr(agents_module, "run_challenge_diagnosis", fake_run_challenge_diagnosis)

    try:
        async def go():
            return await agents_module.run_challenge_pipeline(
                hypotheses_dir="hyps",
                applies_to="worker",
                focus_count=2,
                dry_run=True,
            )
        result = asyncio.run(go())
        assert len(result["ranked"]) == 2
        assert result["agent_runs"] == []
        assert agent_called["count"] == 0
        assert "DRY_RUN" in result["summary"]
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


# ── 真用 (mock agent) ──

def test_pipeline_invokes_agent_for_top_n(patch_project_root, monkeypatch):
    """focus_count=2 + 不 dry_run → mock agent 调 2 次."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    _make_yaml_dir(patch_project_root, count=5, applies_to="worker")

    agent_calls: list[dict] = []
    async def fake_run_challenge_diagnosis(**kwargs):
        agent_calls.append(dict(kwargs))
        return ["fake_event_1", "fake_event_2"]
    monkeypatch.setattr(agents_module, "run_challenge_diagnosis", fake_run_challenge_diagnosis)

    try:
        async def go():
            return await agents_module.run_challenge_pipeline(
                hypotheses_dir="hyps",
                applies_to="worker",
                focus_count=2,
            )
        result = asyncio.run(go())
        assert len(result["ranked"]) == 2
        assert len(result["agent_runs"]) == 2
        assert len(agent_calls) == 2
        # 每次 agent 调用应传 hypothesis path + applies_to=worker
        for call in agent_calls:
            assert "focus_hypothesis_yaml_path" in call
            assert call["applies_to"] == "worker"
        assert all(r["events_count"] == 2 for r in result["agent_runs"])
        assert "PIPELINE" in result["summary"]
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


def test_pipeline_agent_failure_does_not_block_others(patch_project_root, monkeypatch):
    """1 agent 失败不阻塞后续."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    _make_yaml_dir(patch_project_root, count=3, applies_to="worker")

    call_count = {"n": 0}
    async def flaky_agent(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("第 1 次故意挂")
        return ["ok"]
    monkeypatch.setattr(agents_module, "run_challenge_diagnosis", flaky_agent)

    try:
        async def go():
            return await agents_module.run_challenge_pipeline(
                hypotheses_dir="hyps",
                applies_to="worker",
                focus_count=3,
            )
        result = asyncio.run(go())
        assert len(result["agent_runs"]) == 3
        # 第 1 个 error, 后 2 个 OK
        errored = [r for r in result["agent_runs"] if "error" in r]
        ok = [r for r in result["agent_runs"] if not r.get("error")]
        assert len(errored) == 1
        assert len(ok) == 2
        assert "RuntimeError" in errored[0]["error"]
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


# ── skip_frozen 透传 ──

def test_pipeline_skip_frozen_default_skips_falsified(patch_project_root, monkeypatch):
    """skip_frozen 默认 True → falsified 假设不进 ranked."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    d = patch_project_root / "hyps"
    d.mkdir()
    (d / "H-active.yaml").write_text(yaml.safe_dump({
        "id": "H-active", "applies_to": "worker",
        "confidence_level": "low", "risk_if_wrong": "high",
        "verification_status": "untested",
    }, allow_unicode=True), encoding="utf-8")
    (d / "H-falsified.yaml").write_text(yaml.safe_dump({
        "id": "H-falsified", "verification_status": "falsified",
        "confidence_level": "low", "risk_if_wrong": "high",
    }, allow_unicode=True), encoding="utf-8")

    try:
        async def go():
            return await agents_module.run_challenge_pipeline(
                hypotheses_dir="hyps",
                applies_to="worker",
                focus_count=10,
                dry_run=True,
            )
        result = asyncio.run(go())
        ids = [r["hypothesis_id"] for r in result["ranked"]]
        assert "H-active" in ids
        assert "H-falsified" not in ids  # 跳过
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


# ── focus_count=0 + dry_run ──

def test_pipeline_focus_count_zero_with_dry_run_returns_zero(patch_project_root, monkeypatch):
    """focus_count=0 + dry_run → ranked=[]."""
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    real_init = agents_module.__file__
    monkeypatch.setattr(agents_module, "__file__",
                        str(patch_project_root / "src" / "omnicompany" / "agents" / "__init__.py"))
    _make_yaml_dir(patch_project_root, count=5)

    try:
        async def go():
            return await agents_module.run_challenge_pipeline(
                hypotheses_dir="hyps",
                focus_count=0,
                dry_run=True,
            )
        result = asyncio.run(go())
        assert result["ranked"] == []
    finally:
        monkeypatch.setattr(agents_module, "__file__", real_init)


# ── helper 导出 ──

def test_run_challenge_pipeline_exported():
    from omnicompany.packages.services._diagnosis.doctor.agents import run_challenge_pipeline
    assert callable(run_challenge_pipeline)
