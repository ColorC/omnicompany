"""反推中间产物 schema · 用 omnicompany 现有数据语料.

用法:
    python derive_schema_from_corpus.py --type <artifact_type>
    python derive_schema_from_corpus.py --all

artifact_type:
    template_meta / template_understand / template_match / template_construct
    figma_tree / step1_skeleton / step2_components / step10_coverage
    step11_appearance / step12_summary / rule_tree / design_intent

输出:
    1. 字段路径统计 (count / non-null-rate / value 类型分布 / sample 值)
    2. 旧版残留清单 (相同目录里非当前版本的同名文件)
    3. JSON Schema 草稿 (按字段频率推 required vs optional)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None  # rule_tree / template 走纯文本 fallback

# ── 数据根 ──────────────────────────────────────────────
DATA_ROOT = Path("/workspace/omnicompany/data/domains/gameplay_system_ux")
STEP_INTER = DATA_ROOT / "scratch" / "step_intermediates"
FIGMA_PULLS = DATA_ROOT / "scratch" / "figma_pulls"
TEMPLATES_DIR = DATA_ROOT / "standards" / "templates"
TREE_DIR = DATA_ROOT / "tree"

# 当前流水线实际使用的版本 (从 pipeline/step12_yaml_generator.py + paths.py 反推)
CURRENT_VERSIONS = {
    "step10": "step10_coverage_report_llm_v3.json",
    "step11": "step11_appearance.json",
    "step12_summary": "step12_generation_summary.json",
    # step1 skeleton: artcontest/iceblock 走 v3, fightpit/midautumnhs 写死 v2
    "step1_skeleton": {
        "artcontest": "artcontest_skeleton_v3.json",
        "iceblock":   "iceblock_skeleton_v3.json",
        "fightpit":   "fightpit_skeleton_v2.json",
        "midautumnhs": "midautumnhs_skeleton_v2.json",
    },
    "step2_components": {
        m: f"{m}_components_batch_v3.json"
        for m in ("artcontest", "iceblock", "fightpit", "midautumnhs")
    },
}


def _load_json(p: Path) -> Any:
    try:
        return json.loads(p.read_text("utf-8", errors="replace"))
    except Exception as e:
        return {"_load_error": str(e), "_path": str(p)}


def _load_yaml(p: Path) -> Any:
    if yaml is None:
        return {"_load_error": "PyYAML 未安装", "_path": str(p)}
    try:
        return yaml.safe_load(p.read_text("utf-8", errors="replace"))
    except Exception as e:
        return {"_load_error": str(e), "_path": str(p)}


# ── 字段扫描 ────────────────────────────────────────────

class FieldStats:
    """记录每条 field path 的统计."""
    def __init__(self) -> None:
        self.parent_count: Counter[str] = Counter()  # 此 parent path 出现了几次
        self.field_count: Counter[str] = Counter()   # full path 出现了几次
        self.non_null_count: Counter[str] = Counter()
        self.types: dict[str, Counter[str]] = defaultdict(Counter)
        self.samples: dict[str, list[str]] = defaultdict(list)

    def visit(self, obj: Any, parent_path: str = "") -> None:
        if isinstance(obj, dict):
            self.parent_count[parent_path or "<root>"] += 1
            for k, v in obj.items():
                full = f"{parent_path}.{k}" if parent_path else k
                self.field_count[full] += 1
                if v not in (None, "", [], {}):
                    self.non_null_count[full] += 1
                self.types[full][type(v).__name__] += 1
                if len(self.samples[full]) < 3:
                    self.samples[full].append(_short_repr(v))
                if isinstance(v, dict):
                    self.visit(v, full)
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            self.visit(item, full + "[]")
                        else:
                            self.types[full + "[]"][type(item).__name__] += 1

    def report(self) -> list[dict]:
        out = []
        for full, count in sorted(self.field_count.items()):
            parent = full.rsplit(".", 1)[0] if "." in full else "<root>"
            parent_n = self.parent_count.get(parent, count)
            rate = count / parent_n if parent_n else 0
            non_null_rate = self.non_null_count[full] / count if count else 0
            out.append({
                "path": full,
                "count": count,
                "parent_count": parent_n,
                "occurrence_rate": round(rate, 3),
                "non_null_rate": round(non_null_rate, 3),
                "types": dict(self.types[full]),
                "samples": self.samples[full],
            })
        return out


def _short_repr(v: Any) -> str:
    if isinstance(v, str):
        s = v.replace("\n", "\\n")
        return repr(s[:60] + ("…" if len(s) > 60 else ""))
    if isinstance(v, (int, float, bool)):
        return repr(v)
    if isinstance(v, list):
        return f"list[{len(v)}]"
    if isinstance(v, dict):
        return f"dict[{len(v)} keys]"
    if v is None:
        return "None"
    return type(v).__name__


# ── 反推 JSON Schema 草稿 ───────────────────────────────

def derive_schema(stats: FieldStats, title: str, required_threshold: float = 0.95) -> dict:
    """从字段统计推 JSON Schema 草稿.

    - 出现率 ≥ 95% 的字段进 required
    - 类型多 (>1) 的字段标 anyOf
    - 嵌套对象递归处理 (简化版只到顶 2 层)
    """
    fields = stats.report()
    # 找 root fields (无 '.' 的)
    root_fields = [f for f in fields if "." not in f["path"]]
    properties: dict = {}
    required: list[str] = []
    for f in root_fields:
        name = f["path"]
        types = list(f["types"].keys())
        ts = _types_to_jsonschema(types)
        properties[name] = ts
        if f["non_null_rate"] >= required_threshold:
            required.append(name)
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": title,
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
        "$comment": f"反推自 {len(root_fields)} 个 root 字段, required = 非空率 ≥ {required_threshold * 100:.0f}%",
    }


def _types_to_jsonschema(types: list[str]) -> dict:
    """Python type name → JSON Schema 'type'."""
    mapping = {
        "str": "string", "int": "integer", "float": "number",
        "bool": "boolean", "list": "array", "dict": "object", "NoneType": "null",
    }
    js_types = [mapping.get(t, t) for t in types if t in mapping]
    if not js_types:
        return {}
    if len(js_types) == 1:
        return {"type": js_types[0]}
    return {"type": js_types}


# ── 数据源收集 ──────────────────────────────────────────

def collect_template_yamls(yaml_name: str) -> list[tuple[str, Any]]:
    """扫 28 个 T-* 目录下指定 yaml. 返 [(template_id, obj)]."""
    out = []
    for tdir in sorted(TEMPLATES_DIR.glob("T-*")):
        p = tdir / yaml_name
        if not p.exists():
            continue
        out.append((tdir.name, _load_yaml(p)))
    return out


def collect_figma_trees() -> list[tuple[str, Any]]:
    return [(p.stem, _load_json(p)) for p in sorted(FIGMA_PULLS.glob("*.json")) if p.suffix == ".json"]


def collect_step1_skeleton() -> tuple[list[tuple[str, Any]], list[str]]:
    """当前用版本 (artcontest/iceblock v3, fightpit/midautumnhs v2)."""
    out = []
    legacy = []
    for mod, fname in CURRENT_VERSIONS["step1_skeleton"].items():
        p = STEP_INTER / fname
        if p.exists():
            out.append((mod, _load_json(p)))
    # 旧版残留: 找同 prefix 不同版本的文件
    for fp in STEP_INTER.glob("*_skeleton_*.json"):
        if fp.name not in CURRENT_VERSIONS["step1_skeleton"].values():
            legacy.append(fp.name)
    return out, legacy


def collect_step2_components() -> tuple[list[tuple[str, Any]], list[str]]:
    out = []
    legacy = []
    for mod, fname in CURRENT_VERSIONS["step2_components"].items():
        p = STEP_INTER / fname
        if p.exists():
            out.append((mod, _load_json(p)))
    for fp in STEP_INTER.glob("*_components_batch_*.json"):
        if fp.name not in CURRENT_VERSIONS["step2_components"].values():
            legacy.append(fp.name)
    return out, legacy


def collect_step10_coverage() -> tuple[list[tuple[str, Any]], list[str]]:
    fname = CURRENT_VERSIONS["step10"]
    p = STEP_INTER / fname
    out = [(p.stem, _load_json(p))] if p.exists() else []
    legacy = [fp.name for fp in STEP_INTER.glob("step10_coverage_report*.json") if fp.name != fname]
    return out, legacy


def collect_step11_appearance() -> tuple[list[tuple[str, Any]], list[str]]:
    p = STEP_INTER / CURRENT_VERSIONS["step11"]
    return ([(p.stem, _load_json(p))] if p.exists() else [], [])


def collect_step12_summary() -> tuple[list[tuple[str, Any]], list[str]]:
    p = STEP_INTER / CURRENT_VERSIONS["step12_summary"]
    return ([(p.stem, _load_json(p))] if p.exists() else [], [])


def collect_rule_tree() -> list[tuple[str, Any]]:
    out = []
    for fp in sorted(TREE_DIR.rglob("*.yaml")):
        rel = fp.relative_to(TREE_DIR)
        out.append((str(rel).replace("\\", "/"), _load_yaml(fp)))
    return out


# ── 主流程 ──────────────────────────────────────────────

ARTIFACT_TYPES = [
    "template_meta", "template_understand", "template_match", "template_construct",
    "figma_tree", "step1_skeleton", "step2_components",
    "step10_coverage", "step11_appearance", "step12_summary",
    "rule_tree",
]


def derive_for_type(t: str) -> dict:
    legacy: list[str] = []
    samples: list[tuple[str, Any]] = []
    if t.startswith("template_"):
        yaml_name = t.replace("template_", "") + ".yaml"
        samples = collect_template_yamls(yaml_name)
    elif t == "figma_tree":
        samples = collect_figma_trees()
    elif t == "step1_skeleton":
        samples, legacy = collect_step1_skeleton()
    elif t == "step2_components":
        samples, legacy = collect_step2_components()
    elif t == "step10_coverage":
        samples, legacy = collect_step10_coverage()
    elif t == "step11_appearance":
        samples, legacy = collect_step11_appearance()
    elif t == "step12_summary":
        samples, legacy = collect_step12_summary()
    elif t == "rule_tree":
        samples = collect_rule_tree()

    stats = FieldStats()
    for sid, obj in samples:
        if not isinstance(obj, dict):
            continue
        stats.visit(obj)

    return {
        "artifact_type": t,
        "sample_count": len(samples),
        "sample_ids": [sid for sid, _ in samples][:5],
        "legacy_files": legacy,
        "field_stats": stats.report(),
        "schema_draft": derive_schema(stats, title=t),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=ARTIFACT_TYPES + ["all"], default="all")
    ap.add_argument("--output-dir", default=str(DATA_ROOT / "schemas" / "_derived"))
    ap.add_argument("--print-summary", action="store_true", default=True)
    args = ap.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    types = ARTIFACT_TYPES if args.type == "all" else [args.type]
    overall = {}
    for t in types:
        print(f"\n=== {t} ===")
        try:
            result = derive_for_type(t)
        except Exception as e:
            print(f"  ERROR: {e}")
            continue
        overall[t] = result
        path_full = out_dir / f"{t}__derived.json"
        path_full.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  samples={result['sample_count']}  fields={len(result['field_stats'])}")
        print(f"  legacy={len(result['legacy_files'])}: {result['legacy_files'][:3]}")
        print(f"  → 写 {path_full}")
        if args.print_summary:
            print(f"  字段 top 20 (按出现率):")
            top = sorted(result["field_stats"], key=lambda f: -f["occurrence_rate"])[:20]
            for f in top:
                print(f"    {f['occurrence_rate']*100:5.1f}%  {f['path']:60s}  types={f['types']}")

    # 汇总
    summary = {
        t: {
            "sample_count": r["sample_count"],
            "field_count": len(r["field_stats"]),
            "legacy_count": len(r["legacy_files"]),
        }
        for t, r in overall.items()
    }
    (out_dir / "_overall_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n汇总: {out_dir / '_overall_summary.json'}")


if __name__ == "__main__":
    main()
