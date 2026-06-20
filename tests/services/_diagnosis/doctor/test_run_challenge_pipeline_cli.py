# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T16:05:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest V11 CLI run_challenge_pipeline — argparse / dry_run / hypotheses-dir 错 / output-json / mock pipeline"
# [OMNI] why="V11 CLI 入口让真用户一句命令跑 helper. mock run_challenge_pipeline 验 CLI 形态合规"
# [OMNI] tags=test,pytest,cli,doctor,V11
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_run_challenge_pipeline_cli.py"
"""pytest V11 CLI · run_challenge_pipeline 命令行包装.

测 case:
- argparse 默认值 (dry_run=True / focus_count=1 / hypotheses-dir 默认)
- --no-dry-run 切换
- --include-frozen 透传 (skip_frozen=False)
- --output-json 真写文件 + 不含 hypothesis_dict (slim)
- hypotheses-dir 不存在返 1
- pipeline 失败返 2
- stdout 含 summary + ranked 表格
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from omnicompany.packages.services._diagnosis.doctor.agents import __main__ as cli_module


@pytest.fixture
def fake_pipeline_ok(monkeypatch):
    """mock run_challenge_pipeline 返已知 result."""
    async def fake(*, hypotheses_dir, applies_to, focus_count, skip_frozen,
                   depended_by_threshold, dry_run):
        return {
            "ranked": [
                {"hypothesis_id": "H-fake-1", "priority_score": 1100,
                 "reasons": ["a: x", "b: y"], "hypothesis_dict": {"id": "H-fake-1", "x": "data"}},
                {"hypothesis_id": "H-fake-2", "priority_score": 100,
                 "reasons": ["b: z"], "hypothesis_dict": {"id": "H-fake-2"}},
            ],
            "agent_runs": [] if dry_run else [
                {"hypothesis_id": "H-fake-1", "events_count": 2}
            ],
            "summary": ("DRY_RUN" if dry_run else "PIPELINE") + " ranked=2",
        }
    # patch 模块级引用
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_challenge_pipeline", fake)
    return fake


# ── argparse 默认值 ──

def test_cli_default_dry_run(fake_pipeline_ok, capsys):
    """默认 --dry-run=True."""
    rc = cli_module.main(["--applies-to", "worker"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "DRY_RUN" in out
    assert "H-fake-1" in out
    assert "H-fake-2" in out


def test_cli_default_focus_count_is_1(fake_pipeline_ok, capsys, monkeypatch):
    """默认 focus_count=1."""
    captured_kwargs = {}
    async def capture_kwargs(**kwargs):
        captured_kwargs.update(kwargs)
        return {"ranked": [], "agent_runs": [], "summary": "test"}
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_challenge_pipeline", capture_kwargs)
    cli_module.main([])
    assert captured_kwargs["focus_count"] == 1


# ── --no-dry-run 切换 ──

def test_cli_no_dry_run_calls_agent(fake_pipeline_ok, capsys):
    rc = cli_module.main(["--no-dry-run", "--applies-to", "worker"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "PIPELINE" in out
    # agent_runs 表格
    assert "events" in out
    assert "OK" in out


# ── --include-frozen 透传 ──

def test_cli_include_frozen_sets_skip_frozen_false(monkeypatch, capsys):
    captured = {}
    async def capture(**kwargs):
        captured.update(kwargs)
        return {"ranked": [], "agent_runs": [], "summary": "test"}
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_challenge_pipeline", capture)
    cli_module.main(["--include-frozen"])
    assert captured["skip_frozen"] is False


def test_cli_default_skip_frozen_true(monkeypatch, capsys):
    captured = {}
    async def capture(**kwargs):
        captured.update(kwargs)
        return {"ranked": [], "agent_runs": [], "summary": "test"}
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_challenge_pipeline", capture)
    cli_module.main([])
    assert captured["skip_frozen"] is True


# ── --output-json 真写文件 ──

def test_cli_output_json_writes_slim_result(fake_pipeline_ok, tmp_path, capsys):
    out_file = tmp_path / "result.json"
    rc = cli_module.main([
        "--applies-to", "worker",
        "--output-json", str(out_file),
    ])
    assert rc == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    # summary + ranked + agent_runs 字段
    assert "summary" in data
    assert "ranked" in data
    assert "agent_runs" in data
    # ranked 不含 hypothesis_dict (slim)
    for entry in data["ranked"]:
        assert "hypothesis_dict" not in entry


# ── hypotheses-dir 不存在 ──

def test_cli_hypotheses_dir_not_exists_returns_1(monkeypatch, capsys):
    async def fake(**kwargs):
        raise FileNotFoundError("hypotheses_dir 不存在: bad_path")
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_challenge_pipeline", fake)
    rc = cli_module.main(["--hypotheses-dir", "bad_path"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "ERROR" in err


# ── pipeline 跑挂返 2 ──

def test_cli_pipeline_exception_returns_2(monkeypatch, capsys):
    async def fake(**kwargs):
        raise RuntimeError("pipeline 挂了")
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_challenge_pipeline", fake)
    rc = cli_module.main([])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ERROR pipeline 跑挂" in err
    assert "RuntimeError" in err


# ── parser 形态 ──

def test_parser_has_required_args():
    parser = cli_module._build_parser()
    actions = {a.dest for a in parser._actions}
    for arg in ("hypotheses_dir", "applies_to", "focus_count",
                "depended_by_threshold", "include_frozen", "dry_run", "output_json"):
        assert arg in actions, f"parser 缺 arg: {arg}"
