"""Metadata, configuration, and explicit collaborator policy checks."""

from __future__ import annotations

import re

from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.context import ValidationContext, skill_scope


_APPROVED_STATUSES = frozenset(
    {"public-ready", "config-required", "local-required", "experimental"}
)
_CONFIG_VARIABLE_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET|_PATH|_FILE|_DIR|_CONFIG|_HOME)\b"
)
_SKILL_REFERENCE_PATTERNS = (
    re.compile(r"`(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)`\s+skill\b", re.IGNORECASE),
    re.compile(r"\$(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)\b"),
    re.compile(r"skill://(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)\b", re.IGNORECASE),
    re.compile(
        r"skills/(?:[a-z0-9-]+/)?(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)/SKILL\.md",
        re.IGNORECASE,
    ),
)
_COLLABORATOR_PATTERN = re.compile(
    r"(?:\b(?:native\s+)?agents?\b|\b(?:codex|claude|antigravity|cursor|gemini)\s+harness\b|"
    r"\bharness(?:es)?\b|\btools?\b|\bmcp__[a-z0-9_]+|\b[a-z][a-z0-9_]*__"
    r"[a-z0-9_]+|\bspawn_agent\b)",
    re.IGNORECASE,
)
_COLLABORATION_BEHAVIOR_PATTERN = re.compile(
    r"\b(?:requires?|required|needs?|available|unavailable|fallback|without|optional|configured|"
    r"installed)\b",
    re.IGNORECASE,
)


def validate_skill_policy(
    context: ValidationContext, skill: SkillRecord, skill_text: str
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    issues: list[ValidationIssue] = []
    metadata = skill.frontmatter.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    status = metadata.get("status")
    if status is None:
        issues.append(ValidationIssue(scope=scope, message="metadata.status is required"))
    elif status not in _APPROVED_STATUSES:
        approved = ", ".join(sorted(_APPROVED_STATUSES))
        issues.append(
            ValidationIssue(scope=scope, message=f"metadata.status must be one of: {approved}")
        )

    allows_tool_references = metadata.get("allows_tool_references")
    if allows_tool_references not in (None, "true", "false"):
        issues.append(
            ValidationIssue(
                scope=scope,
                message="metadata.allows_tool_references must be 'true' or 'false'",
            )
        )

    compatibility = skill.frontmatter.get("compatibility")
    compatibility_text = compatibility if isinstance(compatibility, str) else ""
    if status in {"config-required", "local-required"} and not compatibility_text.strip():
        issues.append(
            ValidationIssue(
                scope=scope,
                message=f"metadata.status '{status}' requires non-empty compatibility",
            )
        )
    if (
        status == "config-required"
        and compatibility_text.strip()
        and not _CONFIG_VARIABLE_PATTERN.search(compatibility_text)
    ):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "config-required compatibility must name an environment variable or "
                    "config-file path variable"
                ),
            )
        )

    other_skill_references = explicit_skill_references(skill_text) - {skill.name}
    mentions_collaborator = bool(other_skill_references) or bool(
        _COLLABORATOR_PATTERN.search(skill_text)
    )
    if mentions_collaborator and allows_tool_references != "true":
        issues.append(
            ValidationIssue(
                scope=scope,
                message="collaborator reference requires metadata.allows_tool_references: 'true'",
            )
        )
    if allows_tool_references == "true" and not _documents_collaboration(
        compatibility_text
    ):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "metadata.allows_tool_references: 'true' must document collaborator "
                    "requirements or fallback behavior in compatibility"
                ),
            )
        )
    for referenced_name in sorted(other_skill_references - context.public_names):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=f"references unknown public skill '{referenced_name}'",
            )
        )
    return issues


def explicit_skill_references(text: str) -> set[str]:
    references: set[str] = set()
    for pattern in _SKILL_REFERENCE_PATTERNS:
        references.update(match.group("name").lower() for match in pattern.finditer(text))
    return references


def _documents_collaboration(compatibility: str) -> bool:
    if not compatibility.strip() or not _COLLABORATION_BEHAVIOR_PATTERN.search(compatibility):
        return False
    return bool(
        _COLLABORATOR_PATTERN.search(compatibility)
        or explicit_skill_references(compatibility)
        or re.search(r"\b(?:fallback|unavailable|without)\b", compatibility, re.IGNORECASE)
    )
