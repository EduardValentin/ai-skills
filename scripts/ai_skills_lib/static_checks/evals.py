"""Eval, trigger, and fixture definition checks."""

from __future__ import annotations

from collections.abc import Iterator
import json
from pathlib import PurePosixPath
from typing import Any

from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.content import (
    authored_file,
    is_external_reference,
    read_text_fixture,
    walk_authored_files,
)
from scripts.ai_skills_lib.static_checks.context import (
    AuthoredFile,
    ValidationContext,
    skill_scope,
)
from scripts.ai_skills_lib.static_checks.content import find_static_secret_issues
from scripts.ai_skills_lib.trigger_definitions import validate_trigger_query_document


def validate_eval_files(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    issues: list[ValidationIssue] = []
    evals_root = skill.root / "evals"
    evals_path = evals_root / "evals.json"
    triggers_path = evals_root / "triggers.json"
    evals_source = authored_file(evals_path, skill.root)
    triggers_source = authored_file(triggers_path, skill.root)

    if evals_source is None:
        issues.append(ValidationIssue(scope=scope, message="missing evals/evals.json"))
    if triggers_source is None:
        issues.append(ValidationIssue(scope=scope, message="missing evals/triggers.json"))

    evals_data, load_issues = _load_required_json(context, skill, evals_source)
    issues.extend(load_issues)
    triggers_data, load_issues = _load_required_json(context, skill, triggers_source)
    issues.extend(load_issues)

    files = list(walk_authored_files(evals_root, skill.root))
    required_resolved = {
        source.resolved_path for source in (evals_source, triggers_source) if source is not None
    }
    for source in files:
        text = read_text_fixture(source)
        if text is not None:
            issues.extend(_secret_issues(context, skill, source, text))
        if source.logical_path.suffix == ".json" and source.resolved_path not in required_resolved:
            _, json_issues = _load_json(context, skill, source)
            issues.extend(json_issues)

    if evals_data is not None:
        evals = evals_data.get("evals") if isinstance(evals_data, dict) else None
        if not isinstance(evals, list) or not evals:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="evals/evals.json must contain an 'evals' list",
                )
            )
        else:
            for index, item in enumerate(evals):
                if not isinstance(item, dict):
                    issues.append(
                        ValidationIssue(
                            scope=scope,
                            message=f"evals/evals.json eval {index} must be an object",
                        )
                    )
                else:
                    issues.extend(_fixture_path_issues(skill, scope, item))

    if triggers_data is not None:
        issues.extend(validate_trigger_query_document(triggers_data, skill.name, scope))
    return issues


def _load_required_json(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile | None
) -> tuple[Any | None, list[ValidationIssue]]:
    if source is None:
        return None, []
    return _load_json(context, skill, source)


def _load_json(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile
) -> tuple[Any | None, list[ValidationIssue]]:
    try:
        return json.loads(source.resolved_path.read_text(encoding="utf-8")), []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    f"{source.logical_path.relative_to(skill.root)} contains invalid JSON: {error}"
                ),
            )
        ]


def _secret_issues(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile, text: str
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            scope=skill_scope(context, skill),
            message=(
                f"{source.logical_path.relative_to(skill.root)}:{finding.line}:{finding.column}: "
                f"high-confidence secret {finding.pattern} ({finding.category}); value redacted"
            ),
        )
        for finding in find_static_secret_issues(text, source.logical_path)
    ]


def _fixture_path_issues(skill: SkillRecord, scope: str, value: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and "fixture" in key.lower():
                for fixture in _string_values(child):
                    issues.extend(_validate_fixture_path(skill, scope, fixture))
            else:
                issues.extend(_fixture_path_issues(skill, scope, child))
    elif isinstance(value, list):
        for child in value:
            issues.extend(_fixture_path_issues(skill, scope, child))
    return issues


def _string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str):
                yield child


def _validate_fixture_path(
    skill: SkillRecord, scope: str, fixture: str
) -> list[ValidationIssue]:
    if is_external_reference(fixture):
        return []
    pure_path = PurePosixPath(fixture)
    if pure_path.is_absolute() or ".." in pure_path.parts or "\\" in fixture:
        return [
            ValidationIssue(
                scope=scope,
                message=f"fixture path must stay inside the skill: {fixture}",
            )
        ]
    if fixture.startswith("evals/"):
        path = skill.root / pure_path
    elif fixture.startswith("fixtures/"):
        path = skill.root / "evals" / pure_path
    else:
        path = skill.root / "evals" / pure_path
    if authored_file(path, skill.root) is None:
        return [
            ValidationIssue(scope=scope, message=f"fixture path does not exist: {fixture}")
        ]
    return []
