"""Eval, trigger, and fixture definition checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.eval_definitions import (
    MAX_EVAL_DEFINITION_BYTES,
    MAX_EVAL_FIXTURE_FILE_BYTES,
    validate_behavior_eval_document,
)
from scripts.ai_skills_lib.fixture_proxy import FixtureProxyError, load_fixture_definition
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.sandbox_runtime import EvalRuntimeManifest, ManifestError
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text
from scripts.ai_skills_lib.static_checks.content import (
    authored_file,
    find_static_secret_issues,
    read_text_fixture,
    walk_authored_files,
)
from scripts.ai_skills_lib.static_checks.context import (
    AuthoredFile,
    ValidationContext,
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

    evals_data, load_issues = _load_required_json(context, skill, evals_source)
    issues.extend(load_issues)
    triggers_data, load_issues = _load_required_json(context, skill, triggers_source)
    issues.extend(load_issues)

    files = (
        list(walk_authored_files(inspection.evals_root, skill.root))
        if inspection.evals_root is not None
        else []
    )
    required_logical = {
        skill.root / "evals" / filename for filename in _REQUIRED_EVAL_FILES
    }
    for source in files:
        maximum_bytes = (
            MAX_EVAL_DEFINITION_BYTES
            if source.logical_path in required_logical
            else MAX_EVAL_FIXTURE_FILE_BYTES
        )
        try:
            oversized = source.resolved_path.stat().st_size > maximum_bytes
        except OSError:
            oversized = False
        if oversized:
            if source.logical_path not in required_logical:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"{source.logical_path.relative_to(skill.root)} exceeds the "
                            "4 MiB eval fixture file limit"
                        ),
                    )
                )
            continue
        text = read_text_fixture(source)
        if text is not None:
            issues.extend(_secret_issues(context, skill, source, text))
        if (
            source.logical_path.suffix == ".json"
            and source.logical_path not in required_logical
        ):
            _, json_issues = _load_json(
                context,
                skill,
                source,
                maximum_bytes=MAX_EVAL_FIXTURE_FILE_BYTES,
                limit_label="4 MiB eval fixture file limit",
            )
            issues.extend(json_issues)

    issues.extend(
        _validate_fixture_topology(
            context,
            skill,
            evals_data,
            inspection.fixtures_root,
        )
    )
    if evals_data is not None:
        issues.extend(validate_behavior_eval_document(evals_data, skill, scope))
        issues.extend(
            _validate_mockserver_initializations(context, skill, evals_data, files)
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
        entries = {entry.name: entry for entry in evals_root.iterdir()}
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
            ValidationIssue(scope=scope, message=f"unsupported evals entry: {name}")
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
        case_entries = sorted(fixtures_root.iterdir())
    except OSError as error:
        return [
            ValidationIssue(
                scope=scope,
                message=f"cannot inspect evals/fixtures: {error}",
            )
        ]
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
    for case_root in case_entries:
        relative = case_root.relative_to(skill.root)
        if not _is_contained_non_symlink_directory(
            case_root, resolved_fixtures_root
        ):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "eval fixture case entry must be a contained non-symlink "
                        f"directory: {relative}"
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
                        f"'{case_root.name}'"
                    ),
                )
            )
            continue
        issues.extend(
            _validate_case_fixture_tree(context, skill, case_root, raw_case)
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
    case_root: Path,
    raw_case: Mapping[object, object],
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    allowed_files = _declared_case_fixture_files(skill, case_root.name, raw_case)
    resolved_case_root = case_root.resolve(strict=True)
    issues: list[ValidationIssue] = []
    pending = [case_root]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(directory.iterdir(), reverse=True)
        except OSError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"cannot inspect {directory.relative_to(skill.root)}: {error}"
                    ),
                )
            )
            continue
        if not entries:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "empty directory is not allowed: "
                        f"{directory.relative_to(skill.root)}"
                    ),
                )
            )
            continue
        for entry in entries:
            relative = entry.relative_to(skill.root)
            if entry.is_symlink():
                resolution = _resolve_fixture_symlink(entry)
                if resolution is None:
                    issues.append(
                        ValidationIssue(
                            scope=scope,
                            message=f"broken eval fixture symlink: {relative}",
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
                if not _path_is_declared(entry, allowed_files):
                    issues.append(
                        ValidationIssue(
                            scope=scope,
                            message=f"undeclared eval fixture entry: {relative}",
                        )
                    )
                continue
            if entry.is_dir():
                pending.append(entry)
            elif entry.is_file():
                if entry not in allowed_files:
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


def _resolve_fixture_symlink(path: Path) -> Path | None:
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError):
        return None


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
            case_roots = tuple(fixture_root.iterdir())
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
                    message=f"MockServer fixture belongs to unknown eval case '{case_id}'",
                )
            )
            continue
        if _has_symlink_component(path, evals_root) or not path.is_file():
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
            load_fixture_definition(
                path,
                manifest=manifest,
                repository_root=_REPOSITORY_ROOT,
                allowed_fixture_root=path.parent,
            )
        except (FixtureProxyError, ManifestError, OSError) as error:
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


def _load_required_json(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile | None
) -> tuple[Any | None, list[ValidationIssue]]:
    if source is None:
        return None, []
    return _load_json(context, skill, source)


def _load_json(
    context: ValidationContext,
    skill: SkillRecord,
    source: AuthoredFile,
    *,
    maximum_bytes: int = MAX_EVAL_DEFINITION_BYTES,
    limit_label: str = "2 MiB eval definition limit",
) -> tuple[Any | None, list[ValidationIssue]]:
    try:
        if source.resolved_path.stat().st_size > maximum_bytes:
            return None, [
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        f"{source.logical_path.relative_to(skill.root)} exceeds the "
                        f"{limit_label}"
                    ),
                )
            ]
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
