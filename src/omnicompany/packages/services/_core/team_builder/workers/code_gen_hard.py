# [OMNI] origin=claude-code domain=services/team_builder/workers ts=2026-04-24T00:00:00Z type=worker
# [OMNI] material_id="material:core.team_builder.hard_template_generators.six_file.py"
"""CodeGenerator 子 team · 6 个 HARD 模板 Worker (2026-04-24 · 分形重构).

feedback_100pct_required_goes_to_skeleton 的应用:
  formats.py / team.py / run.py / __init__.py / workers/__init__.py / workspace.yaml
  是 100% 必产文件 · 骨架 HARD 模板化产出, 不让 LLM 决定产不产也不让 LLM 主观拼结构.

Worker 对应关系:
  Wh1 FormatsFileGenerator   → formats.py
  Wh2 TeamFileGenerator      → team.py
  Wh3 RunFileGenerator       → run.py
  Wh4 PackageInitGenerator   → __init__.py
  Wh5 WorkersInitGenerator   → workers/__init__.py
  Wh6 WorkspaceYamlGenerator → .omni/workspace.yaml

所有 Worker:
  - 继承 omnicompany.Worker
  - 不调 LLM (HARD)
  - 产 {rel_path, content} 结构扁平 payload (R-23)
  - 每份 .py 产物首行含 OmniMark 头

下游 CodeAggregator (Wa9) 合并 8 路 fan-in 到 code_package.files dict.
"""
from __future__ import annotations

import datetime as _dt
import re
from typing import Any, ClassVar

import yaml

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind


_TODAY = _dt.date.today().isoformat()  # "YYYY-MM-DD"


def _omni_header(team_name: str, file_domain: str, file_type: str = "worker") -> str:
    """OmniMark 头 · 固定格式."""
    return (
        f"# [OMNI] origin=team_builder domain=services/{team_name}/{file_domain} "
        f"ts={_TODAY}T00:00:00Z type={file_type}"
    )


def _slugify_py_ident(name: str) -> str:
    """把 worker_id 或类似字符串规范化为合法 Python 标识符."""
    s = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip())
    if not s:
        s = "unnamed"
    if s[0].isdigit():
        s = "_" + s
    return s


def _class_name_for(worker_id: str) -> str:
    """worker_id → ClassName (snake_case → PascalCaseWorker · 也容忍已是 PascalCase)."""
    s = (worker_id or "").strip()
    # 若已 PascalCase (含大写首字母 + 后续有大写字符), 保留; 否则 snake → Pascal
    if re.match(r"^[A-Z][a-zA-Z0-9]*$", s) and any(c.isupper() for c in s[1:]):
        pascal = s
    else:
        parts = re.split(r"[_\-\s]+", s)
        parts = [p for p in parts if p]
        if not parts:
            return "UnnamedWorker"
        pascal = "".join(p[:1].upper() + p[1:] for p in parts)
    if not pascal.endswith("Worker"):
        pascal += "Worker"
    return pascal


def _module_name_for(worker_id: str) -> str:
    """worker_id → Python 模块文件名 (snake_case, 去 _worker 后缀).

    `CsvReaderWorker` → `csv_reader`
    `csv_reader_worker` → `csv_reader`
    `csv_reader` → `csv_reader`

    Ws7 sub-agent + WorkersInitGenerator + RunFileGenerator 必须用同一转换,
    否则 import 路径不对 (LLM 常用 PascalCase 存文件 `CsvReaderWorker.py`,
    而我们 import `.csvreaderworker` → case-sensitive NotFound).
    """
    s = (worker_id or "").strip()
    if not s:
        return "unnamed"
    # PascalCase → snake_case (CsvReader → csv_reader)
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()
    # Slugify 非法字符
    s = re.sub(r"[^a-z0-9_]", "_", s)
    # 合并 + 去首尾 _
    while "__" in s:
        s = s.replace("__", "_")
    s = s.strip("_")
    # 去后缀 _worker (若有) 保持模块名简洁
    if s.endswith("_worker"):
        s = s[:-7]
    return s or "unnamed"


