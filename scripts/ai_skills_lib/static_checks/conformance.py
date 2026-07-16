"""Pinned official conformance and dependency preflight."""

from __future__ import annotations

try:
    import skills_ref
except ImportError:  # pragma: no cover - exercised in dependency-preflight tests
    skills_ref = None

from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.context import ValidationContext, skill_scope


SKILLS_REF_INSTALL_COMMAND = "python3 -m pip install -r requirements-test.txt"


def preflight_reference_conformance() -> None:
    if skills_ref is None:
        raise RuntimeError(SKILLS_REF_INSTALL_COMMAND)


def validate_reference_conformance(
    context: ValidationContext,
) -> list[ValidationIssue]:
    preflight_reference_conformance()
    issues: list[ValidationIssue] = []
    for skill in context.skills:
        for problem in skills_ref.validate(skill.root):
            issues.append(
                ValidationIssue(scope=skill_scope(context, skill), message=problem)
            )
    return issues
