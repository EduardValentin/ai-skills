"""Shared containment and high-confidence secret checks for authored files."""

from __future__ import annotations

import ast
import codecs
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import tokenize

from scripts.ai_skills_lib.secret_patterns import (
    PRIVATE_KEY_LABEL_PATTERN,
    SECRET_PATTERNS,
    SecretMatch,
    SecretPattern,
)


_PURE_REFERENCE_PATTERN = re.compile(
    r"(?:"
    r"\$[A-Za-z_][A-Za-z0-9_]*"
    r"|\$\{[A-Za-z_][A-Za-z0-9_]*\}"
    r"|os\.environ\[\s*[\"'][A-Za-z_][A-Za-z0-9_]*[\"']\s*\]"
    r"|process\.env\.[A-Za-z_][A-Za-z0-9_]*"
    r"|\{\{\s*[A-Za-z_][A-Za-z0-9_]*\s*\}\}"
    r")\Z"
)
_PYTHON_FSTRING_AUTHORIZATION_PATTERN = re.compile(
    r"f(?P<quote>[\"'])(?:Bearer|Basic)[ \t]+"
    r"\{[A-Za-z_][A-Za-z0-9_]*\}(?P=quote)[ \t]*[,}]?\Z",
    re.IGNORECASE,
)
_FORMAT_REFERENCE_PATTERN = re.compile(r"\{[A-Za-z_][A-Za-z0-9_]*\}\Z")
_FAKE_VALUE_PATTERN = re.compile(r"FAKE_[A-Za-z0-9][A-Za-z0-9_.:/-]*\Z")
_MAX_SAFE_PYTHON_REFERENCE_NODES = 4096
_MAX_SAFE_PYTHON_REFERENCE_DEPTH = 128
_MAX_PYTHON_SOURCE_NODES = 100_000
_MAX_PYTHON_DECODER_EVALUATION_STEPS = 100_000
_MAX_PYTHON_ASSIGNMENT_RECOVERY_BYTES = 1024 * 1024
_MAX_PYTHON_ASSIGNMENT_RECOVERY_TOKENS = 100_000
_SAFE_PYTHON_CALL_LITERALS = frozenset(("ascii", "utf-8", "utf8"))
_SHELL_PURE_REFERENCE_PATTERN = re.compile(
    r"(?:"
    r"\$[A-Za-z_][A-Za-z0-9_]*"
    r"|\$\{[A-Za-z_][A-Za-z0-9_]*\}"
    r")\Z"
)
_SHELL_LOOKUP_REFERENCE_PATTERN = re.compile(
    r"(?:"
    r"\$[A-Za-z_][A-Za-z0-9_]*"
    r"|\$\{[A-Za-z_][A-Za-z0-9_]*\}"
    r")(?:[A-Za-z0-9._:/-]*)\Z"
)
_SHELL_LOOKUP_KEY_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_SAFE_SHELL_PRINTF_FORMATS = frozenset(("%s", "%s\n"))
_BUNDLED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<target>(?:scripts|references|assets)/"
    r"[A-Za-z0-9._/-]+)(?![A-Za-z0-9._/\\-])"
)
_QUOTED_BUNDLED_PATH_PATTERN = re.compile(
    r"`(?P<target>(?:scripts|references|assets)/[^`\r\n]+)`"
)
_WINDOWS_ABSOLUTE_BUNDLED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?P<target>[A-Za-z]:(?:[/\\]+)?"
    r"(?:[A-Za-z0-9._~-]+[/\\]+)*(?:scripts|references|assets)"
    r"[/\\]+[^\s<>\"'`]+)"
)
_POSIX_ABSOLUTE_BUNDLED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_:/>\]}])"
    r"(?P<target>/(?:[A-Za-z0-9._~-]+/)*(?:scripts|references|assets)"
    r"/[^\s<>\"'`]+)"
)
_URI_PATTERN = re.compile(
    r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):/{2}[^\s<>\"']+"
)
_FILE_URI_PATTERN = re.compile(r"\bfile:[^\s<>\"']+", re.IGNORECASE)
_LOCAL_EVAL_RUNTIME_REFERENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:(?:\.{1,2}[/\\])*)evals[/\\]",
    re.IGNORECASE,
)
_PRIVATE_KEY_MARKER_PATTERN = re.compile(
    rf"-----(?P<direction>BEGIN|END) "
    rf"(?P<label>{PRIVATE_KEY_LABEL_PATTERN})-----"
)
_QUOTED_SECRET_VALUE_TERMINATOR = r"(?=\Z|[\s,;.!?`>|)\]}])"
_JSON_QUOTED_SECRET_VALUE = (
    r'"(?:\\(?:["\\/bfnrt]|u[0-9A-Fa-f]{4})|[^"\\\r\n])*"'
    + _QUOTED_SECRET_VALUE_TERMINATOR
)
_SINGLE_QUOTED_SECRET_VALUE = (
    r"'(?:\\[^\r\n]|[^'\\\r\n])*'" + _QUOTED_SECRET_VALUE_TERMINATOR
)
_UNQUOTED_BEARER_SECRET_VALUE = (
    r'(?:\\"(?![ \t]*[,}\]])|\\(?:[\\/bfnrt]|u[0-9A-Fa-f]{4})|'
    r'[^\s,;"\'\\])+'
)
_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r"(?im)(?<![A-Za-z0-9_-])[\"']?(?:authorization|proxy-authorization)[\"']?"
    rf"[ \t]*:[ \t]*(?P<value>{_JSON_QUOTED_SECRET_VALUE}|"
    rf"{_SINGLE_QUOTED_SECRET_VALUE}|[^\r\n]*)"
)
_COOKIE_HEADER_PATTERN = re.compile(
    r"(?im)(?<![A-Za-z0-9_-])[\"']?(?P<name>cookie|set-cookie)[\"']?"
    rf"[ \t]*:[ \t]*(?P<value>{_JSON_QUOTED_SECRET_VALUE}|"
    rf"{_SINGLE_QUOTED_SECRET_VALUE}|[^\r\n]*)"
)
_BEARER_VALUE_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9_-])bearer[ \t]+"
    rf"(?P<value>{_JSON_QUOTED_SECRET_VALUE}|{_SINGLE_QUOTED_SECRET_VALUE}|"
    rf"{_UNQUOTED_BEARER_SECRET_VALUE}|[^\s,;\r\n]+)"
)
_ESCAPED_AUTHORIZATION_HEADER_PATTERN = re.compile(
    r'(?i)\\"(?:authorization|proxy-authorization)\\"[ \t]*:'
)
_ESCAPED_COOKIE_HEADER_PATTERN = re.compile(
    r'(?i)\\"(?:cookie|set-cookie)\\"[ \t]*:'
)
_AUTHORIZATION_HEADER_SECRET = SecretPattern(
    name="authorization-value",
    category="authorization",
    confidence="high",
    regex=_AUTHORIZATION_HEADER_PATTERN,
    value_group="value",
)
_COOKIE_HEADER_SECRET = SecretPattern(
    name="cookie-value",
    category="cookie",
    confidence="high",
    regex=_COOKIE_HEADER_PATTERN,
    value_group="value",
)
_BEARER_VALUE_SECRET = SecretPattern(
    name="bearer-token",
    category="access-token",
    confidence="high",
    regex=_BEARER_VALUE_PATTERN,
    value_group="value",
)
_ESCAPED_AUTHORIZATION_HEADER_SECRET = SecretPattern(
    name="escaped-authorization-context",
    category="authorization",
    confidence="high",
    regex=_ESCAPED_AUTHORIZATION_HEADER_PATTERN,
)
_ESCAPED_COOKIE_HEADER_SECRET = SecretPattern(
    name="escaped-cookie-context",
    category="cookie",
    confidence="high",
    regex=_ESCAPED_COOKIE_HEADER_PATTERN,
)
_RUNTIME_SECRET_PATTERNS = (
    _AUTHORIZATION_HEADER_SECRET,
    _COOKIE_HEADER_SECRET,
    _ESCAPED_AUTHORIZATION_HEADER_SECRET,
    _ESCAPED_COOKIE_HEADER_SECRET,
    _BEARER_VALUE_SECRET,
)
_AUTHORED_READ_CHUNK_BYTES = 64 * 1024


class AuthoredContentReadError(ValueError):
    """Raised when an authored file cannot be read through a stable boundary."""


class AuthoredContentTooLarge(AuthoredContentReadError):
    """Raised when an authored file exceeds its caller-owned byte limit."""


class AuthoredContentComplexityError(ValueError):
    """Raised when authored content exceeds a bounded inspection budget."""


class AuthoredRepositoryBudgetExceeded(ValueError):
    """Raised when one repository validation exceeds its shared resource budget."""


@dataclass
class AuthoredRepositoryBudget:
    """Entry and byte budget shared across one deterministic repository pass."""

    maximum_entries: int = 100_000
    maximum_bytes: int = 256 * 1024 * 1024
    inspected_entries: int = 0
    inspected_bytes: int = 0

    def __post_init__(self) -> None:
        if self.maximum_entries <= 0 or self.maximum_bytes <= 0:
            raise ValueError("authored repository limits must be positive")

    def inspect_entry(self) -> None:
        self.inspected_entries += 1
        if self.inspected_entries > self.maximum_entries:
            raise AuthoredRepositoryBudgetExceeded(
                "repository exceeds the authored entry inspection limit"
            )

    def inspect_bytes(self, byte_count: int) -> None:
        if byte_count < 0:
            raise ValueError("authored byte count cannot be negative")
        self.inspected_bytes += byte_count
        if self.inspected_bytes > self.maximum_bytes:
            raise AuthoredRepositoryBudgetExceeded(
                "repository exceeds the aggregate authored byte inspection limit"
            )


DEFAULT_MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
DEFAULT_MAXIMUM_JSON_NODES = 100_000
DEFAULT_MAXIMUM_JSON_DEPTH = 64
DEFAULT_MAXIMUM_SECRET_SCAN_BYTES = 8 * 1024 * 1024
DEFAULT_MAXIMUM_SECRET_FINDINGS = 64
SENSITIVE_TEXT_REDACTION = "[REDACTED]"
_DIAGNOSTIC_SOURCE = Path("validation-diagnostic")
SENSITIVE_TEXT_QUARANTINE = "[QUARANTINED: sensitive content could not be preserved]"


@dataclass(frozen=True)
class AuthoredFile:
    logical_path: Path
    resolved_path: Path


@dataclass(frozen=True)
class AuthoredTreeEntry:
    """One entry classified during a descriptor-stable authored-tree snapshot."""

    logical_path: Path
    mode: int
    metadata: tuple[int, ...]
    resolved_path: Path | None
    target_mode: int | None
    target_metadata: tuple[int, ...] | None
    child_count: int | None
    symlink_error: str | None = None

    @property
    def is_symlink(self) -> bool:
        return stat.S_ISLNK(self.mode)

    @property
    def is_directory(self) -> bool:
        return not self.is_symlink and stat.S_ISDIR(self.mode)

    @property
    def is_regular_file(self) -> bool:
        return not self.is_symlink and stat.S_ISREG(self.mode)