def _extract_team_name(input_data: dict) -> str:
    """从 team_design / workspace_spec 抽 team_name (多路兜底)."""
    td = input_data.get("_from_team_architect") if isinstance(input_data, dict) else None
    ws = input_data.get("_from_workspace_designer") if isinstance(input_data, dict) else None
    for candidate in (td, ws, input_data):
        if isinstance(candidate, dict):
            name = candidate.get("team_name") or candidate.get("name")
            if isinstance(name, str) and name.strip():
                return re.sub(r"[^a-z0-9_]", "_", name.lower().strip().replace("-", "_"))
    return "unnamed_team"


def _extract_target_package_path(input_data: dict, team_name: str) -> str:
    """从 workspace_spec 抽 target_package_path · 没有则按 team_name 构造."""
    ws = input_data.get("_from_workspace_designer") if isinstance(input_data, dict) else None
    for cand in (ws, input_data):
        if isinstance(cand, dict):
            tp = cand.get("target_package_path") or cand.get("generated_package_path")
            if isinstance(tp, str) and tp.strip():
                return tp.rstrip("/") + "/"
    return f"src/omnicompany/packages/services/{team_name}/"


def _extract_worker_details(input_data: dict) -> list[dict]:
    """从 _from_worker_designer 抽 details list (容错多种 key 结构)."""
    if not isinstance(input_data, dict):
        return []
    wd = input_data.get("_from_worker_designer") or {}
    if isinstance(wd, dict):
        ds = wd.get("details")
        if isinstance(ds, list):
            return [d for d in ds if isinstance(d, dict)]
        if wd.get("worker_id"):  # 单条形式
            return [wd]
    if isinstance(wd, list):
        return [d for d in wd if isinstance(d, dict)]
    return []


def _extract_material_details(input_data: dict) -> list[dict]:
    """从 _from_material_designer 抽 details list."""
    if not isinstance(input_data, dict):
        return []
    md = input_data.get("_from_material_designer") or {}
    if isinstance(md, dict):
        ds = md.get("details")
        if isinstance(ds, list):
            return [d for d in ds if isinstance(d, dict)]
        if md.get("material_id"):
            return [md]
    if isinstance(md, list):
        return [d for d in md if isinstance(d, dict)]
    return []


# ═══════════════════════════════════════════════════════════════════════
# Wh1 · FormatsFileGenerator → formats.py
# ═══════════════════════════════════════════════════════════════════════


class FormatsFileGenerator(Worker):
    """HARD · 依 material_design_detailed list 渲染 formats.py."""

    DESCRIPTION: ClassVar[str] = (
        "CodeGen-Wh1 · HARD 模板 · 依 material_design_detailed 每条渲染 Material(...) 实例 + "
        "register_formats 函数. 不调 LLM · 纯参数化产文件内容."
    )
    FORMAT_IN: ClassVar = [
        "team_builder.material.team_design",
        "team_builder.material.material_design_detailed",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "team_builder.material.formats_py"

    def run(self, input_data: Any) -> Verdict:
        if not isinstance(input_data, dict):
            return Verdict(kind=VerdictKind.FAIL, output={}, diagnosis="input_data must be dict")
        team_name = _extract_team_name(input_data)
        materials = _extract_material_details(input_data)

        header = _omni_header(team_name, "formats", "config")
        lines: list[str] = [
            header,
            f'"""{team_name} Team · Material 定义 (团队 builder 自动产出).',
            "",
            "Material description 五要素: 内容语义 / 字段含义 / 上游承诺 / 下游用途 / 最小样例.",
            '"""',
            "from __future__ import annotations",
            "",
            "from omnicompany.packages.services._core.omnicompany import Material",
            "from omnicompany.protocol.format import FormatRegistry",
            "",
        ]

        var_names: list[str] = []
        for idx, m in enumerate(materials):
            mid = m.get("material_id") or f"{team_name}.material.m{idx}"
            var = "M_" + _slugify_py_ident(mid.replace(".", "_")).upper()
            var_names.append(var)
            parent = m.get("parent") or "doc"
            desc5 = m.get("description_5elems") or {}
            if isinstance(desc5, dict):
                desc_text = " ".join(
                    str(desc5.get(k, "")).strip()
                    for k in ("content_semantic", "field_meaning", "upstream_promise", "downstream_use", "minimal_sample")
                    if desc5.get(k)
                )
            else:
                desc_text = str(desc5)
            if not desc_text.strip():
                desc_text = f"Material {mid} · (LLM 未填详细描述, 骨架占位)"
            desc_text = desc_text.replace('"""', '"').strip()

            json_schema = m.get("json_schema") or {"type": "object"}
            # 骨架铁律: JSON 字面 (false/true/null) 不是合法 Python · 必须 repr() 转 Python (False/True/None)
            # 反例 (2026-04-24 csv_to_md 实测): json.dumps({'default': False}) → '{"default": false}' → import NameError
            # repr(dict) → "{'default': False}" 合法 Python
            schema_py_repr = repr(json_schema) if isinstance(json_schema, dict) else "{'type': 'object'}"
            lifecycle = m.get("lifecycle", "internal")
            tags_list = [team_name, "generated", f"kind.{lifecycle}"]

            lines.append(f"{var} = Material(")
            lines.append(f"    id={mid!r},")
            lines.append(f"    name={mid!r},")
            # 用 repr() 安全转义换行 / 引号 / 非 ASCII (骨架反例: LLM 产多行 description 破 string literal)
            lines.append(f"    description={desc_text[:800]!r},")
            lines.append(f"    parent={parent!r},")
            lines.append(f"    json_schema={schema_py_repr},")
            lines.append(f"    tags={tags_list!r},")
            lines.append(")")
            lines.append("")

        lines.append(f"ALL_MATERIALS = [{', '.join(var_names) if var_names else ''}]")
        lines.append("")
        lines.append("def register_formats(registry: FormatRegistry) -> None:")
        lines.append(f'    """注册 {team_name} 所有 Material 到 registry."""')
        lines.append("    for mat in ALL_MATERIALS:")
        lines.append("        if not registry.is_registered(mat.id):")
        lines.append("            try:")
        lines.append("                registry.register(mat)")
        lines.append("            except Exception:")
        lines.append("                pass")
        lines.append("")

        content = "\n".join(lines)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rel_path": "formats.py", "content": content, "team_name": team_name, "target_package_path": f"src/omnicompany/packages/services/{team_name}/"},
            diagnosis=f"formats.py · {len(materials)} material · {len(content)} bytes",
        )


