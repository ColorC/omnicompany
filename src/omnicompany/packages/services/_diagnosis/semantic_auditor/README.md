
# semantic_auditor · 已归档

> 2026-05-05 整体归档. 详:
> [docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/plan.md](../../../../../../docs/plans/diagnosis/%5B2026-05-05%5DDIAGNOSIS-RECONSOLIDATION/plan.md)

## 去向 (5 worker 概念分配)

| 旧 worker | 用途 | 归 doctor 哪 |
|---|---|---|
| artifact_selector | 收集待审 artifact 打 kind 标签 | `_entity/` (实体扫描入口) |
| standard_matcher | artifact + kind → 适用 standard | `_spec/` + `_exemplar/` (匹配查找) |
| excerpt_retriever | 取每条 standard 摘录 | `_spec/` (规范装载) |
| llm_audit | LLM 主审 (循环调 AuditAgent) | `_hypothesis/` (LLM 假设型诊断) |
| finding_writer | 写 ARCH-CHANGES.jsonl + REGISTRY.md | `_archive_table/` (健康档案接口, 走 registry HealthArchive) |

历史代码: [_archive/](_archive/) (含 knowledge/ 旧 format material 文档).

## 影响

- `omni debt scan --full` 当前等价 `--fast` (semantic_auditor 部分跳过)
- `tests/semantic_auditor/test_phase_b1.py` 跟 `test_phase_b2.py` 失效 (待归档)