@dataclass(frozen=True)
class StrictPathResolution:
    resolved_path: Path | None
    error: OSError | RuntimeError | None


class BoundedJsonError(ValueError):
    """JSON input is invalid or exceeds the shared parser resource policy."""


class JsonPreflightError(ValueError):
    """Strict JSON tokenization failed before object graph construction."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


class SecretScanLimitError(RuntimeError):
    """Secret scanning cannot complete within its declared global budget."""


@dataclass(frozen=True)
class SecretScanResult:
    findings: tuple[SecretMatch, ...]
    minimum_finding_count: int
    finding_count_truncated: bool
    boundary_uncertain: bool
    durable_text: str
    transformed: bool


@dataclass(frozen=True)
class DurableTextResult:
    """Bounded text plus whether the source had to be changed for durability."""

    text: str
    transformed: bool
    minimum_finding_count: int
    finding_count_truncated: bool
    boundary_uncertain: bool
    scan_incomplete: bool
    size_truncated: bool


@dataclass(frozen=True)
class _SensitiveCandidate:
    start: int
    end: int
    pattern: SecretPattern


@dataclass
class SecretScanBudget:
    """One byte and finding budget shared across a complete evidence set."""

    maximum_bytes: int = DEFAULT_MAXIMUM_SECRET_SCAN_BYTES
    maximum_findings: int = DEFAULT_MAXIMUM_SECRET_FINDINGS
    scanned_bytes: int = 0
    retained_findings: int = 0
    finding_limit_reached: bool = False
    _decoder_steps: list[int] = field(
        default_factory=lambda: [_MAX_PYTHON_DECODER_EVALUATION_STEPS],
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if self.maximum_bytes <= 0 or self.maximum_findings <= 0:
            raise ValueError("secret scan limits must be positive")

    def scan(self, text: str, source: Path) -> SecretScanResult:
        if self.finding_limit_reached:
            raise SecretScanLimitError("secret scan finding limit was already reached")
        try:
            size = len(text.encode("utf-8"))
        except (UnicodeEncodeError, MemoryError) as error:
            raise SecretScanLimitError("secret scan input could not be bounded") from error
        if self.scanned_bytes + size > self.maximum_bytes:
            raise SecretScanLimitError("secret scan exceeds the global byte limit")
        self.scanned_bytes += size
        remaining = self.maximum_findings - self.retained_findings
        if remaining == 0:
            probe = scan_static_secret_issues(
                text,
                source,
                maximum_findings=1,
                _decoder_steps=self._decoder_steps,
            )
            if probe.minimum_finding_count:
                self.finding_limit_reached = True
                return SecretScanResult(
                    findings=(),
                    minimum_finding_count=probe.minimum_finding_count,
                    finding_count_truncated=True,
                    boundary_uncertain=probe.boundary_uncertain,
                    durable_text=SENSITIVE_TEXT_QUARANTINE,
                    transformed=True,
                )
            return probe
        result = scan_static_secret_issues(
            text,
            source,
            maximum_findings=remaining,
            _decoder_steps=self._decoder_steps,
        )
        self.retained_findings += len(result.findings)
        self.finding_limit_reached = result.finding_count_truncated
        return result


def prepare_durable_sensitive_text(
    text: str,
    source: Path,
    *,
    maximum_durable_bytes: int,
    scan_budget: SecretScanBudget | None = None,
) -> DurableTextResult:
    """Classify once, derive safe durable text, and enforce a byte limit."""
    if maximum_durable_bytes <= 0:
        raise ValueError("durable text byte limit must be positive")
    budget = scan_budget or SecretScanBudget()
    try:
        result = budget.scan(text, source)
    except SecretScanLimitError:
        return DurableTextResult(
            text=SENSITIVE_TEXT_QUARANTINE,
            transformed=True,
            minimum_finding_count=0,
            finding_count_truncated=False,
            boundary_uncertain=False,
            scan_incomplete=True,
            size_truncated=False,
        )

    durable = result.durable_text
    try:
        encoded = durable.encode("utf-8")
    except (UnicodeEncodeError, MemoryError, SystemError):
        return DurableTextResult(
            text=SENSITIVE_TEXT_QUARANTINE,
            transformed=True,
            minimum_finding_count=result.minimum_finding_count,
            finding_count_truncated=result.finding_count_truncated,
            boundary_uncertain=result.boundary_uncertain,
            scan_incomplete=True,
            size_truncated=False,
        )
    size_truncated = len(encoded) > maximum_durable_bytes
    if size_truncated:
        marker = "[TRUNCATED]"
        budget_bytes = max(0, maximum_durable_bytes - len(marker))
        durable = encoded[:budget_bytes].decode("utf-8", errors="ignore") + marker
    return DurableTextResult(
        text=durable,
        transformed=result.transformed or size_truncated,
        minimum_finding_count=result.minimum_finding_count,
        finding_count_truncated=result.finding_count_truncated,
        boundary_uncertain=result.boundary_uncertain,
        scan_incomplete=False,
        size_truncated=size_truncated,
    )


def resolve_strict(path: Path) -> StrictPathResolution:
    try:
        return StrictPathResolution(path.resolve(strict=True), None)
    except (OSError, RuntimeError) as error:
        return StrictPathResolution(None, error)


def authored_file(logical_path: Path, skill_root: Path) -> AuthoredFile | None:
    """Resolve one contained regular file without following an escape."""
    resolved_root = resolve_strict(skill_root).resolved_path
    resolved_path = resolve_strict(logical_path).resolved_path
    if resolved_root is None or resolved_path is None:
        return None
    if not resolved_path.is_file() or not resolved_path.is_relative_to(resolved_root):
        return None
    return AuthoredFile(logical_path=logical_path, resolved_path=resolved_path)


def sorted_authored_entries(
    directory: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
    reverse: bool = False,
) -> list[Path]:
    """List one directory through a stable handle while charging every entry."""
    descriptor: int | None = None
    try:
        observed = directory.lstat()
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise AuthoredContentReadError(
                "authored directory must be a non-symlink directory"
            )
        descriptor = os.open(directory, _authored_directory_open_flags())
        opened = os.fstat(descriptor)
        expected = _authored_metadata(opened)
        if _authored_metadata(observed) != expected:
            raise AuthoredContentReadError(
                "authored directory changed while being opened"
            )
        names: list[str] = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if budget is not None:
                    budget.inspect_entry()
                names.append(entry.name)
        final = os.fstat(descriptor)
        named_final = directory.lstat()
        if (
            _authored_metadata(final) != expected
            or _authored_metadata(named_final) != expected
        ):
            raise AuthoredContentReadError(
                "authored directory changed during enumeration"
            )
        return [
            directory / name
            for name in sorted(names, reverse=reverse)
        ]
    except AuthoredContentReadError:
        raise
    except OSError as error:
        raise AuthoredContentReadError(
            "authored directory cannot be enumerated safely"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def snapshot_authored_tree(
    content_root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
    excluded_directories: frozenset[str] = frozenset(),
) -> tuple[AuthoredTreeEntry, ...]:
    """Classify a logical tree while retaining every ancestor descriptor."""
    descriptor: int | None = None
    try:
        root_logical = content_root.lstat()
        if stat.S_ISLNK(root_logical.st_mode) or not stat.S_ISDIR(
            root_logical.st_mode
        ):
            raise AuthoredContentReadError(
                "authored tree root must be a non-symlink directory"
            )
        resolved_root = content_root.resolve(strict=True)
        descriptor = os.open(resolved_root, _authored_directory_open_flags())
        opened_root = os.fstat(descriptor)
        if _authored_metadata(opened_root) != _authored_metadata(root_logical):
            raise AuthoredContentReadError(
                "authored tree root changed while being opened"
            )
        entries = _snapshot_open_authored_tree(
            descriptor,
            content_root,
            resolved_root,
            budget,
            excluded_directories,
        )
        final_root = os.fstat(descriptor)
        named_root = content_root.lstat()
        if (
            _authored_metadata(final_root) != _authored_metadata(opened_root)
            or _authored_metadata(named_root) != _authored_metadata(opened_root)
        ):
            raise AuthoredContentReadError(
                "authored tree root changed during traversal"
            )
        return entries
    except AuthoredContentReadError:
        raise
    except (OSError, RuntimeError) as error:
        raise AuthoredContentReadError(
            "authored tree cannot be inspected safely"
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _snapshot_open_authored_tree(
    descriptor: int,
    logical_directory: Path,
    resolved_directory: Path,
    budget: AuthoredRepositoryBudget | None,
    excluded_directories: frozenset[str],
) -> tuple[AuthoredTreeEntry, ...]:
    opened = os.fstat(descriptor)
    observed_entries: list[tuple[str, os.stat_result]] = []
    try:
        with os.scandir(descriptor) as iterator:
            for entry in iterator:
                if budget is not None:
                    budget.inspect_entry()
                observed_entries.append(
                    (entry.name, entry.stat(follow_symlinks=False))
                )
    except OSError as error:
        raise AuthoredContentReadError(
            "authored tree changed during traversal"
        ) from error
    observed_entries.sort(key=lambda item: item[0])

    result: list[AuthoredTreeEntry] = []
    for name, observed in observed_entries:
        logical_path = logical_directory / name
        if stat.S_ISLNK(observed.st_mode):
            try:
                target = os.stat(name, dir_fd=descriptor)
                resolved_path = logical_path.resolve(strict=True)
            except FileNotFoundError as error:
                _require_unchanged_unresolved_authored_symlink(
                    descriptor,
                    name,
                    observed,
                    type(error),
                )
                result.append(
                    AuthoredTreeEntry(
                        logical_path=logical_path,
                        mode=observed.st_mode,
                        metadata=_authored_metadata(observed),
                        resolved_path=None,
                        target_mode=None,
                        target_metadata=None,
                        child_count=None,
                        symlink_error="broken",
                    )
                )
                continue
            except (OSError, RuntimeError) as error:
                _require_unchanged_unresolved_authored_symlink(
                    descriptor,
                    name,
                    observed,
                    type(error),
                )
                result.append(
                    AuthoredTreeEntry(
                        logical_path=logical_path,
                        mode=observed.st_mode,
                        metadata=_authored_metadata(observed),
                        resolved_path=None,
                        target_mode=None,
                        target_metadata=None,
                        child_count=None,
                        symlink_error="invalid",
                    )
                )
                continue
            _require_unchanged_authored_entry(
                descriptor,
                name,
                observed,
                target,
                None,
            )
            result.append(
                AuthoredTreeEntry(
                    logical_path=logical_path,
                    mode=observed.st_mode,
                    metadata=_authored_metadata(observed),
                    resolved_path=resolved_path,
                    target_mode=target.st_mode,
                    target_metadata=_authored_metadata(target),
                    child_count=None,
                )
            )
            continue

        if stat.S_ISDIR(observed.st_mode):
            child_descriptor: int | None = None
            try:
                child_descriptor = os.open(
                    name,
                    _authored_directory_open_flags(),
                    dir_fd=descriptor,
                )
                child_opened = os.fstat(child_descriptor)
                if _authored_metadata(child_opened) != _authored_metadata(
                    observed
                ):
                    raise AuthoredContentReadError(
                        "authored directory changed while being opened"
                    )
                children = (
                    ()
                    if name in excluded_directories
                    else _snapshot_open_authored_tree(
                        child_descriptor,
                        logical_path,
                        resolved_directory / name,
                        budget,
                        excluded_directories,
                    )
                )
                _require_unchanged_authored_entry(
                    descriptor,
                    name,
                    observed,
                    observed,
                    child_descriptor,
                )
            finally:
                if child_descriptor is not None:
                    os.close(child_descriptor)
            result.append(
                AuthoredTreeEntry(
                    logical_path=logical_path,
                    mode=observed.st_mode,
                    metadata=_authored_metadata(observed),
                    resolved_path=resolved_directory / name,
                    target_mode=observed.st_mode,
                    target_metadata=_authored_metadata(observed),
                    child_count=sum(
                        child.logical_path.parent == logical_path
                        for child in children
                    ),
                )
            )
            result.extend(children)
            continue

        _require_unchanged_authored_entry(
            descriptor,
            name,
            observed,
            observed,
            None,
        )
        result.append(
            AuthoredTreeEntry(
                logical_path=logical_path,
                mode=observed.st_mode,
                metadata=_authored_metadata(observed),
                resolved_path=resolved_directory / name,
                target_mode=observed.st_mode,
                target_metadata=_authored_metadata(observed),
                child_count=None,
            )
        )

    if _authored_metadata(os.fstat(descriptor)) != _authored_metadata(opened):
        raise AuthoredContentReadError(
            "authored directory changed during traversal"
        )
    return tuple(result)


def _require_unchanged_unresolved_authored_symlink(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
    expected_error: type[BaseException],
) -> None:
    try:
        current = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if _authored_metadata(current) != _authored_metadata(observed):
            raise AuthoredContentReadError(
                "authored symlink changed during traversal"
            )
        try:
            os.stat(name, dir_fd=parent_descriptor)
        except (OSError, RuntimeError) as error:
            if isinstance(error, expected_error):
                return
        raise AuthoredContentReadError(
            "authored symlink changed during traversal"
        )
    except AuthoredContentReadError:
        raise
    except OSError as error:
        raise AuthoredContentReadError(
            "authored symlink changed during traversal"
        ) from error


def walk_authored_files(
    content_root: Path,
    skill_root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> Iterator[AuthoredFile]:
    """Walk regular files through stable directory handles."""
    resolved_skill_root = resolve_strict(skill_root).resolved_path
    if resolved_skill_root is None:
        raise AuthoredContentReadError("skill root cannot be inspected safely")
    if not content_root.exists() and not content_root.is_symlink():
        return
    resolved_content_root = resolve_strict(content_root).resolved_path
    if resolved_content_root is None:
        if content_root.is_symlink():
            return
        raise AuthoredContentReadError("authored content root cannot be inspected safely")
    if not resolved_content_root.is_dir() or not resolved_content_root.is_relative_to(
        resolved_skill_root
    ):
        if content_root.is_symlink():
            return
        raise AuthoredContentReadError(
            "authored content root is not a contained directory"
        )

    try:
        logical_metadata = content_root.lstat()
        target_metadata = content_root.stat()
        descriptor = os.open(
            resolved_content_root,
            _authored_directory_open_flags(),
        )
    except OSError as error:
        raise AuthoredContentReadError(
            "authored content root cannot be opened safely"
        ) from error
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _authored_identity(opened) != _authored_identity(target_metadata)
        ):
            raise AuthoredContentReadError(
                "authored content root changed while being opened"
            )
        seen_directories: set[tuple[int, int]] = set()
        yield from _walk_open_authored_directory(
            descriptor,
            content_root,
            resolved_content_root,
            resolved_skill_root,
            seen_directories,
            budget,
        )
        final = os.fstat(descriptor)
        current_logical = content_root.lstat()
        current_target = content_root.stat()
        if (
            _authored_metadata(final) != _authored_metadata(opened)
            or _authored_metadata(current_logical)
            != _authored_metadata(logical_metadata)
            or _authored_identity(current_target)
            != _authored_identity(target_metadata)
        ):
            raise AuthoredContentReadError(
                "authored content root changed during traversal"
            )
    except AuthoredContentReadError:
        raise
    except OSError as error:
        raise AuthoredContentReadError(
            "authored directory changed during traversal"
        ) from error
    finally:
        os.close(descriptor)


def _walk_open_authored_directory(
    descriptor: int,
    logical_directory: Path,
    resolved_directory: Path,
    resolved_skill_root: Path,
    seen_directories: set[tuple[int, int]],
    budget: AuthoredRepositoryBudget | None,
) -> Iterator[AuthoredFile]:
    opened = os.fstat(descriptor)
    identity = _authored_identity(opened)
    if identity in seen_directories:
        return
    seen_directories.add(identity)
    entries: list[tuple[str, os.stat_result]] = []
    with os.scandir(descriptor) as iterator:
        for entry in iterator:
            if budget is not None:
                budget.inspect_entry()
            entries.append((entry.name, entry.stat(follow_symlinks=False)))
    entries.sort(key=lambda item: item[0])

    for name, observed in entries:
        logical_path = logical_directory / name
        if stat.S_ISLNK(observed.st_mode):
            resolution = resolve_strict(logical_path).resolved_path
            if (
                resolution is None
                or not resolution.is_relative_to(resolved_skill_root)
            ):
                continue
            try:
                target = os.stat(name, dir_fd=descriptor)
            except OSError as error:
                raise AuthoredContentReadError(
                    "authored entry changed during traversal"
                ) from error
            if stat.S_ISDIR(target.st_mode):
                child_descriptor: int | None = None
                try:
                    child_descriptor = os.open(
                        resolution,
                        _authored_directory_open_flags(),
                    )
                    child_opened = os.fstat(child_descriptor)
                    if _authored_identity(child_opened) != _authored_identity(
                        target
                    ):
                        raise AuthoredContentReadError(
                            "authored directory changed while being opened"
                        )
                    yield from _walk_open_authored_directory(
                        child_descriptor,
                        logical_path,
                        resolution,
                        resolved_skill_root,
                        seen_directories,
                        budget,
                    )
                    _require_unchanged_authored_entry(
                        descriptor,
                        name,
                        observed,
                        target,
                        child_descriptor,
                    )
                finally:
                    if child_descriptor is not None:
                        os.close(child_descriptor)
            elif stat.S_ISREG(target.st_mode):
                yield AuthoredFile(
                    logical_path=logical_path,
                    resolved_path=resolution,
                )
                _require_unchanged_authored_entry(
                    descriptor,
                    name,
                    observed,
                    target,
                    None,
                )
            continue

        if stat.S_ISDIR(observed.st_mode):
            child_descriptor = None
            try:
                child_descriptor = os.open(
                    name,
                    _authored_directory_open_flags(),
                    dir_fd=descriptor,
                )
                child_opened = os.fstat(child_descriptor)
                if _authored_metadata(child_opened) != _authored_metadata(
                    observed
                ):
                    raise AuthoredContentReadError(
                        "authored directory changed while being opened"
                    )
                yield from _walk_open_authored_directory(
                    child_descriptor,
                    logical_path,
                    resolved_directory / name,
                    resolved_skill_root,
                    seen_directories,
                    budget,
                )
                _require_unchanged_authored_entry(
                    descriptor,
                    name,
                    observed,
                    observed,
                    child_descriptor,
                )
            finally:
                if child_descriptor is not None:
                    os.close(child_descriptor)
        elif stat.S_ISREG(observed.st_mode):
            yield AuthoredFile(
                logical_path=logical_path,
                resolved_path=resolved_directory / name,
            )
            _require_unchanged_authored_entry(
                descriptor,
                name,
                observed,
                observed,
                None,
            )

    final = os.fstat(descriptor)
    if _authored_metadata(final) != _authored_metadata(opened):
        raise AuthoredContentReadError(
            "authored directory changed during traversal"
        )


def _require_unchanged_authored_entry(
    parent_descriptor: int,
    name: str,
    logical_metadata: os.stat_result,
    target_metadata: os.stat_result,
    child_descriptor: int | None,
) -> None:
    try:
        current_logical = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        current_target = os.stat(name, dir_fd=parent_descriptor)
        if (
            _authored_metadata(current_logical)
            != _authored_metadata(logical_metadata)
            or _authored_identity(current_target)
            != _authored_identity(target_metadata)
            or (
                child_descriptor is not None
                and _authored_identity(os.fstat(child_descriptor))
                != _authored_identity(target_metadata)
            )
        ):
            raise AuthoredContentReadError(
                "authored entry changed during traversal"
            )
    except AuthoredContentReadError:
        raise
    except OSError as error:
        raise AuthoredContentReadError(
            "authored entry changed during traversal"
        ) from error


def _authored_directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _authored_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _authored_metadata(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def read_bounded_authored_bytes(
    source: AuthoredFile,
    *,
    maximum_bytes: int,
    allowed_root: Path,
    containment_root: Path | None = None,
    budget: AuthoredRepositoryBudget | None = None,
) -> bytes:
    """Read one stable contained authored file without exceeding its byte limit."""
    if maximum_bytes <= 0:
        raise ValueError("authored file byte limit must be positive")
    try:
        stable_root = containment_root or allowed_root
        parent_signatures = _directory_chain_signatures(
            stable_root,
            source.resolved_path.parent,
        )
        resolved_root = allowed_root.resolve(strict=True)
        path = source.resolved_path
        if not path.is_relative_to(resolved_root):
            raise AuthoredContentReadError(
                "authored file is outside its allowed root"
            )
        observed = os.stat(path, follow_symlinks=False)
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISREG(observed.st_mode):
            raise AuthoredContentReadError(
                "authored file is not a regular non-symlink file"
            )
        if observed.st_size > maximum_bytes:
            raise AuthoredContentTooLarge("authored file exceeds its byte limit")
        if budget is not None:
            budget.inspect_bytes(observed.st_size)
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
    except AuthoredContentReadError:
        raise
    except (OSError, MemoryError, RuntimeError) as error:
        raise AuthoredContentReadError("authored file cannot be opened safely") from error

    try:
        opened = os.fstat(descriptor)
        signature = _authored_file_signature(opened)
        if (
            signature != _authored_file_signature(observed)
            or not stat.S_ISREG(opened.st_mode)
        ):
            raise AuthoredContentReadError(
                "authored file changed while it was opened"
            )
        chunks: list[bytes] = []
        consumed = 0
        while True:
            chunk = os.read(descriptor, _AUTHORED_READ_CHUNK_BYTES)
            if not chunk:
                break
            consumed += len(chunk)
            if consumed > maximum_bytes:
                raise AuthoredContentTooLarge(
                    "authored file exceeds its byte limit"
                )
            chunks.append(chunk)
        after = os.fstat(descriptor)
        named_after = os.stat(path, follow_symlinks=False)
        resolved_after = path.resolve(strict=True)
        if (
            _authored_file_signature(after) != signature
            or _authored_file_signature(named_after) != signature
            or resolved_after != path
            or not resolved_after.is_relative_to(resolved_root)
            or _directory_chain_signatures(
                containment_root or allowed_root,
                path.parent,
            )
            != parent_signatures
            or consumed != opened.st_size
        ):
            raise AuthoredContentReadError(
                "authored file changed while it was read"
            )
        return b"".join(chunks)
    except AuthoredContentReadError:
        raise
    except (OSError, MemoryError, RuntimeError) as error:
        raise AuthoredContentReadError("authored file cannot be read safely") from error
    finally:
        os.close(descriptor)


def _authored_file_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_chain_signatures(
    containment_root: Path,
    directory: Path,
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Capture every non-symlink directory component without resolving through it."""
    try:
        root = containment_root.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise AuthoredContentReadError(
            "authored containment root cannot be inspected safely"
        ) from error
    target = directory.absolute()
    try:
        relative = target.relative_to(root)
    except ValueError as error:
        raise AuthoredContentReadError(
            "authored path is outside its containment root"
        ) from error
    signatures: list[tuple[str, tuple[int, ...]]] = []
    current = root
    for component in (".", *relative.parts):
        if component != ".":
            current /= component
        try:
            metadata = current.lstat()
        except OSError as error:
            raise AuthoredContentReadError(
                "authored directory chain cannot be inspected safely"
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise AuthoredContentReadError(
                "authored directory chain contains a symlink or non-directory"
            )
        signatures.append(
            (str(current), _authored_file_signature(metadata))
        )
    return tuple(signatures)


def read_text_fixture(
    source: AuthoredFile,
    *,
    maximum_bytes: int = 4 * 1024 * 1024,
    allowed_root: Path | None = None,
    budget: AuthoredRepositoryBudget | None = None,
) -> str | None:
    """Read one authored UTF-8 text fixture, returning None for binary data."""
    try:
        content = read_bounded_authored_bytes(
            source,
            maximum_bytes=maximum_bytes,
            allowed_root=allowed_root or source.resolved_path.parent,
            budget=budget,
        )
    except AuthoredContentReadError:
        return None
    if b"\x00" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def extract_bundled_paths(
    text: str,
    *,
    maximum_paths: int = 1024,
) -> tuple[str, ...]:
    """Extract clean-looking runtime file paths named in authored eval prose."""
    if maximum_paths < 1:
        raise ValueError("bundled path limit must be positive")
    paths: list[str] = []
    seen: set[str] = set()

    def add(path: str) -> None:
        if path in seen:
            return
        if len(paths) >= maximum_paths:
            raise AuthoredContentComplexityError(
                "authored content exceeds the bundled path limit"
            )
        seen.add(path)
        paths.append(path)

    for match in _FILE_URI_PATTERN.finditer(text):
        add(match.group(0).rstrip(".,;:!?"))

    for absolute_pattern in (
        _WINDOWS_ABSOLUTE_BUNDLED_PATH_PATTERN,
        _POSIX_ABSOLUTE_BUNDLED_PATH_PATTERN,
    ):
        uri_cursors = _bundled_path_exclusion_cursors(text)
        for match in absolute_pattern.finditer(text):
            if _position_is_excluded(match.start("target"), uri_cursors):
                continue
            add(match.group("target").rstrip(".,;:!?"))

    for pattern, strip_punctuation in (
        (_QUOTED_BUNDLED_PATH_PATTERN, False),
        (_BUNDLED_PATH_PATTERN, True),
    ):
        exclusion_cursors = (
            *_bundled_path_exclusion_cursors(text),
            _SortedSpanCursor(
                match.span("target")
                for pattern in (
                    _WINDOWS_ABSOLUTE_BUNDLED_PATH_PATTERN,
                    _POSIX_ABSOLUTE_BUNDLED_PATH_PATTERN,
                )
                for match in pattern.finditer(text)
            ),
        )
        for match in pattern.finditer(text):
            if _position_is_excluded(
                match.start("target"),
                exclusion_cursors,
            ):
                continue
            target = match.group("target")
            add(target.rstrip(".,;:!?") if strip_punctuation else target)
    return tuple(paths)


class _SortedSpanCursor:
    def __init__(self, spans: Iterator[tuple[int, int]]) -> None:
        self._spans = iter(spans)
        self._current = next(self._spans, None)

    def contains(self, position: int) -> bool:
        while self._current is not None and self._current[1] <= position:
            self._current = next(self._spans, None)
        return bool(
            self._current is not None
            and self._current[0] <= position < self._current[1]
        )


def _bundled_path_exclusion_cursors(text: str) -> tuple[_SortedSpanCursor, ...]:
    return (
        _SortedSpanCursor(
            match.span()
            for match in _URI_PATTERN.finditer(text)
            if match.group("scheme").lower() != "file"
            and len(match.group("scheme")) != 1
        ),
        _SortedSpanCursor(
            match.span() for match in _FILE_URI_PATTERN.finditer(text)
        ),
    )


def _position_is_excluded(
    position: int,
    cursors: tuple[_SortedSpanCursor, ...],
) -> bool:
    return any(cursor.contains(position) for cursor in cursors)


def contains_local_eval_runtime_reference(content: str | bytes) -> bool:
    """Return whether actor-visible bytes name local runner-only eval content."""
    if isinstance(content, bytes):
        text = content.decode("latin-1")
    else:
        text = content

    uri_spans = tuple(
        match.span()
        for match in _URI_PATTERN.finditer(text)
        if match.group("scheme").lower() != "file"
        and len(match.group("scheme")) != 1
    )
    return any(
        not any(start <= match.start() < end for start, end in uri_spans)
        for match in _LOCAL_EVAL_RUNTIME_REFERENCE_PATTERN.finditer(text)
    )


def strict_bounded_json_loads(
    value: str | bytes,
    *,
    maximum_bytes: int = DEFAULT_MAXIMUM_JSON_BYTES,
    maximum_nodes: int = DEFAULT_MAXIMUM_JSON_NODES,
    maximum_depth: int = DEFAULT_MAXIMUM_JSON_DEPTH,
) -> object:
    """Parse strict JSON under shared byte, node, and nesting limits."""
    if maximum_bytes <= 0 or maximum_nodes <= 0 or maximum_depth <= 0:
        raise ValueError("JSON parser limits must be positive")
    if not isinstance(value, (str, bytes)):
        raise BoundedJsonError("JSON input must be text or bytes")
    try:
        size = len(value.encode("utf-8")) if isinstance(value, str) else len(value)
    except (UnicodeEncodeError, MemoryError) as error:
        raise BoundedJsonError("JSON input could not be bounded") from error
    if size > maximum_bytes:
        raise BoundedJsonError("JSON input exceeds the byte limit")
    try:
        text = value.decode("utf-8") if isinstance(value, bytes) else value
    except (UnicodeDecodeError, MemoryError) as error:
        raise BoundedJsonError(
            "JSON input is invalid or exceeds parser limits"
        ) from error
    try:
        preflight_bounded_json_structure(
            text,
            maximum_nodes=maximum_nodes,
            maximum_depth=maximum_depth,
        )
    except JsonPreflightError as error:
        if error.kind == "depth":
            raise BoundedJsonError("JSON input exceeds the depth limit") from error
        if error.kind == "nodes":
            raise BoundedJsonError("JSON input exceeds the node limit") from error
        if error.kind == "nonfinite":
            raise BoundedJsonError(
                "JSON input contains a non-finite number"
            ) from error
        raise BoundedJsonError(
            "JSON input is invalid or exceeds parser limits"
        ) from error

    def reject_constant(_: str) -> object:
        raise BoundedJsonError("JSON input contains a non-finite number")

    def reject_duplicate_keys(
        pairs: list[tuple[str, object]],
    ) -> dict[str, object]:
        document: dict[str, object] = {}
        for key, item in pairs:
            if key in document:
                raise BoundedJsonError("JSON input contains a duplicate object key")
            document[key] = item
        return document

    try:
        document = json.loads(
            text,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except BoundedJsonError:
        raise
    except (
        json.JSONDecodeError,
        UnicodeError,
        RecursionError,
        ValueError,
        OverflowError,
        MemoryError,
        SystemError,
    ) as error:
        raise BoundedJsonError("JSON input is invalid or exceeds parser limits") from error

    nodes = 0
    pending: list[tuple[object, int]] = [(document, 1)]
    try:
        while pending:
            item, depth = pending.pop()
            if depth > maximum_depth:
                raise BoundedJsonError("JSON input exceeds the depth limit")
            nodes += 1
            if nodes > maximum_nodes:
                raise BoundedJsonError("JSON input exceeds the node limit")
            if isinstance(item, Mapping):
                nodes += len(item)
                if nodes > maximum_nodes or len(item) > maximum_nodes - nodes:
                    raise BoundedJsonError("JSON input exceeds the node limit")
                pending.extend((child, depth + 1) for child in item.values())
            elif isinstance(item, list):
                if len(item) > maximum_nodes - nodes:
                    raise BoundedJsonError("JSON input exceeds the node limit")
                pending.extend((child, depth + 1) for child in item)
            elif isinstance(item, float) and not math.isfinite(item):
                raise BoundedJsonError("JSON input contains a non-finite number")
    except BoundedJsonError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        RuntimeError,
        SystemError,
    ) as error:
        raise BoundedJsonError("JSON input exceeds parser limits") from error
    return document


def preflight_bounded_json_structure(
    text: str,
    *,
    maximum_nodes: int,
    maximum_depth: int,
    maximum_scalar_bytes: int | None = None,
    maximum_number_characters: int | None = None,
) -> None:
    """Validate strict JSON structure and limits without building its value graph."""
    if (
        not isinstance(text, str)
        or maximum_nodes <= 0
        or maximum_depth <= 0
        or maximum_scalar_bytes is not None
        and maximum_scalar_bytes <= 0
        or maximum_number_characters is not None
        and maximum_number_characters <= 0
    ):
        raise ValueError("JSON preflight limits must be positive")
    scanner = _BoundedJsonScanner(
        text=text,
        maximum_nodes=maximum_nodes,
        maximum_depth=maximum_depth,
        maximum_scalar_bytes=maximum_scalar_bytes,
        maximum_number_characters=maximum_number_characters,
    )
    try:
        scanner.scan()
    except JsonPreflightError:
        raise
    except (MemoryError, OverflowError, RecursionError, SystemError) as error:
        raise JsonPreflightError("invalid") from error


@dataclass
class _BoundedJsonScanner:
    text: str
    maximum_nodes: int
    maximum_depth: int
    maximum_scalar_bytes: int | None
    maximum_number_characters: int | None
    index: int = 0
    nodes: int = 0

    def scan(self) -> None:
        self._skip_whitespace()
        self._scan_value(1)
        self._skip_whitespace()
        if self.index != len(self.text):
            raise JsonPreflightError("invalid")

    def _scan_value(self, depth: int) -> None:
        if depth > self.maximum_depth:
            raise JsonPreflightError("depth")
        self._count_node()
        if self.index >= len(self.text):
            raise JsonPreflightError("invalid")
        marker = self.text[self.index]
        if marker == "{":
            self._scan_object(depth)
            return
        if marker == "[":
            self._scan_array(depth)
            return
        if marker == '"':
            self._scan_string()
            return
        for literal in ("true", "false", "null"):
            if self.text.startswith(literal, self.index):
                self.index += len(literal)
                return
        if self.text.startswith(("NaN", "Infinity", "-Infinity"), self.index):
            raise JsonPreflightError("nonfinite")
        if marker == "-" or marker.isdigit():
            self._scan_number()
            return
        raise JsonPreflightError("invalid")

    def _scan_object(self, depth: int) -> None:
        self.index += 1
        self._skip_whitespace()
        if self._consume_if("}"):
            return
        while True:
            if self.index >= len(self.text) or self.text[self.index] != '"':
                raise JsonPreflightError("invalid")
            self._count_node()
            self._scan_string()
            self._skip_whitespace()
            if not self._consume_if(":"):
                raise JsonPreflightError("invalid")
            self._skip_whitespace()
            self._scan_value(depth + 1)
            self._skip_whitespace()
            if self._consume_if("}"):
                return
            if not self._consume_if(","):
                raise JsonPreflightError("invalid")
            self._skip_whitespace()

    def _scan_array(self, depth: int) -> None:
        self.index += 1
        self._skip_whitespace()
        if self._consume_if("]"):
            return
        while True:
            self._scan_value(depth + 1)
            self._skip_whitespace()
            if self._consume_if("]"):
                return
            if not self._consume_if(","):
                raise JsonPreflightError("invalid")
            self._skip_whitespace()

    def _scan_string(self) -> None:
        self.index += 1
        decoded_bytes = 0
        while self.index < len(self.text):
            character = self.text[self.index]
            if character == '"':
                self.index += 1
                return
            if ord(character) < 0x20:
                raise JsonPreflightError("invalid")
            if character != "\\":
                decoded_bytes += _json_code_point_bytes(ord(character))
                self.index += 1
            else:
                self.index += 1
                if self.index >= len(self.text):
                    raise JsonPreflightError("invalid")
                escape = self.text[self.index]
                if escape in '"\\/bfnrt':
                    decoded_bytes += 1
                    self.index += 1
                elif escape == "u":
                    code_point = self._scan_unicode_escape()
                    if (
                        0xD800 <= code_point <= 0xDBFF
                        and self.text.startswith("\\u", self.index)
                        and self.index + 6 <= len(self.text)
                    ):
                        low_token = self.text[self.index + 2 : self.index + 6]
                        if all(value in "0123456789abcdefABCDEF" for value in low_token):
                            low = int(low_token, 16)
                            if 0xDC00 <= low <= 0xDFFF:
                                self.index += 6
                                decoded_bytes += 4
                            else:
                                decoded_bytes += 3
                        else:
                            decoded_bytes += 3
                    else:
                        decoded_bytes += _json_code_point_bytes(code_point)
                else:
                    raise JsonPreflightError("invalid")
            if (
                self.maximum_scalar_bytes is not None
                and decoded_bytes > self.maximum_scalar_bytes
            ):
                raise JsonPreflightError("scalar")
        raise JsonPreflightError("invalid")

    def _scan_unicode_escape(self) -> int:
        start = self.index + 1
        end = start + 4
        token = self.text[start:end]
        if len(token) != 4 or any(
            value not in "0123456789abcdefABCDEF" for value in token
        ):
            raise JsonPreflightError("invalid")
        self.index = end
        return int(token, 16)

    def _scan_number(self) -> None:
        start = self.index
        self._consume_if("-")
        if self.index >= len(self.text):
            raise JsonPreflightError("invalid")
        if self.text[self.index] == "0":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index].isdigit():
                raise JsonPreflightError("invalid")
        elif self.text[self.index] in "123456789":
            self.index += 1
            while self.index < len(self.text) and self.text[self.index].isdigit():
                self.index += 1
        else:
            raise JsonPreflightError("invalid")
        if self._consume_if("."):
            fraction_start = self.index
            while self.index < len(self.text) and self.text[self.index].isdigit():
                self.index += 1
            if self.index == fraction_start:
                raise JsonPreflightError("invalid")
        if self.index < len(self.text) and self.text[self.index] in "eE":
            self.index += 1
            if self.index < len(self.text) and self.text[self.index] in "+-":
                self.index += 1
            exponent_start = self.index
            while self.index < len(self.text) and self.text[self.index].isdigit():
                self.index += 1
            if self.index == exponent_start:
                raise JsonPreflightError("invalid")
        if (
            self.maximum_number_characters is not None
            and self.index - start > self.maximum_number_characters
        ):
            raise JsonPreflightError("scalar")

    def _count_node(self) -> None:
        self.nodes += 1
        if self.nodes > self.maximum_nodes:
            raise JsonPreflightError("nodes")

    def _skip_whitespace(self) -> None:
        while self.index < len(self.text) and self.text[self.index] in " \t\r\n":
            self.index += 1

    def _consume_if(self, marker: str) -> bool:
        if self.index < len(self.text) and self.text[self.index] == marker:
            self.index += 1
            return True
        return False


