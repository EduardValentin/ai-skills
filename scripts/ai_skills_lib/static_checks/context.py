"""Immutable validation context and shared issue helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.ai_skills_lib.core import SkillRecord, discover_testable_skills
from scripts.ai_skills_lib.issues import ValidationIssue


@dataclass(frozen=True)
class AuthoredFile:
    logical_path: Path
    resolved_path: Path


@dataclass(frozen=True)
class StrictPathResolution:
    resolved_path: Path | None
    error: OSError | RuntimeError | None


@dataclass(frozen=True)
class ValidationContext:
    root: Path
    skills: tuple[SkillRecord, ...]
    public_names: frozenset[str]


def build_validation_context(root: Path) -> ValidationContext:
    resolved_root = root.resolve()
    skills = tuple(discover_testable_skills(resolved_root))
    return ValidationContext(
        root=resolved_root,
        skills=skills,
        public_names=frozenset(skill.name for skill in skills),
    )


def resolve_strict(path: Path) -> StrictPathResolution:
    try:
        return StrictPathResolution(path.resolve(strict=True), None)
    except (OSError, RuntimeError) as error:
        return StrictPathResolution(None, error)


def skill_scope(context: ValidationContext, skill: SkillRecord) -> str:
    try:
        return str(skill.root.relative_to(context.root))
    except ValueError:
        return str(skill.root)


def deduplicate_issues(issues: Iterable[ValidationIssue]) -> list[ValidationIssue]:
    deduplicated: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.scope, issue.message, issue.severity)
        if key not in seen:
            seen.add(key)
            deduplicated.append(issue)
    return deduplicated
