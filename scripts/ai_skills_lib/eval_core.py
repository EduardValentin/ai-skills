"""Shared, runner-neutral mechanics for durable LLM-backed evaluation results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import threading
import time
from typing import Literal
import uuid

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from scripts.ai_skills_lib.authored_content import (
    JsonPreflightError,
    SecretScanBudget,
    prepare_durable_sensitive_text,
    preflight_bounded_json_structure,
)
from scripts.ai_skills_lib.harness import (
    bind_harness_request,
    CapturedOutputPath,
    execution_binding_from_document,
    execution_binding_matches_request,
    HarnessAdapter,
    HarnessCapabilities,
    HarnessExecution,
    HarnessExecutionBinding,
    HarnessRequest,
    canonical_codex_skill_path,
    PreparedFile,
    validated_actor_skill_read_lifecycle,
)


_SCHEMA_ROOT = Path(__file__).resolve().parents[2] / "schemas" / "ai-skills"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_MAX_JUDGE_RESPONSE_BYTES = 256 * 1024
MAX_JUDGE_ARTIFACT_BYTES = 32 * 1024
MAX_PRESERVED_JUDGE_TRACE_SUFFIX_BYTES = 16 * 1024
MAX_PRESERVED_JUDGE_TRACE_BYTES = (
    MAX_JUDGE_ARTIFACT_BYTES + MAX_PRESERVED_JUDGE_TRACE_SUFFIX_BYTES
)
MAX_JUDGE_PROMPT_BYTES = 512 * 1024
_MAX_JUDGE_EVIDENCE_CHARS = 4096
_MAX_JUDGE_EVIDENCE_REFS = 16
_MAX_JUDGE_ARTIFACT_NAME_CHARS = 512
_MAX_JUDGE_LOCATOR_CHARS = 1024
_MAX_JUDGE_DIAGNOSTIC_BYTES = 4096
_MAX_DECLARED_ATTEMPTS = 1024
_MAX_RESULT_JSON_FILE_BYTES = 4 * 1024 * 1024
_MAX_RESULT_JSON_NODES = 100_000
_MAX_RESULT_JSON_DEPTH = 32
_MAX_RESULT_JSON_SCALAR_BYTES = 64 * 1024
_MAX_RESULT_JSON_NUMBER_CHARS = 128
_MAX_RESULT_FILE_BYTES = 16 * 1024 * 1024
_MAX_RESULT_TREE_BYTES = 256 * 1024 * 1024
_MAX_RESULT_TREE_ENTRIES = 100_000
_MAX_RESULT_TREE_DEPTH = 40
_MAX_RESULT_ANCESTOR_DEPTH = 256
_MAX_RESULT_ENTRIES_PER_ATTEMPT = 4096
_MAX_RESULT_ROOT_ENTRIES = 4
_MAX_EVIDENCE_DIGEST_BYTES = 64 * 1024 * 1024
_MAX_EVIDENCE_DIGEST_ENTRIES = 4096
_MAX_EVIDENCE_DIGEST_DEPTH = 64
_MAX_OFFLINE_SCHEMA_BYTES = 1024 * 1024
_RESULT_READ_CHUNK_BYTES = 64 * 1024

_ROOT_RESULT_FILES = frozenset(
    {"invocation.json", "benchmark.json", "summary.md"}
)
_ROOT_FINALIZATION_BYTE_RESERVES = {
    "benchmark.json": _MAX_RESULT_JSON_FILE_BYTES,
    "summary.md": _MAX_RESULT_FILE_BYTES,
}


@dataclass(frozen=True)
class _PersistedAttemptArtifact:
    path_attribute: str
    relative_parts: tuple[str, ...]
    content_kind: str
    schema_name: str | None
    required_for_gradable_attempt: bool
    allowed_as_evidence: bool
    write_as_completion_marker: bool = False


_PERSISTED_ATTEMPT_ARTIFACT_CONTRACT = (
    _PersistedAttemptArtifact(
        path_attribute="manifest",
        relative_parts=("attempt.json",),
        content_kind="json",
        schema_name="attempt.schema.json",
        required_for_gradable_attempt=True,
        allowed_as_evidence=False,
    ),
    _PersistedAttemptArtifact(
        path_attribute="timing",
        relative_parts=("timing.json",),
        content_kind="json",
        schema_name="timing.schema.json",
        required_for_gradable_attempt=True,
        allowed_as_evidence=True,
    ),
    _PersistedAttemptArtifact(
        path_attribute="grading",
        relative_parts=("grading.json",),
        content_kind="json",
        schema_name="grading.schema.json",
        required_for_gradable_attempt=True,
        allowed_as_evidence=False,
        write_as_completion_marker=True,
    ),
    _PersistedAttemptArtifact(
        path_attribute="grading_basis",
        relative_parts=("grading_basis.json",),
        content_kind="json",
        schema_name="grading-basis.schema.json",
        required_for_gradable_attempt=False,
        allowed_as_evidence=False,
    ),
    _PersistedAttemptArtifact(
        path_attribute="response",
        relative_parts=("outputs", "response.md"),
        content_kind="text",
        schema_name=None,
        required_for_gradable_attempt=True,
        allowed_as_evidence=True,
    ),
    _PersistedAttemptArtifact(
        path_attribute="transcript",
        relative_parts=("transcript.md",),
        content_kind="text",
        schema_name=None,
        required_for_gradable_attempt=True,
        allowed_as_evidence=True,
    ),
    _PersistedAttemptArtifact(
        path_attribute="execution_trace",
        relative_parts=("execution_trace.jsonl",),
        content_kind="text",
        schema_name=None,
        required_for_gradable_attempt=True,
        allowed_as_evidence=True,
    ),
    _PersistedAttemptArtifact(
        path_attribute="manual_grading",
        relative_parts=("manual_grading.json",),
        content_kind="json",
        schema_name="grading.schema.json",
        required_for_gradable_attempt=False,
        allowed_as_evidence=False,
    ),
    _PersistedAttemptArtifact(
        path_attribute="feedback",
        relative_parts=("feedback.json",),
        content_kind="json",
        schema_name=None,
        required_for_gradable_attempt=False,
        allowed_as_evidence=False,
    ),
)
_ATTEMPT_ARTIFACT_BY_ATTRIBUTE = {
    artifact.path_attribute: artifact
    for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
}
_FIXED_EVIDENCE_ARTIFACT_PATHS = frozenset(
    artifact.relative_parts
    for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
    if artifact.allowed_as_evidence
)
_PERSISTED_ATTEMPT_FIXED_ENTRY_PATHS = frozenset(
    artifact.relative_parts[:depth]
    for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
    for depth in range(1, len(artifact.relative_parts) + 1)
)
_PERSISTED_ATTEMPT_FIXED_ENTRY_RESERVE = (
    1 + len(_PERSISTED_ATTEMPT_FIXED_ENTRY_PATHS)
)
MAX_CAPTURED_OUTPUT_ENTRIES_PER_ATTEMPT = (
    _MAX_RESULT_ENTRIES_PER_ATTEMPT
    - _PERSISTED_ATTEMPT_FIXED_ENTRY_RESERVE
)
_RESULT_TREE_WRITE_LOCK = threading.Lock()


class ResultArtifactError(RuntimeError):
    """Raised when preserved evaluation evidence cannot be trusted."""

    exit_code = 2


@dataclass(frozen=True)
class TerminalDecision:
    """One precedence-resolved terminal state and its public representations."""

    key: Literal[
        "pass",
        "expectations_failed",
        "pending_review",
        "execution_error",
    ]
    exit_code: int
    durable_label: str
    console_label: str


def resolve_terminal_decision(
    *,
    execution_error: bool,
    pending_review: bool,
    expectation_failure: bool,
) -> TerminalDecision:
    """Resolve terminal state using the repository's single precedence policy."""
    if execution_error:
        return TerminalDecision(
            key="execution_error",
            exit_code=2,
            durable_label="execution error",
            console_label="EXECUTION ERROR",
        )
    if pending_review:
        return TerminalDecision(
            key="pending_review",
            exit_code=1,
            durable_label="pending review",
            console_label="PENDING REVIEW",
        )
    if expectation_failure:
        return TerminalDecision(
            key="expectations_failed",
            exit_code=1,
            durable_label="expectations failed",
            console_label="EXPECTATIONS FAILED",
        )
    return TerminalDecision(
        key="pass",
        exit_code=0,
        durable_label="pass",
        console_label="OK",
    )


class StructuredSkillPathKind(Enum):
    CANONICAL_TARGET = "canonical_target"
    CANONICAL_OTHER = "canonical_other"
    NONCANONICAL = "noncanonical"


def classify_structured_skill_path(
    path: object,
    skill_name: str,
) -> StructuredSkillPathKind:
    """Classify one structured skill path without resolving the filesystem."""
    if not isinstance(path, (str, Path)):
        return StructuredSkillPathKind.NONCANONICAL
    rendered = str(path)
    components = rendered.split("/")
    if (
        not rendered.startswith("/")
        or "\\" in rendered
        or "\x00" in rendered
        or any(component in {"", ".", ".."} for component in components[1:])
    ):
        return StructuredSkillPathKind.NONCANONICAL
    if (
        len(components) < 4
        or components[-3] != "skills"
        or components[-1] != "SKILL.md"
        or re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*",
            components[-2],
        )
        is None
    ):
        return StructuredSkillPathKind.NONCANONICAL
    if components[-2] == skill_name:
        return StructuredSkillPathKind.CANONICAL_TARGET
    return StructuredSkillPathKind.CANONICAL_OTHER


def classify_codex_skill_evidence_path(
    path: object,
    skill_name: str,
) -> StructuredSkillPathKind:
    """Classify evidence bound to the canonical logical Codex skill root."""
    classification = classify_structured_skill_path(path, skill_name)
    if classification is StructuredSkillPathKind.NONCANONICAL:
        return classification
    rendered = str(path)
    installed_skill_name = PurePosixPath(rendered).parent.name
    if rendered != str(canonical_codex_skill_path(installed_skill_name)):
        return StructuredSkillPathKind.NONCANONICAL
    return classification


def digest_evidence_bundle(
    directories: Sequence[str],
    files: Sequence[tuple[str, bytes]],
) -> str:
    """Return one canonical digest for an exact preserved evidence tree."""
    normalized_directories = tuple(sorted(directories))
    normalized_files = tuple(sorted(files, key=lambda item: item[0]))
    directory_paths = set(normalized_directories)
    file_paths = {path for path, _ in normalized_files}
    if (
        len(directory_paths) != len(normalized_directories)
        or len(file_paths) != len(normalized_files)
        or directory_paths & file_paths
    ):
        raise ResultArtifactError("evidence digest paths are ambiguous")
    if (
        len(normalized_directories) + len(normalized_files)
        > _MAX_EVIDENCE_DIGEST_ENTRIES
    ):
        raise ResultArtifactError("evidence digest exceeds the entry limit")
    for path in (*normalized_directories, *file_paths):
        _require_evidence_digest_path(path)
    if not all(isinstance(content, bytes) for _, content in normalized_files):
        raise ResultArtifactError("evidence digest content must be immutable bytes")
    if sum(len(content) for _, content in normalized_files) > _MAX_EVIDENCE_DIGEST_BYTES:
        raise ResultArtifactError("evidence digest exceeds the byte limit")

    digest = hashlib.sha256()
    for path in normalized_directories:
        digest.update(b"D\0")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
    for path, content in normalized_files:
        digest.update(b"F\0")
        digest.update(path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def _require_evidence_digest_path(path: str) -> None:
    if not isinstance(path, str):
        raise ResultArtifactError("evidence digest path must be text")
    candidate = PurePosixPath(path)
    if (
        path in ("", ".")
        or candidate.is_absolute()
        or str(candidate) != path
        or ".." in candidate.parts
        or "\\" in path
        or "\x00" in path
        or len(candidate.parts) > _MAX_EVIDENCE_DIGEST_DEPTH
    ):
        raise ResultArtifactError("evidence digest path is invalid")


def completed_attempt_control_evidence_reference(
    locator: str,
) -> Mapping[str, str]:
    """Reference the required runner-owned record for a completed attempt."""
    artifact = _ATTEMPT_ARTIFACT_BY_ATTRIBUTE["timing"]
    if not artifact.required_for_gradable_attempt or not artifact.allowed_as_evidence:
        raise ResultArtifactError(
            "completed-attempt control evidence is not a required evidence artifact"
        )
    return {
        "artifact": "/".join(artifact.relative_parts),
        "locator": locator,
    }


class JudgeExecutionError(ResultArtifactError):
    """Raised with complete normalized evidence from an untrusted judge execution."""

    def __init__(self, message: str, execution: HarnessExecution):
        super().__init__(message)
        self.execution = execution


class _JsonBoundaryError(ValueError):
    """Internal marker for sanitized strict-JSON boundary failures."""


@dataclass(frozen=True)
class _StableFileRead:
    content: bytes
    metadata: tuple[int, ...]


@dataclass(frozen=True)
class _StableContentIdentity:
    metadata: tuple[int, ...]
    digest: bytes


@dataclass(frozen=True)
class _ResultTreeSnapshot:
    files: Mapping[tuple[str, ...], tuple[int, ...]]
    directories: Mapping[tuple[str, ...], tuple[int, ...]]
    total_bytes: int


@dataclass
class _ResultTreeScanState:
    entries: int = 0
    total_bytes: int = 0


@dataclass
class ResultWorkspace:
    """Invocation-owned durable result and human-summary paths."""

    invocation_id: str
    root: Path
    attempts: Path
    invocation_manifest: Path
    benchmark: Path
    output_summary: Path
    repository_root: Path
    repository_identity: tuple[int, int] = field(repr=False, compare=False)
    root_identity: tuple[int, int, int] = field(repr=False, compare=False)
    attempts_identity: tuple[int, int, int] = field(repr=False, compare=False)
    invocation_identity: _StableContentIdentity | None = field(
        default=None,
        repr=False,
        compare=False,
    )


@dataclass(frozen=True)
class AttemptPaths:
    """Canonical paths for one declared evaluation attempt."""

    invocation_id: str
    root: Path
    manifest: Path
    response: Path
    transcript: Path
    execution_trace: Path
    timing: Path
    grading: Path
    grading_basis: Path
    manual_grading: Path
    feedback: Path
    workspace_root: Path = field(repr=False, compare=False)
    repository_identity: tuple[int, int] = field(repr=False, compare=False)
    workspace_identity: tuple[int, int, int] = field(repr=False, compare=False)
    attempts_identity: tuple[int, int, int] = field(repr=False, compare=False)
    attempt_identity: tuple[int, int, int] = field(repr=False, compare=False)
    invocation_identity: _StableContentIdentity = field(repr=False, compare=False)
    directory_identities: Mapping[tuple[str, ...], tuple[int, int, int]] = field(
        repr=False,
        compare=False,
    )


def _attempt_paths(
    root: Path,
    *,
    invocation_id: str,
    workspace_root: Path,
    repository_identity: tuple[int, int],
    workspace_identity: tuple[int, int, int],
    attempts_identity: tuple[int, int, int],
    attempt_identity: tuple[int, int, int],
    invocation_identity: _StableContentIdentity,
    directory_identities: Mapping[tuple[str, ...], tuple[int, int, int]],
) -> AttemptPaths:
    return AttemptPaths(
        invocation_id=invocation_id,
        root=root,
        workspace_root=workspace_root,
        repository_identity=repository_identity,
        workspace_identity=workspace_identity,
        attempts_identity=attempts_identity,
        attempt_identity=attempt_identity,
        invocation_identity=invocation_identity,
        directory_identities=dict(directory_identities),
        **{
            artifact.path_attribute: root.joinpath(*artifact.relative_parts)
            for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
        },
    )


def _attempt_artifact_parts(
    attempt_parts: tuple[str, ...], path_attribute: str
) -> tuple[str, ...]:
    artifact = _ATTEMPT_ARTIFACT_BY_ATTRIBUTE[path_attribute]
    return (*attempt_parts, *artifact.relative_parts)


def _attempt_artifact_schema(path_attribute: str) -> str:
    schema_name = _ATTEMPT_ARTIFACT_BY_ATTRIBUTE[path_attribute].schema_name
    if schema_name is None:
        raise ResultArtifactError("attempt artifact has no declared JSON schema")
    return schema_name


def _write_persisted_attempt_artifacts(
    paths: AttemptPaths,
    values: Mapping[str, object],
) -> None:
    unknown = set(values) - set(_ATTEMPT_ARTIFACT_BY_ATTRIBUTE)
    if unknown:
        raise ResultArtifactError("attempt writer received an undeclared artifact")
    artifacts = sorted(
        _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT,
        key=lambda artifact: artifact.write_as_completion_marker,
    )
    prepared: list[tuple[_PersistedAttemptArtifact, str, bytes]] = []
    for artifact in artifacts:
        if artifact.path_attribute not in values:
            continue
        value = values[artifact.path_attribute]
        if artifact.content_kind == "json":
            if not isinstance(value, Mapping):
                raise ResultArtifactError("attempt JSON artifact must be an object")
            text = _serialize_json_document(value)
        else:
            if not isinstance(value, str):
                raise ResultArtifactError("attempt text artifact must be text")
            text = value
        try:
            content = text.encode("utf-8")
        except UnicodeError as error:
            raise ResultArtifactError("cannot encode attempt artifact") from error
        prepared.append((artifact, text, content))

    with _RESULT_TREE_WRITE_LOCK:
        _require_persisted_attempt_capacity(paths, prepared)
        for artifact, text, _ in prepared:
            _write_attempt_text_once(
                paths,
                artifact.relative_parts,
                text,
            )
        _require_persisted_attempt_capacity(paths, ())


def _require_persisted_attempt_capacity(
    paths: AttemptPaths,
    prepared: Sequence[tuple[_PersistedAttemptArtifact, str, bytes]],
) -> None:
    attempt = _parse_result_document(
        _read_attempt_artifact(
            paths,
            ("attempt.json",),
            maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
            label="cannot read attempt declaration for publication",
            limit_name="JSON byte limit",
        ).content,
        paths.manifest,
        _attempt_artifact_schema("manifest"),
    )
    root_descriptor: int | None = None
    try:
        root_descriptor, root_metadata = _open_result_root(
            paths.workspace_root,
            paths.workspace_root,
        )
        if (
            _result_directory_identity(os.fstat(root_descriptor))
            != paths.workspace_identity
        ):
            raise ResultArtifactError(
                "results directory changed before attempt publication"
            )
        invocation_read = _read_required_invocation(
            root_descriptor,
            paths.workspace_root,
        )
        invocation = _parse_result_document(
            invocation_read.content,
            paths.workspace_root / "invocation.json",
            "invocation.schema.json",
        )
        declared_attempts = _declared_attempts(invocation)
        if declared_attempts.get(attempt["run_id"]) != attempt:
            raise ResultArtifactError(
                "attempt publication is not declared by the invocation"
            )
        snapshot = _snapshot_result_tree(
            root_descriptor,
            paths.workspace_root,
            declared_attempt_count=len(declared_attempts),
        )

        current_paths = set(snapshot.files) | set(snapshot.directories)
        attempt_prefix = ("attempts", paths.root.name)
        reserved_paths = {
            ("attempts",),
            *((name,) for name in _ROOT_RESULT_FILES),
            attempt_prefix,
            *(
                (*attempt_prefix, *relative_parts)
                for relative_parts in _PERSISTED_ATTEMPT_FIXED_ENTRY_PATHS
            ),
        }
        planned_paths = {
            (*attempt_prefix, *artifact.relative_parts)
            for artifact, _, _ in prepared
        }
        required_paths = reserved_paths | planned_paths
        current_entries = len(snapshot.files) + len(snapshot.directories) - 1
        added_entries = sum(path not in current_paths for path in required_paths)
        current_attempt_entries = sum(
            path[: len(attempt_prefix)] == attempt_prefix
            for path in current_paths
            if path
        )
        added_attempt_entries = sum(
            path not in current_paths
            and path[: len(attempt_prefix)] == attempt_prefix
            for path in required_paths
        )
        if (
            current_attempt_entries + added_attempt_entries
            > _MAX_RESULT_ENTRIES_PER_ATTEMPT
        ):
            raise ResultArtifactError(
                "attempt publication exceeds the per-attempt entry-count limit"
            )
        if (
            current_entries + added_entries
            > _result_tree_entry_limit(len(declared_attempts))
        ):
            raise ResultArtifactError(
                "attempt publication exceeds the result-tree entry-count limit"
            )

        planned_bytes = sum(len(content) for _, _, content in prepared)
        finalization_reserve = sum(
            maximum_bytes
            for name, maximum_bytes in _ROOT_FINALIZATION_BYTE_RESERVES.items()
            if (name,) not in snapshot.files
        )
        if (
            snapshot.total_bytes + planned_bytes + finalization_reserve
            > _MAX_RESULT_TREE_BYTES
        ):
            raise ResultArtifactError(
                "attempt publication exceeds the cumulative result-tree byte limit"
            )
        _verify_open_result_root(
            root_descriptor,
            paths.workspace_root,
            root_metadata,
        )
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)


def _write_attempt_text_once(
    paths: AttemptPaths,
    relative_parts: tuple[str, ...],
    text: str,
) -> _StableContentIdentity:
    try:
        content = text.encode("utf-8")
    except (AttributeError, UnicodeError) as error:
        raise ResultArtifactError("cannot encode attempt artifact") from error
    with _open_bound_attempt_artifact_parent(
        paths,
        relative_parts,
    ) as (parent_descriptor, name):
        try:
            os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            pass
        else:
            raise ResultArtifactError(
                f"result artifact already exists: {paths.root.joinpath(*relative_parts)}"
            )
        metadata = _write_atomic_result_file_at(
            parent_descriptor,
            name,
            content,
            expected_metadata=None,
            maximum_bytes=max(_MAX_RESULT_FILE_BYTES, len(content)),
        )
        os.fsync(parent_descriptor)
    return _StableContentIdentity(
        metadata=metadata,
        digest=hashlib.sha256(content).digest(),
    )


def _read_attempt_artifact(
    paths: AttemptPaths,
    relative_parts: tuple[str, ...],
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str = "byte limit",
) -> _StableFileRead:
    with _open_bound_attempt_artifact_parent(
        paths,
        relative_parts,
    ) as (parent_descriptor, name):
        try:
            observed = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise ResultArtifactError(f"{label} cannot be read safely") from error
        if not stat.S_ISREG(observed.st_mode):
            raise ResultArtifactError(
                f"{label} must be a regular non-symlink file"
            )
        return _read_stable_file_at(
            parent_descriptor,
            name,
            observed,
            maximum_bytes=maximum_bytes,
            label=label,
            limit_name=limit_name,
        )