def _json_code_point_bytes(code_point: int) -> int:
    if code_point <= 0x7F:
        return 1
    if code_point <= 0x7FF:
        return 2
    if code_point <= 0xFFFF:
        return 3
    return 4


def scan_static_secret_issues(
    text: str,
    source: Path,
    *,
    maximum_findings: int = DEFAULT_MAXIMUM_SECRET_FINDINGS,
    allow_python_assignment_comments: bool = True,
    allow_multiline_assignment_context: bool = True,
    _decoder_steps: list[int] | None = None,
) -> SecretScanResult:
    """Classify and sanitize bounded high-confidence credential evidence."""
    if maximum_findings <= 0:
        raise ValueError("maximum secret findings must be positive")
    decoder_steps = (
        _decoder_steps
        if _decoder_steps is not None
        else [_MAX_PYTHON_DECODER_EVALUATION_STEPS]
    )
    candidates: list[_SensitiveCandidate] = []
    truncated = False
    boundary_uncertain = False
    escaped_context_classifications: dict[str, str] = {}
    safe_assignment_spans: list[tuple[int, int]] = []
    python_assignment_values: dict[int, str] | None = (
        None if source.suffix.casefold() == ".py" else {}
    )
    for pattern in (*_RUNTIME_SECRET_PATTERNS, *SECRET_PATTERNS):
        if pattern.name == "private-key-block":
            for start, end in _private_key_blocks(text):
                candidate = _SensitiveCandidate(start, end, pattern)
                if _candidate_overlaps(candidates, candidate):
                    continue
                if len(candidates) >= maximum_findings:
                    truncated = True
                    break
                candidates.append(candidate)
            if truncated:
                break
            continue
        for match in pattern.regex.finditer(text):
            if pattern.name == "sensitive-assignment" and any(
                start < match.end() and match.start() < end
                for start, end in safe_assignment_spans
            ):
                continue
            if pattern.name in {
                "escaped-authorization-context",
                "escaped-cookie-context",
            }:
                classification = escaped_context_classifications.get(pattern.name)
                if classification is None:
                    classification = _classify_escaped_json_sensitive_context(
                        text,
                        pattern.name,
                        decoder_steps=decoder_steps,
                    )
                    escaped_context_classifications[pattern.name] = classification
                if classification == "safe":
                    continue
                boundary_uncertain = True
                start = match.start()
                end = match.end()
            elif pattern.value_group is not None:
                value = match.group(pattern.value_group)
                if pattern.name == "sensitive-assignment":
                    if python_assignment_values is None:
                        python_assignment_values = _python_assignment_values(
                            text
                        )
                    value = python_assignment_values.get(
                        match.start(pattern.value_group),
                        value,
                    )
                    shell_value = _complete_shell_command_substitution(
                        text,
                        match.start(pattern.value_group),
                    )
                    if shell_value is not None:
                        value = shell_value
                classification = _classify_pattern_value(
                    pattern,
                    match,
                    value,
                    allow_python_assignment_comments=allow_python_assignment_comments,
                    decoder_steps=decoder_steps,
                )
                if (
                    classification == "safe"
                    and pattern.name == "sensitive-assignment"
                    and not allow_multiline_assignment_context
                    and ("\n" in text or "\r" in text)
                ):
                    classification = "sensitive"
                if classification == "safe":
                    if pattern.blocks_overlapping_assignments_when_safe:
                        value_start = match.start(pattern.value_group)
                        value = match.group(pattern.value_group)
                        value_start += len(value) - len(value.lstrip(" \t"))
                        if value_start < match.end(pattern.value_group):
                            safe_assignment_spans.append(
                                (value_start, value_start + 1)
                            )
                    continue
                if classification == "uncertain":
                    boundary_uncertain = True
                start = match.start(pattern.value_group)
                end = match.end(pattern.value_group)
            else:
                start = match.start()
                end = match.end()
                if pattern.fake_prefix_allowed and _has_fake_prefix(text, start):
                    continue
            candidate = _SensitiveCandidate(start, end, pattern)
            if _candidate_overlaps(candidates, candidate):
                continue
            if len(candidates) >= maximum_findings:
                truncated = True
                break
            candidates.append(candidate)
        if truncated:
            break

    findings: list[SecretMatch] = []
    line = 1
    previous = 0
    last_newline = -1
    ordered = sorted(candidates, key=lambda item: item.start)
    for candidate in ordered:
        start = candidate.start
        pattern = candidate.pattern
        line += text.count("\n", previous, start)
        newest_newline = text.rfind("\n", previous, start)
        if newest_newline >= 0:
            last_newline = newest_newline
        findings.append(
            SecretMatch(
                pattern=pattern.name,
                category=pattern.category,
                confidence=pattern.confidence,
                source=source,
                line=line,
                column=start - last_newline,
            )
        )
        previous = start
    durable_text = (
        SENSITIVE_TEXT_QUARANTINE
        if truncated or boundary_uncertain
        else _redact_sensitive_candidates(text, ordered)
    )
    return SecretScanResult(
        findings=tuple(findings),
        minimum_finding_count=len(findings) + int(truncated),
        finding_count_truncated=truncated,
        boundary_uncertain=boundary_uncertain,
        durable_text=durable_text,
        transformed=bool(findings or truncated or boundary_uncertain),
    )


