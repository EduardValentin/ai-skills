"""Repository layout and skill-root topology checks."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from pathlib import Path

from scripts.ai_skills_lib.core import SkillRecord, inspect_skill_layout
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    resolve_strict,
    skill_scope,
)


_ALLOWED_SKILL_ROOT_ENTRIES = frozenset(
    {"SKILL.md", "scripts", "references", "assets", "evals"}
)
_DIRECTORY_ENTRIES = _ALLOWED_SKILL_ROOT_ENTRIES - {"SKILL.md"}


def validate_repository_shape(root: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    skills_directory = root / "skills"
    layout = inspect_skill_layout(root)
    for path in layout.invalid_boundaries:
        issues.append(
            ValidationIssue(
                scope="repository",
                message=(
                    f"{path.relative_to(root)} must be a contained non-symlink directory"
                ),
            )
        )
    if (
        skills_directory not in layout.invalid_boundaries
        and skills_directory.exists()
    ):
        skill_documents = sorted(
            path
            for path in _iter_skill_tree(skills_directory)
            if path.name.casefold() == "skill.md"
        )
        for path in skill_documents:
            if path.name != "SKILL.md":
                issues.append(
                    ValidationIssue(
                        scope="repository",
                        message=f"{path.relative_to(root)} must be named SKILL.md",
                    )
                )
                continue
            relative = path.relative_to(skills_directory)
            if len(relative.parts) != 3:
                issues.append(
                    ValidationIssue(
                        scope="repository",
                        message=(
                            f"{path.relative_to(root)} must use "
                            "skills/<group>/<skill>/SKILL.md"
                        ),
                    )
                )

    for pattern in (
        "plugins/*/skills/*/SKILL.md",
        "codex/skills/*/SKILL.md",
        "claude/skills/*/SKILL.md",
    ):
        for path in sorted(root.glob(pattern)):
            if ".system" not in path.parts:
                issues.append(
                    ValidationIssue(
                        scope="repository",
                        message=f"duplicate public skill source: {path.relative_to(root)}",
                    )
                )

    if (root / "dist").exists():
        issues.append(ValidationIssue(scope="repository", message="dist/ must not exist"))
    return issues


def validate_discovered_layout(context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    name_counts = Counter(skill.name for skill in context.skills)
    for name, count in sorted(name_counts.items()):
        if count > 1:
            issues.append(
                ValidationIssue(
                    scope="repository",
                    message=f"duplicate skill name '{name}' appears {count} times",
                )
            )

    for skill in context.skills:
        if skill.root.name != skill.name:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=f"folder name '{skill.root.name}' must match skill name '{skill.name}'",
                )
            )
    return issues


def validate_skill_root(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    issues: list[ValidationIssue] = []
    try:
        root_entries = sorted(skill.root.iterdir())
    except OSError as error:
        return [ValidationIssue(scope=scope, message=f"cannot inspect skill root: {error}")]

    for entry in root_entries:
        if entry.name not in _ALLOWED_SKILL_ROOT_ENTRIES:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"unsupported skill-root entry: {entry.name}",
                )
            )
        elif entry.name in _DIRECTORY_ENTRIES and not entry.is_dir():
            issues.append(
                ValidationIssue(scope=scope, message=f"{entry.name} must be a directory")
            )

    resolved_root = skill.root.resolve()
    for path in _iter_skill_tree(skill.root):
        relative = path.relative_to(skill.root)
        if path.name == ".gitkeep":
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f".gitkeep placeholders are not allowed: {relative}",
                )
            )
        if path.is_symlink():
            resolution = resolve_strict(path)
            if resolution.error is not None:
                kind = (
                    "broken"
                    if isinstance(resolution.error, FileNotFoundError)
                    else "invalid"
                )
                issues.append(
                    ValidationIssue(scope=scope, message=f"{kind} symlink: {relative}")
                )
                continue
            target = resolution.resolved_path
            assert target is not None
            if not target.is_relative_to(resolved_root):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"symlink target must stay inside the skill: {relative}",
                    )
                )
        elif path.is_dir():
            try:
                is_empty = next(path.iterdir(), None) is None
            except OSError:
                is_empty = False
            if is_empty:
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=f"empty directory is not allowed: {relative}",
                    )
                )
    return issues


def _iter_skill_tree(root: Path) -> Iterator[Path]:
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = sorted(directory.iterdir(), reverse=True)
        except OSError:
            continue
        for child in children:
            yield child
            if child.is_dir() and not child.is_symlink():
                pending.append(child)
