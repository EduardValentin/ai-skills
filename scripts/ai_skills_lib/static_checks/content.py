"""Contained authored-content traversal and content-level checks."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path, PurePosixPath
import re

from scripts.ai_skills_lib.authored_content import (
    AuthoredFile,
    authored_file,
    extract_bundled_paths,
    find_static_secret_issues,
    read_text_fixture,
    resolve_strict,
    walk_authored_files,
)
from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    skill_scope,
)


_REFERENCE_DEFINITION_PREFIX = re.compile(
    r"^[ \t]{0,3}\[(?:\\.|[^\]])+\]:[ \t]*", re.MULTILINE
)
_URI_PATTERN = re.compile(r"\b[A-Za-z][A-Za-z0-9+.-]*://[^\s<>\"']+")
_POSIX_PERSONAL_PATH_PATTERN = re.compile(
    r"(?P<prefix>/(?:Users|home)/)(?P<user>[^/\s,;.)]+|<[^<>]+>|\$\{[^}]+\})"
)
_WINDOWS_PERSONAL_PATH_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z]:\\Users\\)(?P<user>[^\\\s,;.)]+|<[^<>]+>)"
)
def read_authored_text(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile
) -> tuple[str | None, list[ValidationIssue]]:
    try:
        return source.resolved_path.read_text(encoding="utf-8"), []
    except (OSError, UnicodeDecodeError) as error:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=f"cannot read {source.logical_path.name}: {error}",
            )
        ]


def validate_skill_document(
    context: ValidationContext, skill: SkillRecord, text: str
) -> list[ValidationIssue]:
    return _validate_authored_text(context, skill, skill.path, text)


def validate_reference_files(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for source in walk_authored_files(skill.root / "references", skill.root):
        if source.logical_path.suffix != ".md":
            continue
        text, read_issues = read_authored_text(context, skill, source)
        issues.extend(read_issues)
        if text is not None:
            issues.extend(_validate_authored_text(context, skill, source.logical_path, text))
    return issues


def validate_script_files(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    scope = skill_scope(context, skill)
    for source in walk_authored_files(skill.root / "scripts", skill.root):
        if not os.access(source.resolved_path, os.X_OK):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"{source.logical_path.relative_to(skill.root)} must be executable",
                )
            )
        text, read_issues = read_authored_text(context, skill, source)
        issues.extend(read_issues)
        if text is not None:
            issues.extend(_personal_path_issues(context, skill, source.logical_path, text))
            issues.extend(_secret_issues(context, skill, source.logical_path, text))
    return issues


def extract_markdown_destinations(text: str) -> list[str]:
    destinations = list(_inline_markdown_destinations(text))
    for match in _REFERENCE_DEFINITION_PREFIX.finditer(text):
        line_end = text.find("\n", match.end())
        fragment = text[match.end() : line_end if line_end >= 0 else len(text)]
        destination, _ = _parse_destination(fragment, 0, closing_parenthesis=False)
        if destination is not None:
            destinations.append(destination)
    return destinations


def is_external_reference(target: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)) or target.startswith("//")


def _validate_authored_text(
    context: ValidationContext, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    issues = _personal_path_issues(context, skill, source, text)
    issues.extend(_secret_issues(context, skill, source, text))
    issues.extend(_local_reference_issues(context, skill, source, text))
    return issues


def _personal_path_issues(
    context: ValidationContext, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    uri_spans = [match.span() for match in _URI_PATTERN.finditer(text)]
    issues: list[ValidationIssue] = []
    for pattern in (_POSIX_PERSONAL_PATH_PATTERN, _WINDOWS_PERSONAL_PATH_PATTERN):
        for match in pattern.finditer(text):
            if _overlaps_any(match.span(), uri_spans) or _is_documentation_user(
                match.group("user")
            ):
                continue
            line = text.count("\n", 0, match.start()) + 1
            last_newline = text.rfind("\n", 0, match.start())
            column = match.start() - last_newline
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        f"{source.relative_to(skill.root)}:{line}:{column} contains a personal "
                        "absolute path"
                    ),
                )
            )
    return issues


def _secret_issues(
    context: ValidationContext, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            scope=skill_scope(context, skill),
            message=(
                f"{source.relative_to(skill.root)}:{finding.line}:{finding.column}: "
                f"high-confidence secret {finding.pattern} ({finding.category}); value redacted"
            ),
        )
        for finding in find_static_secret_issues(text, source)
    ]


def _local_reference_issues(
    context: ValidationContext, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    targets = extract_markdown_destinations(text)
    targets.extend(extract_bundled_paths(text))
    issues: list[ValidationIssue] = []
    for target in targets:
        issues.extend(_validate_local_target(context, skill, source, target))
    return issues


def _validate_local_target(
    context: ValidationContext, skill: SkillRecord, source: Path, raw_target: str
) -> list[ValidationIssue]:
    target = raw_target[1:-1] if raw_target.startswith("<") and raw_target.endswith(">") else raw_target
    if is_external_reference(target) or target.startswith("#"):
        return []
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return []

    scope = skill_scope(context, skill)
    pure_path = PurePosixPath(target)
    if ".." in pure_path.parts:
        return [
            ValidationIssue(
                scope=scope,
                message=f"{source.relative_to(skill.root)} local reference must not contain '..': {target}",
            )
        ]
    if pure_path.is_absolute() or target.startswith("~") or "\\" in target:
        return [
            ValidationIssue(
                scope=scope,
                message=f"{source.relative_to(skill.root)} reference must be a clean skill-relative path: {target}",
            )
        ]

    referenced = authored_file(skill.root / pure_path, skill.root)
    if referenced is None:
        return [
            ValidationIssue(
                scope=scope,
                message=f"referenced local file does not exist: {target}",
            )
        ]
    return []


def _inline_markdown_destinations(text: str) -> Iterator[str]:
    cursor = 0
    while True:
        marker = text.find("](", cursor)
        if marker < 0:
            return
        destination, end = _parse_destination(text, marker + 2, closing_parenthesis=True)
        if destination is not None:
            yield destination
        cursor = max(end, marker + 2)


def _parse_destination(
    text: str, start: int, *, closing_parenthesis: bool
) -> tuple[str | None, int]:
    cursor = start
    while cursor < len(text) and text[cursor] in " \t":
        cursor += 1
    if cursor >= len(text):
        return None, cursor

    if text[cursor] == "<":
        cursor += 1
        characters: list[str] = []
        while cursor < len(text):
            character = text[cursor]
            if character == "\\" and cursor + 1 < len(text):
                characters.append(text[cursor + 1])
                cursor += 2
            elif character == ">":
                return "".join(characters), cursor + 1
            elif character == "\n":
                return None, cursor
            else:
                characters.append(character)
                cursor += 1
        return None, cursor

    characters = []
    nested_parentheses = 0
    while cursor < len(text):
        character = text[cursor]
        if character == "\\" and cursor + 1 < len(text):
            characters.append(text[cursor + 1])
            cursor += 2
            continue
        if closing_parenthesis and character == "(":
            nested_parentheses += 1
            characters.append(character)
            cursor += 1
            continue
        if closing_parenthesis and character == ")":
            if nested_parentheses == 0:
                return "".join(characters), cursor + 1
            nested_parentheses -= 1
            characters.append(character)
            cursor += 1
            continue
        if character.isspace():
            return "".join(characters) or None, cursor
        characters.append(character)
        cursor += 1
    return ("".join(characters) or None), cursor


def _overlaps_any(span: tuple[int, int], candidates: list[tuple[int, int]]) -> bool:
    return any(span[0] < candidate[1] and candidate[0] < span[1] for candidate in candidates)


def _is_documentation_user(user: str) -> bool:
    return bool(
        re.fullmatch(r"<[^<>/\\]+>", user)
        or re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", user)
        or re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", user)
        or re.fullmatch(r"\{[A-Za-z_][A-Za-z0-9_]*\}", user)
        or re.fullmatch(r"%[A-Za-z_][A-Za-z0-9_]*%", user)
    )
