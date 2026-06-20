# [OMNI] origin=codex domain=tests/cli ts=2026-05-17 type=test status=draft
"""Tests for `omni context resolve` progressive context resolution."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_context_resolve_combines_plan_index_and_profiles(tmp_path, monkeypatch):
    from omnicompany.cli.commands import context as context_mod

    monkeypatch.setattr(context_mod, "_project_root", lambda: tmp_path)

    _write(
        tmp_path / "docs/plans/voxel_engine/TEST/plan.md",
        "---\n"
        "title: TEST\n"
        "project: voxel_engine\n"
        "standards:\n"
        "  - standards/protocol/progressive_context.md\n"
        "---\n"
        "# TEST\n",
    )
    _write(tmp_path / "docs/plans/voxel_engine/TEST/brief.md", "# brief\n")
    _write(tmp_path / "docs/plans/voxel_engine/project.md", "# project\n")
    _write(tmp_path / "docs/standards/protocol/progressive_context.md", "# progressive\n")
    _write(tmp_path / "docs/standards/concepts/material.md", "# material\n")
    _write(tmp_path / "docs/standards/concepts/worker.md", "# worker\n")
    _write(tmp_path / "templates/material/register.yaml", "kind: material\n")
    _write(tmp_path / "templates/worker/register.yaml", "kind: worker\n")

    _write(
        tmp_path / "docs/standards/_meta/standards-index.yaml",
        "standards:\n"
        "  - id: MATERIAL\n"
        "    file: docs/standards/concepts/material.md\n"
        "    applies_to: [standard_md]\n"
        "    path_match: [docs/standards/_domain_specific/voxel_engine/**]\n"
        "kind_inference:\n"
        "  - kind: standard_md\n"
        "    match: [docs/standards/**/*.md]\n",
    )
    _write(
        tmp_path / "docs/standards/_meta/context-bindings.yaml",
        "version: 1\n"
        "profiles:\n"
        "  - id: base\n"
        "    priority: 10\n"
        "    applies: {always: true}\n"
        "    include:\n"
        "      standards: [docs/standards/protocol/progressive_context.md]\n"
        "  - id: voxel_engine-material\n"
        "    priority: 20\n"
        "    applies:\n"
        "      projects: [voxel_engine]\n"
        "      trigger_keywords: [material, worker]\n"
        "    include:\n"
        "      standards: [docs/standards/concepts/worker.md]\n"
        "      templates: [templates/material/register.yaml, templates/worker/register.yaml]\n",
    )

    result = CliRunner().invoke(
        context_mod.cmd_context,
        [
            "resolve",
            "--plan",
            "voxel_engine/TEST",
            "--path",
            "docs/standards/_domain_specific/voxel_engine/building.md",
            "--topic",
            "material worker",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    paths = {item["path"] for item in data["contexts"]}
    assert "docs/plans/voxel_engine/TEST/plan.md" in paths
    assert "docs/plans/voxel_engine/TEST/brief.md" in paths
    assert "docs/plans/voxel_engine/project.md" in paths
    assert "docs/standards/concepts/material.md" in paths
    assert "docs/standards/concepts/worker.md" in paths
    assert "templates/material/register.yaml" in paths
    assert data["missing_total"] == 0
