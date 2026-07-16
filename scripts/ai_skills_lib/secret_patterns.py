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
