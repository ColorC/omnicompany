# [OMNI] origin=claude-code domain=services/repo_absorption/workers ts=2026-04-25T00:00:00Z type=worker
# [OMNI] material_id="material:learning.repo.absorption.worker.module_selector_agent.py"
"""ModuleSelectorWorker — repo_absorption Team Worker #2 (AGENT).

Worker 协议:
  FORMAT_IN  = ['repo_absorption.file_inventory', 'repo_absorption.scan_config']
  FORMAT_OUT = repo_absorption.selected_modules
  FORMAT_IN_MODE = and

职责: 基于文件索引与扫描配置，通过 AgentNodeLoop 进行 LLM 驱动的智能模块筛选。
      使用 ReadFile / Grep / Glob / ListDir 工具探索文件结构与内容，
      按复杂度评分选出 top_n 关键模块。
      严格遵守 F-15 诚实原则：只选择 file_inventory 中真实存在的文件路径。
"""
from __future__ import annotations

import json
from typing import Any, ClassVar

from omnicompany.packages.services._core.agent.loop import AgentNodeLoop
from omnicompany.packages.services._core.agent.routers.extract_result import ExtractResultRouter
from omnicompany.packages.services._core.agent.routers.prompt_builder import PromptBuilderRouter
from omnicompany.packages.services._core.agent.routers.single_tool import (
    GlobRouter,
    GrepRouter,
    ListDirRouter,
    ReadFileRouter,
    SingleToolRouter,
    ToolContext,
)
from omnicompany.protocol.anchor import Verdict, VerdictKind


_SYSTEM_PROMPT = """你是 repo_absorption 管线的 ModuleSelectorWorker — 一个基于 LLM 的模块选择 Agent。

## 职责
接收文件索引 (file_inventory) 与扫描配置 (scan_config)，通过探索文件结构与内容，
按复杂度/结构价值评分智能筛选 top_n 个最关键 .py 模块。

## 输入数据格式
- repo_path: 扫描根目录路径
- top_n: 选出模块数量上限
- total_files: 扫描到的 .py 文件总数
- files[]: 全量文件清单，每项含 rel_path, line_count, size_bytes

## 判定维度
1. **体积权重**: 行数 > 500 通常承载核心逻辑；> 1000 为大型核心模块
2. **命名启发**: 含 core/service/engine/manager/handler/factory/protocol/client/adapter/model/schema 等关键域命名优先
3. **结构角色**: __init__.py (包入口)、含 router/pipeline/team/app/cli/worker 的编排文件
4. **内容深度**: 使用 read_file 读取候选文件，评估类/函数数量、导入复杂度、设计模式

## 筛选策略
- 优先选择 line_count > 100 且含核心域命名的文件
- 排除测试/辅助文件 (test_/conftest/fixture/mock_/example_/migrate/sandbox/benchmark)
- __init__.py 如果很小 (< 20 行) 则降权；但如果是大包的入口则保留
- 小型但关键的文件 (如路由配置、协议定义) 不应被遗漏

## 边界处理
- 若 top_n < 3，至少选择 1 个模块 (边界兜底)
- 确保 selected_modules 数组按 complexity_score 降序排列

## 工具
- **read_file**: 读取文件内容评估复杂度 (file_path 必须是绝对路径)
- **grep**: 搜索代码模式 (如 "class "、"def "、"import ")
- **glob**: 探索目录结构 (如 "**/core/*.py")
- **list_dir**: 列出目录内容
- **submit_selected_modules**: 提交最终筛选结果 (结构化 schema，各字段直接填)

## 评分规则
- 0-20: 低价值 (测试/辅助/配置)
- 21-40: 基础模块 (工具类/辅助函数)
- 41-60: 中等模块 (业务逻辑/数据处理)
- 61-80: 核心模块 (主要业务/架构组件)
- 81-100: 关键模块 (核心引擎/协议/入口)

## 重要约束
- **只选择 file_inventory 列表中实际存在的文件路径，绝对不要虚构路径！**
- 使用 read_file 时，file_path = repo_path + "/" + rel_path (绝对路径)
- selection_reason 必须 ≥ 10 字符，说明结构性特征或模式价值
- 最终必须调用 submit_selected_modules 提交结果"""


