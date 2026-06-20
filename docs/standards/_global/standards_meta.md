
# 立规范的元规范

> **状态**: 元规范 v1 (2026-05-06)
> **作用域**: 跨所有 omnicompany 规范文档. 立**任何**新规范前必过这两条
> **关联**: [`single_source_thin_wrap.md`](single_source_thin_wrap.md) (跨目录"源/薄包装" 关系) / [`distributed-docs.md`](distributed-docs.md) (规范放哪)

---

## 一 · 用户原话 (2026-05-06)

> "如果你要尝试去树立规范, 两个是必须要做的:
> 1. 唯一权威源原则: 不要搞两套, 更不要搞矛盾的两套, 也不要和已有其他内容矛盾
> 2. 确保至少有一个完全符合规范 (不是避开规范, 是符合规范) 的样本
>
> 好的, 这是一条元规范."

---

## 二 · 两条硬底线

### 第 1 条 · 唯一权威源原则

立新规范前必检查:

1. **不搞两套**: 同一概念的规则不出现在两份规范文档里. 重叠主题 → 合并 / 引用而不复制
2. **不搞矛盾的两套**: 新规范跟现存 omnicompany 的任何规范 (`docs/standards/` 全部子目录) 跟任何 plan / DESIGN.md / 用户立过的硬规则**不冲突**
3. **不跟已有内容矛盾**: 现存代码里的实际做法 / 命名 / 协议跟新规范一致 — 立规范不是脱离现状画大饼, 是把已生效或将生效的实践显化成文

冲突时优先级: 用户立的硬规则 > 已有规范文档 > 已有代码实践 > 新规范草稿. 反向冲突 = 新规范要改, 不是去改已有.

> 跟现存 [`single_source_thin_wrap.md`](single_source_thin_wrap.md) 关系: 那一份解决跨**目录**的"源/包装"; 本条解决跨**文档**的"重复/矛盾". 互补.

### 第 2 条 · 至少一份真合规样本

立新规范必同时提供:

1. **真存在**: 样本是仓库内一份具体的真实文件, 不是"参见某文" 这种空指针
2. **完全符合**: 把样本拿规范条款逐条对, **每条都满足**. 不是"基本符合" 不是"主要部分符合"
3. **不是避开**: 不允许靠"挑了个不会触发规范的小例子"取巧 (例 plan_template 要求一-七节齐, 样本不能只是个 README 假装 plan)
4. **公开链接**: 在规范文档里直接 link 到样本路径, 让读者一键跳

样本作用:
- 真锚点: 看不懂规范条款时直接看样本就懂
- 防退化: 改规范前必须同步改样本, 不一致是规范出问题信号
- 自检: 样本通不过规范关联的诊断 / lint = 规范本身有 bug 不能立

---

## 三 · 立规范前自检 checklist (落实两条)

写新规范文档前必走:

```
[ ] 1.1 现 docs/standards/ 全扫一遍, 同主题文档清单 (有几份)
[ ] 1.2 跟用户立过的硬规则 / 现存代码实践对照, 列冲突点
[ ] 1.3 冲突点逐条决策: 合并 / 引用 / 撤新规范 / 改已有 (后者很罕见)
[ ] 1.4 决策落到新规范文档的"跟其他规范的关系"节
[ ] 2.1 想清楚合规样本应该长什么样 (列规范条款 → 样本要满足什么)
[ ] 2.2 真去找 / 真去写一份合规样本 (不是后续再补)
[ ] 2.3 拿样本逐条对规范, 每条都过. 不过的修样本 / 修规范一直到匹配
[ ] 2.4 样本路径 link 进规范文档"样本"节, 注 "本样本逐条符合本规范, 修规范前必同步改样本"
[ ] 2.5 (有 doctor 诊断器对应时) 跑诊断器对样本, 应得"全合规" 结果. 不全合规 = 规范跟样本对不齐, 立规范失败
```

---

## 四 · 现存规范的合规样本配套清单 (待补 / 已配)

> 元规范 v1 立时回头查 — 现 standards 各份是否都有合规样本.

