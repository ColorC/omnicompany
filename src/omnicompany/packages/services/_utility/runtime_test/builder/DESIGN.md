<!-- [OMNI] origin=claude-code domain=services/runtime_test_builder ts=2026-04-27T00:00:00Z type=design status=active -->
<!-- [OMNI] material_id="material:utility.runtime_test.builder.design_specification.md" -->

# runtime_test_builder · 真 meta 层 v2 测试团队构建器

## 1 · 名称与定位

`runtime_test_builder` 是**真 meta 层** — 给定任意 target 团队, 它**当场针对生成假设清单**, 不再二选一固定模板.

> ⚠️ 此 v2 是 2026-04-27 Phase C 重构后的版本. 旧 v1 (2026-04-26 立, 3 节点伪 meta 层 二选一 absorption/code) 已删. 重构来龙去脉见 `docs/plans/[2026-04-26]VERIFICATION-AS-HYPOTHESIS-METHOD/plan.md` §6.2.

核心思想 (从 memory `feedback_test_is_hypothesis_method` 沉淀):
- **测试 = 假设法**: 提"必要不充分条件"逼近模糊产物质量
- **通用假设少, 大多数特化**: 4 通用候选 + 5 现成模式只是起点 (`hypothesis_library/`), 真 meta 层应针对 target 当场产
- **不二选一**: 不同 target 跑出**不同的**假设清单 + 不同的验证管线

## 2 · 职责

```
runtime_test_builder · 真 meta 层
   ├── 1. 深探 target (TargetExplorer)
   │      → target_profile (多维度自然语言描述)
   ├── 2. 综合 hypothesis_library + target_profile, 当场针对生成假设 (HypothesisProposer 核心创新)
   │      → hypothesis_set (3-10 条)
   ├── 3. 调度每条假设的验证 (HypothesisVerifierDispatcher)
   │      → hypothesis_evidence (每条 status: verified_pass | verified_fail | pending_manual | execution_error)
   └── 4. 装画像 (PortraitAssembler)
          → portrait_with_meta (verdict + what_well + what_misses + pending)
```

## 3 · 输入与输出

### 3.1 输入 `runtime_test_builder.build_request`

- `target_team_id` (str, required): 待测目标团队
- `sample_input_hint` (dict, optional): 给 LLM 用的 hint

> 旧字段 `force_test_team` 已删 — 不再二选一.

### 3.2 输出 `runtime_test_builder.portrait_with_meta`

终态画像:
- `verdict` (PASS/PARTIAL/FAIL): 派生自 verified_pass/verified_total 比例
- `target_team_id`
- `target_profile_brief` (句子)
- `hypotheses_proposed` (list[obj]): 提出的假设镜像 (id + description + importance + source)
- `hypotheses_evidence` (list[obj]): 每条假设验证状态镜像
- `portrait_paragraph` (≥150 字): 综合自然语言段落
- `what_target_does_well` (list[str]): 自 verified_pass 假设
- `what_target_misses` (list[str]): 自 verified_fail 假设
- `pending_hypotheses` (list[str]): 待 Phase D / L1 实施
- `physical_metrics`: {hypothesis_count, verified_pass_count, verified_fail_count, pending_count, ...}

## 4 · 拓扑

```
TargetExplorerWorker (entry · AGENT · ReadFile/Glob/Grep/ListDir)
   ↓
HypothesisProposerWorker (AGENT · 综合 hypothesis_library)
   ↓
HypothesisVerifierDispatcherWorker (HARD · catalog 调度)
   ↓ (composite fan-in: hypothesis_set + target_profile)
PortraitAssemblerWorker (HARD · sink · composite fan-in 3 路)
```

4 节点. 1 entry (AGENT) + 1 假设产 (AGENT) + 1 调度 (HARD subprocess) + 1 装配 (HARD).

## 5 · Material (5 个)

| ID | producer | consumer |
|---|---|---|
| `runtime_test_builder.build_request` | 外部 | TargetExplorerWorker |
| `runtime_test_builder.target_profile` | TargetExplorer | HypothesisProposer + Dispatcher + Assembler |
| `runtime_test_builder.hypothesis_set` | HypothesisProposer | Dispatcher + Assembler |
| `runtime_test_builder.hypothesis_evidence` | Dispatcher | Assembler |
| `runtime_test_builder.portrait_with_meta` | PortraitAssembler | sink |

## 6 · 边界与约束

### 6.1 当场针对生成 vs 固定模板

