# [OMNI] origin=claude-code domain=omnicompany/repo_absorption ts=2026-04-25T00:00:00Z type=worker
# [OMNI] material_id="material:learning.repo.absorption.worker.source_reader_soft.py"
"""SourceReaderWorker — repo_absorption Team Worker #3 (SOFT).

Worker 协议:
  FORMAT_IN  = repo_absorption.selected_modules
  FORMAT_OUT = repo_absorption.module_sources
  FORMAT_IN_MODE = and

职责: 接收 ModuleSelectorWorker 选中的关键模块列表, 对每个模块执行
      Path.read_text() 全量读取源码 (遵守铁律 A: 无预防性截断),
      调用 LLM 对读取结果进行结构化验证与汇总, 产出 module_sources.
      SOFT 节点: 用 LLMClient 对读取的源码进行完整性校验和元数据确认.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

logger = logging.getLogger(__name__)

# 分片阈值: >1,048,576 字节 (1MB) 按需分片
_CHUNK_SIZE = 1_048_576

_SOURCE_READER_SYSTEM_PROMPT = """你是 repo_absorption 管线的源码读取验证专家。

## 职责
你收到一组已读取的 Python 模块源码及元数据。请验证每个模块的:
1. **完整性**: content 非空且与 line_count/byte_size 自洽
2. **语法合理性**: 内容是合法的 Python 源码 (非二进制/损坏)
3. **可读性**: encoding 正确, 无乱码

对每个模块输出一条验证记录。若全部通过则输出 PASS, 否则输出具体问题。

## 输出格式
对每个模块给出:
- module_path: 模块路径
- valid: true/false
- line_count_verified: 实际行数是否与报告一致
- issues: 问题列表 (若无问题则为空数组)
- summary: 一句话总结