@dataclass(frozen=True)
class TimingRecord:
    """Schema-compatible observable timing and token usage for one run."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    harness: str
    model: str | None
    reasoning_effort: str | None
    started_at: str
    ended_at: str
    duration_ms: int
    total_tokens: int | None
    status: str
    exit_code: int | None
    token_details: Mapping[str, object]
    invocation_id: str | None = None
    execution_binding: HarnessExecutionBinding | None = None
    successful_skill_reads: tuple[Path, ...] = field(default_factory=tuple)
    expected_skill_path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": "ai-skills.eval.timing.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "harness": self.harness,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "duration_ms": self.duration_ms,
            "total_tokens": self.total_tokens,
            "status": self.status,
            "exit_code": self.exit_code,
            "token_details": dict(self.token_details),
        }
        if self.invocation_id is not None:
            document["invocation_id"] = self.invocation_id
        document["execution_binding"] = (
            self.execution_binding.to_dict()
            if self.execution_binding is not None
            else None
        )
        document["successful_skill_reads"] = [
            str(path) for path in self.successful_skill_reads
        ]
        document["expected_skill_path"] = (
            str(self.expected_skill_path)
            if self.expected_skill_path is not None
            else None
        )
        return document


@dataclass(frozen=True)
class AssertionResult:
    """One guide-compatible assertion or deterministic check result."""

    id: str
    kind: str
    text: str
    passed: bool
    checked_by: str
    evidence: str
    evidence_refs: tuple[Mapping[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "passed": self.passed,
            "checked_by": self.checked_by,
            "evidence": self.evidence,
            "evidence_refs": [dict(reference) for reference in self.evidence_refs],
        }


@dataclass(frozen=True)
class AssertionDefinition:
    """Caller-owned identity and text for one assertion sent to a judge."""

    id: str
    kind: str
    text: str


@dataclass(frozen=True)
class AssertionContract:
    """Invocation-declared assertion identity and grading authority."""

    id: str
    kind: str
    text: str
    checked_by: str

    def to_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "checked_by": self.checked_by,
        }


@dataclass(frozen=True)
class GraderRecord:
    """Identity of the human, model, or deterministic grader."""

    type: str
    model: str | None
    reasoning_effort: str | None
    prompt_version: str
    reviewer_identity: str | None = None
    reviewer_label: str | None = None

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "type": self.type,
            "model": self.model,
            "reasoning_effort": self.reasoning_effort,
            "prompt_version": self.prompt_version,
        }
        if self.reviewer_identity is not None:
            document["reviewer_identity"] = self.reviewer_identity
        if self.reviewer_label is not None:
            document["reviewer_label"] = self.reviewer_label
        return document


@dataclass(frozen=True)
class GradingSummary:
    """Counts derived from all assertion results in one grading record."""

    passed: int
    failed: int
    total: int
    pass_rate: float

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "failed": self.failed,
            "total": self.total,
            "pass_rate": self.pass_rate,
        }


@dataclass(frozen=True)
class AggregationMetadata:
    """Caller-provided generic variant and outcome contribution metadata."""

    group_id: str
    variant: str
    contributes_to_outcome: bool
    required_variants: tuple[str, ...]
    compare_to: str | None = None
    minimum_pass_rate: float | None = None
    configured_runs: int | None = None
    run_number: int | None = None

    def __post_init__(self) -> None:
        repeated_fields = (
            self.minimum_pass_rate,
            self.configured_runs,
            self.run_number,
        )
        if any(value is not None for value in repeated_fields) and any(
            value is None for value in repeated_fields
        ):
            raise ValueError(
                "threshold aggregation requires pass rate, configured runs, and run number"
            )
        if self.minimum_pass_rate is not None and not 0 < self.minimum_pass_rate <= 1:
            raise ValueError("minimum pass rate must be greater than zero and at most one")
        if self.configured_runs is not None and (
            self.configured_runs < 1
            or self.run_number is None
            or not 1 <= self.run_number <= self.configured_runs
        ):
            raise ValueError("aggregation run number must belong to the configured run set")

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "group_id": self.group_id,
            "variant": self.variant,
            "contributes_to_outcome": self.contributes_to_outcome,
            "required_variants": list(self.required_variants),
        }
        if self.compare_to is not None:
            value["compare_to"] = self.compare_to
        if self.minimum_pass_rate is not None:
            value["minimum_pass_rate"] = self.minimum_pass_rate
            value["configured_runs"] = self.configured_runs
            value["run_number"] = self.run_number
        return value


@dataclass(frozen=True)
class AttemptManifest:
    """Immutable caller-owned identity and aggregation policy for one attempt."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    aggregation: AggregationMetadata
    assertion_contract: tuple[AssertionContract, ...]
    runtime_input_sha256: str
    scenario_definition_sha256: str
    deterministic_input_sha256: str | None = None
    judge_control_sha256: str | None = None
    expected_activation: bool | None = None
    expected_skill_catalog_path: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[0-9a-f]{64}", self.runtime_input_sha256):
            raise ValueError("attempt runtime input digest must be lowercase SHA-256")
        if not re.fullmatch(r"[0-9a-f]{64}", self.scenario_definition_sha256):
            raise ValueError(
                "attempt scenario definition digest must be lowercase SHA-256"
            )
        if not self.assertion_contract:
            raise ValueError("attempts require an immutable assertion contract")
        identifiers = [assertion.id for assertion in self.assertion_contract]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("attempt assertion identifiers must be unique")
        if self.run_kind == "trigger":
            if (
                self.deterministic_input_sha256 is not None
                or self.judge_control_sha256 is not None
            ):
                raise ValueError(
                    "trigger attempts cannot declare behavior-only inputs"
                )
            if type(self.expected_activation) is not bool:
                raise ValueError(
                    "trigger attempts require one immutable expected activation"
                )
            if not self.expected_skill_catalog_path:
                raise ValueError(
                    "trigger attempts require one immutable installed catalog path"
                )
        else:
            if self.run_kind != self.aggregation.variant:
                raise ValueError(
                    "behavior attempt run kind must match its aggregation variant"
                )
            if not self.deterministic_input_sha256 or not re.fullmatch(
                r"[0-9a-f]{64}", self.deterministic_input_sha256
            ):
                raise ValueError(
                    "behavior attempts require a lowercase deterministic input SHA-256"
                )
            if not self.judge_control_sha256 or not re.fullmatch(
                r"[0-9a-f]{64}", self.judge_control_sha256
            ):
                raise ValueError(
                    "behavior attempts require a lowercase judge control SHA-256"
                )
            if (
                self.expected_activation is not None
                or self.expected_skill_catalog_path is not None
            ):
                raise ValueError(
                    "only trigger attempts may declare activation or catalog expectations"
                )

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": "ai-skills.eval.attempt.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "runtime_input_sha256": self.runtime_input_sha256,
            "scenario_definition_sha256": self.scenario_definition_sha256,
            "assertion_contract": [
                assertion.to_dict() for assertion in self.assertion_contract
            ],
            "aggregation": self.aggregation.to_dict(),
        }
        if self.deterministic_input_sha256 is not None:
            document["deterministic_input_sha256"] = (
                self.deterministic_input_sha256
            )
        if self.judge_control_sha256 is not None:
            document["judge_control_sha256"] = self.judge_control_sha256
        if self.expected_activation is not None:
            document["expected_activation"] = self.expected_activation
        if self.expected_skill_catalog_path is not None:
            document["expected_skill_catalog_path"] = (
                self.expected_skill_catalog_path
            )
        return document


@dataclass(frozen=True)
class PreflightInvocationBinding:
    """One invocation identity proven on both sides of runtime preflight."""

    workspace_root: Path
    command: str
    metadata: tuple[int, ...]
    digest: bytes


@dataclass(frozen=True)
class BoundPreflightReceipt:
    """Capabilities that are usable only with their proven invocation set."""

    adapter: HarnessAdapter = field(repr=False, compare=False)
    capabilities: HarnessCapabilities
    require_fixtures: bool
    bindings: tuple[PreflightInvocationBinding, ...]


@dataclass(frozen=True)
class JudgeGradingContext:
    """Caller-owned grading identity, scope, and aggregation policy."""

    invocation_id: str
    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    prompt_version: str
    graded_at: str
    allowed_evidence_artifacts: tuple[str, ...]
    expected_assertions: tuple[AssertionDefinition, ...]
    aggregation: AggregationMetadata


@dataclass(frozen=True)
class GradingRecord:
    """Complete generated or manual grade for one preserved run."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    grade_source: str
    grader: GraderRecord
    graded_at: str
    assertion_results: tuple[AssertionResult, ...]
    summary: GradingSummary
    aggregation: AggregationMetadata
    measurements: Mapping[str, float] = field(default_factory=dict)
    evidence_sha256: str | None = None
    invocation_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": "ai-skills.eval.grading.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "grade_source": self.grade_source,
            "grader": self.grader.to_dict(),
            "graded_at": self.graded_at,
            "assertion_results": [result.to_dict() for result in self.assertion_results],
            "summary": self.summary.to_dict(),
            "aggregation": self.aggregation.to_dict(),
        }
        if self.measurements:
            document["measurements"] = dict(self.measurements)
        if self.evidence_sha256 is not None:
            document["evidence_sha256"] = self.evidence_sha256
        if self.invocation_id is not None:
            document["invocation_id"] = self.invocation_id
        return document


@dataclass(frozen=True)
class JudgeInvocationResult:
    """A generated grade together with its preservable model execution evidence."""

    grading: GradingRecord
    execution: HarnessExecution


@dataclass(frozen=True)
class GradingBasisRecord:
    """Raw judge result and deterministic checks used to derive one behavior grade."""

    run_id: str
    skill_name: str
    case_id: str
    run_kind: str
    judge_response: str
    judge_control: str
    judge_prompt_sha256: str
    allowed_evidence_artifacts: tuple[str, ...]
    judge_model: str
    judge_reasoning_effort: str
    judge_duration_ms: int
    judge_total_tokens: int | None
    judge_prompt_version: str
    graded_at: str
    deterministic_checks: tuple[Mapping[str, object], ...]
    deterministic_schemas: tuple[Mapping[str, object], ...]
    deterministic_results: tuple[AssertionResult, ...]
    judge_execution_binding: HarnessExecutionBinding | None = None
    invocation_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        document: dict[str, object] = {
            "schema_version": "ai-skills.eval.grading-basis.v1",
            "run_id": self.run_id,
            "skill_name": self.skill_name,
            "case_id": self.case_id,
            "run_kind": self.run_kind,
            "judge_response": self.judge_response,
            "judge_control": self.judge_control,
            "judge_prompt_sha256": self.judge_prompt_sha256,
            "allowed_evidence_artifacts": list(
                self.allowed_evidence_artifacts
            ),
            "judge_model": self.judge_model,
            "judge_reasoning_effort": self.judge_reasoning_effort,
            "judge_duration_ms": self.judge_duration_ms,
            "judge_total_tokens": self.judge_total_tokens,
            "judge_prompt_version": self.judge_prompt_version,
            "graded_at": self.graded_at,
            "deterministic_checks": [
                dict(check) for check in self.deterministic_checks
            ],
            "deterministic_schemas": [
                dict(schema) for schema in self.deterministic_schemas
            ],
            "deterministic_results": [
                result.to_dict() for result in self.deterministic_results
            ],
            "judge_execution_binding": (
                self.judge_execution_binding.to_dict()
                if self.judge_execution_binding is not None
                else None
            ),
        }
        if self.invocation_id is not None:
            document["invocation_id"] = self.invocation_id
        return document


@dataclass(frozen=True)
class EvalRunRecord:
    """Human-readable and structured artifacts produced for one run."""

    response: str
    transcript: str
    execution_trace: tuple[Mapping[str, object], ...]
    timing: TimingRecord
    grading: GradingRecord
    grading_basis: GradingBasisRecord | None = None


def digest_run_evidence(
    record: EvalRunRecord,
    *,
    attempt_manifest: bytes,
    actor_output_directories: Sequence[str] = (),
    actor_output_files: Sequence[tuple[str, bytes]] = (),
) -> str:
    """Bind a grade to every preserved input that can support that grade."""
    directories = tuple(
        f"outputs/{path}" for path in actor_output_directories
    )
    files: tuple[tuple[str, bytes], ...] = (
        ("attempt.json", attempt_manifest),
        ("timing.json", _serialize_json_document(record.timing.to_dict()).encode("utf-8")),
        ("outputs/response.md", record.response.encode("utf-8")),
        ("transcript.md", record.transcript.encode("utf-8")),
        (
            "execution_trace.jsonl",
            _serialize_execution_trace(record.execution_trace).encode("utf-8"),
        ),
        *(
            (f"outputs/{path}", content)
            for path, content in actor_output_files
        ),
    )
    if record.grading_basis is not None:
        files = (
            *files,
            (
                "grading_basis.json",
                _serialize_json_document(
                    record.grading_basis.to_dict()
                ).encode("utf-8"),
            ),
        )
    return digest_evidence_bundle(directories, files)


def default_results_root(
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the external durable result root without creating it."""
    environment = os.environ if environ is None else environ
    xdg_state_home = environment.get("XDG_STATE_HOME")
    configured_state_home = Path(xdg_state_home) if xdg_state_home else None
    state_home = (
        configured_state_home
        if configured_state_home is not None and configured_state_home.is_absolute()
        else (home or Path.home()) / ".local/state"
    )
    return state_home / "ai-skills" / "results"


def resolve_external_result_path(
    path: Path,
    *,
    repository_root: Path | None = None,
) -> Path:
    repository = _REPOSITORY_ROOT if repository_root is None else repository_root
    try:
        resolved_repository = repository.resolve(strict=True)
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError("cannot resolve result path") from error
    if resolved_path == resolved_repository or resolved_path.is_relative_to(resolved_repository):
        raise ResultArtifactError(
            f"result path must be outside the repository: {resolved_path}"
        )
    return resolved_path


def create_result_workspace(
    command: str,
    *,
    results_dir: Path | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    now: datetime | None = None,
    repository_root: Path | None = None,
) -> ResultWorkspace:
    """Create one external invocation workspace."""
    invocation_id = uuid.uuid4().hex
    if results_dir is None:
        created_at = now or datetime.now(timezone.utc)
        timestamp = created_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        command_slug = re.sub(r"[^a-z0-9]+", "-", command.lower()).strip("-") or "results"
        unique_suffix = uuid.uuid4().hex[:12]
        root = default_results_root(environ=environ, home=home) / (
            f"{timestamp}-{command_slug}-{unique_suffix}"
        )
    else:
        root = results_dir
    root = resolve_external_result_path(root, repository_root=repository_root)
    repository = _REPOSITORY_ROOT if repository_root is None else repository_root
    try:
        resolved_repository = repository.resolve(strict=True)
        repository_identity = _resolved_repository_identity(
            resolved_repository
        )
        root.mkdir(parents=True, exist_ok=False)
    except FileExistsError as error:
        raise ResultArtifactError(f"result workspace already exists: {root}") from error
    except OSError as error:
        raise ResultArtifactError(f"cannot create result workspace {root}") from error
    attempts = root / "attempts"
    root_descriptor: int | None = None
    attempts_descriptor: int | None = None
    try:
        root_descriptor = os.open(root, _directory_open_flags())
        root_metadata = os.fstat(root_descriptor)
        if not stat.S_ISDIR(root_metadata.st_mode):
            raise ResultArtifactError("result workspace root is not a directory")
        root_identity = _result_directory_identity(root_metadata)
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
        os.mkdir("attempts", mode=0o700, dir_fd=root_descriptor)
        attempts_descriptor = os.open(
            "attempts",
            _directory_open_flags(),
            dir_fd=root_descriptor,
        )
        attempts_metadata = os.fstat(attempts_descriptor)
        if not stat.S_ISDIR(attempts_metadata.st_mode):
            raise ResultArtifactError("result attempts root is not a directory")
        attempts_identity = _result_directory_identity(attempts_metadata)
        _verify_bound_child_directory(
            root_descriptor,
            "attempts",
            attempts_descriptor,
            attempts_identity,
            label="result attempts root",
        )
        _verify_open_result_root_identity(
            root_descriptor,
            root,
            root_identity,
        )
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
    except ResultArtifactError as error:
        raise _retained_workspace_error(root) from error
    except OSError as error:
        raise _retained_workspace_error(root) from error
    finally:
        if attempts_descriptor is not None:
            os.close(attempts_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)
    return ResultWorkspace(
        invocation_id=invocation_id,
        root=root,
        attempts=attempts,
        invocation_manifest=root / "invocation.json",
        benchmark=root / "benchmark.json",
        output_summary=root / "summary.md",
        repository_root=resolved_repository,
        repository_identity=repository_identity,
        root_identity=root_identity,
        attempts_identity=attempts_identity,
    )


def write_result_summary(workspace: ResultWorkspace, text: str) -> None:
    """Atomically persist the invocation's terminal human-readable status."""
    if not text.strip():
        raise ResultArtifactError("result summary must be non-empty")
    _write_text_atomic(
        workspace.output_summary,
        f"{text.rstrip()}\n",
        workspace.root,
        replace_existing=True,
        expected_root_identity=workspace.root_identity,
        repository_identity=workspace.repository_identity,
    )


def declare_invocation(
    workspace: ResultWorkspace,
    command: str,
    manifests: Sequence[AttemptManifest],
) -> None:
    """Persist the exact expected attempt set before external execution."""
    if not command:
        raise ResultArtifactError("invocation command must be non-empty")
    if not manifests:
        raise ResultArtifactError("invocation must declare at least one attempt")
    if len(manifests) > _MAX_DECLARED_ATTEMPTS:
        raise ResultArtifactError("invocation exceeds the declared attempt limit")
    run_ids = [manifest.run_id for manifest in manifests]
    if len(run_ids) != len(set(run_ids)):
        raise ResultArtifactError("invocation attempt run identifiers must be unique")
    document = _invocation_document(workspace.invocation_id, command, manifests)
    validate_result_document(document, "invocation.schema.json")
    serialized = _serialize_json_document(document)
    workspace.invocation_identity = _write_text_once(
        workspace.invocation_manifest,
        serialized,
        workspace.root,
        expected_root_identity=workspace.root_identity,
        repository_identity=workspace.repository_identity,
    )


def verify_declared_invocation(
    workspace: ResultWorkspace,
    command: str,
    manifests: Sequence[AttemptManifest],
) -> None:
    """Require the exact declaration inode and bytes pinned before preflight."""
    expected = _serialize_json_document(
        _invocation_document(workspace.invocation_id, command, manifests)
    ).encode("utf-8")
    observed = _read_pinned_invocation(workspace)
    if observed.content != expected:
        raise ResultArtifactError(
            "invocation declaration does not match the prepared execution plan"
        )


def preflight_bound_invocations(
    adapter: HarnessAdapter,
    declarations: Sequence[
        tuple[ResultWorkspace, str, Sequence[AttemptManifest]]
    ],
    *,
    require_fixtures: bool,
) -> BoundPreflightReceipt:
    """Run one preflight bracketed by exact invocation identity checks."""
    if not declarations:
        raise ResultArtifactError(
            "preflight requires at least one declared invocation"
        )
    before: list[_StableFileRead] = []
    for workspace, command, manifests in declarations:
        verify_declared_invocation(workspace, command, manifests)
        before.append(_read_pinned_invocation(workspace))
    capabilities = adapter.preflight(require_fixtures=require_fixtures)
    bindings: list[PreflightInvocationBinding] = []
    for (workspace, command, manifests), prior in zip(
        declarations,
        before,
        strict=True,
    ):
        verify_declared_invocation(workspace, command, manifests)
        observed = _read_pinned_invocation(workspace)
        if (
            observed.metadata != prior.metadata
            or hashlib.sha256(observed.content).digest()
            != hashlib.sha256(prior.content).digest()
        ):
            raise ResultArtifactError(
                "invocation declaration changed during runtime preflight"
            )
        bindings.append(
            PreflightInvocationBinding(
                workspace_root=workspace.root.absolute(),
                command=command,
                metadata=observed.metadata,
                digest=hashlib.sha256(observed.content).digest(),
            )
        )
    return BoundPreflightReceipt(
        adapter=adapter,
        capabilities=capabilities,
        require_fixtures=require_fixtures,
        bindings=tuple(bindings),
    )


def capabilities_from_preflight_receipt(
    receipt: BoundPreflightReceipt,
    adapter: HarnessAdapter,
    workspace: ResultWorkspace,
    command: str,
    manifests: Sequence[AttemptManifest],
    *,
    require_fixtures: bool,
) -> HarnessCapabilities:
    """Verify one invocation is covered by an exact bound preflight receipt."""
    if receipt.adapter is not adapter:
        raise ResultArtifactError(
            "preflight receipt belongs to a different harness adapter"
        )
    if require_fixtures and not receipt.require_fixtures:
        raise ResultArtifactError(
            "preflight receipt does not cover required fixture capabilities"
        )
    verify_declared_invocation(workspace, command, manifests)
    observed = _read_pinned_invocation(workspace)
    expected_digest = hashlib.sha256(observed.content).digest()
    matches = tuple(
        binding
        for binding in receipt.bindings
        if (
            binding.workspace_root == workspace.root.absolute()
            and binding.command == command
            and binding.metadata == observed.metadata
            and binding.digest == expected_digest
        )
    )
    if len(matches) != 1:
        raise ResultArtifactError(
            "preflight receipt is not bound to the selected invocation"
        )
    return receipt.capabilities


def _invocation_document(
    invocation_id: str,
    command: str,
    manifests: Sequence[AttemptManifest],
) -> dict[str, object]:
    document = {
        "schema_version": "ai-skills.eval.invocation.v1",
        "invocation_id": invocation_id,
        "command": command,
        "attempts": [
            _bound_attempt_document(manifest, invocation_id)
            for manifest in manifests
        ],
    }
    _require_behavior_attempt_identity(document["attempts"])
    _require_consistent_group_scenario_bindings(document["attempts"])
    _require_shared_behavior_judge_controls(document["attempts"])
    return document


def _require_behavior_attempt_identity(
    attempts: Sequence[Mapping[str, object]],
) -> None:
    for attempt in attempts:
        if attempt["run_kind"] == "trigger":
            continue
        aggregation = attempt["aggregation"]
        if not isinstance(aggregation, Mapping):
            raise ResultArtifactError(
                "behavior attempt aggregation metadata must be an object"
            )
        if attempt["run_kind"] != aggregation["variant"]:
            raise ResultArtifactError(
                "behavior attempt run kind must match its aggregation variant"
            )


def _require_consistent_group_scenario_bindings(
    attempts: Sequence[Mapping[str, object]],
) -> None:
    signatures_by_group: dict[str, set[str]] = defaultdict(set)
    for attempt in attempts:
        aggregation = attempt["aggregation"]
        if not isinstance(aggregation, Mapping):
            raise ResultArtifactError(
                "attempt aggregation metadata must be an object"
            )
        group_id = aggregation["group_id"]
        if not isinstance(group_id, str):
            raise ResultArtifactError("attempt aggregation group id must be a string")
        signature: dict[str, object] = {
            "skill_name": attempt["skill_name"],
            "case_id": attempt["case_id"],
            "scenario_definition_sha256": attempt[
                "scenario_definition_sha256"
            ],
            "assertion_contract": attempt["assertion_contract"],
        }
        if attempt["run_kind"] == "trigger":
            signature.update(
                {
                    "runtime_input_sha256": attempt["runtime_input_sha256"],
                    "expected_activation": attempt["expected_activation"],
                    "expected_skill_catalog_path": attempt[
                        "expected_skill_catalog_path"
                    ],
                    "aggregation": {
                        key: value
                        for key, value in aggregation.items()
                        if key != "run_number"
                    },
                }
            )
        else:
            signature["deterministic_input_sha256"] = attempt[
                "deterministic_input_sha256"
            ]
        signatures_by_group[group_id].add(
            canonical_document_sha256(signature)
        )
    for group_id, signatures in signatures_by_group.items():
        if len(signatures) != 1:
            raise ResultArtifactError(
                f"aggregation group {group_id!r} mixes scenario definitions "
                "or immutable contracts"
            )


def _require_shared_behavior_judge_controls(
    attempts: Sequence[Mapping[str, object]],
) -> None:
    controls_by_group: dict[str, set[str]] = defaultdict(set)
    for attempt in attempts:
        if attempt["run_kind"] == "trigger":
            continue
        aggregation = attempt["aggregation"]
        if not isinstance(aggregation, Mapping):
            raise ResultArtifactError(
                "behavior attempt aggregation metadata must be an object"
            )
        group_id = aggregation["group_id"]
        judge_control_sha256 = attempt["judge_control_sha256"]
        if not isinstance(group_id, str) or not isinstance(
            judge_control_sha256,
            str,
        ):
            raise ResultArtifactError(
                "behavior attempt judge control binding is invalid"
            )
        controls_by_group[group_id].add(judge_control_sha256)
    for group_id, controls in controls_by_group.items():
        if len(controls) != 1:
            raise ResultArtifactError(
                f"behavior aggregation group {group_id!r} must share one "
                "judge control"
            )


def _bound_attempt_document(
    manifest: AttemptManifest,
    invocation_id: str,
) -> dict[str, object]:
    document = manifest.to_dict()
    document["invocation_id"] = invocation_id
    return document


def _read_pinned_invocation(workspace: ResultWorkspace) -> _StableFileRead:
    root_descriptor: int | None = None
    try:
        root_descriptor, _ = _open_result_root(
            workspace.root,
            workspace.root,
        )
        if _result_directory_identity(os.fstat(root_descriptor)) != workspace.root_identity:
            raise ResultArtifactError(
                "result workspace root was replaced after creation"
            )
        _verify_result_root_outside_repository(
            root_descriptor,
            workspace.repository_identity,
        )
        result = _read_pinned_invocation_at(workspace, root_descriptor)
        _verify_open_result_root_identity(
            root_descriptor,
            workspace.root,
            workspace.root_identity,
        )
        _verify_result_root_outside_repository(
            root_descriptor,
            workspace.repository_identity,
        )
        return result
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "invocation declaration cannot be verified safely"
        ) from error
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)