class _ModuleSelectorPromptBuilder(PromptBuilderRouter):
    """定制 prompt builder: 把 file_inventory 数据注入到 agent 首轮会话."""

    def build_initial_messages(self, biz_input: dict) -> list[dict]:
        repo_path = biz_input.get("repo_path", "")
        top_n = biz_input.get("top_n", 5)
        total_files = biz_input.get("total_files", 0)
        files = biz_input.get("files", [])

        if not isinstance(top_n, int) or top_n < 1:
            top_n = 5

        # 构建文件元数据摘要 (让 agent 用工具按需读取内容)
        file_entries = []
        for f in files:
            file_entries.append({
                "rel_path": f.get("rel_path", ""),
                "line_count": f.get("line_count", 0),
                "size_bytes": f.get("size_bytes", 0),
            })

        task = f"""## 任务: 从 {total_files} 个 .py 文件中选出 top {top_n} 关键模块

### 扫描配置
- repo_path: `{repo_path}`
- top_n: {top_n}

### 文件索引 (共 {total_files} 个 .py 文件)

```json
{json.dumps(file_entries, ensure_ascii=False, indent=2)}
```

### 操作流程
1. 根据元数据 (line_count/size_bytes/rel_path) 初步筛选候选文件
2. 对候选文件使用 `read_file` 读取内容，评估实际复杂度 (类/函数数量、导入结构)
3. 使用 `grep` 搜索关键模式 (如 "class "、"def " 出现频率) 辅助评分
4. 使用 `glob` / `list_dir` 探索目录结构来理解包层次
5. 最终调用 `submit_selected_modules` 提交结果

### 注意事项
- **只从上面的文件列表中选择**，不要虚构文件路径
- read_file 的 file_path 必须是绝对路径: `{repo_path}/rel_path`
- 排除测试/辅助文件
- selection_reason 必须 ≥ 10 字符
- 确保输出按 complexity_score 降序排列

请开始探索并提交筛选结果。"""

        return [{"role": "user", "content": task}]


class SubmitSelectedModulesRouter(SingleToolRouter):
    """提交模块筛选结果 · 结构化 schema · 替代 FinishRouter + 手解 JSON."""

    TOOL_NAME: ClassVar[str] = "submit_selected_modules"
    DESCRIPTION: ClassVar[str] = (
        "Submit the final selected modules list. Calling this terminates the agent loop. "
        "All fields are validated by API schema; do not embed JSON in plain text."
    )
    INPUT_SCHEMA: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "repo_path": {
                "type": "string",
                "description": "被扫描的仓库根路径 (透传自输入)",
            },
            "total_files_scanned": {
                "type": "integer",
                "minimum": 0,
                "description": "RepoScannerWorker 枚举的 .py 文件总数",
            },
            "selected_modules": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "relative_path": {
                            "type": "string",
                            "description": "模块文件相对于 repo_path 的相对路径",
                        },
                        "line_count": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "该文件的总行数",
                        },
                        "size_bytes": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "该文件的字节大小",
                        },
                        "complexity_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "LLM 评估的复杂度评分 (越高越关键)",
                        },
                        "selection_reason": {
                            "type": "string",
                            "minLength": 10,
                            "description": "选中理由 (结构性特征或模式价值, ≥10字符)",
                        },
                    },
                    "required": [
                        "relative_path",
                        "line_count",
                        "complexity_score",
                        "selection_reason",
                    ],
                },
                "description": "经 LLM 优先级排序后选中的目标模块列表，按 complexity_score 降序",
            },
            "selection_criteria": {
                "type": "string",
                "description": "本次筛选采用的策略简述",
            },
        },
        "required": ["repo_path", "selected_modules"],
    }
    IS_CONCURRENCY_SAFE: ClassVar[bool] = True
    IS_READONLY: ClassVar[bool] = True

    def _execute(self, args: dict, ctx: ToolContext) -> str:
        selected = args.get("selected_modules", [])
        total = args.get("total_files_scanned", "?")
        return f"submitted: {len(selected)} modules selected from {total} files"


