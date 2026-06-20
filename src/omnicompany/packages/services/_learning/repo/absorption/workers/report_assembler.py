# [OMNI] origin=claude-code domain=services/repo_absorption/workers ts=2026-04-25T00:00:00Z type=worker
# [OMNI] material_id="material:learning.repo.absorption.worker.report_assembler_hard.py"
"""ReportAssemblerWorker — repo_absorption Team Worker #5 (HARD).

Worker 协议:
  FORMAT_IN  = ['repo_absorption.extraction_results', 'repo_absorption.module_sources']
  FORMAT_OUT = repo_absorption.sink_report
  FORMAT_IN_MODE = and

职责: 接收 PatternExtractorWorker 的 extraction_results 与 SourceReaderWorker 的
      module_sources, 严格校验 reference_code 锚点真实性 (文件路径存在于 module_sources,
      snippet 逐字出现在对应 content 中, line_start 在有效行范围内),
      校验通过后组装综合 markdown 报告, 包含 '## 仓库一览', '## 关键模式',
      '## 提案总览' 三个二级章节.
      纯确定性 HARD 节点, 不调 LLM.
"""
from __future__ import annotations

import logging
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

logger = logging.getLogger(__name__)


def _find_module_content(
    file_path: str,
    modules: list[dict],
) -> dict | None:
    """在 module_sources 中查找与 file_path 匹配的模块.

    返回匹配的模块 dict (含 module_path, content, line_count), 未找到返回 None.
    """
    for mod in modules:
        mod_path = mod.get("module_path", "")
        # 精确匹配, 也尝试相对路径去除前缀
        if mod_path == file_path or file_path.endswith("/" + mod_path) or mod_path.endswith(file_path):
            return mod
    return None


def _validate_reference(
    proposal: dict,
    module_by_path: dict[str, dict],
) -> str | None:
    """校验单个提案的 reference_code 锚点真实性.

    返回 None = 校验通过; 非 None = 错误描述.
    """
    ref = proposal.get("reference_code")
    if not isinstance(ref, dict):
        return "reference_code 缺失或格式错误"

    file_path = ref.get("file", "")
    line_start = ref.get("line_start")
    snippet = ref.get("snippet", "")

    if not file_path:
        return "reference_code.file 为空"
    if not isinstance(line_start, int) or line_start < 1:
        return f"reference_code.line_start 必须是 ≥1 的整数 (got {line_start})"
    if not snippet:
        return "reference_code.snippet 为空"

    mod = module_by_path.get(file_path)
    if mod is None:
        return f"reference_code.file '{file_path}' 在 module_sources 中不存在"

    content = mod.get("content", "")
    line_count = mod.get("line_count", 0)

    if line_start > line_count:
        return (
            f"reference_code.line_start={line_start} "
            f"超出文件 '{file_path}' 总行数 ({line_count})"
        )

    # 校验 snippet 首行是否在 content 中逐字出现
    snippet_first_line = snippet.splitlines()[0] if snippet.splitlines() else ""
    if snippet_first_line and snippet_first_line not in content:
        return (
            f"reference_code.snippet 首行 '{snippet_first_line[:80]}...' "
            f"未在 '{file_path}' 源码中找到"
        )

    return None


