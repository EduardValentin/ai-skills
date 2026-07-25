"""Shared bounded preparation for untrusted actor responses and traces."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile

from scripts.ai_skills_lib.authored_content import (
    BoundedJsonError,
    DEFAULT_MAXIMUM_JSON_DEPTH,
    DEFAULT_MAXIMUM_JSON_NODES,
    SecretScanBudget,
    SecretScanLimitError,
    prepare_durable_sensitive_text,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.harness import HarnessExecution
from scripts.ai_skills_lib.eval_core import (
    MAX_CAPTURED_OUTPUT_ENTRIES_PER_ATTEMPT,
    ResultArtifactError,
)


MAX_RESPONSE_BYTES = 64 * 1024
MAX_EXECUTION_TRACE_BYTES = 512 * 1024
MAX_EXECUTION_TRACE_JSON_NODES = DEFAULT_MAXIMUM_JSON_NODES
MAX_EXECUTION_TRACE_JSON_DEPTH = DEFAULT_MAXIMUM_JSON_DEPTH
MAX_CAPTURED_OUTPUT_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_CAPTURED_OUTPUT_SNAPSHOT_ENTRIES = (
    MAX_CAPTURED_OUTPUT_ENTRIES_PER_ATTEMPT
)
MAX_CAPTURED_OUTPUT_SNAPSHOT_DEPTH = 64
MAX_CAPTURED_OUTPUT_SECRET_SCAN_BYTES = (
    MAX_CAPTURED_OUTPUT_SNAPSHOT_BYTES * 3
)
OUTPUT_READ_CHUNK_BYTES = 64 * 1024


@dataclass(frozen=True)
class CapturedOutputFile:
    path: PurePosixPath
    content: bytes


@dataclass(frozen=True)
class CapturedOutputSnapshot:
    root_identity: tuple[int, int, int]
    directories: tuple[PurePosixPath, ...]
    files: tuple[CapturedOutputFile, ...]


class ImmutableJsonObject(dict[str, object]):
    """JSON object snapshot that rejects mutation after trusted parsing."""

    def _reject_mutation(self, *args: object, **kwargs: object) -> None:
        raise TypeError("frozen trace objects cannot be mutated")

    __setitem__ = _reject_mutation
    __delitem__ = _reject_mutation
    clear = _reject_mutation
    pop = _reject_mutation
    popitem = _reject_mutation
    setdefault = _reject_mutation
    update = _reject_mutation
    __ior__ = _reject_mutation


def prepare_durable_actor_execution(
    execution: HarnessExecution,
) -> tuple[HarnessExecution, str]:
    """Fail closed whenever actor response or trace bytes require transformation."""
    response_result = prepare_durable_sensitive_text(
        execution.response,
        Path("outputs/response.md"),
        maximum_durable_bytes=MAX_RESPONSE_BYTES,
    )
    diagnostics: list[str] = []
    if response_result.transformed:
        if response_result.scan_incomplete:
            diagnostics.append(
                "actor response secret scanning exceeded its bounded budget"
            )
        elif response_result.minimum_finding_count:
            diagnostics.append(
                "actor response contained classified sensitive material and was redacted"
            )
        else:
            diagnostics.append(
                "actor response cannot be preserved exactly under the durable 64 KiB policy"
            )

    trace = freeze_scanned_execution_trace(execution.trace)
    if trace is None:
        trace = (
            ImmutableJsonObject(
                {
                    "event": "actor_trace_quarantine",
                    "message": "actor execution trace could not be preserved safely",
                }
            ),
        )
        diagnostics.append(
            "actor execution trace required quarantine before durable commit"
        )

    failure = (
        _bounded_runtime_text(execution.failure, 4096)
        if execution.failure is not None
        else None
    )
    if diagnostics:
        trace = (
            *trace,
            *(
                ImmutableJsonObject(
                    {"event": "evidence_error", "message": diagnostic}
                )
                for diagnostic in diagnostics
            ),
        )
        failure = "\n".join(part for part in (failure, *diagnostics) if part)
    return replace(execution, trace=trace, failure=failure), response_result.text


def snapshot_captured_outputs(
    outputs_root: Path,
    *,
    expected_parent_identity: tuple[int, int, int] | None = None,
    expected_root_identity: tuple[int, int, int] | None = None,
) -> CapturedOutputSnapshot:
    """Freeze the exact regular-file tree produced by one actor attempt."""
    directories: list[PurePosixPath] = []
    files: list[CapturedOutputFile] = []
    entry_count = 0
    consumed_bytes = 0
    scan_budget = SecretScanBudget(
        maximum_bytes=MAX_CAPTURED_OUTPUT_SECRET_SCAN_BYTES,
        maximum_findings=1,
    )
    parent_descriptor: int | None = None
    root_descriptor: int | None = None

    def scan_directory(
        directory_descriptor: int,
        relative_directory: PurePosixPath,
        depth: int,
    ) -> None:
        nonlocal entry_count, consumed_bytes
        try:
            with os.scandir(directory_descriptor) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as error:
            raise ResultArtifactError("cannot inspect captured outputs") from error
        for entry in entries:
            entry_count += 1
            if entry_count > MAX_CAPTURED_OUTPUT_SNAPSHOT_ENTRIES:
                raise ResultArtifactError(
                    "captured output snapshot exceeds the entry limit"
                )
            relative = (
                PurePosixPath(entry.name)
                if relative_directory == PurePosixPath(".")
                else relative_directory / entry.name
            )
            _require_safe_captured_text(
                str(relative),
                Path("captured-output-path"),
                scan_budget,
            )
            try:
                observed = entry.stat(follow_symlinks=False)
            except OSError as error:
                raise ResultArtifactError(
                    "cannot inspect captured output entry"
                ) from error
            if stat.S_ISLNK(observed.st_mode):
                raise ResultArtifactError("captured outputs cannot contain symlinks")
            if stat.S_ISDIR(observed.st_mode):
                if depth >= MAX_CAPTURED_OUTPUT_SNAPSHOT_DEPTH:
                    raise ResultArtifactError(
                        "captured output snapshot exceeds the depth limit"
                    )
                directories.append(relative)
                child_descriptor = _open_stable_output_directory_at(
                    directory_descriptor,
                    entry.name,
                    observed,
                )
                try:
                    scan_directory(child_descriptor, relative, depth + 1)
                    _require_unchanged_output_directory_at(
                        directory_descriptor,
                        entry.name,
                        observed,
                        child_descriptor,
                    )
                finally:
                    os.close(child_descriptor)
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise ResultArtifactError(
                    "captured outputs cannot contain special files"
                )
            content = _read_stable_output_file_at(
                directory_descriptor,
                entry.name,
                observed,
                maximum_bytes=(
                    MAX_CAPTURED_OUTPUT_SNAPSHOT_BYTES - consumed_bytes
                ),
            )
            consumed_bytes += len(content)
            _require_safe_captured_content(
                content,
                Path(str(relative)),
                scan_budget,
            )
            files.append(CapturedOutputFile(relative, content))

    try:
        parent_metadata = outputs_root.parent.lstat()
        if stat.S_ISLNK(parent_metadata.st_mode) or not stat.S_ISDIR(
            parent_metadata.st_mode
        ):
            raise ResultArtifactError(
                "outputs parent must be a regular directory"
            )
        parent_descriptor = os.open(
            outputs_root.parent,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened_parent = os.fstat(parent_descriptor)
        parent_identity = _output_directory_identity(opened_parent)
        if (
            _output_stat_signature(opened_parent)
            != _output_stat_signature(parent_metadata)
            or (
                expected_parent_identity is not None
                and parent_identity != expected_parent_identity
            )
        ):
            raise ResultArtifactError(
                "outputs parent changed while its snapshot was opened"
            )
        root_metadata = os.stat(
            outputs_root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(
            root_metadata.st_mode
        ):
            raise ResultArtifactError(
                "outputs directory must be a regular directory"
            )
        root_descriptor = os.open(
            outputs_root.name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened_root = os.fstat(root_descriptor)
        opened_root_identity = _output_directory_identity(opened_root)
        if (
            _output_stat_signature(opened_root)
            != _output_stat_signature(root_metadata)
            or (
                expected_root_identity is not None
                and opened_root_identity != expected_root_identity
            )
        ):
            raise ResultArtifactError(
                "outputs directory changed while its snapshot was opened"
            )
        scan_directory(root_descriptor, PurePosixPath("."), 0)
        final_root = os.fstat(root_descriptor)
        named_root = os.stat(
            outputs_root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        final_parent = os.fstat(parent_descriptor)
        named_parent = outputs_root.parent.lstat()
        if (
            _output_stat_signature(final_root)
            != _output_stat_signature(opened_root)
            or _output_stat_signature(named_root)
            != _output_stat_signature(opened_root)
            or _output_stat_signature(final_parent)
            != _output_stat_signature(opened_parent)
            or _output_stat_signature(named_parent)
            != _output_stat_signature(opened_parent)
        ):
            raise ResultArtifactError(
                "outputs directory changed while its snapshot was read"
            )
        return CapturedOutputSnapshot(
            root_identity=opened_root_identity,
            directories=tuple(sorted(directories, key=str)),
            files=tuple(sorted(files, key=lambda file: str(file.path))),
        )
    except ResultArtifactError:
        raise
    except OSError as error:
        raise ResultArtifactError("cannot inspect captured outputs") from error
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _require_safe_captured_text(
    text: str,
    source: Path,
    budget: SecretScanBudget,
) -> None:
    try:
        result = budget.scan(text, source)
    except SecretScanLimitError as error:
        raise ResultArtifactError(
            "captured output sensitive-content scanning exceeded its bounded budget"
        ) from error
    if (
        result.transformed
        or result.finding_count_truncated
        or result.boundary_uncertain
        or result.minimum_finding_count
    ):
        raise ResultArtifactError(
            "captured output contains classified sensitive material"
        )


def _require_safe_captured_content(
    content: bytes,
    source: Path,
    budget: SecretScanBudget,
) -> None:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")
    _require_safe_captured_text(text, source, budget)


@contextmanager
def materialized_output_snapshot(
    snapshot: CapturedOutputSnapshot,
) -> Iterator[Path]:
    """Expose a read-only-by-convention copy for deterministic checks."""
    with tempfile.TemporaryDirectory(
        prefix="ai-skills-output-snapshot-"
    ) as directory:
        root = Path(directory) / "outputs"
        root.mkdir(mode=0o700)
        _write_output_snapshot(root, snapshot)
        yield root


def require_unchanged_output_snapshot(
    outputs_root: Path,
    expected: CapturedOutputSnapshot,
    *,
    runner_response: str | None = None,
    expected_parent_identity: tuple[int, int, int] | None = None,
    repository_identity: tuple[int, int] | None = None,
) -> None:
    """Require current actor outputs to equal the frozen evidence snapshot."""
    try:
        current = snapshot_captured_outputs(
            outputs_root,
            expected_parent_identity=expected_parent_identity,
            expected_root_identity=expected.root_identity,
        )
    except ResultArtifactError as error:
        _restore_output_snapshot(
            outputs_root,
            expected,
            runner_response=runner_response,
            expected_parent_identity=expected_parent_identity,
            repository_identity=repository_identity,
        )
        raise ResultArtifactError(
            "captured outputs became unsafe after the actor evidence snapshot"
        ) from error
    if runner_response is not None:
        response_path = PurePosixPath("response.md")
        expected_response = runner_response.encode("utf-8")
        response_files = tuple(
            file for file in current.files if file.path == response_path
        )
        if (
            len(response_files) == 1
            and response_files[0].content == expected_response
        ):
            current = CapturedOutputSnapshot(
                root_identity=current.root_identity,
                directories=current.directories,
                files=tuple(
                    file for file in current.files if file.path != response_path
                ),
            )
    if current != expected:
        _restore_output_snapshot(
            outputs_root,
            expected,
            runner_response=runner_response,
            expected_parent_identity=expected_parent_identity,
            repository_identity=repository_identity,
        )
        raise ResultArtifactError(
            "captured outputs changed after the actor evidence snapshot"
        )


def _open_stable_output_directory_at(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
) -> int:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
    except OSError as error:
        raise ResultArtifactError(
            "captured output directory changed while it was opened"
        ) from error
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _output_stat_signature(opened) != _output_stat_signature(observed)
    ):
        os.close(descriptor)
        raise ResultArtifactError(
            "captured output directory changed while it was opened"
        )
    return descriptor


def _require_unchanged_output_directory_at(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
    descriptor: int,
) -> None:
    try:
        final = os.fstat(descriptor)
        named_final = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
    except OSError as error:
        raise ResultArtifactError(
            "captured output directory changed while it was read"
        ) from error
    signature = _output_stat_signature(observed)
    if (
        _output_stat_signature(final) != signature
        or _output_stat_signature(named_final) != signature
    ):
        raise ResultArtifactError(
            "captured output directory changed while it was read"
        )


def _read_stable_output_file_at(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
    *,
    maximum_bytes: int,
) -> bytes:
    if observed.st_size > maximum_bytes:
        raise ResultArtifactError(
            "captured output snapshot exceeds the aggregate byte limit"
        )
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if _output_stat_signature(opened) != _output_stat_signature(observed):
            raise ResultArtifactError(
                "captured output changed while its snapshot was opened"
            )
        chunks: list[bytes] = []
        consumed = 0
        while True:
            chunk = os.read(descriptor, OUTPUT_READ_CHUNK_BYTES)
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > maximum_bytes:
                raise ResultArtifactError(
                    "captured output snapshot exceeds the aggregate byte limit"
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        signature = _output_stat_signature(opened)
        if (
            _output_stat_signature(after) != signature
            or _output_stat_signature(named_after) != signature
            or consumed != opened.st_size
        ):
            raise ResultArtifactError(
                "captured output changed while its snapshot was read"
            )
        return b"".join(chunks)
    except ResultArtifactError:
        raise
    except (OSError, MemoryError) as error:
        raise ResultArtifactError(
            "cannot read captured output for its evidence snapshot"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _output_stat_signature(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _output_directory_identity(value: os.stat_result) -> tuple[int, int, int]:
    return (value.st_dev, value.st_ino, value.st_mode)


def _write_output_snapshot(
    root: Path,
    snapshot: CapturedOutputSnapshot,
) -> None:
    for relative in sorted(
        snapshot.directories,
        key=lambda path: (len(path.parts), str(path)),
    ):
        root.joinpath(*relative.parts).mkdir(mode=0o700)
    for file in snapshot.files:
        destination = root.joinpath(*file.path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        destination.write_bytes(file.content)
        destination.chmod(0o600)


def _restore_output_snapshot(
    outputs_root: Path,
    snapshot: CapturedOutputSnapshot,
    *,
    runner_response: str | None,
    expected_parent_identity: tuple[int, int, int] | None,
    repository_identity: tuple[int, int] | None,
) -> None:
    parent_descriptor: int | None = None
    root_descriptor: int | None = None
    try:
        observed_parent = outputs_root.parent.lstat()
        if (
            not stat.S_ISDIR(observed_parent.st_mode)
            or stat.S_ISLNK(observed_parent.st_mode)
        ):
            raise ResultArtifactError(
                "captured outputs parent was replaced after its snapshot"
            )
        parent_descriptor = os.open(
            outputs_root.parent,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened_parent = os.fstat(parent_descriptor)
        parent_identity = _output_directory_identity(opened_parent)
        if (
            _output_stat_signature(opened_parent)
            != _output_stat_signature(observed_parent)
            or (
                expected_parent_identity is not None
                and parent_identity != expected_parent_identity
            )
        ):
            raise ResultArtifactError(
                "captured outputs parent was replaced after its snapshot"
            )
        if repository_identity is not None:
            _verify_output_ancestry(
                parent_descriptor,
                repository_identity,
            )
        observed = os.stat(
            outputs_root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            not stat.S_ISDIR(observed.st_mode)
            or _output_directory_identity(observed) != snapshot.root_identity
        ):
            raise ResultArtifactError(
                "captured outputs root was replaced after its snapshot"
            )
        root_descriptor = os.open(
            outputs_root.name,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(root_descriptor)
        if _output_directory_identity(opened) != snapshot.root_identity:
            raise ResultArtifactError(
                "captured outputs root was replaced after its snapshot"
            )
        _clear_output_directory_at(root_descriptor)
        _write_output_snapshot_at(
            root_descriptor,
            snapshot,
            runner_response=runner_response,
        )
        current = os.stat(
            outputs_root.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        final = os.fstat(root_descriptor)
        final_parent = os.fstat(parent_descriptor)
        named_parent = outputs_root.parent.lstat()
        if (
            _output_directory_identity(current) != snapshot.root_identity
            or _output_directory_identity(final) != snapshot.root_identity
            or _output_stat_signature(final_parent)
            != _output_stat_signature(opened_parent)
            or _output_stat_signature(named_parent)
            != _output_stat_signature(opened_parent)
        ):
            raise ResultArtifactError(
                "captured outputs root changed during snapshot restoration"
            )
        os.fsync(root_descriptor)
        if repository_identity is not None:
            _verify_output_ancestry(
                parent_descriptor,
                repository_identity,
            )
    except ResultArtifactError:
        raise
    except (OSError, RuntimeError) as error:
        raise ResultArtifactError(
            "captured outputs changed and their actor snapshot could not be restored"
        ) from error
    finally:
        if root_descriptor is not None:
            os.close(root_descriptor)
        if parent_descriptor is not None:
            os.close(parent_descriptor)


def _verify_output_ancestry(
    descriptor: int,
    repository_identity: tuple[int, int],
) -> None:
    current_descriptor: int | None = None
    try:
        current_descriptor = os.dup(descriptor)
        for _ in range(128):
            current = os.fstat(current_descriptor)
            current_identity = (current.st_dev, current.st_ino)
            if current_identity == repository_identity:
                raise ResultArtifactError(
                    "captured outputs moved inside the repository"
                )
            parent_descriptor = os.open(
                "..",
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_descriptor,
            )
            parent = os.fstat(parent_descriptor)
            if (parent.st_dev, parent.st_ino) == current_identity:
                os.close(parent_descriptor)
                return
            os.close(current_descriptor)
            current_descriptor = parent_descriptor
        raise ResultArtifactError(
            "captured output ancestry exceeds the safety limit"
        )
    except ResultArtifactError:
        raise
    except OSError as error:
        raise ResultArtifactError(
            "captured output ancestry cannot be verified safely"
        ) from error
    finally:
        if current_descriptor is not None:
            os.close(current_descriptor)


def _clear_output_directory_at(directory_descriptor: int) -> None:
    try:
        with os.scandir(directory_descriptor) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except OSError as error:
        raise ResultArtifactError(
            "captured outputs could not be cleared safely"
        ) from error
    for entry in entries:
        try:
            observed = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(observed.st_mode) and not stat.S_ISLNK(
                observed.st_mode
            ):
                child_descriptor = _open_stable_output_directory_at(
                    directory_descriptor,
                    entry.name,
                    observed,
                )
                try:
                    _clear_output_directory_at(child_descriptor)
                    _require_unchanged_output_directory_at(
                        directory_descriptor,
                        entry.name,
                        observed,
                        child_descriptor,
                    )
                finally:
                    os.close(child_descriptor)
                os.rmdir(entry.name, dir_fd=directory_descriptor)
            else:
                os.unlink(entry.name, dir_fd=directory_descriptor)
        except ResultArtifactError:
            raise
        except OSError as error:
            raise ResultArtifactError(
                "captured outputs could not be cleared safely"
            ) from error


def _write_output_snapshot_at(
    root_descriptor: int,
    snapshot: CapturedOutputSnapshot,
    *,
    runner_response: str | None,
) -> None:
    opened_directories: dict[tuple[str, ...], int] = {(): root_descriptor}
    owned_descriptors: list[int] = []
    try:
        for relative in sorted(
            snapshot.directories,
            key=lambda path: (len(path.parts), str(path)),
        ):
            parts = tuple(relative.parts)
            parent_descriptor = opened_directories[parts[:-1]]
            os.mkdir(parts[-1], mode=0o700, dir_fd=parent_descriptor)
            child_descriptor = os.open(
                parts[-1],
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=parent_descriptor,
            )
            opened_directories[parts] = child_descriptor
            owned_descriptors.append(child_descriptor)

        files = list(snapshot.files)
        if runner_response is not None:
            files.append(
                CapturedOutputFile(
                    path=PurePosixPath("response.md"),
                    content=runner_response.encode("utf-8"),
                )
            )
        for file in files:
            parts = tuple(file.path.parts)
            parent_descriptor = opened_directories[parts[:-1]]
            descriptor = os.open(
                parts[-1],
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
                0o600,
                dir_fd=parent_descriptor,
            )
            try:
                remaining = memoryview(file.content)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written < 1:
                        raise ResultArtifactError(
                            "captured output snapshot could not be restored"
                        )
                    remaining = remaining[written:]
                os.fsync(descriptor)
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)
        for descriptor in opened_directories.values():
            os.fsync(descriptor)
    except ResultArtifactError:
        raise
    except (OSError, UnicodeError) as error:
        raise ResultArtifactError(
            "captured output snapshot could not be restored"
        ) from error
    finally:
        for descriptor in reversed(owned_descriptors):
            os.close(descriptor)


def freeze_scanned_execution_trace(
    trace: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...] | None:
    """Freeze, scan, parse, and detach one canonical harness trace snapshot."""
    try:
        serialized = _canonical_bounded_actor_trace_bytes(trace)
        rendered = serialized.decode("ascii")
        scan_result = SecretScanBudget(
            maximum_bytes=MAX_EXECUTION_TRACE_BYTES,
        ).scan(rendered, Path("execution_trace.json"))
        if scan_result.transformed:
            return None
        parsed = strict_bounded_json_loads(
            serialized,
            maximum_bytes=MAX_EXECUTION_TRACE_BYTES,
            maximum_nodes=MAX_EXECUTION_TRACE_JSON_NODES,
            maximum_depth=MAX_EXECUTION_TRACE_JSON_DEPTH,
        )
        if not isinstance(parsed, list) or not all(
            isinstance(event, dict) for event in parsed
        ):
            return None
        frozen = _freeze_parsed_trace_json(parsed)
        if not isinstance(frozen, tuple) or not all(
            isinstance(event, ImmutableJsonObject) for event in frozen
        ):
            return None
        return frozen
    except (
        BoundedJsonError,
        SecretScanLimitError,
        UnicodeError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        RuntimeError,
        MemoryError,
        SystemError,
    ):
        return None


def freeze_scanned_actor_trace(
    trace: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...] | None:
    """Backward-compatible actor-specific name for the shared trace boundary."""
    return freeze_scanned_execution_trace(trace)


def _canonical_bounded_actor_trace_bytes(
    trace: Sequence[Mapping[str, object]],
) -> bytes:
    snapshot = _materialize_bounded_actor_trace(trace)
    encoder = json.JSONEncoder(
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    chunks: list[bytes] = []
    consumed = 0
    for chunk in encoder.iterencode(snapshot):
        encoded = chunk.encode("ascii")
        consumed += len(encoded)
        if consumed > MAX_EXECUTION_TRACE_BYTES:
            raise ValueError("actor trace exceeds its canonical byte limit")
        chunks.append(encoded)
    return b"".join(chunks)


def _materialize_bounded_actor_trace(
    trace: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Deep-snapshot trace JSON while bounding structure and scalar width."""
    nodes = 0
    serialized_bytes = 0

    def account(size: int) -> None:
        nonlocal serialized_bytes
        serialized_bytes += size
        if serialized_bytes > MAX_EXECUTION_TRACE_BYTES:
            raise ValueError("actor trace exceeds its canonical byte limit")

    def materialize(value: object, depth: int) -> object:
        nonlocal nodes
        nodes += 1
        if (
            nodes > MAX_EXECUTION_TRACE_JSON_NODES
            or depth > MAX_EXECUTION_TRACE_JSON_DEPTH
        ):
            raise ValueError("actor trace exceeds its structural limits")

        if isinstance(value, Mapping):
            expected_items = len(value)
            if expected_items > MAX_EXECUTION_TRACE_JSON_NODES - nodes:
                raise ValueError("actor trace exceeds its structural limits")
            account(2)
            copied: dict[str, object] = {}
            observed_items = 0
            for key, nested in value.items():
                observed_items += 1
                if (
                    observed_items > expected_items
                    or type(key) is not str
                    or key in copied
                ):
                    raise ValueError("actor trace object is unstable")
                if observed_items > 1:
                    account(1)
                account(_actor_trace_json_string_token_size(key))
                account(1)
                copied[key] = materialize(nested, depth + 1)
            if observed_items != expected_items or len(value) != expected_items:
                raise ValueError("actor trace object changed while preparing")
            return copied

        if isinstance(value, (list, tuple)):
            expected_items = len(value)
            if expected_items > MAX_EXECUTION_TRACE_JSON_NODES - nodes:
                raise ValueError("actor trace exceeds its structural limits")
            account(2 + max(0, expected_items - 1))
            copied_items: list[object] = []
            for nested in value:
                if len(copied_items) >= expected_items:
                    raise ValueError("actor trace array is unstable")
                copied_items.append(materialize(nested, depth + 1))
            if len(copied_items) != expected_items or len(value) != expected_items:
                raise ValueError("actor trace array changed while preparing")
            return copied_items

        if type(value) is str:
            account(_actor_trace_json_string_token_size(value))
            return value
        if value is None:
            account(4)
            return None
        if type(value) is bool:
            account(4 if value else 5)
            return value
        if type(value) is int:
            account(_actor_trace_json_integer_token_size(value))
            return value
        if type(value) is float:
            if not math.isfinite(value):
                raise ValueError("actor trace contains a non-finite number")
            account(len(repr(value)))
            return value
        raise TypeError("actor trace must contain only JSON values")

    snapshot = materialize(trace, 1)
    if not isinstance(snapshot, list) or not all(
        isinstance(event, dict) for event in snapshot
    ):
        raise TypeError("actor trace must be a sequence of JSON objects")
    return snapshot


