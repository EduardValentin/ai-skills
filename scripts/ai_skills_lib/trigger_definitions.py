"""Shared authored trigger-query discovery and validation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.ai_skills_lib.authored_content import (
    AuthoredContentReadError,
    AuthoredContentTooLarge,
    AuthoredRepositoryBudget,
    AuthoredRepositoryBudgetExceeded,
    BoundedJsonError,
    authored_file,
    find_additional_decoded_json_secret_issues,
    find_static_secret_issues,
    read_bounded_authored_bytes,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.core import (
    SkillRecord,
    discover_testable_skills,
    snapshot_canonical_skills_tree,
)
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text
from scripts.ai_skills_lib.static_checks.context import render_safe_diagnostic_issues


_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "ai-skills" / "triggers.schema.json"
)
_MAX_QUERY_BYTES = 16 * 1024
MAX_TRIGGER_DEFINITION_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class TriggerQuery:
    """One authored installed-catalog pickup scenario."""

    id: str
    query: str
    should_trigger: bool


@dataclass(frozen=True)
class SkillTriggerQueries:
    """Validated trigger scenarios for one discovered skill."""

    skill: SkillRecord
    queries: tuple[TriggerQuery, ...]


class TriggerDefinitionError(RuntimeError):
    """Raised when trigger execution is requested for invalid authored files."""

    def __init__(self, issues: Sequence[ValidationIssue]):
        super().__init__("trigger definitions are invalid")
        self.issues = tuple(issues)


def validate_trigger_query_files(root: Path) -> list[ValidationIssue]:
    """Discover every skill and validate its trigger file with one contract."""
    _, issues = _inspect_trigger_query_files(root)
    return render_safe_diagnostic_issues(issues)


def load_trigger_queries(root: Path) -> tuple[SkillTriggerQueries, ...]:
    """Discover, validate, and load typed trigger definitions in one pass."""
    definitions, issues = _inspect_trigger_query_files(root)
    safe_issues = render_safe_diagnostic_issues(issues)
    if safe_issues:
        raise TriggerDefinitionError(safe_issues)
    return definitions


def _inspect_trigger_query_files(
    root: Path,
) -> tuple[tuple[SkillTriggerQueries, ...], list[ValidationIssue]]:
    budget = AuthoredRepositoryBudget()
    try:
        initial_skills_tree = snapshot_canonical_skills_tree(
            root,
            budget=budget,
        )
        skills = discover_testable_skills(root, budget=budget)
    except (OSError, UnicodeDecodeError, ValueError) as error:
        diagnostic = bounded_redacted_runtime_text(str(error), 2048)
        return (), [
            ValidationIssue(
                scope="trigger discovery",
                message=f"cannot discover skills: {diagnostic}",
            )
        ]

    issues: list[ValidationIssue] = []
    definitions: list[SkillTriggerQueries] = []
    name_counts = Counter(skill.name for skill in skills)
    for name, count in sorted(name_counts.items()):
        if count > 1:
            issues.append(
                ValidationIssue(
                    scope="trigger discovery",
                    message=f"duplicate skill name '{name}' appears {count} times",
                )
            )
    for skill in skills:
        scope = str(skill.root.relative_to(root))
        if skill.root.name != skill.name:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"folder name '{skill.root.name}' must match skill name "
                        f"'{skill.name}'"
                    ),
                )
            )
        path = skill.root / "evals" / "triggers.json"
        if path.parent.is_symlink() or path.is_symlink():
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "evals/triggers.json must be a contained non-symlink "
                        "regular file"
                    ),
                )
            )
            continue
        source = authored_file(path, skill.root)
        if source is None:
            message = (
                "missing evals/triggers.json"
                if not path.exists()
                else "evals/triggers.json must be a contained non-symlink regular file"
            )
            issues.append(ValidationIssue(scope=scope, message=message))
            continue
        try:
            raw = read_bounded_authored_bytes(
                source,
                maximum_bytes=MAX_TRIGGER_DEFINITION_BYTES,
                allowed_root=skill.root,
                containment_root=root,
                budget=budget,
            )
            text = raw.decode("utf-8")
        except AuthoredRepositoryBudgetExceeded as error:
            issues.append(
                ValidationIssue(
                    scope="trigger discovery",
                    message=bounded_redacted_runtime_text(str(error), 2048),
                )
            )
            return (), issues
        except AuthoredContentTooLarge:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "evals/triggers.json exceeds the "
                        "2 MiB trigger definition limit"
                    ),
                )
            )
            continue
        except (AuthoredContentReadError, UnicodeDecodeError) as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"cannot read evals/triggers.json: {error}",
                )
            )
            continue
        secret_findings = find_static_secret_issues(text, path)
        for finding in secret_findings:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"evals/triggers.json:{finding.line}:{finding.column}: "
                        f"high-confidence secret {finding.pattern}; value redacted"
                    ),
                )
            )
        try:
            document = strict_bounded_json_loads(
                text,
                maximum_bytes=MAX_TRIGGER_DEFINITION_BYTES,
            )
        except BoundedJsonError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"evals/triggers.json contains invalid JSON: {error}",
                )
            )
            continue
        try:
            decoded_findings = find_additional_decoded_json_secret_issues(
                document,
                path,
                maximum_bytes=MAX_TRIGGER_DEFINITION_BYTES,
                raw_findings=secret_findings,
            )
        except BoundedJsonError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "evals/triggers.json cannot be secret-scanned after JSON "
                        f"decoding: {error}"
                    ),
                )
            )
            continue
        for finding in decoded_findings:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "evals/triggers.json contains a high-confidence secret "
                        f"after JSON decoding: {finding.pattern}; value redacted"
                    ),
                )
            )
        document_issues = validate_trigger_query_document(document, skill.name, scope)
        issues.extend(document_issues)
        if secret_findings or decoded_findings or document_issues:
            continue
        definitions.append(
            SkillTriggerQueries(
                skill=skill,
                queries=tuple(
                    TriggerQuery(
                        id=query["id"],
                        query=query["query"],
                        should_trigger=query["should_trigger"],
                    )
                    for query in document["queries"]
                ),
            )
        )
    try:
        final_skills_tree = snapshot_canonical_skills_tree(
            root,
            budget=budget,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        diagnostic = bounded_redacted_runtime_text(str(error), 2048)
        issues.append(
            ValidationIssue(
                scope="trigger discovery",
                message=f"cannot reverify canonical skills tree: {diagnostic}",
            )
        )
        return (), issues
    if final_skills_tree != initial_skills_tree:
        issues.append(
            ValidationIssue(
                scope="trigger discovery",
                message=(
                    "canonical skills tree changed during definition loading"
                ),
            )
        )
        return (), issues
    return tuple(definitions), issues


def validate_trigger_query_document(
    document: object,
    expected_skill_name: str,
    scope: str,
) -> list[ValidationIssue]:
    """Validate one parsed trigger document and its discovered-skill identity."""
    issues: list[ValidationIssue] = []
    try:
        validator = _trigger_validator()
    except (OSError, json.JSONDecodeError) as error:
        return [ValidationIssue(scope=scope, message=f"cannot load trigger schema: {error}")]

    for error in sorted(validator.iter_errors(document), key=_validation_error_key):
        if error.validator == "contains" and tuple(error.absolute_path) == ("queries",):
            continue
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "evals/triggers.json schema error at "
                    f"{_validation_path(error.absolute_path)}: {error.validator}"
                ),
            )
        )
    if not isinstance(document, Mapping):
        return issues
    skill_name = document.get("skill_name")
    if isinstance(skill_name, str) and skill_name != expected_skill_name:
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    f"evals/triggers.json skill_name '{skill_name}' must match "
                    f"skill name '{expected_skill_name}'"
                ),
            )
        )
    queries = document.get("queries")
    if isinstance(queries, Sequence) and not isinstance(queries, (str, bytes)):
        decisions = [
            query.get("should_trigger")
            for query in queries
            if isinstance(query, Mapping) and type(query.get("should_trigger")) is bool
        ]
        if True not in decisions:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="evals/triggers.json requires a should_trigger: true query",
                )
            )
        if False not in decisions:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="evals/triggers.json requires a should_trigger: false query",
                )
            )
        identifiers = [
            query.get("id")
            for query in queries
            if isinstance(query, Mapping) and isinstance(query.get("id"), str)
        ]
        seen: set[str] = set()
        for identifier in identifiers:
            if identifier in seen:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"evals/triggers.json has duplicate query id '{identifier}'",
                    )
                )
            seen.add(identifier)
        for query in queries:
            if not isinstance(query, Mapping):
                continue
            query_text = query.get("query")
            if not isinstance(query_text, str):
                continue
            if len(query_text.encode("utf-8")) <= _MAX_QUERY_BYTES:
                continue
            identifier = query.get("id")
            label = f" '{identifier}'" if isinstance(identifier, str) else ""
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"evals/triggers.json query{label} exceeds the "
                        "16 KiB UTF-8 limit"
                    ),
                )
            )
    return issues


@lru_cache(maxsize=1)
def _trigger_validator() -> Draft202012Validator:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def _validation_error_key(error) -> tuple[tuple[str, ...], str]:
    return tuple(str(part) for part in error.absolute_path), str(error.validator)


def _validation_path(parts: Sequence[object]) -> str:
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered
