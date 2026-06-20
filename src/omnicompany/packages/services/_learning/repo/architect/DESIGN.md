
# repo_architect · 设计文档

## 状态
- **版本**: V1 (Phase D Diamond shortcut 2026-04-20)
- **成熟度**: active
- **下一步**: 补 UserInquiry 真实实现（AdaptiveInterviewerRouter 当前为 stub）；Stage 3 真迁 LLM 节点为独立 Worker

## 核心目的
对任意 GitHub 仓库或本地仓库进行深度架构分析，产出**可追溯证据链的架构报告** + 覆盖率报告，并将结果写入 OmniKB 供后续 absorption 循环跨仓库比对。

差异化能力：每条分析断言都必须有 evidence_refs（源码文件+行号），禁止 LLM 凭记忆输出结论，消灭幻觉。最终报告写入知识库，支持跨仓库能力对齐（omni_parallels 字段）。

## 核心接口

- [workers/__init__.py](workers/__init__.py) — `ALL_WORKERS` (21 Worker, Diamond shortcut)
- [formats.py](formats.py) — 17 个 Material 定义（6 阶段）
- [pipeline.py](pipeline.py) — `build_pipeline()`
- [_archive/routers_legacy.py](_archive/routers_legacy.py) — 原 21 Router 实现

## 架构决策

### D1 — Diamond Shortcut 迁移

21 个 Router 中含多个 LLM 节点（ScaleSurveyor / RepoIntrospection / DocsReader / AdaptiveInterviewer / ReportDesigner / ModuleDrafterLeaf / CrossValidator / ReportFuser），采用 Diamond shortcut: `class XxxWorker(Worker, _LegacyRouter)`. 业务逻辑保留在 `_archive/routers_legacy.py`。

### D2 — 证据链不变量

所有 LLM 分析节点输出都要求 evidence_refs：`{file, lines, claim}` 三元组。cross_validator 的不一致列表要求 evidence_upstream 指向上游断言的来源节点+行号。这是防幻觉的核心机制。

### D3 — Scatter / GATHER 模式

ModuleDrafterLeafRouter 是 Scatter Leaf，每个 focus_module 一个 leaf 实例并行运行。DraftCollectorRouter 是 GATHER 节点，收集所有 leaf 产出成 draft-set。

### D4 — 三路并行信息收集 (fan-in)

阶段 2 有三条独立分支：RepoIntrospection（自述调研） / DocsReader（文档解析） / AdaptiveInterviewer（用户焦点问卷）。三路都是 mode-selected 的消费者，产物由 ReportDesigner 合并（三路 fan-in）。每路都有降级回落（ResearchDegraded / DocsFallback / InterviewDefaults）。

### D5 — 身份锚防幻觉 (RepoIdentityAnchor)

RepoIdentityAnchorRouter 在阶段 1 从真实文件提取 disambiguation_hint，后续所有 LLM 节点在 prompt 开头强制粘贴此 hint。这直接解决了"OmniCompany vs voxel_sandbox OmniCompany mod"类同名幻觉问题。

### D6 — 覆盖率用语义三档而非数值

CoverageGater 判定用 complete/partial/insufficient 三档而非百分比，禁止"coverage: 95%"这种数值输出。retry 上限 3 次，超限则整条管线 HALT。

## 数据流 / 拓扑

```
【阶段 1 准备】
repo-architect.input (source)
  → InputValidatorWorker (校验)
  → RepoAcquirerWorker (Clone/Mount)
  → repo-architect.acquired-repo (internal)
  → RepoIdentityAnchorWorker (身份提取)
  → repo-architect.repo-identity (internal)
  → ScaleSurveyorWorker (规模+模块拓扑, LLM)
  → repo-architect.scaled-survey (internal)
  → ModeSelectorWorker / DefaultModeWorker
  → repo-architect.mode-selected (internal)

【阶段 2 信息收集, 三路并行】
mode-selected → RepoIntrospectionWorker → research-notes (internal)
mode-selected → DocsReaderWorker → docs-summary (internal)
mode-selected → AdaptiveInterviewerWorker → user-focus-profile (internal)

【阶段 3 骨架】
research-notes + docs-summary + user-focus-profile
  → ReportDesignerWorker (LLM, fan-in 3路)
  → repo-architect.report-skeleton (internal)

【阶段 4 并行深度, Scatter/Gather】
report-skeleton → [per focus_module] ModuleDrafterLeafWorker (LLM, Scatter)
  → repo-architect.module-draft × N (internal)
  → DraftCollectorWorker (Gather)
  → repo-architect.draft-set (internal)

【阶段 5 质量门】
draft-set → CoverageGaterWorker → coverage-feedback (internal)
  ↳ retry → ModuleDrafterLeafWorker (重跑 insufficient 模块)
  ↳ pass → ValidatedDraftsWorker → validated-drafts (internal)
validated-drafts → CrossValidatorWorker (LLM) → cross-validation (internal)

【阶段 6 融合发布】
validated-drafts + cross-validation → ReportFuserWorker (LLM) → arch-report (internal)
validated-drafts → CoverageReporterWorker → coverage-report (internal)
arch-report + coverage-report → KBIngesterWorker → repo-architect.kb-entry (sink)
```

