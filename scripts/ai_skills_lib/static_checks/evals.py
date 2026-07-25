"""Eval, trigger, and fixture definition checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.authored_content import (
    AuthoredContentReadError,
    AuthoredContentTooLarge,
    AuthoredTreeEntry,
    find_additional_decoded_json_secret_issues,
    find_static_secret_issues_in_bytes,
    read_bounded_authored_bytes,
    snapshot_authored_tree,
    sorted_authored_entries,
)
from scripts.ai_skills_lib.bounded_json import (
    BoundedJsonError,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.eval_definitions import (
    MAX_EVAL_DEFINITION_BYTES,
    MAX_EVAL_FIXTURE_FILE_BYTES,
    validate_behavior_eval_document,
)
from scripts.ai_skills_lib.fixture_proxy import (
    FixtureProxyError,
    load_fixture_definition_bytes,
)
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.sandbox_runtime import EvalRuntimeManifest, ManifestError
from scripts.ai_skills_lib.secret_patterns import (
    SecretMatch,
    bounded_redacted_runtime_text,
)
from scripts.ai_skills_lib.static_checks.content import (
    authored_file,
    find_static_secret_issues,
    walk_authored_files,
)
from scripts.ai_skills_lib.static_checks.context import (
    AuthoredFile,
    ValidationContext,
    render_safe_diagnostic_path,
    render_safe_diagnostic_text,
    skill_scope,
)
from scripts.ai_skills_lib.trigger_definitions import validate_trigger_query_document


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_RUNTIME_MANIFEST_PATH = _REPOSITORY_ROOT / "config" / "eval-runtime.json"
_MOCKSERVER_INITIALIZATION = "mockserverInitialization.json"
_REQUIRED_EVAL_FILES = frozenset({"evals.json", "triggers.json"})
_ALLOWED_EVAL_ROOT_ENTRIES = _REQUIRED_EVAL_FILES | {"fixtures"}


@dataclass(frozen=True)
class _EvalRootInspection:
    evals_root: Path | None
    fixtures_root: Path | None
    evals_source: AuthoredFile | None
    triggers_source: AuthoredFile | None
    issues: tuple[ValidationIssue, ...]


def validate_eval_files(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    inspection = _inspect_eval_root(context, skill)
    issues = list(inspection.issues)
    evals_source = inspection.evals_source
    triggers_source = inspection.triggers_source
    loaded_content: dict[Path, bytes] = {}
    raw_secret_findings: dict[Path, tuple[SecretMatch, ...]] = {}
    files: tuple[AuthoredFile, ...] = ()
    tree_before: tuple[AuthoredTreeEntry, ...] = ()
    if inspection.evals_root is not None:
        try:
            tree_before = snapshot_authored_tree(
                inspection.evals_root,
                budget=context.budget,
            )
            files = tuple(
                walk_authored_files(
                    inspection.evals_root,
                    skill.root,
                    budget=context.budget,
                )
            )
        except AuthoredContentReadError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"cannot capture one coherent eval definition tree: {error}",
                )
            )
            return issues

    required_logical = {
        skill.root / "evals" / filename for filename in _REQUIRED_EVAL_FILES
    }
    mockserver_sources: list[AuthoredFile] = []
    for source in files:
        if source.logical_path.name == _MOCKSERVER_INITIALIZATION:
            mockserver_sources.append(source)
        maximum_bytes = (
            MAX_EVAL_DEFINITION_BYTES
            if source.logical_path in required_logical
            else MAX_EVAL_FIXTURE_FILE_BYTES
        )
        try:
            content = read_bounded_authored_bytes(
                source,
                maximum_bytes=maximum_bytes,
                allowed_root=skill.root,
                containment_root=context.root,
                budget=context.budget,
            )
            loaded_content[source.logical_path] = content
        except AuthoredContentTooLarge:
            limit = (
                "2 MiB eval definition limit"
                if source.logical_path in required_logical
                else "4 MiB eval fixture file limit"
            )
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)} "
                        "exceeds the "
                        f"{limit}"
                    ),
                )
            )
            continue
        except AuthoredContentReadError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "cannot read "
                        f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}: "
                        f"{error}"
                    ),
                )
            )
            continue
        source_secret_findings = tuple(
            find_static_secret_issues_in_bytes(
                content,
                source.logical_path,
            )
        )
        raw_secret_findings[source.logical_path] = source_secret_findings
        issues.extend(
            _secret_issues(context, skill, source, source_secret_findings)
        )
        if (
            source.logical_path.suffix.casefold() == ".json"
            and source.logical_path not in required_logical
        ):
            _, json_issues = _parse_json_content(
                context,
                skill,
                source,
                content,
                maximum_bytes=MAX_EVAL_FIXTURE_FILE_BYTES,
                raw_secret_findings=source_secret_findings,
            )
            issues.extend(json_issues)

    if inspection.evals_root is not None:
        try:
            tree_after = snapshot_authored_tree(
                inspection.evals_root,
                budget=context.budget,
            )
        except AuthoredContentReadError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"cannot verify the captured eval definition tree: {error}",
                )
            )
            return issues
        if tree_after != tree_before:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="eval definition tree changed during validation",
                )
            )
            return issues

    evals_data = None
    if evals_source is not None:
        evals_content = loaded_content.get(evals_source.logical_path)
        if evals_content is not None:
            evals_data, load_issues = _parse_json_content(
                context,
                skill,
                evals_source,
                evals_content,
                maximum_bytes=MAX_EVAL_DEFINITION_BYTES,
                raw_secret_findings=raw_secret_findings.get(
                    evals_source.logical_path,
                    (),
                ),
            )
            issues.extend(load_issues)
    triggers_data = None
    if triggers_source is not None:
        triggers_content = loaded_content.get(triggers_source.logical_path)
        if triggers_content is not None:
            triggers_data, load_issues = _parse_json_content(
                context,
                skill,
                triggers_source,
                triggers_content,
                maximum_bytes=MAX_EVAL_DEFINITION_BYTES,
                raw_secret_findings=raw_secret_findings.get(
                    triggers_source.logical_path,
                    (),
                ),
            )
            issues.extend(load_issues)

    issues.extend(
        _validate_fixture_topology(
            context,
            skill,
            evals_data,
            inspection.fixtures_root,
        )
    )
    if evals_data is not None:
        issues.extend(
            validate_behavior_eval_document(
                evals_data,
                skill,
                scope,
                budget=context.budget,
                loaded_content=loaded_content,
            )
        )
        issues.extend(
            _validate_mockserver_initializations(
                context,
                skill,
                evals_data,
                mockserver_sources,
                loaded_content,
            )
        )

    if triggers_data is not None:
        issues.extend(validate_trigger_query_document(triggers_data, skill.name, scope))
    return issues


def _inspect_eval_root(
    context: ValidationContext, skill: SkillRecord
) -> _EvalRootInspection:
    scope = skill_scope(context, skill)
    issues: list[ValidationIssue] = []
    evals_root = skill.root / "evals"
    if evals_root.is_symlink():
        return _EvalRootInspection(
            evals_root=None,
            fixtures_root=None,
            evals_source=None,
            triggers_source=None,
            issues=(
                ValidationIssue(
                    scope=scope,
                    message="evals must be a contained non-symlink directory",
                ),
            ),
        )
    if not evals_root.exists():
        return _EvalRootInspection(
            evals_root=None,
            fixtures_root=None,
            evals_source=None,
            triggers_source=None,
            issues=(
                ValidationIssue(scope=scope, message="missing evals/evals.json"),
                ValidationIssue(scope=scope, message="missing evals/triggers.json"),
            ),
        )
    resolved_skill_root = skill.root.resolve(strict=True)
    if not _is_contained_non_symlink_directory(evals_root, resolved_skill_root):
        return _EvalRootInspection(
            evals_root=None,
            fixtures_root=None,
            evals_source=None,
            triggers_source=None,
            issues=(
                ValidationIssue(
                    scope=scope,
                    message="evals must be a contained non-symlink directory",
                ),
            ),
        )

    try:
        entries = {
            entry.name: entry
            for entry in sorted_authored_entries(
                evals_root,
                budget=context.budget,
            )
        }
    except OSError as error:
        return _EvalRootInspection(
            evals_root=None,
            fixtures_root=None,
            evals_source=None,
            triggers_source=None,
            issues=(
                ValidationIssue(scope=scope, message=f"cannot inspect evals: {error}"),
            ),
        )

    for name in sorted(entries.keys() - _ALLOWED_EVAL_ROOT_ENTRIES):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "unsupported evals entry: "
                    f"{render_safe_diagnostic_text(name)}"
                ),
            )
        )

    required_sources: dict[str, AuthoredFile | None] = {}
    for filename in sorted(_REQUIRED_EVAL_FILES):
        path = evals_root / filename
        if filename not in entries:
            issues.append(
                ValidationIssue(scope=scope, message=f"missing evals/{filename}")
            )
            required_sources[filename] = None
            continue
        if not _is_contained_non_symlink_file(path, resolved_skill_root):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"evals/{filename} must be a contained non-symlink regular file"
                    ),
                )
            )
            required_sources[filename] = None
            continue
        required_sources[filename] = authored_file(path, skill.root)

    fixtures_root: Path | None = None
    if "fixtures" in entries:
        candidate = evals_root / "fixtures"
        if _is_contained_non_symlink_directory(candidate, resolved_skill_root):
            fixtures_root = candidate
        else:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "evals/fixtures must be a contained non-symlink directory"
                    ),
                )
            )
    return _EvalRootInspection(
        evals_root=evals_root,
        fixtures_root=fixtures_root,
        evals_source=required_sources["evals.json"],
        triggers_source=required_sources["triggers.json"],
        issues=tuple(issues),
    )


def _validate_fixture_topology(
    context: ValidationContext,
    skill: SkillRecord,
    document: object,
    fixtures_root: Path | None,
) -> list[ValidationIssue]:
    if fixtures_root is None:
        return []
    scope = skill_scope(context, skill)
    try:
        tree = snapshot_authored_tree(
            fixtures_root,
            budget=context.budget,
        )
    except AuthoredContentReadError as error:
        return [
            ValidationIssue(
                scope=scope,
                message=f"cannot inspect evals/fixtures: {error}",
            )
        ]
    case_entries = tuple(
        entry
        for entry in tree
        if entry.logical_path.parent == fixtures_root
    )
    if not case_entries:
        return [
            ValidationIssue(
                scope=scope,
                message="empty directory is not allowed: evals/fixtures",
            )
        ]

    declared_cases = _declared_eval_cases(document)
    resolved_fixtures_root = fixtures_root.resolve(strict=True)
    issues: list[ValidationIssue] = []
    for case_entry in case_entries:
        case_root = case_entry.logical_path
        if (
            not case_entry.is_directory
            or case_entry.resolved_path is None
            or not case_entry.resolved_path.is_relative_to(
                resolved_fixtures_root
            )
        ):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "eval fixture case entry must be a contained non-symlink "
                        "directory: "
                        f"{render_safe_diagnostic_path(case_root, relative_to=skill.root)}"
                    ),
                )
            )
            continue
        raw_case = declared_cases.get(case_root.name)
        if raw_case is None:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "fixture tree belongs to undeclared eval case "
                        f"'{render_safe_diagnostic_text(case_root.name)}'"
                    ),
                )
            )
            continue
        issues.extend(
            _validate_case_fixture_tree(
                context,
                skill,
                case_entry,
                tuple(
                    entry
                    for entry in tree
                    if case_root in entry.logical_path.parents
                ),
                raw_case,
            )
        )
    return issues


def _declared_eval_cases(document: object) -> dict[str, Mapping[object, object]]:
    if not isinstance(document, Mapping):
        return {}
    raw_cases = document.get("evals")
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, (str, bytes)):
        return {}
    declared: dict[str, Mapping[object, object]] = {}
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            continue
        case_id = raw_case.get("id")
        if isinstance(case_id, str):
            declared[case_id] = raw_case
    return declared


def _validate_case_fixture_tree(
    context: ValidationContext,
    skill: SkillRecord,
    case_entry: AuthoredTreeEntry,
    entries: tuple[AuthoredTreeEntry, ...],
    raw_case: Mapping[object, object],
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    case_root = case_entry.logical_path
    allowed_files = _declared_case_fixture_files(skill, case_root.name, raw_case)
    resolved_case_root = case_entry.resolved_path
    assert resolved_case_root is not None
    issues: list[ValidationIssue] = []
    if case_entry.child_count == 0:
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "empty directory is not allowed: "
                    f"{render_safe_diagnostic_path(case_root, relative_to=skill.root)}"
                ),
            )
        )
    for entry in entries:
        relative = render_safe_diagnostic_path(
            entry.logical_path,
            relative_to=skill.root,
        )
        if entry.is_symlink:
            resolution = entry.resolved_path
            if resolution is None:
                kind = entry.symlink_error or "invalid"
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"{kind} eval fixture symlink: {relative}",
                    )
                )
                continue
            if not resolution.is_relative_to(resolved_case_root):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            "eval fixture symlink target must stay inside its case: "
                            f"{relative}"
                        ),
                    )
                )
                continue
            if not _path_is_declared(entry.logical_path, allowed_files):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"undeclared eval fixture entry: {relative}",
                    )
                )
            continue
        if entry.is_directory:
            if entry.child_count == 0:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"empty directory is not allowed: {relative}",
                    )
                )
        elif entry.is_regular_file:
            if entry.logical_path not in allowed_files:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"undeclared eval fixture file: {relative}",
                    )
                )
        else:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"unsupported eval fixture entry: {relative}",
                )
            )
    return issues


def _declared_case_fixture_files(
    skill: SkillRecord,
    case_id: str,
    raw_case: Mapping[object, object],
) -> set[Path]:
    case_prefix = PurePosixPath("fixtures") / case_id
    declared: set[Path] = {
        skill.root / "evals" / case_prefix / _MOCKSERVER_INITIALIZATION
    }
    raw_files = raw_case.get("files")
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for raw_path in raw_files:
            fixture_path = _case_bound_fixture_path(raw_path, case_prefix)
            if fixture_path is not None:
                declared.add(skill.root / "evals" / fixture_path)
    raw_checks = raw_case.get("checks")
    if isinstance(raw_checks, Sequence) and not isinstance(raw_checks, (str, bytes)):
        for raw_check in raw_checks:
            if not isinstance(raw_check, Mapping):
                continue
            fixture_path = _case_bound_fixture_path(
                raw_check.get("schema"), case_prefix
            )
            if fixture_path is not None:
                declared.add(skill.root / "evals" / fixture_path)
    return declared


def _case_bound_fixture_path(
    raw_path: object, case_prefix: PurePosixPath
) -> PurePosixPath | None:
    if not isinstance(raw_path, str) or "\\" in raw_path:
        return None
    path = PurePosixPath(raw_path)
    if path.is_absolute() or ".." in path.parts or path == case_prefix:
        return None
    if case_prefix not in path.parents:
        return None
    return path


def _path_is_declared(path: Path, declared_files: set[Path]) -> bool:
    return path in declared_files or any(
        path in declared.parents for declared in declared_files
    )


def _is_contained_non_symlink_directory(path: Path, resolved_root: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        return path.resolve(strict=True).is_relative_to(resolved_root)
    except (OSError, RuntimeError):
        return False


def _is_contained_non_symlink_file(path: Path, resolved_root: Path) -> bool:
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return path.resolve(strict=True).is_relative_to(resolved_root)
    except (OSError, RuntimeError):
        return False


def _validate_mockserver_initializations(
    context: ValidationContext,
    skill: SkillRecord,
    document: object,
    authored_files: list[AuthoredFile],
    loaded_content: Mapping[Path, bytes],
) -> list[ValidationIssue]:
    if not isinstance(document, dict):
        return []
    raw_cases = document.get("evals")
    if not isinstance(raw_cases, list):
        return []
    declared_cases = {
        raw_case.get("id")
        for raw_case in raw_cases
        if isinstance(raw_case, dict) and isinstance(raw_case.get("id"), str)
    }
    evals_root = skill.root / "evals"
    fixture_root = evals_root / "fixtures"
    candidates = {
        source.logical_path
        for source in authored_files
        if source.logical_path.name == _MOCKSERVER_INITIALIZATION
    }
    resolved_skill_root = skill.root.resolve(strict=True)
    if _is_contained_non_symlink_directory(fixture_root, resolved_skill_root):
        try:
            case_roots = tuple(
                sorted_authored_entries(
                    fixture_root,
                    budget=context.budget,
                )
            )
        except OSError:
            case_roots = ()
        for case_root in case_roots:
            if not _is_contained_non_symlink_directory(
                case_root, fixture_root.resolve(strict=True)
            ):
                continue
            initialization = case_root / _MOCKSERVER_INITIALIZATION
            if initialization.exists() or initialization.is_symlink():
                candidates.add(initialization)

    issues: list[ValidationIssue] = []
    manifest: EvalRuntimeManifest | None = None
    for path in sorted(candidates, key=str):
        try:
            relative = path.relative_to(evals_root)
        except ValueError:
            relative = path
        parts = relative.parts
        case_id = parts[1] if len(parts) == 3 and parts[0] == "fixtures" else None
        if case_id is None or parts[2] != _MOCKSERVER_INITIALIZATION:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        "MockServer fixture must be exactly "
                        "evals/fixtures/<eval-id>/mockserverInitialization.json"
                    ),
                )
            )
            continue
        if case_id not in declared_cases:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        "MockServer fixture belongs to unknown eval case "
                        f"'{render_safe_diagnostic_text(case_id)}'"
                    ),
                )
            )
            continue
        source = authored_file(path, skill.root)
        if _has_symlink_component(path, evals_root) or source is None:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message="MockServer fixture must be a non-symlink regular file",
                )
            )
            continue
        try:
            if manifest is None:
                manifest = EvalRuntimeManifest.load(_RUNTIME_MANIFEST_PATH)
            content = loaded_content.get(source.logical_path)
            if content is None:
                raise AuthoredContentReadError(
                    "fixture bytes were not captured during authored traversal"
                )
            load_fixture_definition_bytes(
                content,
                source=path,
                manifest=manifest,
                repository_root=_REPOSITORY_ROOT,
            )
        except (
            AuthoredContentReadError,
            FixtureProxyError,
            ManifestError,
            OSError,
        ) as error:
            diagnostic = bounded_redacted_runtime_text(str(error), 2048)
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=f"MockServer fixture is invalid: {diagnostic}",
                )
            )
    return issues


def _has_symlink_component(path: Path, root: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current == root:
            return False
        if root not in current.parents:
            return True
        current = current.parent


def _parse_json_content(
    context: ValidationContext,
    skill: SkillRecord,
    source: AuthoredFile,
    content: bytes,
    *,
    maximum_bytes: int,
    raw_secret_findings: Sequence[SecretMatch] = (),
) -> tuple[Any | None, list[ValidationIssue]]:
    try:
        text = content.decode("utf-8")
        document = strict_bounded_json_loads(
            text,
            maximum_bytes=maximum_bytes,
        )
    except (UnicodeDecodeError, BoundedJsonError) as error:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)} "
                    f"contains invalid JSON: {error}"
                ),
            )
        ]
    try:
        decoded_findings = find_additional_decoded_json_secret_issues(
            document,
            source.logical_path,
            maximum_bytes=maximum_bytes,
            raw_findings=raw_secret_findings,
        )
    except BoundedJsonError as error:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)} "
                    "cannot be "
                    f"secret-scanned after JSON decoding: {error}"
                ),
            )
        ]
    return document, [
        ValidationIssue(
            scope=skill_scope(context, skill),
            message=(
                f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)} "
                "contains a "
                f"high-confidence secret after JSON decoding: {finding.pattern} "
                f"({finding.category}); value redacted"
            ),
        )
        for finding in decoded_findings
    ]


def _secret_issues(
    context: ValidationContext,
    skill: SkillRecord,
    source: AuthoredFile,
    findings: Sequence[SecretMatch],
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            scope=skill_scope(context, skill),
            message=(
                f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}:"
                f"{finding.line}:{finding.column}: "
                f"high-confidence secret {finding.pattern} ({finding.category}); value redacted"
            ),
        )
        for finding in findings
    ]