def _read_pinned_invocation_at(
    workspace: ResultWorkspace,
    root_descriptor: int,
) -> _StableFileRead:
    expected = workspace.invocation_identity
    if expected is None:
        raise ResultArtifactError("invocation declaration identity was not pinned")
    try:
        observed = os.stat(
            workspace.invocation_manifest.name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
    except OSError as error:
        raise ResultArtifactError(
            "invocation declaration was replaced after it was pinned"
        ) from error
    if (
        not stat.S_ISREG(observed.st_mode)
        or _stable_result_metadata(observed) != expected.metadata
    ):
        raise ResultArtifactError(
            "invocation declaration was replaced after it was pinned"
        )
    result = _read_stable_file_at(
        root_descriptor,
        workspace.invocation_manifest.name,
        observed,
        maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        label="invocation declaration",
        limit_name="JSON byte limit",
    )
    if (
        result.metadata != expected.metadata
        or hashlib.sha256(result.content).digest() != expected.digest
    ):
        raise ResultArtifactError(
            "invocation declaration changed after it was pinned"
        )
    return result


def create_attempt_workspace(
    workspace: ResultWorkspace,
    manifest: AttemptManifest,
) -> AttemptPaths:
    """Declare one attempt durably before any external execution."""
    document = _bound_attempt_document(manifest, workspace.invocation_id)
    validate_result_document(document, _attempt_artifact_schema("manifest"))
    if manifest.aggregation.variant not in manifest.aggregation.required_variants:
        raise ResultArtifactError(
            "attempt aggregation variant must be one of its required variants"
        )
    invocation_identity = workspace.invocation_identity
    if invocation_identity is None:
        raise ResultArtifactError(
            "results directory must contain one regular invocation.json: "
            f"{workspace.root}"
        )
    run_slug = re.sub(r"[^a-z0-9]+", "-", manifest.run_id.lower()).strip("-") or "attempt"
    directory_name = f"{run_slug}-{uuid.uuid4().hex[:12]}"
    root = workspace.attempts / directory_name
    manifest_content = _serialize_json_document(document).encode("utf-8")
    root_descriptor: int | None = None
    attempts_descriptor: int | None = None
    attempt_descriptor: int | None = None
    child_descriptors: list[int] = []
    directory_identities: dict[tuple[str, ...], tuple[int, int, int]] = {}
    try:
        root_descriptor, _ = _open_result_root(workspace.root, workspace.root)
        if _result_directory_identity(os.fstat(root_descriptor)) != workspace.root_identity:
            raise ResultArtifactError(
                "result workspace root was replaced after creation"
            )
        _verify_result_root_outside_repository(
            root_descriptor,
            workspace.repository_identity,
        )
        pinned_invocation = _parse_result_document(
            _read_pinned_invocation_at(workspace, root_descriptor).content,
            workspace.invocation_manifest,
            "invocation.schema.json",
        )
        declared_attempts = _declared_attempts(pinned_invocation)
        if declared_attempts.get(manifest.run_id) != document:
            raise ResultArtifactError(
                "attempt does not match the immutable invocation manifest"
            )
        attempts_descriptor = _open_bound_child_directory(
            root_descriptor,
            "attempts",
            workspace.attempts_identity,
            label="invocation attempts directory",
        )
        os.mkdir(directory_name, mode=0o700, dir_fd=attempts_descriptor)
        attempt_descriptor = os.open(
            directory_name,
            _directory_open_flags(),
            dir_fd=attempts_descriptor,
        )
        attempt_identity = _result_directory_identity(os.fstat(attempt_descriptor))
        _verify_bound_child_directory(
            attempts_descriptor,
            directory_name,
            attempt_descriptor,
            attempt_identity,
            label="attempt workspace",
        )
        output_directories = sorted(
            {
                artifact.relative_parts[:-1]
                for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
                if len(artifact.relative_parts) > 1
            },
            key=lambda parts: (len(parts), parts),
        )
        opened_by_parts: dict[tuple[str, ...], int] = {(): attempt_descriptor}
        for relative in output_directories:
            parent_parts = relative[:-1]
            parent_descriptor = opened_by_parts[parent_parts]
            name = relative[-1]
            os.mkdir(name, mode=0o700, dir_fd=parent_descriptor)
            child_descriptor = os.open(
                name,
                _directory_open_flags(),
                dir_fd=parent_descriptor,
            )
            child_descriptors.append(child_descriptor)
            identity = _result_directory_identity(os.fstat(child_descriptor))
            _verify_bound_child_directory(
                parent_descriptor,
                name,
                child_descriptor,
                identity,
                label="attempt artifact directory",
            )
            opened_by_parts[relative] = child_descriptor
            directory_identities[relative] = identity
        _write_atomic_result_file_at(
            attempt_descriptor,
            "attempt.json",
            manifest_content,
            expected_metadata=None,
            maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        )
        os.fsync(attempt_descriptor)
        _read_pinned_invocation_at(workspace, root_descriptor)
        for relative in reversed(output_directories):
            parent_descriptor = opened_by_parts[relative[:-1]]
            _verify_bound_child_directory(
                parent_descriptor,
                relative[-1],
                opened_by_parts[relative],
                directory_identities[relative],
                label="attempt artifact directory",
            )
        _verify_bound_child_directory(
            attempts_descriptor,
            directory_name,
            attempt_descriptor,
            attempt_identity,
            label="attempt workspace",
        )
        _verify_bound_child_directory(
            root_descriptor,
            "attempts",
            attempts_descriptor,
            workspace.attempts_identity,
            label="invocation attempts directory",
        )
        _verify_open_result_root_identity(
            root_descriptor,
            workspace.root,
            workspace.root_identity,
        )
        _verify_result_root_outside_repository(
            root_descriptor,
            workspace.repository_identity,
        )
    except FileExistsError as error:
        raise ResultArtifactError(f"attempt workspace already exists: {root}") from error
    except ResultArtifactError:
        raise
    except OSError as error:
        raise ResultArtifactError(f"cannot create attempt workspace {root}") from error
    finally:
        for descriptor in reversed(child_descriptors):
            os.close(descriptor)
        if attempt_descriptor is not None:
            os.close(attempt_descriptor)
        if attempts_descriptor is not None:
            os.close(attempts_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)
    return _attempt_paths(
        root,
        invocation_id=workspace.invocation_id,
        workspace_root=workspace.root,
        repository_identity=workspace.repository_identity,
        workspace_identity=workspace.root_identity,
        attempts_identity=workspace.attempts_identity,
        attempt_identity=attempt_identity,
        invocation_identity=invocation_identity,
        directory_identities=directory_identities,
    )


def record_harness_timing(
    *,
    invocation_id: str,
    run_id: str,
    skill_name: str,
    case_id: str,
    run_kind: str,
    harness_name: str,
    started_at: datetime,
    ended_at: datetime,
    execution: HarnessExecution,
) -> TimingRecord:
    """Build required timing evidence directly from normalized harness execution."""
    binding = execution.execution_binding
    binding_matches_attempt = bool(
        binding is not None
        and binding.invocation_id == invocation_id
        and binding.run_id == run_id
        and binding.role == "actor"
    )
    status = (
        "timeout"
        if execution.timed_out
        else "failed"
        if (
            execution.failure is not None
            or execution.exit_code != 0
            or execution.model is None
            or execution.reasoning_effort is None
            or not binding_matches_attempt
        )
        else "completed"
    )
    return TimingRecord(
        invocation_id=invocation_id,
        run_id=run_id,
        skill_name=skill_name,
        case_id=case_id,
        run_kind=run_kind,
        harness=harness_name,
        model=execution.model,
        reasoning_effort=execution.reasoning_effort,
        started_at=_format_timestamp(started_at),
        ended_at=_format_timestamp(ended_at),
        duration_ms=execution.duration_ms,
        total_tokens=execution.total_tokens,
        status=status,
        exit_code=execution.exit_code,
        token_details={
            "input": execution.input_tokens,
            "output": execution.output_tokens,
            "cached": execution.cached_tokens,
            "source": execution.token_source,
        },
        execution_binding=execution.execution_binding,
        successful_skill_reads=execution.successful_skill_reads,
        expected_skill_path=execution.expected_skill_path,
    )


def enforce_execution_binding(
    execution: HarnessExecution,
    request: HarnessRequest,
) -> HarnessExecution:
    """Quarantine an adapter result that did not echo this exact request."""
    if execution_binding_matches_request(execution, request):
        return execution
    return replace(
        execution,
        response="",
        trace=(
            {
                "event": "execution_binding_mismatch",
                "role": request.role,
            },
        ),
        total_tokens=None,
        input_tokens=None,
        output_tokens=None,
        cached_tokens=None,
        token_source="unavailable",
        successful_skill_reads=(),
        exit_code=None,
        failure=(
            f"{request.role} HarnessExecution did not return the exact "
            "fresh execution binding"
        ),
        model=None,
        reasoning_effort=None,
        timed_out=False,
        expected_skill_path=None,
        captured_output_paths=(),
        execution_binding=None,
    )


def enforce_execution_configuration(
    execution: HarnessExecution,
    *,
    expected_model: str,
    expected_reasoning_effort: str,
    role: str,
) -> HarnessExecution:
    """Fail when adapter-reported request configuration drifts from preflight."""
    if (
        execution.timed_out
        or execution.failure is not None
        or execution.exit_code != 0
        or execution.model is None
        or execution.reasoning_effort is None
    ):
        return execution
    if (
        execution.model == expected_model
        and execution.reasoning_effort == expected_reasoning_effort
    ):
        return execution
    diagnostic = (
        f"{role} execution model configuration differs from the "
        "preflight-selected configuration"
    )
    return replace(
        execution,
        trace=(
            *execution.trace,
            {
                "event": "execution_configuration_mismatch",
                "role": role,
            },
        ),
        failure="\n".join(
            part for part in (execution.failure, diagnostic) if part
        ),
    )


def validate_result_document(document: Mapping[str, object], schema_name: str) -> None:
    """Validate one result document against a repository-owned offline schema."""
    schema_path = _SCHEMA_ROOT / schema_name
    try:
        schema_bytes = _read_stable_path_file(
            schema_path,
            maximum_bytes=_MAX_OFFLINE_SCHEMA_BYTES,
            label="offline result schema",
        ).content
        schema = _parse_bounded_json(
            schema_bytes,
            label="offline result schema",
            maximum_bytes=_MAX_OFFLINE_SCHEMA_BYTES,
        )
        if not isinstance(schema, dict):
            raise ResultArtifactError("offline result schema must contain a JSON object")
        _validate_bounded_json_structure(
            document,
            label=f"{schema_name} result",
            maximum_scalar_bytes=_result_json_scalar_limit(schema_name),
        )
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    except ValidationError as error:
        keyword = str(error.validator)
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", keyword):
            keyword = "validation"
        raise ResultArtifactError(
            f"invalid {schema_name} result at {_safe_validation_path(error.absolute_path)}: "
            f"{keyword}"
        ) from error
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            f"cannot load or apply offline schema {schema_name}"
        ) from error


def write_eval_run_artifacts(
    paths: AttemptPaths,
    record: EvalRunRecord,
    *,
    actor_output_directories: Sequence[str] = (),
    actor_output_files: Sequence[tuple[str, bytes]] = (),
    completion_guard: Callable[[bool], None] | None = None,
) -> GradingRecord:
    """Write one complete generated run without touching manual review artifacts."""
    _require_declared_attempt_paths(paths)
    _require_missing_grading_completion_marker(paths)
    try:
        bound_record = _bind_run_record_to_invocation(
            record,
            paths.invocation_id,
        )
        attempt_manifest = _read_attempt_artifact(
            paths,
            ("attempt.json",),
            maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
            label="cannot bind evaluation evidence to its attempt declaration",
            limit_name="JSON byte limit",
        ).content
        evidence_sha256 = digest_run_evidence(
            bound_record,
            attempt_manifest=attempt_manifest,
            actor_output_directories=actor_output_directories,
            actor_output_files=actor_output_files,
        )
        if (
            bound_record.grading.evidence_sha256 is not None
            and bound_record.grading.evidence_sha256 != evidence_sha256
        ):
            raise ResultArtifactError(
                "grading does not match the complete preserved evidence"
            )
        bound_record = replace(
            bound_record,
            grading=replace(
                bound_record.grading,
                evidence_sha256=evidence_sha256,
            ),
        )
        timing = bound_record.timing.to_dict()
        grading = bound_record.grading.to_dict()
        validate_result_document(timing, _attempt_artifact_schema("timing"))
        validate_result_document(grading, _attempt_artifact_schema("grading"))
        grading_basis = (
            bound_record.grading_basis.to_dict()
            if bound_record.grading_basis is not None
            else None
        )
        if grading_basis is not None:
            validate_result_document(
                grading_basis,
                _attempt_artifact_schema("grading_basis"),
            )
        _grading_evidence_artifact_parts(grading)

        trace_text = _serialize_execution_trace(bound_record.execution_trace)
        if completion_guard is not None:
            completion_guard(False)
        artifact_values: dict[str, object] = {
            "timing": timing,
            "response": bound_record.response,
            "transcript": bound_record.transcript,
            "execution_trace": trace_text,
            "grading": grading,
        }
        if grading_basis is not None:
            artifact_values["grading_basis"] = grading_basis
        _write_persisted_attempt_artifacts(paths, artifact_values)
        if completion_guard is not None:
            completion_guard(True)
        _verify_persisted_fixed_evidence(paths, bound_record)
    except BaseException as error:
        try:
            _remove_invalid_grading_completion_marker(paths)
        except ResultArtifactError as cleanup_error:
            error.add_note(
                "the grading completion marker could not be removed because "
                f"the attempt path was no longer trustworthy: {cleanup_error}"
            )
        try:
            _clear_incomplete_attempt_outputs(paths)
        except ResultArtifactError as cleanup_error:
            error.add_note(
                "actor outputs could not be quarantined because the attempt "
                f"path was no longer trustworthy: {cleanup_error}"
            )
        raise
    return bound_record.grading


def _require_missing_grading_completion_marker(paths: AttemptPaths) -> None:
    with _open_bound_attempt_artifact_parent(
        paths,
        ("grading.json",),
    ) as (parent_descriptor, name):
        try:
            os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            return
        except OSError as error:
            raise ResultArtifactError(
                "grading completion marker cannot be inspected safely"
            ) from error
    raise ResultArtifactError(f"result artifact already exists: {paths.grading}")


def _bind_run_record_to_invocation(
    record: EvalRunRecord,
    invocation_id: str,
) -> EvalRunRecord:
    timing = _bind_structured_artifact_to_invocation(
        record.timing,
        invocation_id,
        label="timing",
    )
    grading = _bind_structured_artifact_to_invocation(
        record.grading,
        invocation_id,
        label="grading",
    )
    grading_basis = (
        _bind_structured_artifact_to_invocation(
            record.grading_basis,
            invocation_id,
            label="grading basis",
        )
        if record.grading_basis is not None
        else None
    )
    return replace(
        record,
        timing=timing,
        grading=grading,
        grading_basis=grading_basis,
    )


def _bind_structured_artifact_to_invocation(
    artifact: TimingRecord | GradingRecord | GradingBasisRecord,
    invocation_id: str,
    *,
    label: str,
) -> TimingRecord | GradingRecord | GradingBasisRecord:
    if artifact.invocation_id not in (None, invocation_id):
        raise ResultArtifactError(
            f"{label} is bound to a different evaluation invocation"
        )
    return replace(artifact, invocation_id=invocation_id)


def _verify_persisted_fixed_evidence(
    paths: AttemptPaths,
    record: EvalRunRecord,
) -> None:
    expected = (
        (("timing.json",), _serialize_json_document(record.timing.to_dict()).encode("utf-8")),
        (("outputs", "response.md"), record.response.encode("utf-8")),
        (("transcript.md",), record.transcript.encode("utf-8")),
        (
            ("execution_trace.jsonl",),
            _serialize_execution_trace(record.execution_trace).encode("utf-8"),
        ),
    )
    if record.grading_basis is not None:
        expected = (
            *expected,
            (
                ("grading_basis.json",),
                _serialize_json_document(
                    record.grading_basis.to_dict()
                ).encode("utf-8"),
            ),
        )
    for relative_parts, content in expected:
        persisted = _read_attempt_artifact(
            paths,
            relative_parts,
            maximum_bytes=_MAX_RESULT_FILE_BYTES,
            label="cannot verify persisted evaluation evidence",
            limit_name="persisted evidence byte limit",
        )
        if persisted.content != content:
            raise ResultArtifactError(
                "persisted evaluation evidence changed before completion"
            )


def _remove_invalid_grading_completion_marker(paths: AttemptPaths) -> None:
    descriptor: int | None = None
    try:
        with _open_bound_attempt_artifact_parent(
            paths,
            ("grading.json",),
        ) as (parent_descriptor, name):
            try:
                descriptor = os.open(
                    name,
                    _regular_file_open_flags(),
                    dir_fd=parent_descriptor,
                )
            except FileNotFoundError:
                return
            _remove_result_entry_for_descriptor(
                parent_descriptor,
                name,
                descriptor,
                label="invalid grading completion marker",
            )
    except ResultArtifactError:
        raise
    except OSError as error:
        raise ResultArtifactError(
            "cannot remove an invalid grading completion marker"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def write_incomplete_attempt_artifacts(
    paths: AttemptPaths,
    *,
    response: str | None,
    transcript: str | None,
    execution_trace: Sequence[Mapping[str, object]],
    timing: TimingRecord,
) -> None:
    """Preserve available failed-attempt evidence without inventing a grade."""
    _require_declared_attempt_paths(paths)
    _clear_incomplete_attempt_outputs(paths)
    bound_timing = _bind_structured_artifact_to_invocation(
        timing,
        paths.invocation_id,
        label="timing",
    )
    timing_document = bound_timing.to_dict()
    validate_result_document(
        timing_document,
        _attempt_artifact_schema("timing"),
    )
    values: dict[str, object] = {
        "timing": timing_document,
    }
    if response is not None:
        values["response"] = response
    if transcript is not None:
        values["transcript"] = transcript
    _write_persisted_attempt_artifacts(paths, values)
    _write_persisted_attempt_artifacts(
        paths,
        {"execution_trace": _serialize_execution_trace(execution_trace)},
    )


def _clear_incomplete_attempt_outputs(paths: AttemptPaths) -> None:
    """Remove ungraded actor files before an incomplete attempt becomes durable."""
    with _open_bound_attempt_artifact_parent(
        paths,
        ("outputs", "__incomplete_clear__"),
    ) as (outputs_descriptor, _):
        _clear_result_directory_at(outputs_descriptor)
        try:
            os.fsync(outputs_descriptor)
            with os.scandir(outputs_descriptor) as entries:
                if next(entries, None) is not None:
                    raise ResultArtifactError(
                        "incomplete attempt outputs could not be cleared safely"
                    )
        except ResultArtifactError:
            raise
        except (
            OSError,
            MemoryError,
            OverflowError,
            RecursionError,
            RuntimeError,
            SystemError,
        ) as error:
            raise ResultArtifactError(
                "incomplete attempt outputs could not be cleared safely"
            ) from error


def _clear_result_directory_at(directory_descriptor: int) -> None:
    try:
        with os.scandir(directory_descriptor) as entries:
            observed = sorted(
                (
                    entry.name,
                    entry.stat(follow_symlinks=False),
                )
                for entry in entries
            )
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "incomplete attempt outputs could not be cleared safely"
        ) from error

    for name, metadata in observed:
        child_descriptor: int | None = None
        try:
            if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(
                metadata.st_mode
            ):
                child_descriptor = os.open(
                    name,
                    os.O_RDONLY
                    | os.O_DIRECTORY
                    | getattr(os, "O_CLOEXEC", 0)
                    | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=directory_descriptor,
                )
                opened = os.fstat(child_descriptor)
                current = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                expected_identity = _result_directory_identity(metadata)
                if (
                    _result_directory_identity(opened) != expected_identity
                    or _result_directory_identity(current) != expected_identity
                ):
                    raise ResultArtifactError(
                        "incomplete attempt outputs changed during cleanup"
                    )
                _clear_result_directory_at(child_descriptor)
                _verify_bound_child_directory(
                    directory_descriptor,
                    name,
                    child_descriptor,
                    expected_identity,
                    label="incomplete attempt output directory",
                )
                os.close(child_descriptor)
                child_descriptor = None
                os.rmdir(name, dir_fd=directory_descriptor)
            else:
                current = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                if _stable_result_metadata(current) != _stable_result_metadata(
                    metadata
                ):
                    raise ResultArtifactError(
                        "incomplete attempt outputs changed during cleanup"
                    )
                os.unlink(name, dir_fd=directory_descriptor)
        except ResultArtifactError:
            raise
        except (
            OSError,
            MemoryError,
            OverflowError,
            RecursionError,
            RuntimeError,
            SystemError,
        ) as error:
            raise ResultArtifactError(
                "incomplete attempt outputs could not be cleared safely"
            ) from error
        finally:
            if child_descriptor is not None:
                os.close(child_descriptor)


def parse_judge_response(
    response: str,
    context: JudgeGradingContext,
    *,
    model: str | None = None,
    reasoning_effort: str | None = None,
) -> GradingRecord:
    """Parse judge verdicts while retaining caller-owned scope and policy."""
    document = _parse_bounded_json(
        response,
        label="invalid judge response",
        maximum_bytes=_MAX_JUDGE_RESPONSE_BYTES,
    )
    if not isinstance(document, dict):
        raise ResultArtifactError("invalid judge response: expected a JSON object")
    if set(document) != {"assertion_results"}:
        raise ResultArtifactError(
            "invalid judge response: expected only assertion_results"
        )
    raw_results = document["assertion_results"]
    if not isinstance(raw_results, list):
        raise ResultArtifactError(
            "invalid judge response: assertion_results must be an array"
        )
    expected_ids = [definition.id for definition in context.expected_assertions]
    actual_ids = [
        result.get("id") if isinstance(result, dict) else None
        for result in raw_results
    ]
    if actual_ids != expected_ids:
        raise ResultArtifactError(
            "invalid judge response: did not return every expected assertion exactly once"
        )

    verdicts: list[tuple[bool, str, tuple[Mapping[str, str], ...]]] = []
    expected_result_fields = {"id", "passed", "evidence", "evidence_refs"}
    expected_reference_fields = {"artifact", "locator"}
    for result in raw_results:
        if not isinstance(result, dict) or set(result) != expected_result_fields:
            raise ResultArtifactError(
                "invalid judge response: assertion result fields are not allowed"
            )
        if type(result["passed"]) is not bool:
            raise ResultArtifactError(
                "invalid judge response: passed must be a boolean"
            )
        if (
            not isinstance(result["evidence"], str)
            or not result["evidence"]
            or len(result["evidence"]) > _MAX_JUDGE_EVIDENCE_CHARS
        ):
            raise ResultArtifactError(
                "invalid judge response: evidence must be a bounded non-empty string"
            )
        raw_references = result["evidence_refs"]
        if (
            not isinstance(raw_references, list)
            or not raw_references
            or len(raw_references) > _MAX_JUDGE_EVIDENCE_REFS
        ):
            raise ResultArtifactError(
                "invalid judge response: evidence_refs must contain bounded evidence"
            )
        references: list[Mapping[str, str]] = []
        for reference in raw_references:
            if (
                not isinstance(reference, dict)
                or set(reference) != expected_reference_fields
                or any(
                    not isinstance(reference[field], str) or not reference[field]
                    for field in expected_reference_fields
                )
                or len(reference["artifact"]) > _MAX_JUDGE_ARTIFACT_NAME_CHARS
                or len(reference["locator"]) > _MAX_JUDGE_LOCATOR_CHARS
            ):
                raise ResultArtifactError(
                    "invalid judge response: evidence reference is incomplete"
                )
            if reference["artifact"] not in context.allowed_evidence_artifacts:
                raise ResultArtifactError(
                    "invalid judge response: evidence artifact is not allowed"
                )
            references.append(reference)
        verdicts.append((result["passed"], result["evidence"], tuple(references)))

    assertion_results = tuple(
        AssertionResult(
            id=definition.id,
            kind=definition.kind,
            text=definition.text,
            passed=verdict[0],
            checked_by="judge",
            evidence=verdict[1],
            evidence_refs=verdict[2],
        )
        for definition, verdict in zip(
            context.expected_assertions, verdicts, strict=True
        )
    )
    grading = GradingRecord(
        invocation_id=context.invocation_id,
        run_id=context.run_id,
        skill_name=context.skill_name,
        case_id=context.case_id,
        run_kind=context.run_kind,
        grade_source="judge",
        grader=GraderRecord(
            type="llm",
            model=model,
            reasoning_effort=reasoning_effort,
            prompt_version=context.prompt_version,
        ),
        graded_at=context.graded_at,
        assertion_results=assertion_results,
        summary=_summarize_assertions(assertion_results),
        aggregation=context.aggregation,
    )
    validate_result_document(grading.to_dict(), "grading.schema.json")
    return grading


