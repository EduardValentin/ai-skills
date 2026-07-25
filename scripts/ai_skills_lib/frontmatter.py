"""Strict YAML frontmatter parsing and Agent Skills field validation."""

from __future__ import annotations

from pathlib import Path
import re

from strictyaml import load
from strictyaml.ruamel.error import YAMLError


_ALLOWED_FIELDS = frozenset(
    {"name", "description", "license", "compatibility", "allowed-tools", "metadata"}
)
_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")


def parse_skill_frontmatter(text: str, source: Path) -> dict[str, object]:
    """Parse and validate the YAML frontmatter at the start of a skill file."""
    document = _extract_frontmatter_document(text, source)
    try:
        parsed = load(document).data
    except YAMLError as error:
        raise ValueError(f"{source}: invalid YAML frontmatter") from error

    if not isinstance(parsed, dict):
        raise ValueError(f"{source}: frontmatter must be a mapping")

    unknown_fields = set(parsed) - _ALLOWED_FIELDS
    if unknown_fields:
        raise ValueError(f"{source}: unsupported top-level frontmatter field")

    _validate_name(parsed, source)
    _validate_required_string(parsed, "description", source, maximum_length=1024)
    _validate_optional_string(parsed, "license", source)
    _validate_optional_string(parsed, "compatibility", source, maximum_length=500)
    _validate_optional_scalar_string(parsed, "allowed-tools", source)
    _validate_metadata(parsed, source)
    return parsed


def _extract_frontmatter_document(text: str, source: Path) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{source}: missing YAML frontmatter")

    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            return "".join(lines[1:index])

    raise ValueError(f"{source}: missing YAML frontmatter")


def _validate_name(frontmatter: dict[str, object], source: Path) -> None:
    name = frontmatter.get("name")
    if not isinstance(name, str) or not 1 <= len(name) <= 64 or not _NAME_PATTERN.fullmatch(name):
        raise ValueError(f"{source}: invalid name")


def _validate_required_string(
    frontmatter: dict[str, object], field: str, source: Path, maximum_length: int | None = None
) -> None:
    value = frontmatter.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: {field} must be a non-empty scalar string")
    if maximum_length is not None and len(value) > maximum_length:
        raise ValueError(f"{source}: {field} must be at most {maximum_length} characters")


def _validate_optional_string(
    frontmatter: dict[str, object], field: str, source: Path, maximum_length: int | None = None
) -> None:
    if field not in frontmatter:
        return
    _validate_required_string(frontmatter, field, source, maximum_length)


def _validate_optional_scalar_string(frontmatter: dict[str, object], field: str, source: Path) -> None:
    if field in frontmatter and not isinstance(frontmatter[field], str):
        raise ValueError(f"{source}: {field} must be a scalar string")


def _validate_metadata(frontmatter: dict[str, object], source: Path) -> None:
    if "metadata" not in frontmatter:
        return

    metadata = frontmatter["metadata"]
    if not isinstance(metadata, dict):
        raise ValueError(f"{source}: metadata must be a mapping")
    if not all(isinstance(key, str) and isinstance(value, str) for key, value in metadata.items()):
        raise ValueError(f"{source}: metadata values must be scalar strings")
