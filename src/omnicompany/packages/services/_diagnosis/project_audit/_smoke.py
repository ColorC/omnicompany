# [OMNI] origin=claude-code domain=services/_diagnosis/project_audit ts=2026-06-20T00:00:00Z type=test status=active
# [OMNI] summary="project_audit 扩展后的红绿冒烟:三 team 接线 + PromptHarvester/CodeReader/Auditor 链路真跑(小范围)。"
"""红绿冒烟测试(不依赖 pytest,直接跑)。"""
import os
import sys

from omnicompany.packages.services._diagnosis.project_audit.team import (
    build_team, build_discovery_team, build_completeness_team,
)
from omnicompany.packages.services._diagnosis.project_audit.run import (
    build_bindings, build_discovery_bindings, build_completeness_bindings,
)
from omnicompany.packages.services._diagnosis.project_audit.workers.tree_enumerator import TreeEnumeratorWorker
from omnicompany.packages.services._diagnosis.project_audit.workers.prompt_harvester import PromptHarvester
from omnicompany.packages.services._diagnosis.project_audit.workers.code_reader import CodeReader
from omnicompany.packages.services._diagnosis.project_audit.workers.completeness_critic import CompletenessCritic

ok = True
def check(name, cond, extra=""):
    global ok
    print(("PASS" if cond else "FAIL"), name, extra)
    if not cond: ok = False

# 1) 三 team 接线
t1, t2, t3 = build_team(), build_discovery_team(), build_completeness_team()
check("build_team 5 节点", len(t1.nodes) == 5, f"nodes={[n.id for n in t1.nodes]}")
check("主 team 边链路", len(t1.edges) == 5)
check("discovery team", t2.entry == "ProjectDiscoverer")
check("completeness team", t3.entry == "CompletenessCritic")
b1, b2, b3 = build_bindings(), build_discovery_bindings(), build_completeness_bindings()
check("主 bindings 5 worker", len(b1) == 5, str(list(b1)))
check("每个节点都有绑定", all(n.id in b1 for n in t1.nodes))

# 2) TreeEnumerator → CodeReader 真跑(用 project_audit 包自己当小项目)
pkg_root = os.path.dirname(__file__)
tv = TreeEnumeratorWorker().run({"name": "project_audit_pkg", "root": pkg_root})
check("TreeEnumerator PASS", tv.kind.name == "PASS", f"files={tv.output.get('total_files')}")
tree = tv.output
# PromptHarvester:限定小 session_root 验证解析(personal-homepage claude 目录, 1 文件)
ph_root = os.path.expanduser("~/.claude/projects/E--workspace-webworks-apps-personal-homepage")
tree["target"]["session_roots"] = [ph_root]
tree["target"]["harvest_keywords"] = ["personal-homepage", "作品集", "colorc"]
pv = PromptHarvester().run(tree)
check("PromptHarvester PASS", pv.kind.name == "PASS",
      f"scanned={pv.output.get('prompt_meta',{}).get('scanned_files')} kept={pv.output.get('prompt_meta',{}).get('kept')}")
cv = CodeReader().run(pv.output)
check("CodeReader PASS", cv.kind.name == "PASS",
      f"files_read={cv.output.get('code_meta',{}).get('files_read')} loc={cv.output.get('code_meta',{}).get('loc_by_lang')}")
check("CodeReader 真读到内容", (cv.output.get('code') and cv.output['code'][0].get('head')))

# 3) CompletenessCritic 红绿:缺页应 FAIL
seed_fail = {"owned_projects": ["proj-a"], "reports": {}, "pages": {}}
fv = CompletenessCritic().run(seed_fail)
check("Completeness 缺失→FAIL", fv.kind.name == "FAIL", fv.output.get("summary"))
seed_pass = {
    "owned_projects": ["proj-a"],
    "reports": {"proj-a": {"evidence_base": {"prompts_harvested": 5, "code_files_read": 10}}},
    "pages": {"proj-a": {"chars": 3000, "has_image": True, "traceable": True}},
}
pv2 = CompletenessCritic().run(seed_pass)
check("Completeness 达标→PASS", pv2.kind.name == "PASS", pv2.output.get("summary"))

print("\n=== 冒烟结论:", "全绿 ✅" if ok else "有红 ❌", "===")
sys.exit(0 if ok else 1)
