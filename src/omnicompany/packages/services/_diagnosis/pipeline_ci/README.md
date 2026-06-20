
# pipeline_ci · 已归档

> 2026-05-05 整体归档. 详:
> [docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/plan.md](../../../../../../docs/plans/diagnosis/%5B2026-05-05%5DDIAGNOSIS-RECONSOLIDATION/plan.md)

## 去向

- **概念并入**:
  - `domain_scanner_worker` → doctor `_entity/` 子域 (实体扫源)
  - `batch_auditor_worker` (合规/拓扑/输出) → doctor `_spec/` (合规) + `_hypothesis/` (拓扑)
  - `ci_gate_worker` (critical_count > 0 阻断) → doctor `_archive_table/` (汇总判 gate, 跟 guardian 钩子联动)
- **历史代码**: 本目录 [_archive/](_archive/) 完整保留
