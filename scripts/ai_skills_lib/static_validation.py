"""Public façade for deterministic repository skill validation."""

from __future__ import annotations

from pathlib import Path

from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.secret_patterns import SecretMatch, SecretPattern
from scripts.ai_skills_lib.static_checks.conformance import (
    preflight_reference_conformance,
    validate_reference_conformance,
)
from scripts.ai_skills_lib.static_checks.content import (
    authored_file,
    find_static_secret_issues,
    read_authored_text,
    validate_reference_files,
    validate_script_files,
    validate_skill_document,
)
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    build_validation_context,
    deduplicate_issues,
)
from scripts.ai_skills_lib.static_checks.evals import validate_eval_files
from scripts.ai_skills_lib.static_checks.policy import validate_skill_policy
from scripts.ai_skills_lib.static_checks.topology import (
    validate_discovered_layout,
    validate_repository_shape,
    validate_skill_root,
)


def run_static_validation(root: Path) -> list[ValidationIssue]:
    """Apply local repository policy to one discovered skill context."""
    resolved_root = root.resolve()
    repository_issues = validate_repository_shape(resolved_root)
    try:
        context = build_validation_context(resolved_root)
    except (OSError, ValueError) as error:
        repository_issues.append(ValidationIssue(scope="static", message=str(error)))
        return deduplicate_issues(repository_issues)
    return _run_static_context(context, repository_issues)


def run_reference_conformance(root: Path) -> list[ValidationIssue]:
    """Run pinned official conformance with one discovered skill context."""
    preflight_reference_conformance()
    try:
        context = build_validation_context(root)
    except (OSError, ValueError) as error:
        return [ValidationIssue(scope="reference conformance", message=str(error))]
    return validate_reference_conformance(context)


def run_ci_validation(root: Path) -> list[ValidationIssue]:
    """Run static then reference checks from a single discovery pass."""
    preflight_reference_conformance()
    resolved_root = root.resolve()
    repository_issues = validate_repository_shape(resolved_root)
    try:
        context = build_validation_context(resolved_root)
    except (OSError, ValueError) as error:
        repository_issues.append(ValidationIssue(scope="static", message=str(error)))
        return deduplicate_issues(repository_issues)
    issues = _run_static_context(context, repository_issues)
    issues.extend(validate_reference_conformance(context))
    return deduplicate_issues(issues)


def _run_static_context(
    context: ValidationContext, repository_issues: list[ValidationIssue]
) -> list[ValidationIssue]:
    issues = list(repository_issues)
    issues.extend(validate_discovered_layout(context))
    for skill in context.skills:
        issues.extend(validate_skill_root(context, skill))
        skill_source = authored_file(skill.path, skill.root)
        if skill_source is not None:
            skill_text, read_issues = read_authored_text(context, skill, skill_source)
            issues.extend(read_issues)
            if skill_text is not None:
                issues.extend(validate_skill_policy(context, skill, skill_text))
                issues.extend(validate_skill_document(context, skill, skill_text))
        issues.extend(validate_reference_files(context, skill))
        issues.extend(validate_script_files(context, skill))
        issues.extend(validate_eval_files(context, skill))
    return deduplicate_issues(issues)


__all__ = [
    "SecretMatch",
    "SecretPattern",
    "find_static_secret_issues",
    "preflight_reference_conformance",
    "run_ci_validation",
    "run_reference_conformance",
    "run_static_validation",
]
