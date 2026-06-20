
# absorption_runtime_test · absorption 类工作的特化测试团队

## 1 · 名称与定位

`absorption_runtime_test` 是 **absorption 类目标团队** (例: `repo-absorption` 产代码改进提案 + 报告) 的特化测试团队.

> ⚠️ **不是知识产物通用模板**. 2026-04-26 L1 审视后明示: 测试本质是**假设法**, 通用假设很少, 大多数有效假设领域+工作特化. 本团队的 3 路验证只覆盖 absorption 一类工作, 不可硬套到其他知识产物 (故事/config_table/UI/决策类等).
> 详细推演见 `docs/plans/[2026-04-26]VERIFICATION-AS-HYPOTHESIS-METHOD/plan.md`. 通用层假设构建在 Phase B/C 立 (真 meta 层).

它不是契约扫描 (那是 team_supervisor 干的事), 而是**真跑 + 多路逼近**: 取样跑目标团队多次, 用 3 条独立路径产证据, 汇总成画像.

立项: 2026-04-26 (旧名 `knowledge_runtime_test`, 2026-04-27 改名 absorption 特化). 沉淀自 [data/domains/test_team/scratch/](../../../../data/domains/test_team/scratch/) 三个 scratch 实验. 完整历程: [journey.md](../../../../../../../data/domains/test_team/scratch/journey.md).

## 2 · 职责

接收 `absorption_runtime_test.target_spec` (target_team_id + sample_input + run_count), 跑出画像 `absorption_runtime_test.portrait`.

具体步骤:
1. 装载 target 元数据
2. 用 sample_input 真跑 target N 次 (subprocess 隔离避嵌套 dispatch async loop 冲突)
3. **路 1 跨次稳定性**: N 次产物文件层 + 主题层重叠 (通用假设, 但 LLM 主题判得严控)
4. **路 3 抽样落地** (absorption 特化): 挑 1-2 条提案, 让 LLM 真写实施代码, 判是否解决 problem. **此路仅适用代码改进提案类**, 套到非可实施产物 (故事/config_table/UI 等) 错
5. **路 4 源覆盖** (absorbing 类特化): 扫 target 输入源仓库, 对照"程序化关键模块清单"看哪些目标团队漏没. 关键模块识别**减少 LLM 自评成分**, 用引用数 + 文件大小作机械排名, LLM 仅在 top-K 候选里选语义关键的子集
6. 装画像: 多维证据汇总 + 自然语言段落 + "做得好/做得不好"两段句子列表

> 旧版**路 2 独立重评**已删除. 2026-04-26 实验显示同模型 LLM 评 LLM 重叠率本质是同框架自评, 没分辨力.

## 3 · 输入与输出

### 3.1 输入 `absorption_runtime_test.target_spec`

- `target_team_id` (str, required): 待测目标团队的注册 id (如 `repo-absorption`)
- `sample_input` (dict, required): 给目标团队真跑用的 input_data (含 `repo_path` 之类源仓库)
- `run_count` (int, default=2, ≥2): 跨次稳定性需 ≥2 次取样
- `spot_impl_count` (int, default=2): 抽样落地的提案数

### 3.2 输出 `absorption_runtime_test.portrait`

按 [feedback_semantic_sentences_not_classification](C:/Users/user/.claude/projects/e--workspace/memory/feedback_semantic_sentences_not_classification.md) 规约: 自然语言句子承载语义证据, 禁打分 / 标签.

字段:
- `verdict` (协议层硬枚举): PASS / PARTIAL / FAIL
- `target_team_id`: 透传
- `evidence_paths` (3 条独立路证据汇总): cross_run / spot_impl / source_coverage
- `portrait_paragraph` (自然语言段落): 总体画像段落 (≥150 字)
- `what_target_does_well` (句子列表): 它做得好的方面 (具体)
- `what_target_misses` (句子列表): 它漏掉的方面 (具体)
- `physical_metrics`: 仅允许物理度量 (run_count / overlap_pct / impl_solves_count 等), 不语义打分

## 4 · 拓扑

```
TargetIngressWorker (entry · HARD)
  ↓
SampleRunsExecutorWorker (HARD · subprocess 嵌套 dispatch · 跑 N 次)
  ↓
  ├──→ CrossRunStabilityVerifierWorker (SOFT · 文件 + 主题重叠)
  ├──→ SpotImplVerifierWorker (AGENT · 挑提案让 LLM 实施 + 判定)
  └──→ SourceCoverageVerifierWorker (AGENT · 扫源 + 看 target 漏没)
            ↓ 3 路 fan-in
       PortraitAssemblerWorker (HARD · 装画像 sink)
```

6 节点, 1 入口 + 1 取样 + 3 验证 (并行) + 1 装配.

## 5 · Material (7 个)

| ID | producer | consumer |
|---|---|---|
| `absorption_runtime_test.target_spec` | 外部 | TargetIngressWorker |
| `absorption_runtime_test.target_metadata` | TargetIngress | SampleRunsExecutor + 3 验证器 |
| `absorption_runtime_test.sample_runs` | SampleRunsExecutor | 3 验证器 |
| `absorption_runtime_test.cross_run_evidence` | CrossRunStabilityVerifier | PortraitAssembler |
| `absorption_runtime_test.spot_impl_evidence` | SpotImplVerifier | PortraitAssembler |
| `absorption_runtime_test.source_coverage_evidence` | SourceCoverageVerifier | PortraitAssembler |
| `absorption_runtime_test.portrait` | PortraitAssembler | sink |

