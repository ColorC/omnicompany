# -*- coding: utf-8 -*-
"""一次性脚本: 从 yarn_blocks_raw.json 浓缩 + 写 yarn_blocks/class_index.md."""
from __future__ import annotations

import json
import pathlib
import re


def parse(javap_out: str) -> tuple[str, list[str]]:
    """**保留全限定路径**, 不 simplify (LLM 需看真包路径才能写对 import)."""
    lines = javap_out.split("\n")
    extends = ""
    methods: list[str] = []
    for ln in lines:
        ln = ln.strip()
        if (ln.startswith("public class") or ln.startswith("public abstract class")
                or ln.startswith("public final class") or ln.startswith("class ")
                or ln.startswith("public interface")):
            m = re.search(r"extends\s+([\w.$]+)", ln)
            if m:
                extends = m.group(1)  # 保留全路径
        elif (ln.startswith("public ") or ln.startswith("protected ")) and "(" in ln and ln.endswith(";"):
            sig = ln.rstrip(";")  # 不 simplify
            methods.append(sig)
    return extends, methods


def main() -> None:
    raw = json.loads(pathlib.Path("/tmp/yarn_blocks_raw.json").read_text(encoding="utf-8"))
    condensed: dict = {}
    for cls, raw_text in raw.items():
        ext, ms = parse(raw_text)
        condensed[cls] = {"extends": ext, "methods": ms}

    print(f"condensed classes: {len(condensed)}")

    lines: list[str] = []
    lines.append("<!-- [OMNI] origin=claude-code domain=data/domains/voxel_engine/references/yarn_blocks ts=2026-04-26T15:00:00Z type=doc status=active -->")
    lines.append("")
    lines.append("# Yarn 1.21.1 Block class index (net.voxel_sandbox.block.*)")
    lines.append("")
    lines.append("> Source: javap -protected on each .class in net/voxel_sandbox/block/.")
    lines.append("> Use: BlockEngineer LLM looks up which methods are overrideable + their real signatures.")
    lines.append("")
    lines.append(f"- Total classes: {len(condensed)}")
    lines.append("")
    lines.append("## Hot base classes (full method list)")
    lines.append("")

    hot = ["AbstractBlock", "Block", "LeavesBlock", "FallingBlock", "TransparentBlock",
           "GlassBlock", "StainedGlassBlock", "SlabBlock", "StairsBlock", "FenceBlock",
           "WallBlock", "DoorBlock", "TrapdoorBlock", "TorchBlock", "LanternBlock",
           "PressurePlateBlock", "ButtonBlock", "GrassBlock", "DirtBlock"]

    for cls in hot:
        if cls not in condensed:
            continue
        info = condensed[cls]
        lines.append(f"### `net.voxel_sandbox.block.{cls}` (extends {info['extends']})")
        lines.append("")
        if info["methods"]:
            for m in info["methods"]:
                lines.append(f"- `{m}`")
        else:
            lines.append("- (no exposed methods, constructors only)")
        lines.append("")

    lines.append("## All classes (alphabetical)")
    lines.append("")
    lines.append("> Class name + extends + method count. Look up details via javap or search above hot list.")
    lines.append("")
    lines.append("| Class | Extends | Method count |")
    lines.append("|---|---|---|")
    for cls in sorted(condensed.keys()):
        info = condensed[cls]
        lines.append(f"| `{cls}` | `{info['extends'] or '-'}` | {len(info['methods'])} |")
    lines.append("")
    lines.append("## Usage")
    lines.append("")
    lines.append("- Before writing a Block subclass, look up the target base class here to see its overridable methods.")
    lines.append("- Example: 'fully opaque leaves block' -> check LeavesBlock for `protected int getOpacity(BlockState, BlockView, BlockPos)` (3 params, not 1).")
    lines.append("- LLM picks base class + which methods must be overridden. Designer does not specify.")

    out = pathlib.Path("/workspace/omnicompany/data/domains/voxel_engine/references/yarn_blocks/class_index.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(lines)} lines)")


if __name__ == "__main__":
    main()
