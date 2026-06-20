# [OMNI] origin=claude-code domain=services/_governance ts=2026-06-12T12:00:00Z type=config
# [OMNI] material_id="material:governance.package_init.py"
"""Governance department.

Members:
- plan_steward: plan ownership, Chinese short titles, and format checks.
- work_history: repeated user needs and corrections mined from work history.

CLI entry: `omni governance`.
Structured JSON LLM calls consume `runtime.llm.structured.call_json`; the default
model is resolved by the `OMNI_STRUCTURED_LLM_MODEL` slot.
"""
