"""Shared repository and public-skill discovery helpers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from scripts.ai_skills_lib.frontmatter import parse_skill_frontmatter


@dataclass(frozen=True)
class SkillRecord:
    name: str
    group: str
    path: Path
    root: Path
    frontmatter: dict[str, object]


@dataclass(frozen=True)
class SkillLayoutInspection:
    skill_roots: tuple[Path, ...]
    invalid_boundaries: tuple[Path, ...]


def repo_root() -> Path:
    """Return the repository containing this CLI implementation."""
    return Path(__file__).resolve().parents[2]


def skill_relative_path(root: Path, path: Path) -> Path:
    """Return a skill path relative to the repository's skills directory."""
    return path.relative_to(skills_root(root))


def skills_root(root: Path) -> Path:
    """Return the canonical public-skills source directory."""
    return root / "skills"


def inspect_skill_layout(root: Path) -> SkillLayoutInspection:
    """Inspect canonical layout boundaries without following directory symlinks."""
    resolved_root = root.resolve(strict=True)
    skills_directory = skills_root(root)
    if skills_directory.is_symlink():
        return SkillLayoutInspection(
            skill_roots=(), invalid_boundaries=(skills_directory,)
        )
    if not skills_directory.exists():
        return SkillLayoutInspection(skill_roots=(), invalid_boundaries=())
    if not _is_contained_non_symlink_directory(skills_directory, resolved_root):
        return SkillLayoutInspection(
            skill_roots=(), invalid_boundaries=(skills_directory,)
        )

    groups: list[Path] = []
    invalid_boundaries: list[Path] = []
    for group in sorted(skills_directory.iterdir()):
        if _is_contained_non_symlink_directory(group, resolved_root):
            groups.append(group)
        else:
            invalid_boundaries.append(group)

    skill_directories: list[Path] = []
    for group in groups:
        for skill_directory in sorted(group.iterdir()):
            if _is_contained_non_symlink_directory(skill_directory, resolved_root):
                skill_directories.append(skill_directory)
            else:
                invalid_boundaries.append(skill_directory)
    return SkillLayoutInspection(
        skill_roots=tuple(skill_directories),
        invalid_boundaries=tuple(invalid_boundaries),
    )


def iter_skill_files(root: Path) -> Iterator[Path]:
    """Yield skill documents in the repository's canonical source layout."""
    inspection = inspect_skill_layout(root)
    if inspection.invalid_boundaries:
        messages = (
            f"{path.relative_to(root)} must be a contained non-symlink directory"
            for path in inspection.invalid_boundaries
        )
        raise ValueError("; ".join(messages))
    yield from (
        skill_root / "SKILL.md"
        for skill_root in inspection.skill_roots
        if (skill_root / "SKILL.md").is_file()
    )


def discover_testable_skills(root: Path) -> list[SkillRecord]:
    """Discover public skills and parse their frontmatter once for all runners."""
    records: list[SkillRecord] = []
    for path in iter_skill_files(root):
        frontmatter = parse_skill_frontmatter(path.read_text(encoding="utf-8"), path)
        relative_path = skill_relative_path(root, path)
        records.append(
            SkillRecord(
                name=frontmatter["name"],
                group=relative_path.parts[0],
                path=path,
                root=path.parent,
                frontmatter=frontmatter,
            )
        )
    return records


def _is_contained_non_symlink_directory(path: Path, resolved_root: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        return path.resolve(strict=True).is_relative_to(resolved_root)
    except (OSError, RuntimeError):
        return False
