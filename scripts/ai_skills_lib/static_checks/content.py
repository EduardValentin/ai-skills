"""Contained authored-content traversal and content-level checks."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from itertools import chain
import os
from pathlib import Path, PurePosixPath
import re

from scripts.ai_skills_lib.authored_content import (
    AuthoredContentComplexityError,
    AuthoredContentReadError,
    AuthoredContentTooLarge,
    AuthoredFile,
    authored_file,
    extract_bundled_paths,
    find_additional_decoded_json_secret_issues,
    find_static_secret_issues,
    find_static_secret_issues_in_bytes,
    read_bounded_authored_bytes,
    resolve_strict,
    walk_authored_files,
)
from scripts.ai_skills_lib.bounded_json import (
    BoundedJsonError,
    strict_bounded_json_loads,
)
from scripts.ai_skills_lib.core import SkillRecord
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.secret_patterns import SecretMatch
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    render_safe_diagnostic_path,
    render_safe_diagnostic_text,
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
_MAX_AUTHORED_VALIDATION_BYTES = 64 * 1024 * 1024
_MAX_CONTENT_ISSUES_PER_CATEGORY = 128
_MAX_LOCAL_REFERENCE_TARGETS = 1024


def read_authored_text(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile
) -> tuple[str | None, list[ValidationIssue]]:
    content, issues = read_authored_content(context, skill, source)
    if content is None:
        return None, issues
    try:
        return content.decode("utf-8"), []
    except UnicodeDecodeError as error:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    "cannot read "
                    f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}: "
                    f"{error}"
                ),
            )
        ]


def read_authored_content(
    context: ValidationContext, skill: SkillRecord, source: AuthoredFile
) -> tuple[bytes | None, list[ValidationIssue]]:
    try:
        return (
            read_bounded_authored_bytes(
                source,
                maximum_bytes=_MAX_AUTHORED_VALIDATION_BYTES,
                allowed_root=skill.root,
                containment_root=context.root,
                budget=context.budget,
            ),
            [],
        )
    except AuthoredContentTooLarge:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    "cannot read "
                    f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}: "
                    "file exceeds the validation byte limit"
                ),
            )
        ]
    except AuthoredContentReadError as error:
        return None, [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    "cannot read "
                    f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}: "
                    f"{error}"
                ),
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
    for source in walk_authored_files(
        skill.root / "references",
        skill.root,
        budget=context.budget,
    ):
        content, read_issues = read_authored_content(context, skill, source)
        issues.extend(read_issues)
        if content is None:
            continue
        issues.extend(_content_secret_issues(context, skill, source, content))
        if source.logical_path.suffix != ".md":
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        "cannot read "
                        f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}: "
                        f"{error}"
                    ),
                )
            )
            continue
        issues.extend(
            _personal_path_issues(
                context,
                skill,
                source.logical_path,
                text,
            )
        )
        issues.extend(
            _local_reference_issues(
                context,
                skill,
                source.logical_path,
                text,
            )
        )
    return issues


def validate_asset_files(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for source in walk_authored_files(
        skill.root / "assets",
        skill.root,
        budget=context.budget,
    ):
        content, read_issues = read_authored_content(context, skill, source)
        issues.extend(read_issues)
        if content is not None:
            issues.extend(_content_secret_issues(context, skill, source, content))
    return issues


def validate_script_files(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    scope = skill_scope(context, skill)
    for source in walk_authored_files(
        skill.root / "scripts",
        skill.root,
        budget=context.budget,
    ):
        if not os.access(source.resolved_path, os.X_OK):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)} "
                        "must be executable"
                    ),
                )
            )
        content, read_issues = read_authored_content(context, skill, source)
        issues.extend(read_issues)
        if content is None:
            continue
        issues.extend(_content_secret_issues(context, skill, source, content))
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "cannot read "
                        f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)}: "
                        f"{error}"
                    ),
                )
            )
            continue
        issues.extend(_personal_path_issues(context, skill, source.logical_path, text))
    return issues


def extract_markdown_destinations(text: str) -> list[str]:
    return list(_markdown_destinations(text))


def _markdown_destinations(text: str) -> Iterator[str]:
    yield from _inline_markdown_destinations(text)
    for match in _REFERENCE_DEFINITION_PREFIX.finditer(text):
        line_end = text.find("\n", match.end())
        fragment = text[match.end() : line_end if line_end >= 0 else len(text)]
        destination, _ = _parse_destination(fragment, 0, closing_parenthesis=False)
        if destination is not None:
            yield destination


def is_external_reference(target: str) -> bool:
    if target.startswith("//"):
        return True
    scheme = re.match(r"^(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*):", target)
    if scheme is None:
        return False
    name = scheme.group("scheme")
    if name.lower() == "file" or len(name) == 1:
        return False
    return True


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
    issues: list[ValidationIssue] = []
    for pattern in (_POSIX_PERSONAL_PATH_PATTERN, _WINDOWS_PERSONAL_PATH_PATTERN):
        uri_spans = _SortedSpanCursor(
            match.span() for match in _URI_PATTERN.finditer(text)
        )
        scanned_to = 0
        line = 1
        last_newline = -1
        for match in pattern.finditer(text):
            if uri_spans.overlaps(match.span()) or _is_documentation_user(
                match.group("user")
            ):
                continue
            segment_end = match.start()
            added_lines = text.count("\n", scanned_to, segment_end)
            if added_lines:
                line += added_lines
                last_newline = text.rfind("\n", scanned_to, segment_end)
            scanned_to = segment_end
            column = match.start() - last_newline
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        f"{render_safe_diagnostic_path(source, relative_to=skill.root)}:"
                        f"{line}:{column} contains a personal "
                        "absolute path"
                    ),
                )
            )
            if len(issues) >= _MAX_CONTENT_ISSUES_PER_CATEGORY:
                issues.append(_content_limit_issue(context, skill, source, "personal paths"))
                return issues
    return issues


def _secret_issues(
    context: ValidationContext, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            scope=skill_scope(context, skill),
            message=(
                f"{render_safe_diagnostic_path(source, relative_to=skill.root)}:"
                f"{finding.line}:{finding.column}: "
                f"high-confidence secret {finding.pattern} ({finding.category}); value redacted"
            ),
        )
        for finding in find_static_secret_issues(text, source)
    ]


def _content_secret_issues(
    context: ValidationContext,
    skill: SkillRecord,
    source: AuthoredFile,
    content: bytes,
) -> list[ValidationIssue]:
    raw_findings = tuple(
        find_static_secret_issues_in_bytes(
            content,
            source.logical_path,
        )
    )
    issues = _secret_finding_issues(
        context,
        skill,
        source.logical_path,
        raw_findings,
    )
    if source.logical_path.suffix.casefold() != ".json":
        return issues
    try:
        document = strict_bounded_json_loads(
            content,
            maximum_bytes=_MAX_AUTHORED_VALIDATION_BYTES,
        )
        decoded_findings = find_additional_decoded_json_secret_issues(
            document,
            source.logical_path,
            maximum_bytes=_MAX_AUTHORED_VALIDATION_BYTES,
            raw_findings=raw_findings,
        )
    except BoundedJsonError as error:
        issues.append(
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    f"{render_safe_diagnostic_path(source.logical_path, relative_to=skill.root)} "
                    "contains "
                    f"invalid JSON: {error}"
                ),
            )
        )
        return issues
    issues.extend(
        _secret_finding_issues(
            context,
            skill,
            source.logical_path,
            decoded_findings,
            decoded=True,
        )
    )
    return issues


def _secret_finding_issues(
    context: ValidationContext,
    skill: SkillRecord,
    source: Path,
    findings: Iterable[SecretMatch],
    *,
    decoded: bool = False,
) -> list[ValidationIssue]:
    location = " after JSON decoding" if decoded else ""
    return [
        ValidationIssue(
            scope=skill_scope(context, skill),
            message=(
                f"{render_safe_diagnostic_path(source, relative_to=skill.root)}:"
                f"{finding.line}:{finding.column}: "
                f"high-confidence secret{location} {finding.pattern} "
                f"({finding.category}); value redacted"
            ),
        )
        for finding in findings
    ]


def _local_reference_issues(
    context: ValidationContext, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    try:
        bundled_paths = extract_bundled_paths(
            text,
            maximum_paths=_MAX_LOCAL_REFERENCE_TARGETS,
        )
    except AuthoredContentComplexityError:
        return [_content_limit_issue(context, skill, source, "local references")]

    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    inspected = 0
    for target in chain(_markdown_destinations(text), bundled_paths):
        inspected += 1
        if inspected > _MAX_LOCAL_REFERENCE_TARGETS:
            issues.append(_content_limit_issue(context, skill, source, "local references"))
            return issues
        if target in seen:
            continue
        seen.add(target)
        issues.extend(_validate_local_target(context, skill, source, target))
        if len(issues) >= _MAX_CONTENT_ISSUES_PER_CATEGORY:
            issues.append(_content_limit_issue(context, skill, source, "local references"))
            return issues
    return issues


def _content_limit_issue(
    context: ValidationContext,
    skill: SkillRecord,
    source: Path,
    category: str,
) -> ValidationIssue:
    return ValidationIssue(
        scope=skill_scope(context, skill),
        message=(
            f"{render_safe_diagnostic_path(source, relative_to=skill.root)} "
            f"exceeds the static {category} "
            "inspection limit"
        ),
    )


def _validate_local_target(
    context: ValidationContext, skill: SkillRecord, source: Path, raw_target: str
) -> list[ValidationIssue]:
    target = raw_target[1:-1] if raw_target.startswith("<") and raw_target.endswith(">") else raw_target
    if is_external_reference(target) or target.startswith("#"):
        return []
    if target.lower().startswith("file:"):
        return [
            ValidationIssue(
                scope=skill_scope(context, skill),
                message=(
                    f"{render_safe_diagnostic_path(source, relative_to=skill.root)} "
                    "local reference must be "
                    f"skill-relative: {render_safe_diagnostic_text(target)}"
                ),
            )
        ]
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return []

    scope = skill_scope(context, skill)
    pure_path = PurePosixPath(target)
    if ".." in pure_path.parts:
        return [
            ValidationIssue(
                scope=scope,
                message=(
                    f"{render_safe_diagnostic_path(source, relative_to=skill.root)} "
                    "local reference must not contain '..': "
                    f"{render_safe_diagnostic_text(target)}"
                ),
            )
        ]
    if (
        pure_path.is_absolute()
        or target.startswith("~")
        or "\\" in target
        or re.match(r"^[A-Za-z]:", target)
    ):
        return [
            ValidationIssue(
                scope=scope,
                message=(
                    f"{render_safe_diagnostic_path(source, relative_to=skill.root)} "
                    "reference must be a clean skill-relative path: "
                    f"{render_safe_diagnostic_text(target)}"
                ),
            )
        ]

    referenced = authored_file(skill.root / pure_path, skill.root)
    if referenced is None:
        return [
            ValidationIssue(
                scope=scope,
                message=(
                    "referenced local file does not exist: "
                    f"{render_safe_diagnostic_text(target)}"
                ),
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


class _SortedSpanCursor:
    def __init__(self, spans: Iterator[tuple[int, int]]) -> None:
        self._spans = iter(spans)
        self._current = next(self._spans, None)

    def overlaps(self, span: tuple[int, int]) -> bool:
        while self._current is not None and self._current[1] <= span[0]:
            self._current = next(self._spans, None)
        return bool(
            self._current is not None
            and span[0] < self._current[1]
            and self._current[0] < span[1]
        )


def _is_documentation_user(user: str) -> bool:
    return bool(
        re.fullmatch(r"<[^<>/\\]+>", user)
        or re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", user)
        or re.fullmatch(r"\$[A-Za-z_][A-Za-z0-9_]*", user)
        or re.fullmatch(r"\{[A-Za-z_][A-Za-z0-9_]*\}", user)
        or re.fullmatch(r"%[A-Za-z_][A-Za-z0-9_]*%", user)
    )
