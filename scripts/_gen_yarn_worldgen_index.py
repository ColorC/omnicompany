# -*- coding: utf-8 -*-
"""一次性脚本: 从 yarn_worldgen_raw.json 写 yarn_worldgen/class_index.md."""
from __future__ import annotations

import json
import pathlib
import re


def parse(javap_out: str) -> tuple[str, list[str]]:
    """保留全限定路径."""
    lines = javap_out.split("\n")
    extends = ""
    methods: list[str] = []
    for ln in lines:
        ln = ln.strip()
        if (ln.startswith("public class") or ln.startswith("public abstract class")
                or ln.startswith("public final class") or ln.startswith("class ")
                or ln.startswith("public interface") or ln.startswith("public record")):
            m = re.search(r"extends\s+([\w.$]+)", ln)
            if m:
                extends = m.group(1)
        elif (ln.startswith("public ") or ln.startswith("protected ")) and "(" in ln and ln.endswith(";"):
            sig = ln.rstrip(";")
            methods.append(sig)
    return extends, methods


def main() -> None:
    raw = json.loads(pathlib.Path("/tmp/yarn_worldgen_raw.json").read_text(encoding="utf-8"))
    condensed: dict = {}
    for cls, raw_text in raw.items():
        short = cls.split(".")[-1]
        ext, ms = parse(raw_text)
        condensed[short] = {"full": cls, "extends": ext, "methods": ms}

    print(f"condensed worldgen classes: {len(condensed)}")

    lines: list[str] = []
    lines.append("<!-- [OMNI] origin=claude-code domain=data/domains/voxel_engine/references/yarn_worldgen ts=2026-04-26T17:00:00Z type=doc status=active -->")
    lines.append("")
    lines.append("# Yarn 1.21.1 Worldgen class index")
    lines.append("")
    lines.append("> Source: javap -protected on net/voxel_sandbox/world/gen/, /world/biome/, /structure/, /world/dimension/.")
    lines.append("> Use: WorldgenEngineer LLM looks up real signatures + class paths for ConfiguredFeature/PlacedFeature/BiomeModifier.")
    lines.append("")
    lines.append(f"- Total classes: {len(condensed)}")
    lines.append("")
    lines.append("## Hot classes (full method list)")
    lines.append("")

    hot = [
        # ConfiguredFeature 系
        "ConfiguredFeature", "Feature", "RegistryKey",
        "RandomPatchFeatureConfig", "SimpleBlockFeatureConfig",
        "BlockStateProvider", "SimpleBlockStateProvider",
        # PlacedFeature 系
        "PlacedFeature", "PlacementModifier", "CountPlacementModifier",
        "RarityFilterPlacementModifier", "InSquarePlacementModifier",
        "HeightRangePlacementModifier",
        # Biome 系
        "Biome", "BiomeKeys", "GenerationStep",
        # Structure 系
        "Structure", "StructureType", "StructurePoolElement",
    ]

    for cls in hot:
        if cls not in condensed:
            continue
        info = condensed[cls]
        lines.append(f"### `{info['full']}` (extends {info['extends']})")
        lines.append("")
        if info["methods"]:
            for m in info["methods"][:30]:
                lines.append(f"- `{m}`")
            if len(info["methods"]) > 30:
                lines.append(f"- (... {len(info['methods'])-30} more methods)")
        else:
            lines.append("- (no exposed methods)")
        lines.append("")

    lines.append("## All classes (alphabetical)")
    lines.append("")
    lines.append("| Class | Full path | Extends | Methods |")
    lines.append("|---|---|---|---|")
    for cls in sorted(condensed.keys()):
        info = condensed[cls]
        lines.append(f"| `{cls}` | `{info['full']}` | `{info['extends'] or '-'}` | {len(info['methods'])} |")
    lines.append("")
    lines.append("## Datapack JSON references (most critical for worldgen)")
    lines.append("")
    lines.append("Worldgen 大部分配置走 datapack JSON, 不是 Java 类继承. 关键 JSON schema:")
    lines.append("")
    lines.append("**configured_feature/<id>.json** schema:")
    lines.append("```json")
    lines.append('{')
    lines.append('  "type": "voxel_sandbox:random_patch",')
    lines.append('  "config": {')
    lines.append('    "tries": 64,')
    lines.append('    "xz_spread": 7,')
    lines.append('    "y_spread": 3,')
    lines.append('    "feature": {')
    lines.append('      "feature": {')
    lines.append('        "type": "voxel_sandbox:simple_block",')
    lines.append('        "config": {"to_place": {"type": "voxel_sandbox:simple_state_provider", "state": {"Name": "eternal-war:dark_leaves"}}}')
    lines.append('      },')
    lines.append('      "placement": [{"type": "voxel_sandbox:block_predicate_filter", "predicate": {"type": "voxel_sandbox:matching_blocks", "blocks": "voxel_sandbox:grass_block"}}]')
    lines.append('    }')
    lines.append('  }')
    lines.append('}')
    lines.append('```')
    lines.append("")
    lines.append("**placed_feature/<id>.json** schema:")
    lines.append("```json")
    lines.append('{')
    lines.append('  "feature": "eternal-war:dark_leaves_cluster",')
    lines.append('  "placement": [')
    lines.append('    {"type": "voxel_sandbox:count", "count": 2},')
    lines.append('    {"type": "voxel_sandbox:in_square"},')
    lines.append('    {"type": "voxel_sandbox:height_range", "height": {"type": "voxel_sandbox:uniform", "min_inclusive": {"absolute": 60}, "max_inclusive": {"absolute": 90}}},')
    lines.append('    {"type": "voxel_sandbox:biome"}')
    lines.append('  ]')
    lines.append('}')
    lines.append('```')
    lines.append("")
    lines.append("**Fabric biome_modifier** (注入 placed_feature 到指定 biome):")
    lines.append("由 fabric-biome-api-v1 的 BiomeModifications API 在 Java 注册 (无独立 datapack JSON 标准 — 这是 Fabric 扩展). 看 fabric_api/module_index.md 找 BiomeModifications.")
    lines.append("")
    lines.append("## Usage")
    lines.append("")
    lines.append("- 简单 worldgen 任务 (例 dark_leaves 平原簇生成) **可全 datapack JSON 实现**, 不一定需 Java")
    lines.append("- 复杂 worldgen (新 biome / structure / noise) 需 Java bootstrap + datapack JSON")
    lines.append("- LLM 看上方 hot classes 真签名挑实现路径")

    out = pathlib.Path("/workspace/omnicompany/data/domains/voxel_engine/references/yarn_worldgen/class_index.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(lines)} lines)")


if __name__ == "__main__":
    main()
