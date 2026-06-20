# [OMNI] origin=claude-code domain=services/team_builder/scripts ts=2026-04-25T00:00:00Z type=tool
# [OMNI] material_id="material:core.team_builder.sequential_worker_builder.agent_orchestrator.py"
"""sequential_worker_builder · 逐工人编排器 · 体系化动态引用 (非拷贝).

哲学 (用户 2026-04-25 直接指示, 二轮迭代):
- workspace 不知道给啥就全给 · 但**动态引用**而非拷贝
- LLM 用 read_file/grep/list_dir 工具自取 SKILL.md / docs/standards/ / 已运行 team 范本
- 给资料地图 (引用清单) · LLM 自己按需读
- 一次写一个工人 · 静态过关后才写下一个
- SOFT/AGENT 工人代码必须真调 LLM (强约束 · 否则 LLM 会偷懒写规则代码冒充)

变化 (vs v1):
- v1: 单次 LLMClient.call · system prompt 拷贝资料 · LLM 没体系认知
- v2: AgentNodeLoop · 给 5 工具 · 资料地图 (路径) · LLM 自己探索

实现: 复用 omnicompany 已有 AgentNodeLoop + ReadFileRouter/GlobRouter/GrepRouter/ListDirRouter/FinishRouter.

用法:
    python -m omnicompany.packages.services._core.team_builder.scripts.sequential_worker_builder \\
        --snapshot data/domains/team_builder/snapshots/<run_id> \\
        --worktree data/_workspaces/team_builder/seq_<run_id>
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import inspect
import json
import re
import sys
from pathlib import Path
from typing import ClassVar

# ──────────────────────────────────────────────────────────────────────────
# §1 · 工人代码生成 Agent (用 omnicompany AgentNodeLoop · 5 工具)
# ──────────────────────────────────────────────────────────────────────────


_RESOURCE_MAP = """
## 资料地图 (你写代码前应当查的文档 · 用 read_file / grep / list_dir 取 · 不要凭印象)

omnicompany 是分布式 AI-native 软件工厂. 你正在为它写一个 Worker (= Router 的 omnicompany 层别名).

### 必读 · 项目体系认知
- `.claude/skills/omnicompany-dev/SKILL.md` (1839 行 · omnicompany 完整开发规范)
  - §第二步 Material 体系 (字段五要素 / kind 必填)
  - §第三步 Worker 设计 (19 项节点单表 / 输入形态 / 信息源清单)
  - §第五步 Worker 实现 (各 impl_type 代码模板 · §5.1.1 单入 · §5.1.2 多入 · §5.1.3 子 job)
  - §第八步 Case Study (P3.B 历史教训 + 7 条铁律 — **必看**)

### 标准库 (按需读)
- `docs/standards/worker.md` — Worker 20 条标准 + 4 原则 + 11 反模式
- `docs/standards/material.md` — Material F-01~F-19 + 反模式
- `docs/standards/team.md` — Team 拓扑健康度 + P-01~P-13
- `docs/standards/llm_first.md` — LLM 第一原则 + **铁律 A 禁预防性截断 / B 预算宽松**
- `docs/standards/agent_first.md` — agent-first 方法论
- `docs/standards/format.md` — Format/Material 命名 + 类型规范

### 已运行 team 范本 (按 impl_type 找参考 · 用 read_file 看完整源码 · 用 grep 找类似工人)

> **首选** guardian / doctor 的工人作范本 — 它们正在生产环境跑且代码质量好.

**HARD 工人范本** (确定性 Python · 不调 LLM · 用规则/AST):
- `src/omnicompany/packages/services/guardian/workers/rule_engine_worker.py` (102 行 · 规则引擎 + 调用 14 条规则函数)
- `src/omnicompany/packages/services/guardian/workers/fs_scanner_worker.py` (214 行 · 文件系统扫描)
- `src/omnicompany/packages/services/doctor/workers/blackboard/material_kind_legality.py` (105 行 · Material kind 静态检查)
- `src/omnicompany/packages/services/doctor/workers/blackboard/orphan_worker_scanner.py` (84 行 · 订阅图静态分析)

