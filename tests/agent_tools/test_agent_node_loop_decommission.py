"""T9 guard: legacy runtime AgentNodeLoop and ToolDefinition are retired."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src" / "omnicompany"


def _active_python_files():
    skipped_parts = {"_archive", "_graveyard", "__pycache__"}
    for path in SRC_ROOT.rglob("*.py"):
        if skipped_parts & set(path.parts):
            continue
        yield path


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))


def test_legacy_loop_files_are_removed():
    retired = [
        SRC_ROOT / "runtime" / "agent" / "agent_node_loop.py",
        SRC_ROOT / "runtime" / "agent" / "ide_agent_loop.py",
        SRC_ROOT / "runtime" / "agent" / "agent_loop_permissions.py",
    ]
    assert all(not path.exists() for path in retired)


def test_agent_loop_tools_is_toolcontext_only():
    path = SRC_ROOT / "runtime" / "agent" / "agent_loop_tools.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(path))
    class_names = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}

    assert class_names == {"ToolContext"}
    assert "__all__ = [\"ToolContext\"]" in text
    for retired_name in ["ToolDefinition", "IDE_TOOLS", "ReadFileTool", "BashTool", "FinishTool"]:
        assert retired_name not in text


def test_active_source_does_not_import_legacy_loop_modules():
    forbidden = {
        "omnicompany.runtime.agent.agent_node_loop",
        "omnicompany.runtime.agent.ide_agent_loop",
    }
    offenders: list[str] = []

    for path in _active_python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in forbidden:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden:
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")

    assert offenders == []


def test_active_source_does_not_use_tooldefinition_runtime():
    offenders: list[str] = []

    for path in _active_python_files():
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "ToolDefinition":
                        offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:import")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "ToolDefinition":
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}:call")

    assert offenders == []


def test_pipeline_runner_crystallize_uses_new_agent_loop():
    path = SRC_ROOT / "runtime" / "exec" / "runner.py"
    text = path.read_text(encoding="utf-8")
    assert "packages.services._core.agent.loop import AgentNodeLoop" in text
    assert "runtime.agent.agent_node_loop import AgentNodeLoop" not in text
