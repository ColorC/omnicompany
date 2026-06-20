# [OMNI] DEPRECATED 2026-04-21 -- migrated to team.py
# [OMNI] material_id="material:learning.absorption.pipeline_deprecated_shim.py"
from .team import (
    build_survey_pipeline,
)


def build_team():
    """Backward-compatible default team builder for package discovery."""
    return build_survey_pipeline()


build_pipeline = build_team