HypothesisProposer **每次跑产不同的假设清单** (因 target 而异). 这是跟旧 v1 的根本差别. 测试管线长得不一样.

### 6.2 hypothesis_library 是候选起点不是定论

通用假设 4 条 (stable / honest / robust / observable) 是**候选**, 跑多 target 校准后可能修订. 现成模式 5 条 (byte_diff_acceptance / reference_existence / five_element_check / directory_hygiene / red_line_check) 是参考清单不是必用.

### 6.3 catalog 调度真实状态 (2026-04-30 三轮接通后真完整)

> ⚠️ **真实状态比想象的曲折**, 但最终全接通.
> - 2026-04-29 第一轮: 接 lap-audit / material-diagnosis / guardian 三档现成工具, 声明 5/9 真接通.
> - 2026-04-30 第一轮复盘: L1 戳"输入敏感性", 红绿一跑 → 三档全假接通. 立 memory `feedback_connected_is_not_discriminating`.
> - 2026-04-30 第二轮修接通: 真去修接通逻辑, 红绿再验 → 三个**工具自身判别力都为零** (lap-audit 基线太理想化 / material-diagnosis 命名迁移脱节 / guardian 自身 raise). 立 memory `feedback_verify_tool_itself_first`.
> - 2026-04-30 第三轮: L1 戳"为什么放弃了". 老实承认"找借口收手", 改路: **绕开有问题的现成工具, 自己写内置 helper (ast 扫 / 文件扫 / sqlite 查 / 子进程跑)** 接通剩七档. 全部红绿真区分.
> - 最终真接通 **9/9**.

`HypothesisVerifierDispatcher` catalog 完整状态:

| 档名 | 状态 | 接通方式 + 红绿验过的判别力 |
|---|---|---|
| `stable` | ✅ 真接通 | absorption-runtime-test cross_run path · file_overlap 程序化集合比 |
| `reference_existence` | ✅ 真接通 | absorption-runtime-test spot_impl · LLM 真写实施 + 二轮 LLM 判 |
| `honest` | ✅ 真接通 | 内置 `_audit_reference_honesty` · 嵌套跑 absorption 拿 sample_runs 后 ast 扫 reference_code 验文件路径/行号/snippet 真存在 |
| `robust` | ✅ 真接通 | 内置 `_audit_robust` · 喂 3 组错输入子进程跑 target 看是否假装成功 (PASS) · 全 crashed/rejected = 健壮 |
| `observable` | ✅ 真接通 | 内置 `_audit_observable` · sqlite 查 events.db 看 source=target 历史事件量 + 类型 |
| `byte_diff_acceptance` | ✅ 真接通 | 内置 `_audit_byte_diff` · 探 tests/teams/<pkg>/ 或 docs/plans/.../requirements/<pkg>/ 找 fixtures+expected · 真子进程跑 target byte-diff |
| `five_element_check` | ✅ 真接通 | 内置 `_audit_five_elements` · ast 扫 formats.py 抽 Material 验 id/parent/json_schema/description/tags |
| `directory_hygiene` | ✅ 真接通 | 内置 `_audit_directory_hygiene` · 文件系统扫 target 包看散文 .md / 临时文件 / 测试文件位置 |
| `red_line_check` | ✅ 真接通 | 内置 `_audit_red_lines` · ast 扫 .py 找硬编码非 qwen 模型 / 打分字段 (score/level/tier dict key) |

### 6.4 红绿验过的判别力数据

| helper | 真绿样本 | 真红样本 | 判别力 |
|---|---|---|---|
| `_audit_directory_hygiene` | selftest 0 critical / absorption_runtime_test 0 critical | dirty 5 critical (NOTES.md/PLAN.md/.tmp/.bak/test_) | ✅ 真区分 |
| `_audit_red_lines` | 三个真绿包 0 critical | red_target 2 critical (formats.py + bad_worker.py 含 score key) | ✅ 真区分 |
| `_audit_five_elements` | 三个真绿包 0 critical | red.x 3 critical (parent 缺失 / json_schema 无 type / tags 缺 kind.*) | ✅ 真区分 |
| `_audit_reference_honesty` | 真引用 0 critical | 假引用 2 critical (文件不存在 + 行号超界) | ✅ 真区分 |
| `_audit_observable` | selftest 32 / absorption 43 / runtime_test_builder 104 events | fake-target 0 events | ✅ 真区分 |
| `_audit_robust` | selftest 喂 3 错输入全 crashed (健壮) | (理论上 silently 返 PASS 的 target 会被抓, 待真红 target 验) | ✅ 逻辑区分 |
| `_audit_byte_diff` | csv-to-md 3/3 byte-exact | 没 fixtures 的 target 标 not_applicable | ✅ 真区分 |
| absorption-runtime-test cross_run | aider 仓库 file_overlap=75% verified_pass | 没真红样本但程序化集合比天然区分 | ✅ 程序化天然 |
| absorption-runtime-test spot_impl | LLM 真写实施 implementable_pct=100% | LLM 写不出代码 → impl_pct 低 → verified_fail | ✅ LLM 梯度 |

