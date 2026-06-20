# -*- coding: utf-8 -*-
"""一次性脚本: 从 yarn_entities_raw.json 浓缩 + 写 yarn_entities/class_index.md."""
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
                extends = m.group(1)
        elif (ln.startswith("public ") or ln.startswith("protected ")) and "(" in ln and ln.endswith(";"):
            sig = ln.rstrip(";")
            methods.append(sig)
    return extends, methods


def main() -> None:
    raw = json.loads(pathlib.Path("/tmp/yarn_entities_raw.json").read_text(encoding="utf-8"))
    condensed: dict = {}
    for cls, raw_text in raw.items():
        # 短名: net.voxel_sandbox.entity.passive.RabbitEntity → RabbitEntity
        short = cls.split(".")[-1]
        ext, ms = parse(raw_text)
        condensed[short] = {"full": cls, "extends": ext, "methods": ms}

    print(f"condensed entity classes: {len(condensed)}")

    lines: list[str] = []
    lines.append("<!-- [OMNI] origin=claude-code domain=data/domains/voxel_engine/references/yarn_entities ts=2026-04-26T16:30:00Z type=doc status=active -->")
    lines.append("")
    lines.append("# Yarn 1.21.1 Entity class index (net.voxel_sandbox.entity.*)")
    lines.append("")
    lines.append("> Source: javap -protected on each .class in net/voxel_sandbox/entity/.")
    lines.append("> Use: EntityEngineer LLM looks up which super to extend + overrideable method signatures.")
    lines.append("")
    lines.append(f"- Total classes: {len(condensed)}")
    lines.append("")
    lines.append("## Hot base classes (full method list)")
    lines.append("")

    hot = [
        # 抽象/中间类
        "Entity", "LivingEntity", "MobEntity", "PathAwareEntity",
        "AnimalEntity", "PassiveEntity", "TameableEntity",
        "HostileEntity",
        # 被动 (常作 super)
        "RabbitEntity", "ChickenEntity", "PigEntity", "CowEntity", "SheepEntity",
        "VillagerEntity", "AxolotlEntity", "FoxEntity", "WolfEntity",
        "BatEntity", "ParrotEntity",
        # 敌对 (常作 super)
        "ZombieEntity", "SkeletonEntity", "SpiderEntity",
        "IronGolemEntity",
    ]

    for cls in hot:
        if cls not in condensed:
            continue
        info = condensed[cls]
        lines.append(f"### `{info['full']}` (extends {info['extends']})")
        lines.append("")
        if info["methods"]:
            for m in info["methods"]:
                lines.append(f"- `{m}`")
        else:
            lines.append("- (no exposed methods, constructors only)")
        lines.append("")

    lines.append("## All classes (alphabetical)")
    lines.append("")
    lines.append("> Class name + full path + extends + method count.")
    lines.append("")
    lines.append("| Class | Full path | Extends | Methods |")
    lines.append("|---|---|---|---|")
    for cls in sorted(condensed.keys()):
        info = condensed[cls]
        lines.append(f"| `{cls}` | `{info['full']}` | `{info['extends'] or '-'}` | {len(info['methods'])} |")
    lines.append("")
    lines.append("## Common AI Goal classes (under net.voxel_sandbox.entity.ai.goal)")
    lines.append("")
    lines.append("> These are NOT in this index (separate package). Common ones to use in initGoals():")
    lines.append("> - FleeEntityGoal: flee from a target entity type")
    lines.append("> - EscapeDangerGoal: panic when hurt")
    lines.append("> - MeleeAttackGoal / ActiveTargetGoal: attack")
    lines.append("> - LookAtEntityGoal / LookAroundGoal: look behavior")
    lines.append("> - SwimGoal / WanderAroundGoal / WanderAroundFarGoal: movement")
    lines.append("> - TemptGoal: follow holder of specific item")
    lines.append("> Look up real signatures by inspecting net.voxel_sandbox.entity.ai.goal.* via javap if needed.")
    lines.append("")
    lines.append("## Usage")
    lines.append("")
    lines.append("- Before writing an Entity subclass, look up the target super class for overrideable methods.")
    lines.append("- Pick super class by **shape match** (form + locomotion), not by behavior.")
    lines.append("  - 'small jumping mammal' -> RabbitEntity")
    lines.append("  - 'standing humanoid NPC' -> VillagerEntity")
    lines.append("  - 'aquatic fish' -> AxolotlEntity")
    lines.append("- For non-default behavior (flee from player, etc), override initGoals() in subclass.")
    lines.append("- LLM picks super class. Designer does not specify.")

    out = pathlib.Path("/workspace/omnicompany/data/domains/voxel_engine/references/yarn_entities/class_index.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size} bytes, {len(lines)} lines)")


if __name__ == "__main__":
    main()