# ═══════════════════════════════════════════════════════════════════════
# Wh2 · TeamFileGenerator → team.py
# ═══════════════════════════════════════════════════════════════════════


class TeamFileGenerator(Worker):
    """HARD · 依 team_design + worker_design_detailed 渲染 team.py (TeamSpec + nodes + edges)."""

    DESCRIPTION: ClassVar[str] = (
        "CodeGen-Wh2 · HARD 模板 · 依 team_design 的 workers_skeleton / entry + worker_design_detailed "
        "的 routes 渲染 build_team() 返回 TeamSpec. 不调 LLM."
    )
    FORMAT_IN: ClassVar = [
        "team_builder.material.team_design",
        "team_builder.material.worker_design_detailed",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "team_builder.material.team_py"

    def run(self, input_data: Any) -> Verdict:
        if not isinstance(input_data, dict):
            return Verdict(kind=VerdictKind.FAIL, output={}, diagnosis="input_data must be dict")
        team_name = _extract_team_name(input_data)
        td = input_data.get("_from_team_architect") or {}
        if not isinstance(td, dict):
            td = {}
        details = _extract_worker_details(input_data)
        details_by_id = {d.get("worker_id"): d for d in details if d.get("worker_id")}

        workers_skeleton = td.get("workers_skeleton") or []
        if not isinstance(workers_skeleton, list):
            workers_skeleton = []
        purpose = str(td.get("purpose") or f"{team_name} team")
        entry = td.get("entry")
        if not entry and workers_skeleton:
            entry = (workers_skeleton[0] or {}).get("worker_name") or (workers_skeleton[0] or {}).get("worker_id")
        if not entry and details:
            entry = details[0].get("worker_id")
        entry = entry or "unknown_entry"

        header = _omni_header(team_name, "team", "team")
        lines: list[str] = [
            header,
            f'"""{team_name} Team · 拓扑声明 (team_builder 自动产出)."""',
            "from __future__ import annotations",
            "",
            "from omnicompany.protocol.anchor import (",
            "    AnchorSpec, Route, RouteAction, ValidatorKind, ValidatorSpec, VerdictKind,",
            ")",
            "from omnicompany.protocol.team import (",
            "    NodeKind, NodeMaturity, TeamEdge, TeamNode, TeamSpec,",
            ")",
            "",
            "",
            "def _anchor(node_id, fmt_in, fmt_out, *, vkind, desc, routes, maturity=NodeMaturity.GROWING):",
            "    return TeamNode(",
            "        id=node_id,",
            "        kind=NodeKind.ANCHOR,",
            "        maturity=maturity,",
            "        anchor=AnchorSpec(",
            "            id=f'a_{node_id}',",
            "            name=node_id,",
            "            format_in=fmt_in,",
            "            format_out=fmt_out,",
            "            validator=ValidatorSpec(id=f'v_{node_id}', kind=vkind, description=desc),",
            "            routes=routes,",
            "        ),",
            "    )",
            "",
            "",
            "def build_team() -> TeamSpec:",
            f'    """构建 {team_name} Team."""',
            "    nodes = []",
        ]

        # 渲染每个 worker 节点 (优先 detailed · 否则用 skeleton)
        seen_ids: set[str] = set()
        # 先遍历 skeleton 保持顺序 · 再补 details 里有但 skeleton 没的
        worker_order: list[str] = []
        for ws in workers_skeleton:
            if not isinstance(ws, dict):
                continue
            wid = ws.get("worker_name") or ws.get("worker_id")
            if wid and wid not in seen_ids:
                seen_ids.add(wid)
                worker_order.append(wid)
        for d in details:
            wid = d.get("worker_id")
            if wid and wid not in seen_ids:
                seen_ids.add(wid)
                worker_order.append(wid)

        for wid in worker_order:
            d = details_by_id.get(wid, {})
            impl_type = (d.get("impl_type") or "SOFT").upper()
            vkind = {"HARD": "HARD", "SOFT": "SOFT", "AGENT": "SOFT"}.get(impl_type, "SOFT")
            fmt_in = d.get("format_in")
            fmt_out = d.get("format_out")
            if isinstance(fmt_in, list):
                fmt_in_repr = "[" + ", ".join(repr(x) for x in fmt_in) + "]"
            else:
                fmt_in_repr = repr(fmt_in or "unknown_material")
            fmt_out_repr = repr(fmt_out or "unknown_material")
            # desc: rule_spec (HARD) 或 prompt_template.system (SOFT/AGENT)
            # 用 repr() 安全转义换行 / 引号 / 非 ASCII (骨架反例: LLM 产多行 rule_spec 破 string literal)
            pt = d.get("prompt_template") or {}
            raw_desc = pt.get("system", "") if impl_type != "HARD" else d.get("rule_spec", "")
            desc = str(raw_desc or f"{wid} ({impl_type})")[:300]

            lines.append('    nodes.append(_anchor(')
            lines.append(f'        {wid!r}, {fmt_in_repr}, {fmt_out_repr},')
            lines.append(f"        vkind=ValidatorKind.{vkind},")
            lines.append(f"        desc={desc!r},")
            lines.append("        routes={")
            lines.append("            VerdictKind.PASS: Route(action=RouteAction.NEXT),")
            lines.append("            VerdictKind.FAIL: Route(action=RouteAction.RETRY, max_retries=1),")
            lines.append("        },")
            lines.append("    ))")

        # 渲染 edges · 依 worker_design_detailed 的 routes
        lines.append("    edges = []")
        for wid in worker_order:
            d = details_by_id.get(wid, {})
            routes = d.get("routes") or {}
            if not isinstance(routes, dict):
                continue
            for branch, rt in routes.items():
                if not isinstance(rt, dict):
                    continue
                target = rt.get("target")
                if target and target in seen_ids and target != wid:
                    vk = {"PASS": "PASS", "FAIL": "FAIL", "PARTIAL": "PARTIAL"}.get(branch, "PASS")
                    lines.append(f'    edges.append(TeamEdge(source="{wid}", target="{target}", condition=VerdictKind.{vk}))')

        lines.append('    return TeamSpec(')
        lines.append(f"        id={team_name!r},")
        lines.append(f"        name={team_name!r},")
        lines.append(f"        description={purpose[:300]!r},")
        lines.append(f"        entry={entry!r},")
        lines.append("        nodes=nodes,")
        lines.append("        edges=edges,")
        lines.append(f"        tags=[{team_name!r}, 'generated'],")
        lines.append("    )")
        lines.append("")

        content = "\n".join(lines)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rel_path": "team.py", "content": content, "team_name": team_name, "target_package_path": f"src/omnicompany/packages/services/{team_name}/"},
            diagnosis=f"team.py · {len(worker_order)} nodes · {len(content)} bytes",
        )


