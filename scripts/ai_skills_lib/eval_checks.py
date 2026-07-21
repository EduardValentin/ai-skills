"""Deterministic checks for completed behavior-evaluation actor runs."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat

from jsonschema import Draft202012Validator

from scripts.ai_skills_lib.authored_content import (
    BoundedJsonError,
    DEFAULT_MAXIMUM_SECRET_SCAN_BYTES,
    SecretScanBudget,
    SecretScanLimitError,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.eval_core import (
    AssertionResult,
    ResultArtifactError,
    completed_attempt_control_evidence_reference,
)
from scripts.ai_skills_lib.eval_definitions import BehaviorCheck
from scripts.ai_skills_lib.harness import HarnessExecution, PreparedFile
from scripts.ai_skills_lib.json_schema_policy import (
    MAX_JSON_SCHEMA_BYTES,
    JsonSchemaPolicyError,
    bounded_json_schema_errors,
    build_safe_json_schema_validator,
)


_MAX_EVAL_OUTPUT_JSON_BYTES = 4 * 1024 * 1024
_MAX_SECRET_EVIDENCE_REFERENCES = 16


def evaluate_deterministic_checks(
    checks: Sequence[BehaviorCheck],
    *,
    outputs_root: Path,
    response: str,
    execution: HarnessExecution,
    skill_root: Path,
    prepared_schemas: Sequence[tuple[PurePosixPath, PreparedFile]] | None = None,
) -> tuple[AssertionResult, ...]:
    """Evaluate authored hard contracts without matching model prose."""
    output_files = list_safe_output_files(outputs_root)
    schema_catalog = _prepared_schema_catalog(prepared_schemas)
    results: list[AssertionResult] = []
    for index, check in enumerate(checks, start=1):
        check_id = f"check-{index}"
        if check.type == "file_exists":
            results.append(_file_exists(check_id, check, outputs_root))
        elif check.type == "path_absent":
            results.append(_path_absent(check_id, check, outputs_root, execution))
        elif check.type == "json_schema":
            results.append(
                _json_schema(
                    check_id,
                    check,
                    outputs_root,
                    skill_root,
                    schema_catalog,
                )
            )
        elif check.type == "exit_code":
            results.append(_exit_code(check_id, check, execution))
        elif check.type == "no_secret_patterns":
            results.append(
                _no_secret_patterns(check_id, response, outputs_root, output_files)
            )
        elif check.type == "response_protocol":
            results.append(
                _response_protocol(
                    check_id,
                    check,
                    response,
                    skill_root,
                    schema_catalog,
                )
            )
        else:
            raise ResultArtifactError(f"unsupported deterministic check type: {check.type}")
    return tuple(results)


def _file_exists(
    check_id: str,
    check: BehaviorCheck,
    outputs_root: Path,
) -> AssertionResult:
    path = _required_path(check)
    target = _output_path(outputs_root, path)
    passed = target.is_file() and not target.is_symlink()
    if not passed:
        return _control_result(
            check_id,
            f"The actor creates the regular output file {path}.",
            False,
            f"outputs/{path} is not a regular file.",
            f"status=completed; outputs/{path} is not a captured regular file",
        )
    return _result(
        check_id,
        f"The actor creates the regular output file {path}.",
        True,
        f"outputs/{path} is a regular file.",
        f"outputs/{path}",
        "regular-file check",
    )


def _path_absent(
    check_id: str,
    check: BehaviorCheck,
    outputs_root: Path,
    execution: HarnessExecution,
) -> AssertionResult:
    path = _required_path(check)
    target = _output_path(outputs_root, path)
    descriptor_paths = tuple(item.path for item in execution.captured_output_paths)
    descriptor_present = any(
        candidate == path or path in candidate.parents
        for candidate in descriptor_paths
    )
    passed = (
        not descriptor_present
        and not target.exists()
        and not target.is_symlink()
    )
    if not passed and target.is_file():
        return _result(
            check_id,
            f"The actor does not create outputs/{path}.",
            False,
            f"outputs/{path} exists.",
            f"outputs/{path}",
            "path exists as a regular file",
        )
    return _control_result(
        check_id,
        f"The actor does not create outputs/{path}.",
        passed,
        f"outputs/{path} {'is absent' if passed else 'exists'}.",
        (
            f"status=completed; outputs/{path} "
            f"{'is absent' if passed else 'was observed as a non-file path'}"
        ),
    )


def _json_schema(
    check_id: str,
    check: BehaviorCheck,
    outputs_root: Path,
    skill_root: Path,
    prepared_schemas: Mapping[PurePosixPath, PreparedFile] | None,
) -> AssertionResult:
    path = _required_path(check)
    schema_path = _required_schema(check)
    target = _output_path(outputs_root, path)
    if not target.is_file():
        return _control_result(
            check_id,
            f"The output {path} conforms to {schema_path}.",
            False,
            f"outputs/{path} is not a regular file.",
            f"status=completed; outputs/{path} is not a captured regular file",
        )
    try:
        document = strict_bounded_json_loads(
            target.read_bytes(),
            maximum_bytes=_MAX_EVAL_OUTPUT_JSON_BYTES,
        )
    except (OSError, BoundedJsonError):
        return _result(
            check_id,
            f"The output {path} conforms to {schema_path}.",
            False,
            f"outputs/{path} is not valid UTF-8 JSON.",
            f"outputs/{path}",
            "JSON parse",
        )
    _, validator = _load_schema(skill_root, schema_path, prepared_schemas)
    errors = _schema_errors(validator, document)
    passed = not errors
    evidence = (
        f"outputs/{path} conforms to the declared JSON schema."
        if passed
        else f"outputs/{path} has {len(errors)} JSON schema violation(s)."
    )
    return _result(
        check_id,
        f"The output {path} conforms to {schema_path}.",
        passed,
        evidence,
        f"outputs/{path}",
        f"validated with evals/{schema_path}",
    )


def _exit_code(
    check_id: str,
    check: BehaviorCheck,
    execution: HarnessExecution,
) -> AssertionResult:
    if check.expected is None:
        raise ResultArtifactError("exit_code check is missing expected")
    passed = execution.exit_code == check.expected
    return _result(
        check_id,
        f"The actor harness exits with code {check.expected}.",
        passed,
        f"The recorded actor harness exit code is {execution.exit_code!r}.",
        "timing.json",
        "exit_code",
    )


def _no_secret_patterns(
    check_id: str,
    response: str,
    outputs_root: Path,
    output_files: Sequence[Path],
) -> AssertionResult:
    findings: list[tuple[str, int, str]] = []
    minimum_finding_count = 0
    finding_count_truncated = False
    scan_budget = SecretScanBudget(
        maximum_findings=_MAX_SECRET_EVIDENCE_REFERENCES,
    )
    scan_incomplete = False
    try:
        for relative, text in _secret_scan_sources(
            response,
            outputs_root,
            output_files,
            maximum_bytes=scan_budget.maximum_bytes,
        ):
            result = scan_budget.scan(text, Path(relative))
            minimum_finding_count += result.minimum_finding_count
            finding_count_truncated = (
                finding_count_truncated or result.finding_count_truncated
            )
            for finding in result.findings:
                findings.append((relative, finding.line, finding.pattern))
            if result.finding_count_truncated:
                break
    except SecretScanLimitError:
        scan_incomplete = True
    passed = minimum_finding_count == 0 and not scan_incomplete
    references = tuple(
        {
            "artifact": artifact,
            "locator": f"line {line}; {pattern}; value redacted",
        }
        for artifact, line, pattern in findings
    ) or (
        {
            "artifact": "outputs/response.md",
            "locator": "response and captured-output high-confidence secret scan",
        },
    )
    return AssertionResult(
        id=check_id,
        kind="check",
        text="The final response and captured text outputs contain no high-confidence secrets.",
        passed=passed,
        checked_by="deterministic",
        evidence=(
            "No high-confidence secret pattern was found."
            if passed
            else (
                "Secret scanning exceeded its bounded evidence budget."
                if not findings
                else "Found "
                + ("at least " if finding_count_truncated or scan_incomplete else "")
                + f"{minimum_finding_count} high-confidence secret occurrence(s); "
                "values redacted."
            )
        ),
        evidence_refs=references,
    )


def _secret_scan_sources(
    response: str,
    outputs_root: Path,
    output_files: Sequence[Path],
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_SECRET_SCAN_BYTES,
) -> Iterator[tuple[str, str]]:
    try:
        consumed = len(response.encode("utf-8"))
    except (UnicodeEncodeError, MemoryError) as error:
        raise SecretScanLimitError("secret scan input could not be bounded") from error
    if consumed > maximum_bytes:
        raise SecretScanLimitError("secret scan exceeds the global byte limit")
    yield "outputs/response.md", response
    for path in output_files:
        try:
            size = path.stat().st_size
            if consumed + size > maximum_bytes:
                raise SecretScanLimitError(
                    "secret scan exceeds the global byte limit"
                )
            content = path.read_bytes()
        except OSError as error:
            raise ResultArtifactError(
                "cannot read captured output for secret scanning"
            ) from error
        consumed += size
        relative = f"outputs/{path.relative_to(outputs_root).as_posix()}"
        yield relative, content.decode("utf-8", errors="ignore")


def _response_protocol(
    check_id: str,
    check: BehaviorCheck,
    response: str,
    skill_root: Path,
    prepared_schemas: Mapping[PurePosixPath, PreparedFile] | None,
) -> AssertionResult:
    if check.format not in ("json", "jsonl"):
        raise ResultArtifactError("response_protocol check has an unsupported format")
    try:
        if check.format == "json":
            values = (
                strict_bounded_json_loads(
                    response,
                    maximum_bytes=_MAX_EVAL_OUTPUT_JSON_BYTES,
                ),
            )
        else:
            try:
                response_bytes = len(response.encode("utf-8"))
            except (UnicodeEncodeError, MemoryError) as error:
                raise BoundedJsonError("JSONL response could not be bounded") from error
            if response_bytes + 2 > _MAX_EVAL_OUTPUT_JSON_BYTES:
                raise BoundedJsonError("JSONL response exceeds the byte limit")
            lines = tuple(line for line in response.splitlines() if line.strip())
            if not lines:
                raise BoundedJsonError("JSONL response is empty")
            parsed = strict_bounded_json_loads(
                "[" + ",".join(lines) + "]",
                maximum_bytes=_MAX_EVAL_OUTPUT_JSON_BYTES,
            )
            if not isinstance(parsed, list):
                raise BoundedJsonError("JSONL response has an invalid shape")
            values = tuple(parsed)
    except BoundedJsonError:
        return _result(
            check_id,
            f"The final response uses the {check.format} protocol.",
            False,
            f"outputs/response.md is not valid {check.format}.",
            "outputs/response.md",
            f"strict {check.format} parse",
        )

    schema_violations = 0
    if check.schema is not None:
        _, validator = _load_schema(skill_root, check.schema, prepared_schemas)
        schema_violations = sum(len(_schema_errors(validator, value)) for value in values)
    passed = schema_violations == 0
    return _result(
        check_id,
        f"The final response uses the {check.format} protocol.",
        passed,
        (
            f"outputs/response.md is valid {check.format}."
            if passed
            else f"outputs/response.md has {schema_violations} JSON schema violation(s)."
        ),
        "outputs/response.md",
        f"strict {check.format} parse",
    )


def list_safe_output_files(outputs_root: Path) -> tuple[Path, ...]:
    """List contained regular output files or reject the artifact tree."""
    if outputs_root.is_symlink() or not outputs_root.is_dir():
        raise ResultArtifactError("outputs directory must be a regular directory")
    files: list[Path] = []
    pending = [outputs_root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise ResultArtifactError("cannot inspect captured outputs") from error
        for entry in entries:
            path = Path(entry.path)
            try:
                metadata = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ResultArtifactError("cannot inspect captured output entry") from error
            if stat.S_ISLNK(metadata.st_mode):
                raise ResultArtifactError("captured outputs cannot contain symlinks")
            if stat.S_ISDIR(metadata.st_mode):
                pending.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                files.append(path)
            else:
                raise ResultArtifactError("captured outputs cannot contain special files")
    return tuple(files)


def _output_path(outputs_root: Path, relative: PurePosixPath) -> Path:
    _require_safe_relative_path(relative)
    target = outputs_root.joinpath(*relative.parts)
    current = target
    while current != outputs_root:
        if current.is_symlink():
            raise ResultArtifactError("captured output path contains a symlink")
        current = current.parent
    return target


def _load_schema(
    skill_root: Path,
    relative: PurePosixPath,
    prepared_schemas: Mapping[PurePosixPath, PreparedFile] | None = None,
) -> tuple[Mapping[str, object], Draft202012Validator]:
    _require_safe_relative_path(relative)
    schema_root = skill_root / "evals"
    path = schema_root.joinpath(*relative.parts)
    try:
        if prepared_schemas is None:
            try:
                resolved_root = schema_root.resolve(strict=True)
                resolved = path.resolve(strict=True)
            except (OSError, RuntimeError) as error:
                raise ResultArtifactError(
                    "declared eval schema cannot be resolved"
                ) from error
            if (
                _has_symlink_component(path, schema_root)
                or not resolved.is_relative_to(resolved_root)
                or not resolved.is_file()
            ):
                raise ResultArtifactError(
                    "declared eval schema is not a contained regular file"
                )
            if resolved.stat().st_size > MAX_JSON_SCHEMA_BYTES:
                raise JsonSchemaPolicyError(
                    "JSON Schema exceeds the 256 KiB byte limit"
                )
            content = resolved.read_bytes()
        else:
            prepared = prepared_schemas.get(relative)
            if prepared is None:
                raise ResultArtifactError(
                    "declared eval schema is missing from prepared material"
                )
            if hashlib.sha256(prepared.content).hexdigest() != prepared.sha256:
                raise ResultArtifactError(
                    "prepared eval schema failed integrity verification"
                )
            content = prepared.content
        document = strict_bounded_json_loads(
            content,
            maximum_bytes=MAX_JSON_SCHEMA_BYTES,
        )
        if not isinstance(document, Mapping):
            raise ResultArtifactError("declared eval schema must be a JSON object")
        validator = build_safe_json_schema_validator(document)
    except JsonSchemaPolicyError as error:
        raise ResultArtifactError(
            f"declared eval schema violates the safe JSON Schema policy: {error}"
        ) from error
    except ResultArtifactError:
        raise
    except (
        OSError,
        BoundedJsonError,
        MemoryError,
        SystemError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ResultArtifactError("declared eval schema is invalid") from error
    return document, validator


def _schema_errors(
    validator: Draft202012Validator,
    document: object,
) -> tuple[object, ...]:
    try:
        return bounded_json_schema_errors(validator, document)
    except (
        JsonSchemaPolicyError,
        MemoryError,
        SystemError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ResultArtifactError(
            "declared eval schema validation violated the safe JSON Schema policy"
        ) from error


def _prepared_schema_catalog(
    prepared_schemas: Sequence[tuple[PurePosixPath, PreparedFile]] | None,
) -> Mapping[PurePosixPath, PreparedFile] | None:
    if prepared_schemas is None:
        return None
    try:
        catalog = dict(prepared_schemas)
    except (
        TypeError,
        ValueError,
        MemoryError,
        SystemError,
        RecursionError,
        OverflowError,
    ) as error:
        raise ResultArtifactError("prepared eval schema catalog is invalid") from error
    if len(catalog) != len(prepared_schemas) or any(
        not isinstance(path, PurePosixPath) or not isinstance(schema, PreparedFile)
        for path, schema in catalog.items()
    ):
        raise ResultArtifactError("prepared eval schema catalog is invalid")
    return catalog


def _required_path(check: BehaviorCheck) -> PurePosixPath:
    if check.path is None:
        raise ResultArtifactError(f"{check.type} check is missing path")
    return check.path


def _required_schema(check: BehaviorCheck) -> PurePosixPath:
    if check.schema is None:
        raise ResultArtifactError(f"{check.type} check is missing schema")
    return check.schema


def _require_safe_relative_path(path: PurePosixPath) -> None:
    if (
        path.is_absolute()
        or not path.parts
        or str(path) in ("", ".")
        or ".." in path.parts
        or "\\" in str(path)
    ):
        raise ResultArtifactError("eval check path must be a contained relative path")


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


def _result(
    check_id: str,
    text: str,
    passed: bool,
    evidence: str,
    artifact: str,
    locator: str,
) -> AssertionResult:
    return AssertionResult(
        id=check_id,
        kind="check",
        text=text,
        passed=passed,
        checked_by="deterministic",
        evidence=evidence,
        evidence_refs=({"artifact": artifact, "locator": locator},),
    )


def _control_result(
    check_id: str,
    text: str,
    passed: bool,
    evidence: str,
    locator: str,
) -> AssertionResult:
    return AssertionResult(
        id=check_id,
        kind="check",
        text=text,
        passed=passed,
        checked_by="deterministic",
        evidence=evidence,
        evidence_refs=(completed_attempt_control_evidence_reference(locator),),
    )