## 6 · 边界与约束

### 6.1 真跑非静态

按 L1 明示: 验证必须真跑, 不是静态契约扫. 3 条验证路全有实跑成分:
- 路 1: SampleRunsExecutor 真 dispatch 目标 N 次 (subprocess)
- 路 3: 真调 LLM 写代码
- 路 4: 真扫 target 输入源仓库

### 6.2 多路不互相依赖

3 条路独立产证据, 任一路出问题不影响其他路 (PortraitAssembler 容错 — 缺一路则该路 evidence 标 unavailable, 仍出画像).

### 6.3 反模式禁令

按 [feedback_semantic_sentences_not_classification](C:/Users/user/.claude/projects/e--workspace/memory/feedback_semantic_sentences_not_classification.md):
- 画像字段全自然语言句子
- 禁 score / level / tier / tags 字段
- 仅允许物理度量 (count / pct / time)

按 [feedback_validation_calibration_red_green_gradient](C:/Users/user/.claude/projects/e--workspace/memory/feedback_validation_calibration_red_green_gradient.md):
- 测试团队必须自带红绿基线 (放在 scratch 校准脚本里, 不阻塞主路)

按 [feedback_test_is_hypothesis_method](C:/Users/user/.claude/projects/e--workspace/memory/feedback_test_is_hypothesis_method.md):
- 本团队 3 路 = 3 个针对 absorption 特化的假设打包, **不是知识产物通用模板**
- 路 3 (可执行) 只适用代码改进提案. 套到故事/config_table/UI 等非可实施产物, 是错的抽象层级
- 路 4 (源覆盖) 只适用 absorbing 类 (从外部源仓库提产物). 适用面比路 1/3 都窄
- 真通用层在 hypothesis_library + 真 meta 层 (Phase B/C)

### 6.4 嵌套 dispatch 的 subprocess 隔离

`SampleRunsExecutorWorker` 用 subprocess 跑目标 dispatch. 因为外层 (absorption_runtime_test 自己) 跑在 async loop 内, 直接 asyncio.run() 会冲突. 复用 [team_supervisor/routers/dispatch_team.py](../../../_core/team_supervisor/routers/dispatch_team.py) 的 subprocess 模式.

### 6.5 适用产物类型

仅适合 **absorption 类工作** (目标团队从外部源仓库读源码 + 产代码改进提案/吸纳分析报告):
- ✅ repo_absorption (代码改进提案 · 立项原型)
- ⚠️ repo_architect (仓库架构报告 · 部分适用 — 路 3 大概率不适用)
- ❌ csv_to_md (代码产物 · 有 ground truth · 走 byte-diff)
- ❌ team_builder (代码产物 · 走编译跑测试)
- ❌ 故事生成 / config_table / UI / 决策类 (无 ground truth 但路 3 不适用)

非 absorption 的"知识产物"测试待真 meta 层针对生成假设 (Phase B/C).

## 7 · 假设清单 (按 §假设法 沉淀)

| 路 | 假设 | 怎么验 (本团队当前实施) | 通用性 |
|---|---|---|---|
| 路 1 | 同输入跨次产物 (文件层 + 主题层) 高重叠 → 团队稳定 | 文件 set 真重叠 (程序化) + LLM 判主题层 | **通用** (大多数产物适用) |
| 路 3 | 提案可被 LLM 真写出实施代码 → 提案具体 | LLM 读源码写实施 + 二轮 LLM 判 truly_solves | **absorption 特化** (代码改进提案适用; 套故事/config_table错) |
| 路 4 | target 摸过的关键模块 / 程序化排名候选关键模块 重叠高 → 视野全 | 引用数 + LOC 排名 top-K (程序化) → LLM 在候选里选 5-10 → 对照 target 摸过 | **absorbing 特化** (target 必须消费 repo_path; 不消费时 applicable=false) |

3 条假设独立, 任一通过不能证明 target 健康, 任一失败给信号. 综合 portrait 装配规则 ≥2/3 路过 → PARTIAL, 3/3 → PASS.

## 8 · 未决与未来

- **路 5 跨模型**: 用不同模型 (qwen vs claude vs gpt) 跑 target, 看是否 model-dependent. 当前略
- **试管中真改 target 仓库**: 路 3 现在只让 LLM 写 diff 不真改文件. 未来可在 worktree 隔离环境真改 + 跑 target 现有测试
- **画像稳定性**: 同 target 跑两次 absorption_runtime_test, 画像应一致 (路 3 用 LLM, 有抖动). 待验
- **梯度的进阶定义**: 当前画像段落 + 做得好/漏 两列表, 未细分"做得很好/特别好" 等档. 实跑多个 target 后再看是否需要更细
- **跨 absorption 子类型适用性**: 当前主要在 repo-absorption 上证. 跑 repo-architect 时是否需要为 architect 子拆出特化路? 留 Phase D