def find_static_secret_issues(text: str, source: Path) -> list[SecretMatch]:
    """Return bounded high-confidence authored findings without exposing values."""
    return list(scan_static_secret_issues(text, source).findings)


def render_safe_diagnostic_text(text: str) -> str:
    """Redact high-confidence values from one bounded diagnostic string."""
    redacted = _redact_diagnostic_fragment(text)
    if redacted == SENSITIVE_TEXT_REDACTION:
        return redacted
    fragments = re.split(r"([/\\])", redacted)
    return "".join(
        fragment
        if fragment in {"/", "\\"}
        else _redact_diagnostic_fragment(fragment)
        for fragment in fragments
    )


def _redact_diagnostic_fragment(text: str) -> str:
    result = scan_static_secret_issues(
        text,
        _DIAGNOSTIC_SOURCE,
        allow_python_assignment_comments=False,
        allow_multiline_assignment_context=False,
    )
    return SENSITIVE_TEXT_REDACTION if result.transformed else result.durable_text


def find_static_secret_issues_in_bytes(
    content: bytes,
    source: Path,
    *,
    maximum_findings: int = DEFAULT_MAXIMUM_SECRET_FINDINGS,
) -> list[SecretMatch]:
    """Scan byte-preserving and Unicode views of bounded authored content."""
    if maximum_findings <= 0:
        raise ValueError("maximum secret findings must be positive")
    decoder_steps = [_MAX_PYTHON_DECODER_EVALUATION_STEPS]
    findings: list[SecretMatch] = []
    for encoding, offset in (
        ("latin-1", 0),
        ("utf-16-le", 0),
        ("utf-16-le", 1),
        ("utf-16-be", 0),
        ("utf-16-be", 1),
        ("utf-32-le", 0),
        ("utf-32-le", 1),
        ("utf-32-le", 2),
        ("utf-32-le", 3),
        ("utf-32-be", 0),
        ("utf-32-be", 1),
        ("utf-32-be", 2),
        ("utf-32-be", 3),
    ):
        remaining = maximum_findings - len(findings)
        if remaining <= 0:
            break
        findings.extend(
            _scan_static_secret_byte_view(
                content,
                source,
                encoding=encoding,
                offset=offset,
                maximum_findings=remaining,
                decoder_steps=decoder_steps,
            )
        )
    return findings