def invoke_judge(
    adapter: HarnessAdapter,
    request: HarnessRequest,
    artifact_dir: Path,
    context: JudgeGradingContext,
) -> JudgeInvocationResult:
    """Invoke one judge request exactly once and parse its trustworthy response."""
    if request.role != "judge":
        raise ValueError("judge invocation requires a request with role='judge'")
    if request.model is None or request.reasoning_effort is None:
        raise ValueError(
            "judge invocation requires the preflight-selected model configuration"
        )
    request = bind_harness_request(
        request,
        invocation_id=context.invocation_id,
        run_id=context.run_id,
    )
    started = time.monotonic()
    try:
        execution = adapter.execute(request, artifact_dir)
    except Exception as error:
        diagnostic = _normalized_judge_diagnostic(
            _safe_exception_text(error),
            fallback="judge adapter raised an exception",
        )
        failed_execution = HarnessExecution(
            response="",
            trace=(
                {
                    "event": "judge_adapter_error",
                    "message": diagnostic,
                },
            ),
            duration_ms=max(0, round((time.monotonic() - started) * 1000)),
            total_tokens=None,
            input_tokens=None,
            output_tokens=None,
            cached_tokens=None,
            token_source="unavailable",
            successful_skill_reads=(),
            exit_code=None,
            failure=diagnostic,
            model=None,
            reasoning_effort=None,
            timed_out=False,
        )
        raise JudgeExecutionError(
            f"judge execution failed: {diagnostic}",
            failed_execution,
        ) from None
    execution = enforce_execution_binding(execution, request)
    execution = enforce_execution_configuration(
        execution,
        expected_model=request.model,
        expected_reasoning_effort=request.reasoning_effort,
        role="judge",
    )
    if execution.failure is not None:
        execution = replace(
            execution,
            failure=_normalized_judge_diagnostic(
                execution.failure,
                fallback="judge harness reported a failure",
            ),
        )
    if execution.timed_out:
        raise JudgeExecutionError("judge execution timed out", execution)
    if execution.failure:
        raise JudgeExecutionError(
            f"judge execution failed: {execution.failure}", execution
        )
    if execution.exit_code != 0:
        raise JudgeExecutionError(
            f"judge execution failed with exit code {execution.exit_code}", execution
        )
    if execution.model is None or execution.reasoning_effort is None:
        raise JudgeExecutionError(
            "judge execution did not report model and reasoning metadata",
            execution,
        )
    if (
        execution.successful_skill_reads
        or execution.expected_skill_path is not None
        or execution.captured_output_paths
    ):
        raise JudgeExecutionError(
            "judge isolation was violated by skill, tool, or actor-output access",
            execution,
        )
    lifecycle_error = _judge_lifecycle_error(execution.trace)
    if lifecycle_error is not None:
        raise JudgeExecutionError(lifecycle_error, execution)
    prepared_response = prepare_durable_sensitive_text(
        execution.response,
        Path("grading_basis.json"),
        maximum_durable_bytes=_MAX_JUDGE_RESPONSE_BYTES,
    )
    if prepared_response.transformed:
        safe_execution = replace(
            execution,
            response=prepared_response.text,
            failure="judge response could not be preserved safely",
        )
        raise JudgeExecutionError(
            "judge response could not be preserved safely",
            safe_execution,
        )
    execution = replace(execution, response=prepared_response.text)
    try:
        grading = parse_judge_response(
            execution.response,
            context,
            model=execution.model,
            reasoning_effort=execution.reasoning_effort,
        )
    except ResultArtifactError as error:
        raise JudgeExecutionError(str(error), execution) from error

    return JudgeInvocationResult(
        grading=grading,
        execution=execution,
    )


def _judge_lifecycle_error(
    trace: Sequence[Mapping[str, object]],
) -> str | None:
    events: list[str] = []
    for item in trace:
        if set(item) != {"event"} or not isinstance(item.get("event"), str):
            return (
                "judge isolation was violated by unexpected skill, tool, shell, "
                "or lifecycle evidence"
            )
        events.append(item["event"])
    accepted = {
        ("judge.completed",),
        (
            "harness_thread_started",
            "harness_turn_started",
            "harness_turn_completed",
        ),
    }
    if tuple(events) not in accepted:
        if events:
            return (
                "judge isolation was violated by unexpected skill, tool, shell, "
                "or lifecycle evidence"
            )
        return "judge execution has no exact successful isolated lifecycle"
    return None


def _safe_exception_text(error: Exception) -> str:
    try:
        detail = str(error)
    except BaseException:
        detail = ""
    return f"{type(error).__name__}: {detail}" if detail else type(error).__name__


def _normalized_judge_diagnostic(value: str, *, fallback: str) -> str:
    prepared = prepare_durable_sensitive_text(
        value,
        Path("judge-runtime-diagnostic"),
        maximum_durable_bytes=_MAX_JUDGE_DIAGNOSTIC_BYTES,
    )
    return prepared.text or fallback


def combine_grading_results(
    judge_grading: GradingRecord,
    deterministic_results: Sequence[AssertionResult],
) -> GradingRecord:
    """Prepend deterministic checks and recompute one complete generated grade."""
    assertion_results = (*deterministic_results, *judge_grading.assertion_results)
    identifiers = [result.id for result in assertion_results]
    if len(identifiers) != len(set(identifiers)):
        raise ResultArtifactError("grading assertion result identifiers must be unique")
    combined = replace(
        judge_grading,
        assertion_results=assertion_results,
        summary=_summarize_assertions(assertion_results),
    )
    validate_result_document(combined.to_dict(), "grading.schema.json")
    return combined


def aggregate_results(
    results_dir: Path,
    grade_source: str,
    *,
    repository_root: Path | None = None,
    terminal_decision: str | None = None,
) -> dict[str, object]:
    """Aggregate only complete attempts anchored by immutable declarations."""
    if grade_source not in ("judge", "manual", "both"):
        raise ResultArtifactError(
            "grade_source must be one of 'judge', 'manual', or 'both'"
        )
    if terminal_decision not in (None, "pass", "expectations failed"):
        raise ResultArtifactError(
            "aggregate terminal decision must be 'pass' or 'expectations failed'"
        )
    repository_identity = _resolved_repository_identity(repository_root)
    root = resolve_external_result_path(
        results_dir,
        repository_root=repository_root,
    )
    root_descriptor, root_metadata = _open_result_root(root, results_dir)
    try:
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
        invocation_read = _read_required_invocation(root_descriptor, root)
        invocation = _parse_result_document(
            invocation_read.content,
            root / "invocation.json",
            "invocation.schema.json",
        )
        declared_attempts = _declared_attempts(invocation)
        _require_behavior_attempt_identity(
            tuple(declared_attempts.values())
        )
        _require_consistent_group_scenario_bindings(
            tuple(declared_attempts.values())
        )
        _require_shared_behavior_judge_controls(
            tuple(declared_attempts.values())
        )
        snapshot = _snapshot_result_tree(
            root_descriptor,
            root,
            declared_attempt_count=len(declared_attempts),
        )
        if snapshot.files.get(("invocation.json",)) != invocation_read.metadata:
            raise ResultArtifactError(
                "result invocation changed during bounded inventory"
            )
        attempt_directories = _validate_result_tree(snapshot, results_dir)

        requested_sources = (
            ("judge", "manual") if grade_source == "both" else (grade_source,)
        )
        preserved: dict[
            str,
            list[tuple[dict[str, object], dict[str, object]]],
        ] = {source: [] for source in requested_sources}
        run_ids: set[str] = set()
        actor_configurations: set[tuple[object, object, object]] = set()
        judge_configurations: set[tuple[object, object]] = set()
        trigger_generated_records: list[
            tuple[dict[str, object], dict[str, object]]
        ] = []
        for directory_name in attempt_directories:
            attempt_parts = ("attempts", directory_name)
            manifest_parts = _attempt_artifact_parts(attempt_parts, "manifest")
            manifest_path = root.joinpath(*manifest_parts)
            manifest = _read_snapshotted_result_document(
                root_descriptor,
                snapshot,
                manifest_parts,
                manifest_path,
                _attempt_artifact_schema("manifest"),
            )
            run_id = manifest["run_id"]
            if run_id in run_ids:
                raise ResultArtifactError(
                    f"duplicate run_id in attempt manifests: {run_id}"
                )
            run_ids.add(run_id)
            if declared_attempts.get(run_id) != manifest:
                raise ResultArtifactError(
                    f"attempt does not match the immutable invocation manifest: {run_id}"
                )
            aggregation = manifest["aggregation"]
            if aggregation["variant"] not in aggregation["required_variants"]:
                raise ResultArtifactError(
                    f"unexpected variant in attempt manifest: {aggregation['variant']}"
                )
            _validate_gradable_attempt_artifacts(
                snapshot,
                attempt_parts,
            )

            timing_parts = _attempt_artifact_parts(attempt_parts, "timing")
            timing_path = root.joinpath(*timing_parts)
            timing = _read_snapshotted_result_document(
                root_descriptor,
                snapshot,
                timing_parts,
                timing_path,
                _attempt_artifact_schema("timing"),
            )
            generated_parts = _attempt_artifact_parts(attempt_parts, "grading")
            generated_path = root.joinpath(*generated_parts)
            generated = _read_snapshotted_result_document(
                root_descriptor,
                snapshot,
                generated_parts,
                generated_path,
                _attempt_artifact_schema("grading"),
            )
            generated_evidence = _validate_grading_semantics(
                generated,
                expected_source="judge",
            )
            _validate_generated_assertion_contract(generated, manifest)
            _validate_snapshotted_grading_evidence(
                generated_evidence,
                snapshot,
                attempt_parts,
            )
            _validate_artifact_matches_manifest(timing, manifest, timing_path)
            _validate_artifact_matches_manifest(generated, manifest, generated_path)
            _validate_persisted_execution_binding(
                timing.get("execution_binding"),
                manifest,
                role="actor",
            )
            _validate_evidence_binding(
                generated,
                root_descriptor,
                snapshot,
                attempt_parts,
            )
            if manifest["run_kind"] == "trigger":
                grading_basis_parts = _attempt_artifact_parts(
                    attempt_parts,
                    "grading_basis",
                )
                if grading_basis_parts in snapshot.files:
                    raise ResultArtifactError(
                        "trigger attempts cannot contain a behavior grading basis"
                    )
                _validate_trigger_grading_semantics(
                    generated,
                    manifest,
                    timing,
                    root_descriptor,
                    snapshot,
                    attempt_parts,
                )
                trigger_generated_records.append((generated, timing))
            else:
                basis_parts = _attempt_artifact_parts(
                    attempt_parts,
                    "grading_basis",
                )
                basis_path = root.joinpath(*basis_parts)
                basis = _read_snapshotted_result_document(
                    root_descriptor,
                    snapshot,
                    basis_parts,
                    basis_path,
                    _attempt_artifact_schema("grading_basis"),
                )
                _validate_artifact_matches_manifest(
                    basis,
                    manifest,
                    basis_path,
                )
                _validate_persisted_execution_binding(
                    basis.get("judge_execution_binding"),
                    manifest,
                    role="judge",
                )
                _validate_without_skill_baseline_evidence(
                    manifest,
                    timing,
                    root_descriptor,
                    snapshot,
                    attempt_parts,
                )
                judge_configurations.add(
                    (
                        basis["judge_model"],
                        basis["judge_reasoning_effort"],
                    )
                )
                _validate_behavior_grading_derivation(
                    generated,
                    manifest,
                    basis,
                    timing,
                    root_descriptor,
                    snapshot,
                    attempt_parts,
                )
            if timing["status"] != "completed":
                raise ResultArtifactError(
                    f"attempt is not trustworthy: timing status is {timing['status']}"
                )
            _validate_completed_timing(timing, timing_path)
            actor_configurations.add(
                (
                    timing["harness"],
                    timing["model"],
                    timing["reasoning_effort"],
                )
            )

            if "judge" in preserved:
                preserved["judge"].append((generated, timing))
            if "manual" in preserved:
                manual_parts = _attempt_artifact_parts(
                    attempt_parts,
                    "manual_grading",
                )
                manual_path = root.joinpath(*manual_parts)
                manual = _read_snapshotted_result_document(
                    root_descriptor,
                    snapshot,
                    manual_parts,
                    manual_path,
                    _attempt_artifact_schema("manual_grading"),
                )
                manual_evidence = _validate_grading_semantics(
                    manual,
                    expected_source="manual",
                )
                _validate_snapshotted_grading_evidence(
                    manual_evidence,
                    snapshot,
                    attempt_parts,
                )
                _validate_artifact_matches_manifest(manual, manifest, manual_path)
                _validate_complete_manual_override(
                    generated,
                    manual,
                    timing,
                    manual_path,
                )
                if manifest["run_kind"] == "trigger":
                    _validate_trigger_grading_semantics(
                        manual,
                        manifest,
                        timing,
                        root_descriptor,
                        snapshot,
                        attempt_parts,
                    )
                preserved["manual"].append((manual, timing))

        if run_ids != set(declared_attempts):
            raise ResultArtifactError(
                "attempt set does not match the immutable invocation manifest"
            )
        if len(actor_configurations) != 1:
            raise ResultArtifactError(
                "evaluation invocation mixes actor model configurations or harnesses"
            )
        if len(judge_configurations) > 1:
            raise ResultArtifactError(
                "evaluation invocation mixes judge model configurations"
            )
        _require_manual_review_for_passing_trigger_disagreements(
            trigger_generated_records,
            grade_source,
        )

        benchmark: dict[str, object] = {
            "schema_version": "ai-skills.eval.benchmark.v1",
            "invocation_id": invocation["invocation_id"],
            "generated_at": _format_timestamp(datetime.now(timezone.utc)),
            "grade_source": grade_source,
            "source_summaries": {
                source: _aggregate_source(records)
                for source, records in preserved.items()
            },
        }
        validate_result_document(benchmark, "benchmark.schema.json")
        benchmark_terminal_decision = (
            "expectations failed" if benchmark_exit_code(benchmark) else "pass"
        )
        if (
            terminal_decision is not None
            and terminal_decision != benchmark_terminal_decision
        ):
            raise ResultArtifactError(
                "aggregate terminal decision contradicts benchmark outcome"
            )
        resolved_terminal_decision = benchmark_terminal_decision
        final_snapshot = _snapshot_result_tree(
            root_descriptor,
            root,
            declared_attempt_count=len(declared_attempts),
        )
        if final_snapshot != snapshot:
            raise ResultArtifactError(
                "result tree changed during bounded aggregation"
            )
        _verify_open_result_root(root_descriptor, root, root_metadata)
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
        _write_aggregate_result_artifacts(
            root_descriptor,
            root,
            root_metadata,
            repository_identity,
            snapshot,
            benchmark,
            terminal_decision=resolved_terminal_decision,
            declared_attempt_count=len(declared_attempts),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result aggregation exceeded bounded resource limits"
        ) from error
    finally:
        try:
            os.close(root_descriptor)
        except OSError as error:
            raise ResultArtifactError(
                "result aggregation could not release its directory handle"
            ) from error
    return benchmark


def benchmark_exit_code(benchmark: Mapping[str, object]) -> int:
    """Return 1 only when a caller-designated contributing result failed."""
    validate_result_document(benchmark, "benchmark.schema.json")
    source_summaries = benchmark["source_summaries"]
    effective_sources = (
        (source_summaries["manual"],)
        if benchmark["grade_source"] == "both"
        else tuple(source_summaries.values())
    )
    return 1 if any(
        source_summary["summary"]["failed_cases"]
        for source_summary in effective_sources
    ) else 0


def format_benchmark_summary(benchmark: Mapping[str, object]) -> str:
    """Render aggregate outcomes and prominently label non-positive deltas."""
    validate_result_document(benchmark, "benchmark.schema.json")
    lines = [f"Aggregate grade source: {benchmark['grade_source']}"]
    for source, source_summary in benchmark["source_summaries"].items():
        summary = source_summary["summary"]
        lines.append(
            f"{source}: {summary['passed_cases']}/{summary['total_cases']} contributing cases passed "
            f"({summary['pass_rate']:.4f})"
        )
        for group in source_summary["groups"]:
            variants = ", ".join(
                f"{name}={details['pass_rate']:.4f}"
                for name, details in group["variants"].items()
            )
            lines.append(f"  {group['group_id']}: {variants}")
            for comparison in group["comparisons"]:
                label = " INVESTIGATE: zero or negative delta" if comparison[
                    "investigation_required"
                ] else ""
                lines.append(
                    f"    {comparison['variant']} - {comparison['baseline_variant']} "
                    f"delta={comparison['pass_rate_delta']:+.4f}{label}"
                )
        for skill in source_summary["skill_summaries"]:
            measurements = ", ".join(
                f"{name}={details['mean']:.4f} (n={details['count']})"
                for name, details in skill["measurements"].items()
            )
            if measurements:
                lines.append(f"  {skill['skill_name']} measurements: {measurements}")
    return "\n".join(lines)


def _aggregate_source(
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    grouped: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    for grading, timing in records:
        grouped[grading["aggregation"]["group_id"]].append((grading, timing))

    groups = [_aggregate_group(group_id, grouped[group_id]) for group_id in sorted(grouped)]
    contributing_outcomes = [
        outcome
        for group_id in sorted(grouped)
        for outcome in _contributing_outcomes(group_id, grouped[group_id])
    ]
    if not contributing_outcomes:
        raise ResultArtifactError("grading source has no contributing outcomes")
    passed_cases = sum(contributing_outcomes)
    total_cases = len(contributing_outcomes)
    return {
        "summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": total_cases - passed_cases,
            "pass_rate": passed_cases / total_cases if total_cases else 0.0,
        },
        "groups": groups,
        "skill_summaries": _aggregate_skill_summaries(grouped),
    }


def _require_manual_review_for_passing_trigger_disagreements(
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
    grade_source: str,
) -> None:
    grouped: dict[
        str,
        list[tuple[dict[str, object], dict[str, object]]],
    ] = defaultdict(list)
    for grading, timing in records:
        grouped[grading["aggregation"]["group_id"]].append((grading, timing))
    for group_id, group_records in grouped.items():
        contributing = [
            grading
            for grading, _ in group_records
            if grading["aggregation"]["contributes_to_outcome"]
        ]
        outcomes = [_grading_passed(grading) for grading in contributing]
        if len(set(outcomes)) <= 1:
            continue
        group_outcomes = _contributing_outcomes(group_id, group_records)
        if group_outcomes == [True] and grade_source == "judge":
            raise ResultArtifactError(
                "passing non-unanimous trigger results require complete "
                "validated manual grading"
            )


def _aggregate_group(
    group_id: str,
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    skill_names = {grading["skill_name"] for grading, _ in records}
    case_ids = {grading["case_id"] for grading, _ in records}
    required_variant_sets = {
        tuple(sorted(grading["aggregation"]["required_variants"]))
        for grading, _ in records
    }
    if len(skill_names) != 1 or len(case_ids) != 1:
        raise ResultArtifactError(f"aggregation group {group_id!r} mixes skills or cases")
    if len(required_variant_sets) != 1:
        raise ResultArtifactError(f"aggregation group {group_id!r} has conflicting required variants")
    actor_configurations = {
        (timing["model"], timing["reasoning_effort"])
        for _, timing in records
    }
    if len(actor_configurations) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} mixes actor model configurations"
        )
    judge_configurations = {
        (
            grading["grader"]["model"],
            grading["grader"]["reasoning_effort"],
        )
        for grading, _ in records
        if grading["grader"]["type"] == "llm"
    }
    if len(judge_configurations) > 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} mixes judge model configurations"
        )

    by_variant: dict[str, list[tuple[dict[str, object], dict[str, object]]]] = defaultdict(list)
    for grading, timing in records:
        by_variant[grading["aggregation"]["variant"]].append((grading, timing))
    required_variants = set(next(iter(required_variant_sets)))
    missing = sorted(required_variants - set(by_variant))
    if missing:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} is missing required variants: {', '.join(missing)}"
        )
    unexpected = sorted(set(by_variant) - required_variants)
    if unexpected:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has unexpected variants: {', '.join(unexpected)}"
        )
    run_counts = {variant: len(variant_records) for variant, variant_records in by_variant.items()}
    if len(set(run_counts.values())) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has unequal repeated-run counts"
        )
    for variant, variant_records in by_variant.items():
        policies = {
            (
                grading["aggregation"]["contributes_to_outcome"],
                grading["aggregation"].get("compare_to"),
                grading["aggregation"].get("minimum_pass_rate"),
                grading["aggregation"].get("configured_runs"),
                grading["run_kind"],
            )
            for grading, _ in variant_records
        }
        if len(policies) != 1:
            raise ResultArtifactError(
                f"aggregation group {group_id!r} has inconsistent metadata for variant {variant!r}"
            )

    variants = {
        variant: _aggregate_variant(by_variant[variant]) for variant in sorted(by_variant)
    }
    comparison_pairs = {
        (grading["aggregation"]["variant"], grading["aggregation"].get("compare_to"))
        for grading, _ in records
        if grading["aggregation"].get("compare_to") is not None
    }
    comparisons: list[dict[str, object]] = []
    for variant, baseline in sorted(comparison_pairs):
        if baseline not in variants:
            raise ResultArtifactError(
                f"aggregation group {group_id!r} comparison baseline is missing: {baseline}"
            )
        delta = variants[variant]["pass_rate"] - variants[baseline]["pass_rate"]
        comparisons.append(
            {
                "variant": variant,
                "baseline_variant": baseline,
                "pass_rate_delta": delta,
                "investigation_required": delta <= 0,
            }
        )
    return {
        "group_id": group_id,
        "skill_name": next(iter(skill_names)),
        "case_id": next(iter(case_ids)),
        "variants": variants,
        "comparisons": comparisons,
    }


def _contributing_outcomes(
    group_id: str,
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> list[bool]:
    contributing = [
        grading
        for grading, _ in records
        if grading["aggregation"]["contributes_to_outcome"]
    ]
    if not contributing:
        return []
    thresholds = {
        grading["aggregation"].get("minimum_pass_rate") for grading in contributing
    }
    if thresholds == {None}:
        return [_grading_passed(grading) for grading in contributing]
    if None in thresholds or len(thresholds) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has inconsistent outcome thresholds"
        )
    variants = {grading["aggregation"]["variant"] for grading in contributing}
    if len(variants) != 1:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} applies one threshold to multiple variants"
        )
    threshold = next(iter(thresholds))
    configured_runs = {
        grading["aggregation"].get("configured_runs") for grading in contributing
    }
    if len(configured_runs) != 1 or None in configured_runs:
        raise ResultArtifactError(
            f"aggregation group {group_id!r} has inconsistent configured run counts"
        )
    configured_run_count = next(iter(configured_runs))
    run_numbers = [grading["aggregation"].get("run_number") for grading in contributing]
    if (
        len(contributing) != configured_run_count
        or len(set(run_numbers)) != configured_run_count
        or set(run_numbers) != set(range(1, configured_run_count + 1))
    ):
        raise ResultArtifactError(
            f"aggregation group {group_id!r} does not contain the complete configured run set"
        )
    pass_rate = sum(_grading_passed(grading) for grading in contributing) / len(contributing)
    return [pass_rate >= threshold]


