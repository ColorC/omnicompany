# [OMNI] origin=codex domain=tests/services/_learning/repo/exporter ts=2026-06-19 type=test

from pathlib import Path

from omnicompany.packages.services._learning.repo.exporter._lib import (
    FileInfo,
    build_staged_github,
    load_matrix,
    match_file_policies,
    rewrite_for_github,
    scrub_identity,
)


MATRIX_PATH = Path("config/publishing/desensitization_matrix.yaml")


def test_company_identity_scrubs_inside_identifier() -> None:
    assert scrub_identity("THE_COMPANY_***=the_company_xxx") == "the_company_***=the_company_xxx"


def test_the_company_api_key_is_recognized_and_masked_in_github_stage(tmp_path: Path) -> None:
    matrix = load_matrix(MATRIX_PATH)
    source_repo = tmp_path / "source"
    staged_dir = tmp_path / "staged"
    source_repo.mkdir()

    text = 'THE_COMPANY_*** = "placeholder-only"\n'
    files = [
        FileInfo(
            rel_path="sample.py",
            size=len(text),
            ext=".py",
            text=text,
        )
    ]
    decisions = match_file_policies(files, matrix)

    assert decisions[0].github_action == "rewrite"
    assert "enterprise_term:company_name" in decisions[0].rationale

    rewritten = rewrite_for_github(files, decisions, [])
    build_staged_github(source_repo, staged_dir, files, decisions, rewritten)

    staged_text = (staged_dir / "sample.py").read_text(encoding="utf-8")
    assert "THE_COMPANY_***" not in staged_text
    assert "the_company_***" in staged_text


def test_leaked_domain_directories_are_redacted_for_github() -> None:
    matrix = load_matrix(MATRIX_PATH)
    files = [
        FileInfo(rel_path=f"src/omnicompany/packages/domains/{domain}/team.py", size=0, ext=".py", text="")
        for domain in ("vilo", "research", "decisions", "publish")
    ]

    decisions = match_file_policies(files, matrix)

    assert [d.github_action for d in decisions] == ["redact", "redact", "redact", "redact"]
