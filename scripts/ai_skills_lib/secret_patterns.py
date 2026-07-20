"""Redacted high-confidence secret pattern definitions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from re import Pattern
from typing import Literal


@dataclass(frozen=True)
class SecretPattern:
    name: str
    category: str
    confidence: Literal["high"]
    regex: Pattern[str]
    value_group: str | None = None
    fake_prefix_allowed: bool = True


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
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----.*?"
            r"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
            re.DOTALL,
        ),
        fake_prefix_allowed=False,
    ),
    SecretPattern(
        name="github-token",
        category="access-token",
        confidence="high",
        regex=re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    ),
    SecretPattern(
        name="slack-token",
        category="access-token",
        confidence="high",
        regex=re.compile(r"\bxox[A-Za-z]-[A-Za-z0-9-]{20,}\b"),
    ),
    SecretPattern(
        name="aws-access-key-id",
        category="access-key-id",
        confidence="high",
        regex=re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
    ),
    SecretPattern(
        name="openai-api-key",
        category="api-key",
        confidence="high",
        regex=re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    ),
    SecretPattern(
        name="sensitive-assignment",
        category="assigned-secret",
        confidence="high",
        regex=re.compile(
            r"(?<![A-Za-z0-9_])(?:"
            r"[\"']?[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET)[\"']?"
            r"|os\.environ\[\s*[\"'][A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET)"
            r"[\"']\s*\]"
            r"|process\.env\.[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET)"
            r")"
            r"[ \t]*(?:=|:)[ \t]*"
            r"(?P<value>"
            r"\"[^\"\r\n]*\"|'[^'\r\n]*'"
            r"|\$\([^\r\n)]*\)[^\s#;,\r\n\"']*"
            r"|\{\{[^\r\n}]*\}\}[^\s#;,\r\n\"']*"
            r"|os\.environ\[\s*[\"'][A-Za-z_][A-Za-z0-9_]*[\"']\s*\]"
            r"[^\s#;,\r\n\"']*"
            r"|[^\s#;,\r\n\"']*)",
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