**SOFT 工人范本** (单次 LLM 调用 · 用 LLMClient):
- `src/omnicompany/packages/services/guardian/workers/patrol_worker.py` (254 行 · **真用 LLMClient + JSON 解析** · 看 `from omnicompany.runtime.llm.llm import LLMClient` + `client.call()` 用法)

**AGENT 工人范本** (多轮 LLM + 工具 · 继承 AgentNodeLoop):
- `src/omnicompany/packages/services/team_builder/workers/design_validator.py` (~310 行 · **2026-04-25 已重构**) — 5 工具 = ReadFile/Glob/Grep/ListDir/**SubmitDesignReportRouter** (自定义 · 结构化 schema · 替代 FinishRouter+json.loads · **正例**) · 直接读 `block["input"]["field"]` 不解 JSON

### 框架真源码 (用 read_file 看 · 不要凭印象)
- `src/omnicompany/packages/services/omnicompany/__init__.py` — Worker / Material / Team alias
- `src/omnicompany/packages/services/agent/loop.py` — AgentNodeLoop 基类
- `src/omnicompany/runtime/llm/llm.py` — LLMClient.__init__ + .call() 真签名
- `src/omnicompany/protocol/anchor.py` — Verdict / VerdictKind / Route

### 写工人前 3 步建议 (省时)
1. **看你的 impl_type** (HARD / SOFT / AGENT) → 决定要不要调 LLM:
   - HARD = 不调 LLM · 纯 Python 规则
   - SOFT = 单次 LLM (用 LLMClient)
   - AGENT = 多轮 LLM + 工具 (继承 AgentNodeLoop)
2. **grep 找模板**: `grep "class.*Worker" src/omnicompany/packages/services/<某 team>/workers/*.py`
3. **read_file 看完整范本** + 你的 worker_design

## 强约束 (违反 = 静态校验直接 FAIL)

1. **F-15 声明即消费**: 代码读 `input_data["k"]` 的每个 k 必须在 FORMAT_IN material 的 json_schema 内
2. **FORMAT_OUT 完整**: `Verdict(output={...})` dict 必含 FORMAT_OUT material schema 的全部 required 字段 (字段名逐字)
3. **平铺**: `Verdict.output = {...}` 顶层扁平 · 不要 `{"<format_id>": ...}` 嵌套
4. **跨平台**: 禁 Unix-only shell (`find` / `wc` / `grep` / `awk` / `sed` 字面量) · 用 `Path.rglob` / `Path.read_text` / `Path.stat` (Windows 上 `find` = `FIND.EXE` 不兼容)
5. **input_data 平铺读**: TeamRunner `_merge_inputs` 行为 = 上游 Verdict.output 平铺 merge 到顶层 · 用 `input_data["files"]` 不要 `input_data["<team>.<material>"]`
6. **SOFT/AGENT 必须真调 LLM**: 若 impl_type=SOFT 必须 `from omnicompany.runtime.llm.llm import LLMClient` + `client.call(...)` · 若 impl_type=AGENT 必须 `from omnicompany.packages.services._core.agent.loop import AgentNodeLoop` + 继承. **禁用 AST/regex 模拟 LLM 行为冒充 SOFT/AGENT 工人**
7. **错误处理**: 失败 `return Verdict(kind=VerdictKind.FAIL, diagnosis=...)` 不抛异常
8. **AGENT 工人内部 LLM 输出 = 结构化 schema 不手解** (2026-04-25 L1 铁律): 写 AGENT 工人时:
   - **禁** `from ...single_tool import FinishRouter` + `_parse_json_loose(result)`
   - **必** 自定义 `SubmitXxxRouter(SingleToolRouter)` 子类 + 各字段 INPUT_SCHEMA · ExtractResult 直接读 `block["input"]["field"]`
   - 正例参考: `design_validator.py::SubmitDesignReportRouter` (2026-04-25 重构后) + 本工具自己 (`SubmitWorkerCodeRouter`)
   - 详见 SKILL.md §第十步

## 任务

为指定工人 (id 在用户消息) 写**完整 Python 代码**.

写完调 **`submit_worker_code`** 工具提交 (结构化 schema):
- `code`: 完整 .py 源码 · **纯 Python · 不要 markdown fence (```python```) · 不要前后散文**
- `impl_type`: HARD / SOFT / AGENT (必须匹配设计稿)
- `imports_summary`: 关键 import 列表 (校验用)

> 注: 用 `submit_worker_code` 不是旧的 `finish` 工具. submit_worker_code 强 JSON schema · 直接结构化交付 · 解析方按字段读 · 不做正则 / markdown 提取.

不要现在就写 — 先用 read_file / grep / list_dir 取需要的资料 (尤其 SKILL.md 关键节 + 同 impl_type 范本) · 看完再写.
"""


def _build_worker_specific_context(worker_id: str, ws: dict, written: dict[str, str]) -> str:
    """工人级 context · 装到 user message · 比 system 短."""
    w = ws["workers"][worker_id]
    materials = ws["materials"]

    fmt_in = w.get("format_in")
    fmt_out = w.get("format_out")
    fmt_in_list = [fmt_in] if isinstance(fmt_in, str) else (fmt_in or [])

    in_block = []
    for mid in fmt_in_list:
        m = materials.get(mid, {})
        in_block.append(
            f"### {mid}\n"
            f"description (5 elems): {json.dumps(m.get('description_5elems', {}), ensure_ascii=False)}\n"
            f"schema:\n```json\n{json.dumps(m.get('json_schema', {}), ensure_ascii=False, indent=2)}\n```"
        )
    in_str = "\n\n".join(in_block) if in_block else "(none)"

    out_m = materials.get(fmt_out, {})
    out_block = (
        f"### {fmt_out}\n"
        f"schema:\n```json\n{json.dumps(out_m.get('json_schema', {}), ensure_ascii=False, indent=2)}\n```\n"
        f"required (Verdict.output 必含): {out_m.get('json_schema', {}).get('required') or []}"
    )

    upstream_block = (
        "(this is the first worker · no upstream code yet)"
        if not written
        else "\n\n".join(f"### {wid} (上游 · 看字段如何被产出)\n```python\n{code}\n```" for wid, code in written.items())
    )

    team = ws["team_design"]

    return f"""## 你正在为 omnicompany 写工人 · `{worker_id}`

## team 全景
team_name: {team.get('team_name')}
5 workers (拓扑序): {[w_['worker_name'] for w_ in team.get('workers_skeleton', [])]}
6 materials: {[m['material_id'] for m in team.get('materials_skeleton', [])]}

## 你这个工人 (worker_design_detailed 摘录)
- impl_type: **{w.get('impl_type')}** ← 这决定调不调 LLM (见强约束 #6)
- format_in: {fmt_in}
- format_out: {fmt_out}
- format_in_mode: {w.get('format_in_mode') or 'and (default · 多入)'}
- routes: {w.get('routes')}
- context_sources (设计期标的信息源): {w.get('context_sources')}
- hallucination_risks (设计期识别的风险): {w.get('hallucination_risks')}
- output_token_budget: {w.get('output_token_budget')}

## 你的输入 material 全 schema
{in_str}

## 你的输出 material 全 schema (Verdict.output 必含 required 字段 · 名逐字)
{out_block}

## 上游已写工人代码 (你的 input_data 顶层字段就是上游 Verdict.output 的字段 · 用 grep / read 看清楚)
{upstream_block}

---

按 system prompt 的"写工人前 3 步建议":
1. 现在你的 impl_type = **{w.get('impl_type')}** · 决定调 LLM 与否
2. 用 grep 找同 impl_type 的范本 (system prompt 资料地图列了 HARD/SOFT/AGENT 各自的范本路径)
3. 用 read_file 看完整范本 1-2 份 · 学清楚 import / class 结构 / 调用方式

写完调 `finish(result=代码)`. 不要绕过 · 不要写 markdown 解释.
"""


# ──────────────────────────────────────────────────────────────────────────
# §2 · workspace 装载 (复用 v1 的 4 份产物)
# ──────────────────────────────────────────────────────────────────────────


def load_workspace(snapshot_dir: Path) -> dict:
    return {
        "team_design": json.loads((snapshot_dir / "team_design.json").read_text(encoding="utf-8")),
        "materials": {
            m["material_id"]: m
            for m in json.loads((snapshot_dir / "material_design_detailed.json").read_text(encoding="utf-8"))["details"]
        },
        "workers": {
            w["worker_id"]: w
            for w in json.loads((snapshot_dir / "worker_design_detailed.json").read_text(encoding="utf-8"))["details"]
        },
        "contract_audit": json.loads((snapshot_dir / "contract_audit.json").read_text(encoding="utf-8")),
    }


def topo_order_workers(ws: dict) -> list[str]:
    workers = ws["workers"]
    deps = {wid: set() for wid in workers}
    for c in ws["contract_audit"].get("connections", []):
        if c.get("ok") and c.get("producer_worker") and c.get("consumer_worker"):
            deps[c["consumer_worker"]].add(c["producer_worker"])
    order = []
    remaining = dict(deps)
    while remaining:
        no_deps = sorted(w for w, d in remaining.items() if not d)
        if not no_deps:
            raise RuntimeError(f"topo cycle: {remaining}")
        order.extend(no_deps)
        for w in no_deps:
            del remaining[w]
        for w in remaining:
            remaining[w] -= set(no_deps)
    return order


# ──────────────────────────────────────────────────────────────────────────
# §3 · 静态校验 (强化 · SOFT/AGENT 必有 LLM)
# ──────────────────────────────────────────────────────────────────────────


def _to_snake(name: str) -> str:
    s = name.replace("Worker", "")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", s).lower()


def _pascal_to_class(name: str) -> str:
    return name if name.endswith("Worker") else (name + "Worker")


def static_check(code: str, worker_id: str, ws: dict) -> tuple[bool, list[str]]:
    issues = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, [f"syntax error: {e}"]

    cls_name = _pascal_to_class(worker_id)
    if not any(isinstance(n, ast.ClassDef) and n.name == cls_name for n in ast.walk(tree)):
        issues.append(f"未找到 class {cls_name}")

    w = ws["workers"][worker_id]
    fmt_in = w.get("format_in")
    fmt_out = w.get("format_out")
    fmt_in_list = [fmt_in] if isinstance(fmt_in, str) else (fmt_in or [])
    impl_type = (w.get("impl_type") or "").upper()

    in_props = set()
    for fid in fmt_in_list:
        sch = (ws["materials"].get(fid) or {}).get("json_schema") or {}
        in_props.update((sch.get("properties") or {}).keys())

    out_required = set(((ws["materials"].get(fmt_out) or {}).get("json_schema") or {}).get("required") or [])

    # 收集 input keys + output keys + imports
    input_keys = set()
    var_map: dict[str, set] = {}
    out_keys = set()
    has_llmclient_import = False
    has_agentnodeloop_import = False
    has_llmclient_call = False

    for node in ast.walk(tree):
        # input keys
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                input_keys.add(node.args[0].value)
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            input_keys.add(node.slice.value)
        # output dict literals 跟踪变量
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Dict):
                for k in node.value.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        var_map.setdefault(tgt.id, set()).add(k.value)
            if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Name) and isinstance(tgt.slice, ast.Constant) and isinstance(tgt.slice.value, str):
                var_map.setdefault(tgt.value.id, set()).add(tgt.slice.value)
        # Verdict(output=...)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Verdict":
            for kw in node.keywords:
                if kw.arg == "output":
                    if isinstance(kw.value, ast.Dict):
                        for k in kw.value.keys:
                            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                out_keys.add(k.value)
                    elif isinstance(kw.value, ast.Name):
                        out_keys.update(var_map.get(kw.value.id, set()))
        # imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            mod = getattr(node, "module", "") or ""
            names = [a.name for a in node.names]
            if "llm" in mod and any("LLMClient" in n for n in names):
                has_llmclient_import = True
            if "agent.loop" in mod and any("AgentNodeLoop" in n for n in names):
                has_agentnodeloop_import = True
        # LLMClient.call() 调用
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr == "call":
                # 简易: 任何 .call() 都算 (减少误判)
                # 严格判要查 var instance, 这里宽松
                pass  # 用 import 判断更可靠
        if isinstance(node, ast.Name) and node.id == "LLMClient":
            has_llmclient_call = True

    # F-15 单向上闭 (代码读 ⊆ schema) — INFO 不阻塞
    missing_required_input = (set(((ws["materials"].get(fmt_in_list[0]) if fmt_in_list else {}) or {}).get("json_schema", {}).get("required", [])) - input_keys) if fmt_in_list else set()
    if missing_required_input:
        print(f"  [INFO] {worker_id} 未读 FORMAT_IN required {sorted(missing_required_input)} (可能合理 · 不阻塞)")

    # FORMAT_OUT required (硬 fail)
    # 若工人定义了 SubmitXxxRouter 且 INPUT_SCHEMA.required 含 FORMAT_OUT required
    # → 信任 API 层 schema · Verdict.output 必能含这些字段 (LLM 不能绕过 API schema)
    # 这避免对 `Verdict(output=dict(submit_input))` 类静态追踪不到的合法模式误报
    submit_router_required: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name.endswith("Router") and node.name.startswith("Submit"):
            for stmt in node.body:
                # INPUT_SCHEMA: ClassVar[dict] = {...}
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.target.id == "INPUT_SCHEMA":
                    if isinstance(stmt.value, ast.Dict):
                        for k, v in zip(stmt.value.keys, stmt.value.values):
                            if isinstance(k, ast.Constant) and k.value == "required" and isinstance(v, ast.List):
                                for elt in v.elts:
                                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                        submit_router_required.add(elt.value)
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name) and tgt.id == "INPUT_SCHEMA" and isinstance(stmt.value, ast.Dict):
                            for k, v in zip(stmt.value.keys, stmt.value.values):
                                if isinstance(k, ast.Constant) and k.value == "required" and isinstance(v, ast.List):
                                    for elt in v.elts:
                                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                            submit_router_required.add(elt.value)

    missing_out = out_required - out_keys - submit_router_required
    if missing_out:
        issues.append(f"Verdict.output 缺 FORMAT_OUT required: {sorted(missing_out)}")

    # 跨平台 (Unix-only shell) 硬 fail
    forbidden = []
    for ln_idx, line in enumerate(code.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("#", '"""', "'''")):
            continue
        for cmd in ("'find'", '"find"', "'wc'", '"wc"', "'grep'", '"grep"', "'awk'", '"awk"', "'sed'", '"sed"'):
            if cmd in stripped:
                forbidden.append(f"L{ln_idx}: {stripped[:70]}")
                break
    if forbidden:
        issues.append(f"跨平台违规 (用 Path/os 替代): {forbidden[:3]}")

    # SOFT/AGENT 必须真调 LLM (强约束 · 阻塞)
    if impl_type in ("SOFT", "AGENT"):
        if not (has_llmclient_import or has_agentnodeloop_import or has_llmclient_call):
            issues.append(
                f"impl_type={impl_type} 必须真调 LLM · 但代码里没 import LLMClient / AgentNodeLoop. "
                f"禁用 ast/regex/dict 模拟 LLM 行为."
            )

    # AGENT 工人禁 FinishRouter (2026-04-25 L1 铁律 · SKILL.md §10) — AST 检测真 import / 真用作 class · 不扫注释字面
    finish_imported = False
    finish_in_tool_routers = False
    parse_json_loose_called = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "FinishRouter":
                    finish_imported = True
        # 找 ClassVar[list] = [..., FinishRouter, ...]
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "TOOL_ROUTERS":
            if isinstance(node.value, ast.List):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Name) and elt.id == "FinishRouter":
                        finish_in_tool_routers = True
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "TOOL_ROUTERS" and isinstance(node.value, ast.List):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Name) and elt.id == "FinishRouter":
                            finish_in_tool_routers = True
        # 找 _parse_json_loose() 调用
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_parse_json_loose":
            parse_json_loose_called = True

    if impl_type == "AGENT" and (finish_imported or finish_in_tool_routers):
        issues.append(
            "impl_type=AGENT 真 import 了 FinishRouter / 用作 TOOL_ROUTERS 是反模式 (L1 铁律 SKILL.md §10). "
            "改用自定义 SubmitXxxRouter(SingleToolRouter) · INPUT_SCHEMA 强 schema · "
            "ExtractResult 直接读 block['input']['field'] 不解 JSON."
        )
    if parse_json_loose_called:
        issues.append(
            "禁调 _parse_json_loose() · 改用结构化 SubmitXxxRouter INPUT_SCHEMA (API 已校验) · "
            "ExtractResult 直接读 block['input']['field']."
        )

    return (not issues), issues


# ──────────────────────────────────────────────────────────────────────────
# §4 · AgentNodeLoop 工人代码生成 (核心改动 v1→v2)
# ──────────────────────────────────────────────────────────────────────────


def _build_agent_class():
    """惰性构造 · 避免 module 导入时拉重依赖.

    用 **结构化函数调用**取代 finish + 手解 markdown · 用户 2026-04-25 命定:
    "凡涉 LLM 结构化返回 · 禁手动解析 · 必走 structured output / function call"
    """
    from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
    from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
    from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
    from omnicompany.packages.services._core.agent.routers.single_tool import (
        GlobRouter, GrepRouter, ListDirRouter, ReadFileRouter, SingleToolRouter, ToolContext,
    )
    from omnicompany.protocol.anchor import Verdict, VerdictKind

    # 自定义结构化提交工具 · 严 schema · 替代 FinishRouter+regex
    class SubmitWorkerCodeRouter(SingleToolRouter):
        TOOL_NAME: ClassVar[str] = "submit_worker_code"
        DESCRIPTION: ClassVar[str] = (
            "Submit the complete worker .py file. Calling this terminates the agent loop. "
            "The 'code' field must be **plain Python source** (no markdown fences, no leading/trailing prose). "
            "The 'impl_type' must match the worker's design impl_type (HARD/SOFT/AGENT). "
            "If impl_type is SOFT or AGENT, you MUST import LLMClient or AgentNodeLoop in the code."
        )
        INPUT_SCHEMA: ClassVar[dict] = {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Complete .py file content as plain Python (no ``` fences). Must include all imports + class definition + run() method.",
                },
                "impl_type": {
                    "type": "string",
                    "enum": ["HARD", "SOFT", "AGENT"],
                    "description": "Implementation type. Must match the worker_design's impl_type.",
                },
                "imports_summary": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of key imports used (e.g. ['LLMClient', 'AgentNodeLoop', 'Path']). Helps verification.",
                },
            },
            "required": ["code", "impl_type"],
        }
        IS_CONCURRENCY_SAFE: ClassVar[bool] = True
        IS_READONLY: ClassVar[bool] = True

        def _execute(self, args: dict, ctx: ToolContext) -> str:
            return f"submitted: {len(args.get('code',''))} chars · impl_type={args.get('impl_type')}"

    class _CodeGenPromptBuilder(PromptBuilderRouter):
        def build_initial_messages(self, biz_input: dict) -> list[dict]:
            user_text = biz_input.get("worker_specific_context", "")
            return [{"role": "user", "content": user_text}]

    class _CodeGenExtractResult(ExtractResultRouter):
        def extract(self, *, final_text: str, messages: list, turn_count: int, stop_reason: str) -> Verdict:
            # 找 submit_worker_code tool_use · 直接读结构化 code 字段 · 不解 markdown
            for msg in reversed(messages):
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "submit_worker_code":
                            inp = block.get("input", {}) or {}
                            code = inp.get("code", "")
                            impl_type = inp.get("impl_type", "")
                            imports = inp.get("imports_summary", [])
                            if isinstance(code, str) and code.strip():
                                return Verdict(
                                    kind=VerdictKind.PASS,
                                    output={
                                        "code": code,
                                        "impl_type_declared": impl_type,
                                        "imports_summary": imports,
                                        "turns": turn_count,
                                    },
                                    diagnosis=f"submit_worker_code · {len(code)} chars · impl_type={impl_type} · turns={turn_count}",
                                )
            return Verdict(
                kind=VerdictKind.FAIL,
                output={"code": "", "turns": turn_count, "stop_reason": stop_reason},
                diagnosis=f"未调 submit_worker_code (turns={turn_count}, stop={stop_reason})",
            )

    class _WorkerCodeAgent(AgentNodeLoop):
        FORMAT_IN: ClassVar = "agent.code-request"
        FORMAT_OUT: ClassVar = "agent.code-output"
        ALLOW_NO_BUS: ClassVar = True
        TOOL_ROUTERS: ClassVar = [ReadFileRouter, GlobRouter, GrepRouter, ListDirRouter, SubmitWorkerCodeRouter]
        NODE_PROMPT: ClassVar = _RESOURCE_MAP

        def __init__(self):
            from omnicompany.bus.memory import MemoryBus
            super().__init__(bus=MemoryBus(), role="runtime_main")

        def build_prompt_builder(self, *, bus):
            return _CodeGenPromptBuilder(template=self.NODE_PROMPT, bus=bus)

        def build_extract_result(self, *, bus):
            return _CodeGenExtractResult(bus=bus)

    return _WorkerCodeAgent


# ──────────────────────────────────────────────────────────────────────────
# §5 · 主流程 · 逐工人 (调 agent loop)
# ──────────────────────────────────────────────────────────────────────────


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--target-pkg-path", default=None)
    ap.add_argument("--max-retries", type=int, default=2)
    args = ap.parse_args()

    snapshot = Path(args.snapshot)
    worktree = Path(args.worktree)
    if not snapshot.is_dir() or not worktree.is_dir():
        print(f"[FAIL] 路径不存在: snapshot={snapshot} worktree={worktree}", file=sys.stderr)
        return 2

    ws = load_workspace(snapshot)
    target_pkg = args.target_pkg_path
    if target_pkg is None:
        sink_path = snapshot / "sink_registration_plan.json"
        if sink_path.exists():
            target_pkg = json.loads(sink_path.read_text(encoding="utf-8"))["target_package_path"]
        else:
            target_pkg = f"src/omnicompany/packages/services/{ws['team_design']['team_name']}/"
    target_pkg = target_pkg.rstrip("/") + "/"

    order = topo_order_workers(ws)
    print(f"[seq-v2] 写入顺序 ({len(order)}): {order}")
    print(f"[seq-v2] target pkg: {target_pkg}")
    print(f"[seq-v2] worktree: {worktree}\n")

    AgentClass = _build_agent_class()

    written: dict[str, str] = {}
    workers_dir = worktree / target_pkg / "workers"
    workers_dir.mkdir(parents=True, exist_ok=True)
    failed_dir = worktree / "_failed_attempts"
    failed_dir.mkdir(exist_ok=True)

    for idx, wid in enumerate(order, 1):
        print(f"\n{'='*60}\n  工人 {idx}/{len(order)} · {wid} (impl_type={ws['workers'][wid].get('impl_type')})\n{'='*60}")
        success = False
        for attempt in range(1, args.max_retries + 2):
            print(f"[seq-v2] attempt {attempt}/{args.max_retries+1} · agent loop 取资料 + 写代码 ...")
            ws_ctx = _build_worker_specific_context(wid, ws, written)
            agent = AgentClass()
            try:
                run_result = agent.run({"worker_specific_context": ws_ctx})
                if inspect.iscoroutine(run_result):
                    verdict = asyncio.run(run_result)
                else:
                    verdict = run_result
            except Exception as e:
                print(f"  [agent-error] {type(e).__name__}: {e}")
                continue
            kind_val = getattr(getattr(verdict, "kind", None), "value", "?")
            output = getattr(verdict, "output", {}) or {}
            code = output.get("code", "")
            (failed_dir / f"{wid}_attempt{attempt}.py").write_text(code or "(empty)", encoding="utf-8")
            if kind_val != "pass" or not code:
                print(f"  [agent-fail] verdict={kind_val} · {(getattr(verdict,'diagnosis','') or '')[:200]}")
                continue
            ok, issues = static_check(code, wid, ws)
            if ok:
                fpath = workers_dir / f"{_to_snake(wid)}.py"
                fpath.write_text(code, encoding="utf-8")
                size = fpath.stat().st_size
                print(f"[OK] {wid} · {size} bytes · 静态全 PASS · turns={output.get('turns')} · 落 {fpath.relative_to(worktree)}")
                written[wid] = code
                success = True
                break
            print(f"[STATIC FAIL] {wid} attempt {attempt}:")
            for i in issues:
                print(f"  · {i}")
            print(f"  [debug] LLM 产物已落 {(failed_dir / f'{wid}_attempt{attempt}.py').relative_to(worktree)}")
        if not success:
            print(f"\n[ABORT] {wid} {args.max_retries+1} 次重试后仍失败 · 中止. 已写工人保留.")
            return 1

    print(f"\n=== {len(written)}/{len(order)} 工人全部静态通过 · worktree: {worktree} ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
