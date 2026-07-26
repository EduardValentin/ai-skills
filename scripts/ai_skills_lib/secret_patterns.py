"""Redacted high-confidence secret pattern definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from re import Pattern
from typing import Literal


_ASCII_TOKEN_START = r"(?<![A-Za-z0-9_])"
_ASCII_TOKEN_END = r"(?![A-Za-z0-9_])"
_CREDENTIAL_KEY_SUFFIX = (
    r"(?:"
    r"API(?:[_-]?KEY|[_-]?TOKEN)"
    r"|ACCESS(?:[_-]?KEY(?:[_-]?ID)?|[_-]?TOKEN)"
    r"|AUTH[_-]?TOKEN"
    r"|BEARER[_-]?TOKEN"
    r"|CLIENT[_-]?SECRET"
    r"|ID[_-]?TOKEN"
    r"|OAUTH[_-]?TOKEN"
    r"|PRIVATE[_-]?KEY"
    r"|REFRESH[_-]?TOKEN"
    r"|SECRET(?:[_-]?ACCESS[_-]?KEY|[_-]?KEY)?"
    r"|SESSION[_-]?TOKEN"
    r"|PASSWORD|PASSWD|PASSPHRASE"
    r"|CREDENTIALS?"
    r"|TOKEN"
    r")"
)
_CREDENTIAL_KEY_PREFIX = (
    r"(?:"
    r"[A-Z][A-Z0-9]*(?:[_-][A-Z][A-Z0-9]*)*[_-]"
    r"|[A-Z][A-Z0-9]*?"
    r")?"
)
_SENSITIVE_CREDENTIAL_KEY = (
    rf"(?i:{_CREDENTIAL_KEY_PREFIX}{_CREDENTIAL_KEY_SUFFIX})"
)
_ENVIRONMENT_CREDENTIAL_TARGET = (
    rf"(?:{_SENSITIVE_CREDENTIAL_KEY}"
    rf"|os\.environ\[\s*[\"']{_SENSITIVE_CREDENTIAL_KEY}[\"']\s*\]"
    rf"|process\.env\.{_SENSITIVE_CREDENTIAL_KEY})"
)
_ASSIGNED_SCALAR_VALUE = (
    r"\"[^\"\r\n]*\"|'[^'\r\n]*'"
    r"|\$\([^\r\n)]*\)[^\s#;,\r\n\"']*"
    r"|\{\{[^\r\n}]*\}\}[^\s#;,\r\n\"']*"
    r"|os\.environ\[\s*[\"'][A-Za-z_][A-Za-z0-9_]*[\"']\s*\]"
    r"[^\s#;,\r\n\"']*"
    r"|[^\s#;,\r\n\"']*"
)
_QUOTED_ASSIGNED_SCALAR_VALUE = r"\"[^\"\r\n]*\"|'[^'\r\n]*'"
PRIVATE_KEY_LABEL_PATTERN = (
    r"(?:"
    r"(?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY"
    r"|PGP (?:PRIVATE|SECRET) KEY BLOCK"
    r")"
)


@dataclass(frozen=True)
class SecretPattern:
    name: str
    category: str
    confidence: Literal["high"]
    regex: Pattern[str]
    value_group: str | None = None
    fake_prefix_allowed: bool = True
    blocks_overlapping_assignments_when_safe: bool = False


@dataclass(frozen=True)
class SecretMatch:
    pattern: str
    category: str
    confidence: Literal["high"]
    source: Path
    line: int
    column: int


SECRET_PATTERNS: tuple[SecretPattern, ...] = (
    SecretPattern(
        name="private-key-block",
        category="private-key",
        confidence="high",
        regex=re.compile(
            rf"-----BEGIN (?P<label>{PRIVATE_KEY_LABEL_PATTERN})-----.*?"
            r"-----END (?P=label)-----",
            re.DOTALL,
        ),
        fake_prefix_allowed=False,
    ),
    SecretPattern(
        name="github-token",
        category="access-token",
        confidence="high",
        regex=re.compile(
            _ASCII_TOKEN_START
            + (
                r"(?:gh[pousr]_[A-Za-z0-9_.-]{20,2048}"
                r"|github_pat_[A-Za-z0-9_.-]{20,2048})"
            )
            + _ASCII_TOKEN_END
        ),
    ),
    SecretPattern(
        name="slack-token",
        category="access-token",
        confidence="high",
        regex=re.compile(
            _ASCII_TOKEN_START
            + (
                r"(?:xox[A-Za-z]-[A-Za-z0-9-]{20,}"
                r"|xapp-[0-9]+-[A-Z0-9]{8,}-[0-9]{10,}-"
                r"[A-Za-z0-9]{20,2048})"
            )
            + _ASCII_TOKEN_END
        ),
    ),
    SecretPattern(
        name="aws-access-key-id",
        category="access-key-id",
        confidence="high",
        regex=re.compile(
            _ASCII_TOKEN_START + r"(?:AKIA|ASIA)[A-Z0-9]{16}" + _ASCII_TOKEN_END
        ),
    ),
    SecretPattern(
        name="openai-api-key",
        category="api-key",
        confidence="high",
        regex=re.compile(
            _ASCII_TOKEN_START + r"sk-[A-Za-z0-9_-]{20,}" + _ASCII_TOKEN_END
        ),
    ),
    SecretPattern(
        name="sensitive-assignment",
        category="assigned-secret",
        confidence="high",
        regex=re.compile(
            rf"^[ \t]*(?:-[ \t]+)?(?:export[ \t]+)?"
            rf"{_ENVIRONMENT_CREDENTIAL_TARGET}[ \t]*(?:=|:)[ \t]*"
            r"(?P<value>[^\r\n]*)",
            re.MULTILINE,
        ),
        value_group="value",
        blocks_overlapping_assignments_when_safe=True,
    ),
    SecretPattern(
        name="sensitive-assignment",
        category="assigned-secret",
        confidence="high",
        regex=re.compile(
            rf"(?<![A-Za-z0-9_])[\"']{_SENSITIVE_CREDENTIAL_KEY}[\"']"
            rf"[ \t]*(?:=|:)[ \t]*(?P<value>{_ASSIGNED_SCALAR_VALUE})",
            re.MULTILINE,
        ),
        value_group="value",
    ),
    SecretPattern(
        name="sensitive-assignment",
        category="assigned-secret",
        confidence="high",
        regex=re.compile(
            rf"(?:\{{|,)[ \t\r\n]*{_SENSITIVE_CREDENTIAL_KEY}"
            rf"[ \t]*:[ \t]*(?P<value>{_QUOTED_ASSIGNED_SCALAR_VALUE})",
            re.MULTILINE,
        ),
        value_group="value",
    ),
    SecretPattern(
        name="sensitive-assignment",
        category="assigned-secret",
        confidence="high",
        regex=re.compile(
            rf"(?<![A-Za-z0-9_\\]){_ENVIRONMENT_CREDENTIAL_TARGET}"
            rf"[ \t]*=[ \t]*(?P<value>{_ASSIGNED_SCALAR_VALUE})",
            re.MULTILINE,
        ),
        value_group="value",
    ),
)


def redact_runtime_secrets(text: str) -> str:
    """Redact high-confidence values and authorization syntax from runtime evidence."""
    redacted = re.sub(
        r"\bFAKE_[A-Za-z0-9][A-Za-z0-9_.:/-]*",
        "[REDACTED]",
        text,
    )
    for pattern in SECRET_PATTERNS:
        redacted = pattern.regex.sub("[REDACTED]", redacted)
    redacted = re.sub(
        r"(?i)\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*[^\r\n]+",
        "[REDACTED]",
        redacted,
    )
    return re.sub(
        r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]+=*",
        "Bearer [REDACTED]",
        redacted,
    )


def bounded_redacted_runtime_text(text: str, maximum_bytes: int) -> str:
    """Redact one durable runtime scalar and enforce its UTF-8 byte limit."""
    if maximum_bytes <= 0:
        raise ValueError("runtime text byte limit must be positive")
    redacted = redact_runtime_secrets(text)
    encoded = redacted.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return redacted
    marker = "[TRUNCATED]"
    budget = max(0, maximum_bytes - len(marker.encode("ascii")))
    return encoded[:budget].decode("utf-8", errors="ignore") + marker
