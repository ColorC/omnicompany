# [OMNI] origin=claude-code domain=omnicompany/guardian ts=2026-04-23T00:00:00Z type=router
# [OMNI] material_id="material:core.guardian.workers.hygiene_scanner.implementation.py"
"""HygieneScanWorker — Guardian 运行空间卫生巡查 Worker (2026-04-23 I-09 首发).

Worker 协议:
  FORMAT_IN  = guardian.hygiene-request
  FORMAT_OUT = guardian.hygiene-report

职责:
  扫描"运行空间健康" 维度 (plan GUARDIAN-COMPLIANCE-HARDENING §零 定义):
    OMNI-047 空文件夹            ✅ 首发
    OMNI-048 临时文件残留        🔲 (I-10 待接入)
    OMNI-049 过期运行产物老化    🔲 (I-11)
    OMNI-050 数据体积异常告警    🔲 (I-12)

  本 Worker 只产告警, 不清理 (§九 '告警 ≠ 清理' 边界). 产出 Material
  `guardian.hygiene-report`, 下游清理设施 (I-27 缺口) 消费决定动作.

粒度原则:
  一个 Worker 统筹运行空间卫生四维扫描, 不是 "每条规则一个 Worker".
  规则元数据在 `rules/runtime_hygiene.py`, 扫描函数也在同模块, 本 Worker 只做
  调度 + Violation 打包.

使用:
  > omni run guardian-hygiene

产出落盘:
  data/services/guardian/hygiene/hygiene-<ts>.json
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnicompany.packages.services._core.omnicompany import Worker
from omnicompany.protocol.anchor import Verdict, VerdictKind

from ..hygiene_whitelist import is_whitelisted, load_whitelist
from ..rules._base import Violation
from ..rules.runtime_hygiene import (
    scan_aging_items,
    scan_data_root_layout_violations,
    scan_data_subdir_violations,
    scan_empty_dirs,
    scan_placeholder_data_layout_candidates,
    scan_suspicious_temp_candidates,
    scan_temp_files,
    scan_volume_alerts,
)
from ..rules.project_profile_hygiene import scan_project_profile_violations

logger = logging.getLogger(__name__)


class HygieneScanWorker(Worker):
    """扫描运行空间卫生 (空目录 / 临时文件 / 过期产物 / 体积), 产出告警清单."""

    DESCRIPTION = (
        "Guardian 运行空间卫生巡查: 空文件夹 (OMNI-047) + 临时文件 (OMNI-048) + "
        "过期产物 (OMNI-049) + 体积告警 (OMNI-050). 只产告警不清理, "
        "下游清理设施消费 (见 plan §九 '告警 ≠ 清理')."
    )
    FORMAT_IN = "guardian.hygiene-request"
    FORMAT_OUT = "guardian.hygiene-report"
    INPUT_KEYS = ["project_root"]

    def run(self, input_data: dict[str, Any]) -> Verdict:
        project_root_str = input_data.get("project_root")
        if project_root_str:
            project_root = Path(project_root_str)
        else:
            from omnicompany.core.config import _project_root
            project_root = _project_root()

        if not project_root.exists():
            return Verdict(
                kind=VerdictKind.FAIL,
                diagnosis=f"project_root 不存在: {project_root}",
            )

        now = datetime.now(timezone.utc).isoformat()
        date_str = now[:10]
        violations: list[Violation] = []
        candidates_for_judge: list[dict[str, Any]] = []
        whitelisted_hits: list[dict[str, Any]] = []  # 命中白名单的条目 (便于审计)
        counter = 0

        # 加载 whitelist (第二波 §十一 · 2026-04-23)
        whitelist = load_whitelist(project_root)

        def _next_ticket() -> str:
            nonlocal counter
            counter += 1
            return f"TICKET-{date_str}-HYG-{counter:03d}"

        def _check_whitelist(rule_id: str, path: str) -> bool:
            """whitelist 命中 → 挪到 whitelisted_hits, 返回 True (跳过 violations)."""
            hit = is_whitelisted(rule_id, path, whitelist)
            if hit is None:
                return False
            whitelisted_hits.append({
                "rule_id": rule_id,
                "path": path,
                "matched_pattern": hit.path_pattern,
                "reason": hit.reason,
            })
            return True

        # ── OMNI-047 空文件夹 ──
        for rel_path in scan_empty_dirs(project_root):
            if _check_whitelist("OMNI-047", rel_path):
                continue
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id="OMNI-047",
                severity="LOW",
                path=rel_path,
                message=(
                    f"{rel_path}: 空目录. 若为 agent 创建中途失败遗留, "
                    f"应由清理设施清除. 若合理保留, 请在该目录置 README.md 或 .gitkeep 说明用途."
                ),
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        # ── OMNI-048a 临时文件硬模式 ──
        for rel_path in scan_temp_files(project_root):
            if _check_whitelist("OMNI-048a", rel_path):
                continue
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id="OMNI-048a",
                severity="MEDIUM",
                path=rel_path,
                message=(
                    f"{rel_path}: 临时文件残留 (硬模式命中). "
                    f"由清理设施删除, 或加 .gitignore 若是合法本地缓存."
                ),
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        # ── OMNI-048b 临时文件气味候选 (送 GuardianAgent 复核) ──
        # 本波只产候选, LLM 复核延至 I-25.
        for rel_path in scan_suspicious_temp_candidates(project_root):
            if _check_whitelist("OMNI-048b", rel_path):
                continue
            candidates_for_judge.append({
                "rule_id": "OMNI-048b",
                "path": rel_path,
                "severity": "LOW",
                "message": (
                    f"{rel_path}: 文件名气味像临时品, 待 GuardianAgent 语义复核. "
                    f"若是合法模块, 请改名去除 scratch/tmp/try/wip 等字样."
                ),
                "pending_review": True,
            })

        # ── OMNI-051a data/ 分布式白名单 (对已声明 data_layout 的 service) ──
        for item in scan_data_subdir_violations(project_root):
            if _check_whitelist("OMNI-051a", item["path"]):
                continue
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id="OMNI-051a",
                severity="MEDIUM",
                path=item["path"],
                message=(
                    f"{item['path']}: data/services/{item['svc']}/ 下存在未声明的 {item['kind']}. "
                    f"在 src/.../services/{item['svc']}/.omni/manifest.yaml 的 kind: data_layout "
                    f"document 里添加对应声明, 或清理此污染."
                ),
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        # ── OMNI-051b data_layout 描述占位候选 (送 LLM 复核) ──
        data_root_layout_violations_all = scan_data_root_layout_violations(project_root)
        data_root_layout_violations = [
            it for it in data_root_layout_violations_all
            if not _check_whitelist("OMNI-056", it["path"])
        ]
        for item in data_root_layout_violations:
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id="OMNI-056",
                severity="HIGH",
                path=item["path"],
                message=(
                    f"{item['path']}: data/ top-level {item['kind']} is outside the "
                    f"docs/archmap.yaml closed set. Move it under data/_runtime, "
                    f"data/services/<svc>, data/domains/<domain>, or update archmap "
                    f"after human review."
                ),
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        for item in scan_placeholder_data_layout_candidates(project_root):
            candidates_for_judge.append({
                "rule_id": "OMNI-051b",
                "path": f"src/omnicompany/packages/services/{item['svc']}/.omni/manifest.yaml",
                "severity": "LOW",
                "svc": item["svc"],
                "subdir_name": item["subdir_name"],
                "description": item["description"],
                "message": (
                    f"service {item['svc']} 的 data_layout subdir '{item['subdir_name']}' "
                    f"描述 '{item['description']}' 疑似占位. 待 GuardianAgent 复核."
                ),
                "pending_review": True,
            })

        # ── OMNI-049 过期产物老化 (按各 service manifest 声明) ──
        aging_list_all = scan_aging_items(project_root)
        aging_list = [it for it in aging_list_all if not _check_whitelist("OMNI-049", it["path"])]
        for item in aging_list:
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id="OMNI-049",
                severity=item.get("severity", "warn").upper() if item.get("severity", "warn").upper() in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"} else "MEDIUM",
                path=item["path"],
                message=(
                    f"{item['path']}: 文件年龄 {item['age_days']} 天, "
                    f"超过 service {item['source_svc']} 声明的 max_age_days={item['max_age_days']}. "
                    f"建议清理设施按 severity 处置."
                ),
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        # ── OMNI-050 数据体积异常告警 (内建默认 + service manifest 追加) ──
        volume_alerts_all = scan_volume_alerts(project_root)
        volume_alerts = [it for it in volume_alerts_all if not _check_whitelist("OMNI-050", it["path"])]
        for item in volume_alerts:
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id="OMNI-050",
                severity=item["severity"],
                path=item["path"],
                message=(
                    f"{item['path']}: 大小 {item['size_mb']}MB, "
                    f"超阈值 {item['max_size_mb']}MB (policy from {item['source_svc']}). "
                    f"主数据库清理需独立设施."
                ),
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        # ── Project hygiene profile (.omni/hygiene-profile.yaml) ──
        # Generic opt-in layer for sibling repos such as quant-lab. This keeps
        # repository-specific directory rules out of Guardian core rules while
        # still surfacing them through the normal hygiene command.
        for item in scan_project_profile_violations(project_root):
            if _check_whitelist(item["rule_id"], item["path"]):
                continue
            violations.append(Violation(
                ticket_id=_next_ticket(),
                rule_id=item["rule_id"],
                severity=item.get("severity", "MEDIUM"),
                path=item["path"],
                message=item["message"],
                disposition=["warn"],
                confidence=1.0,
                detected_at=now,
            ))

        # 分组统计
        by_rule: dict[str, int] = {}
        for v in violations:
            by_rule[v.rule_id] = by_rule.get(v.rule_id, 0) + 1
        by_rule_pending: dict[str, int] = {}
        for c in candidates_for_judge:
            rid = c["rule_id"]
            by_rule_pending[rid] = by_rule_pending.get(rid, 0) + 1

        # 落盘
        try:
            from omnicompany.core.config import resolve_service_data_dir
            hygiene_dir = resolve_service_data_dir("guardian") / "hygiene"
            hygiene_dir.mkdir(parents=True, exist_ok=True)
            report_path = hygiene_dir / f"hygiene-{now.replace(':', '-')}.json"
            report_path.write_text(
                json.dumps(
                    {
                        "scan_ts": now,
                        "project_root": str(project_root),
                        "violations": [asdict(v) for v in violations],
                        "violation_count": len(violations),
                        "by_rule": by_rule,
                        "candidates_for_judge": candidates_for_judge,
                        "candidate_count": len(candidates_for_judge),
                        "by_rule_pending": by_rule_pending,
                        "data_root_layout_violations": data_root_layout_violations,
                        "aging_list": aging_list,      # 原始 aging items (带 age_days / policy_pattern)
                        "volume_alerts": volume_alerts, # 原始 volume alerts (带 size_mb / policy_pattern)
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            # I-20 data-provenance: 写 sidecar 记录合法写入者身份
            try:
                from omnicompany.core.omnimark import write_data_sidecar
                write_data_sidecar(
                    report_path,
                    written_by=f"{self.__class__.__module__}.{self.__class__.__name__}",
                    source_path=__file__,
                    ttl_days=30,
                )
            except Exception as e:
                logger.debug("sidecar 写入失败 (非致命): %s", e)
            logger.info("hygiene report written: %s", report_path)
        except Exception as e:
            logger.warning("hygiene report 落盘失败: %s", e)

        return Verdict(
            kind=VerdictKind.PASS,
            output={
                "project_root": str(project_root),
                "scan_ts": now,
                "violations": [asdict(v) for v in violations],
                "violation_count": len(violations),
                "by_rule": by_rule,
                "candidates_for_judge": candidates_for_judge,
                "candidate_count": len(candidates_for_judge),
                "by_rule_pending": by_rule_pending,
                "data_root_layout_violations": data_root_layout_violations,
                "aging_list": aging_list,
                "volume_alerts": volume_alerts,
                "whitelisted_hits": whitelisted_hits,
                "whitelisted_count": len(whitelisted_hits),
            },
            diagnosis=(
                f"hygiene scan: {len(violations)} 硬告警 · {len(candidates_for_judge)} 待复核候选 · "
                f"{len(whitelisted_hits)} 白名单豁免 (by rule: {by_rule}; pending: {by_rule_pending})"
                if (violations or candidates_for_judge or whitelisted_hits)
                else "hygiene scan: 运行空间干净 · 0 告警 · 0 候选"
            ),
        )