def _aggregate_skill_summaries(
    grouped: Mapping[str, Sequence[tuple[dict[str, object], dict[str, object]]]],
) -> list[dict[str, object]]:
    by_skill: dict[str, list[tuple[str, Sequence[tuple[dict[str, object], dict[str, object]]]]]] = defaultdict(list)
    for group_id, records in grouped.items():
        skill_names = {grading["skill_name"] for grading, _ in records}
        if len(skill_names) != 1:
            raise ResultArtifactError(f"aggregation group {group_id!r} mixes skills")
        by_skill[next(iter(skill_names))].append((group_id, records))

    summaries: list[dict[str, object]] = []
    for skill_name in sorted(by_skill):
        outcomes: list[bool] = []
        measurements: dict[str, list[float]] = defaultdict(list)
        for group_id, records in by_skill[skill_name]:
            outcomes.extend(_contributing_outcomes(group_id, records))
            for grading, _ in records:
                for name, value in grading.get("measurements", {}).items():
                    measurements[name].append(value)
        summaries.append(
            {
                "skill_name": skill_name,
                "total_outcomes": len(outcomes),
                "passed_outcomes": sum(outcomes),
                "failed_outcomes": len(outcomes) - sum(outcomes),
                "pass_rate": sum(outcomes) / len(outcomes) if outcomes else 0.0,
                "measurements": {
                    name: {
                        "count": len(values),
                        "total": sum(values),
                        "mean": sum(values) / len(values),
                    }
                    for name, values in sorted(measurements.items())
                },
            }
        )
    return summaries


def _aggregate_variant(
    records: Sequence[tuple[dict[str, object], dict[str, object]]],
) -> dict[str, object]:
    passed = sum(_grading_passed(grading) for grading, _ in records)
    token_counts = [timing["total_tokens"] for _, timing in records]
    return {
        "runs": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "pass_rate": passed / len(records),
        "duration_ms_total": sum(timing["duration_ms"] for _, timing in records),
        "total_tokens": None if any(value is None for value in token_counts) else sum(token_counts),
    }


def _grading_passed(grading: Mapping[str, object]) -> bool:
    return grading["summary"]["failed"] == 0


def _parse_bounded_json(
    value: str | bytes,
    *,
    label: str,
    maximum_bytes: int | None = None,
    maximum_nodes: int | None = None,
    maximum_depth: int | None = None,
    maximum_scalar_bytes: int | None = None,
) -> object:
    maximum_bytes = (
        _MAX_RESULT_JSON_FILE_BYTES if maximum_bytes is None else maximum_bytes
    )
    maximum_nodes = _MAX_RESULT_JSON_NODES if maximum_nodes is None else maximum_nodes
    maximum_depth = _MAX_RESULT_JSON_DEPTH if maximum_depth is None else maximum_depth
    maximum_scalar_bytes = (
        _MAX_RESULT_JSON_SCALAR_BYTES
        if maximum_scalar_bytes is None
        else maximum_scalar_bytes
    )
    if min(
        maximum_bytes,
        maximum_nodes,
        maximum_depth,
        maximum_scalar_bytes,
    ) < 1:
        raise ResultArtifactError(f"{label} has invalid JSON boundary limits")
    if not isinstance(value, (str, bytes)):
        raise ResultArtifactError(f"{label} is not bounded JSON text")
    try:
        if isinstance(value, bytes):
            encoded_size = len(value)
            text = value.decode("utf-8")
        else:
            encoded_size = len(value.encode("utf-8"))
            text = value
    except (MemoryError, UnicodeError) as error:
        raise ResultArtifactError(f"{label} is not bounded UTF-8 JSON") from error
    if encoded_size > maximum_bytes:
        raise ResultArtifactError(f"{label} exceeds the JSON byte limit")
    try:
        preflight_bounded_json_structure(
            text,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
            maximum_scalar_bytes=maximum_scalar_bytes,
            maximum_number_characters=_MAX_RESULT_JSON_NUMBER_CHARS,
        )
    except JsonPreflightError as error:
        if error.kind == "depth":
            raise ResultArtifactError(f"{label} exceeds the JSON depth limit") from error
        if error.kind == "nodes":
            raise ResultArtifactError(f"{label} exceeds the JSON node limit") from error
        if error.kind == "scalar":
            raise ResultArtifactError(f"{label} exceeds the JSON scalar limit") from error
        if error.kind == "nonfinite":
            raise ResultArtifactError(
                f"{label} contains a non-finite JSON number"
            ) from error
        raise ResultArtifactError(f"{label} is invalid bounded JSON") from error

    def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, item in pairs:
            if key in document:
                raise _JsonBoundaryError("contains a duplicate JSON key")
            document[key] = item
        return document

    def bounded_integer(token: str) -> int:
        if len(token) > _MAX_RESULT_JSON_NUMBER_CHARS:
            raise _JsonBoundaryError("exceeds the JSON scalar limit")
        return int(token)

    def bounded_float(token: str) -> float:
        if len(token) > _MAX_RESULT_JSON_NUMBER_CHARS:
            raise _JsonBoundaryError("exceeds the JSON scalar limit")
        result = float(token)
        if not math.isfinite(result):
            raise _JsonBoundaryError("contains a non-finite JSON number")
        return result

    def reject_constant(_: str) -> object:
        raise _JsonBoundaryError("contains a non-finite JSON number")

    try:
        document = json.loads(
            text,
            object_pairs_hook=unique_object,
            parse_int=bounded_integer,
            parse_float=bounded_float,
            parse_constant=reject_constant,
        )
    except _JsonBoundaryError as error:
        raise ResultArtifactError(f"{label} {error}") from error
    except (
        json.JSONDecodeError,
        MemoryError,
        OverflowError,
        RecursionError,
        UnicodeError,
        ValueError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} is invalid bounded JSON") from error
    _validate_bounded_json_structure(
        document,
        label=label,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
    )
    return document


def _validate_bounded_json_structure(
    document: object,
    *,
    label: str,
    maximum_nodes: int | None = None,
    maximum_depth: int | None = None,
    maximum_scalar_bytes: int | None = None,
) -> None:
    maximum_nodes = _MAX_RESULT_JSON_NODES if maximum_nodes is None else maximum_nodes
    maximum_depth = _MAX_RESULT_JSON_DEPTH if maximum_depth is None else maximum_depth
    maximum_scalar_bytes = (
        _MAX_RESULT_JSON_SCALAR_BYTES
        if maximum_scalar_bytes is None
        else maximum_scalar_bytes
    )
    pending: list[tuple[object, int]] = [(document, 1)]
    nodes = 0
    try:
        while pending:
            item, depth = pending.pop()
            if depth > maximum_depth:
                raise ResultArtifactError(f"{label} exceeds the JSON depth limit")
            nodes += 1
            if nodes > maximum_nodes:
                raise ResultArtifactError(f"{label} exceeds the JSON node limit")
            if isinstance(item, Mapping):
                if len(item) > maximum_nodes - nodes:
                    raise ResultArtifactError(f"{label} exceeds the JSON node limit")
                for key, child in item.items():
                    nodes += 1
                    if nodes > maximum_nodes:
                        raise ResultArtifactError(f"{label} exceeds the JSON node limit")
                    _validate_json_scalar(
                        key,
                        label=label,
                        maximum_scalar_bytes=maximum_scalar_bytes,
                    )
                    pending.append((child, depth + 1))
            elif isinstance(item, list):
                if len(item) > maximum_nodes - nodes:
                    raise ResultArtifactError(f"{label} exceeds the JSON node limit")
                pending.extend((child, depth + 1) for child in item)
            else:
                _validate_json_scalar(
                    item,
                    label=label,
                    maximum_scalar_bytes=maximum_scalar_bytes,
                )
    except ResultArtifactError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            f"{label} exceeds bounded JSON structure limits"
        ) from error


def _validate_json_scalar(
    value: object,
    *,
    label: str,
    maximum_scalar_bytes: int,
) -> None:
    if isinstance(value, str):
        if len(value.encode("utf-8")) > maximum_scalar_bytes:
            raise ResultArtifactError(f"{label} exceeds the JSON scalar limit")
        return
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if value.bit_length() > _MAX_RESULT_JSON_NUMBER_CHARS * 4:
            raise ResultArtifactError(f"{label} exceeds the JSON scalar limit")
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ResultArtifactError(f"{label} contains a non-finite JSON number")
        return
    raise ResultArtifactError(f"{label} contains a non-JSON scalar")


def _parse_result_document(
    content: bytes,
    path: Path,
    schema_name: str,
) -> dict[str, object]:
    document = _parse_bounded_json(
        content,
        label=f"cannot read trustworthy result {path}:",
        maximum_scalar_bytes=_result_json_scalar_limit(schema_name),
    )
    if not isinstance(document, dict):
        raise ResultArtifactError(f"result artifact must contain a JSON object: {path}")
    if schema_name == "invocation.schema.json":
        attempts = document.get("attempts")
        if isinstance(attempts, list) and len(attempts) > _MAX_DECLARED_ATTEMPTS:
            raise ResultArtifactError("invocation exceeds the declared attempt limit")
    validate_result_document(document, schema_name)
    return document


def _result_json_scalar_limit(schema_name: str) -> int:
    if schema_name == "grading-basis.schema.json":
        return MAX_JUDGE_PROMPT_BYTES
    return _MAX_RESULT_JSON_SCALAR_BYTES


def _declared_attempts(
    invocation: Mapping[str, object],
) -> dict[str, dict[str, object]]:
    try:
        invocation_id = invocation["invocation_id"]
        attempts = invocation["attempts"]
        if len(attempts) > _MAX_DECLARED_ATTEMPTS:
            raise ResultArtifactError("invocation exceeds the declared attempt limit")
        declared_attempts: dict[str, dict[str, object]] = {}
        for attempt in attempts:
            if attempt["invocation_id"] != invocation_id:
                raise ResultArtifactError(
                    "attempt declaration is bound to a different evaluation invocation"
                )
            run_id = attempt["run_id"]
            if run_id in declared_attempts:
                raise ResultArtifactError(
                    f"duplicate run_id in invocation manifest: {run_id}"
                )
            declared_attempts[run_id] = attempt
        return declared_attempts
    except ResultArtifactError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "invocation declaration exceeds bounded resource limits"
        ) from error


def _read_stable_path_file(
    path: Path,
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str = "byte limit",
) -> _StableFileRead:
    parent_descriptor: int | None = None
    try:
        parent_descriptor = os.open(path.parent, _directory_open_flags())
        observed = os.stat(
            path.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise ResultArtifactError(
                f"{label} must be a regular non-symlink file"
            )
        return _read_stable_file_at(
            parent_descriptor,
            path.name,
            observed,
            maximum_bytes=maximum_bytes,
            label=label,
            limit_name=limit_name,
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} cannot be read safely") from error
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _read_stable_file_at(
    directory_descriptor: int,
    name: str,
    expected_metadata: os.stat_result,
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str,
) -> _StableFileRead:
    if expected_metadata.st_size < 0 or expected_metadata.st_size > maximum_bytes:
        raise ResultArtifactError(f"{label} exceeds the {limit_name}")
    file_descriptor: int | None = None
    try:
        file_descriptor = os.open(
            name,
            _regular_file_open_flags(),
            dir_fd=directory_descriptor,
        )
        opened = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _stable_result_metadata(expected_metadata)
            != _stable_result_metadata(opened)
        ):
            raise ResultArtifactError(f"{label} changed while being read")
        if opened.st_size < 0 or opened.st_size > maximum_bytes:
            raise ResultArtifactError(f"{label} exceeds the {limit_name}")

        remaining = opened.st_size
        content = bytearray()
        while remaining:
            chunk = os.read(
                file_descriptor,
                min(_RESULT_READ_CHUNK_BYTES, remaining),
            )
            if not chunk:
                raise ResultArtifactError(f"{label} changed while being read")
            content.extend(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise ResultArtifactError(f"{label} changed while being read")

        final = os.fstat(file_descriptor)
        current = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_result_metadata(opened) != _stable_result_metadata(final)
            or _stable_result_metadata(final) != _stable_result_metadata(current)
        ):
            raise ResultArtifactError(f"{label} changed while being read")
        return _StableFileRead(
            content=bytes(content),
            metadata=_stable_result_metadata(final),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} changed while being read") from error
    finally:
        if file_descriptor is not None:
            os.close(file_descriptor)


def _open_result_root(root: Path, requested_root: Path) -> tuple[int, tuple[int, ...]]:
    try:
        observed = os.stat(root, follow_symlinks=False)
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError(
            f"results directory does not exist: {requested_root}"
        ) from error
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
        raise ResultArtifactError(
            f"results directory must be a regular non-symlink directory: {requested_root}"
        )
    descriptor: int | None = None
    try:
        descriptor = os.open(root, _directory_open_flags())
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _stable_result_metadata(observed)
            != _stable_result_metadata(opened)
        ):
            raise ResultArtifactError(
                "results directory changed while opening bounded aggregation"
            )
        return descriptor, _stable_result_metadata(opened)
    except ResultArtifactError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ResultArtifactError(
            "results directory cannot be opened for bounded aggregation"
        ) from error


def _resolved_repository_identity(
    repository_root: Path | None,
) -> tuple[int, int]:
    repository = _REPOSITORY_ROOT if repository_root is None else repository_root
    try:
        resolved = repository.resolve(strict=True)
        metadata = os.stat(resolved, follow_symlinks=False)
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError("cannot resolve result path") from error
    if not stat.S_ISDIR(metadata.st_mode):
        raise ResultArtifactError("cannot resolve result path")
    return metadata.st_dev, metadata.st_ino


def _verify_result_root_outside_repository(
    root_descriptor: int,
    repository_identity: tuple[int, int],
) -> None:
    current_descriptor: int | None = None
    try:
        current_descriptor = os.dup(root_descriptor)
        for _ in range(_MAX_RESULT_ANCESTOR_DEPTH):
            current = os.fstat(current_descriptor)
            current_identity = (current.st_dev, current.st_ino)
            if current_identity == repository_identity:
                raise ResultArtifactError(
                    "result path must be outside the repository"
                )
            parent_descriptor = os.open(
                "..",
                _directory_open_flags(),
                dir_fd=current_descriptor,
            )
            parent = os.fstat(parent_descriptor)
            parent_identity = (parent.st_dev, parent.st_ino)
            if parent_identity == current_identity:
                os.close(parent_descriptor)
                return
            os.close(current_descriptor)
            current_descriptor = parent_descriptor
        raise ResultArtifactError(
            "result path ancestry exceeds the verification depth limit"
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result path ancestry cannot be verified safely"
        ) from error
    finally:
        if current_descriptor is not None:
            os.close(current_descriptor)


def _verify_open_result_root(
    descriptor: int,
    root: Path,
    expected_metadata: tuple[int, ...],
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(root, follow_symlinks=False)
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "results directory changed during bounded aggregation"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or expected_metadata != _stable_result_metadata(opened)
        or expected_metadata != _stable_result_metadata(current)
    ):
        raise ResultArtifactError(
            "results directory changed during bounded aggregation"
        )


def _write_aggregate_result_artifacts(
    root_descriptor: int,
    root: Path,
    root_metadata: tuple[int, ...],
    repository_identity: tuple[int, int],
    snapshot: _ResultTreeSnapshot,
    benchmark: Mapping[str, object],
    *,
    terminal_decision: str,
    declared_attempt_count: int,
) -> None:
    try:
        payloads = (
            (
                "benchmark.json",
                f"{json.dumps(benchmark, indent=2, sort_keys=True)}\n".encode("utf-8"),
                _MAX_RESULT_JSON_FILE_BYTES,
            ),
            (
                "summary.md",
                (
                    "# Evaluation Aggregate\n\n"
                    f"Decision: {terminal_decision}\n\n"
                    "## Results\n\n"
                    f"{format_benchmark_summary(benchmark)}\n"
                ).encode("utf-8"),
                _MAX_RESULT_FILE_BYTES,
            ),
        )
    except ResultArtifactError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            "cannot serialize aggregate result artifacts within resource limits"
        ) from error

    replaced_bytes = sum(
        snapshot.files.get((name,), (0, 0, 0, 0, 0))[4]
        for name, _, _ in payloads
    )
    payload_bytes = sum(len(content) for _, content, _ in payloads)
    if any(len(content) > limit for _, content, limit in payloads):
        raise ResultArtifactError(
            "aggregate result artifacts exceed the per-file byte limit"
        )
    if snapshot.total_bytes - replaced_bytes + payload_bytes > _MAX_RESULT_TREE_BYTES:
        raise ResultArtifactError(
            "aggregate result artifacts exceed the cumulative byte limit"
        )
    current_entries = len(snapshot.files) + len(snapshot.directories) - 1
    added_entries = sum(
        (name,) not in snapshot.files for name, _, _ in payloads
    )
    if (
        current_entries + added_entries
        > _result_tree_entry_limit(declared_attempt_count)
    ):
        raise ResultArtifactError(
            "aggregate result artifacts exceed the entry-count limit"
        )

    original_content: dict[str, bytes | None] = {}
    for name, _, maximum_bytes in payloads:
        if (name,) not in snapshot.files:
            original_content[name] = None
            continue
        original_content[name] = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            (name,),
            maximum_bytes=maximum_bytes,
            label="aggregate result target",
            limit_name="byte limit",
        ).content

    written_metadata: dict[tuple[str, ...], tuple[int, ...]] = {}
    attempted_names: list[str] = []
    try:
        for name, content, maximum_bytes in payloads:
            attempted_names.append(name)
            written_metadata[(name,)] = _write_atomic_result_file_at(
                root_descriptor,
                name,
                content,
                expected_metadata=snapshot.files.get((name,)),
                maximum_bytes=maximum_bytes,
            )
            _verify_open_result_root_identity(
                root_descriptor,
                root,
                root_metadata,
            )
            _verify_result_root_outside_repository(
                root_descriptor,
                repository_identity,
            )
        try:
            os.fsync(root_descriptor)
        except OSError as error:
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            ) from error

        post_write = _snapshot_result_tree(
            root_descriptor,
            root,
            declared_attempt_count=declared_attempt_count,
        )
        expected_files = dict(snapshot.files)
        expected_files.update(written_metadata)
        if post_write.files != expected_files:
            raise ResultArtifactError(
                "result tree changed while writing aggregate artifacts"
            )
        if set(post_write.directories) != set(snapshot.directories) or any(
            post_write.directories[relative] != metadata
            for relative, metadata in snapshot.directories.items()
            if relative
        ):
            raise ResultArtifactError(
                "result tree changed while writing aggregate artifacts"
            )
        _verify_open_result_root_identity(
            root_descriptor,
            root,
            root_metadata,
        )
        _verify_result_root_outside_repository(
            root_descriptor,
            repository_identity,
        )
    except BaseException as error:
        try:
            _rollback_aggregate_result_artifacts(
                root_descriptor,
                payloads,
                original_content,
                attempted_names,
            )
        except BaseException as rollback_error:
            if not isinstance(rollback_error, Exception):
                raise
            raise ResultArtifactError(
                "cannot rollback aggregate result artifacts"
            ) from rollback_error
        if not isinstance(error, Exception):
            raise
        if isinstance(error, ResultArtifactError):
            raise
        if isinstance(
            error,
            (OSError, MemoryError, OverflowError, RuntimeError, SystemError),
        ):
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            ) from error
        raise


def _rollback_aggregate_result_artifacts(
    root_descriptor: int,
    payloads: Sequence[tuple[str, bytes, int]],
    original_content: Mapping[str, bytes | None],
    attempted_names: Sequence[str],
) -> None:
    payload_by_name = {
        name: (content, maximum_bytes)
        for name, content, maximum_bytes in payloads
    }
    for name in reversed(attempted_names):
        replacement, maximum_bytes = payload_by_name[name]
        _restore_aggregate_result_artifact(
            root_descriptor,
            name,
            replacement=replacement,
            original=original_content[name],
            maximum_bytes=maximum_bytes,
        )
    try:
        os.fsync(root_descriptor)
    except OSError as error:
        raise ResultArtifactError(
            "cannot rollback aggregate result artifacts"
        ) from error


def _restore_aggregate_result_artifact(
    root_descriptor: int,
    name: str,
    *,
    replacement: bytes,
    original: bytes | None,
    maximum_bytes: int,
) -> None:
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(
                name,
                _regular_file_open_flags(),
                dir_fd=root_descriptor,
            )
        except FileNotFoundError:
            return
        current = _fingerprint_result_descriptor(
            descriptor,
            maximum_bytes=maximum_bytes,
            label="aggregate result target during rollback",
        )
        original_digest = (
            None if original is None else hashlib.sha256(original).digest()
        )
        replacement_digest = hashlib.sha256(replacement).digest()
        if original_digest is not None and current.digest == original_digest:
            return
        if current.digest != replacement_digest:
            return
        if original is None:
            _remove_result_entry_for_descriptor(
                root_descriptor,
                name,
                descriptor,
                label="aggregate result target during rollback",
                expected_identity=current,
                maximum_bytes=maximum_bytes,
            )
            return
        expected_metadata = current.metadata
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as error:
                raise ResultArtifactError(
                    "cannot release aggregate result handles"
                ) from error
    _write_atomic_result_file_at(
        root_descriptor,
        name,
        original,
        expected_metadata=expected_metadata,
        maximum_bytes=maximum_bytes,
    )


def _write_atomic_result_file_at(
    root_descriptor: int,
    name: str,
    content: bytes,
    *,
    expected_metadata: tuple[int, ...] | None,
    maximum_bytes: int,
) -> tuple[int, ...]:
    existing_descriptor: int | None = None
    descriptor: int | None = None
    temporary_name = f".{name}.{uuid.uuid4().hex}.tmp"
    temporary_present = False
    result_metadata: tuple[int, ...] | None = None
    try:
        try:
            current = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            if expected_metadata is not None:
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )
        except OSError as error:
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            ) from error
        else:
            if (
                expected_metadata is None
                or not stat.S_ISREG(current.st_mode)
                or _stable_result_metadata(current) != expected_metadata
            ):
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )
            existing_descriptor = os.open(
                name,
                _regular_file_open_flags(),
                dir_fd=root_descriptor,
            )
            opened_existing = os.fstat(existing_descriptor)
            current_existing = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened_existing.st_mode)
                or _stable_result_metadata(opened_existing) != expected_metadata
                or _stable_result_metadata(current_existing) != expected_metadata
            ):
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )

        descriptor = os.open(
            temporary_name,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=root_descriptor,
        )
        temporary_present = True
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written < 1:
                raise ResultArtifactError(
                    "cannot write aggregate result artifacts"
                )
            remaining = remaining[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o600)
        staged = os.fstat(descriptor)
        if not stat.S_ISREG(staged.st_mode) or staged.st_size != len(content):
            raise ResultArtifactError(
                "cannot write aggregate result artifacts"
            )
        if expected_metadata is None:
            try:
                os.link(
                    temporary_name,
                    name,
                    src_dir_fd=root_descriptor,
                    dst_dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            except FileExistsError as error:
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                ) from error
            linked = os.fstat(descriptor)
            installed = os.stat(
                name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(installed.st_mode)
                or _stable_result_metadata(linked)
                != _stable_result_metadata(installed)
            ):
                raise ResultArtifactError(
                    "aggregate result target changed while writing"
                )
            _remove_result_entry_for_descriptor(
                root_descriptor,
                temporary_name,
                descriptor,
                label="aggregate temporary artifact",
            )
            temporary_present = False
        else:
            if existing_descriptor is None:
                raise ResultArtifactError(
                    "aggregate result target changed before writing"
                )
            _replace_existing_result_entry_at(
                root_descriptor,
                temporary_name,
                name,
                staged_descriptor=descriptor,
                existing_descriptor=existing_descriptor,
                expected_metadata=expected_metadata,
                maximum_bytes=maximum_bytes,
            )
            temporary_present = False
        final = os.fstat(descriptor)
        installed = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(installed.st_mode)
            or _stable_result_metadata(final)
            != _stable_result_metadata(installed)
        ):
            raise ResultArtifactError(
                "aggregate result target changed while writing"
            )
        result_metadata = _stable_result_metadata(final)
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "cannot write aggregate result artifacts"
        ) from error
    finally:
        cleanup_error: ResultArtifactError | None = None
        if temporary_present and descriptor is not None:
            try:
                _remove_result_entry_for_descriptor(
                    root_descriptor,
                    temporary_name,
                    descriptor,
                    label="aggregate temporary artifact",
                )
            except ResultArtifactError as error:
                cleanup_error = error
        for open_descriptor in (existing_descriptor, descriptor):
            if open_descriptor is None:
                continue
            try:
                os.close(open_descriptor)
            except OSError as error:
                if cleanup_error is None:
                    cleanup_error = ResultArtifactError(
                        "cannot release aggregate result handles"
                    )
                    cleanup_error.__cause__ = error
        if cleanup_error is not None:
            raise cleanup_error
    if result_metadata is None:
        raise ResultArtifactError("cannot write aggregate result artifacts")
    return result_metadata