| 规范 | 合规样本 | 状态 |
|---|---|---|
| [`protocol/design_md_template.md`](../protocol/design_md_template.md) (从属三件套规范) | [`csv_to_md/DESIGN.md`](../../../src/omnicompany/packages/services/_utility/csv_to_md/DESIGN.md) (六必需节齐 — 状态/核心接口/架构决策/数据流-拓扑/已知局限/参考资料; 2026-06-13 起核心目的归 README, 样本残留核心目的不违规) | 配 (2026-05-06 验; 2026-06-13 随规范切换更新口径) |
| [`protocol/plan_template.md`](../protocol/plan_template.md) | [`docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/samples/sample_compliant_plan_exemplar_library.md`](../../plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/samples/sample_compliant_plan_exemplar_library.md) | 配 (2026-05-06 立, 跟元规范一起诞生; PlanDiagnosticAgent dogfood 验收 4 finding 全正面) |
| [`protocol/l2_session_summary_protocol.md`](../protocol/l2_session_summary_protocol.md) | [`compact_summary_2026-05-05.md`](../../plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/compact_summary_2026-05-05.md) (4.1.1-4.8 八项 checklist 齐 + 附录) | 配 (2026-05-06 验) |
| [`protocol/self_creative_content_three_files.md`](../protocol/self_creative_content_three_files.md) | [`docauthor/`](../../../src/omnicompany/packages/services/_authoring/docauthor/) (含 README + SKILL + DESIGN 三件套齐) | 配 (2026-05-06 候选, 待逐条对规范 2.5 项验) |
| [`concepts/worker.md`](../concepts/worker.md) | [`csv_reader.py`](../../../src/omnicompany/packages/services/_utility/csv_to_md/workers/csv_reader.py) (E-worker-csv_reader-2026-05-05 yaml) | 配 (跟样例库共享, doctor.exemplar 实例) |
| [`concepts/material.md`](../concepts/material.md) | [`E-material-doctor_exemplar-2026-05-06.yaml`](../../plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/samples/sample_exemplar_E-material-doctor_exemplar-2026-05-06.yaml) (DIAG_EXEMPLAR Material 自身, 自指演示) | 配 (2026-05-06) |
| [`concepts/team.md`](../concepts/team.md) | [`E-team-csv_to_md-2026-05-06.yaml`](../../plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/samples/sample_exemplar_E-team-csv_to_md-2026-05-06.yaml) (csv_to_md HARD 端到端 Team) | 配 (2026-05-06) |
| [`concepts/agent_first.md`](../concepts/agent_first.md) | [`E-agent-spec_diagnostic-2026-05-06.yaml`](../../plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/samples/sample_exemplar_E-agent-spec_diagnostic-2026-05-06.yaml) (SpecDiagnosticAgent ConfigurableAgent 子类典型) | 配 (2026-05-06, 跟 agent_tools 共享) |
| [`concepts/agent_tools.md`](../concepts/agent_tools.md) | 同上 (P-3 yaml — SpecDiagnosticAgent 工具集 6 个 ≤10 + bash 主, 跟 agent 工具集铁律一致) | 配 (跟 agent_first 共享) |
| [`concepts/plan.md`](../concepts/plan.md) | 同 plan_template 合规样本 (concept 层 + protocol 层共享同一份样本, 实例既是 plan 概念实例又是 plan_template 模板实例) | 配 (2026-05-06) |
| [`concepts/template.md`](../concepts/template.md) | — | 待找 (template 是抽象规范, 样本应是一组按 template 实例化产出的具象产物, 待评估) |
| [`concepts/workspace.md`](../concepts/workspace.md) | [`csv_to_md/.omni/workspace.yaml`](../../../src/omnicompany/packages/services/_utility/csv_to_md/.omni/workspace.yaml) | 配 (2026-05-06 候选, 待逐条对规范验) |
| `concepts/hook.md` | — | 规范本身未立, 待立后回头配样本 |
| `concepts/tool.md` | — | 规范本身未立; 现有 [`agent_tools.md`](../concepts/agent_tools.md) 是 agent 工具集铁律, 不是 tool kind 概念规范 |
| 各 `_global/` 全局规范 | — | 这类一般没单一对象样本, 用条款例子代替 (例 [`single_source_thin_wrap.md`](single_source_thin_wrap.md) 用具体目录跟 SKILL 文件作例) |

待补的合规样本跟 doctor.exemplar 库 (`data/services/doctor/exemplars/`) 是同一件事 — **每条规范的合规样本就是该 kind 的 exemplar 实例**, ExemplarDiagnosticAgent 用它做对照.

> 收尾状态 (2026-05-06): 现存 concepts + protocol 共 12 份规范, 9 份已配合规样本 ✓, 2 份候选待逐条验 (self_creative_content / workspace), 1 份样本类型待评估 (template), 2 份规范本身未立 (hook / tool). 元规范第 2 条覆盖度 75% (9/12).

---

## 五 · 反例 (历史教训, 立此元规范的触发场景)

**plan_template.md 立时违反第 2 条**:

我 (AI IDE) 2026-05-05 立 plan_template.md 时, §五 写"合格例: 本计划用的 plan.md". 当晚跑 PlanDiagnosticAgent dogfood 用 plan_template 诊断本计划, LLM 准确指出本计划用"用户决策清单 / 现状摸底速记" 等节名跟模板的"一 需求清单 / 二 产物清单 / 三 验收标准" 不对应, 6 处 finding.

也即: 我立规范的同时推荐了一份**反例**作合规样本. 读者按"合格例"学 → 学到的是反规范的写法.

教训:
- 立规范前应先有合规样本, 不能"边立规范边找样本"
- 没合规样本前规范应标 status=draft, 不能 active
- 元规范 v1 把这条上升为立规范者的硬底线, 防再犯

---

## 六 · 实施

立元规范当天 (2026-05-06):
1. 修 plan_template.md §五 (撤"本计划是合格例" 错指, 改指真合规样本)
2. 立第一份真合规 plan.md 样本 (sample_compliant_plan_exemplar_library.md, 跟元规范同生)
3. 跑 PlanDiagnosticAgent dogfood 验合规样本应得"全合规" 结果 (元规范第 2 条第 2.5 项)
4. 这之后任何新立规范都过元规范 §三 checklist
