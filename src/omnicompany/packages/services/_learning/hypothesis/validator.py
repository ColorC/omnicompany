# [OMNI] origin=claude-code domain=services/hypothesis ts=2026-04-17T00:00:00Z type=module status=active
# [OMNI] material_id="material:services.learning.hypothesis.validator.doc_checker.py"
"""hypothesis.validator — khyp 主题文档的格式校验器。

给 Reflector 的"安全门"：每次 Reflector 用 edit/write_file 改文档后，
调此校验器检查写入是否破坏了文档的结构合法性。

只做 schema 层校验，不做 append-only（见 plan "Not in Scope"）。
"""

from __future__ import annotations

import re
import json
from pathlib import Path
from typing import Any

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_OMNIMARK_LINE_RE = re.compile(r"^#\s*\[OMNI\][^\n]*\n+")

_VALID_MATURITIES = {"draft", "living", "stable", "deprecated"}
_VALID_KINDS = {"state", "transition", "policy", "invariant"}


def validate_hypothesis_doc(path: str | Path) -> dict:
    """校验一份 khyp 文档。

    返回:
        {
          "ok": bool,              # 无 error 时为 True
          "errors": [str, ...],    # 阻止性错误
          "warnings": [str, ...],  # 提醒但不阻止
          "stats": {
            "total_hypotheses": N,
            "by_maturity": {...},
            "deleted_count": N,
          }
        }
    """
    errors: list[str] = []
    warnings: list[str] = []
    stats: dict[str, Any] = {}

    p = Path(path)
    if not p.exists():
        errors.append(f"文件不存在: {path}")
        return _make_result(errors, warnings, stats)

    try:
        text = p.read_text(encoding="utf-8")
    except Exception as exc:
        errors.append(f"读文件失败: {exc}")
        return _make_result(errors, warnings, stats)

    # 剥 OmniMark 自动头
    stripped = _OMNIMARK_LINE_RE.sub("", text, count=1)
    m = _FRONTMATTER_RE.match(stripped)
    if not m:
        errors.append("找不到 YAML frontmatter（--- ... --- 块）")
        return _make_result(errors, warnings, stats)

    fm_raw = m.group(1)

    if not _HAS_YAML:
        errors.append("pyyaml 未安装，无法校验 frontmatter 结构")
        return _make_result(errors, warnings, stats)

    try:
        fm = yaml.safe_load(fm_raw) or {}
        if not isinstance(fm, dict):
            fm = None
    except yaml.YAMLError as exc:
        fm = None
        strict_exc = exc
    else:
        strict_exc = None

    if fm is None:
        # 2026-04-19 容错 B：严格 YAML 解析失败时降级为 per-hypothesis 恢复
        fm, recovery_info = _partial_recover_frontmatter(fm_raw)
        if fm is None:
            errors.append(
                f"YAML 解析完全失败，连降级恢复都不可行: {strict_exc}"
            )
            return _make_result(errors, warnings, stats)
        warnings.append(
            f"YAML 严格解析失败，已降级为部分恢复："
            f"成功 {recovery_info['recovered']} 条假设、跳过 {recovery_info['failed']} 条。"
            f"原因：{str(strict_exc)[:200] if strict_exc else 'frontmatter 不是字典'}"
        )
        if recovery_info.get("failed_reasons"):
            for idx, reason in recovery_info["failed_reasons"][:5]:
                warnings.append(f"  · 假设[{idx}] 跳过: {reason[:160]}")

    # 硬规则
    if fm.get("omnikb_type") != "khyp":
        errors.append(f"omnikb_type 必须是 'khyp'，当前是 {fm.get('omnikb_type')!r}")

    if not fm.get("id"):
        errors.append("id 为空或缺失")

    if not fm.get("name"):
        errors.append("name 为空或缺失")

    hyps = fm.get("hypotheses", [])
    if not isinstance(hyps, list):
        errors.append(f"hypotheses 必须是 list，当前是 {type(hyps).__name__}")
        hyps = []

    deleted = fm.get("deleted_hypotheses", [])
    if not isinstance(deleted, list):
        errors.append(f"deleted_hypotheses 必须是 list（可为空），当前是 {type(deleted).__name__}")
        deleted = []

    # 假设条目逐项检查
    seen_ids: set[str] = set()
    all_ids: set[str] = set()  # 含 deleted 的全集，供引用校验

    for i, h in enumerate(hyps):
        if not isinstance(h, dict):
            errors.append(f"hypotheses[{i}] 不是字典")
            continue

        hid = h.get("id", "")
        if not hid or not isinstance(hid, str):
            errors.append(f"hypotheses[{i}]: id 为空或非字符串")
            continue

        if hid in seen_ids:
            errors.append(f"hypotheses[{i}]: id '{hid}' 重复")
        seen_ids.add(hid)
        all_ids.add(hid)

        if not h.get("summary"):
            errors.append(f"hypotheses[{hid}]: summary 为空")

        mat = h.get("maturity", "")
        if mat not in _VALID_MATURITIES:
            errors.append(
                f"hypotheses[{hid}]: maturity '{mat}' 非法，必须是 {sorted(_VALID_MATURITIES)} 之一"
            )

        kind = h.get("kind", "")
        if kind not in _VALID_KINDS:
            errors.append(
                f"hypotheses[{hid}]: kind '{kind}' 非法，必须是 {sorted(_VALID_KINDS)} 之一"
            )

        # P-strict (2026-04-18): format_in / format_out 必须结构化填写，不能为 None。
        # 2026-04-18 晚补：支持 fan-in/fan-out — 允许 list[dict] 表达多入/多出场景。
        # 语义：format_in = "什么东西/状态" 的容器；format_out = "经过本 virtual router 后变成什么" 的容器。
        # 一个虚 Router 可消费多个 format（fan-in）或产出多个 format（fan-out）。
        for field_name in ("format_in", "format_out"):
            v = h.get(field_name)
            if v is None:
                errors.append(
                    f"hypotheses[{hid}]: {field_name} 未填写 "
                    f"（该字段描述虚 Router 的输入/输出契约，不可为 None；"
                    f"单入单出用 dict，多入/多出用 list[dict]）"
                )
            elif isinstance(v, dict):
                if not v:
                    errors.append(
                        f"hypotheses[{hid}]: {field_name} 不能为空 dict {{}}——"
                        f"必须至少含一个字段（如 summary）描述契约内容"
                    )
            elif isinstance(v, list):
                if not v:
                    errors.append(
                        f"hypotheses[{hid}]: {field_name} 不能为空 list []——"
                        f"fan-in/fan-out 至少含一项"
                    )
                else:
                    for i, item in enumerate(v):
                        if not isinstance(item, dict):
                            errors.append(
                                f"hypotheses[{hid}]: {field_name}[{i}] 必须是 dict，"
                                f"当前是 {type(item).__name__}"
                            )
                        elif not item:
                            errors.append(
                                f"hypotheses[{hid}]: {field_name}[{i}] 不能是空 dict {{}}"
                            )
            else:
                errors.append(
                    f"hypotheses[{hid}]: {field_name} 必须是 dict（单入/单出）或 list[dict]"
                    f"（fan-in/fan-out），当前是 {type(v).__name__}"
                )

        # 软规则：evidence / counterexamples 的结构
        for field_name in ("evidence", "counterexamples"):
            v = h.get(field_name, [])
            if v is None:
                continue
            if not isinstance(v, list):
                errors.append(f"hypotheses[{hid}]: {field_name} 必须是 list")
                continue
            for j, item in enumerate(v):
                if isinstance(item, dict):
                    if not any(item.get(k) for k in ("描述", "description", "desc")):
                        warnings.append(
                            f"hypotheses[{hid}]: {field_name}[{j}] 建议带 '描述' 字段"
                        )

        # state_log 结构
        slog = h.get("state_log", [])
        if slog is not None and not isinstance(slog, list):
            errors.append(f"hypotheses[{hid}]: state_log 必须是 list")

    # 归档的 deleted_hypotheses 也纳入 id 集合（供引用校验）
    for i, d in enumerate(deleted):
        if not isinstance(d, dict):
            warnings.append(f"deleted_hypotheses[{i}] 不是字典")
            continue
        did = d.get("id", "")
        if did:
            all_ids.add(did)
        if not d.get("理由") and not d.get("reason"):
            warnings.append(f"deleted_hypotheses[{did or i}] 建议带 '理由' 字段")

    # 2026-04-18 晚移除：depends_on / derived_from / contradicts 引用完整性检查。
    # L1 决定：三类关系是"二级产物"，现实关系远多于此三类，强塞 3 字段反而丢信息。
    # 关系改为：自然语言放在 summary / evidence；同 format_in/out 自然聚类出关系族。
    # 现有数据里若已有这些字段，validator 不再检查（静默容忍），但不强制 Reflector 产出。

    # 统计
    stats["total_hypotheses"] = len(hyps)
    stats["deleted_count"] = len(deleted)
    by_mat: dict[str, int] = {}
    for h in hyps:
        if isinstance(h, dict):
            m_val = h.get("maturity", "draft")
            by_mat[m_val] = by_mat.get(m_val, 0) + 1
    stats["by_maturity"] = by_mat

    return _make_result(errors, warnings, stats)


