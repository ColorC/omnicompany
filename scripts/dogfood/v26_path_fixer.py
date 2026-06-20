# OMNI-PERSISTENT-SCRIPT
# owner: ai-ide
# purpose: V0-V26 plan 目录重组后批改所有引用路径 (2026-05-08)
"""真批改所有引用 V0-V26 旧路径 → 新路径 (samples/data/reports 子目录)."""
from __future__ import annotations

import os


MOVED = {
    "sample_compliant_plan_exemplar_library.md": "samples/sample_compliant_plan_exemplar_library.md",
    "sample_exemplar_E-agent-spec_diagnostic-2026-05-06.yaml": "samples/sample_exemplar_E-agent-spec_diagnostic-2026-05-06.yaml",
    "sample_exemplar_E-material-doctor_exemplar-2026-05-06.yaml": "samples/sample_exemplar_E-material-doctor_exemplar-2026-05-06.yaml",
    "sample_exemplar_E-team-csv_to_md-2026-05-06.yaml": "samples/sample_exemplar_E-team-csv_to_md-2026-05-06.yaml",
    "sample_exemplar_E-worker-csv_reader-2026-05-05.yaml": "samples/sample_exemplar_E-worker-csv_reader-2026-05-05.yaml",
    "sample_hypothesis_H-2026-05-05-001.yaml": "samples/sample_hypothesis_H-2026-05-05-001.yaml",
    "sample_hypothesis_green_solid.yaml": "samples/sample_hypothesis_green_solid.yaml",
    "sample_hypothesis_red_easy_falsify.yaml": "samples/sample_hypothesis_red_easy_falsify.yaml",
    "anti_patterns/": "data/anti_patterns/",
    "canonical_anchors/": "data/canonical_anchors/",
    "error_samples/": "data/error_samples/",
    "ap_024_scanner_dogfood_2026-05-07.md": "reports/ap_024_scanner_dogfood_2026-05-07.md",
    "challenge_agent_v3_architecture_2026-05-07.md": "reports/challenge_agent_v3_architecture_2026-05-07.md",
    "challenge_agent_v7_architecture_final_2026-05-07.md": "reports/challenge_agent_v7_architecture_final_2026-05-07.md",
    "confidence_audit_finding_2026-05-07.md": "reports/confidence_audit_finding_2026-05-07.md",
    "dogfood_step7_report.md": "reports/dogfood_step7_report.md",
    "dogfood_step8_4_report.md": "reports/dogfood_step8_4_report.md",
    "hypothesis_v1_upgrade_report_2026-05-07.md": "reports/hypothesis_v1_upgrade_report_2026-05-07.md",
    "meta_dogfood_report_2026-05-07.md": "reports/meta_dogfood_report_2026-05-07.md",
    "meta_red_green_finding_2026-05-07.md": "reports/meta_red_green_finding_2026-05-07.md",
    "stage10_4hr_interrogation_2026-05-07.md": "reports/stage10_4hr_interrogation_2026-05-07.md",
    "stage10_self_interrogation_2026-05-07.md": "reports/stage10_self_interrogation_2026-05-07.md",
    "v14_full_e2e_rework_2026-05-07.md": "reports/v14_full_e2e_rework_2026-05-07.md",
    "v16_deriver_quality_dogfood_2026-05-07.md": "reports/v16_deriver_quality_dogfood_2026-05-07.md",
    "v17_new_hypothesis_full_closure_2026-05-07.md": "reports/v17_new_hypothesis_full_closure_2026-05-07.md",
    "v18_team_derivation_2026-05-07.md": "reports/v18_team_derivation_2026-05-07.md",
    "v19_h034_batch_finding_2026-05-07.md": "reports/v19_h034_batch_finding_2026-05-07.md",
    "v20_h034_project_scale_finding_2026-05-07.md": "reports/v20_h034_project_scale_finding_2026-05-07.md",
    "v21_h034_falsified_schema_5steps_2026-05-07.md": "reports/v21_h034_falsified_schema_5steps_2026-05-07.md",
    "v22_h034b_upgraded_2026-05-07.md": "reports/v22_h034b_upgraded_2026-05-07.md",
    "v23_deriver_auto_upgrade_2026-05-07.md": "reports/v23_deriver_auto_upgrade_2026-05-07.md",
    "v24_real_fix_sw_tdd_2026-05-07.md": "reports/v24_real_fix_sw_tdd_2026-05-07.md",
    "v26_real_audit_findings_2026-05-07.md": "reports/v26_real_audit_findings_2026-05-07.md",
    "v3_1_real_llm_dogfood_2026-05-07.md": "reports/v3_1_real_llm_dogfood_2026-05-07.md",
    "v3_workers_inventory_and_classification.md": "reports/v3_workers_inventory_and_classification.md",
    "self_audit_2026-05-06.md": "reports/self_audit_2026-05-06.md",
}

V26_PREFIX = "[2026-05-05]DIAGNOSIS-RECONSOLIDATION/"
ROOT = "/workspace/omnicompany"
SKIP_DIRS = {"_workspaces", "_archive", "_graveyard", "__pycache__", "node_modules", ".git", "venv"}


def main():
    files_changed = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        parts = dirpath.replace("\\", "/").split("/")
        if any(d in parts for d in SKIP_DIRS):
            continue
        for fn in filenames:
            if not fn.endswith((".md", ".py", ".yaml", ".yml", ".json", ".jsonl")):
                continue
            full = os.path.join(dirpath, fn)
            full_norm = full.replace("\\", "/")
            # 跳挪后真新位置 (避免改自己引用自己)
            if any(s in full_norm for s in (
                "DIAGNOSIS-RECONSOLIDATION/reports/",
                "DIAGNOSIS-RECONSOLIDATION/samples/",
                "DIAGNOSIS-RECONSOLIDATION/data/",
            )):
                continue
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            original = content
            for old, new in MOVED.items():
                old_path = V26_PREFIX + old
                new_path = V26_PREFIX + new
                if old_path in content:
                    content = content.replace(old_path, new_path)
            if content != original:
                files_changed.append(full)
                with open(full, "w", encoding="utf-8") as f:
                    f.write(content)
    print(f"真改了 {len(files_changed)} 个文件:")
    for f in files_changed:
        print(f"  {f.replace(chr(92), '/')}")


if __name__ == "__main__":
    main()
