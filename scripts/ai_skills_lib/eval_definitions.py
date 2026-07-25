"""Discovery and validation for authored behavior evaluation definitions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
import re

from jsonschema import Draft202012Validator

from scripts.ai_skills_lib.authored_content import (
    AuthoredContentComplexityError,
    AuthoredContentReadError,
    AuthoredContentTooLarge,
    AuthoredRepositoryBudget,
    AuthoredRepositoryBudgetExceeded,
    authored_file,
    contains_local_eval_runtime_reference,
    extract_bundled_paths,
    find_additional_decoded_json_secret_issues,
    find_static_secret_issues,
    read_bounded_authored_bytes,
    render_bounded_decoded_json,
    walk_authored_files,
)
from scripts.ai_skills_lib.bounded_json import (
    BoundedJsonError,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.core import (
    SkillRecord,
    discover_testable_skills,
    snapshot_canonical_skills_tree,
)
from scripts.ai_skills_lib.eval_core import AssertionDefinition
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.json_schema_policy import (
    MAX_JSON_SCHEMA_BYTES,
    JsonSchemaPolicyError,
    build_safe_json_schema_validator,
)
from scripts.ai_skills_lib.secret_patterns import bounded_redacted_runtime_text
from scripts.ai_skills_lib.static_checks.context import render_safe_diagnostic_issues


_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "schemas" / "ai-skills" / "evals.schema.json"
)
_RUNTIME_DIRECTORIES = ("scripts", "references", "assets")
MAX_EVAL_DEFINITION_BYTES = 2 * 1024 * 1024
MAX_EVAL_FIXTURE_FILE_BYTES = 4 * 1024 * 1024
MAX_INSTALLABLE_REFERENCE_SCAN_BYTES = 64 * 1024 * 1024
_MAX_CASE_ORACLE_BYTES = 320 * 1024
MAX_CASE_DETERMINISTIC_SCHEMA_BYTES = 512 * 1024
_CASE_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_PRIVATE_PROVIDER = (
    r"(?:Atlassian|Bitbucket|Clerk|Figma|GitHub|GitLab|Google(?:\s+Drive)?|"
    r"Jira|Linear|Slack)"
)
_PRIVATE_RESOURCE = (
    rf"(?:(?:{_PRIVATE_PROVIDER})\s+)?(?:api\s+(?:key|token)|"
    r"internal\s+apis?|apis?|"
    r"browser(?:\s+(?:profile|session))?|"
    r"cookies?|credentials?|inbox(?:es)?|emails?|calendars?|accounts?|sessions?|"
    r"ssh\s+keys?|tokens?|repositor(?:y|ies)|repos?|databases?|"
    r"(?:customer[- ])?records?|data(?:sets?)?|projects?|channels?|workspaces?|"
    r"environments?|issues?|tickets?|documents?|files?|resources?)"
)
_PRIVATE_STATE_LIVE_QUALIFIER = (
    r"(?:actual|live|personal|private|prod(?:uction)?|real|logged[- ]in)"
)
_PRIVATE_STATE_OWNER_QUALIFIER = r"(?:my|our|your)"
_PRIVATE_STATE_LIVE_PATTERNS = (
    re.compile(
        rf"\b{_PRIVATE_STATE_LIVE_QUALIFIER}\s+{_PRIVATE_RESOURCE}\b",
        re.IGNORECASE,
    ),
)
_PRIVATE_STATE_OWNED_PATTERNS = (
    re.compile(
        rf"\b{_PRIVATE_STATE_OWNER_QUALIFIER}\s+"
        rf"(?:saved\s+|stored\s+|logged[- ]in\s+)?"
        rf"{_PRIVATE_RESOURCE}\b",
        re.IGNORECASE,
    ),
)
_PRIVATE_STATE_NONLIVE_PREQUALIFIER = re.compile(
    r"\b(?:fake|fixture|mock|sandbox|simulated|simulation|transcript)"
    r"(?:[- ]backed)?\s+$",
    re.IGNORECASE,
)
_PRIVATE_STATE_NONLIVE_POSTQUALIFIER = re.compile(
    r"\s+(?:fake|fixture|mock|sandbox|simulation|transcript)\b",
    re.IGNORECASE,
)
_PRIVATE_STATE_DIRECT_NOUN_NEGATION = re.compile(
    r"\b(?:no|not|without)\s+(?:an?\s+|the\s+)?$",
    re.IGNORECASE,
)
_PRIVATE_STATE_DIRECT_REQUEST_NEGATION = re.compile(
    r"\b(?:avoid|do\s+not|don't|never|not|without)\s+"
    r"[A-Za-z-]+\s+"
    r"(?:(?:(?:an?|the)\s+)?[A-Za-z-]+\s+)?"
    r"(?:(?:against|from|in|into|on|to|with)\s+)?"
    r"(?:(?:an?|my|our|the|your)\s+)?$",
    re.IGNORECASE,
)
_ORACLE_STRUCTURAL_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_])expected_output(?![A-Za-z0-9_])", re.IGNORECASE),
    re.compile(
        r"(?<![A-Za-z0-9_.-])(?:benchmark|grading|manual_grading)\.json"
        r"(?![A-Za-z0-9_.-])",
        re.IGNORECASE,
    ),
    re.compile(r"[\"']assertions[\"']\s*:", re.IGNORECASE),
    re.compile(
        r"\b(?:evaluation|grader|grading|judge)\s+assertions?\b",
        re.IGNORECASE,
    ),
)
_ORACLE_INSTRUCTION_PATTERNS = (
    re.compile(
        r"\b(?:evaluation\s+judge|evaluator|grader|judge)\s+"
        r"(?:must|should|will)\s+(?:accept|approve|grade|pass|score)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:pass|satisfy)\s+(?:the\s+)?(?:evaluation|evaluator|grader|judge)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bfollow\s+(?:the\s+)?(?:evaluation|evaluator|grader|judge)\s+instructions\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class BehaviorCheck:
    type: str
    path: PurePosixPath | None = None
    schema: PurePosixPath | None = None
    expected: int | None = None
    format: str | None = None


@dataclass(frozen=True)
class BehaviorEvalCase:
    id: str
    prompt: str
    expected_output: str
    assertions: tuple[AssertionDefinition, ...]
    files: tuple[PurePosixPath, ...]
    checks: tuple[BehaviorCheck, ...]


@dataclass(frozen=True)
class SkillBehaviorEvals:
    skill: SkillRecord
    cases: tuple[BehaviorEvalCase, ...]


class BehaviorDefinitionError(RuntimeError):
    def __init__(self, issues: Sequence[ValidationIssue]):
        super().__init__("behavior eval definitions are invalid")
        self.issues = tuple(issues)


def validate_behavior_eval_files(root: Path) -> list[ValidationIssue]:
    """Discover every skill and validate its behavior eval file."""
    _, issues = _inspect_behavior_eval_files(root)
    return render_safe_diagnostic_issues(issues)


def load_behavior_evals(root: Path) -> tuple[SkillBehaviorEvals, ...]:
    """Discover, validate, and load typed behavior definitions in one pass."""
    definitions, issues = _inspect_behavior_eval_files(root)
    safe_issues = render_safe_diagnostic_issues(issues)
    if safe_issues:
        raise BehaviorDefinitionError(safe_issues)
    return definitions


def _inspect_behavior_eval_files(
    root: Path,
) -> tuple[tuple[SkillBehaviorEvals, ...], list[ValidationIssue]]:
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
                scope="behavior eval discovery",
                message=f"cannot discover skills: {diagnostic}",
            )
        ]

    issues: list[ValidationIssue] = []
    definitions: list[SkillBehaviorEvals] = []
    for name, count in sorted(Counter(skill.name for skill in skills).items()):
        if count > 1:
            issues.append(
                ValidationIssue(
                    scope="behavior eval discovery",
                    message=f"duplicate skill name '{name}' appears {count} times",
                )
            )
    for skill in skills:
        scope = str(skill.root.relative_to(root))
        issue_start = len(issues)
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
        path = skill.root / "evals" / "evals.json"
        if _has_symlink_component(path, skill.root):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="evals/evals.json must be a contained non-symlink regular file",
                )
            )
            continue
        source = authored_file(path, skill.root)
        if source is None:
            message = (
                "missing evals/evals.json"
                if not path.exists()
                else "evals/evals.json must be a contained non-symlink regular file"
            )
            issues.append(ValidationIssue(scope=scope, message=message))
            continue
        try:
            content = read_bounded_authored_bytes(
                source,
                maximum_bytes=MAX_EVAL_DEFINITION_BYTES,
                allowed_root=skill.root,
                containment_root=root,
                budget=budget,
            )
            text = content.decode("utf-8")
        except AuthoredRepositoryBudgetExceeded as error:
            issues.append(
                ValidationIssue(
                    scope="behavior eval discovery",
                    message=bounded_redacted_runtime_text(str(error), 2048),
                )
            )
            return (), issues
        except AuthoredContentTooLarge:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="evals/evals.json exceeds the 2 MiB definition limit",
                )
            )
            continue
        except (AuthoredContentReadError, UnicodeDecodeError) as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"cannot read evals/evals.json: {error}",
                )
            )
            continue
        secret_findings = find_static_secret_issues(text, path)
        for finding in secret_findings:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"evals/evals.json:{finding.line}:{finding.column}: "
                        f"high-confidence secret {finding.pattern}; value redacted"
                    ),
                )
            )
        try:
            document = strict_bounded_json_loads(
                content,
                maximum_bytes=MAX_EVAL_DEFINITION_BYTES,
            )
        except BoundedJsonError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"evals/evals.json contains invalid JSON: {error}",
                )
            )
            continue
        try:
            decoded_findings = find_additional_decoded_json_secret_issues(
                document,
                path,
                maximum_bytes=MAX_EVAL_DEFINITION_BYTES,
                raw_findings=secret_findings,
            )
        except BoundedJsonError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "evals/evals.json cannot be secret-scanned after JSON "
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
                        "evals/evals.json contains a high-confidence secret "
                        f"after JSON decoding: {finding.pattern}; value redacted"
                    ),
                )
            )
        try:
            issues.extend(
                validate_behavior_eval_document(
                    document,
                    skill,
                    scope,
                    budget=budget,
                )
            )
        except AuthoredRepositoryBudgetExceeded as error:
            issues.append(
                ValidationIssue(
                    scope="behavior eval discovery",
                    message=bounded_redacted_runtime_text(str(error), 2048),
                )
            )
            return (), issues
        if len(issues) != issue_start:
            continue
        assert isinstance(document, Mapping)
        definitions.append(_typed_definition(skill, document))
    try:
        final_skills_tree = snapshot_canonical_skills_tree(
            root,
            budget=budget,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        diagnostic = bounded_redacted_runtime_text(str(error), 2048)
        issues.append(
            ValidationIssue(
                scope="behavior eval discovery",
                message=f"cannot reverify canonical skills tree: {diagnostic}",
            )
        )
        return (), issues
    if final_skills_tree != initial_skills_tree:
        issues.append(
            ValidationIssue(
                scope="behavior eval discovery",
                message=(
                    "canonical skills tree changed during definition loading"
                ),
            )
        )
        return (), issues
    return tuple(definitions), issues


def validate_behavior_eval_document(
    document: object,
    skill: SkillRecord,
    scope: str,
    *,
    budget: AuthoredRepositoryBudget | None = None,
    loaded_content: Mapping[Path, bytes] | None = None,
) -> list[ValidationIssue]:
    """Validate one parsed behavior document and its skill-local resources."""
    issues: list[ValidationIssue] = []
    try:
        validator = _behavior_validator()
    except (OSError, BoundedJsonError, ValueError) as error:
        return [ValidationIssue(scope=scope, message=f"cannot load eval schema: {error}")]
    for error in sorted(validator.iter_errors(document), key=_validation_error_key):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "evals/evals.json schema error at "
                    f"{_validation_path(error.absolute_path)}: {error.validator}"
                ),
            )
        )
    if not isinstance(document, Mapping):
        return issues
    issues.extend(_installable_eval_reference_issues(skill, scope, budget=budget))
    skill_name = document.get("skill_name")
    if isinstance(skill_name, str) and skill_name != skill.name:
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    f"evals/evals.json skill_name '{skill_name}' must match "
                    f"skill name '{skill.name}'"
                ),
            )
        )
    raw_cases = document.get("evals")
    if not isinstance(raw_cases, Sequence) or isinstance(raw_cases, (str, bytes)):
        return issues
    seen_ids: set[str] = set()
    exercises_bundled_file = False
    for raw_case in raw_cases:
        if not isinstance(raw_case, Mapping):
            continue
        case_id = raw_case.get("id")
        if not isinstance(case_id, str):
            continue
        if case_id in seen_ids:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"evals/evals.json has duplicate eval id '{case_id}'",
                )
            )
        seen_ids.add(case_id)
        case_id_is_valid = len(case_id) <= 64 and bool(
            _CASE_ID_PATTERN.fullmatch(case_id)
        )
        if case_id_is_valid:
            issues.extend(_case_path_issues(scope, case_id, raw_case))
            issues.extend(
                _case_resource_issues(
                    skill,
                    scope,
                    case_id,
                    raw_case,
                    budget=budget,
                    loaded_content=loaded_content,
                )
            )
        prompt = raw_case.get("prompt")
        has_isolated_resources = case_id_is_valid and (
            _case_has_declared_isolated_resources(
                skill,
                case_id,
                raw_case,
            )
        )
        private_state_message: str | None = None
        if isinstance(prompt, str) and _requires_private_state(
            prompt,
            _PRIVATE_STATE_LIVE_PATTERNS,
        ):
            private_state_message = (
                f"eval '{case_id}' explicitly requests live or private credentials "
                "or session state; use isolated non-production resources"
            )
        elif (
            isinstance(prompt, str)
            and not has_isolated_resources
            and _requires_private_state(prompt, _PRIVATE_STATE_OWNED_PATTERNS)
        ):
            private_state_message = (
                f"eval '{case_id}' requires private credentials or session state "
                "without declared isolated case resources"
            )
        if private_state_message is not None:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=private_state_message,
                )
            )
        if isinstance(prompt, str) and _contains_actor_prompt_oracle_leak(prompt):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"eval '{case_id}' actor prompt contains runner-owned oracle "
                        "or grading instructions"
                    ),
                )
            )
        raw_assertions = raw_case.get("assertions")
        assertion_texts = (
            tuple(value for value in raw_assertions if isinstance(value, str))
            if isinstance(raw_assertions, Sequence)
            and not isinstance(raw_assertions, (str, bytes))
            else ()
        )
        oracle_values = (
            raw_case.get("prompt"),
            raw_case.get("expected_output"),
            *assertion_texts,
        )
        oracle_size = sum(
            len(value.encode("utf-8"))
            for value in oracle_values
            if isinstance(value, str)
        )
        if oracle_size > _MAX_CASE_ORACLE_BYTES:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"eval '{case_id}' oracle text exceeds the 320 KiB UTF-8 limit"
                    ),
                )
            )
        authored_text = "\n".join(
            value
            for value in (
                raw_case.get("prompt"),
                raw_case.get("expected_output"),
                *assertion_texts,
            )
            if isinstance(value, str)
        )
        try:
            bundled_paths = extract_bundled_paths(authored_text)
        except AuthoredContentComplexityError:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"eval '{case_id}' exceeds the bundled path inspection limit"
                    ),
                )
            )
        else:
            if any(
                authored_file(skill.root / path, skill.root) is not None
                for path in bundled_paths
            ):
                exercises_bundled_file = True
    has_bundled_files = any(
        any(
            walk_authored_files(
                skill.root / directory,
                skill.root,
                budget=budget,
            )
        )
        for directory in _RUNTIME_DIRECTORIES
    )
    if has_bundled_files and not exercises_bundled_file:
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "evals/evals.json must exercise bundled runtime material by naming "
                    "a real scripts/, references/, or assets/ path"
                ),
            )
        )
    return issues


def _case_resource_issues(
    skill: SkillRecord,
    scope: str,
    case_id: str,
    raw_case: Mapping[object, object],
    *,
    budget: AuthoredRepositoryBudget | None = None,
    loaded_content: Mapping[Path, bytes] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    expected_inputs = PurePosixPath("fixtures") / case_id / "inputs"
    raw_files = raw_case.get("files")
    prompt = raw_case.get("prompt")
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for raw_path in raw_files:
            if not isinstance(raw_path, str):
                continue
            if not _is_canonical_relative_path(raw_path):
                continue
            path = PurePosixPath(raw_path)
            if path.parent != expected_inputs and expected_inputs not in path.parents:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"actor input '{raw_path}' must stay below "
                            f"{expected_inputs}"
                        ),
                    )
                )
                continue
            actor_path = path.relative_to(expected_inputs).as_posix()
            logical = skill.root / "evals" / path
            source = authored_file(logical, skill.root)
            actor_names = [actor_path]
            if (
                path.relative_to(expected_inputs).parent == PurePosixPath("bin")
                and source is not None
                and _authored_file_is_executable(source.resolved_path)
            ):
                actor_names.append(path.name)
            if isinstance(prompt, str) and not any(
                _text_names_path(prompt, actor_name) for actor_name in actor_names
            ):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"eval '{case_id}' prompt must name staged actor input "
                            f"'{actor_path}'"
                        ),
                    )
                )
            if (
                _has_symlink_component(logical, skill.root)
                or source is None
            ):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"actor input does not exist as a regular file: {raw_path}",
                    )
                )
    raw_checks = raw_case.get("checks")
    deterministic_schema_bytes = 0
    counted_schema_paths: set[Path] = set()
    if isinstance(raw_checks, Sequence) and not isinstance(raw_checks, (str, bytes)):
        for raw_check in raw_checks:
            if not isinstance(raw_check, Mapping):
                continue
            raw_schema = raw_check.get("schema")
            if not isinstance(raw_schema, str) or not _is_canonical_relative_path(
                raw_schema
            ):
                continue
            schema_path = PurePosixPath(raw_schema)
            case_root = PurePosixPath("fixtures") / case_id
            if schema_path.parent != case_root and case_root not in schema_path.parents:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"runner-only schema '{raw_schema}' must stay below {case_root}"
                        ),
                    )
                )
                continue
            inputs_root = case_root / "inputs"
            if schema_path.parent == inputs_root or inputs_root in schema_path.parents:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message="runner-only schema must not be below inputs",
                    )
                )
                continue
            logical = skill.root / "evals" / schema_path
            schema_source = authored_file(logical, skill.root)
            if _has_symlink_component(logical, skill.root) or schema_source is None:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"runner-only schema does not exist: {raw_schema}",
                    )
                )
                continue
            try:
                if loaded_content is None:
                    schema_content = read_bounded_authored_bytes(
                        schema_source,
                        maximum_bytes=MAX_JSON_SCHEMA_BYTES,
                        allowed_root=skill.root,
                        containment_root=skill.root.parents[2],
                        budget=budget,
                    )
                else:
                    schema_content = loaded_content.get(logical)
                    if schema_content is None:
                        raise AuthoredContentReadError(
                            "runner-only schema has no validated content snapshot"
                        )
                if logical not in counted_schema_paths:
                    counted_schema_paths.add(logical)
                    deterministic_schema_bytes += len(schema_content)
                schema_document = strict_bounded_json_loads(
                    schema_content,
                    maximum_bytes=MAX_JSON_SCHEMA_BYTES,
                )
                if not isinstance(schema_document, Mapping):
                    raise JsonSchemaPolicyError("JSON Schema root must be an object")
                build_safe_json_schema_validator(schema_document)
            except AuthoredContentTooLarge:
                error = JsonSchemaPolicyError(
                    "JSON Schema exceeds the 256 KiB byte limit"
                )
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"runner-only schema is invalid: {raw_schema}; {error}"
                        ),
                    )
                )
                continue
            except (
                AuthoredContentReadError,
                BoundedJsonError,
                JsonSchemaPolicyError,
            ) as error:
                policy_detail = (
                    f"; {error}" if isinstance(error, JsonSchemaPolicyError) else ""
                )
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            "runner-only schema is not a valid JSON Schema object: "
                            f"{raw_schema}{policy_detail}"
                        ),
                    )
                )
                continue
    if deterministic_schema_bytes > MAX_CASE_DETERMINISTIC_SCHEMA_BYTES:
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    f"eval '{case_id}' deterministic schemas exceed the "
                    "512 KiB aggregate byte limit"
                ),
            )
        )
    return issues


def _case_path_issues(
    scope: str,
    case_id: str,
    raw_case: Mapping[object, object],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    actor_paths: dict[str, str] = {}
    raw_files = raw_case.get("files")
    if isinstance(raw_files, Sequence) and not isinstance(raw_files, (str, bytes)):
        for raw_path in raw_files:
            if not isinstance(raw_path, str):
                continue
            normalized = PurePosixPath(raw_path).as_posix()
            if not _is_canonical_relative_path(raw_path):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"eval '{case_id}' actor input '{raw_path}' must be a "
                            "canonical relative path"
                        ),
                    )
                )
            prior = actor_paths.get(normalized)
            if prior is not None and prior != raw_path:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"eval '{case_id}' actor input '{raw_path}' aliases another "
                            "actor input after normalization"
                        ),
                    )
                )
            else:
                actor_paths[normalized] = raw_path

    raw_checks = raw_case.get("checks")
    if isinstance(raw_checks, Sequence) and not isinstance(raw_checks, (str, bytes)):
        for index, raw_check in enumerate(raw_checks):
            if not isinstance(raw_check, Mapping):
                continue
            for field in ("path", "schema"):
                raw_path = raw_check.get(field)
                if isinstance(raw_path, str) and not _is_canonical_relative_path(raw_path):
                    issues.append(
                        ValidationIssue(
                            scope=scope,
                            message=(
                                f"eval '{case_id}' check {index + 1} {field} '{raw_path}' "
                                "must be a canonical relative path"
                            ),
                        )
                    )
    return issues


def _is_canonical_relative_path(raw_path: str) -> bool:
    path = PurePosixPath(raw_path)
    return (
        raw_path not in ("", ".")
        and "\x00" not in raw_path
        and "\\" not in raw_path
        and not path.is_absolute()
        and ".." not in path.parts
        and raw_path == path.as_posix()
    )


def _text_names_path(text: str, path: str) -> bool:
    return re.search(
        rf"(?<![A-Za-z0-9._/\\-]){re.escape(path)}(?![A-Za-z0-9._/\\-])",
        text,
    ) is not None


def _installable_eval_reference_issues(
    skill: SkillRecord,
    scope: str,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> list[ValidationIssue]:
    sources = []
    skill_source = authored_file(skill.path, skill.root)
    if skill_source is not None:
        sources.append(skill_source)
    for directory in _RUNTIME_DIRECTORIES:
        sources.extend(
            walk_authored_files(
                skill.root / directory,
                skill.root,
                budget=budget,
            )
        )

    issues: list[ValidationIssue] = []
    for source in sources:
        try:
            content = read_bounded_authored_bytes(
                source,
                maximum_bytes=MAX_INSTALLABLE_REFERENCE_SCAN_BYTES,
                allowed_root=skill.root,
                budget=budget,
            )
        except AuthoredContentTooLarge:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"{source.logical_path.relative_to(skill.root)} "
                        "exceeds the installable-reference validation byte limit"
                    ),
                )
            )
            continue
        except AuthoredContentReadError:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"{source.logical_path.relative_to(skill.root)} "
                        "cannot be inspected for prohibited evals/ references"
                    ),
                )
            )
            continue
        inspection_values: list[str | bytes] = [content]
        if source.logical_path.suffix.casefold() == ".json":
            try:
                document = strict_bounded_json_loads(
                    content,
                    maximum_bytes=MAX_INSTALLABLE_REFERENCE_SCAN_BYTES,
                )
                inspection_values.append(
                    render_bounded_decoded_json(
                        document,
                        maximum_bytes=MAX_INSTALLABLE_REFERENCE_SCAN_BYTES,
                    )
                )
            except BoundedJsonError:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"{source.logical_path.relative_to(skill.root)} "
                            "contains invalid JSON for installable-reference inspection"
                        ),
                    )
                )
                continue
        if not any(
            contains_local_eval_runtime_reference(value)
            for value in inspection_values
        ):
            continue
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    f"{source.logical_path.relative_to(skill.root)} installable content "
                    "must not reference evals/"
                ),
            )
        )
    return issues


def _requires_private_state(
    prompt: str,
    patterns: tuple[re.Pattern[str], ...],
) -> bool:
    for pattern in patterns:
        for match in pattern.finditer(prompt):
            if _has_direct_nonlive_qualification(prompt, match):
                continue
            if _has_direct_private_state_negation(prompt, match):
                continue
            return True
    return False


def _case_has_declared_isolated_resources(
    skill: SkillRecord,
    case_id: str,
    raw_case: Mapping[object, object],
) -> bool:
    fixture_root = skill.root / "evals" / "fixtures" / case_id
    initialization = fixture_root / "mockserverInitialization.json"
    if (
        not _has_symlink_component(initialization, skill.root)
        and authored_file(initialization, skill.root) is not None
    ):
        return True

    expected_inputs = PurePosixPath("fixtures") / case_id / "inputs"
    raw_files = raw_case.get("files")
    if not isinstance(raw_files, Sequence) or isinstance(raw_files, (str, bytes)):
        return False
    for raw_path in raw_files:
        if not isinstance(raw_path, str) or not _is_canonical_relative_path(raw_path):
            continue
        path = PurePosixPath(raw_path)
        if path.parent != expected_inputs and expected_inputs not in path.parents:
            continue
        logical = skill.root / "evals" / path
        if (
            not _has_symlink_component(logical, skill.root)
            and authored_file(logical, skill.root) is not None
        ):
            return True
    return False


def _authored_file_is_executable(path: Path) -> bool:
    try:
        return bool(path.stat().st_mode & 0o111)
    except OSError:
        return False


def _has_direct_nonlive_qualification(prompt: str, match: re.Match[str]) -> bool:
    return (
        _PRIVATE_STATE_NONLIVE_PREQUALIFIER.search(prompt, 0, match.start()) is not None
        or _PRIVATE_STATE_NONLIVE_POSTQUALIFIER.match(prompt, match.end()) is not None
    )


def _has_direct_private_state_negation(
    prompt: str,
    match: re.Match[str],
) -> bool:
    return (
        _PRIVATE_STATE_DIRECT_NOUN_NEGATION.search(prompt, 0, match.start())
        is not None
        or _PRIVATE_STATE_DIRECT_REQUEST_NEGATION.search(prompt, 0, match.start())
        is not None
    )


def _contains_actor_prompt_oracle_leak(prompt: str) -> bool:
    return any(
        pattern.search(prompt) is not None
        for pattern in (*_ORACLE_STRUCTURAL_PATTERNS, *_ORACLE_INSTRUCTION_PATTERNS)
    )


def _typed_definition(
    skill: SkillRecord,
    document: Mapping[object, object],
) -> SkillBehaviorEvals:
    raw_cases = document["evals"]
    assert isinstance(raw_cases, Sequence)
    cases: list[BehaviorEvalCase] = []
    for raw_case in raw_cases:
        assert isinstance(raw_case, Mapping)
        raw_assertions = raw_case["assertions"]
        assert isinstance(raw_assertions, Sequence)
        assertions = tuple(
            AssertionDefinition(id=f"assertion-{index}", kind="assertion", text=text)
            for index, text in enumerate(raw_assertions, start=1)
        )
        raw_checks = raw_case.get("checks", ())
        assert isinstance(raw_checks, Sequence)
        checks = tuple(
            BehaviorCheck(
                type=check["type"],
                path=PurePosixPath(check["path"]) if "path" in check else None,
                schema=PurePosixPath(check["schema"]) if "schema" in check else None,
                expected=check.get("expected"),
                format=check.get("format"),
            )
            for check in raw_checks
            if isinstance(check, Mapping)
        )
        cases.append(
            BehaviorEvalCase(
                id=raw_case["id"],
                prompt=raw_case["prompt"],
                expected_output=raw_case["expected_output"],
                assertions=assertions,
                files=tuple(PurePosixPath(path) for path in raw_case.get("files", ())),
                checks=checks,
            )
        )
    return SkillBehaviorEvals(skill=skill, cases=tuple(cases))


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


@lru_cache(maxsize=1)
def _behavior_validator() -> Draft202012Validator:
    schema = strict_bounded_json_loads(
        _SCHEMA_PATH.read_bytes(),
        maximum_bytes=MAX_EVAL_DEFINITION_BYTES,
    )
    if not isinstance(schema, Mapping):
        raise ValueError("eval schema root must be an object")
    return Draft202012Validator(schema)


def _validation_error_key(error) -> tuple[tuple[str, ...], str]:
    return tuple(str(part) for part in error.absolute_path), str(error.validator)


def _validation_path(parts: Sequence[object]) -> str:
    rendered = "$"
    for part in parts:
        rendered += f"[{part}]" if isinstance(part, int) else f".{part}"
    return rendered