def _make_result(errors: list, warnings: list, stats: dict) -> dict:
    return {
        "ok": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": stats,
    }


# ════════════════════════════════════════════════════════════════════════════
# 容错降级恢复（2026-04-19）
# 背景：Reflector 写 inline dict 形如 `format_in: {summary: "xxx: yyy"}` 时，
# 内层未转义冒号让 YAML parser 整段报 "mapping values are not allowed here"，
# 导致整份文档校验崩，阻塞后续 edit。
# 容错策略：严格 parse 失败时，**单条假设独立 parse**——失败条目跳过只发 warning，
# 其他正确条目继续走正常检查。validator 不再一条 YAML 错就让整个跑失败。
# ════════════════════════════════════════════════════════════════════════════

_HYP_ITEM_START = re.compile(r"^(\s+)- id:\s*(\S.*)$", re.MULTILINE)


def _partial_recover_frontmatter(fm_raw: str) -> tuple[dict | None, dict]:
    """严格 yaml parse 失败时降级恢复。

    策略：
      1. 切 `hypotheses:` 前后段，前段是顶层字段，单独 parse
      2. `hypotheses:` 块按 `  - id: xxx` 分段，每段独立 parse
      3. `deleted_hypotheses:` 之后的段也单独 parse
      4. 失败的假设条目 → 记录 (index, reason) 给 warning
    """
    # 识别 hypotheses 段落位置
    hyp_header = re.search(r"^hypotheses:\s*$", fm_raw, re.MULTILINE)
    if hyp_header is None:
        # 没 hypotheses 块？试直接 parse（可能缺 key）
        try:
            fm = yaml.safe_load(fm_raw) or {}
            return (fm if isinstance(fm, dict) else None), {
                "recovered": 0, "failed": 0, "failed_reasons": [],
            }
        except yaml.YAMLError:
            return None, {}

    pre_text = fm_raw[: hyp_header.start()]
    post_start = hyp_header.end()
    # 找 hypotheses 块结束：下一个顶层键（^\w+:）或文本末尾
    post_text_full = fm_raw[post_start:]
    next_top_key = re.search(r"^\S+:", post_text_full, re.MULTILINE)
    if next_top_key:
        hyp_block = post_text_full[: next_top_key.start()]
        post_text = post_text_full[next_top_key.start() :]
    else:
        hyp_block = post_text_full
        post_text = ""

    # 1. 顶层字段
    top_level: dict[str, Any] = {}
    for chunk_label, chunk in [("pre", pre_text), ("post", post_text)]:
        if not chunk.strip():
            continue
        try:
            parsed = yaml.safe_load(chunk)
            if isinstance(parsed, dict):
                top_level.update(parsed)
        except yaml.YAMLError:
            pass  # 忽略顶层解析失败（Reflector 通常不改顶层）

    # 2. 逐条假设恢复
    recovered_items: list[dict] = []
    failed_reasons: list[tuple[int, str]] = []

    # 按 `  - id: xxx` 切块
    item_starts = list(_HYP_ITEM_START.finditer(hyp_block))
    items: list[str] = []
    for i, mstart in enumerate(item_starts):
        start = mstart.start()
        end = item_starts[i + 1].start() if i + 1 < len(item_starts) else len(hyp_block)
        items.append(hyp_block[start:end])

    for idx, item_text in enumerate(items):
        # 单条构造 minimal list 做 parse
        # 形如 "  - id: foo\n    summary: ..." 可直接 yaml.safe_load 得 list[dict]
        # 去掉首行额外缩进：把最小缩进归零
        lines = item_text.rstrip().split("\n")
        # 计算最小缩进（非空行）
        indents = [len(l) - len(l.lstrip()) for l in lines if l.strip()]
        base_indent = min(indents) if indents else 0
        normalized = "\n".join(l[base_indent:] if len(l) >= base_indent else l for l in lines)
        try:
            parsed = yaml.safe_load(normalized)
        except yaml.YAMLError as exc:
            failed_reasons.append((idx, str(exc)))
            continue
        if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
            recovered_items.append(parsed[0])
        elif isinstance(parsed, dict):
            recovered_items.append(parsed)
        else:
            failed_reasons.append((idx, f"解析结果类型异常: {type(parsed).__name__}"))

    top_level["hypotheses"] = recovered_items
    if not recovered_items and not top_level.get("id"):
        return None, {}

    return top_level, {
        "recovered": len(recovered_items),
        "failed": len(failed_reasons),
        "failed_reasons": failed_reasons,
    }


