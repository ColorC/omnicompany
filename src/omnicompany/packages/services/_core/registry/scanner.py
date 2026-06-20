# [OMNI] origin=claude-code domain=services/registry ts=2026-04-11T00:00:00Z
# [OMNI] material_id="material:core.registry.code_scanner.ast_discovery.py"
"""
Registry Scanner — 唯一注册方式源

"代码即注册"原则的执行者：Scanner 读取代码中的正典声明形式，
将其转换为 InstanceEntry 写入 InstanceRegistry。

不存在其他注册路径。Scanner 是唯一权威。

每种实体类型有对应的扫描函数，扫描范围和识别规则与 MetaTypeRegistry 中的
canonical_form 描述完全一致。

扫描结果保证：
  - 同一实体重复扫描 → 幂等（entity_id 不变，只更新 scanned_at）
  - 代码中删除实体 → 旧记录留存（需显式调用 prune_stale() 清除）
  - 私有类（_开头）跳过
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Iterator

from .instance import InstanceEntry, InstanceRegistry

log = logging.getLogger(__name__)

# ── 判定哪些路径应跳过 ──────────────────────────────────────────────────────

_SKIP_DIRS = {"__pycache__", "_graveyard", ".venv", "node_modules", "_archive"}


def _should_skip(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


# ── Package 推断：从文件路径推断 package 点分路径 ──────────────────────────

def _infer_package(py_file: Path, source_root: Path) -> str:
    """从文件路径推断逻辑 package 名称（相对于 source_root）。

    示例：
      source_root = src/omnicompany
      py_file = src/omnicompany/packages/domains/demogame/team_table/workers/schema_assembler.py
      → "demogame.team_table"

    过滤规则：
      - 去掉架构基础目录（packages/domains/services/protocol/runtime）
      - 去掉常见实现子目录（routers/flows/rules/hooks/tools/formatters 等）——
        这些目录是文件系统组织习惯，不代表逻辑包层级
    """
    # 架构基础目录：不含业务语义
    _INFRA = {"packages", "domains", "services", "protocol", "runtime", "core"}
    # 实现子目录：表示"该目录下存放 X 类型文件"，不是逻辑命名空间
    _IMPL_DIRS = {
        "routers", "flows", "rules", "hooks", "tools", "formatters",
        "formats", "schema", "schemas", "models", "handlers", "utils",
    }
    try:
        rel = py_file.relative_to(source_root)
        parts = list(rel.parts)[:-1]  # 去掉文件名
        parts = [p for p in parts if p not in _INFRA and p not in _IMPL_DIRS]
        return ".".join(parts) if parts else ""
    except ValueError:
        return ""


def _rel_to_root(py_file: Path, source_root: Path) -> str:
    """返回文件相对于 source_root.parent（omnicompany 根）的路径字符串。"""
    try:
        return str(py_file.relative_to(source_root.parent))
    except ValueError:
        return str(py_file)


# ── Format 扫描 ─────────────────────────────────────────────────────────────

def scan_formats(source_root: Path) -> Iterator[InstanceEntry]:
    """扫描 source_root 下所有 formats.py，提取 Format(id=..., ...) 实例。

    正典形式：formats.py 文件中的 Format(id='...', name='...', ...) 调用。
    """
    for py_file in source_root.rglob("formats.py"):
        if _should_skip(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            log.debug("scan_formats: cannot parse %s: %s", py_file, e)
            continue

        package = _infer_package(py_file, source_root)
        rel = _rel_to_root(py_file, source_root)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Format(...) 或 Format(id=...) 调用
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "Format"):
                continue

            # 提取 kwargs
            kwargs: dict[str, object] = {}
            for kw in node.keywords:
                if kw.arg is None:
                    continue
                try:
                    kwargs[kw.arg] = ast.literal_eval(kw.value)
                except Exception:
                    kwargs[kw.arg] = None

            fmt_id = kwargs.get("id")
            if not isinstance(fmt_id, str) or not fmt_id:
                continue

            entity_id = f"format:{fmt_id}"

            # 依赖：parent + components
            deps: list[str] = []
            if parent := kwargs.get("parent"):
                if isinstance(parent, str):
                    deps.append(f"format:{parent}")
            for comp in (kwargs.get("components") or []):
                if isinstance(comp, str):
                    deps.append(f"format:{comp}")

            yield InstanceEntry(
                entity_id=entity_id,
                type="format",
                name=fmt_id,
                package=package,
                source_file=rel,
                attrs={
                    "display_name": kwargs.get("name"),
                    "description": kwargs.get("description"),
                    "tags": kwargs.get("tags") or [],
                    "parent": kwargs.get("parent"),
                    "components": kwargs.get("components") or [],
                    "has_examples": bool(kwargs.get("examples")),
                    "has_json_schema": bool(kwargs.get("json_schema")),
                },
                deps=deps,
            )


# ── Router / AgentLoop 扫描 ─────────────────────────────────────────────────

_ROUTER_BASES = {"Router", "LLMRouter", "AgentNodeLoop"}
_AGENT_BASES = {"AgentNodeLoop"}


def scan_routers(source_root: Path) -> Iterator[InstanceEntry]:
    """扫描 source_root 下所有 .py 文件，提取继承自 Router/LLMRouter 的类。

    AgentNodeLoop 子类单独产出为 agent_loop 类型（不重复产出为 router）。
    私有类（_开头）跳过。
    """
    for py_file in source_root.rglob("*.py"):
        if _should_skip(py_file):
            continue
        if "test" in py_file.name.lower():
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            log.debug("scan_routers: cannot parse %s: %s", py_file, e)
            continue

        package = _infer_package(py_file, source_root)
        rel = _rel_to_root(py_file, source_root)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name.startswith("_"):
                continue  # 私有类跳过

            base_names = set()
            for base in node.bases:
                if isinstance(base, ast.Name):
                    base_names.add(base.id)
                elif isinstance(base, ast.Attribute):
                    base_names.add(base.attr)

            is_router = bool(base_names & _ROUTER_BASES)
            is_agent = bool(base_names & _AGENT_BASES)
            if not is_router:
                continue

            entity_type = "agent_loop" if is_agent else "router"

            # 提取类变量
            class_vars: dict[str, object] = {}
            class_var_kinds: dict[str, str] = {}
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for t in stmt.targets:
                    if not (isinstance(t, ast.Name) and t.id in (
                        "DESCRIPTION", "FORMAT_IN", "FORMAT_OUT", "INPUT_KEYS", "OUTPUT_KEYS",
                    )):
                        continue
                    if t.id in ("FORMAT_IN", "FORMAT_OUT"):
                        if isinstance(stmt.value, ast.JoinedStr):
                            class_vars[t.id] = None
                            class_var_kinds[t.id] = "fstring"
                        elif isinstance(stmt.value, ast.List):
                            try:
                                class_vars[t.id] = ast.literal_eval(stmt.value)
                            except Exception:
                                class_vars[t.id] = None
                            class_var_kinds[t.id] = "list"
                        else:
                            try:
                                class_vars[t.id] = ast.literal_eval(stmt.value)
                                class_var_kinds[t.id] = "literal"
                            except Exception:
                                class_vars[t.id] = None
                                class_var_kinds[t.id] = "dynamic"
                    else:
                        try:
                            class_vars[t.id] = ast.literal_eval(stmt.value)
                        except Exception:
                            class_vars[t.id] = None

            # 检查 run() 是否 async
            run_is_async = False
            for stmt in node.body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "run":
                    run_is_async = isinstance(stmt, ast.AsyncFunctionDef)
                    break

            fmt_in = class_vars.get("FORMAT_IN")
            fmt_out = class_vars.get("FORMAT_OUT")
            entity_id = f"{entity_type}:{package}.{node.name}" if package else f"{entity_type}:{node.name}"

            # 依赖：FORMAT_IN → format（仅 literal 字符串）
            deps: list[str] = []
            if isinstance(fmt_in, str):
                deps.append(f"format:{fmt_in}")
            if isinstance(fmt_out, str):
                deps.append(f"format:{fmt_out}")

            attrs: dict = {
                "description": class_vars.get("DESCRIPTION"),
                "format_in": fmt_in,
                "format_out": fmt_out,
                "format_in_kind": class_var_kinds.get("FORMAT_IN", "literal"),
                "format_out_kind": class_var_kinds.get("FORMAT_OUT", "literal"),
                "run_is_async": run_is_async,
            }
            if is_agent:
                # AgentLoop 额外属性（max_turns 等需从 __init__ 提取，此处先记录占位）
                attrs["base_class"] = list(base_names & _AGENT_BASES)[0]

            yield InstanceEntry(
                entity_id=entity_id,
                type=entity_type,
                name=node.name,
                package=package,
                source_file=rel,
                attrs=attrs,
                deps=deps,
            )


# ── Pipeline 扫描 ────────────────────────────────────────────────────────────

def scan_pipelines(source_root: Path) -> Iterator[InstanceEntry]:
    """扫描 *pipeline*.py 文件，提取 build_*_pipeline() 函数声明的 TeamSpec。

    正典形式：def build_{name}_pipeline() → TeamSpec(...)
    Pipeline 名称 = 函数名去掉 build_ 前缀和 _pipeline 后缀。
    """
    for py_file in source_root.rglob("*.py"):
        if _should_skip(py_file):
            continue
        # 只扫描 pipeline 相关文件
        if "pipeline" not in py_file.name.lower():
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(py_file))
        except Exception as e:
            log.debug("scan_pipelines: cannot parse %s: %s", py_file, e)
            continue

        package = _infer_package(py_file, source_root)
        rel = _rel_to_root(py_file, source_root)

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            fn = node.name
            # 识别 build_*_pipeline() 模式
            if not (fn.startswith("build_") and fn.endswith("_pipeline")):
                continue

            # Pipeline 名称 = 去掉 build_ 和 _pipeline
            pipeline_name = fn[len("build_"):-len("_pipeline")]

            # 尝试提取 TeamSpec(purpose=...) 的 purpose 字段
            purpose = ""
            for child in ast.walk(node):
                if not isinstance(child, ast.Call):
                    continue
                func = child.func
                is_pipeline_spec = (
                    (isinstance(func, ast.Name) and func.id == "TeamSpec")
                    or (isinstance(func, ast.Attribute) and func.attr == "TeamSpec")
                )
                if not is_pipeline_spec:
                    continue
                for kw in child.keywords:
                    if kw.arg == "purpose":
                        try:
                            purpose = ast.literal_eval(kw.value)
                        except Exception:
                            purpose = "(dynamic)"
                        break
                break

            entity_id = f"pipeline:{package}.{pipeline_name}" if package else f"pipeline:{pipeline_name}"

            yield InstanceEntry(
                entity_id=entity_id,
                type="pipeline",
                name=pipeline_name,
                package=package,
                source_file=rel,
                attrs={
                    "builder_fn": fn,
                    "purpose": purpose,
                },
                deps=[],
            )


# ── 主扫描入口 ───────────────────────────────────────────────────────────────

def scan_all(source_root: Path, registry: InstanceRegistry) -> dict[str, int]:
    """扫描 source_root，将所有发现的实体写入 registry。

    返回各类型的新写入/更新数量。
    """
    counts: dict[str, int] = {
        "format": 0, "router": 0, "agent_loop": 0, "pipeline": 0,
    }

    for entry in scan_formats(source_root):
        registry.write(entry)
        counts["format"] += 1

    seen_agent_ids: set[str] = set()
    for entry in scan_routers(source_root):
        registry.write(entry)
        if entry.type == "agent_loop":
            seen_agent_ids.add(entry.entity_id)
            counts["agent_loop"] += 1
        else:
            counts["router"] += 1

    for entry in scan_pipelines(source_root):
        registry.write(entry)
        counts["pipeline"] += 1

    log.info(
        "scan_all complete: format=%d router=%d agent_loop=%d pipeline=%d",
        counts["format"], counts["router"], counts["agent_loop"], counts["pipeline"],
    )
    return counts


def scan_file(py_file: Path, source_root: Path, registry: InstanceRegistry) -> list[str]:
    """重新扫描单个文件，更新其中包含的实体。返回更新的 entity_id 列表。

    用于增量诊断：git diff 识别到某文件变化后，只重扫该文件。
    """
    updated: list[str] = []
    py_file = Path(py_file)

    if py_file.name == "formats.py":
        for entry in scan_formats(py_file.parent):
            registry.write(entry)
            updated.append(entry.entity_id)
    elif "pipeline" in py_file.name.lower():
        # 扫描单个 pipeline 文件
        for entry in _scan_pipelines_file(py_file, source_root):
            registry.write(entry)
            updated.append(entry.entity_id)
    else:
        # 扫描单个 Router 文件
        for entry in _scan_routers_file(py_file, source_root):
            registry.write(entry)
            updated.append(entry.entity_id)

    return updated


def _scan_routers_file(py_file: Path, source_root: Path) -> Iterator[InstanceEntry]:
    """扫描单个文件的 Router 类（scan_routers 的单文件版）。

    直接解析指定文件而非扫描整个目录，保证 entity_id / source_file 准确。
    """
    try:
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content, filename=str(py_file))
    except Exception as e:
        log.debug("_scan_routers_file: cannot parse %s: %s", py_file, e)
        return
    package = _infer_package(py_file, source_root)
    rel = _rel_to_root(py_file, source_root)

    if _should_skip(py_file) or "test" in py_file.name.lower():
        return

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name.startswith("_"):
            continue

        base_names = set()
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_names.add(base.id)
            elif isinstance(base, ast.Attribute):
                base_names.add(base.attr)

        is_router = bool(base_names & _ROUTER_BASES)
        is_agent = bool(base_names & _AGENT_BASES)
        if not is_router:
            continue

        entity_type = "agent_loop" if is_agent else "router"

        class_vars: dict[str, object] = {}
        class_var_kinds: dict[str, str] = {}
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            for t in stmt.targets:
                if not (isinstance(t, ast.Name) and t.id in (
                    "DESCRIPTION", "FORMAT_IN", "FORMAT_OUT", "INPUT_KEYS", "OUTPUT_KEYS",
                )):
                    continue
                if t.id in ("FORMAT_IN", "FORMAT_OUT"):
                    if isinstance(stmt.value, ast.JoinedStr):
                        class_vars[t.id] = None
                        class_var_kinds[t.id] = "fstring"
                    elif isinstance(stmt.value, ast.List):
                        try:
                            class_vars[t.id] = ast.literal_eval(stmt.value)
                        except Exception:
                            class_vars[t.id] = None
                        class_var_kinds[t.id] = "list"
                    else:
                        try:
                            class_vars[t.id] = ast.literal_eval(stmt.value)
                            class_var_kinds[t.id] = "literal"
                        except Exception:
                            class_vars[t.id] = None
                            class_var_kinds[t.id] = "dynamic"
                else:
                    try:
                        class_vars[t.id] = ast.literal_eval(stmt.value)
                    except Exception:
                        class_vars[t.id] = None

        run_is_async = False
        for stmt in node.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == "run":
                run_is_async = isinstance(stmt, ast.AsyncFunctionDef)
                break

        fmt_in = class_vars.get("FORMAT_IN")
        fmt_out = class_vars.get("FORMAT_OUT")
        entity_id = f"{entity_type}:{package}.{node.name}" if package else f"{entity_type}:{node.name}"

        deps: list[str] = []
        if isinstance(fmt_in, str):
            deps.append(f"format:{fmt_in}")
        if isinstance(fmt_out, str):
            deps.append(f"format:{fmt_out}")

        attrs: dict = {
            "description": class_vars.get("DESCRIPTION"),
            "format_in": fmt_in,
            "format_out": fmt_out,
            "format_in_kind": class_var_kinds.get("FORMAT_IN", "literal"),
            "format_out_kind": class_var_kinds.get("FORMAT_OUT", "literal"),
            "run_is_async": run_is_async,
        }
        if is_agent:
            attrs["base_class"] = list(base_names & _AGENT_BASES)[0]

        yield InstanceEntry(
            entity_id=entity_id,
            type=entity_type,
            name=node.name,
            package=package,
            source_file=rel,
            attrs=attrs,
            deps=deps,
        )


def _scan_pipelines_file(py_file: Path, source_root: Path) -> Iterator[InstanceEntry]:
    """扫描单个 pipeline 文件。"""
    try:
        content = py_file.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
    except Exception:
        return
    package = _infer_package(py_file, source_root)
    rel = _rel_to_root(py_file, source_root)
    for entry in _iter_pipeline_entries(tree, package, rel):
        yield entry


def _iter_pipeline_entries(tree: ast.Module, package: str, rel: str) -> Iterator[InstanceEntry]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        fn = node.name
        if not (fn.startswith("build_") and fn.endswith("_pipeline")):
            continue
        pipeline_name = fn[len("build_"):-len("_pipeline")]
        purpose = ""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                is_ps = (isinstance(func, ast.Name) and func.id == "TeamSpec") or \
                        (isinstance(func, ast.Attribute) and func.attr == "TeamSpec")
                if is_ps:
                    for kw in child.keywords:
                        if kw.arg == "purpose":
                            try:
                                purpose = ast.literal_eval(kw.value)
                            except Exception:
                                purpose = "(dynamic)"
                    break
        entity_id = f"pipeline:{package}.{pipeline_name}" if package else f"pipeline:{pipeline_name}"
        yield InstanceEntry(
            entity_id=entity_id, type="pipeline", name=pipeline_name,
            package=package, source_file=rel,
            attrs={"builder_fn": fn, "purpose": purpose}, deps=[],
        )
