---
omnikb_type: kformat
id: "kb.core.workflow_requirement"
name: "工作流原始需求"
tags: []
relates_to_formats:
  - wf.requirement_raw
  - requirement
relates_to_krouters:
  - kb.core.requirement_to_spec
maturity: stable
summary: "用自然语言表达的工作流创建需求，是 workflow_factory 管线的起点。"
---

# 工作流原始需求

用自然语言表达的工作流创建需求，是 `workflow_factory` 管线的唯一入口。其描述质量直接决定后续 Format 链和 Router 节点设计的准确性。

## 已知结构特征

- **核心内容**：目标描述（"做什么"）、领域标识（"在哪个域下面"）、输入输出的直觉描述
- **典型格式**：自然语言段落，长度从一句话到数百字不等
- **可选元素**：
  - 约束条件（如"不能修改数据库"、"必须在 5 秒内完成"）
  - 参考案例（"类似 sw-review 但要..."）
  - 错误场景预期（"如果 LLM 返回乱码要..."）
- **语言**：中文为主

## 验证要点

1. 文本非空
2. 包含可识别的目标（至少有动词+宾语结构）
3. 能够从中提取领域信息（即使是模糊的也可以）

注意：这类数据**非常宽泛**，验证标准刻意保持宽松——对于模糊需求，应由后续节点（如 `ReqAnalyzerRouter`）通过 UserInquiry 补充信息，而不是在入口处拒绝。

## 下游用途

- **`wf.req_analyzer` → `wf.requirement`**：LLM 将自然语言需求解析为结构化需求规格
- 是 workflow_factory 管线的 `FORMAT_IN = "wf.requirement_raw"` 类型的语义描述

## 关联 Format 说明

与可执行 `wf.requirement_raw` Format 的关系：
- 两者在语义上完全对应，`wf.requirement_raw` 是此 KFormat 的精确形式化版本
- `wf.requirement_raw` 有 JSON Schema 约束（要求 `text` 字段），而此 KFormat 描述的是在 Schema 约束之外的语义理解
- 当 `wf.requirement_raw` 定义需要更新时，此文档也应同步更新

## 良好需求的特征

以下特征有助于提高后续节点的输出质量（供人类参考）：

| 特征 | 示例 |
|------|------|
| 明确目标 | "生成一个能将 Markdown 文档转换为 PDF 的工作流" |
| 领域定位 | "在 demogame 域下" / "在 local 域下测试用" |
| 输出期望 | "最终产物是一个 Python 函数，接受路径返回 PDF 字节" |
| 约束说明 | "不能依赖 LaTeX 环境" |
| 参考案例 | "参考 lang-rewrite 管线的 Format 链设计方式" |
