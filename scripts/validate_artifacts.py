"""跑 gameplay_system_ux 中间产物 schema 验证.

用法:
    python validate_artifacts.py --all
    python validate_artifacts.py --type template_meta
    python validate_artifacts.py --type template_meta --id T-btn-main

依赖 jsonschema 4.x + PyYAML.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml  # type: ignore
import jsonschema  # type: ignore
from jsonschema import Draft202012Validator  # type: ignore

DATA_ROOT = Path("/workspace/omnicompany/data/domains/gameplay_system_ux")
SCHEMAS_DIR = DATA_ROOT / "schemas"
STEP_INTER = DATA_ROOT / "scratch" / "step_intermediates"
FIGMA_PULLS = DATA_ROOT / "scratch" / "figma_pulls"
TEMPLATES_DIR = DATA_ROOT / "standards" / "templates"
TREE_DIR = DATA_ROOT / "tree"


def _load_yaml(p: Path) -> Any:
    return yaml.safe_load(p.read_text("utf-8", errors="replace"))


def _load_json(p: Path) -> Any:
    return json.loads(p.read_text("utf-8", errors="replace"))


def load_schema(name: str) -> dict:
    p = SCHEMAS_DIR / f"{name}.schema.yaml"
    return _load_yaml(p)


# ── artifact 收集 ─────────────────────────────────────

def collect_templates(yaml_name: str) -> list[tuple[str, Path, Any]]:
    """返 [(template_id, yaml_path, data)]"""
    out = []
    for tdir in sorted(TEMPLATES_DIR.glob("T-*")):
        p = tdir / yaml_name
        if not p.exists():
            continue
        try:
            data = _load_yaml(p)
        except Exception as e:
            data = {"_load_error": str(e)}
        out.append((tdir.name, p, data))
    return out


def collect_step1_skeleton() -> list[tuple[str, Path, Any]]:
    out = []
    for mod, fname in [
        ("artcontest", "artcontest_skeleton_v3.json"),
        ("iceblock",   "iceblock_skeleton_v3.json"),
        ("fightpit",   "fightpit_skeleton_v2.json"),
        ("midautumnhs","midautumnhs_skeleton_v2.json"),
    ]:
        p = STEP_INTER / fname
        if p.exists():
            out.append((mod, p, _load_json(p)))
    return out


def collect_step2_components() -> list[tuple[str, Path, Any]]:
    out = []
    for mod in ("artcontest", "iceblock", "fightpit", "midautumnhs"):
        p = STEP_INTER / f"{mod}_components_batch_v3.json"
        if p.exists():
            out.append((mod, p, _load_json(p)))
    return out


def collect_single_json(name: str, fname: str) -> list[tuple[str, Path, Any]]:
    p = STEP_INTER / fname
    if not p.exists():
        return []
    return [(name, p, _load_json(p))]


def collect_figma_trees() -> list[tuple[str, Path, Any]]:
    out = []
    for p in sorted(FIGMA_PULLS.glob("*.json")):
        try:
            out.append((p.stem, p, _load_json(p)))
        except Exception as e:
            out.append((p.stem, p, {"_load_error": str(e)}))
    return out


def collect_rule_tree() -> list[tuple[str, Path, Any]]:
    out = []
    for fp in sorted(TREE_DIR.rglob("*.yaml")):
        try:
            out.append((fp.relative_to(TREE_DIR).as_posix(), fp, _load_yaml(fp)))
        except Exception as e:
            out.append((fp.name, fp, {"_load_error": str(e)}))
    return out


# ── design_intent 软规范 ─────────────────────────────

DESIGN_INTENT_REQUIRED_SECTIONS = [
    "主要 UI 区域", "按钮交互行为", "状态变化跟特效", "流程顺序", "Tips",
]
DESIGN_INTENT_REQUIRED_FRONTMATTER = ["module", "file_key", "frame_id", "filled_by", "data_version"]


def validate_design_intent(p: Path) -> tuple[bool, list[str]]:
    errors = []
    text = p.read_text("utf-8", errors="replace")
    # frontmatter
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return False, ["缺 YAML frontmatter (--- ... ---)"]
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception as e:
        return False, [f"frontmatter YAML 解析失败: {e}"]
    for key in DESIGN_INTENT_REQUIRED_FRONTMATTER:
        if key not in fm:
            errors.append(f"frontmatter 缺 {key}")
    # H2 sections
    body = text[m.end():]
    found_sections = re.findall(r"^##\s+(.+?)\s*$", body, re.MULTILINE)
    found_text = " ".join(found_sections)
    for sec in DESIGN_INTENT_REQUIRED_SECTIONS:
        if sec not in found_text:
            errors.append(f"缺必填 section '## {sec}'")
    return len(errors) == 0, errors


# ── 主流程 ────────────────────────────────────────────

ARTIFACT_TYPES = {
    "template_meta":      ("template_meta",     lambda: collect_templates("meta.yaml")),
    "template_understand":("template_understand", lambda: collect_templates("understand.yaml")),
    "template_match":     ("template_match",    lambda: collect_templates("match.yaml")),
    "template_construct": ("template_construct",lambda: collect_templates("construct.yaml")),
    "step1_skeleton":     ("step1_skeleton",    collect_step1_skeleton),
    "step2_components":   ("step2_components",  collect_step2_components),
    "step10_coverage":    ("step10_coverage",   lambda: collect_single_json("step10_coverage", "step10_coverage_report_llm_v3.json")),
    "step11_appearance":  ("step11_appearance", lambda: collect_single_json("step11_appearance", "step11_appearance.json")),
    "step12_summary":     ("step12_summary",    lambda: collect_single_json("step12_summary", "step12_generation_summary.json")),
    "figma_tree":         ("figma_tree",        collect_figma_trees),
    "rule_tree":          ("rule_tree",         collect_rule_tree),
}


def _fmt_err(e: jsonschema.ValidationError) -> str:
    path = ".".join(str(x) for x in e.absolute_path)
    return f"  · {path or '<root>'}: {e.message}"


def validate_type(t: str, id_filter: str | None = None) -> dict:
    schema_name, collector = ARTIFACT_TYPES[t]
    schema = load_schema(schema_name)
    validator = Draft202012Validator(schema)
    samples = collector()
    if id_filter:
        samples = [(s, p, d) for s, p, d in samples if id_filter in s]
    results = {"type": t, "total": len(samples), "pass": 0, "fail": 0, "errors_by_id": {}}
    for sid, p, data in samples:
        if isinstance(data, dict) and "_load_error" in data:
            results["fail"] += 1
            results["errors_by_id"][sid] = [f"  · 加载失败: {data['_load_error']}"]
            continue
        errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
        if errs:
            results["fail"] += 1
            results["errors_by_id"][sid] = [_fmt_err(e) for e in errs[:5]]
        else:
            results["pass"] += 1
    return results


def validate_design_intent_all() -> dict:
    results = {"type": "design_intent", "total": 0, "pass": 0, "fail": 0, "errors_by_id": {}}
    for p in sorted(STEP_INTER.glob("design_intent_*.md")):
        results["total"] += 1
        ok, errors = validate_design_intent(p)
        if ok:
            results["pass"] += 1
        else:
            results["fail"] += 1
            results["errors_by_id"][p.stem] = [f"  · {e}" for e in errors]
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--type", choices=list(ARTIFACT_TYPES.keys()) + ["design_intent", "all"], default="all")
    ap.add_argument("--id", help="按 id 子串过滤 (例 T-btn-main)")
    ap.add_argument("--verbose", action="store_true", help="打印所有 fail 详情")
    args = ap.parse_args()

    types = list(ARTIFACT_TYPES.keys()) + ["design_intent"] if args.type == "all" else [args.type]
    overall = {"pass_total": 0, "fail_total": 0, "by_type": {}}

    for t in types:
        print(f"\n=== {t} ===")
        try:
            if t == "design_intent":
                r = validate_design_intent_all()
            else:
                r = validate_type(t, args.id)
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
            continue
        print(f"  total={r['total']}  PASS={r['pass']}  FAIL={r['fail']}")
        if r["fail"] > 0:
            for sid, errs in list(r["errors_by_id"].items())[:10 if not args.verbose else 999]:
                print(f"  ✗ {sid}:")
                for line in errs:
                    print(line)
            if r["fail"] > 10 and not args.verbose:
                print(f"  ... 还有 {r['fail'] - 10} 个 fail (用 --verbose 看全)")
        overall["pass_total"] += r["pass"]
        overall["fail_total"] += r["fail"]
        overall["by_type"][t] = {"pass": r["pass"], "fail": r["fail"], "total": r["total"]}

    print("\n" + "=" * 60)
    print(f"汇总: PASS={overall['pass_total']}  FAIL={overall['fail_total']}")
    print()
    for t, s in overall["by_type"].items():
        pct = 100 * s["pass"] / s["total"] if s["total"] else 0
        print(f"  {t:25s}  {s['pass']:4d}/{s['total']:4d}  PASS率 {pct:5.1f}%")


if __name__ == "__main__":
    main()