def _remove_result_entry_for_descriptor(
    root_descriptor: int,
    name: str,
    open_descriptor: int,
    *,
    label: str,
    expected_identity: _StableContentIdentity | None = None,
    maximum_bytes: int | None = None,
) -> None:
    try:
        if expected_identity is None:
            opened_metadata = _stable_result_metadata(
                os.fstat(open_descriptor)
            )
        else:
            if maximum_bytes is None:
                raise ResultArtifactError(f"{label} has no fingerprint byte limit")
            current_identity = _fingerprint_result_descriptor(
                open_descriptor,
                maximum_bytes=maximum_bytes,
                expected_metadata=expected_identity.metadata,
                label=label,
            )
            if current_identity != expected_identity:
                raise ResultArtifactError(f"{label} changed during cleanup")
            opened_metadata = current_identity.metadata
        current = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(opened_metadata[2])
            or _stable_result_metadata(current)
            != opened_metadata
        ):
            raise ResultArtifactError(f"{label} changed during cleanup")
        os.unlink(name, dir_fd=root_descriptor)
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} changed during cleanup") from error


def _fingerprint_result_descriptor(
    descriptor: int,
    *,
    maximum_bytes: int,
    label: str,
    expected_metadata: tuple[int, ...] | None = None,
) -> _StableContentIdentity:
    try:
        positioned_read = getattr(os, "pread", None)
        if positioned_read is None or maximum_bytes < 0:
            raise ResultArtifactError(f"{label} cannot be fingerprinted safely")
        opened = os.fstat(descriptor)
        opened_metadata = _stable_result_metadata(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_size < 0
            or opened.st_size > maximum_bytes
            or (
                expected_metadata is not None
                and opened_metadata != expected_metadata
            )
        ):
            raise ResultArtifactError(f"{label} changed while fingerprinting")

        digest = hashlib.sha256()
        offset = 0
        while offset < opened.st_size:
            chunk = positioned_read(
                descriptor,
                min(_RESULT_READ_CHUNK_BYTES, opened.st_size - offset),
                offset,
            )
            if not chunk:
                raise ResultArtifactError(f"{label} changed while fingerprinting")
            digest.update(chunk)
            offset += len(chunk)
        if positioned_read(descriptor, 1, offset):
            raise ResultArtifactError(f"{label} changed while fingerprinting")

        final_metadata = _stable_result_metadata(os.fstat(descriptor))
        if (
            final_metadata != opened_metadata
            or (
                expected_metadata is not None
                and final_metadata != expected_metadata
            )
        ):
            raise ResultArtifactError(f"{label} changed while fingerprinting")
        return _StableContentIdentity(
            metadata=final_metadata,
            digest=digest.digest(),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
        TypeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(f"{label} changed while fingerprinting") from error


def _replace_existing_result_entry_at(
    root_descriptor: int,
    temporary_name: str,
    name: str,
    *,
    staged_descriptor: int,
    existing_descriptor: int,
    expected_metadata: tuple[int, ...],
    maximum_bytes: int,
) -> None:
    exchanged = False
    rollback_descriptor: int | None = None
    try:
        expected_identity = _fingerprint_result_descriptor(
            existing_descriptor,
            maximum_bytes=maximum_bytes,
            expected_metadata=expected_metadata,
            label="aggregate result target",
        )
        current_before_exchange = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if _stable_result_metadata(current_before_exchange) != expected_metadata:
            raise ResultArtifactError(
                "aggregate result target changed before writing"
            )
        _atomic_exchange_result_entries(
            root_descriptor,
            temporary_name,
            name,
        )
        exchanged = True
        staged = os.fstat(staged_descriptor)
        installed = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        retained_identity = _fingerprint_result_descriptor(
            existing_descriptor,
            maximum_bytes=maximum_bytes,
            label="aggregate result target",
        )
        retained = os.stat(
            temporary_name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISREG(installed.st_mode)
            or not stat.S_ISREG(retained.st_mode)
            or _stable_result_metadata(installed)
            != _stable_result_metadata(staged)
            or _stable_result_metadata(retained)
            != retained_identity.metadata
            or retained_identity.metadata[:-1]
            != expected_identity.metadata[:-1]
            or retained_identity.digest != expected_identity.digest
        ):
            raise ResultArtifactError(
                "aggregate result target changed while writing"
            )
        _remove_result_entry_for_descriptor(
            root_descriptor,
            temporary_name,
            existing_descriptor,
            label="aggregate result target",
            expected_identity=retained_identity,
            maximum_bytes=maximum_bytes,
        )
        exchanged = False
    except (
        ResultArtifactError,
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        if exchanged:
            try:
                rollback_descriptor = os.open(
                    temporary_name,
                    _regular_file_open_flags(),
                    dir_fd=root_descriptor,
                )
                rollback_identity = _fingerprint_result_descriptor(
                    rollback_descriptor,
                    maximum_bytes=maximum_bytes,
                    label="aggregate retained result target",
                )
                current_installed = os.stat(
                    name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                current_retained = os.stat(
                    temporary_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                staged = os.fstat(staged_descriptor)
                if (
                    _stable_result_metadata(current_installed)
                    != _stable_result_metadata(staged)
                    or _stable_result_metadata(current_retained)
                    != rollback_identity.metadata
                ):
                    raise ResultArtifactError(
                        "aggregate result target changed during rollback"
                    )
                _atomic_exchange_result_entries(
                    root_descriptor,
                    temporary_name,
                    name,
                )
                restored_target = os.stat(
                    name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                restored_temporary = os.stat(
                    temporary_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
                staged = os.fstat(staged_descriptor)
                restored_retained = os.fstat(rollback_descriptor)
                if (
                    _stable_result_metadata(restored_target)
                    != _stable_result_metadata(restored_retained)
                    or _stable_result_metadata(restored_temporary)
                    != _stable_result_metadata(staged)
                ):
                    raise ResultArtifactError(
                        "aggregate result target changed during rollback"
                    )
                exchanged = False
            except ResultArtifactError as rollback_error:
                raise ResultArtifactError(
                    "aggregate result target changed during rollback"
                ) from rollback_error
        if isinstance(error, ResultArtifactError):
            raise error
        raise ResultArtifactError(
            "cannot atomically replace aggregate result target"
        ) from error
    finally:
        if rollback_descriptor is not None:
            try:
                os.close(rollback_descriptor)
            except OSError as error:
                raise ResultArtifactError(
                    "cannot release aggregate result handles"
                ) from error


def _atomic_exchange_result_entries(
    root_descriptor: int,
    first_name: str,
    second_name: str,
) -> None:
    try:
        library = ctypes.CDLL(None, use_errno=True)
        if hasattr(library, "renameatx_np"):
            exchange = library.renameatx_np
        elif hasattr(library, "renameat2"):
            exchange = library.renameat2
        else:
            raise ResultArtifactError(
                "atomic aggregate replacement is unsupported"
            )
        exchange.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        exchange.restype = ctypes.c_int
        result = exchange(
            root_descriptor,
            os.fsencode(first_name),
            root_descriptor,
            os.fsencode(second_name),
            0x00000002,
        )
        if result != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, "atomic aggregate replacement failed")
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
        TypeError,
        ValueError,
    ) as error:
        raise ResultArtifactError(
            "cannot atomically replace aggregate result target"
        ) from error


def _verify_open_result_root_identity(
    descriptor: int,
    root: Path,
    expected_metadata: tuple[int, ...],
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(root, follow_symlinks=False)
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "results directory changed while writing aggregate artifacts"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _stable_result_metadata(opened)[:3] != expected_metadata[:3]
        or _stable_result_metadata(current)[:3] != expected_metadata[:3]
    ):
        raise ResultArtifactError(
            "results directory changed while writing aggregate artifacts"
        )


def _read_required_invocation(
    root_descriptor: int,
    root: Path,
) -> _StableFileRead:
    try:
        observed = os.stat(
            "invocation.json",
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
    except (OSError, MemoryError, OverflowError, RuntimeError) as error:
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {root}"
        ) from error
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {root}"
        )
    return _read_stable_file_at(
        root_descriptor,
        "invocation.json",
        observed,
        maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        label=f"cannot read trustworthy result {root / 'invocation.json'}",
        limit_name="JSON byte limit",
    )


def _snapshot_result_tree(
    root_descriptor: int,
    root: Path,
    *,
    declared_attempt_count: int,
) -> _ResultTreeSnapshot:
    maximum_entries = _result_tree_entry_limit(declared_attempt_count)
    if maximum_entries < 1:
        raise ResultArtifactError("result tree has an invalid entry-count limit")
    try:
        initial_root = os.fstat(root_descriptor)
        if not stat.S_ISDIR(initial_root.st_mode):
            raise ResultArtifactError(
                "results directory changed during bounded inventory"
            )
        files: dict[tuple[str, ...], tuple[int, ...]] = {}
        directories: dict[tuple[str, ...], tuple[int, ...]] = {
            (): _stable_result_metadata(initial_root)
        }
        state = _ResultTreeScanState()
        _scan_result_directory(
            root_descriptor,
            (),
            files,
            directories,
            state,
            maximum_entries=maximum_entries,
            maximum_attempt_entries=declared_attempt_count + 1,
        )
        final_root = os.fstat(root_descriptor)
        current_root = os.stat(root, follow_symlinks=False)
        if (
            _stable_result_metadata(initial_root)
            != _stable_result_metadata(final_root)
            or _stable_result_metadata(final_root)
            != _stable_result_metadata(current_root)
        ):
            raise ResultArtifactError(
                "result tree changed during bounded inventory"
            )
        return _ResultTreeSnapshot(
            files=files,
            directories=directories,
            total_bytes=state.total_bytes,
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result tree cannot be inventoried within resource limits"
        ) from error


def _result_tree_entry_limit(declared_attempt_count: int) -> int:
    return min(
        _MAX_RESULT_TREE_ENTRIES,
        _MAX_RESULT_ROOT_ENTRIES
        + declared_attempt_count * _MAX_RESULT_ENTRIES_PER_ATTEMPT,
    )


def _scan_result_directory(
    directory_descriptor: int,
    parent_parts: tuple[str, ...],
    files: dict[tuple[str, ...], tuple[int, ...]],
    directories: dict[tuple[str, ...], tuple[int, ...]],
    state: _ResultTreeScanState,
    *,
    maximum_entries: int,
    maximum_attempt_entries: int,
) -> None:
    inspected: list[tuple[str, os.stat_result]] = []
    try:
        with os.scandir(directory_descriptor) as entries:
            for entry in entries:
                state.entries += 1
                if state.entries > maximum_entries:
                    raise ResultArtifactError(
                        "result tree exceeds the entry-count limit"
                    )
                if (
                    parent_parts == ("attempts",)
                    and len(inspected) >= maximum_attempt_entries
                ):
                    raise ResultArtifactError(
                        "attempt inventory exceeds the declared attempt count bound "
                        "for the immutable invocation manifest"
                    )
                inspected.append(
                    (entry.name, entry.stat(follow_symlinks=False))
                )
        inspected.sort(key=lambda item: item[0])
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result tree cannot inspect an entry within resource limits"
        ) from error

    for name, expected in inspected:
        relative = (*parent_parts, name)
        if len(relative) > _MAX_RESULT_TREE_DEPTH:
            raise ResultArtifactError(
                "result tree exceeds the directory depth limit"
            )
        if stat.S_ISLNK(expected.st_mode):
            raise ResultArtifactError(
                "attempt entry or result artifact must not be a symlink"
            )
        if stat.S_ISDIR(expected.st_mode):
            _scan_result_child_directory(
                directory_descriptor,
                name,
                expected,
                relative,
                files,
                directories,
                state,
                maximum_entries=maximum_entries,
                maximum_attempt_entries=maximum_attempt_entries,
            )
            continue
        if not stat.S_ISREG(expected.st_mode):
            raise ResultArtifactError("result tree contains a special file")
        if expected.st_size < 0 or expected.st_size > _MAX_RESULT_FILE_BYTES:
            raise ResultArtifactError(
                "result tree exceeds the per-file byte limit"
            )
        if state.total_bytes + expected.st_size > _MAX_RESULT_TREE_BYTES:
            raise ResultArtifactError(
                "result tree exceeds the cumulative byte limit"
            )
        state.total_bytes += expected.st_size
        files[relative] = _stable_result_metadata(expected)


def _scan_result_child_directory(
    parent_descriptor: int,
    name: str,
    expected: os.stat_result,
    relative: tuple[str, ...],
    files: dict[tuple[str, ...], tuple[int, ...]],
    directories: dict[tuple[str, ...], tuple[int, ...]],
    state: _ResultTreeScanState,
    *,
    maximum_entries: int,
    maximum_attempt_entries: int,
) -> None:
    child_descriptor: int | None = None
    try:
        child_descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(child_descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _stable_result_metadata(expected)
            != _stable_result_metadata(opened)
        ):
            raise ResultArtifactError(
                "result tree changed during bounded inventory"
            )
        directories[relative] = _stable_result_metadata(opened)
        _scan_result_directory(
            child_descriptor,
            relative,
            files,
            directories,
            state,
            maximum_entries=maximum_entries,
            maximum_attempt_entries=maximum_attempt_entries,
        )
        final = os.fstat(child_descriptor)
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_result_metadata(opened) != _stable_result_metadata(final)
            or _stable_result_metadata(final) != _stable_result_metadata(current)
        ):
            raise ResultArtifactError(
                "result tree changed during bounded inventory"
            )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "result tree changed during bounded inventory"
        ) from error
    finally:
        if child_descriptor is not None:
            os.close(child_descriptor)


def _validate_result_tree(
    snapshot: _ResultTreeSnapshot,
    results_dir: Path,
) -> tuple[str, ...]:
    root_files = {
        relative[0] for relative in snapshot.files if len(relative) == 1
    }
    root_directories = {
        relative[0]
        for relative in snapshot.directories
        if len(relative) == 1
    }
    if root_directories != {"attempts"}:
        if "attempts" not in root_directories:
            raise ResultArtifactError(
                f"results directory has no attempts: {results_dir}"
            )
        raise ResultArtifactError("result tree contains an undeclared result entry")
    if "invocation.json" not in root_files:
        raise ResultArtifactError(
            f"results directory must contain one regular invocation.json: {results_dir}"
        )
    if not root_files.issubset(_ROOT_RESULT_FILES):
        raise ResultArtifactError("result tree contains an undeclared result entry")

    direct_attempt_files = [
        relative
        for relative in snapshot.files
        if len(relative) == 2 and relative[0] == "attempts"
    ]
    if direct_attempt_files:
        raise ResultArtifactError("attempt entry must be a directory")
    attempt_directories = tuple(
        sorted(
            relative[1]
            for relative in snapshot.directories
            if len(relative) == 2 and relative[0] == "attempts"
        )
    )
    if not attempt_directories:
        raise ResultArtifactError(
            f"no attempt.json declarations found under {results_dir}"
        )

    for directory_name in attempt_directories:
        attempt_prefix = ("attempts", directory_name)
        direct_files = {
            relative[-1]
            for relative in snapshot.files
            if relative[:-1] == attempt_prefix
        }
        direct_directories = {
            relative[-1]
            for relative in snapshot.directories
            if relative[:-1] == attempt_prefix
        }
        manifest_artifact = _ATTEMPT_ARTIFACT_BY_ATTRIBUTE["manifest"]
        if (*attempt_prefix, *manifest_artifact.relative_parts) not in snapshot.files:
            raise ResultArtifactError(
                "attempt entry must contain required persisted artifact "
                f"{'/'.join(manifest_artifact.relative_parts)}"
            )
        allowed_direct_files = {
            artifact.relative_parts[0]
            for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
            if len(artifact.relative_parts) == 1
        }
        if not direct_files.issubset(allowed_direct_files):
            raise ResultArtifactError(
                "result tree contains an undeclared result entry"
            )
        required_directories = {
            artifact.relative_parts[0]
            for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
            if len(artifact.relative_parts) > 1
        }
        if direct_directories != required_directories:
            raise ResultArtifactError(
                "attempt entry must contain only its outputs directory"
            )
    return attempt_directories


def _validate_gradable_attempt_artifacts(
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> None:
    for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT:
        if not artifact.required_for_gradable_attempt:
            continue
        persisted_path = (*attempt_parts, *artifact.relative_parts)
        if persisted_path not in snapshot.files:
            raise ResultArtifactError(
                "attempt entry must contain required persisted artifact "
                f"{'/'.join(artifact.relative_parts)}"
            )


def _read_snapshotted_result_document(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    relative: tuple[str, ...],
    path: Path,
    schema_name: str,
) -> dict[str, object]:
    read = _read_snapshotted_file(
        root_descriptor,
        snapshot,
        relative,
        maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
        label=f"cannot read trustworthy result {path}",
        limit_name="JSON byte limit",
    )
    return _parse_result_document(read.content, path, schema_name)


def _read_snapshotted_file(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    relative: tuple[str, ...],
    *,
    maximum_bytes: int,
    label: str,
    limit_name: str,
) -> _StableFileRead:
    expected_file = snapshot.files.get(relative)
    if expected_file is None:
        raise ResultArtifactError(f"{label} is missing from the bounded inventory")

    def descend(directory_descriptor: int, index: int) -> _StableFileRead:
        name = relative[index]
        if index == len(relative) - 1:
            try:
                observed = os.stat(
                    name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
            except (
                OSError,
                MemoryError,
                OverflowError,
                RuntimeError,
                SystemError,
            ) as error:
                raise ResultArtifactError(f"{label} changed while being read") from error
            if (
                not stat.S_ISREG(observed.st_mode)
                or _stable_result_metadata(observed) != expected_file
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            result = _read_stable_file_at(
                directory_descriptor,
                name,
                observed,
                maximum_bytes=maximum_bytes,
                label=label,
                limit_name=limit_name,
            )
            if result.metadata != expected_file:
                raise ResultArtifactError(f"{label} changed while being read")
            return result

        prefix = relative[: index + 1]
        expected_directory = snapshot.directories.get(prefix)
        if expected_directory is None:
            raise ResultArtifactError(f"{label} changed while being read")
        child_descriptor: int | None = None
        try:
            observed = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISDIR(observed.st_mode)
                or _stable_result_metadata(observed) != expected_directory
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            child_descriptor = os.open(
                name,
                _directory_open_flags(),
                dir_fd=directory_descriptor,
            )
            opened = os.fstat(child_descriptor)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _stable_result_metadata(opened) != expected_directory
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            result = descend(child_descriptor, index + 1)
            final = os.fstat(child_descriptor)
            current = os.stat(
                name,
                dir_fd=directory_descriptor,
                follow_symlinks=False,
            )
            if (
                _stable_result_metadata(final) != expected_directory
                or _stable_result_metadata(current) != expected_directory
            ):
                raise ResultArtifactError(f"{label} changed while being read")
            return result
        except ResultArtifactError:
            raise
        except (
            OSError,
            MemoryError,
            OverflowError,
            RecursionError,
            RuntimeError,
            SystemError,
        ) as error:
            raise ResultArtifactError(f"{label} changed while being read") from error
        finally:
            if child_descriptor is not None:
                os.close(child_descriptor)

    return descend(root_descriptor, 0)


def _stable_result_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _result_directory_identity(metadata: os.stat_result) -> tuple[int, int, int]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode)


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _regular_file_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _open_bound_child_directory(
    parent_descriptor: int,
    name: str,
    expected_identity: tuple[int, int, int],
    *,
    label: str,
) -> int:
    descriptor: int | None = None
    try:
        observed = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(observed.st_mode)
            or _result_directory_identity(observed) != expected_identity
        ):
            raise ResultArtifactError(f"{label} was replaced")
        descriptor = os.open(
            name,
            _directory_open_flags(),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _result_directory_identity(opened) != expected_identity
        ):
            raise ResultArtifactError(f"{label} was replaced")
        return descriptor
    except ResultArtifactError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        if descriptor is not None:
            os.close(descriptor)
        raise ResultArtifactError(f"{label} cannot be opened safely") from error


def _verify_bound_child_directory(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    expected_identity: tuple[int, int, int],
    *,
    label: str,
) -> None:
    try:
        opened = os.fstat(descriptor)
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except (
        OSError,
        MemoryError,
        OverflowError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"{label} changed during access") from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or _result_directory_identity(opened) != expected_identity
        or _result_directory_identity(current) != expected_identity
    ):
        raise ResultArtifactError(f"{label} changed during access")