# ═══════════════════════════════════════════════════════════════════════
# Wh3 · RunFileGenerator → run.py
# ═══════════════════════════════════════════════════════════════════════


class RunFileGenerator(Worker):
    """HARD · 依 worker_design_detailed list 渲染 run.py (build_bindings)."""

    DESCRIPTION: ClassVar[str] = (
        "CodeGen-Wh3 · HARD 模板 · 依 worker_design_detailed 映射 worker_id → ClassName() 实例. "
        "不调 LLM."
    )
    FORMAT_IN: ClassVar = [
        "team_builder.material.team_design",
        "team_builder.material.worker_design_detailed",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "team_builder.material.run_py"

    def run(self, input_data: Any) -> Verdict:
        if not isinstance(input_data, dict):
            return Verdict(kind=VerdictKind.FAIL, output={}, diagnosis="input_data must be dict")
        team_name = _extract_team_name(input_data)
        details = _extract_worker_details(input_data)

        header = _omni_header(team_name, "run", "config")
        lines: list[str] = [
            header,
            f'"""{team_name} Team · build_bindings (team_builder 自动产出)."""',
            "from __future__ import annotations",
            "",
            "from omnicompany.packages.services._core.omnicompany import Worker",
            "from omnicompany.protocol.format import create_builtin_registry",
            "",
            "from .formats import register_formats  # 相对 import · 支持 tmp smoke + 正式部署两场景",
            "",
        ]
        # per-worker import
        for d in details:
            wid = d.get("worker_id") or "unknown"
            cls = _class_name_for(wid)
            module = _module_name_for(wid)
            lines.append(f"from .workers.{module} import {cls}")
        lines.append("")
        lines.append("")
        lines.append("def build_bindings(input_dict: dict | None = None) -> dict[str, Worker]:")
        lines.append(f'    """构建 {team_name} 节点绑定."""')
        lines.append("    registry = create_builtin_registry()")
        lines.append("    register_formats(registry)")
        lines.append("    return {")
        for d in details:
            wid = d.get("worker_id") or "unknown"
            cls = _class_name_for(wid)
            lines.append(f'        "{wid}": {cls}(),')
        lines.append("    }")
        lines.append("")

        content = "\n".join(lines)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rel_path": "run.py", "content": content, "team_name": team_name, "target_package_path": f"src/omnicompany/packages/services/{team_name}/"},
            diagnosis=f"run.py · {len(details)} bindings · {len(content)} bytes",
        )