def _scan_static_secret_byte_view(
    content: bytes,
    source: Path,
    *,
    encoding: str,
    offset: int,
    maximum_findings: int,
    decoder_steps: list[int],
) -> tuple[SecretMatch, ...]:
    """Decode and scan one bounded byte view before allocating the next."""
    text = codecs.decode(memoryview(content)[offset:], encoding, "replace")
    return scan_static_secret_issues(
        text,
        source,
        maximum_findings=maximum_findings,
        _decoder_steps=decoder_steps,
    ).findings


def find_additional_decoded_json_secret_issues(
    document: object,
    source: Path,
    *,
    maximum_bytes: int,
    raw_findings: Sequence[SecretMatch] = (),
) -> list[SecretMatch]:
    """Find secrets revealed only after strict JSON escape decoding."""
    text = render_bounded_decoded_json(
        document,
        maximum_bytes=maximum_bytes,
    )
    remaining_raw = Counter(
        (finding.pattern, finding.category) for finding in raw_findings
    )
    additional: list[SecretMatch] = []
    for finding in find_static_secret_issues(text, source):
        identity = (finding.pattern, finding.category)
        if remaining_raw[identity]:
            remaining_raw[identity] -= 1
        else:
            additional.append(finding)
    return additional


def render_bounded_decoded_json(
    document: object,
    *,
    maximum_bytes: int,
) -> str:
    """Render one parsed JSON value for bounded decoded-content inspection."""
    if maximum_bytes <= 0:
        raise ValueError("decoded JSON secret scan limit must be positive")
    try:
        text = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        if len(text.encode("utf-8")) > maximum_bytes:
            raise BoundedJsonError("decoded JSON exceeds the secret scan byte limit")
    except BoundedJsonError:
        raise
    except (
        MemoryError,
        OverflowError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as error:
        raise BoundedJsonError(
            "decoded JSON cannot be bounded for secret scanning"
        ) from error
    return text


def _private_key_blocks(text: str) -> Iterator[tuple[int, int]]:
    open_block: tuple[int, str] | None = None
    for marker in _PRIVATE_KEY_MARKER_PATTERN.finditer(text):
        if marker.group("direction") == "BEGIN":
            if open_block is None:
                open_block = (marker.start(), marker.group("label"))
        elif open_block is not None and marker.group("label") == open_block[1]:
            yield open_block[0], marker.end()
            open_block = None
    if open_block is not None:
        yield open_block[0], len(text)


def _candidate_overlaps(
    candidates: list[_SensitiveCandidate],
    candidate: _SensitiveCandidate,
) -> bool:
    if candidate.start >= candidate.end:
        return True
    return any(
        candidate.start < existing.end and existing.start < candidate.end
        for existing in candidates
    )


def _redact_sensitive_candidates(
    text: str,
    candidates: list[_SensitiveCandidate],
) -> str:
    if not candidates:
        return text
    parts: list[str] = []
    previous = 0
    for candidate in candidates:
        parts.append(text[previous : candidate.start])
        parts.append(SENSITIVE_TEXT_REDACTION)
        previous = candidate.end
    parts.append(text[previous:])
    return "".join(parts)


def _classify_pattern_value(
    pattern: SecretPattern,
    match: re.Match[str],
    value: str,
    *,
    allow_python_assignment_comments: bool = True,
    decoder_steps: list[int],
) -> str:
    if (
        pattern.name == "authorization-value"
        and _PYTHON_FSTRING_AUTHORIZATION_PATTERN.fullmatch(value.strip())
    ):
        return "safe"
    if pattern.name in {
        "authorization-value",
        "cookie-value",
        "bearer-token",
    }:
        value, boundary_proven = _decode_runtime_sensitive_value(
            value,
            bearer=pattern.name == "bearer-token",
        )
        if not boundary_proven:
            return "uncertain"
    if pattern.name == "cookie-value":
        safe = _is_safe_cookie_value(
            match.group("name"),
            value,
            decoder_steps=decoder_steps,
        )
        return "safe" if safe else "sensitive"
    if pattern.name == "authorization-value":
        parts = value.strip().split(None, 1)
        credential = parts[1] if len(parts) == 2 else value
        return (
            "safe"
            if _is_safe_authorization_credential(
                credential,
                decoder_steps=decoder_steps,
            )
            else "sensitive"
        )
    if pattern.name == "sensitive-assignment":
        return (
            "safe"
            if _is_safe_sensitive_assignment_value(
                match,
                value,
                allow_python_assignment_comments=allow_python_assignment_comments,
                decoder_steps=decoder_steps,
            )
            else "sensitive"
        )
    return (
        "safe"
        if _is_safe_assigned_value(
            value,
            decoder_steps=decoder_steps,
        )
        else "sensitive"
    )


def _classify_escaped_json_sensitive_context(
    text: str,
    pattern_name: str,
    *,
    decoder_steps: list[int],
) -> str:
    """Classify a decoded header while failing closed on its outer byte boundary."""
    direct_pattern = (
        _AUTHORIZATION_HEADER_SECRET
        if pattern_name == "escaped-authorization-context"
        else _COOKIE_HEADER_SECRET
    )
    escaped_pattern = (
        _ESCAPED_AUTHORIZATION_HEADER_PATTERN
        if pattern_name == "escaped-authorization-context"
        else _ESCAPED_COOKIE_HEADER_PATTERN
    )
    try:
        matched = False
        index = 0
        token_start: int | None = None
        while index < len(text):
            character = text[index]
            if token_start is None:
                if character == '"':
                    token_start = index
                index += 1
                continue
            if character in "\r\n":
                token_start = None
                index += 1
                continue
            if character == "\\":
                index += 2
                continue
            if character != '"':
                index += 1
                continue

            token = text[token_start : index + 1]
            token_start = None
            index += 1
            if escaped_pattern.search(token) is None:
                continue
            if len(token) > DEFAULT_MAXIMUM_JSON_BYTES:
                return "uncertain"
            decoded = json.loads(token)
            if not isinstance(decoded, str):
                return "uncertain"
            token_matched = False
            for match in direct_pattern.regex.finditer(decoded):
                token_matched = True
                classification = _classify_pattern_value(
                    direct_pattern,
                    match,
                    match.group("value"),
                    decoder_steps=decoder_steps,
                )
                if classification != "safe":
                    return classification
            if not token_matched:
                return "uncertain"
            matched = True
        return "safe" if matched else "uncertain"
    except (
        json.JSONDecodeError,
        UnicodeError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
        MemoryError,
        SystemError,
    ):
        return "uncertain"


def _is_safe_cookie_value(
    name: str,
    value: str,
    *,
    decoder_steps: list[int],
) -> bool:
    segments = value.split(";")
    if name.casefold() == "set-cookie":
        segments = segments[:1]
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        candidate = segment.split("=", 1)[1] if "=" in segment else segment
        if not _is_safe_assigned_value(
            candidate,
            decoder_steps=decoder_steps,
        ):
            return False
    return True


def _decode_runtime_sensitive_value(
    value: str,
    *,
    bearer: bool,
) -> tuple[str, bool]:
    stripped = value.strip()
    if not stripped:
        return stripped, True
    if stripped.startswith('"'):
        try:
            decoded = json.loads(stripped)
        except (
            json.JSONDecodeError,
            UnicodeError,
            RecursionError,
            ValueError,
            OverflowError,
            MemoryError,
            SystemError,
        ):
            return "", False
        return (decoded.strip(), True) if isinstance(decoded, str) else ("", False)
    if stripped.startswith("'"):
        if len(stripped) < 2 or not stripped.endswith("'"):
            return "", False
        inner = stripped[1:-1]
        index = 0
        while index < len(inner):
            if inner[index] == "\\":
                if index + 1 >= len(inner):
                    return "", False
                index += 2
            else:
                index += 1
        return inner.strip(), True
    if not bearer:
        return stripped, True

    index = 0
    while index < len(stripped):
        character = stripped[index]
        if character in {'"', "'"}:
            return "", False
        if character != "\\":
            index += 1
            continue
        if index + 1 >= len(stripped):
            return "", False
        escaped = stripped[index + 1]
        if escaped == "u":
            digits = stripped[index + 2 : index + 6]
            if len(digits) != 4 or any(digit not in "0123456789abcdefABCDEF" for digit in digits):
                return "", False
            index += 6
        elif escaped in '"\\/bfnrt':
            index += 2
        else:
            return "", False
    return stripped, True


def _has_fake_prefix(text: str, start: int) -> bool:
    return text[max(0, start - len("FAKE_")) : start] == "FAKE_"


def _is_safe_assigned_value(
    raw_value: str,
    *,
    decoder_steps: list[int],
) -> bool:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if not value:
        return True
    if (
        _PURE_REFERENCE_PATTERN.fullmatch(value)
        or _FORMAT_REFERENCE_PATTERN.fullmatch(value)
        or _FAKE_VALUE_PATTERN.fullmatch(value)
        or _is_safe_shell_command_substitution(
            value,
            decoder_steps=decoder_steps,
        )
    ):
        return True
    if value.upper() in {
        "[REDACTED]",
        "[REMOVED]",
        "[MASKED]",
        "[PLACEHOLDER]",
    }:
        return True

    normalized = value.upper().replace("-", "_").replace(" ", "_")
    if normalized in {
        "REDACTED",
        "REMOVED",
        "MASKED",
        "PLACEHOLDER",
        "CHANGEME",
        "CHANGE_ME",
        "EXAMPLE",
        "NONE",
        "NULL",
    }:
        return True
    if re.fullmatch(r"YOUR_[A-Z0-9_]+(?:_HERE)?", normalized):
        return True
    if re.fullmatch(r"<(?:YOUR_[A-Z0-9_]+|REDACTED|PLACEHOLDER)>", normalized):
        return True
    return bool(re.fullmatch(r"(?:X{3,}|\*{3,})", normalized))


def _is_safe_sensitive_assignment_value(
    match: re.Match[str],
    raw_value: str,
    *,
    allow_python_assignment_comments: bool,
    decoder_steps: list[int],
) -> bool:
    value = raw_value.strip()
    if _is_safe_fake_shell_assignment(value):
        return True
    if (
        _is_safe_python_runtime_expression(
            value,
            allow_comments=allow_python_assignment_comments,
            decoder_steps=decoder_steps,
        )
        or _is_safe_shell_command_substitution(
            value,
            decoder_steps=decoder_steps,
        )
    ):
        return True
    if not _is_safe_assigned_value(
        value,
        decoder_steps=decoder_steps,
    ):
        return False

    line_end = match.string.find("\n", match.end("value"))
    if line_end < 0:
        line_end = len(match.string)
    remainder = match.string[match.end("value") : line_end].lstrip()
    return (
        not remainder
        or remainder.startswith(("#", "//"))
        or re.match(r"(?:[,;)}\]]|[\"'][,;)}\]])", remainder) is not None
    )


def _is_safe_fake_shell_assignment(value: str) -> bool:
    match = re.match(
        r"(?P<fake>FAKE_[A-Za-z0-9][A-Za-z0-9_.:/-]*)(?:[ \t]+(?P<rest>.*))?\Z",
        value,
    )
    if match is None:
        return False
    remainder = match.group("rest")
    if remainder is None:
        return True
    try:
        tokens = shlex.split(remainder, posix=True)
    except ValueError:
        return False
    return (
        len(tokens) >= 2
        and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", tokens[0]) is not None
    )


def _python_assignment_values(text: str) -> dict[int, str]:
    """Map Python RHS offsets to complete expressions for multiline scanning."""
    if len(text) > _MAX_PYTHON_ASSIGNMENT_RECOVERY_BYTES:
        return {}
    try:
        if (
            len(text.encode("utf-8"))
            > _MAX_PYTHON_ASSIGNMENT_RECOVERY_BYTES
        ):
            return {}
    except (MemoryError, UnicodeError):
        return {}
    token_count = 0
    try:
        for _ in tokenize.generate_tokens(io.StringIO(text).readline):
            token_count += 1
            if token_count > _MAX_PYTHON_ASSIGNMENT_RECOVERY_TOKENS:
                return {}
    except (
        IndentationError,
        MemoryError,
        RecursionError,
        SyntaxError,
        tokenize.TokenError,
        UnicodeError,
    ):
        return {}
    try:
        tree = ast.parse(text)
    except (
        SyntaxError,
        ValueError,
        MemoryError,
        RecursionError,
        UnicodeError,
    ):
        return {}
    line_starts = [0]
    line_starts.extend(
        index + 1
        for index, character in enumerate(text)
        if character == "\n"
    )
    values: dict[int, str] = {}
    inspected = 0
    try:
        for node in ast.walk(tree):
            inspected += 1
            if inspected > _MAX_PYTHON_SOURCE_NODES:
                return {}
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            value = node.value
            segment = ast.get_source_segment(text, value)
            if segment is None:
                continue
            line_index = value.lineno - 1
            if line_index < 0 or line_index >= len(line_starts):
                return {}
            line_end = text.find("\n", line_starts[line_index])
            if line_end < 0:
                line_end = len(text)
            line = text[line_starts[line_index] : line_end]
            prefix = line.encode("utf-8")[: value.col_offset]
            column = len(prefix.decode("utf-8"))
            values[line_starts[line_index] + column] = segment
    except (
        AttributeError,
        MemoryError,
        RecursionError,
        TypeError,
        UnicodeError,
        ValueError,
    ):
        return {}
    return values


def _is_safe_python_runtime_expression(
    value: str,
    *,
    allow_comments: bool,
    decoder_steps: list[int],
) -> bool:
    if not allow_comments and _contains_python_comment(value):
        return False
    try:
        expression = ast.parse(value, mode="eval").body
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False
    return _is_safe_python_reference_node(
        expression,
        decoder_steps=decoder_steps,
    )


def _contains_python_comment(value: str) -> bool:
    try:
        return any(
            token.type == tokenize.COMMENT
            for token in tokenize.generate_tokens(io.StringIO(value).readline)
        )
    except (
        IndentationError,
        MemoryError,
        RecursionError,
        SyntaxError,
        tokenize.TokenError,
        UnicodeError,
    ):
        return True


def _is_safe_python_reference_node(
    expression: ast.expr,
    *,
    decoder_steps: list[int],
) -> bool:
    inspected = 0

    def classify(
        node: ast.expr,
        depth: int,
        *,
        lookup_key: bool = False,
        formatted_literal: bool = False,
    ) -> str | None:
        nonlocal inspected
        inspected += 1
        if (
            inspected > _MAX_SAFE_PYTHON_REFERENCE_NODES
            or depth > _MAX_SAFE_PYTHON_REFERENCE_DEPTH
        ):
            return None
        child_depth = depth + 1
        if isinstance(node, ast.Name):
            if node.id.isupper():
                return None
            return "runtime"
        if isinstance(node, ast.Attribute):
            if isinstance(node.value, (ast.Call, ast.Constant)):
                return None
            return (
                "runtime"
                if classify(node.value, child_depth) == "runtime"
                else None
            )
        if isinstance(node, ast.Await):
            return (
                "runtime"
                if classify(node.value, child_depth) == "runtime"
                else None
            )
        if isinstance(node, ast.Call):
            return classify_call(node, child_depth)
        if isinstance(node, ast.JoinedStr):
            has_runtime_value = False
            for value in node.values:
                classification = classify(
                    value,
                    child_depth,
                    formatted_literal=isinstance(value, ast.Constant),
                )
                if classification is None:
                    return None
                has_runtime_value = has_runtime_value or classification == "runtime"
            return "runtime" if has_runtime_value else None
        if isinstance(node, ast.FormattedValue):
            if classify(node.value, child_depth) != "runtime":
                return None
            if node.format_spec is not None:
                if classify(node.format_spec, child_depth) is None:
                    return None
            return "runtime"
        if isinstance(node, ast.Subscript):
            if classify(node.value, child_depth) != "runtime":
                return None
            if classify(node.slice, child_depth, lookup_key=True) is None:
                return None
            return "runtime"
        if isinstance(node, ast.IfExp):
            branches = (
                classify(node.body, child_depth),
                classify(node.orelse, child_depth),
            )
            if None in branches or "runtime" not in branches:
                return None
            return "runtime"
        if isinstance(node, ast.Constant):
            if lookup_key and isinstance(node.value, str):
                if re.fullmatch(
                    r"[A-Za-z_][A-Za-z0-9_.-]*",
                    node.value,
                ):
                    return "literal"
                return None
            if node.value is None:
                return "literal"
            if isinstance(node.value, str):
                if formatted_literal:
                    return (
                        "literal"
                        if re.fullmatch(r"[^A-Za-z0-9]*", node.value)
                        else None
                    )
                if (
                    _is_safe_assigned_value(
                        node.value,
                        decoder_steps=decoder_steps,
                    )
                    or node.value.casefold() in _SAFE_PYTHON_CALL_LITERALS
                    or re.fullmatch(r"[^A-Za-z0-9]*", node.value)
                ):
                    return "literal"
            return None
        return None

    def classify_call(node: ast.Call, depth: int) -> str | None:
        if any(isinstance(argument, ast.Starred) for argument in node.args):
            return None
        if any(keyword.arg is None for keyword in node.keywords):
            return None
        dotted_name = _python_dotted_name(node.func)
        if dotted_name in {
            "base64.b64encode",
            "base64.urlsafe_b64encode",
        }:
            if (
                len(node.args) != 1
                or node.keywords
                or classify(node.args[0], depth) != "runtime"
            ):
                return None
            return "runtime"
        if isinstance(node.func, ast.Attribute) and node.func.attr in {
            "encode",
            "decode",
        }:
            if classify(node.func.value, depth) != "runtime":
                return None
            if len(node.args) > 1 or node.keywords:
                return None
            if node.args:
                argument = node.args[0]
                if (
                    not isinstance(argument, ast.Constant)
                    or not isinstance(argument.value, str)
                    or argument.value.casefold() not in _SAFE_PYTHON_CALL_LITERALS
                ):
                    return None
            return "runtime"
        if (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in {"get", "getenv"}
            and _is_python_runtime_receiver(node.func.value)
        ) or (
            isinstance(node.func, ast.Name)
            and node.func.id == "getenv"
        ):
            if len(node.args) > 2:
                return None
            allowed_keywords = {"key", "name", "default"}
            if any(keyword.arg not in allowed_keywords for keyword in node.keywords):
                return None
            key_values = [
                *node.args[:1],
                *(
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg in {"key", "name"}
                ),
            ]
            if len(key_values) != 1:
                return None
            if classify(key_values[0], depth, lookup_key=True) is None:
                return None
            defaults = [
                *node.args[1:],
                *(
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "default"
                ),
            ]
            if len(defaults) > 1 or any(
                classify(default, depth) is None for default in defaults
            ):
                return None
            return "runtime"
        return None

    return classify(expression, 0) == "runtime"


def _python_dotted_name(expression: ast.expr) -> str | None:
    parts: list[str] = []
    current = expression
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _is_python_runtime_receiver(expression: ast.expr) -> bool:
    if isinstance(expression, ast.Name):
        return not expression.id.isupper()
    if isinstance(expression, ast.Attribute):
        return _is_python_runtime_receiver(expression.value)
    if isinstance(expression, ast.Subscript):
        return _is_python_runtime_receiver(expression.value)
    return False


def _complete_shell_command_substitution(text: str, start: int) -> str | None:
    if not text.startswith("$(", start):
        return None
    depth = 1
    quote: str | None = None
    index = start + 2
    while index < len(text):
        character = text[index]
        if quote == "'":
            if character == "'":
                quote = None
            index += 1
            continue
        if quote == '"':
            if character == "\\":
                index += 2
                continue
            if character == '"':
                quote = None
            index += 1
            continue
        if character == "\\":
            index += 2
            continue
        if character in {"'", '"'}:
            quote = character
            index += 1
            continue
        if text.startswith("$(", index):
            depth += 1
            index += 2
            continue
        if character == ")":
            depth -= 1
            index += 1
            if depth == 0:
                line_end = text.find("\n", index)
                if line_end < 0:
                    line_end = len(text)
                suffix = text[index:line_end].strip()
                if suffix and re.fullmatch(
                    r"\|\|[ \t]+exit[ \t]+[0-9]+",
                    suffix,
                ) is None:
                    return None
                return text[start:index]
            continue
        index += 1
    return None


def _is_safe_shell_command_substitution(
    value: str,
    *,
    decoder_steps: list[int],
) -> bool:
    if not value.startswith("$(") or not value.endswith(")"):
        return False
    try:
        tokens = shlex.split(value[2:-1].strip(), posix=True)
    except ValueError:
        return False
    if not tokens:
        return False
    if tokens[0].startswith("<"):
        referenced_path = tokens[0][1:]
        return len(tokens) == 1 and bool(
            _SHELL_PURE_REFERENCE_PATTERN.fullmatch(referenced_path)
        )
    if "|" in tokens:
        pipe_index = tokens.index("|")
        return (
            tokens.count("|") == 1
            and _is_safe_shell_printf(tokens[:pipe_index])
            and _is_safe_python_stdout_filter(
                tokens[pipe_index + 1 :],
                decoder_steps=decoder_steps,
            )
        )
    if tokens[0] == "printf":
        return _is_safe_shell_printf(tokens)
    if tokens[0] == "read_keychain":
        return (
            len(tokens) == 3
            and _SHELL_LOOKUP_REFERENCE_PATTERN.fullmatch(tokens[1]) is not None
            and _SHELL_LOOKUP_KEY_PATTERN.fullmatch(tokens[2]) is not None
        )
    return False


def _is_safe_shell_printf(tokens: Sequence[str]) -> bool:
    return (
        len(tokens) >= 3
        and tokens[0] == "printf"
        and tokens[1] in _SAFE_SHELL_PRINTF_FORMATS
        and all(
            _SHELL_PURE_REFERENCE_PATTERN.fullmatch(argument)
            for argument in tokens[2:]
        )
    )


def _is_safe_python_stdout_filter(
    tokens: Sequence[str],
    *,
    decoder_steps: list[int],
) -> bool:
    if len(tokens) != 5 or tuple(tokens[:4]) != ("python3", "-I", "-S", "-c"):
        return False
    try:
        tree = ast.parse(tokens[4])
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return False
    if not _python_decoder_statements_are_safe(tree.body):
        return False
    assignments: dict[str, list[ast.expr]] = {}
    inspected = 0
    try:
        for node in ast.walk(tree):
            inspected += 1
            if inspected > _MAX_PYTHON_SOURCE_NODES:
                return False
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if not isinstance(target, ast.Name):
                        return False
                    assignments.setdefault(target.id, []).append(node.value)
    except (MemoryError, RecursionError):
        return False

    stdout_values = 0
    try:
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            dotted_name = _python_dotted_name(node.func)
            if dotted_name == "print":
                file_values = [
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "file"
                ]
                if file_values:
                    if (
                        len(file_values) != 1
                        or len(node.keywords) != 1
                        or _python_dotted_name(file_values[0]) != "sys.stderr"
                    ):
                        return False
                    continue
                if (
                    len(node.args) != 1
                    or node.keywords
                    or not _is_runtime_decoder_expression(
                        node.args[0],
                        assignments,
                        remaining_steps=decoder_steps,
                    )
                ):
                    return False
                stdout_values += 1
                continue
            if not _is_permitted_python_decoder_call(
                node,
                assignments,
                remaining_steps=decoder_steps,
            ):
                return False
    except (MemoryError, RecursionError):
        return False
    return stdout_values == 1


def _python_decoder_statements_are_safe(
    statements: Sequence[ast.stmt],
) -> bool:
    for statement in statements:
        if isinstance(statement, ast.Import):
            if any(
                alias.asname is not None
                or alias.name not in {"base64", "json", "sys"}
                for alias in statement.names
            ):
                return False
            continue
        if isinstance(statement, ast.Assign):
            if not statement.targets or any(
                not isinstance(target, ast.Name)
                for target in statement.targets
            ):
                return False
            continue
        if isinstance(statement, (ast.Expr, ast.Raise, ast.Pass)):
            continue
        if isinstance(statement, ast.If):
            if not _python_decoder_statements_are_safe(
                statement.body
            ) or not _python_decoder_statements_are_safe(statement.orelse):
                return False
            continue
        if isinstance(statement, ast.Try):
            if (
                not _python_decoder_statements_are_safe(statement.body)
                or not _python_decoder_statements_are_safe(statement.orelse)
                or not _python_decoder_statements_are_safe(statement.finalbody)
                or any(
                    not _python_decoder_statements_are_safe(handler.body)
                    for handler in statement.handlers
                )
            ):
                return False
            continue
        return False
    return True


def _is_runtime_decoder_expression(
    expression: ast.expr,
    assignments: Mapping[str, Sequence[ast.expr]],
    *,
    remaining_steps: list[int],
    resolving: frozenset[str] = frozenset(),
    depth: int = 0,
) -> bool:
    remaining_steps[0] -= 1
    if remaining_steps[0] < 0:
        return False
    if depth > _MAX_SAFE_PYTHON_REFERENCE_DEPTH:
        return False
    next_depth = depth + 1
    if isinstance(expression, ast.Name):
        values = assignments.get(expression.id)
        if not values or expression.id in resolving:
            return False
        next_resolving = resolving | {expression.id}
        return all(
            _is_runtime_decoder_expression(
                value,
                assignments,
                remaining_steps=remaining_steps,
                resolving=next_resolving,
                depth=next_depth,
            )
            for value in values
        )
    if isinstance(expression, ast.Attribute):
        if _python_dotted_name(expression) == "sys.stdin":
            return True
        return _is_runtime_decoder_expression(
            expression.value,
            assignments,
            remaining_steps=remaining_steps,
            resolving=resolving,
            depth=next_depth,
        )
    if isinstance(expression, ast.Subscript):
        return (
            _is_runtime_decoder_expression(
                expression.value,
                assignments,
                remaining_steps=remaining_steps,
                resolving=resolving,
                depth=next_depth,
            )
            and isinstance(expression.slice, ast.Constant)
            and isinstance(expression.slice.value, (str, int))
        )
    if isinstance(expression, ast.IfExp):
        return _is_runtime_decoder_expression(
            expression.body,
            assignments,
            remaining_steps=remaining_steps,
            resolving=resolving,
            depth=next_depth,
        ) and (
            _is_runtime_decoder_expression(
                expression.orelse,
                assignments,
                remaining_steps=remaining_steps,
                resolving=resolving,
                depth=next_depth,
            )
            or (
                isinstance(expression.orelse, ast.Constant)
                and expression.orelse.value is None
            )
        )
    if not isinstance(expression, ast.Call):
        return False
    dotted_name = _python_dotted_name(expression.func)
    if dotted_name == "json.load":
        return (
            len(expression.args) == 1
            and not expression.keywords
            and _python_dotted_name(expression.args[0]) == "sys.stdin"
        )
    if dotted_name in {"json.loads", "base64.b64decode"}:
        if len(expression.args) != 1:
            return False
        if dotted_name == "json.loads" and expression.keywords:
            return False
        if dotted_name == "base64.b64decode" and any(
            keyword.arg != "validate"
            or not isinstance(keyword.value, ast.Constant)
            or keyword.value.value is not True
            for keyword in expression.keywords
        ):
            return False
        return _is_runtime_decoder_expression(
            expression.args[0],
            assignments,
            remaining_steps=remaining_steps,
            resolving=resolving,
            depth=next_depth,
        )
    if (
        isinstance(expression.func, ast.Attribute)
        and expression.func.attr == "get"
        and len(expression.args) in {1, 2}
        and not expression.keywords
        and isinstance(expression.args[0], ast.Constant)
        and isinstance(expression.args[0].value, str)
        and re.fullmatch(
            r"[A-Za-z_][A-Za-z0-9_.-]*",
            expression.args[0].value,
        )
        is not None
    ):
        return _is_runtime_decoder_expression(
            expression.func.value,
            assignments,
            remaining_steps=remaining_steps,
            resolving=resolving,
            depth=next_depth,
        ) and (
            len(expression.args) == 1
            or (
                isinstance(expression.args[1], ast.Constant)
                and expression.args[1].value is None
            )
        )
    return False


def _is_permitted_python_decoder_call(
    call: ast.Call,
    assignments: Mapping[str, Sequence[ast.expr]],
    *,
    remaining_steps: list[int],
) -> bool:
    dotted_name = _python_dotted_name(call.func)
    if _is_runtime_decoder_expression(
        call,
        assignments,
        remaining_steps=remaining_steps,
    ):
        return True
    if dotted_name == "isinstance":
        return len(call.args) == 2 and not call.keywords
    if dotted_name == "type":
        return len(call.args) == 1 and not call.keywords
    if dotted_name == "ValueError":
        return len(call.args) <= 1 and not call.keywords
    if dotted_name == "sys.exit":
        return (
            len(call.args) <= 1
            and not call.keywords
            and (
                not call.args
                or (
                    isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, int)
                )
            )
        )
    return False


def _is_safe_authorization_credential(
    raw_value: str,
    *,
    decoder_steps: list[int],
) -> bool:
    """Allow an exact shell reference when a quoted header leaves its closing quote."""
    if _is_safe_assigned_value(
        raw_value,
        decoder_steps=decoder_steps,
    ):
        return True
    value = raw_value.rstrip()
    if value.endswith("\\"):
        value = value[:-1].rstrip()
    if not value.endswith(("'", '"')):
        return False
    return bool(_PURE_REFERENCE_PATTERN.fullmatch(value[:-1].rstrip()))