## 已知局限

1. **AdaptiveInterviewerRouter stub** — UserInquiry 交互未完整实现，当前走 InterviewDefaults 降级。**升级路径**：接入 UserInquiry 原语，实现真实 1-3 轮焦点问卷。

2. **Diamond 体未真迁移** — 21 个 Router 业务逻辑仍在 _archive/。Stage 3 低优先级。

3. **Scatter/Gather 并发模型** — ModuleDrafterLeafRouter 的并行实现依赖 pipeline runner 的 SCATTER 支持。当前 runner 是否真并行需验证。

4. **RepoAcquirer 网络依赖** — Clone GitHub URL 需网络访问，无离线降级。**升级路径**：加 cache/pre-fetched 机制。

### doctor.blackboard 扫描已知违规（Phase D · 保留登记）

| Material | 违规类型 | 决定 | 理由 |
|---|---|---|---|
| repo-architect.input | kind.source 但 InputValidatorWorker 声明为 producer（FORMAT_OUT=同名） | **保留** | InputValidatorRouter 采用"验证-透传"模式：校验输入有效后 re-emit 同一 Material，让 RepoAcquirerRouter 消费。这是 gate 设计而非真实产出；source 语义（"外部注入入口"）保留合理 |
| repo-architect.research-notes | kind.internal 无 consumer Worker | **保留** | ReportDesignerRouter 是真实消费者，但 Diamond shortcut 下 FORMAT_IN 只能声明一路（user-focus-profile）；doctor 无法感知 fan-in 3 路中的其他两路。Stage 3 真迁移时补全 composite FORMAT_IN |
| repo-architect.docs-summary | kind.internal 无 consumer Worker | **保留** | 同上；DocsReaderRouter 产出，ReportDesignerRouter 内部多路读取，Diamond 下不可见 |

**根因**：Diamond shortcut 限制 — `FORMAT_IN` 为单 str，无法声明 3-way fan-in；InputValidator 透传设计；两者均为历史设计决策，不影响实际运行时正确性。Stage 3 真迁移时解决。

## 新哲学对齐（Phase D · 2026-04-20）

### Material 层（F-16/17/18/19）

| 条款 | 状态 | 说明 |
|---|---|---|
| F-16 kind 三分 | ✅ | input=source; kb-entry=sink; 其余 15 个=internal（arch-report/coverage-report 被 kb_ingester 消费，故为 internal 而非 sink）|
| F-17 Workspace 大明文 | ✅ | arch-report/coverage-report 落盘到 data/absorption/reports/coverage/，FORMAT_OUT 只含路径指针（report_path/coverage_report_path）|
| F-18 Job × Material 绑定 | N/A | 传统 pipeline，待新 Runtime |
| F-19 kind.* tag 必填 | ✅ | Phase D 修正：17 条 Material 全部补 kind.* |

### Worker 层（R-18~R-25）

| 条款 | 状态 | 说明 |
|---|---|---|
| R-18 粒度 | ✅ | 21 Worker 各有完整职责 + FORMAT 边界，粒度适当 |
| R-19 Agent Worker 升级 | ⚠️ 待评估 | ModuleDrafterLeafRouter 有多个 LLM 调用可能受益于 Agent Worker；当前 grandfathered |
| R-20 Agent Worker 三件套 | ⚠️ 待评估 | 同上 |
| R-21 Diagnosis Agent Worker | N/A | |
| R-22 WorkspaceWriterWorker | ⚠️ 待评估 | ReportFuserRouter / CoverageReporterRouter 直接落盘，未走 WorkspaceWriterWorker；升级路径 Stage 3 |
| R-23 Verdict.output 平铺 | ✅ | 检查 _archive/ 代码，Worker 输出无嵌套 format_id |
| R-24 FORMAT_IN_MODE | N/A | 所有 pipeline Worker FORMAT_IN 为单 str |
| R-25 子 job | N/A | 无 _emit_as_new_job |

### Team 层（P-13~P-17）

| 条款 | 状态 | 说明 |
|---|---|---|
| P-13 声明即消费 | ✅ | 各 Worker 只消费 FORMAT_IN 声明的 Material |
| P-14~17 Workspace 目录 | ✅ 部分 | 落盘路径通过 config.resolve_db_dir("absorption")，不硬编码 cwd |

**结论**: F-19 缺口已修正。Diamond shortcut 完成（21 Workers）。R-22 WorkspaceWriterWorker 和 R-19/20 Agent Worker 升级路径 grandfathered 记录，待 Stage 3 真迁时处理。

## 参考资料

- [workers/](workers/) — 21 个 Worker (Diamond shortcut)
- [formats.py](formats.py) — 17 个 Material（6 阶段完整链）
- [_archive/routers_legacy.py](_archive/routers_legacy.py) — 原 Router 实现
- [docs/plans/[2026-04-08]REPO-ABSORPTION-WORKFLOW/](../../../../../docs/plans/[2026-04-08]REPO-ABSORPTION-WORKFLOW/) — 设计历史
- [../absorption/](../absorption/) — 调用 repo-architect 的 absorption Team