class ReportAssemblerWorker(Worker):
    """组装并验证 repo_absorption 最终 sink 报告 (HARD).

    严格校验 reference_code 真实性, 通过后组装 markdown 报告.
    """

    DESCRIPTION = (
        "接收 repo_absorption.extraction_results 和 repo_absorption.module_sources, "
        "严格校验每个提案的 reference_code 锚点真实性 (文件路径存在于 module_sources, "
        "snippet 逐字出现在对应 content 中, line_start 在有效行范围内), "
        "校验通过后组装综合 markdown 报告 (含 '## 仓库一览' '## 关键模式' '## 提案总览'), "
        "产出 repo_absorption.sink_report. 纯确定性 HARD 节点."
    )
    FORMAT_IN = [
        "repo_absorption.extraction_results",
        "repo_absorption.module_sources",
    ]
    FORMAT_IN_MODE = "and"
    FORMAT_OUT = "repo_absorption.sink_report"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        # ── 提取输入 (平铺读, 对应上游 FORMAT_OUT 字段) ──
        proposals: list[dict] | None = input_data.get("proposals")
        source_analysis_context: dict | None = input_data.get("source_analysis_context")
        analysis_metadata: dict | None = input_data.get("analysis_metadata")
        module_count: int | None = input_data.get("module_count")
        modules: list[dict] | None = input_data.get("modules")
        repo_path: str | None = input_data.get("repo_path")

        # 字段完整性校验
        if proposals is None or not isinstance(proposals, list):
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="extraction_results.proposals 缺失或格式错误",
            )
        if source_analysis_context is None:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="extraction_results.source_analysis_context 缺失",
            )
        if analysis_metadata is None:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="extraction_results.analysis_metadata 缺失",
            )
        if modules is None or not isinstance(modules, list):
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="module_sources.modules 缺失或格式错误",
            )

        if not isinstance(module_count, int) or module_count < 1:
            module_count = len(modules)

        # ── 构建 module_path → content 快速索引 ──
        module_by_path: dict[str, dict] = {}
        for mod in modules:
            mp = mod.get("module_path", "")
            if mp:
                module_by_path[mp] = mod

        # ── 校验 proposals 的 reference_code 锚点真实性 ──
        valid_proposals: list[dict] = []
        invalid_proposals: list[dict] = []
        validation_errors: list[dict] = []

        for proposal in proposals:
            if not isinstance(proposal, dict):
                validation_errors.append({"proposal": str(proposal)[:50], "error": "非 dict 类型"})
                invalid_proposals.append(proposal)
                continue

            prop_id = proposal.get("id", "(无id)")
            err = _validate_reference(proposal, module_by_path)
            if err:
                validation_errors.append({"proposal_id": prop_id, "error": err})
                invalid_proposals.append(proposal)
                logger.warning("ReportAssembler: proposal %s 锚点校验失败: %s", prop_id, err)
            else:
                valid_proposals.append(proposal)

        total = len(proposals)
        valid_count = len(valid_proposals)
        invalid_count = len(invalid_proposals)

        # 有效性判断
        if valid_count == 0:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=(
                    f"所有 {total} 条提案的 reference_code 锚点均校验失败. "
                    f"前 3 条错误: {validation_errors[:3]}"
                ),
            )

        # ── 组装 markdown 报告 ──
        identified_patterns: list[str] = source_analysis_context.get("identified_patterns", [])
        module_summaries: list[dict] = source_analysis_context.get("module_summaries", [])
        files_analyzed: int = analysis_metadata.get("files_analyzed", module_count)
        total_lines: int = analysis_metadata.get("total_lines", 0)
        repo: str = repo_path or analysis_metadata.get("repo_path", "(未知)")

        # 统计风险等级分布 (从 proposal 的 risk 文本中粗略提取)
        risk_summary_parts: list[str] = []
        for p in valid_proposals:
            risk_summary_parts.append(f"- **{p['id']}**: {p['risk']}")

        report_parts: list[str] = []

        # 标题
        report_parts.append(f"# 代码分析报告: {repo}")
        report_parts.append("")
        report_parts.append(
            f"> 分析范围: {repo} · 共 {files_analyzed} 个文件, "
            f"{total_lines} 行代码 · {len(identified_patterns)} 个识别模式 · "
            f"{valid_count}/{total} 条提案通过锚点校验"
        )
        report_parts.append("")

        # ## 仓库一览
        report_parts.append("## 仓库一览")
        report_parts.append("")
        report_parts.append(f"- **仓库路径**: `{repo}`")
        report_parts.append(f"- **分析文件数**: {files_analyzed}")
        if total_lines > 0:
            report_parts.append(f"- **总代码行数**: {total_lines}")
        report_parts.append(f"- **分析模块数**: {module_count}")
        report_parts.append("")

        if module_summaries:
            report_parts.append("### 模块职责概览")
            report_parts.append("")
            report_parts.append("| 模块 | 职责 | 复杂度备注 |")
            report_parts.append("|------|------|------------|")
            for ms in module_summaries:
                fp = ms.get("file_path", "(未知)")
                rs = ms.get("role_summary", "(未描述)")
                cn = ms.get("complexity_note", "-")
                report_parts.append(f"| `{fp}` | {rs} | {cn} |")
            report_parts.append("")

        report_parts.append("### 已读取模块详情")
        report_parts.append("")
        report_parts.append(f"成功读取 {len(modules)} 个模块源码:")
        report_parts.append("")
        for mod in modules:
            mp = mod.get("module_path", "(未知)")
            lc = mod.get("line_count", 0)
            bs = mod.get("byte_size", 0)
            report_parts.append(f"- `{mp}` — {lc} 行, {bs:,} 字节")
        report_parts.append("")

        # ## 关键模式
        report_parts.append("## 关键模式")
        report_parts.append("")
        if identified_patterns:
            for idx, pattern in enumerate(identified_patterns, 1):
                report_parts.append(f"{idx}. {pattern}")
            report_parts.append("")
        else:
            report_parts.append("> 未识别到明确的代码模式.")
            report_parts.append("")

        # ## 提案总览
        report_parts.append("## 提案总览")
        report_parts.append("")
        report_parts.append(
            f"共 {total} 条提案, 其中 {valid_count} 条通过 reference_code 锚点校验, "
            f"{invalid_count} 条因锚点不合法被排除."
        )
        report_parts.append("")

        for p in valid_proposals:
            ref = p.get("reference_code", {})
            file = ref.get("file", "")
            line_start = ref.get("line_start", 0)
            snippet = ref.get("snippet", "")

            # 容错: LLM 偶尔会少字段, 用 .get 避免 KeyError 阻断整次跑 (2026-04-26 修)
            report_parts.append(f"### {p.get('id','?')}: {p.get('title','(无标题)')}")
            report_parts.append("")
            report_parts.append(f"**问题**: {p.get('problem','(无)')}")
            report_parts.append("")
            report_parts.append(f"**改进方向**: {p.get('proposed_change','(无)')}")
            report_parts.append("")
            report_parts.append(f"**风险**: {p.get('risk','(无)')}")
            report_parts.append("")
            report_parts.append(f"**参考代码**: `{file}:{line_start}`")
            report_parts.append("")
            if snippet:
                # snippet 截断显示 (报告中展示前 10 行)
                snippet_lines = snippet.splitlines()
                display_snippet = "\n".join(snippet_lines[:10])
                if len(snippet_lines) > 10:
                    display_snippet += f"\n...(共 {len(snippet_lines)} 行)"
                report_parts.append("```python")
                report_parts.append(display_snippet)
                report_parts.append("```")
                report_parts.append("")

        # 校验失败信息 (如果有)
        if invalid_count > 0:
            report_parts.append("## ⚠️ 锚点校验排除的提案")
            report_parts.append("")
            for ve in validation_errors:
                report_parts.append(f"- **{ve.get('proposal_id', 'unknown')}**: {ve['error']}")
            report_parts.append("")

        report_markdown = "\n".join(report_parts)

        # 最终长度校验 (FORMAT_OUT minLength=500)
        if len(report_markdown) < 500:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"生成的 report_markdown 仅 {len(report_markdown)} 字符, 不满足 ≥500 的最低要求",
            )

        # 章节完整性校验
        required_sections = ["## 仓库一览", "## 关键模式", "## 提案总览"]
        missing_sections = [s for s in required_sections if s not in report_markdown]
        if missing_sections:
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"report_markdown 缺少必需章节: {missing_sections}",
            )

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "report_markdown": report_markdown,
                "proposals": valid_proposals,
            },
            diagnosis=(
                f"报告组装完成: {valid_count}/{total} 条提案通过锚点校验, "
                f"报告 {len(report_markdown)} 字符, "
                f"包含 {len(identified_patterns)} 个代码模式"
            ),
            confidence=1.0,
        )