# ═══════════════════════════════════════════════════════════════════════
# Wh4 · PackageInitGenerator → __init__.py
# ═══════════════════════════════════════════════════════════════════════


class PackageInitGenerator(Worker):
    """HARD · 顶层 __init__.py 样板."""

    DESCRIPTION: ClassVar[str] = (
        "CodeGen-Wh4 · HARD 样板 · 产 team 顶层 __init__.py (docstring + re-export build_team / "
        "build_bindings). 不调 LLM."
    )
    FORMAT_IN: ClassVar[str] = "team_builder.material.team_design"
    FORMAT_OUT: ClassVar[str] = "team_builder.material.pkg_init_py"

    def run(self, input_data: Any) -> Verdict:
        team_name = _extract_team_name(input_data if isinstance(input_data, dict) else {"team_name": "unnamed"})
        td = input_data.get("_from_team_architect") if isinstance(input_data, dict) else {}
        if not isinstance(td, dict):
            td = {}
        # 规范化: 去换行 + 去三引号序列 · 限 200 字 (骨架反例: LLM 产多行 purpose 破 docstring)
        purpose_raw = str(td.get("purpose") or f"{team_name} team")
        purpose = purpose_raw.replace("\r", " ").replace("\n", " ").replace('"""', '"')[:200]

        header = _omni_header(team_name, "__init__", "config")
        content = "\n".join([
            header,
            f'"""{team_name} Team · {purpose}',
            "",
            "由 team_builder 自动产出的骨架.",
            '"""',
            "from __future__ import annotations",
            "",
            "from .team import build_team",
            "from .run import build_bindings",
            "",
            '__all__ = ["build_team", "build_bindings"]',
            "",
        ])
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rel_path": "__init__.py", "content": content, "team_name": team_name, "target_package_path": f"src/omnicompany/packages/services/{team_name}/"},
            diagnosis=f"__init__.py · {len(content)} bytes",
        )


