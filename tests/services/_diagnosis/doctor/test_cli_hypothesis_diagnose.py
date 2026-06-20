# [OMNI] origin=ai-ide domain=tests/services/_diagnosis/doctor ts=2026-05-07T22:05:00Z type=test status=active agent=ai-ide
# [OMNI] summary="pytest V20 CLI cli_hypothesis_diagnose — argparse / mock helper / output-json / 退出码"
# [OMNI] why="V20 CLI 让真用户跑批量诊断不用写 Python. mock helper 验形态合规"
# [OMNI] tags=test,pytest,cli,doctor,V20
# [OMNI] material_id="material:tests.services.diagnosis.doctor.test_cli_hypothesis_diagnose.py"
"""pytest V20 CLI · HypothesisDiagnosticAgent 命令行入口.

测 case:
- argparse 必填 --target / --target-kind / --hypothesis-yaml
- target-kind choices 限制
- 多假设 --hypothesis-yaml H-A H-B ...
- mock helper 验调用参数
- output-json 真写 + 含 findings 完整字段
- 异常返 2
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from omnicompany.packages.services._diagnosis.doctor.agents import (
    cli_hypothesis_diagnose as cli_module,
)


class _FakeEvent:
    def __init__(self, event_type, payload):
        self.event_type = event_type
        self.payload = payload


@pytest.fixture
def fake_helper(monkeypatch):
    captured = {}
    async def fake(**kwargs):
        captured.update(kwargs)
        return [
            _FakeEvent("doctor.hypothesis_diagnosis.request", {}),
            _FakeEvent("doctor.hypothesis_diagnosis.verdict", {
                "findings": [
                    {"finding_kind": "hypothesis", "applied_hypotheses": ["H-fake-001"],
                     "evidence": "fake.py:10 缺 X", "commentary": "fake commentary 30+ chars",
                     "concern": "fake concern 30+ chars natural language meaning"},
                ],
                "creative_content": "fake creative_content for testing CLI behavior with full sentences",
            }),
        ]
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_hypothesis_diagnosis", fake)
    return captured


# ── argparse ──

def test_cli_required_target(capsys):
    with pytest.raises(SystemExit):
        cli_module.main(["--target-kind", "worker", "--hypothesis-yaml", "x.yaml"])


def test_cli_required_target_kind(capsys):
    with pytest.raises(SystemExit):
        cli_module.main(["--target", "x.py", "--hypothesis-yaml", "x.yaml"])


def test_cli_target_kind_choices_invalid(capsys):
    with pytest.raises(SystemExit):
        cli_module.main([
            "--target", "x.py",
            "--target-kind", "invalid_kind",
            "--hypothesis-yaml", "x.yaml",
        ])


def test_cli_required_hypothesis_yaml(capsys):
    with pytest.raises(SystemExit):
        cli_module.main(["--target", "x.py", "--target-kind", "worker"])


# ── mock 跑通 ──

def test_cli_calls_helper_with_args(fake_helper, capsys):
    rc = cli_module.main([
        "--target", "src/x/team.py",
        "--target-kind", "team",
        "--hypothesis-yaml", "H-001.yaml",
    ])
    assert rc == 0
    assert fake_helper["target_entity_path"] == "src/x/team.py"
    assert fake_helper["target_entity_kind"] == "team"
    assert fake_helper["applicable_hypothesis_paths"] == ["H-001.yaml"]


def test_cli_multiple_hypothesis_yaml(fake_helper, capsys):
    rc = cli_module.main([
        "--target", "src/x/team.py",
        "--target-kind", "team",
        "--hypothesis-yaml", "H-A.yaml", "H-B.yaml", "H-C.yaml",
    ])
    assert rc == 0
    assert fake_helper["applicable_hypothesis_paths"] == ["H-A.yaml", "H-B.yaml", "H-C.yaml"]


def test_cli_stdout_table(fake_helper, capsys):
    cli_module.main([
        "--target", "src/x/team.py",
        "--target-kind", "team",
        "--hypothesis-yaml", "H-001.yaml",
    ])
    out = capsys.readouterr().out
    assert "events: 2" in out
    assert "findings: 1" in out
    assert "H-fake-001" in out
    assert "fake.py:10" in out


# ── output-json ──

def test_cli_output_json_writes_full_findings(fake_helper, tmp_path):
    out_file = tmp_path / "verdict.json"
    rc = cli_module.main([
        "--target", "src/x/team.py",
        "--target-kind", "team",
        "--hypothesis-yaml", "H-001.yaml",
        "--output-json", str(out_file),
    ])
    assert rc == 0
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert data["target"] == "src/x/team.py"
    assert data["target_kind"] == "team"
    assert data["events_count"] == 2
    assert data["findings_count"] == 1
    # 完整 finding 含 evidence/commentary/concern
    assert data["findings"][0]["evidence"] == "fake.py:10 缺 X"
    assert "natural language" in data["findings"][0]["concern"]


# ── 异常 ──

def test_cli_helper_exception_returns_2(monkeypatch, capsys):
    async def broken(**kwargs):
        raise RuntimeError("helper 挂了")
    from omnicompany.packages.services._diagnosis.doctor import agents as agents_module
    monkeypatch.setattr(agents_module, "run_hypothesis_diagnosis", broken)
    rc = cli_module.main([
        "--target", "x.py",
        "--target-kind", "worker",
        "--hypothesis-yaml", "x.yaml",
    ])
    assert rc == 2
    err = capsys.readouterr().err
    assert "ERROR" in err
    assert "RuntimeError" in err


# ── parser 形态 ──

def test_parser_has_required_args():
    parser = cli_module._build_parser()
    actions = {a.dest for a in parser._actions}
    for arg in ("target", "target_kind", "hypothesis_yaml", "output_json"):
        assert arg in actions
