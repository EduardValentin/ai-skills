"""Immutable validation context and shared issue helpers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from scripts.ai_skills_lib.authored_content import (
    AuthoredContentReadError,
    AuthoredFile,
    AuthoredRepositoryBudget,
    StrictPathResolution,
    render_safe_diagnostic_text,
    resolve_strict,
)
from scripts.ai_skills_lib.core import (
    CanonicalSkillsTreeSnapshot,
    SkillRecord,
    discover_testable_skills,
    skill_source_matches_record,
    snapshot_canonical_skills_tree,
)
from scripts.ai_skills_lib.issues import ValidationIssue


@dataclass(frozen=True)
class ValidationContext:
    root: Path
    skills: tuple[SkillRecord, ...]
    public_names: frozenset[str]
    budget: AuthoredRepositoryBudget
    canonical_skills_tree: CanonicalSkillsTreeSnapshot


def build_validation_context(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> ValidationContext:
    resolved_root = root.resolve()
    repository_budget = budget or AuthoredRepositoryBudget()
    canonical_skills_tree = snapshot_canonical_skills_tree(
        resolved_root,
        budget=repository_budget,
    )
    skills = tuple(
        discover_testable_skills(
            resolved_root,
            budget=repository_budget,
        )
    )
    return ValidationContext(
        root=resolved_root,
        skills=skills,
        public_names=frozenset(skill.name for skill in skills),
        budget=repository_budget,
        canonical_skills_tree=canonical_skills_tree,
    )


def skill_scope(context: ValidationContext, skill: SkillRecord) -> str:
    return render_safe_diagnostic_path(skill.root, relative_to=context.root)


def render_safe_diagnostic_path(
    path: Path,
    *,
    relative_to: Path | None = None,
) -> str:
    """Render a logical path without disclosing secret-shaped components."""
    rendered_path = path
    if relative_to is not None:
        try:
            rendered_path = path.relative_to(relative_to)
        except ValueError:
            pass
    return "/".join(
        render_safe_diagnostic_text(component)
        for component in rendered_path.as_posix().split("/")
    )


def render_safe_diagnostic_issue(issue: ValidationIssue) -> ValidationIssue:
    """Render one issue without disclosing secret-shaped authored text."""
    return ValidationIssue(
        scope=render_safe_diagnostic_text(issue.scope),
        message=render_safe_diagnostic_text(issue.message),
        severity=issue.severity,
    )


def render_safe_diagnostic_issues(
    issues: Iterable[ValidationIssue],
) -> list[ValidationIssue]:
    """Render issue scopes and messages through the shared diagnostic policy."""
    return [render_safe_diagnostic_issue(issue) for issue in issues]


def validate_skill_sources_unchanged(
    context: ValidationContext,
) -> list[ValidationIssue]:
    """Require every cached SKILL.md to remain its exact discovered source."""
    issues: list[ValidationIssue] = []
    for skill in context.skills:
        try:
            unchanged = skill_source_matches_record(
                skill,
                context.root,
                budget=context.budget,
            )
        except AuthoredContentReadError as error:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=f"SKILL.md source cannot be reverified: {error}",
                )
            )
            continue
        if not unchanged:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message="SKILL.md changed after discovery",
                )
            )
    return issues


def validate_canonical_skills_tree_unchanged(
    context: ValidationContext,
) -> list[ValidationIssue]:
    """Require the complete canonical skills tree to remain the captured source."""
    try:
        current = snapshot_canonical_skills_tree(
            context.root,
            budget=context.budget,
        )
    except AuthoredContentReadError as error:
        return [
            ValidationIssue(
                scope="repository",
                message=f"canonical skills tree cannot be reverified: {error}",
            )
        ]
    if current == context.canonical_skills_tree:
        return []
    return [
        ValidationIssue(
            scope="repository",
            message="canonical skills tree changed after discovery",
        )
    ]


def deduplicate_issues(issues: Iterable[ValidationIssue]) -> list[ValidationIssue]:
    deduplicated: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        safe_issue = render_safe_diagnostic_issue(issue)
        key = (safe_issue.scope, safe_issue.message, safe_issue.severity)
        if key not in seen:
            seen.add(key)
            deduplicated.append(safe_issue)
    return deduplicated