# ═══════════════════════════════════════════════════════════════════════
# Wh5 · WorkersInitGenerator → workers/__init__.py
# ═══════════════════════════════════════════════════════════════════════


class WorkersInitGenerator(Worker):
    """HARD · workers/__init__.py · 导出所有 Worker."""

    DESCRIPTION: ClassVar[str] = (
        "CodeGen-Wh5 · HARD 模板 · 依 worker_design_detailed 产 per-worker import + ALL_WORKERS 清单 "
        "+ __all__. 不调 LLM."
    )
    FORMAT_IN: ClassVar = [
        "team_builder.material.team_design",
        "team_builder.material.worker_design_detailed",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "team_builder.material.workers_init_py"

    def run(self, input_data: Any) -> Verdict:
        team_name = _extract_team_name(input_data if isinstance(input_data, dict) else {})
        details = _extract_worker_details(input_data if isinstance(input_data, dict) else {})

        header = _omni_header(team_name, "workers/__init__", "config")
        lines: list[str] = [
            header,
            f'"""{team_name} Team · workers 子包导出."""',
            "from __future__ import annotations",
            "",
            "from omnicompany.packages.services._core.omnicompany import Worker",
            "",
        ]
        class_names: list[str] = []
        for d in details:
            wid = d.get("worker_id") or "unknown"
            cls = _class_name_for(wid)
            module = _module_name_for(wid)
            class_names.append(cls)
            lines.append(f"from .{module} import {cls}")
        lines.append("")
        lines.append(f"ALL_WORKERS: list[type[Worker]] = [{', '.join(class_names) if class_names else ''}]")
        lines.append("")
        all_exports = class_names + ["ALL_WORKERS"]
        lines.append("__all__ = [" + ", ".join(f'"{x}"' for x in all_exports) + "]")
        lines.append("")

        content = "\n".join(lines)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rel_path": "workers/__init__.py", "content": content, "team_name": team_name, "target_package_path": f"src/omnicompany/packages/services/{team_name}/"},
            diagnosis=f"workers/__init__.py · {len(class_names)} exports · {len(content)} bytes",
        )


# ═══════════════════════════════════════════════════════════════════════
# Wh6 · WorkspaceYamlGenerator → .omni/workspace.yaml
# ═══════════════════════════════════════════════════════════════════════


class WorkspaceYamlGenerator(Worker):
    """HARD · 依 workspace_spec 产 .omni/workspace.yaml 内容."""

    DESCRIPTION: ClassVar[str] = (
        "CodeGen-Wh6 · HARD · 依 workspace_spec material 做 yaml.safe_dump. 不调 LLM."
    )
    FORMAT_IN: ClassVar[str] = "team_builder.material.workspace_spec"
    FORMAT_OUT: ClassVar[str] = "team_builder.material.workspace_yaml"

    def run(self, input_data: Any) -> Verdict:
        if not isinstance(input_data, dict):
            return Verdict(kind=VerdictKind.FAIL, output={}, diagnosis="input_data must be dict")

        # 直接取 workspace_spec payload (平铺 or 嵌在 _from_workspace_designer)
        spec = input_data.get("_from_workspace_designer") or input_data
        if not isinstance(spec, dict):
            return Verdict(kind=VerdictKind.FAIL, output={}, diagnosis="workspace_spec not dict")

        team_name = _extract_team_name(input_data)

        # 只保留规范字段, 丢掉 _meta / _from_*
        canonical_keys = (
            "name", "write_prefixes", "read_prefixes", "bash_cwd_prefixes",
            "generated_package_path",
        )
        cleaned = {k: spec[k] for k in canonical_keys if k in spec}
        if not cleaned.get("name"):
            cleaned["name"] = team_name

        yaml_text = yaml.safe_dump(cleaned, allow_unicode=True, sort_keys=False)
        return Verdict(
            kind=VerdictKind.PASS,
            output={"rel_path": ".omni/workspace.yaml", "content": yaml_text, "team_name": team_name, "target_package_path": f"src/omnicompany/packages/services/{team_name}/"},
            diagnosis=f".omni/workspace.yaml · {len(yaml_text)} bytes",
        )
