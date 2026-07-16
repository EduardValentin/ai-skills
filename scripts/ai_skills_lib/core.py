"""Shared repository and public-skill discovery helpers."""

from __future__ import annotations

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


def repo_root() -> Path:
    """Return the repository containing this CLI implementation."""
    return Path(__file__).resolve().parents[2]


def skill_relative_path(root: Path, path: Path) -> Path:
    """Return a skill path relative to the repository's skills directory."""
    return path.relative_to(skills_root(root))


def skills_root(root: Path) -> Path:
    """Return the canonical public-skills source directory."""
    return root / "skills"


def iter_skill_files(root: Path):
    """Yield skill documents in the repository's canonical source layout."""
    yield from sorted(skills_root(root).glob("*/*/SKILL.md"))


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