class _ModuleSelectorExtractResult(ExtractResultRouter):
    """从 messages 中提取 submit_selected_modules 的结构化结果 (不解 JSON)."""

    def extract(
        self,
        *,
        final_text: str,
        messages: list[dict],
        turn_count: int,
        stop_reason: str,
    ) -> Verdict:
        # 找 submit_selected_modules tool_use · 直接读结构化 input · 不解 JSON
        result_json: dict | None = None
        for msg in reversed(messages):
            content = msg.get("content")
            if isinstance(content, list):
                for block in content:
                    if (
                        isinstance(block, dict)
                        and block.get("type") == "tool_use"
                        and block.get("name") == "submit_selected_modules"
                    ):
                        inp = block.get("input", {})
                        if isinstance(inp, dict):
                            result_json = dict(inp)
                            break
            if result_json:
                break

        if not isinstance(result_json, dict):
            return Verdict(
                kind=VerdictKind.FAIL,
                output={"final_text": final_text[:500], "turn_count": turn_count},
                diagnosis=(
                    f"ModuleSelectorWorker 未调用 submit_selected_modules "
                    f"(turns={turn_count}, stop={stop_reason})"
                ),
            )

        # 验证必需字段
        repo_path = result_json.get("repo_path")
        selected_modules = result_json.get("selected_modules")

        if not repo_path or not isinstance(repo_path, str):
            return Verdict(
                kind=VerdictKind.FAIL,
                output=result_json,
                diagnosis="缺失 repo_path 或类型非法",
            )

        if (
            not selected_modules
            or not isinstance(selected_modules, list)
            or len(selected_modules) == 0
        ):
            return Verdict(
                kind=VerdictKind.FAIL,
                output=result_json,
                diagnosis="selected_modules 为空或格式非法",
            )

        # 确保按 complexity_score 降序排列
        try:
            selected_modules.sort(
                key=lambda m: m.get("complexity_score", 0), reverse=True
            )
        except Exception:
            pass

        # 构建平铺输出 (Verdict.output 不含嵌套)
        output_payload: dict[str, Any] = {
            "repo_path": repo_path,
            "selected_modules": selected_modules,
        }

        if "total_files_scanned" in result_json:
            output_payload["total_files_scanned"] = result_json["total_files_scanned"]
        if "selection_criteria" in result_json:
            output_payload["selection_criteria"] = result_json["selection_criteria"]

        # 根据 stop_reason 决定 verdict kind
        if stop_reason == "max_turns":
            return Verdict(
                kind=VerdictKind.PARTIAL,
                output=output_payload,
                diagnosis=f"预算耗尽: {turn_count} turns，已选 {len(selected_modules)} 个模块",
            )

        return Verdict(
            kind=VerdictKind.PASS,
            output=output_payload,
            diagnosis=f"成功选出 {len(selected_modules)} 个关键模块",
            confidence=0.9,
        )


class ModuleSelectorWorker(AgentNodeLoop):
    """repo_absorption Team Worker #2 · AGENT 模块智能筛选.

    通过 AgentNodeLoop 多轮探索 (ReadFile / Grep / Glob / ListDir)，
    LLM 综合评估文件复杂度与结构价值，选出 top_n 关键模块。
    """

    FORMAT_IN: ClassVar[list[str]] = [
        "repo_absorption.file_inventory",
        "repo_absorption.scan_config",
    ]
    FORMAT_IN_MODE: ClassVar[str] = "and"
    FORMAT_OUT: ClassVar[str] = "repo_absorption.selected_modules"
    DESCRIPTION: ClassVar[str] = (
        "基于文件索引与扫描配置，通过 AgentNodeLoop 进行 LLM 驱动的智能模块筛选。"
        "使用 ReadFile/Grep/Glob/ListDir 工具探索文件结构与内容，按复杂度评分选出 top_n 关键模块。"
        "严格遵守 F-15 诚实原则：只选择 file_inventory 中真实存在的文件路径。"
    )
    ALLOW_NO_BUS: ClassVar[bool] = True
    TOOL_ROUTERS: ClassVar[list] = [
        ReadFileRouter,
        GlobRouter,
        GrepRouter,
        ListDirRouter,
        SubmitSelectedModulesRouter,
    ]
    NODE_PROMPT: ClassVar[str] = _SYSTEM_PROMPT

    def __init__(self) -> None:
        from omnicompany.bus.memory import MemoryBus

        super().__init__(bus=MemoryBus(), role="runtime_main")

    def build_prompt_builder(self, *, bus: Any) -> _ModuleSelectorPromptBuilder:
        return _ModuleSelectorPromptBuilder(template=self.NODE_PROMPT, bus=bus)

    def build_extract_result(self, *, bus: Any) -> _ModuleSelectorExtractResult:
        return _ModuleSelectorExtractResult(bus=bus)
