# [OMNI] origin=codex domain=omnicompany/guardian ts=2026-06-18 type=rule
"""Project hygiene profile scanner.

This module lets non-Omnicompany repositories opt into Guardian hygiene checks
without hard-coding their directory shape in Guardian itself. A project provides
`.omni/hygiene-profile.yaml`; `HygieneScanWorker` reads it and emits warnings
next to the existing OMNI hygiene rules.
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

try:
    import yaml
except Exception:  # pragma: no cover - dependency exists in omnicompany
    yaml = None  # type: ignore[assignment]


PROFILE_REL = ".omni/hygiene-profile.yaml"

_VERSION_RE = re.compile(
    r"(^|[-_.])v\d+([-_.]|$)|"
    r"(^|[-_.])V\d+([-_.]|$)|"
    r"\.bak(\.|$)|"
    r"(^|[-_.])backup([-_.]|$)|"
    r"(^|[-_.])retry([-_.]|$)|"
    r"(^|[-_.])copy([-_.]|$)|"
    r"(^|[-_.])old([-_.]|$)|"
    r"step\d+_\d+|phase\d+_\d+",
    re.IGNORECASE,
)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _as_str_set(value: Any) -> set[str]:
    return {str(item) for item in _as_list(value)}


def _resolve_profile_root(project_root: Path, root_spec: dict[str, Any]) -> Path:
    raw = str(root_spec.get("path", "."))
    p = Path(raw)
    if not p.is_absolute():
        p = project_root / p
    return p.resolve()


def _iter_entries(root: Path) -> list[Path]:
    try:
        return sorted(root.iterdir(), key=lambda p: p.name.lower())
    except (PermissionError, OSError):
        return []


def _iter_files_and_dirs(root: Path) -> list[Path]:
    out: list[Path] = []
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            children = list(cur.iterdir())
        except (PermissionError, OSError):
            continue
        for child in children:
            out.append(child)
            if child.is_dir() and child.name not in {".git", ".venv", "venv", "node_modules"}:
                stack.append(child)
    return out


def _rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _path_matches(rel_path: str, pattern: str) -> bool:
    """Path-aware glob match.

    `PurePosixPath.match()` treats patterns as suffix matches, so `tmp/**` can
    unexpectedly match `var/tmp/...`. For hygiene profiles most slash patterns
    are intended to be rooted at the configured scan root. Basename-only globs
    such as `*.json` still match by filename.
    """
    rel_path = rel_path.strip("/")
    pattern = pattern.strip("/")
    if not rel_path or not pattern:
        return False
    if "/" not in pattern:
        return PurePosixPath(rel_path).match(pattern)
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        if prefix.startswith("**/"):
            marker = prefix[3:]
            return rel_path == marker or rel_path.endswith("/" + marker) or f"/{marker}/" in f"/{rel_path}/"
        return rel_path == prefix or rel_path.startswith(prefix + "/")
    if pattern.startswith("**/"):
        suffix_pattern = pattern[3:]
        parts = rel_path.split("/")
        return any(
            PurePosixPath("/".join(parts[idx:])).match(suffix_pattern)
            for idx in range(len(parts))
        )
    first = pattern.split("/", 1)[0]
    if first not in {"*", "**"} and rel_path != first and not rel_path.startswith(first + "/"):
        return False
    return PurePosixPath(rel_path).match(pattern)


def _matches_any(rel_path: str, patterns: list[str]) -> bool:
    return any(_path_matches(rel_path, pat) for pat in patterns)


def _issue(
    *,
    rule_id: str,
    severity: str,
    profile_root: str,
    rel_path: str,
    message: str,
) -> dict[str, str]:
    return {
        "rule_id": rule_id,
        "severity": severity.upper(),
        "path": f"{profile_root}:{rel_path}" if rel_path else profile_root,
        "message": message,
    }


def scan_project_profile_violations(project_root: Path) -> list[dict[str, str]]:
    """Scan `.omni/hygiene-profile.yaml` if present.

    The schema is intentionally small:
      roots.<name>.path
      roots.<name>.required_paths
      roots.<name>.allowed_root_dirs / allowed_root_files
      roots.<name>.forbidden_globs
      roots.<name>.versioned_name_scan.include/exclude
    """
    profile_path = project_root / PROFILE_REL
    if not profile_path.exists():
        return []
    if yaml is None:
        return [_issue(
            rule_id="PROJ-HYG-000",
            severity="HIGH",
            profile_root="profile",
            rel_path=PROFILE_REL,
            message="Cannot load hygiene profile because PyYAML is unavailable.",
        )]

    try:
        profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return [_issue(
            rule_id="PROJ-HYG-000",
            severity="HIGH",
            profile_root="profile",
            rel_path=PROFILE_REL,
            message=f"Cannot parse hygiene profile: {exc}",
        )]

    roots = profile.get("roots") or {}
    if not isinstance(roots, dict):
        return [_issue(
            rule_id="PROJ-HYG-000",
            severity="HIGH",
            profile_root="profile",
            rel_path=PROFILE_REL,
            message="hygiene profile field `roots` must be a mapping.",
        )]

    issues: list[dict[str, str]] = []
    for root_name, root_spec_any in roots.items():
        if not isinstance(root_spec_any, dict):
            continue
        root_spec: dict[str, Any] = root_spec_any
        scan_root = _resolve_profile_root(project_root, root_spec)
        root_label = str(root_name)
        if not scan_root.exists():
            issues.append(_issue(
                rule_id="PROJ-HYG-ROOT-MISSING",
                severity=str(root_spec.get("missing_severity", "HIGH")),
                profile_root=root_label,
                rel_path="",
                message=f"Configured hygiene root does not exist: {scan_root}",
            ))
            continue

        required_paths = [str(p) for p in _as_list(root_spec.get("required_paths"))]
        for required in required_paths:
            if not (scan_root / required).exists():
                issues.append(_issue(
                    rule_id="PROJ-HYG-REQUIRED-MISSING",
                    severity="HIGH",
                    profile_root=root_label,
                    rel_path=required,
                    message=f"Required path is missing under {root_label}: {required}",
                ))

        allowed_dirs = _as_str_set(root_spec.get("allowed_root_dirs"))
        allowed_files = _as_str_set(root_spec.get("allowed_root_files"))
        if allowed_dirs or allowed_files:
            for entry in _iter_entries(scan_root):
                if entry.is_dir():
                    if entry.name not in allowed_dirs:
                        issues.append(_issue(
                            rule_id="PROJ-HYG-ROOT-CLOSED-SET",
                            severity="MEDIUM",
                            profile_root=root_label,
                            rel_path=entry.name,
                            message=(
                                f"Root directory `{entry.name}` is outside the hygiene "
                                f"closed set for {root_label}."
                            ),
                        ))
                elif entry.is_file() and entry.name not in allowed_files:
                    issues.append(_issue(
                        rule_id="PROJ-HYG-ROOT-CLOSED-SET",
                        severity="MEDIUM",
                        profile_root=root_label,
                        rel_path=entry.name,
                        message=(
                            f"Root file `{entry.name}` is outside the hygiene closed "
                            f"set for {root_label}."
                        ),
                    ))

        forbidden = root_spec.get("forbidden_globs") or []
        for item_any in _as_list(forbidden):
            if isinstance(item_any, str):
                item = {"pattern": item_any}
            elif isinstance(item_any, dict):
                item = item_any
            else:
                continue
            pattern = str(item.get("pattern", ""))
            if not pattern:
                continue
            severity = str(item.get("severity", "HIGH"))
            reason = str(item.get("reason", "forbidden by hygiene profile"))
            exclude = [str(p) for p in _as_list(item.get("exclude"))]
            for path in _iter_files_and_dirs(scan_root):
                rel_path = _rel(path, scan_root)
                if _matches_any(rel_path, exclude):
                    continue
                if _path_matches(rel_path, pattern):
                    issues.append(_issue(
                        rule_id=str(item.get("rule_id", "PROJ-HYG-FORBIDDEN-PATH")),
                        severity=severity,
                        profile_root=root_label,
                        rel_path=rel_path,
                        message=f"{rel_path}: {reason}",
                    ))

        version_scan = root_spec.get("versioned_name_scan")
        if isinstance(version_scan, dict):
            include = [str(p) for p in _as_list(version_scan.get("include") or ["**/*"])]
            exclude = [str(p) for p in _as_list(version_scan.get("exclude"))]
            severity = str(version_scan.get("severity", "MEDIUM"))
            for path in _iter_files_and_dirs(scan_root):
                rel_path = _rel(path, scan_root)
                if not _matches_any(rel_path, include):
                    continue
                if _matches_any(rel_path, exclude):
                    continue
                if _VERSION_RE.search(path.name):
                    issues.append(_issue(
                        rule_id="PROJ-HYG-VERSIONED-NAME",
                        severity=severity,
                        profile_root=root_label,
                        rel_path=rel_path,
                        message=(
                            f"{rel_path}: version/copy/backup marker in active path. "
                            "Keep the stable name in place and move old variants to an archive."
                        ),
                    ))

    return issues