def _actor_trace_json_string_token_size(value: str) -> int:
    if len(value) + 2 > MAX_EXECUTION_TRACE_BYTES:
        raise ValueError("actor trace scalar exceeds its canonical byte limit")
    size = 2
    for character in value:
        codepoint = ord(character)
        if codepoint in {0x22, 0x5C, 0x08, 0x09, 0x0A, 0x0C, 0x0D}:
            size += 2
        elif codepoint < 0x20 or 0x7F <= codepoint <= 0xFFFF:
            size += 6
        elif codepoint > 0xFFFF:
            size += 12
        else:
            size += 1
        if size > MAX_EXECUTION_TRACE_BYTES:
            raise ValueError("actor trace scalar exceeds its canonical byte limit")
    return size


def _actor_trace_json_integer_token_size(value: int) -> int:
    bit_length = value.bit_length()
    minimum_digits = (
        ((bit_length - 1) * 3_010_299_956) // 10_000_000_000 + 1
        if bit_length
        else 1
    )
    if minimum_digits + int(value < 0) > MAX_EXECUTION_TRACE_BYTES:
        raise ValueError("actor trace scalar exceeds its canonical byte limit")
    return len(str(value))


def _freeze_parsed_trace_json(value: object) -> object:
    if isinstance(value, dict):
        return ImmutableJsonObject(
            {
                key: _freeze_parsed_trace_json(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, list):
        return tuple(_freeze_parsed_trace_json(item) for item in value)
    return value


def _bounded_runtime_text(value: str, maximum_bytes: int) -> str:
    return prepare_durable_sensitive_text(
        value,
        Path("runtime-diagnostic"),
        maximum_durable_bytes=maximum_bytes,
    ).text
