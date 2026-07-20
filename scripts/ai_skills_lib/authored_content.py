"""Shared containment and high-confidence secret checks for authored files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from scripts.ai_skills_lib.secret_patterns import SECRET_PATTERNS, SecretMatch


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


@dataclass(frozen=True)
class AuthoredFile:
    logical_path: Path
    resolved_path: Path


@dataclass(frozen=True)
class StrictPathResolution:
    resolved_path: Path | None
    error: OSError | RuntimeError | None


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


def find_static_secret_issues(text: str, source: Path) -> list[SecretMatch]:
    """Return high-confidence authored credential values without exposing them."""
    findings: list[SecretMatch] = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.regex.finditer(text):
            if pattern.value_group is not None:
                value = match.group(pattern.value_group)
                if _is_safe_assigned_value(value):
                    continue
                start = match.start(pattern.value_group)
            else:
                start = match.start()
                if pattern.fake_prefix_allowed and _has_fake_prefix(text, start):
                    continue

            line = text.count("\n", 0, start) + 1
            last_newline = text.rfind("\n", 0, start)
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
    return findings


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
