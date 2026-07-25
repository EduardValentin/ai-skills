"""Deterministic repository runtime-test validation."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import signal
import stat
import subprocess
from subprocess import TimeoutExpired
import sys
import tempfile
import threading
import time

from scripts.ai_skills_lib.authored_content import (
    find_static_secret_issues,
    find_static_secret_issues_in_bytes,
    render_safe_diagnostic_text,
)


RUNTIME_TESTS_PATH = Path("tests/runtime")
UNIT_TEST_TIMEOUT_SECONDS = 600
RUNTIME_SUITE_TIMEOUT_SECONDS = 300
RUNTIME_VALIDATION_TIMEOUT_SECONDS = 900
MAXIMUM_TEST_TREE_ENTRIES = 100_000
MAXIMUM_TEST_TREE_BYTES = 256 * 1024 * 1024
MAXIMUM_TEST_TREE_DEPTH = 64
_TEST_SNAPSHOT_DIRECTORIES = (
    "agents",
    "config",
    "schemas",
    "scripts",
    "skills",
    "tests",
)
_TEST_SNAPSHOT_FILES = (
    "AGENTS.md",
    "README.md",
    "requirements.txt",
    "requirements-test.txt",
)
_IGNORED_GENERATED_TEST_ENTRIES = frozenset(
    {"__pycache__", ".pytest_cache"}
)
_TEST_ENVIRONMENT_ALLOWLIST = frozenset(
    {
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "PATH",
        "TERM",
        "TZ",
    }
)
_MAXIMUM_TEST_OUTPUT_BYTES = 4 * 1024 * 1024
_PROCESS_GROUP_CLEANUP_GRACE_SECONDS = 1.0


class RuntimeTestLayoutError(ValueError):
    """The repository runtime-test root violates its directory contract."""


@dataclass(frozen=True)
class BoundedProcessResult:
    """A completed test process with bounded byte output."""

    args: tuple[str, ...]
    returncode: int
    stdout: bytes
    stderr: bytes
    output_limit_exceeded: frozenset[str]


class _BoundedStreamCollector:
    def __init__(
        self,
        stream: object,
        *,
        maximum_bytes: int,
        overflow: threading.Event,
    ) -> None:
        self._stream = stream
        self._maximum_bytes = maximum_bytes
        self._overflow = overflow
        self.data = bytearray()
        self.exceeded = False
        self.error: BaseException | None = None

    def drain(self) -> None:
        try:
            read = getattr(self._stream, "read1", self._stream.read)
            while True:
                chunk = read(64 * 1024)
                if not chunk:
                    break
                remaining = self._maximum_bytes - len(self.data)
                if remaining > 0:
                    self.data.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    self.exceeded = True
                    self._overflow.set()
        except BaseException as error:
            self.error = error
            self._overflow.set()
        finally:
            try:
                self._stream.close()
            except OSError:
                pass


def _signal_test_process(
    process: subprocess.Popen[bytes],
    *,
    process_group_id: int | None,
    force: bool,
) -> None:
    try:
        if process_group_id is not None:
            os.killpg(
                process_group_id,
                signal.SIGKILL if force else signal.SIGTERM,
            )
        elif process.poll() is not None:
            return
        elif force:
            process.kill()
        else:
            process.terminate()
    except ProcessLookupError:
        pass


def _test_process_group_exists(process_group_id: int) -> bool:
    try:
        os.killpg(process_group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _retire_test_process_group(
    process: subprocess.Popen[bytes],
    process_group_id: int | None,
) -> None:
    if process_group_id is None:
        return
    _signal_test_process(
        process,
        process_group_id=process_group_id,
        force=False,
    )
    deadline = (
        time.monotonic() + _PROCESS_GROUP_CLEANUP_GRACE_SECONDS
    )
    while (
        _test_process_group_exists(process_group_id)
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    if _test_process_group_exists(process_group_id):
        _signal_test_process(
            process,
            process_group_id=process_group_id,
            force=True,
        )
        deadline = (
            time.monotonic() + _PROCESS_GROUP_CLEANUP_GRACE_SECONDS
        )
        while (
            _test_process_group_exists(process_group_id)
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
    if _test_process_group_exists(process_group_id):
        raise OSError("test process group did not terminate")


def run_bounded_test_process(
    command: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout: float,
    maximum_output_bytes: int = _MAXIMUM_TEST_OUTPUT_BYTES,
) -> BoundedProcessResult:
    """Run one deterministic test process with capped stdout and stderr."""
    if timeout <= 0:
        raise ValueError("test process timeout must be positive")
    if maximum_output_bytes <= 0:
        raise ValueError("test output limit must be positive")
    arguments = tuple(command)
    if (
        not arguments
        or any(
            not isinstance(argument, str) or not argument or "\x00" in argument
            for argument in arguments
        )
    ):
        raise ValueError("test process command must contain safe arguments")

    process = subprocess.Popen(
        list(arguments),
        cwd=cwd,
        env=dict(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=os.name == "posix",
    )
    process_group_id = process.pid if os.name == "posix" else None
    if process.stdout is None or process.stderr is None:
        _signal_test_process(
            process,
            process_group_id=process_group_id,
            force=True,
        )
        raise OSError("test process output pipes were not created")

    overflow = threading.Event()
    collectors = {
        "stdout": _BoundedStreamCollector(
            process.stdout,
            maximum_bytes=maximum_output_bytes,
            overflow=overflow,
        ),
        "stderr": _BoundedStreamCollector(
            process.stderr,
            maximum_bytes=maximum_output_bytes,
            overflow=overflow,
        ),
    }
    threads = tuple(
        threading.Thread(
            target=collector.drain,
            name=f"ai-skills-test-{stream_name}",
            daemon=True,
        )
        for stream_name, collector in collectors.items()
    )
    for thread in threads:
        thread.start()

    deadline = time.monotonic() + timeout
    termination_started: float | None = None
    timed_out = False
    try:
        while process.poll() is None:
            now = time.monotonic()
            if termination_started is None and overflow.is_set():
                termination_started = now
                _signal_test_process(
                    process,
                    process_group_id=process_group_id,
                    force=False,
                )
            elif termination_started is None and now >= deadline:
                timed_out = True
                termination_started = now
                _signal_test_process(
                    process,
                    process_group_id=process_group_id,
                    force=False,
                )
            elif (
                termination_started is not None
                and now - termination_started >= 1.0
            ):
                _signal_test_process(
                    process,
                    process_group_id=process_group_id,
                    force=True,
                )
            time.sleep(0.01)
        returncode = process.wait()
        _retire_test_process_group(process, process_group_id)
    except BaseException:
        _signal_test_process(
            process,
            process_group_id=process_group_id,
            force=True,
        )
        try:
            process.wait(timeout=1)
        except (OSError, TimeoutExpired):
            pass
        raise
    finally:
        for thread in threads:
            thread.join(timeout=1)

    if any(thread.is_alive() for thread in threads):
        _signal_test_process(
            process,
            process_group_id=process_group_id,
            force=False,
        )
        for thread in threads:
            thread.join(timeout=1)
    if any(thread.is_alive() for thread in threads):
        _signal_test_process(
            process,
            process_group_id=process_group_id,
            force=True,
        )
        for thread in threads:
            thread.join(timeout=1)
    if any(thread.is_alive() for thread in threads):
        raise OSError("test process output pipes did not close")
    collector_error = next(
        (
            collector.error
            for collector in collectors.values()
            if collector.error is not None
        ),
        None,
    )
    if collector_error is not None:
        raise OSError("test process output capture failed") from collector_error

    result = BoundedProcessResult(
        args=arguments,
        returncode=returncode,
        stdout=bytes(collectors["stdout"].data),
        stderr=bytes(collectors["stderr"].data),
        output_limit_exceeded=frozenset(
            stream_name
            for stream_name, collector in collectors.items()
            if collector.exceeded
        ),
    )
    if timed_out:
        raise TimeoutExpired(
            cmd=list(arguments),
            timeout=timeout,
            output=result.stdout,
            stderr=result.stderr,
        )
    return result


def isolated_test_environment(
    state_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a credential-free environment for repository-controlled tests."""
    source = os.environ if environ is None else environ
    home = state_root / "home"
    temporary = state_root / "tmp"
    xdg = home / ".local"
    for directory in (
        home,
        temporary,
        home / ".cache",
        home / ".config",
        xdg / "share",
        xdg / "state",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    environment = {
        name: value
        for name, value in source.items()
        if name in _TEST_ENVIRONMENT_ALLOWLIST
        and isinstance(value, str)
        and "\x00" not in value
    }
    environment.update(
        {
            "PATH": environment.get("PATH", os.defpath),
            "HOME": str(home),
            "TMPDIR": str(temporary),
            "USER": "ai-skills-test",
            "LOGNAME": "ai-skills-test",
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(xdg / "share"),
            "XDG_STATE_HOME": str(xdg / "state"),
            "SSH_AUTH_SOCK": "",
            "GNUPGHOME": str(home / ".gnupg"),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONHASHSEED": "0",
            "NO_COLOR": "1",
        }
    )
    return environment


def report_test_process_output(completed: object, label: str) -> bool:
    """Emit bounded, secret-free captured output and report whether it is safe."""
    label = render_safe_diagnostic_text(label)
    output_is_safe = True
    exceeded_streams = getattr(
        completed,
        "output_limit_exceeded",
        frozenset(),
    )
    for stream_name, destination in (
        ("stdout", sys.stdout),
        ("stderr", sys.stderr),
    ):
        if stream_name in exceeded_streams:
            print(
                f"{label} {stream_name} exceeded the output limit and was quarantined",
                file=destination,
            )
            output_is_safe = False
            continue
        value = getattr(completed, stream_name, b"")
        if isinstance(value, bytes):
            if not value:
                continue
            encoded_size = len(value)
        elif isinstance(value, str):
            if not value:
                continue
            try:
                encoded_size = len(value.encode("utf-8"))
            except (MemoryError, UnicodeError):
                encoded_size = _MAXIMUM_TEST_OUTPUT_BYTES + 1
        else:
            continue
        if encoded_size > _MAXIMUM_TEST_OUTPUT_BYTES:
            print(
                f"{label} {stream_name} exceeded the output limit and was quarantined",
                file=destination,
            )
            output_is_safe = False
            continue
        if isinstance(value, bytes):
            secret_issues = find_static_secret_issues_in_bytes(
                value,
                Path(f"{label}-{stream_name}.txt"),
            )
            rendered = value.decode("utf-8", errors="replace")
        else:
            secret_issues = find_static_secret_issues(
                value,
                Path(f"{label}-{stream_name}.txt"),
            )
            rendered = value
        if secret_issues:
            print(
                f"{label} {stream_name} contained high-confidence secret material "
                "and was quarantined",
                file=destination,
            )
            output_is_safe = False
            continue
        destination.write(rendered)
        destination.flush()
    return output_is_safe


@dataclass
class _TestTreeBudget:
    entries: int = 0
    bytes: int = 0

    def inspect_entry(self) -> None:
        self.entries += 1
        if self.entries > MAXIMUM_TEST_TREE_ENTRIES:
            raise RuntimeTestLayoutError(
                "test repository exceeds the entry limit"
            )

    def inspect_bytes(self, count: int) -> None:
        self.bytes += count
        if self.bytes > MAXIMUM_TEST_TREE_BYTES:
            raise RuntimeTestLayoutError(
                "test repository exceeds the aggregate byte limit"
            )


def require_contained_test_directory(
    root: Path,
    relative_path: Path,
) -> Path:
    """Require every logical test-root component to be a contained directory."""
    if relative_path.is_absolute() or not relative_path.parts or ".." in relative_path.parts:
        raise RuntimeTestLayoutError("test directory must use a contained relative path")
    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
    except OSError as error:
        raise RuntimeTestLayoutError(f"cannot inspect repository root: {error}") from error
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeTestLayoutError("repository root must be a non-symlink directory")

    current = root
    for component in relative_path.parts:
        current /= component
        try:
            metadata = current.lstat()
            resolved = current.resolve(strict=True)
        except OSError as error:
            raise RuntimeTestLayoutError(
                f"{relative_path} must be a non-symlink directory contained in the repository"
            ) from error
        if (
            current.is_symlink()
            or not stat.S_ISDIR(metadata.st_mode)
            or not resolved.is_relative_to(resolved_root)
        ):
            raise RuntimeTestLayoutError(
                f"{relative_path} must be a non-symlink directory contained in the repository"
            )
    return current


def discover_runtime_suites(root: Path) -> tuple[Path, ...]:
    """Return repository runtime-test suite directories in stable order."""
    runtime_root = root / RUNTIME_TESTS_PATH
    if not runtime_root.exists():
        if runtime_root.is_symlink():
            require_contained_test_directory(root, RUNTIME_TESTS_PATH)
        tests_root = root / "tests"
        if tests_root.exists() or tests_root.is_symlink():
            require_contained_test_directory(root, Path("tests"))
        return ()
    runtime_root = require_contained_test_directory(root, RUNTIME_TESTS_PATH)

    budget = _TestTreeBudget()
    suites: list[Path] = []
    for entry in _bounded_directory_entries(runtime_root, budget):
        if entry.is_symlink() or not entry.is_dir() or entry.name.startswith("."):
            raise RuntimeTestLayoutError(
                f"unsupported tests/runtime entry: {entry.name}"
            )
        test_modules = _validate_runtime_suite_tree(entry, budget)
        if not test_modules:
            raise RuntimeTestLayoutError(
                f"runtime suite '{entry.name}' has no test*.py modules"
            )
        suites.append(entry)
    if not suites:
        raise RuntimeTestLayoutError("tests/runtime contains no runtime test suites")
    return tuple(suites)


def _validate_runtime_suite_tree(
    suite: Path,
    budget: _TestTreeBudget,
) -> tuple[Path, ...]:
    test_modules: list[Path] = []
    pending = [(suite, 0)]
    while pending:
        directory, depth = pending.pop()
        entries = _bounded_scandir(directory, budget)
        for entry in entries:
            relative = Path(entry.path).relative_to(suite)
            if entry.name.startswith("."):
                raise RuntimeTestLayoutError(
                    f"unsupported hidden runtime entry: {suite.name}/{relative}"
                )
            if entry.is_symlink():
                raise RuntimeTestLayoutError(
                    f"unsupported runtime symlink: {suite.name}/{relative}"
                )
            if entry.is_dir(follow_symlinks=False):
                if depth >= MAXIMUM_TEST_TREE_DEPTH:
                    raise RuntimeTestLayoutError(
                        f"runtime suite '{suite.name}' exceeds the depth limit"
                    )
                pending.append((Path(entry.path), depth + 1))
                continue
            if not entry.is_file(follow_symlinks=False):
                raise RuntimeTestLayoutError(
                    f"unsupported runtime special file: {suite.name}/{relative}"
                )
            path = Path(entry.path)
            if entry.name.startswith("test") and path.suffix == ".py":
                test_modules.append(path)
    return tuple(sorted(test_modules))


def _bounded_directory_entries(
    directory: Path,
    budget: _TestTreeBudget,
) -> tuple[Path, ...]:
    return tuple(
        Path(entry.path)
        for entry in _bounded_scandir(directory, budget)
    )


def _bounded_scandir(
    directory: Path | int,
    budget: _TestTreeBudget,
) -> tuple[os.DirEntry[str], ...]:
    entries: list[os.DirEntry[str]] = []
    try:
        with os.scandir(directory) as iterator:
            for entry in iterator:
                if entry.name in _IGNORED_GENERATED_TEST_ENTRIES:
                    budget.inspect_entry()
                    if entry.is_symlink() or not entry.is_dir(
                        follow_symlinks=False
                    ):
                        raise RuntimeTestLayoutError(
                            "generated runtime cache entry must be a "
                            f"non-symlink directory: {entry.name}"
                        )
                    _require_no_test_modules_in_generated_cache(
                        directory,
                        entry,
                        budget,
                    )
                    continue
                budget.inspect_entry()
                entries.append(entry)
    except OSError as error:
        raise RuntimeTestLayoutError(
            "cannot inspect deterministic test tree"
        ) from error
    return tuple(sorted(entries, key=lambda entry: entry.name))


def _require_no_test_modules_in_generated_cache(
    parent: Path | int,
    cache_entry: os.DirEntry[str],
    budget: _TestTreeBudget,
) -> None:
    observed = cache_entry.stat(follow_symlinks=False)
    cache_descriptor: int | None = None
    try:
        if isinstance(parent, int):
            cache_descriptor = _open_stable_directory_at(
                parent,
                cache_entry.name,
                observed,
            )
        else:
            cache_descriptor = os.open(
                cache_entry.path,
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            if _stable_metadata(os.fstat(cache_descriptor)) != _stable_metadata(
                observed
            ):
                raise RuntimeTestLayoutError(
                    "generated test cache changed while opening"
                )
        _scan_generated_cache_descriptor(
            cache_descriptor,
            budget,
            depth=0,
        )
        if isinstance(parent, int):
            _require_unchanged_entry(
                parent,
                cache_entry.name,
                observed,
                cache_descriptor,
            )
        elif _stable_metadata(
            cache_entry.stat(follow_symlinks=False)
        ) != _stable_metadata(observed):
            raise RuntimeTestLayoutError(
                "generated test cache changed while being inspected"
            )
    except OSError as error:
        raise RuntimeTestLayoutError(
            "cannot inspect generated test cache"
        ) from error
    finally:
        if cache_descriptor is not None:
            os.close(cache_descriptor)


def _scan_generated_cache_descriptor(
    directory_descriptor: int,
    budget: _TestTreeBudget,
    *,
    depth: int,
) -> None:
    try:
        with os.scandir(directory_descriptor) as iterator:
            entries = tuple(iterator)
    except OSError as error:
        raise RuntimeTestLayoutError(
            "cannot inspect generated test cache"
        ) from error
    for entry in entries:
        budget.inspect_entry()
        path = Path(entry.name)
        if (
            entry.name.startswith("test")
            and path.suffix == ".py"
            and not entry.is_dir(follow_symlinks=False)
        ):
            raise RuntimeTestLayoutError(
                "generated test cache contains a test*.py module"
            )
        if (
            entry.is_dir(follow_symlinks=False)
            and not entry.is_symlink()
        ):
            if depth >= MAXIMUM_TEST_TREE_DEPTH:
                raise RuntimeTestLayoutError(
                    "generated test cache exceeds the depth limit"
                )
            observed = entry.stat(follow_symlinks=False)
            child_descriptor: int | None = None
            try:
                child_descriptor = _open_stable_directory_at(
                    directory_descriptor,
                    entry.name,
                    observed,
                )
                _scan_generated_cache_descriptor(
                    child_descriptor,
                    budget,
                    depth=depth + 1,
                )
                _require_unchanged_entry(
                    directory_descriptor,
                    entry.name,
                    observed,
                    child_descriptor,
                )
            finally:
                if child_descriptor is not None:
                    os.close(child_descriptor)


@contextmanager
def materialized_test_repository(root: Path) -> Iterator[Path]:
    """Copy executable test inputs through descriptor-anchored stable reads."""
    try:
        resolved_root = root.resolve(strict=True)
        root_metadata = root.lstat()
    except OSError as error:
        raise RuntimeTestLayoutError(
            "cannot inspect repository for deterministic tests"
        ) from error
    if root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeTestLayoutError(
            "repository root must be a non-symlink directory"
        )

    descriptor: int | None = None
    try:
        descriptor = os.open(
            resolved_root,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if _stable_metadata(opened) != _stable_metadata(root_metadata):
            raise RuntimeTestLayoutError(
                "repository changed while preparing deterministic tests"
            )
        with tempfile.TemporaryDirectory(
            prefix="ai-skills-test-snapshot-"
        ) as directory:
            snapshot = Path(directory) / "repository"
            snapshot.mkdir(mode=0o700)
            budget = _TestTreeBudget()
            for name in _TEST_SNAPSHOT_DIRECTORIES:
                _copy_optional_snapshot_entry(
                    descriptor,
                    name,
                    snapshot / name,
                    budget,
                    expect_directory=True,
                    repository_root=resolved_root,
                    source_path=resolved_root / name,
                    materialize_symlinks=name == "skills",
                )
            for name in _TEST_SNAPSHOT_FILES:
                _copy_optional_snapshot_entry(
                    descriptor,
                    name,
                    snapshot / name,
                    budget,
                    expect_directory=False,
                    repository_root=resolved_root,
                    source_path=resolved_root / name,
                    materialize_symlinks=False,
                )
            final = os.fstat(descriptor)
            named_final = resolved_root.lstat()
            if (
                _stable_metadata(final) != _stable_metadata(opened)
                or _stable_metadata(named_final) != _stable_metadata(opened)
            ):
                raise RuntimeTestLayoutError(
                    "repository changed while preparing deterministic tests"
                )
            yield snapshot
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _copy_optional_snapshot_entry(
    root_descriptor: int,
    name: str,
    destination: Path,
    budget: _TestTreeBudget,
    *,
    expect_directory: bool,
    repository_root: Path,
    source_path: Path,
    materialize_symlinks: bool,
) -> None:
    try:
        observed = os.stat(
            name,
            dir_fd=root_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return
    except OSError as error:
        raise RuntimeTestLayoutError(
            "cannot inspect deterministic test input"
        ) from error
    budget.inspect_entry()
    if expect_directory:
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise RuntimeTestLayoutError(
                f"deterministic test input {name} must be a non-symlink "
                "directory contained in the repository"
            )
        destination.mkdir()
        child_descriptor = _open_stable_directory_at(
            root_descriptor,
            name,
            observed,
        )
        try:
            _copy_snapshot_directory(
            child_descriptor,
            destination,
            budget,
            depth=0,
            repository_root=repository_root,
            source_path=source_path,
            materialize_symlinks=materialize_symlinks,
            active_directories=set(),
        )
            _require_unchanged_entry(
                root_descriptor,
                name,
                observed,
                child_descriptor,
            )
        finally:
            os.close(child_descriptor)
        return
    if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
        raise RuntimeTestLayoutError(
            f"deterministic test input {name} must be a non-symlink regular file"
        )
    content = _read_stable_file_at(root_descriptor, name, observed, budget)
    destination.write_bytes(content)
    destination.chmod(_snapshot_file_mode(observed.st_mode))


def _copy_snapshot_directory(
    source_descriptor: int,
    destination: Path,
    budget: _TestTreeBudget,
    *,
    depth: int,
    repository_root: Path,
    source_path: Path,
    materialize_symlinks: bool,
    active_directories: set[tuple[int, int]],
) -> None:
    if depth > MAXIMUM_TEST_TREE_DEPTH:
        raise RuntimeTestLayoutError(
            "deterministic test input exceeds the depth limit"
        )
    directory_identity = (
        os.fstat(source_descriptor).st_dev,
        os.fstat(source_descriptor).st_ino,
    )
    if directory_identity in active_directories:
        raise RuntimeTestLayoutError(
            "deterministic test input contains a directory cycle"
        )
    active_directories.add(directory_identity)
    try:
        entries = _bounded_scandir(source_descriptor, budget)
        for entry in entries:
            observed = entry.stat(follow_symlinks=False)
            target = destination / entry.name
            logical_source = source_path / entry.name
            if stat.S_ISLNK(observed.st_mode):
                if not materialize_symlinks:
                    raise RuntimeTestLayoutError(
                        "deterministic test inputs must be a non-symlink directory "
                        "or regular file contained in the repository"
                    )
                _materialize_contained_snapshot_symlink(
                    source_descriptor,
                    entry.name,
                    observed,
                    logical_source,
                    target,
                    budget,
                    depth=depth,
                    repository_root=repository_root,
                    active_directories=active_directories,
                )
                continue
            if stat.S_ISDIR(observed.st_mode):
                target.mkdir()
                child_descriptor = _open_stable_directory_at(
                    source_descriptor,
                    entry.name,
                    observed,
                )
                try:
                    _copy_snapshot_directory(
                        child_descriptor,
                        target,
                        budget,
                        depth=depth + 1,
                        repository_root=repository_root,
                        source_path=logical_source,
                        materialize_symlinks=materialize_symlinks,
                        active_directories=active_directories,
                    )
                    _require_unchanged_entry(
                        source_descriptor,
                        entry.name,
                        observed,
                        child_descriptor,
                    )
                finally:
                    os.close(child_descriptor)
                continue
            if not stat.S_ISREG(observed.st_mode):
                raise RuntimeTestLayoutError(
                    "deterministic test inputs cannot contain special files"
                )
            content = _read_stable_file_at(
                source_descriptor,
                entry.name,
                observed,
                budget,
            )
            target.write_bytes(content)
            target.chmod(_snapshot_file_mode(observed.st_mode))
    finally:
        active_directories.remove(directory_identity)


def _materialize_contained_snapshot_symlink(
    parent_descriptor: int,
    name: str,
    link_metadata: os.stat_result,
    logical_source: Path,
    destination: Path,
    budget: _TestTreeBudget,
    *,
    depth: int,
    repository_root: Path,
    active_directories: set[tuple[int, int]],
) -> None:
    try:
        resolved = logical_source.resolve(strict=True)
        target_metadata = os.stat(name, dir_fd=parent_descriptor)
    except OSError as error:
        raise RuntimeTestLayoutError(
            "deterministic test symlink cannot be resolved safely"
        ) from error
    if not resolved.is_relative_to(repository_root):
        raise RuntimeTestLayoutError(
            "deterministic test symlink escapes the repository"
        )

    if stat.S_ISDIR(target_metadata.st_mode):
        if depth >= MAXIMUM_TEST_TREE_DEPTH:
            raise RuntimeTestLayoutError(
                "deterministic test input exceeds the depth limit"
            )
        child_descriptor: int | None = None
        try:
            child_descriptor = os.open(
                resolved,
                os.O_RDONLY
                | os.O_DIRECTORY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0),
            )
            opened = os.fstat(child_descriptor)
            if _stable_metadata(opened) != _stable_metadata(target_metadata):
                raise RuntimeTestLayoutError(
                    "deterministic test symlink target changed while opening"
                )
            destination.mkdir()
            _copy_snapshot_directory(
                child_descriptor,
                destination,
                budget,
                depth=depth + 1,
                repository_root=repository_root,
                source_path=resolved,
                materialize_symlinks=True,
                active_directories=active_directories,
            )
            _require_unchanged_snapshot_symlink(
                parent_descriptor,
                name,
                link_metadata,
                target_metadata,
                child_descriptor,
            )
        finally:
            if child_descriptor is not None:
                os.close(child_descriptor)
        return

    if not stat.S_ISREG(target_metadata.st_mode):
        raise RuntimeTestLayoutError(
            "deterministic test symlink target must be a regular file or directory"
        )
    target_parent_descriptor: int | None = None
    try:
        target_parent_descriptor = os.open(
            resolved.parent,
            os.O_RDONLY
            | os.O_DIRECTORY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        content = _read_stable_file_at(
            target_parent_descriptor,
            resolved.name,
            target_metadata,
            budget,
        )
        _require_unchanged_snapshot_symlink(
            parent_descriptor,
            name,
            link_metadata,
            target_metadata,
            None,
        )
    except OSError as error:
        raise RuntimeTestLayoutError(
            "deterministic test symlink target cannot be read safely"
        ) from error
    finally:
        if target_parent_descriptor is not None:
            os.close(target_parent_descriptor)
    destination.write_bytes(content)
    destination.chmod(_snapshot_file_mode(target_metadata.st_mode))


def _require_unchanged_snapshot_symlink(
    parent_descriptor: int,
    name: str,
    link_metadata: os.stat_result,
    target_metadata: os.stat_result,
    target_descriptor: int | None,
) -> None:
    try:
        current_link = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        current_target = os.stat(name, dir_fd=parent_descriptor)
        if (
            _stable_metadata(current_link) != _stable_metadata(link_metadata)
            or _stable_metadata(current_target)
            != _stable_metadata(target_metadata)
            or (
                target_descriptor is not None
                and _stable_metadata(os.fstat(target_descriptor))
                != _stable_metadata(target_metadata)
            )
        ):
            raise RuntimeTestLayoutError(
                "deterministic test symlink changed while being copied"
            )
    except RuntimeTestLayoutError:
        raise
    except OSError as error:
        raise RuntimeTestLayoutError(
            "deterministic test symlink changed while being copied"
        ) from error


def _open_stable_directory_at(
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
        raise RuntimeTestLayoutError(
            "deterministic test directory changed while being opened"
        ) from error
    if _stable_metadata(opened) != _stable_metadata(observed):
        os.close(descriptor)
        raise RuntimeTestLayoutError(
            "deterministic test directory changed while being opened"
        )
    return descriptor


def _read_stable_file_at(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
    budget: _TestTreeBudget,
) -> bytes:
    if observed.st_size < 0:
        raise RuntimeTestLayoutError(
            "deterministic test file has an invalid size"
        )
    budget.inspect_bytes(observed.st_size)
    descriptor: int | None = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        if _stable_metadata(opened) != _stable_metadata(observed):
            raise RuntimeTestLayoutError(
                "deterministic test file changed while being opened"
            )
        chunks: list[bytes] = []
        consumed = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > observed.st_size:
                raise RuntimeTestLayoutError(
                    "deterministic test file changed while being read"
                )
            chunks.append(chunk)
        final = os.fstat(descriptor)
        named_final = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if (
            consumed != observed.st_size
            or _stable_metadata(final) != _stable_metadata(observed)
            or _stable_metadata(named_final) != _stable_metadata(observed)
        ):
            raise RuntimeTestLayoutError(
                "deterministic test file changed while being read"
            )
        return b"".join(chunks)
    except RuntimeTestLayoutError:
        raise
    except OSError as error:
        raise RuntimeTestLayoutError(
            "deterministic test file cannot be read safely"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _require_unchanged_entry(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
    child_descriptor: int,
) -> None:
    final = os.fstat(child_descriptor)
    named_final = os.stat(
        name,
        dir_fd=parent_descriptor,
        follow_symlinks=False,
    )
    if (
        _stable_metadata(final) != _stable_metadata(observed)
        or _stable_metadata(named_final) != _stable_metadata(observed)
    ):
        raise RuntimeTestLayoutError(
            "deterministic test directory changed while being copied"
        )


def _stable_metadata(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _snapshot_file_mode(mode: int) -> int:
    return 0o755 if mode & 0o111 else 0o644


def run_runtime_validation(root: Path) -> int:
    """Run deterministic repository runtime tests."""
    try:
        with materialized_test_repository(root) as discovery_root:
            suite_paths = tuple(
                suite.relative_to(discovery_root)
                for suite in discover_runtime_suites(discovery_root)
            )
        return _run_runtime_validation_suites(root, suite_paths)
    except (OSError, RuntimeTestLayoutError) as error:
        print(
            "validate runtime: FAILED "
            f"({render_safe_diagnostic_text(str(error))})"
        )
        return 1


def _run_runtime_validation_suites(
    root: Path,
    suite_paths: tuple[Path, ...],
) -> int:
    if not suite_paths:
        print("validate runtime: OK (no runtime test suites found)")
        return 0

    failed_suites: list[str] = []
    deadline = time.monotonic() + RUNTIME_VALIDATION_TIMEOUT_SECONDS
    for index, relative_suite in enumerate(suite_paths):
        safe_suite_name = render_safe_diagnostic_text(relative_suite.name)
        print(f"\nRuntime suite: {safe_suite_name}", flush=True)
        with materialized_test_repository(root) as snapshot_root:
            current_suite_paths = tuple(
                suite.relative_to(snapshot_root)
                for suite in discover_runtime_suites(snapshot_root)
            )
            if current_suite_paths != suite_paths:
                raise RuntimeTestLayoutError(
                    "runtime test suite layout changed during validation"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                unstarted = suite_paths[index:]
                failed_suites.extend(
                    candidate.name for candidate in unstarted
                )
                print(
                    "Runtime validation: FAILED "
                    f"(exceeded {RUNTIME_VALIDATION_TIMEOUT_SECONDS}s aggregate timeout; "
                    f"{len(unstarted)} suites were not started)"
                )
                break
            suite = snapshot_root / relative_suite
            suite_test_modules = tuple(
                path.relative_to(snapshot_root)
                for path in _validate_runtime_suite_tree(
                    suite,
                    _TestTreeBudget(),
                )
            )
            try:
                with tempfile.TemporaryDirectory(
                    prefix="ai-skills-runtime-suite-"
                ) as state:
                    completed = run_bounded_test_process(
                        [
                            sys.executable,
                            "-I",
                            "-m",
                            "pytest",
                            "-ra",
                            "--override-ini=python_files=test*.py",
                            *(str(path) for path in suite_test_modules),
                        ],
                        cwd=snapshot_root,
                        env=isolated_test_environment(Path(state)),
                        timeout=min(RUNTIME_SUITE_TIMEOUT_SECONDS, remaining),
                    )
                    output_is_safe = report_test_process_output(
                        completed,
                        f"Runtime suite {safe_suite_name}",
                    )
            except TimeoutExpired:
                failed_suites.append(suite.name)
                if remaining < RUNTIME_SUITE_TIMEOUT_SECONDS:
                    unstarted = suite_paths[index + 1 :]
                    failed_suites.extend(candidate.name for candidate in unstarted)
                    print(
                        f"Runtime suite {safe_suite_name}: FAILED "
                        f"(aggregate runtime validation exceeded "
                        f"{RUNTIME_VALIDATION_TIMEOUT_SECONDS}s timeout)"
                    )
                    break
                print(
                    f"Runtime suite {safe_suite_name}: FAILED "
                    f"(exceeded {RUNTIME_SUITE_TIMEOUT_SECONDS}s timeout)"
                )
                continue
            except OSError as error:
                failed_suites.append(suite.name)
                print(
                    f"Runtime suite {safe_suite_name}: FAILED "
                    f"({render_safe_diagnostic_text(str(error))})"
                )
                continue
            if completed.returncode == 0 and output_is_safe:
                print(f"Runtime suite {safe_suite_name}: OK")
            else:
                failed_suites.append(suite.name)
                if completed.returncode == 0:
                    print(
                        f"Runtime suite {safe_suite_name}: FAILED "
                        "(captured output was quarantined)"
                    )
                    continue
                print(
                    f"Runtime suite {safe_suite_name}: FAILED "
                    f"(pytest exit {completed.returncode})"
                )

    if failed_suites:
        print(
            "validate runtime: FAILED "
            f"({len(failed_suites)} of {len(suite_paths)} suites failed)"
        )
        return 1
    print(f"validate runtime: OK ({len(suite_paths)} suites passed)")
    return 0