# ════════════════════════════════════════════════════════════════════════════
# 给 Reflector 暴露的 Tool
# ════════════════════════════════════════════════════════════════════════════

def make_validator_tool():
    """返回一个 SingleToolRouter，给 Reflector 自查用。"""
    from typing import ClassVar

    from omnicompany.packages.services._core.agent.routers.single_tool import SingleToolRouter
    from omnicompany.runtime.agent.agent_loop_tools import ToolContext

    class ValidateHypothesisDocRouter(SingleToolRouter):
        TOOL_NAME: ClassVar[str] = "validate_hypothesis_doc"
        DESCRIPTION: ClassVar[str] = (
            "Validate a khyp hypothesis document and return JSON with ok, errors, "
            "warnings, and stats. Use after edit/write_file changes."
        )
        INPUT_SCHEMA: ClassVar[dict] = {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the hypothesis document"},
            },
            "required": ["path"],
        }
        IS_CONCURRENCY_SAFE: ClassVar[bool] = True
        IS_READONLY: ClassVar[bool] = True

        def _execute(self, args: dict, ctx: ToolContext) -> str:
            result = validate_hypothesis_doc(args.get("path", ""))
            return json.dumps(result, ensure_ascii=False, indent=2)

    return ValidateHypothesisDocRouter

    def _handle(path: str) -> str:
        result = validate_hypothesis_doc(path)
        return json.dumps(result, ensure_ascii=False, indent=2)

    return _Tool(
        name="validate_hypothesis_doc",
        description=(
            "校验一份 khyp 主题假设文档的格式是否合法。"
            "参数: path（文件绝对路径）。"
            "返回 JSON: {ok, errors, warnings, stats}。"
            "建议每次用 edit/write_file 修改文档后立刻调此工具自查。"
            "errors 非空 → 文档有致命问题必须修；warnings → 软建议可选。"
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "假设文档的绝对路径"},
            },
            "required": ["path"],
        },
        is_concurrency_safe=True,
        is_readonly=True,
        handler=_handle,
    )
