
# cleanup_bot · 已归档

> 2026-05-05 整体归档. 详:
> [docs/plans/diagnosis/[2026-05-05]DIAGNOSIS-RECONSOLIDATION/plan.md](../../../../../../docs/plans/diagnosis/%5B2026-05-05%5DDIAGNOSIS-RECONSOLIDATION/plan.md)

## 去向

- **不属诊断**: 三个 worker (evidence_gatherer 扫磁盘 + anomaly_detector LLM 判正误触 + rollback_planner 打印清理脚本) 是清理工具的取证, 跟"健康诊断"不同质
- **历史代码**: 本目录 [_archive/](_archive/) 完整保留

## 后续

如有真需求 (扫 AI 误触磁盘垃圾), 应作独立工具放别处, 不归诊断或 doctor 范围.
