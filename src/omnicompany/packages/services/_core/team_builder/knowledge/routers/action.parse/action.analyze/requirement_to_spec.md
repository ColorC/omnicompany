---
omnikb_type: krouter
id: "kb.core.requirement_to_spec"
name: "自然语言需求到结构化规格的解析"
tags: []
kformat_in: "kb.core.workflow_requirement"
kformat_out: ""
format_in: "wf.requirement_raw"
format_out: "wf.requirement"
relates_to_routers:
  - ReqAnalyzerRouter
confidence: high
maturity: stable
summary: "将自然语言工作流需求解析为结构化需求规格，提取目标、领域、约束等关键元素。"
---

# 自然语言需求到结构化规格的解析

将用户提供的自然语言工作流描述，通过 LLM 分析提取出结构化的需求规格。这是 `workflow_factory` 管线中责任最重的第一步，其输出质量决定整个工作流的方向。

## 已知成功路径

### 典型 LLM 解析流程

1. **输入预处理**：确认 `text` 字段非空，长度合理（过短则可能是误触发）
2. **LLM 调用**：使用 `_REQ_SYSTEM` 系统 prompt，要求 LLM 提取以下字段：
   - `goal`：一句话描述目标
   - `domain`：所属领域（如 sw / demogame / local / custom）
   - `input_description`：输入数据的语义描述
   - `output_description`：期望输出的语义描述
   - `constraints`：约束条件列表
   - `reference_pipelines`：可参考的现有管线
   - `verification_requirements`：各阶段的验证方式
   - `error_scenarios`：可能的错误场景
   - `needs_user_interaction`：需要用户确认的决策点
3. **JSON 提取**：从 LLM 输出中提取第一个合法 JSON 对象
4. **自评估过滤**：如果 LLM 在输出中标记自身置信度低，进入 PARTIAL 路由

### 关键设计决策

- **REFLECTION_ENABLED=True**：允许 LLM 在输出前自评估，降低低质量结果进入下游的概率
- **UserInquiry 机制**：当 `needs_user_interaction` 非空时，可以暂停流水线向用户追问，而不是用假设继续

## 已知失败模式

| 场景 | 症状 | 处理方式 |
|------|------|---------|
| 输入过于模糊 | LLM 无法从中提取 `goal` 和 `domain` | 返回 PARTIAL，追问用户 |
| LLM 未返回 JSON | 输出为纯文本解释 | `_extract_json_obj()` 失败，返回 FAIL |
| 需求横跨多个领域 | `domain` 字段不明确 | LLM 可能选错，需人工确认 |
| 技术性过强 | 用户直接描述实现细节而非目标 | LLM 可能混淆"实现"和"目标" |

## 与可执行 Router 的映射关系

**对应实现**：`ReqAnalyzerRouter`（位于 `workflow_factory/routers.py`）

该路由器已完整实现，覆盖了"已知成功路径"中描述的全部步骤。
主要系统 prompt 在 `_REQ_SYSTEM` 变量中定义，包含输出格式约定和领域参考列表。

## 决策依据

- 选择 LLM 而非规则解析的原因：自然语言需求的表述方式差异极大，规则解析的覆盖率过低
- 选择 SOFT（LLM）而非 HARD（确定性）节点的原因：无法用代码完整枚举所有合法需求格式
- REFLECTION 机制的引入：避免 LLM 在不确定时"自信地输出错误答案"，改为触发 PARTIAL 路由

## 参考

- `ReqAnalyzerRouter` — 对应可执行实现
- `wf.requirement_raw` — 输入 Format（可执行域）
- `wf.requirement` — 输出 Format（可执行域）
- `kb.core.workflow_requirement` — 输入的知识域描述
