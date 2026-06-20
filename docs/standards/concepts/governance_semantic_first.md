<!-- [OMNI] origin=claude-code domain=standards/concepts ts=2026-06-13T08:00:00Z type=standard status=active -->
<!-- [OMNI] summary="治理方法原则 — 语义判断优先用性价比模型 agent, 规则脚本是批量规律的结晶, 不是语义判断的首选" -->
<!-- [OMNI] why="2026-06-13 用户裁决: OMNI-093 用脆弱字符串匹配做语义判断(权威漂移), 措辞一变就漏/无关文档误报。规则不该承担语义判断; 那是性价比模型 agent 的活" -->
<!-- [OMNI] tags=standards,governance,agent_first,llm_first,rules,semantic -->
<!-- [OMNI] material_id="material:standards.concepts.governance_semantic_first.md" -->

# 治理方法: 语义判断优先用性价比模型 agent

> **权威**: 本文件。**触发**(用户, 2026-06-13): "Omnicompany 应当考虑用性价比模型驱动的
> agent 进行语义判断为主, 后续发现批量操作规律了再进一步落地成规则脚本。"
> 跟 [`agent_first.md`](agent_first.md) / [`_global/llm_first.md`](../_global/llm_first.md) 同源, 本文是它们在**治理/守卫**场景的具体落点。

## 一 · 原则

凡涉及**语义判断**的治理(权威是否漂移、规范是否过期、文档是否自相矛盾、归属是否正确),
**首选性价比模型 agent**(deepseek-v4-pro / glm-5.1, 走 [`runtime/llm/structured.py`](../../../src/omnicompany/runtime/llm/structured.py) 的统一调用面)。
**确定性规则脚本(如 guardian rules)是"批量规律的结晶", 不是语义判断的首选。**

判据 — 一个检查该是规则还是 agent?

| 维度 | 用确定性规则 | 用性价比模型 agent |
|---|---|---|
| 判断性质 | 字面/结构(文件在不在、状态枚举、锚点字串在不在) | 语义(意思变没变、是否过期、是否冲突、是否另立权威) |
| 措辞鲁棒性 | 不依赖具体措辞 | 换种说法仍要判对 |
| 误报代价 | 几乎不误报 | 字符串匹配会因无关文档命中而误报 |
| 沉淀时机 | **已观察到稳定批量规律**后, 把规律固化成规则 | 规律未明 / 语义空间大时 |

## 二 · 反模式(2026-06-13 实例)

OMNI-093d 曾用"讨论了收束概念 + 出现权威词 + 没有锚点 → 违规"的字符串启发式判断"权威漂移"。
问题: ① 任何无关文档偶然提到那几个词就误报; ② 把权威文档换种说法重写, 字串没了, 规则**静默判过**——
本该拦的漂移恰恰溜过去。**这是用规则做语义判断的典型失败。**

裁决后的形态:
- OMNI-093a/b/c/d **降为确定性兜底**: 只查特定文件里特定标记在不在; content 不可读时不判定(不凭空误报)。
- 全面的**权威漂移 / 规范时效性语义判断**交给治理部门 [`doc_steward`](../../../src/omnicompany/packages/services/_governance/doc_steward/)(性价比模型)**为主**。

## 三 · "后续发现批量规律再落地成规则"的回路

性价比模型 agent 跑出的 findings 会暴露**反复出现的同型问题**。当某类问题:
1. 在多轮治理里稳定复现(批量规律明确), 且
2. 可用确定性信号无歧义地捕获(不依赖语义),

就把它从 agent 判断**结晶**成一条确定性规则(guardian rule 或脚本), 让便宜且不误报的规则接管这部分,
agent 腾出来judge更难的。**规则是 agent 判断沉淀下来的产物, 不是它的替代或前置。**

## 四 · 适用范围

- 治理部门(`_governance`): plan 归属、工作历史、**文档/规范时效性**(doc_steward)全部按本原则。
- 守卫(`guardian`): 结构/字面规则保留; 语义类检查不新增进 rules, 改提案给对应 steward。
- 任何"要不要新写一条规则做 X 判断"的决定: 先问 X 是不是语义判断 — 是, 默认走 agent。