@contextmanager
def _open_bound_attempt(
    paths: AttemptPaths,
):
    expected_root = paths.workspace_root / "attempts" / paths.root.name
    if (
        paths.root != expected_root
        or paths.root.parent.name != "attempts"
        or not paths.root.name
    ):
        raise ResultArtifactError(
            "attempt artifact paths are not owned by their invocation"
        )
    root_descriptor: int | None = None
    attempts_descriptor: int | None = None
    attempt_descriptor: int | None = None
    try:
        root_descriptor, _ = _open_result_root(
            paths.workspace_root,
            paths.workspace_root,
        )
        if (
            _result_directory_identity(os.fstat(root_descriptor))
            != paths.workspace_identity
        ):
            raise ResultArtifactError("result workspace root was replaced")
        _verify_result_root_outside_repository(
            root_descriptor,
            paths.repository_identity,
        )
        attempts_descriptor = _open_bound_child_directory(
            root_descriptor,
            "attempts",
            paths.attempts_identity,
            label="invocation attempts directory",
        )
        attempt_descriptor = _open_bound_child_directory(
            attempts_descriptor,
            paths.root.name,
            paths.attempt_identity,
            label="attempt workspace",
        )
        yield root_descriptor, attempts_descriptor, attempt_descriptor
        _verify_bound_child_directory(
            attempts_descriptor,
            paths.root.name,
            attempt_descriptor,
            paths.attempt_identity,
            label="attempt workspace",
        )
        _verify_bound_child_directory(
            root_descriptor,
            "attempts",
            attempts_descriptor,
            paths.attempts_identity,
            label="invocation attempts directory",
        )
        _verify_open_result_root_identity(
            root_descriptor,
            paths.workspace_root,
            paths.workspace_identity,
        )
        _verify_result_root_outside_repository(
            root_descriptor,
            paths.repository_identity,
        )
    finally:
        if attempt_descriptor is not None:
            os.close(attempt_descriptor)
        if attempts_descriptor is not None:
            os.close(attempts_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


@contextmanager
def _open_bound_attempt_artifact_parent(
    paths: AttemptPaths,
    relative_parts: tuple[str, ...],
):
    if (
        not relative_parts
        or any(part in ("", ".", "..") for part in relative_parts)
    ):
        raise ResultArtifactError("attempt artifact path is invalid")
    opened_descriptors: list[
        tuple[int, str, int, tuple[int, int, int], str]
    ] = []
    with _open_bound_attempt(paths) as descriptors:
        parent_descriptor = descriptors[2]
        prefix: tuple[str, ...] = ()
        try:
            for name in relative_parts[:-1]:
                prefix = (*prefix, name)
                expected_identity = paths.directory_identities.get(prefix)
                if expected_identity is None:
                    raise ResultArtifactError(
                        "attempt artifact parent is not pinned"
                    )
                child_descriptor = _open_bound_child_directory(
                    parent_descriptor,
                    name,
                    expected_identity,
                    label="attempt artifact directory",
                )
                opened_descriptors.append(
                    (
                        parent_descriptor,
                        name,
                        child_descriptor,
                        expected_identity,
                        "attempt artifact directory",
                    )
                )
                parent_descriptor = child_descriptor
            yield parent_descriptor, relative_parts[-1]
            for (
                ancestor_descriptor,
                name,
                child_descriptor,
                expected_identity,
                label,
            ) in reversed(opened_descriptors):
                _verify_bound_child_directory(
                    ancestor_descriptor,
                    name,
                    child_descriptor,
                    expected_identity,
                    label=label,
                )
        finally:
            for _, _, descriptor, _, _ in reversed(opened_descriptors):
                os.close(descriptor)


def _require_declared_attempt_paths(paths: AttemptPaths) -> None:
    """Confirm attempt writers operate only on one invocation-declared attempt."""
    if any(
        getattr(paths, artifact.path_attribute)
        != paths.root.joinpath(*artifact.relative_parts)
        for artifact in _PERSISTED_ATTEMPT_ARTIFACT_CONTRACT
    ):
        raise ResultArtifactError(
            "attempt artifact paths are not owned by an invocation workspace"
        )
    with _open_bound_attempt(paths) as (
        root_descriptor,
        _,
        attempt_descriptor,
    ):
        try:
            manifest_metadata = os.stat(
                "attempt.json",
                dir_fd=attempt_descriptor,
                follow_symlinks=False,
            )
            invocation_metadata = os.stat(
                "invocation.json",
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        except OSError as error:
            raise ResultArtifactError(
                "results directory must contain one regular invocation.json: "
                f"{paths.workspace_root}"
            ) from error
        manifest = _parse_result_document(
            _read_stable_file_at(
                attempt_descriptor,
                "attempt.json",
                manifest_metadata,
                maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
                label="attempt declaration",
                limit_name="JSON byte limit",
            ).content,
            paths.manifest,
            _attempt_artifact_schema("manifest"),
        )
        invocation = _read_stable_file_at(
            root_descriptor,
            "invocation.json",
            invocation_metadata,
            maximum_bytes=_MAX_RESULT_JSON_FILE_BYTES,
            label="invocation declaration",
            limit_name="JSON byte limit",
        )
        if (
            invocation.metadata != paths.invocation_identity.metadata
            or hashlib.sha256(invocation.content).digest()
            != paths.invocation_identity.digest
        ):
            raise ResultArtifactError(
                "invocation declaration changed after the attempt was created"
            )
        invocation_document = _parse_result_document(
            invocation.content,
            paths.workspace_root / "invocation.json",
            "invocation.schema.json",
        )
        if invocation_document["invocation_id"] != paths.invocation_id:
            raise ResultArtifactError(
                "attempt paths are bound to a different evaluation invocation"
            )
        declared_attempts = _declared_attempts(invocation_document)
    if declared_attempts.get(manifest["run_id"]) != manifest:
        raise ResultArtifactError(
            "attempt does not match the immutable invocation manifest"
        )


def _validate_grading_semantics(
    grading: Mapping[str, object], *, expected_source: str
) -> tuple[tuple[str, ...], ...]:
    if grading["grade_source"] != expected_source:
        raise ResultArtifactError(
            f"expected {expected_source} grading for run {grading['run_id']}, "
            f"got {grading['grade_source']}"
        )
    results = grading["assertion_results"]
    identifiers = [result["id"] for result in results]
    if len(identifiers) != len(set(identifiers)):
        raise ResultArtifactError(
            f"grading for run {grading['run_id']} has duplicate assertion identifiers"
        )
    passed = sum(bool(result["passed"]) for result in results)
    total = len(results)
    expected_summary = {
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "pass_rate": passed / total if total else 0.0,
    }
    if grading["summary"] != expected_summary:
        raise ResultArtifactError(f"grading summary does not match results for run {grading['run_id']}")
    aggregation = grading["aggregation"]
    if aggregation["variant"] not in aggregation["required_variants"]:
        raise ResultArtifactError(
            f"aggregation variant is not declared as required for run {grading['run_id']}"
        )
    return _grading_evidence_artifact_parts(grading)


def _validate_persisted_execution_binding(
    document: object,
    manifest: Mapping[str, object],
    *,
    role: str,
) -> None:
    if not isinstance(document, Mapping):
        raise ResultArtifactError(
            f"completed {role} execution is missing its fresh execution binding"
        )
    try:
        binding = execution_binding_from_document(document)
    except ValueError as error:
        raise ResultArtifactError(
            f"completed {role} execution has an invalid execution binding"
        ) from error
    if (
        binding.invocation_id != manifest["invocation_id"]
        or binding.run_id != manifest["run_id"]
        or binding.role != role
    ):
        raise ResultArtifactError(
            f"completed {role} execution binding does not match the attempt"
        )


def _validate_without_skill_baseline_evidence(
    manifest: Mapping[str, object],
    timing: Mapping[str, object],
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> None:
    if manifest["run_kind"] != "without_skill":
        return
    skill_name = manifest["skill_name"]
    paths = timing.get("successful_skill_reads")
    if not isinstance(paths, list):
        raise ResultArtifactError(
            "without_skill timing lacks canonical skill-read metadata"
        )
    for path in paths:
        classification = classify_structured_skill_path(path, skill_name)
        if classification is StructuredSkillPathKind.CANONICAL_TARGET:
            raise ResultArtifactError(
                "without_skill attempt identifies the target skill in "
                "successful_skill_reads"
            )
        if classification is StructuredSkillPathKind.NONCANONICAL:
            raise ResultArtifactError(
                "without_skill attempt contains a noncanonical path in "
                "successful_skill_reads"
            )
    expected_path = timing.get("expected_skill_path")
    if expected_path is not None:
        classification = classify_structured_skill_path(
            expected_path,
            skill_name,
        )
        if classification is StructuredSkillPathKind.CANONICAL_TARGET:
            raise ResultArtifactError(
                "without_skill attempt identifies the target skill as "
                "expected_skill_path"
            )
        if classification is StructuredSkillPathKind.NONCANONICAL:
            raise ResultArtifactError(
                "without_skill attempt contains a noncanonical "
                "expected_skill_path"
            )
    trace = _read_snapshotted_file(
        root_descriptor,
        snapshot,
        (*attempt_parts, "execution_trace.jsonl"),
        maximum_bytes=MAX_PRESERVED_JUDGE_TRACE_BYTES,
        label="cannot read without_skill execution trace",
        limit_name="without_skill execution trace byte limit",
    ).content
    for line_number, line in enumerate(trace.splitlines(), start=1):
        event = _parse_bounded_json(
            line,
            label=f"invalid without_skill execution trace event {line_number}",
            maximum_bytes=_MAX_RESULT_JSON_SCALAR_BYTES,
            maximum_nodes=256,
            maximum_depth=8,
            maximum_scalar_bytes=4096,
        )
        if not isinstance(event, dict) or event.get("event") != "skill_read":
            continue
        classification = classify_structured_skill_path(
            event.get("path"),
            skill_name,
        )
        if classification is StructuredSkillPathKind.CANONICAL_TARGET:
            raise ResultArtifactError(
                "without_skill attempt raw trace identifies the target skill"
            )
        if classification is StructuredSkillPathKind.NONCANONICAL:
            raise ResultArtifactError(
                "without_skill attempt raw trace contains a noncanonical "
                "skill_read path"
            )


def _grading_evidence_artifact_parts(
    grading: Mapping[str, object],
) -> tuple[tuple[str, ...], ...]:
    artifact_paths: list[tuple[str, ...]] = []
    for result in grading["assertion_results"]:
        for reference in result["evidence_refs"]:
            artifact = reference["artifact"]
            if (
                len(artifact) > _MAX_JUDGE_ARTIFACT_NAME_CHARS
                or artifact.startswith("/")
                or "\\" in artifact
                or "\x00" in artifact
            ):
                raise ResultArtifactError(
                    "grading evidence artifact path is invalid"
                )
            parts = tuple(artifact.split("/"))
            if not parts or any(part in ("", ".", "..") for part in parts):
                raise ResultArtifactError(
                    "grading evidence artifact path is invalid"
                )
            if parts not in _FIXED_EVIDENCE_ARTIFACT_PATHS and not (
                len(parts) > 1 and parts[0] == "outputs"
            ):
                raise ResultArtifactError(
                    "grading evidence artifact is not allowed"
                )
            artifact_paths.append(parts)
    return tuple(artifact_paths)


def _validate_snapshotted_grading_evidence(
    artifact_paths: Sequence[tuple[str, ...]],
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> None:
    for artifact_parts in artifact_paths:
        if (*attempt_parts, *artifact_parts) not in snapshot.files:
            raise ResultArtifactError(
                "grading evidence artifact does not resolve to a regular "
                "snapshotted artifact"
            )


def _validate_evidence_binding(
    grading: Mapping[str, object],
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> None:
    expected = grading.get("evidence_sha256")
    if not isinstance(expected, str):
        raise ResultArtifactError(
            "grading is missing its complete evidence digest"
        )
    actual = _snapshotted_evidence_digest(
        root_descriptor,
        snapshot,
        attempt_parts,
    )
    if actual != expected:
        raise ResultArtifactError(
            "grading does not match the complete preserved evidence"
        )


def _snapshotted_evidence_digest(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> str:
    outputs_prefix = (*attempt_parts, "outputs")
    outputs_prefix_length = len(outputs_prefix)
    attempt_length = len(attempt_parts)
    directories: list[str] = []
    files: list[tuple[str, bytes]] = []
    evidence_file_parts = {
        _attempt_artifact_parts(attempt_parts, "manifest"),
    }
    evidence_file_parts.update(
        (*attempt_parts, *relative_parts)
        for relative_parts in _FIXED_EVIDENCE_ARTIFACT_PATHS
    )
    grading_basis_parts = _attempt_artifact_parts(
        attempt_parts,
        "grading_basis",
    )
    if grading_basis_parts in snapshot.files:
        evidence_file_parts.add(grading_basis_parts)
    evidence_file_parts.update(
        relative
        for relative in snapshot.files
        if relative[:outputs_prefix_length] == outputs_prefix
    )
    evidence_directory_parts = tuple(
        relative
        for relative in snapshot.directories
        if (
            relative[:outputs_prefix_length] == outputs_prefix
            and len(relative) > outputs_prefix_length
        )
    )
    if (
        len(evidence_file_parts) + len(evidence_directory_parts)
        > _MAX_EVIDENCE_DIGEST_ENTRIES
    ):
        raise ResultArtifactError("evidence digest exceeds the entry limit")
    for relative in evidence_directory_parts:
        evidence_relative = relative[attempt_length:]
        if len(evidence_relative) > _MAX_EVIDENCE_DIGEST_DEPTH:
            raise ResultArtifactError("evidence digest exceeds the depth limit")
        directories.append("/".join(evidence_relative))

    consumed = 0
    for relative in evidence_file_parts:
        evidence_relative = relative[attempt_length:]
        if len(evidence_relative) > _MAX_EVIDENCE_DIGEST_DEPTH:
            raise ResultArtifactError("evidence digest exceeds the depth limit")
        read = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            relative,
            maximum_bytes=_MAX_EVIDENCE_DIGEST_BYTES - consumed,
            label="cannot read trustworthy evaluation evidence",
            limit_name="evidence digest byte limit",
        )
        consumed += len(read.content)
        if consumed > _MAX_EVIDENCE_DIGEST_BYTES:
            raise ResultArtifactError("evidence digest exceeds the byte limit")
        files.append(("/".join(evidence_relative), read.content))
    return digest_evidence_bundle(directories, files)


def _validate_generated_assertion_contract(
    grading: Mapping[str, object],
    manifest: Mapping[str, object],
) -> None:
    expected = [
        (
            assertion["id"],
            assertion["kind"],
            assertion["text"],
            assertion["checked_by"],
        )
        for assertion in manifest["assertion_contract"]
    ]
    actual = [
        (
            assertion["id"],
            assertion["kind"],
            assertion["text"],
            assertion["checked_by"],
        )
        for assertion in grading["assertion_results"]
    ]
    if actual != expected:
        raise ResultArtifactError(
            "generated grading does not match the immutable assertion contract"
        )


def _validate_behavior_grading_derivation(
    grading: Mapping[str, object],
    manifest: Mapping[str, object],
    basis: Mapping[str, object],
    timing: Mapping[str, object],
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> None:
    from scripts.ai_skills_lib.eval_checks import (
        behavior_check_from_document,
        evaluate_deterministic_checks,
    )

    contracts = manifest["assertion_contract"]
    if any(
        contract["checked_by"] not in ("deterministic", "judge")
        for contract in contracts
    ):
        raise ResultArtifactError(
            "behavior assertion contract contains an invalid grading authority"
        )
    deterministic_contracts = [
        contract
        for contract in contracts
        if contract["checked_by"] == "deterministic"
    ]
    judge_contracts = [
        contract for contract in contracts if contract["checked_by"] == "judge"
    ]
    deterministic_results = tuple(
        _assertion_result_from_document(result)
        for result in basis["deterministic_results"]
    )
    deterministic_signatures = [
        (result.id, result.kind, result.text, result.checked_by)
        for result in deterministic_results
    ]
    expected_deterministic_signatures = [
        (
            contract["id"],
            contract["kind"],
            contract["text"],
            contract["checked_by"],
        )
        for contract in deterministic_contracts
    ]
    if deterministic_signatures != expected_deterministic_signatures:
        raise ResultArtifactError(
            "behavior deterministic results do not match the immutable assertion contract"
        )
    checks = tuple(
        behavior_check_from_document(document)
        for document in basis["deterministic_checks"]
    )
    prepared_schemas: list[tuple[PurePosixPath, PreparedFile]] = []
    schema_digest_entries: list[dict[str, str]] = []
    schema_paths: set[PurePosixPath] = set()
    for schema in basis["deterministic_schemas"]:
        path = PurePosixPath(schema["path"])
        if (
            path.is_absolute()
            or not path.parts
            or str(path) in ("", ".")
            or ".." in path.parts
            or "\\" in schema["path"]
            or path in schema_paths
        ):
            raise ResultArtifactError(
                "behavior deterministic schema path is invalid or duplicated"
            )
        schema_paths.add(path)
        try:
            content = schema["content"].encode("utf-8")
        except (AttributeError, UnicodeError) as error:
            raise ResultArtifactError(
                "behavior deterministic schema content is invalid"
            ) from error
        prepared = PreparedFile(source=Path(path.as_posix()), content=content)
        prepared_schemas.append((path, prepared))
        schema_digest_entries.append(
            {"path": path.as_posix(), "sha256": prepared.sha256}
        )
    deterministic_input_sha256 = canonical_document_sha256(
        {
            "checks": [dict(document) for document in basis["deterministic_checks"]],
            "schemas": schema_digest_entries,
        }
    )
    if deterministic_input_sha256 != manifest["deterministic_input_sha256"]:
        raise ResultArtifactError(
            "behavior deterministic inputs do not match the immutable attempt"
        )
    with tempfile.TemporaryDirectory(prefix="ai-skills-regrade-") as directory:
        outputs_root = Path(directory) / "outputs"
        outputs_root.mkdir(mode=0o700)
        captured_paths = _materialize_snapshotted_actor_outputs(
            root_descriptor,
            snapshot,
            attempt_parts,
            outputs_root,
        )
        response_parts = (*attempt_parts, "outputs", "response.md")
        response_read = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            response_parts,
            maximum_bytes=_MAX_RESULT_FILE_BYTES,
            label="cannot read behavior response for deterministic regrading",
            limit_name="response byte limit",
        )
        try:
            response = response_read.content.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ResultArtifactError(
                "behavior response is not valid UTF-8"
            ) from error
        execution = HarnessExecution(
            response=response,
            trace=(),
            duration_ms=timing["duration_ms"],
            total_tokens=timing["total_tokens"],
            input_tokens=timing["token_details"]["input"],
            output_tokens=timing["token_details"]["output"],
            cached_tokens=timing["token_details"]["cached"],
            token_source=timing["token_details"]["source"],
            successful_skill_reads=(),
            exit_code=timing["exit_code"],
            failure=None,
            model=timing["model"],
            reasoning_effort=timing["reasoning_effort"],
            timed_out=False,
            captured_output_paths=captured_paths,
        )
        recomputed_results = evaluate_deterministic_checks(
            checks,
            outputs_root=outputs_root,
            response=response,
            execution=execution,
            skill_root=Path(directory),
            prepared_schemas=tuple(prepared_schemas),
        )
    if tuple(result.to_dict() for result in recomputed_results) != tuple(
        result.to_dict() for result in deterministic_results
    ):
        raise ResultArtifactError(
            "behavior deterministic results are not derived from preserved evidence"
        )

    prepared_response = prepare_durable_sensitive_text(
        basis["judge_response"],
        Path("grading_basis.json"),
        maximum_durable_bytes=_MAX_JUDGE_RESPONSE_BYTES,
    )
    if prepared_response.transformed:
        raise ResultArtifactError(
            "behavior judge response cannot be preserved safely"
        )
    judge_control = basis["judge_control"]
    if (
        hashlib.sha256(judge_control.encode("utf-8")).hexdigest()
        != manifest["judge_control_sha256"]
    ):
        raise ResultArtifactError(
            "behavior judge control does not match the immutable attempt"
        )
    actor_trace = _validate_preserved_judge_trace(
        root_descriptor,
        snapshot,
        attempt_parts,
        basis,
    )
    allowed_artifacts, reconstructed_prompt = _snapshotted_exact_judge_evidence(
        root_descriptor,
        snapshot,
        attempt_parts,
        control_prefix=judge_control,
        execution_trace_text=actor_trace,
    )
    if allowed_artifacts != tuple(basis["allowed_evidence_artifacts"]):
        raise ResultArtifactError(
            "behavior judge evidence set does not match the preserved basis"
        )
    if (
        hashlib.sha256(reconstructed_prompt.encode("utf-8")).hexdigest()
        != basis["judge_prompt_sha256"]
    ):
        raise ResultArtifactError(
            "behavior judge prompt is not derived from the preserved evidence"
        )
    aggregation = manifest["aggregation"]
    context = JudgeGradingContext(
        invocation_id=manifest["invocation_id"],
        run_id=manifest["run_id"],
        skill_name=manifest["skill_name"],
        case_id=manifest["case_id"],
        run_kind=manifest["run_kind"],
        prompt_version=basis["judge_prompt_version"],
        graded_at=basis["graded_at"],
        allowed_evidence_artifacts=allowed_artifacts,
        expected_assertions=tuple(
            AssertionDefinition(
                id=contract["id"],
                kind=contract["kind"],
                text=contract["text"],
            )
            for contract in judge_contracts
        ),
        aggregation=AggregationMetadata(
            group_id=aggregation["group_id"],
            variant=aggregation["variant"],
            contributes_to_outcome=aggregation["contributes_to_outcome"],
            required_variants=tuple(aggregation["required_variants"]),
            compare_to=aggregation.get("compare_to"),
            minimum_pass_rate=aggregation.get("minimum_pass_rate"),
            configured_runs=aggregation.get("configured_runs"),
            run_number=aggregation.get("run_number"),
        ),
    )
    judge_grading = parse_judge_response(
        prepared_response.text,
        context,
        model=basis["judge_model"],
        reasoning_effort=basis["judge_reasoning_effort"],
    )
    canonical = combine_grading_results(
        judge_grading,
        deterministic_results,
    )
    canonical = replace(
        canonical,
        evidence_sha256=grading["evidence_sha256"],
    )
    if canonical.to_dict() != dict(grading):
        raise ResultArtifactError(
            "behavior grading is not exactly derived from the preserved judge result"
        )


def _materialize_snapshotted_actor_outputs(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
    outputs_root: Path,
) -> tuple[CapturedOutputPath, ...]:
    prefix = (*attempt_parts, "outputs")
    prefix_length = len(prefix)
    captured: list[CapturedOutputPath] = []
    for relative in sorted(snapshot.directories):
        if relative[:prefix_length] != prefix or len(relative) == prefix_length:
            continue
        output_relative = PurePosixPath(*relative[prefix_length:])
        target = outputs_root.joinpath(*output_relative.parts)
        target.mkdir(mode=0o700, parents=True, exist_ok=True)
        captured.append(CapturedOutputPath(path=output_relative, kind="directory"))
    for relative in sorted(snapshot.files):
        if relative[:prefix_length] != prefix:
            continue
        output_relative = PurePosixPath(*relative[prefix_length:])
        if output_relative == PurePosixPath("response.md"):
            continue
        read = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            relative,
            maximum_bytes=_MAX_RESULT_FILE_BYTES,
            label="cannot read captured actor output for deterministic regrading",
            limit_name="captured output byte limit",
        )
        target = outputs_root.joinpath(*output_relative.parts)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        target.write_bytes(read.content)
        captured.append(CapturedOutputPath(path=output_relative, kind="file"))
    return tuple(captured)


def _assertion_result_from_document(
    document: Mapping[str, object],
) -> AssertionResult:
    return AssertionResult(
        id=document["id"],
        kind=document["kind"],
        text=document["text"],
        passed=document["passed"],
        checked_by=document["checked_by"],
        evidence=document["evidence"],
        evidence_refs=tuple(
            {
                "artifact": reference["artifact"],
                "locator": reference["locator"],
            }
            for reference in document["evidence_refs"]
        ),
    )


def _snapshotted_exact_judge_evidence(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
    *,
    control_prefix: str,
    execution_trace_text: str,
) -> tuple[tuple[str, ...], str]:
    outputs_prefix = (*attempt_parts, "outputs")
    candidates: dict[str, str] = {}
    required = (
        ("outputs/response.md", (*attempt_parts, "outputs", "response.md")),
        ("transcript.md", (*attempt_parts, "transcript.md")),
    )
    for artifact, relative in required:
        read = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            relative,
            maximum_bytes=MAX_JUDGE_ARTIFACT_BYTES,
            label=f"cannot read exact judge evidence {artifact}",
            limit_name="judge artifact byte limit",
        )
        try:
            candidates[artifact] = read.content.decode("utf-8")
        except (UnicodeDecodeError, MemoryError) as error:
            raise ResultArtifactError(
                "actor evidence cannot be represented as exact UTF-8 judge evidence"
            ) from error
    candidates["execution_trace.jsonl"] = execution_trace_text

    response_parts = (*attempt_parts, "outputs", "response.md")
    for relative in sorted(snapshot.files):
        if (
            relative[: len(outputs_prefix)] != outputs_prefix
            or relative == response_parts
        ):
            continue
        artifact = "/".join(relative[len(attempt_parts) :])
        if artifact in candidates:
            raise ResultArtifactError(
                "captured output conflicts with a reserved judge evidence path"
            )
        read = _read_snapshotted_file(
            root_descriptor,
            snapshot,
            relative,
            maximum_bytes=MAX_JUDGE_ARTIFACT_BYTES,
            label=f"cannot read exact judge evidence {artifact}",
            limit_name="judge artifact byte limit",
        )
        try:
            candidates[artifact] = read.content.decode("utf-8")
        except (UnicodeDecodeError, MemoryError) as error:
            raise ResultArtifactError(
                "actor evidence cannot be represented as exact UTF-8 judge evidence"
            ) from error
    return prepare_exact_judge_evidence(
        candidates,
        control_prefix=control_prefix,
    )


def _validate_preserved_judge_trace(
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
    basis: Mapping[str, object],
) -> str:
    trace = _read_snapshotted_file(
        root_descriptor,
        snapshot,
        (*attempt_parts, "execution_trace.jsonl"),
        maximum_bytes=MAX_PRESERVED_JUDGE_TRACE_BYTES,
        label="cannot read preserved judge execution trace",
        limit_name="preserved judge trace byte limit",
    ).content
    events: list[dict[str, object]] = []
    for line_number, line in enumerate(trace.splitlines(), start=1):
        if not line:
            raise ResultArtifactError(
                "behavior execution trace contains an empty event"
            )
        event = _parse_bounded_json(
            line,
            label=f"invalid behavior execution trace event {line_number}",
            maximum_bytes=_MAX_RESULT_JSON_SCALAR_BYTES,
            maximum_nodes=256,
            maximum_depth=8,
            maximum_scalar_bytes=4096,
        )
        if not isinstance(event, dict):
            raise ResultArtifactError(
                "behavior execution trace event must be an object"
            )
        events.append(event)
    if not events or events[-1].get("event") != "judge_completed":
        raise ResultArtifactError(
            "behavior execution trace is missing the terminal judge completion"
        )
    completions = [
        event for event in events if event.get("event") == "judge_completed"
    ]
    if len(completions) != 1:
        raise ResultArtifactError(
            "behavior execution trace must contain one judge completion"
        )
    completion = completions[0]
    expected_completion = {
        "event": "judge_completed",
        "duration_ms": basis["judge_duration_ms"],
        "total_tokens": basis["judge_total_tokens"],
        "model": basis["judge_model"],
        "reasoning_effort": basis["judge_reasoning_effort"],
    }
    if completion != expected_completion:
        raise ResultArtifactError(
            "behavior judge completion does not match the preserved basis"
        )

    harness_events = [
        event for event in events if event.get("event") == "judge_harness_event"
    ]
    if not harness_events:
        raise ResultArtifactError(
            "behavior execution trace is missing judge harness evidence"
        )
    judge_trace: list[Mapping[str, object]] = []
    for event in harness_events:
        if set(event) != {"event", "detail"} or not isinstance(
            event["detail"], dict
        ):
            raise ResultArtifactError(
                "behavior judge harness evidence is malformed"
            )
        detail_event = event["detail"].get("event")
        if not isinstance(detail_event, str):
            raise ResultArtifactError(
                "behavior judge harness evidence has no event type"
            )
        judge_trace.append(event["detail"])
    lifecycle_error = _judge_lifecycle_error(judge_trace)
    if lifecycle_error is not None:
        raise ResultArtifactError(
            f"behavior judge trace is invalid: {lifecycle_error}"
        )
    if any(event.get("event") == "judge_failure" for event in events):
        raise ResultArtifactError(
            "behavior judge trace contains a failure event"
        )
    boundary = next(
        index
        for index, event in enumerate(events)
        if event.get("event") == "judge_harness_event"
    )
    if any(
        event.get("event") not in {"judge_harness_event", "judge_completed"}
        for event in events[boundary:]
    ):
        raise ResultArtifactError(
            "behavior execution trace interleaves actor and judge evidence"
        )
    try:
        actor_trace = "\n".join(
            json.dumps(
                event,
                sort_keys=True,
                ensure_ascii=True,
                allow_nan=False,
            )
            for event in events[:boundary]
        )
        judge_suffix = "".join(
            f"{json.dumps(event, sort_keys=True, ensure_ascii=True, allow_nan=False)}\n"
            for event in events[boundary:]
        )
    except (
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
        SystemError,
    ) as error:
        raise ResultArtifactError(
            "behavior actor trace cannot be reconstructed exactly"
        ) from error
    if len(actor_trace.encode("utf-8")) > MAX_JUDGE_ARTIFACT_BYTES:
        raise ResultArtifactError(
            "behavior actor trace exceeds the per-artifact judge byte limit"
        )
    if (
        len(judge_suffix.encode("utf-8"))
        > MAX_PRESERVED_JUDGE_TRACE_SUFFIX_BYTES
    ):
        raise ResultArtifactError(
            "behavior judge trace exceeds its preserved suffix byte limit"
        )
    return actor_trace


def _validate_trigger_grading_semantics(
    grading: Mapping[str, object],
    manifest: Mapping[str, object],
    timing: Mapping[str, object],
    root_descriptor: int,
    snapshot: _ResultTreeSnapshot,
    attempt_parts: tuple[str, ...],
) -> None:
    expected_activation = manifest.get("expected_activation")
    if type(expected_activation) is not bool:
        raise ResultArtifactError(
            "trigger attempt is missing its immutable expected activation"
        )
    trace_relative = (*attempt_parts, "execution_trace.jsonl")
    trace = _read_snapshotted_file(
        root_descriptor,
        snapshot,
        trace_relative,
        maximum_bytes=_MAX_RESULT_FILE_BYTES,
        label="cannot read trustworthy trigger execution trace",
        limit_name="trigger execution trace byte limit",
    ).content
    activation_events: list[Mapping[str, object]] = []
    trace_events: list[Mapping[str, object]] = []
    for line_number, line in enumerate(trace.splitlines(), start=1):
        if not line:
            raise ResultArtifactError(
                "trigger execution trace contains an empty event"
            )
        event = _parse_bounded_json(
            line,
            label=f"invalid trigger execution trace event {line_number}",
            maximum_bytes=_MAX_RESULT_JSON_SCALAR_BYTES,
            maximum_nodes=256,
            maximum_depth=8,
            maximum_scalar_bytes=4096,
        )
        if not isinstance(event, dict):
            raise ResultArtifactError(
                "trigger execution trace events must be JSON objects"
            )
        trace_events.append(event)
        if event.get("event") == "trigger_activation_evidence":
            activation_events.append(event)
    if len(activation_events) != 1:
        raise ResultArtifactError(
            "trigger execution trace must contain exactly one activation event"
        )

    activation_event = activation_events[0]
    activation = activation_event.get("successful_exact_read")
    expected_path = activation_event.get("expected_skill_path")
    event_catalog_path = activation_event.get("expected_skill_catalog_path")
    declared_catalog_path = manifest.get("expected_skill_catalog_path")
    canonical_expected_path = str(
        canonical_codex_skill_path(manifest["skill_name"])
    )
    if (
        type(activation) is not bool
        or not isinstance(expected_path, str)
        or not isinstance(event_catalog_path, str)
        or not isinstance(declared_catalog_path, str)
        or event_catalog_path != declared_catalog_path
    ):
        raise ResultArtifactError(
            "trigger activation event is missing exact-read evidence"
        )
    catalog_path = PurePosixPath(declared_catalog_path)
    canonical_catalog_parts = (
        "codex-home",
        "skills",
        manifest["skill_name"],
        "SKILL.md",
    )
    if (
        expected_path != canonical_expected_path
        or classify_codex_skill_evidence_path(
            expected_path,
            manifest["skill_name"],
        )
        is not StructuredSkillPathKind.CANONICAL_TARGET
        or catalog_path.is_absolute()
        or str(catalog_path) != declared_catalog_path
        or "\\" in declared_catalog_path
        or "\x00" in declared_catalog_path
        or ".." in catalog_path.parts
        or catalog_path.parts != canonical_catalog_parts
    ):
        raise ResultArtifactError(
            "trigger activation event has an invalid installed skill path"
        )

    raw_skill_read_classifications = tuple(
        classify_codex_skill_evidence_path(
            path,
            manifest["skill_name"],
        )
        for path in _validated_trigger_lifecycle_skill_reads(
            trace_events,
        )
    )
    if any(
        classification is StructuredSkillPathKind.NONCANONICAL
        for classification in raw_skill_read_classifications
    ):
        raise ResultArtifactError(
            "trigger trace has an invalid installed skill path"
        )
    exact_skill_reads = sum(
        classification is StructuredSkillPathKind.CANONICAL_TARGET
        for classification in raw_skill_read_classifications
    )
    if exact_skill_reads != int(activation):
        raise ResultArtifactError(
            "trigger activation event does not match the raw exact skill-read evidence"
        )

    timing_expected_path = timing.get("expected_skill_path")
    timing_skill_reads = timing.get("successful_skill_reads")
    if (
        timing_expected_path != canonical_expected_path
        or not isinstance(timing_skill_reads, list)
    ):
        raise ResultArtifactError(
            "trigger timing has an invalid installed skill path"
        )
    timing_read_classifications = tuple(
        classify_codex_skill_evidence_path(
            timing_path,
            manifest["skill_name"],
        )
        for timing_path in timing_skill_reads
    )
    if any(
        classification is StructuredSkillPathKind.NONCANONICAL
        for classification in timing_read_classifications
    ):
        raise ResultArtifactError(
            "trigger timing has an invalid installed skill path"
        )
    timing_exact_skill_reads = sum(
        classification is StructuredSkillPathKind.CANONICAL_TARGET
        for classification in timing_read_classifications
    )
    if timing_exact_skill_reads != int(activation):
        raise ResultArtifactError(
            "trigger activation event does not match timing skill-read metadata"
        )

    assertion_results = grading["assertion_results"]
    if len(assertion_results) != 1:
        raise ResultArtifactError(
            "trigger grading must contain exactly one activation assertion"
        )
    assertion = assertion_results[0]
    expected_pass = activation is expected_activation
    expected_text = (
        f"The installed harness "
        f"{'loads' if expected_activation else 'does not load'} "
        f"the {manifest['skill_name']} skill."
    )
    expected_evidence = (
        f"The harness recorded a successful exact installed SKILL.md read at "
        f"{expected_path}."
        if activation
        else (
            "No successful exact installed SKILL.md read was recorded for "
            f"{manifest['skill_name']}."
        )
    )
    expected_locator = (
        "trigger_activation_evidence successful_exact_read=true"
        if activation
        else "trigger_activation_evidence successful_exact_read=false"
    )
    grade_source = grading["grade_source"]
    expected_checked_by = (
        "trigger_runner" if grade_source == "judge" else "human"
    )
    if (
        assertion["id"] != "expected-skill-activation"
        or assertion["kind"] != "trigger"
        or assertion["text"] != expected_text
        or assertion["checked_by"] != expected_checked_by
        or assertion["passed"] is not expected_pass
        or assertion["evidence"] != expected_evidence
        or assertion["evidence_refs"]
        != [
            {
                "artifact": "execution_trace.jsonl",
                "locator": expected_locator,
            }
        ]
    ):
        raise ResultArtifactError(
            "trigger grading assertion does not match the immutable expectation "
            "and activation evidence"
        )
    measurements = grading.get("measurements")
    if (
        not isinstance(measurements, dict)
        or set(measurements)
        != {"trigger_rate", "expected_trigger_rate"}
        or type(measurements.get("trigger_rate")) not in (int, float)
        or type(measurements.get("expected_trigger_rate")) not in (int, float)
        or float(measurements["trigger_rate"]) != float(activation)
        or float(measurements["expected_trigger_rate"]) != float(expected_activation)
    ):
        raise ResultArtifactError(
            "trigger grading measurements do not match the immutable expectation "
            "and activation evidence"
        )
    grader = grading["grader"]
    if grade_source == "judge":
        if (
            grader["type"] != "deterministic"
            or grader["model"] is not None
            or grader["reasoning_effort"] is not None
            or grader["prompt_version"] != "trigger-runner-v1"
        ):
            raise ResultArtifactError(
                "generated trigger grading must be produced by the deterministic "
                "trigger runner"
            )
    elif grader["type"] != "human":
        raise ResultArtifactError(
            "manual trigger grading must identify a human grader"
        )


def _validated_trigger_lifecycle_skill_reads(
    trace_events: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    if (
        not trace_events
        or trace_events[-1].get("event") != "trigger_activation_evidence"
        or any(
            event.get("event") == "trigger_activation_evidence"
            for event in trace_events[:-1]
        )
    ):
        raise ResultArtifactError(
            "trigger activation evidence must follow one complete actor lifecycle"
        )
    try:
        return validated_actor_skill_read_lifecycle(trace_events[:-1])
    except ValueError as error:
        raise ResultArtifactError(
            f"trigger actor lifecycle is invalid: {error}"
        ) from error


def _validate_complete_manual_override(
    generated: Mapping[str, object],
    manual: Mapping[str, object],
    timing: Mapping[str, object],
    manual_path: Path,
) -> None:
    identity_fields = (
        "run_id",
        "skill_name",
        "case_id",
        "run_kind",
        "aggregation",
        "evidence_sha256",
    )
    if any(generated.get(field) != manual.get(field) for field in identity_fields):
        raise ResultArtifactError(f"manual grading is not a complete override for {manual_path}")
    if generated.get("measurements", {}) != manual.get("measurements", {}):
        raise ResultArtifactError(f"manual grading is not a complete override for {manual_path}")
    generated_assertions = [
        (result["id"], result["kind"], result["text"])
        for result in generated["assertion_results"]
    ]
    manual_assertions = [
        (result["id"], result["kind"], result["text"])
        for result in manual["assertion_results"]
    ]
    if generated_assertions != manual_assertions:
        raise ResultArtifactError(f"manual grading is not a complete override for {manual_path}")
    for generated_result, manual_result in zip(
        generated["assertion_results"],
        manual["assertion_results"],
        strict=True,
    ):
        if generated_result.get("checked_by") != "deterministic":
            continue
        if any(
            generated_result.get(field) != manual_result.get(field)
            for field in ("passed", "evidence", "evidence_refs")
        ):
            raise ResultArtifactError(
                "manual grading cannot override deterministic assertion "
                f"{generated_result['id']} in {manual_path}"
            )
    if any(
        result.get("checked_by") != "human"
        for result in manual["assertion_results"]
    ):
        raise ResultArtifactError(
            f"manual grading assertions must be checked by a human in {manual_path}"
        )
    grader = manual["grader"]
    if (
        grader.get("type") != "human"
        or grader.get("model") is not None
        or grader.get("reasoning_effort") is not None
    ):
        raise ResultArtifactError(
            f"manual grading human reviewer model metadata is invalid in {manual_path}"
        )
    reviewer_identity = grader.get("reviewer_identity")
    reviewer_label = grader.get("reviewer_label")
    if not any(
        isinstance(value, str) and value.strip()
        for value in (reviewer_identity, reviewer_label)
    ):
        raise ResultArtifactError(
            f"manual grading requires a nonempty reviewer identity or reviewer label in {manual_path}"
        )
    try:
        generated_at = _parse_result_timestamp(generated["graded_at"])
        attempt_ended_at = _parse_result_timestamp(timing["ended_at"])
        reviewed_at = _parse_result_timestamp(manual["graded_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise ResultArtifactError(
            f"manual grading has an invalid review timestamp in {manual_path}"
        ) from error
    if reviewed_at <= generated_at or reviewed_at < attempt_ended_at:
        raise ResultArtifactError(
            f"manual grading review timestamp must be distinct from and not earlier "
            f"than the generated grade and attempt in {manual_path}"
        )


def _parse_result_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise TypeError("timestamp must be text")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)


def _validate_artifact_matches_manifest(
    artifact: Mapping[str, object],
    manifest: Mapping[str, object],
    artifact_path: Path,
) -> None:
    for field in (
        "invocation_id",
        "run_id",
        "skill_name",
        "case_id",
        "run_kind",
    ):
        if artifact[field] != manifest[field]:
            raise ResultArtifactError(
                f"artifact does not match attempt manifest in {artifact_path}: {field}"
            )
    if "aggregation" in artifact and artifact["aggregation"] != manifest["aggregation"]:
        raise ResultArtifactError(
            f"artifact aggregation policy does not match attempt manifest in {artifact_path}"
        )


def _validate_completed_timing(
    timing: Mapping[str, object], timing_path: Path
) -> None:
    if timing["status"] == "completed" and timing["exit_code"] != 0:
        raise ResultArtifactError(
            f"completed timing lacks an explicit successful exit in {timing_path}"
        )
    if timing["status"] == "completed" and (
        timing["model"] is None or timing["reasoning_effort"] is None
    ):
        raise ResultArtifactError(
            f"completed timing lacks model or reasoning metadata in {timing_path}"
        )


def _summarize_assertions(results: Sequence[AssertionResult]) -> GradingSummary:
    passed = sum(result.passed for result in results)
    total = len(results)
    return GradingSummary(
        passed=passed,
        failed=total - passed,
        total=total,
        pass_rate=passed / total if total else 0.0,
    )


def _write_json_atomic(
    path: Path,
    value: Mapping[str, object],
    root: Path,
    *,
    expected_root_identity: tuple[int, int, int] | None = None,
) -> None:
    _write_text_atomic(
        path,
        _serialize_json_document(value),
        root,
        replace_existing=True,
        expected_root_identity=expected_root_identity,
    )


def _serialize_json_document(value: Mapping[str, object]) -> str:
    try:
        text = f"{json.dumps(value, indent=2, sort_keys=True)}\n"
        encoded_size = len(text.encode("utf-8"))
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise ResultArtifactError("cannot serialize result JSON") from error
    if encoded_size > _MAX_RESULT_JSON_FILE_BYTES:
        raise ResultArtifactError("result JSON exceeds the JSON byte limit")
    return text


def canonical_document_sha256(value: object) -> str:
    """Hash one bounded JSON-compatible document using a canonical encoding."""
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except (MemoryError, OverflowError, RecursionError, TypeError, ValueError) as error:
        raise ResultArtifactError(
            "cannot hash an evaluation input document"
        ) from error
    if len(encoded) > _MAX_RESULT_JSON_FILE_BYTES:
        raise ResultArtifactError("evaluation input document exceeds the hash byte limit")
    return hashlib.sha256(encoded).hexdigest()


def prepare_exact_judge_evidence(
    artifact_candidates: Mapping[str, str],
    *,
    control_prefix: str,
    maximum_artifact_bytes: int = MAX_JUDGE_ARTIFACT_BYTES,
    maximum_prompt_bytes: int = MAX_JUDGE_PROMPT_BYTES,
) -> tuple[tuple[str, ...], str]:
    """Validate exact actor evidence and render the bounded judge prompt."""
    exact_evidence: dict[str, str] = {}
    evidence_scan = SecretScanBudget()
    for name, value in artifact_candidates.items():
        if "\x00" in name or "\x00" in value:
            raise ResultArtifactError(
                "actor evidence cannot contain NUL bytes"
            )
        prepared_name = prepare_durable_sensitive_text(
            name,
            Path("artifact-name"),
            maximum_durable_bytes=_MAX_JUDGE_ARTIFACT_NAME_CHARS,
            scan_budget=evidence_scan,
        )
        if prepared_name.transformed or prepared_name.text != name:
            raise ResultArtifactError(
                "actor evidence path required sensitive-content transformation"
            )
        prepared_value = prepare_durable_sensitive_text(
            value,
            Path(name),
            maximum_durable_bytes=maximum_artifact_bytes,
            scan_budget=evidence_scan,
        )
        if prepared_value.transformed or prepared_value.text != value:
            if prepared_value.size_truncated and not (
                prepared_value.minimum_finding_count
                or prepared_value.scan_incomplete
                or prepared_value.finding_count_truncated
            ):
                raise ResultArtifactError(
                    "actor evidence exceeds the per-artifact judge byte limit"
                )
            raise ResultArtifactError(
                "actor evidence required sensitive-content transformation before judging"
            )
        exact_evidence[name] = value

    required_artifacts = {
        "outputs/response.md",
        "transcript.md",
        "execution_trace.jsonl",
    }
    if not required_artifacts.issubset(exact_evidence):
        raise ResultArtifactError(
            "judge control envelope leaves insufficient room for required evidence"
        )
    prompt = (
        f"{control_prefix}"
        f"UNTRUSTED_EVIDENCE_JSON\n"
        f"{json.dumps(exact_evidence, sort_keys=True)}"
    )
    if len(prompt.encode("utf-8")) > maximum_prompt_bytes:
        raise ResultArtifactError(
            "exact actor evidence exceeds the aggregate judge prompt byte limit"
        )
    return tuple(exact_evidence), prompt


def _write_text_once(
    path: Path,
    text: str,
    root: Path,
    *,
    expected_root_identity: tuple[int, int, int] | None = None,
    repository_identity: tuple[int, int] | None = None,
) -> _StableContentIdentity:
    return _write_text_atomic(
        path,
        text,
        root,
        replace_existing=False,
        expected_root_identity=expected_root_identity,
        repository_identity=repository_identity,
    )


def _retained_workspace_error(path: Path) -> ResultArtifactError:
    return ResultArtifactError(
        f"cannot initialize result workspace; retained partial state at {path}"
    )


def _write_text_atomic(
    path: Path,
    text: str,
    root: Path,
    *,
    replace_existing: bool,
    expected_root_identity: tuple[int, int, int] | None = None,
    repository_identity: tuple[int, int] | None = None,
) -> _StableContentIdentity:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ResultArtifactError(f"artifact path escapes result workspace: {path}") from error
    if (
        not relative.parts
        or any(part in ("", ".", "..") for part in relative.parts)
    ):
        raise ResultArtifactError(f"artifact path escapes result workspace: {path}")
    try:
        content = text.encode("utf-8")
    except (AttributeError, UnicodeError) as error:
        raise ResultArtifactError(f"cannot write result artifact {path}") from error

    root_descriptor: int | None = None
    opened_descriptors: list[int] = []
    ancestry: list[tuple[int, str, int, tuple[int, ...]]] = []
    try:
        root_descriptor, root_metadata = _open_result_root(root, root)
        if (
            expected_root_identity is not None
            and _result_directory_identity(os.fstat(root_descriptor))
            != expected_root_identity
        ):
            raise ResultArtifactError("result workspace root was replaced")
        if repository_identity is not None:
            _verify_result_root_outside_repository(
                root_descriptor,
                repository_identity,
            )
        opened_descriptors.append(root_descriptor)
        parent_descriptor = root_descriptor
        for name in relative.parts[:-1]:
            observed = os.stat(
                name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
                raise ResultArtifactError(
                    f"artifact parent must be a regular directory: {path}"
                )
            child_descriptor = os.open(
                name,
                _directory_open_flags(),
                dir_fd=parent_descriptor,
            )
            opened = os.fstat(child_descriptor)
            expected_metadata = _stable_result_metadata(opened)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _stable_result_metadata(observed) != expected_metadata
            ):
                os.close(child_descriptor)
                raise ResultArtifactError(
                    f"artifact parent changed while opening: {path}"
                )
            ancestry.append(
                (parent_descriptor, name, child_descriptor, expected_metadata)
            )
            opened_descriptors.append(child_descriptor)
            parent_descriptor = child_descriptor

        leaf = relative.parts[-1]
        try:
            current = os.stat(
                leaf,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            expected_metadata = None
        else:
            if not replace_existing:
                raise ResultArtifactError(f"result artifact already exists: {path}")
            if stat.S_ISLNK(current.st_mode) or not stat.S_ISREG(current.st_mode):
                raise ResultArtifactError(
                    f"artifact target must be a regular file: {path}"
                )
            expected_metadata = _stable_result_metadata(current)

        written_metadata = _write_atomic_result_file_at(
            parent_descriptor,
            leaf,
            content,
            expected_metadata=expected_metadata,
            maximum_bytes=max(_MAX_RESULT_FILE_BYTES, len(content)),
        )
        os.fsync(parent_descriptor)
        for (
            ancestor_descriptor,
            name,
            child_descriptor,
            expected_directory,
        ) in reversed(ancestry):
            current = os.stat(
                name,
                dir_fd=ancestor_descriptor,
                follow_symlinks=False,
            )
            opened = os.fstat(child_descriptor)
            if (
                not stat.S_ISDIR(current.st_mode)
                or _stable_result_metadata(current)[:3]
                != expected_directory[:3]
                or _stable_result_metadata(opened)[:3]
                != expected_directory[:3]
            ):
                raise ResultArtifactError(
                    f"artifact parent changed while writing: {path}"
                )
        _verify_open_result_root_identity(
            root_descriptor,
            root,
            expected_root_identity or root_metadata,
        )
        if repository_identity is not None:
            _verify_result_root_outside_repository(
                root_descriptor,
                repository_identity,
            )
        return _StableContentIdentity(
            metadata=written_metadata,
            digest=hashlib.sha256(content).digest(),
        )
    except ResultArtifactError:
        raise
    except (
        OSError,
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise ResultArtifactError(f"cannot write result artifact {path}") from error
    finally:
        for descriptor in reversed(opened_descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _ensure_safe_artifact_path(root: Path, path: Path) -> None:
    if path.is_symlink():
        raise ResultArtifactError(f"artifact path must not be a symlink: {path}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_parent = path.parent.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError(f"cannot resolve artifact path {path}") from error
    if not resolved_parent.is_relative_to(resolved_root):
        raise ResultArtifactError(f"artifact path escapes result workspace: {path}")


def _format_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamps must include timezone information")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _serialize_execution_trace(
    execution_trace: Sequence[Mapping[str, object]],
) -> str:
    try:
        return "".join(
            f"{json.dumps(dict(event), sort_keys=True)}\n"
            for event in execution_trace
        )
    except (TypeError, ValueError) as error:
        raise ResultArtifactError("cannot serialize normalized execution trace") from error


def _safe_validation_path(path: Sequence[object]) -> str:
    safe_fields = {
        "schema_version",
        "run_id",
        "skill_name",
        "case_id",
        "run_kind",
        "grader",
        "type",
        "model",
        "reasoning_effort",
        "prompt_version",
        "graded_at",
        "evidence_sha256",
        "assertion_results",
        "id",
        "kind",
        "text",
        "passed",
        "checked_by",
        "evidence",
        "evidence_refs",
        "artifact",
        "locator",
        "summary",
        "aggregation",
        "group_id",
        "variant",
        "contributes_to_outcome",
        "required_variants",
        "compare_to",
        "source_summaries",
        "groups",
        "variants",
        "comparisons",
    }
    rendered = "$"
    for component in path:
        if isinstance(component, int):
            rendered += f"[{component}]"
        elif component in safe_fields:
            rendered += f".{component}"
        else:
            rendered += ".<property>"
    return rendered
