# [OMNI] origin=claude-code domain=services/repo_learner ts=2026-04-09T12:00:00Z
# [OMNI] material_id="material:learning.repo.learner.package_exports.py"
"""repo_learner — 带目的的 repo 学习支流。

与 repo_architect (结构化描述) 并列。不追求覆盖率、不画架构图;
让一个主 agent 带着"找出学习价值 + 学习位置"的目的自由读仓库, 必要时 spawn
一层 sub-agent 深读某个模块, 最终产出自由格式 learning report。

共享 repo_architect 的前 4 个基础节点 (input_validator / repo_acquirer /
repo_identity_anchor / scale_surveyor), 通过 bindings 直接引用同一 Router 类,
不 copy, 不 fork。
"""