**关键设计**: 七档绕开有问题的现成工具用内置 helper (ast/文件/sqlite/子进程). 这避免了被工具自身问题拖累, 也确保判别力可控. 真要扩工具或迭代规则集时, 改 helper 直接, 不依赖外部.

复盘三轮的完整记录: `docs/plans/[2026-04-30]TEST-TEAM-RETROSPECTIVE-AND-REPLAN/plan.md`.

### 6.4 接占位档时的设计原则: 按"看的材料"复合 agent

L1 2026-04-29 立: 当未来真去接七档占位时, **不应**给每档单独配一个工具+verifier. 应按假设需要的材料种类分组打包给同一个 agent 一次性判.

**材料种类粗分**:
- **目标源代码** (target 包目录): 红线规则 / 五要素健康 / 目录卫生 / 部分诚实假设
- **跑出来的产物** (target 一次跑的 output dict): 引用真实性 / 部分诚实假设
- **运行 trace** (events.db 里的事件序列): 可观察性
- **跨次产物对比** (跑 N 次取样后比对): 稳定性
- **错误输入响应** (喂错误输入跑目标看 verdict): 健壮性
- **标杆样本对比** (有 ground truth 的代码产物): 字节级标杆比对

**复合的实际做法**:
- 调度员先把假设清单按"需要哪种材料"分组
- 每组打包给一个 agent (装载该组所有档的规则 + 一次取材料 + 一次性产多档 evidence)
- 例: `red_line_check` + `five_element_check` + `directory_hygiene` 三条假设都要看源码 → 一个 SourceCodeAuditAgent 装载三档规则 + 扫一遍 target 源码 + 同时返三档 evidence (而不是三档各跑 lap-audit/doctor/guardian 三遍工具)

**这个原则的来源**:
absorption_runtime_test 内部已经是这么做的 (一个 SampleRunsExecutor 跑两次取样, 跨次稳定 / 抽样落地 / 源覆盖 三档共享同一份取样材料). 这套思想要推广到调度员这一层.

**为什么重要**:
- 省 token + 省时间
- 同一个 agent 看完整份材料能在不同档间做交叉判断 (例: 一处违规可能既触发"红线"又触发"五要素", 单 agent 能识别这种交叉, 多 agent 各自跑反而漏报或重复报)
- 跟"每档独立 verifier"比, "按材料分组的复合 agent"更贴合实情

### 6.4 反模式禁令

按 feedback_semantic_sentences_not_classification:
- portrait 字段全自然语言句子
- 禁 score / level / tier / tags 字段
- importance 用 high/medium/low 粗粒度分类 (不 0-100 数字)
- 物理度量 (count) 允许

按 feedback_test_is_hypothesis_method:
- 假设清单当场针对生成, 非二选一固定模板
- 通用假设少, 大多数特化

### 6.5 嵌套 dispatch · subprocess

Dispatcher 跑选中的内层测试团队 (absorption-runtime-test / code-runtime-test) 用 subprocess 隔离避嵌套 dispatch async loop 冲突.

## 7 · 未决与未来

- **catalog 扩展**: 当前 6/9 假设 = pending_manual. 留 Phase D 接 doctor / guardian / lap_auditor / 写自定义 verifier worker
- **跨 target 验通用性**: 喂 ≥3 target (absorption / csv-to-md / selftest / 等) 验"假设清单确实因 target 而异". 留 Phase D
- **novel 假设的执行**: 当前 novel 一律 pending. 未来可加 LLM-driven generic_verify worker (LLM 解读 verification_recipe + 自由 dispatch 工具). 留 Phase D+
- **假设依赖图**: 假设之间可能有依赖 ("诚实"是"覆盖"前提). 当前各假设独立列, 未识别依赖. 留 Phase C+
- **质量保证**: HypothesisProposer 当场产假设的质量需 L1 抽样审, 不能 LLM 自评 (违反 feedback_semantic_sentences_not_classification)
