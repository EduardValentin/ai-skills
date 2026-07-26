"""Public façade for deterministic repository skill validation."""

from __future__ import annotations

from pathlib import Path

from scripts.ai_skills_lib.authored_content import (
    AuthoredRepositoryBudget,
    AuthoredRepositoryBudgetExceeded,
)
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.secret_patterns import SecretMatch, SecretPattern
from scripts.ai_skills_lib.static_checks.conformance import (
    preflight_reference_conformance,
    validate_reference_conformance,
)
from scripts.ai_skills_lib.static_checks.content import (
    find_static_secret_issues,
    validate_asset_files,
    validate_reference_files,
    validate_script_files,
    validate_skill_document,
)
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    build_validation_context,
    deduplicate_issues,
    render_safe_diagnostic_text,
    validate_canonical_skills_tree_unchanged,
    validate_skill_sources_unchanged,
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
    budget = AuthoredRepositoryBudget()
    repository_issues: list[ValidationIssue] = []
    try:
        repository_issues.extend(
            validate_repository_shape(resolved_root, budget=budget)
        )
        context = build_validation_context(resolved_root, budget=budget)
        return _run_static_context(context, repository_issues)
    except AuthoredRepositoryBudgetExceeded as error:
        repository_issues.append(
            ValidationIssue(scope="static", message=str(error))
        )
    except (OSError, ValueError) as error:
        repository_issues.append(ValidationIssue(scope="static", message=str(error)))
    return deduplicate_issues(repository_issues)


def run_reference_conformance(root: Path) -> list[ValidationIssue]:
    """Run pinned official conformance with one discovered skill context."""
    try:
        context = build_validation_context(
            root,
            budget=AuthoredRepositoryBudget(),
        )
    except AuthoredRepositoryBudgetExceeded as error:
        return [
            ValidationIssue(
                scope="reference conformance",
                message=render_safe_diagnostic_text(str(error)),
            )
        ]
    except (OSError, ValueError) as error:
        return [
            ValidationIssue(
                scope="reference conformance",
                message=render_safe_diagnostic_text(str(error)),
            )
        ]
    issues = validate_reference_conformance(context)
    issues.extend(validate_skill_sources_unchanged(context))
    issues.extend(validate_canonical_skills_tree_unchanged(context))
    issues.extend(
        validate_repository_shape(
            context.root,
            budget=context.budget,
        )
    )
    return deduplicate_issues(issues)


def run_pre_model_validation(root: Path) -> list[ValidationIssue]:
    """Run the complete deterministic trust gate before model-backed setup."""
    resolved_root = root.resolve()
    budget = AuthoredRepositoryBudget()
    repository_issues: list[ValidationIssue] = []
    try:
        repository_issues.extend(
            validate_repository_shape(resolved_root, budget=budget)
        )
        context = build_validation_context(resolved_root, budget=budget)
        issues = _run_static_context(context, repository_issues)
        issues.extend(validate_reference_conformance(context))
        issues.extend(validate_skill_sources_unchanged(context))
        issues.extend(validate_canonical_skills_tree_unchanged(context))
        issues.extend(
            validate_repository_shape(
                context.root,
                budget=context.budget,
            )
        )
        return deduplicate_issues(issues)
    except AuthoredRepositoryBudgetExceeded as error:
        repository_issues.append(
            ValidationIssue(scope="static", message=str(error))
        )
    except (OSError, ValueError) as error:
        repository_issues.append(ValidationIssue(scope="static", message=str(error)))
    return deduplicate_issues(repository_issues)


def run_ci_validation(root: Path) -> list[ValidationIssue]:
    """Use the same deterministic trust gate as model-backed commands."""
    return run_pre_model_validation(root)


def _run_static_context(
    context: ValidationContext, repository_issues: list[ValidationIssue]
) -> list[ValidationIssue]:
    issues = list(repository_issues)
    issues.extend(validate_discovered_layout(context))
    for skill in context.skills:
        issues.extend(validate_skill_root(context, skill))
        issues.extend(validate_skill_policy(context, skill, skill.source_text))
        issues.extend(validate_skill_document(context, skill, skill.source_text))
        issues.extend(validate_reference_files(context, skill))
        issues.extend(validate_script_files(context, skill))
        issues.extend(validate_asset_files(context, skill))
        issues.extend(validate_eval_files(context, skill))
    issues.extend(validate_skill_sources_unchanged(context))
    issues.extend(validate_canonical_skills_tree_unchanged(context))
    issues.extend(
        validate_repository_shape(
            context.root,
            budget=context.budget,
        )
    )
    return deduplicate_issues(issues)


__all__ = [
    "SecretMatch",
    "SecretPattern",
    "find_static_secret_issues",
    "preflight_reference_conformance",
    "run_ci_validation",
    "run_pre_model_validation",
    "run_reference_conformance",
    "run_static_validation",
]
