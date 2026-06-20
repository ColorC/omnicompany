
# hypothesis_library · 假设库 (库模块, 非 team)

## 1 · 名称与定位

`hypothesis_library` 是 **Phase B 沉淀的假设候选库**, 给真 meta 层 (Phase C `runtime_test_builder` 重构后) 当原料.

**它不是 team** (无 build_team / build_bindings). 它是个 **库模块** — 提供两类数据 + 查询 helper:
1. **通用假设候选清单** (`universal_hypotheses.py`): 跨大多数产物可能适用的"地基假设" (4 条候选, 待跑多 target 校准)
2. **现成模式清单** (`patterns.py`): 从 OmniCompany 现有团队 (csv-to-md / repo_absorption / doctor / guardian / lap_auditor) 提取的可复用验证模式 (5 条)

> ⚠️ 通用假设是**候选**, 不是定论. 跑多类产物校准后可能修订 (新增 / 删除 / 改适用条件). 详见 [feedback_test_is_hypothesis_method](C:/Users/user/.claude/projects/e--workspace/memory/feedback_test_is_hypothesis_method.md).

立项: 2026-04-27 · Phase B 沉淀 · 来龙去脉见 `docs/plans/[2026-04-26]VERIFICATION-AS-HYPOTHESIS-METHOD/plan.md` §6.2.

## 2 · 职责

```
hypothesis_library
   ├── universal_hypotheses.py · 4 条候选地基假设
   ├── patterns.py · 5 条现成验证模式
   └── __init__.py · 统一导出 + 查询 helper

下游消费者 (Phase C 立):
   runtime_test_builder.HypothesisProposerWorker
     └── 综合 target 探包 + 通用假设清单 + 现成模式
         → 当场针对 target 生成 N 条特化假设 (含可证伪方式)
```

## 3 · 输入与输出

### 3.1 数据类型

`Hypothesis` (dataclass, frozen):
- `id` (str): 唯一 id, snake_case
- `description` (str): 一句话主张 (自然语言句子, 非分类码)
- `when_applicable` (str): 适用条件 (自然语言, 描述什么 target 该用)
- `verification_template` (str): 验证方式模板 (自然语言, "怎么程序化判")
- `examples` (list[str]): 具体例子 (各产物形态怎么用此假设)
- `category` (str): 分类标签 (`universal` / `pattern`)
- `provenance` (str): 来源 (哪条 memory / 哪个 team 提取)

### 3.2 模块级常量

- `UNIVERSAL_HYPOTHESES`: list[Hypothesis] · 4 条候选
- `PATTERNS`: list[Hypothesis] · 5 条现成模式
- `ALL_HYPOTHESES`: 上述合并

### 3.3 Helper 函数

- `find_by_id(hyp_id: str) -> Hypothesis | None`
- `filter_by_category(category: str) -> list[Hypothesis]`
- `render_for_prompt(hyps: list[Hypothesis]) -> str`: 渲染成给 LLM 看的 markdown 段子

## 4 · 拓扑

**N/A** — 库模块, 无管线拓扑.

## 5 · Material

**N/A** — 库模块, 不参与 dispatch (无 Material 注册).

## 6 · 边界与约束

### 6.1 库定位

- 不是 team (无 dispatch 能力)
- 不入 PipelineRegistry
- 不在 core/pipelines.py 注册
- Phase C 真 meta 层 worker 直接 import 此模块拿数据

### 6.2 反模式禁令

按 [feedback_semantic_sentences_not_classification](C:/Users/user/.claude/projects/e--workspace/memory/feedback_semantic_sentences_not_classification.md):
- description / when_applicable / verification_template 全自然语言句子
- 禁 score / level / tier 字段
- category 是分类标签, 但仅用于内部分组 (universal vs pattern), 不做语义判定

按 [feedback_test_is_hypothesis_method](C:/Users/user/.claude/projects/e--workspace/memory/feedback_test_is_hypothesis_method.md):
- 通用假设少, 当前 4 条仅是**候选**, 待校准
- 真 meta 层应基于 target 现场生成假设, 不是固定模板套
- 本库是**候选起点**, 不是**必用清单**

### 6.3 现成模式来源

模式条目从已跑通的现成验证团队提取, 记录其有效性边界:
- csv-to-md byte-diff (代码产物有 GT 时通用)
- repo_absorption ReportAssembler 引用真实性 (任何带文件引用的产物)
- doctor 五要素 (Material 健康)
- guardian 卫生 (目录/文件规范)
- lap_auditor 红线 (硬性禁令)

### 6.4 不做"分级"

不区分"高优先级假设"或"低优先级假设". 让真 meta 层基于 target 做判断, 不替它定级.

### 6.5 假设的"材料维度"分类 (给下游调度员复合 agent 用)

L1 2026-04-29 立: 假设除了"通用/模式/特化"分类, 还有更实用的另一个维度 — **它要看什么材料才能验**. 下游调度员按这个维度分组用同一个 agent 复合判, 比每档独立跑工具高效.

每条假设隐含一种或多种材料需求:

| 假设 id | 主要材料 |
|---|---|
| `stable` | 跨次产物对比 (跑 N 次取样的产物 set 对比) |
| `honest` | 跑出来的产物本身 (扫产物里的引用是否真存在) |
| `robust` | 错误输入响应 (喂错误输入跑目标看 verdict) |
| `observable` | 运行 trace (events.db 事件序列) |
| `byte_diff_acceptance` | 跑出来的产物 + 标杆样本 |
| `reference_existence` | 跑出来的产物 + 目标源仓库 |
| `five_element_check` | 目标包源代码 (formats.py 等) |
| `directory_hygiene` | 目标包源代码 + 文件系统 |
| `red_line_check` | 目标包源代码 |

**直接推论**: `five_element_check` + `directory_hygiene` + `red_line_check` 三档主材料都是目标源代码 → 应给同一个 SourceCodeAuditAgent 一次扫一遍同时判三档.

详见 `runtime_test_builder/DESIGN.md` §6.4.

## 7 · 未决与未来

- **校准**: 跑多类产物后, 4 条通用假设可能修订 (新增 / 删除 / 改适用边界). 留 Phase D 实验数据驱动
- **5 条现成模式不够**: voxel_engine 的 worldgen 假设 / gameplay_system 的 csv diff 假设 / chat_platform-cli 的协作平台 API 假设等都待沉淀. 留 Phase D+
- **假设之间依赖**: 当前各假设独立列. 真 meta 层可能需要识别"假设依赖图" (如"诚实"是"覆盖"的前提). 留 Phase C 实施时见
- **可证伪方式跨语言**: 当前 verification_template 都是自然语言. 进 Phase C 后可能需要让模板带"程序化骨架" (像 pytest fixture) — 进一步的离散度. 留 Phase C+