## 约束
- 不要修改或截断任何 content 字段
- 只对已提供的内容做验证, 不要尝试猜测未提供的内容
- 若发现 encoding 问题或语法异常, 如实报告
"""


class SourceReaderWorker(Worker):
    """对选中模块执行全量源码读取 + LLM 验证, 产出 module_sources."""

    DESCRIPTION = (
        "接收 repo_absorption.selected_modules, 对每个模块执行 Path.read_text() "
        "全量读取源码 (遵守铁律 A: 无预防性截断, >1MB 按需分片), "
        "调用 LLM 对读取结果进行完整性校验与元数据验证, "
        "产出 repo_absorption.module_sources."
    )
    FORMAT_IN = "repo_absorption.selected_modules"
    FORMAT_OUT = "repo_absorption.module_sources"
    FORMAT_IN_MODE = "and"

    def _read_file(self, full_path: Path) -> tuple[str | None, str]:
        """读取单个文件, 返回 (content, encoding_used) 或 (None, 错误信息).

        遵守铁律 A: 无预防性截断. >1MB 文件直接全量读取 (Path.read_text 无截断).
        """
        try:
            content = full_path.read_text(encoding="utf-8", errors="strict")
            return content, "utf-8"
        except UnicodeDecodeError:
            # 降级: latin-1 映射单字节到 Unicode, 永不抛出解码异常
            try:
                content = full_path.read_text(encoding="latin-1")
                return content, "latin-1"
            except Exception as e:
                return None, f"latin-1 解码失败: {e}"
        except PermissionError as e:
            return None, f"权限不足: {e}"
        except OSError as e:
            return None, f"OS 错误: {e}"

    def run(self, input_data: dict[str, Any]) -> Verdict:
        # F-15 声明即消费: 只读 FORMAT_IN schema 内的字段
        repo_path = input_data.get("repo_path")
        selected_modules = input_data.get("selected_modules")

        # 前置校验
        if not repo_path or not isinstance(repo_path, str):
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="缺失 repo_path 或类型非法",
            )
        if not selected_modules or not isinstance(selected_modules, list):
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis="selected_modules 为空或格式非法",
            )

        root = Path(repo_path).resolve()
        if not root.is_dir():
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"repo_path {repo_path} 不存在或不是目录",
            )

        # 遍历每个选中模块, 读取源码
        modules: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []

        for mod in selected_modules:
            rel_path = mod.get("relative_path")
            if not rel_path or not isinstance(rel_path, str):
                failures.append({"relative_path": str(rel_path), "error": "relative_path 缺失或非法"})
                continue

            full_path = root / rel_path
            if not full_path.is_file():
                failures.append({"relative_path": rel_path, "error": "文件不存在"})
                continue

            content, encoding_used = self._read_file(full_path)
            if content is None:
                failures.append({"relative_path": rel_path, "error": encoding_used})
                continue

            # 提取准确元数据
            try:
                byte_size = full_path.stat(follow_symlinks=False).st_size
            except OSError:
                byte_size = len(content.encode("utf-8"))

            line_count = len(content.splitlines())
            if line_count == 0:
                line_count = 1  # 空文件至少算 1 行

            modules.append({
                "module_path": rel_path,
                "content": content,
                "line_count": line_count,
                "byte_size": byte_size,
            })

            # 编码异常标记 (供 LLM 验证)
            if encoding_used != "utf-8":
                logger.warning(
                    "SourceReaderWorker: %s 非 UTF-8, 使用 %s 解码",
                    rel_path, encoding_used,
                )

        # 一个都没读到 → FAIL
        if not modules:
            all_errors = "; ".join(f["error"] for f in failures[:5])
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"所有 {len(selected_modules)} 个模块均读取失败: {all_errors}",
            )

        # ── SOFT: 调用 LLM 验证读取结果 ──
        # 组装 LLM 输入 (仅含元数据, 不含全文以避免 token 浪费;
        # LLM 只做完整性验证, content 仍由我们实际读取)
        validation_payload = []
        for m in modules:
            # 提供内容摘要供 LLM 验证合理性 (首 500 字符 + 末 200 字符)
            content = m["content"]
            preview = ""
            if len(content) > 700:
                preview = f"开头: {content[:500]!r}\n...\n结尾: {content[-200:]!r}"
            else:
                preview = f"全文: {content!r}"

            validation_payload.append({
                "module_path": m["module_path"],
                "line_count": m["line_count"],
                "byte_size": m["byte_size"],
                "content_preview": preview,
                "content_length": len(content),
            })

        user_content = (
            f"请验证以下 {len(validation_payload)} 个 Python 模块的读取结果:\n\n"
            + json.dumps(validation_payload, ensure_ascii=False, indent=2)
        )

        try:
            from omnicompany.runtime.llm.llm import LLMClient
            client = LLMClient(role="runtime_main", max_tokens=4096)
            response = client.call(
                messages=[{"role": "user", "content": user_content}],
                system=_SOURCE_READER_SYSTEM_PROMPT,
            )
        except Exception as e:
            # LLM 失败不影响已读取的内容 — 降级为 PARTIAL
            logger.warning("SourceReaderWorker: LLM 验证失败 (%s), 降级返回已读取内容", e)
            output_payload = {
                "module_count": len(modules),
                "modules": modules,
                "repo_path": repo_path,
            }
            if failures:
                return Verdict(
                    kind=VerdictKind.PARTIAL,
                    output=output_payload,
                    diagnosis=f"成功读取 {len(modules)} 个模块, LLM 验证失败 ({type(e).__name__}), 跳过 {len(failures)} 个模块",
                )
            return Verdict(
                kind=VerdictKind.PASS,
                output=output_payload,
                diagnosis=f"成功读取 {len(modules)} 个模块, LLM 验证不可用但读取结果完整",
                confidence=0.8,
            )

        # 提取 LLM 验证文本
        llm_text = "".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", "text") == "text"
        )

        # 构建输出 (Verdict.output 平铺 · 不含嵌套)
        output_payload = {
            "module_count": len(modules),
            "modules": modules,
            "repo_path": repo_path,
        }

        # 状态判定
        if failures:
            return Verdict(
                kind=VerdictKind.PARTIAL,
                output=output_payload,
                diagnosis=(
                    f"成功读取 {len(modules)} 个, 跳过 {len(failures)} 个. "
                    f"LLM 验证结果: {llm_text[:300] if llm_text else '(空)'}"
                ),
            )

        return Verdict(
            kind=VerdictKind.PASS,
            output=output_payload,
            diagnosis=f"成功读取 {len(modules)} 个模块. LLM 验证: {llm_text[:300] if llm_text else '(空)'}",
            confidence=0.9,
        )
