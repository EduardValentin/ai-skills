"""Shared containment and high-confidence secret checks for authored files."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from scripts.ai_skills_lib.secret_patterns import (
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
_FAKE_VALUE_PATTERN = re.compile(r"FAKE_[A-Za-z0-9][A-Za-z0-9_.:/-]*\Z")
_BUNDLED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<target>(?:scripts|references|assets)/"
    r"[A-Za-z0-9._/-]+)(?![A-Za-z0-9._/\\-])"
)
_QUOTED_BUNDLED_PATH_PATTERN = re.compile(
    r"`(?P<target>(?:scripts|references|assets)/[^`\r\n]+)`"
)
_URI_PATTERN = re.compile(
    r"\b(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):/{2}[^\s<>\"']+"
)
_LOCAL_EVAL_RUNTIME_REFERENCE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:(?:\.{1,2}[/\\])*)evals[/\\]",
    re.IGNORECASE,
)
_PRIVATE_KEY_MARKER_PATTERN = re.compile(
    r"-----(?P<direction>BEGIN|END) "
    r"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
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
DEFAULT_MAXIMUM_JSON_BYTES = 4 * 1024 * 1024
DEFAULT_MAXIMUM_JSON_NODES = 100_000
DEFAULT_MAXIMUM_JSON_DEPTH = 64
DEFAULT_MAXIMUM_SECRET_SCAN_BYTES = 8 * 1024 * 1024
DEFAULT_MAXIMUM_SECRET_FINDINGS = 64
SENSITIVE_TEXT_REDACTION = "[REDACTED]"
SENSITIVE_TEXT_QUARANTINE = "[QUARANTINED: sensitive content could not be preserved]"


@dataclass(frozen=True)
class AuthoredFile:
    logical_path: Path
    resolved_path: Path


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
            probe = scan_static_secret_issues(text, source, maximum_findings=1)
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
        result = scan_static_secret_issues(text, source, maximum_findings=remaining)
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


def walk_authored_files(content_root: Path, skill_root: Path) -> Iterator[AuthoredFile]:
    """Walk regular files while rejecting escapes and directory cycles."""
    resolved_skill_root = resolve_strict(skill_root).resolved_path
    resolved_content_root = resolve_strict(content_root).resolved_path
    if resolved_skill_root is None or resolved_content_root is None:
        return
    if not resolved_content_root.is_dir() or not resolved_content_root.is_relative_to(
        resolved_skill_root
    ):
        return

    pending = [content_root]
    seen_directories: set[Path] = set()
    while pending:
        logical_directory = pending.pop()
        resolved_directory = resolve_strict(logical_directory).resolved_path
        if resolved_directory is None:
            continue
        if (
            resolved_directory in seen_directories
            or not resolved_directory.is_relative_to(resolved_skill_root)
        ):
            continue
        seen_directories.add(resolved_directory)
        try:
            children = sorted(logical_directory.iterdir(), reverse=True)
        except OSError:
            continue
        for logical_path in children:
            resolved_path = resolve_strict(logical_path).resolved_path
            if resolved_path is None or not resolved_path.is_relative_to(resolved_skill_root):
                continue
            if resolved_path.is_dir():
                pending.append(logical_path)
            elif resolved_path.is_file():
                yield AuthoredFile(logical_path=logical_path, resolved_path=resolved_path)


def read_text_fixture(source: AuthoredFile) -> str | None:
    """Read one authored UTF-8 text fixture, returning None for binary data."""
    try:
        content = source.resolved_path.read_bytes()
    except OSError:
        return None
    if b"\x00" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def extract_bundled_paths(text: str) -> tuple[str, ...]:
    """Extract clean-looking runtime file paths named in authored eval prose."""
    quoted = tuple(
        match.group("target") for match in _QUOTED_BUNDLED_PATH_PATTERN.finditer(text)
    )
    unquoted = tuple(
        match.group("target").rstrip(".,;:!?")
        for match in _BUNDLED_PATH_PATTERN.finditer(text)
    )
    return tuple(dict.fromkeys((*quoted, *unquoted)))


def contains_local_eval_runtime_reference(content: str | bytes) -> bool:
    """Return whether actor-visible text names local runner-only eval content."""
    if isinstance(content, bytes):
        if b"\x00" in content:
            return False
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return False
    else:
        text = content
        if "\x00" in text:
            return False

    uri_spans = tuple(
        match.span()
        for match in _URI_PATTERN.finditer(text)
        if match.group("scheme").lower() != "file"
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

    try:
        document = json.loads(text, parse_constant=reject_constant)
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
) -> SecretScanResult:
    """Classify and sanitize bounded high-confidence credential evidence."""
    if maximum_findings <= 0:
        raise ValueError("maximum secret findings must be positive")
    candidates: list[_SensitiveCandidate] = []
    truncated = False
    boundary_uncertain = False
    escaped_context_classifications: dict[str, str] = {}
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
            if pattern.name in {
                "escaped-authorization-context",
                "escaped-cookie-context",
            }:
                classification = escaped_context_classifications.get(pattern.name)
                if classification is None:
                    classification = _classify_escaped_json_sensitive_context(
                        text,
                        pattern.name,
                    )
                    escaped_context_classifications[pattern.name] = classification
                if classification == "safe":
                    continue
                boundary_uncertain = True
                start = match.start()
                end = match.end()
            elif pattern.value_group is not None:
                value = match.group(pattern.value_group)
                classification = _classify_pattern_value(pattern, match, value)
                if classification == "safe":
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


def _private_key_blocks(text: str) -> Iterator[tuple[int, int]]:
    open_block: int | None = None
    for marker in _PRIVATE_KEY_MARKER_PATTERN.finditer(text):
        if marker.group("direction") == "BEGIN":
            if open_block is None:
                open_block = marker.start()
        elif open_block is not None:
            yield open_block, marker.end()
            open_block = None


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
) -> str:
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
        safe = _is_safe_cookie_value(match.group("name"), value)
        return "safe" if safe else "sensitive"
    if pattern.name == "authorization-value":
        parts = value.strip().split(None, 1)
        credential = parts[1] if len(parts) == 2 else value
        return (
            "safe"
            if _is_safe_authorization_credential(credential)
            else "sensitive"
        )
    return "safe" if _is_safe_assigned_value(value) else "sensitive"


def _classify_escaped_json_sensitive_context(
    text: str,
    pattern_name: str,
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


def _is_safe_cookie_value(name: str, value: str) -> bool:
    segments = value.split(";")
    if name.casefold() == "set-cookie":
        segments = segments[:1]
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        candidate = segment.split("=", 1)[1] if "=" in segment else segment
        if not _is_safe_assigned_value(candidate):
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


def _is_safe_assigned_value(raw_value: str) -> bool:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if not value:
        return True
    if _PURE_REFERENCE_PATTERN.fullmatch(value) or _FAKE_VALUE_PATTERN.fullmatch(value):
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


def _is_safe_authorization_credential(raw_value: str) -> bool:
    """Allow an exact shell reference when a quoted header leaves its closing quote."""
    if _is_safe_assigned_value(raw_value):
        return True
    value = raw_value.rstrip()
    if value.endswith("\\"):
        value = value[:-1].rstrip()
    if not value.endswith(("'", '"')):
        return False
    return bool(_PURE_REFERENCE_PATTERN.fullmatch(value[:-1].rstrip()))
