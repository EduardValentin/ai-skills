"""Shared repository and public-skill discovery helpers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat

from scripts.ai_skills_lib.authored_content import (
    AuthoredContentReadError,
    AuthoredContentTooLarge,
    AuthoredFile,
    AuthoredRepositoryBudget,
    AuthoredTreeEntry,
    read_bounded_authored_bytes,
    snapshot_authored_tree,
)
from scripts.ai_skills_lib.frontmatter import parse_skill_frontmatter


MAXIMUM_SKILL_DOCUMENT_BYTES = 4 * 1024 * 1024
MAXIMUM_CANONICAL_SKILLS_TREE_FILE_BYTES = 64 * 1024 * 1024
PUBLIC_INSTALLER_DISCOVERY_EXCLUDED_DIRECTORIES = frozenset(
    {"node_modules", ".git", "dist", "build", "__pycache__"}
)
PUBLIC_INSTALLER_EXCLUDED_FILE_NAMES = frozenset({"metadata.json"})
PUBLIC_INSTALLER_EXCLUDED_DIRECTORY_NAMES = frozenset(
    {".git", "__pycache__", "__pypackages__"}
)


@dataclass(frozen=True)
class SkillRecord:
    name: str
    group: str
    path: Path
    root: Path
    frontmatter: dict[str, object]
    source_text: str
    source_signature: tuple[int, ...]


@dataclass(frozen=True)
class SkillLayoutInspection:
    skill_roots: tuple[Path, ...]
    invalid_boundaries: tuple[Path, ...]
    installer_excluded_boundaries: tuple[Path, ...] = ()


@dataclass(frozen=True)
class CanonicalSkillsTreeSnapshot:
    """Bounded content and identity snapshot of the canonical skills tree."""

    root_metadata: tuple[int, ...] | None
    entries: tuple[AuthoredTreeEntry, ...]
    regular_file_digests: tuple[tuple[Path, str], ...]


def repo_root() -> Path:
    """Return the repository containing this CLI implementation."""
    return Path(__file__).resolve().parents[2]


def skill_relative_path(root: Path, path: Path) -> Path:
    """Return a skill path relative to the repository's skills directory."""
    return path.relative_to(skills_root(root))


def skills_root(root: Path) -> Path:
    """Return the canonical public-skills source directory."""
    return root / "skills"


def snapshot_canonical_skills_tree(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget,
) -> CanonicalSkillsTreeSnapshot:
    """Capture every canonical entry's identity and every regular file's bytes."""
    content_root = skills_root(root)
    try:
        root_metadata = _directory_signature(content_root.lstat())
    except FileNotFoundError:
        return CanonicalSkillsTreeSnapshot(None, (), ())
    except OSError as error:
        raise AuthoredContentReadError(
            "canonical skills tree root cannot be inspected safely"
        ) from error

    tree_before = snapshot_authored_tree(content_root, budget=budget)
    digests: list[tuple[Path, str]] = []
    for entry in tree_before:
        if not entry.is_regular_file or entry.resolved_path is None:
            continue
        try:
            content = read_bounded_authored_bytes(
                AuthoredFile(
                    logical_path=entry.logical_path,
                    resolved_path=entry.resolved_path,
                ),
                maximum_bytes=MAXIMUM_CANONICAL_SKILLS_TREE_FILE_BYTES,
                allowed_root=content_root,
                containment_root=root,
                budget=budget,
            )
        except AuthoredContentTooLarge as error:
            raise AuthoredContentReadError(
                "canonical skills tree contains a file above the snapshot limit"
            ) from error
        digests.append((entry.logical_path, hashlib.sha256(content).hexdigest()))

    tree_after = snapshot_authored_tree(content_root, budget=budget)
    try:
        final_root_metadata = _directory_signature(content_root.lstat())
    except OSError as error:
        raise AuthoredContentReadError(
            "canonical skills tree root cannot be reverified safely"
        ) from error
    if tree_after != tree_before or final_root_metadata != root_metadata:
        raise AuthoredContentReadError(
            "canonical skills tree changed while its snapshot was captured"
        )
    return CanonicalSkillsTreeSnapshot(
        root_metadata=root_metadata,
        entries=tree_after,
        regular_file_digests=tuple(digests),
    )


def inspect_skill_layout(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> SkillLayoutInspection:
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
    installer_excluded_boundaries: list[Path] = []
    for group in _stable_directory_entries(skills_directory, budget=budget):
        is_directory = _is_contained_non_symlink_directory(
            group,
            resolved_root,
        )
        if (
            is_directory
            and group.name in PUBLIC_INSTALLER_DISCOVERY_EXCLUDED_DIRECTORIES
        ):
            installer_excluded_boundaries.append(group)
        elif is_directory:
            groups.append(group)
        else:
            invalid_boundaries.append(group)

    skill_directories: list[Path] = []
    for group in groups:
        for skill_directory in _stable_directory_entries(group, budget=budget):
            is_directory = _is_contained_non_symlink_directory(
                skill_directory,
                resolved_root,
            )
            if (
                is_directory
                and skill_directory.name
                in PUBLIC_INSTALLER_DISCOVERY_EXCLUDED_DIRECTORIES
            ):
                installer_excluded_boundaries.append(skill_directory)
            elif is_directory:
                skill_directories.append(skill_directory)
            else:
                invalid_boundaries.append(skill_directory)
    return SkillLayoutInspection(
        skill_roots=tuple(skill_directories),
        invalid_boundaries=tuple(invalid_boundaries),
        installer_excluded_boundaries=tuple(installer_excluded_boundaries),
    )


def iter_skill_files(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> Iterator[Path]:
    """Yield skill documents in the repository's canonical source layout."""
    inspection = inspect_skill_layout(root, budget=budget)
    if inspection.invalid_boundaries:
        messages = (
            f"{path.relative_to(root)} must be a contained non-symlink directory"
            for path in inspection.invalid_boundaries
        )
        raise ValueError("; ".join(messages))
    if inspection.installer_excluded_boundaries:
        messages = (
            "public installer discovery excludes directory "
            f"{path.relative_to(root)}"
            for path in inspection.installer_excluded_boundaries
        )
        raise ValueError("; ".join(messages))
    skill_files: list[Path] = []
    invalid_skill_roots: list[Path] = []
    for skill_root in inspection.skill_roots:
        skill_file = _exact_regular_skill_document(skill_root, budget=budget)
        if skill_file is None:
            invalid_skill_roots.append(skill_root)
        else:
            skill_files.append(skill_file)
    if invalid_skill_roots:
        messages = (
            f"{skill_root.relative_to(root)} requires an exact regular non-symlink SKILL.md"
            for skill_root in invalid_skill_roots
        )
        raise ValueError("; ".join(messages))
    yield from skill_files


def discover_testable_skills(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> list[SkillRecord]:
    """Discover public skills and parse their frontmatter once for all runners."""
    records: list[SkillRecord] = []
    for path in iter_skill_files(root, budget=budget):
        try:
            content, source_signature = read_stable_skill_document(
                path,
                root,
                budget=budget,
            )
            source_text = content.decode("utf-8")
        except AuthoredContentTooLarge as error:
            raise ValueError(
                f"{path}: SKILL.md exceeds the {MAXIMUM_SKILL_DOCUMENT_BYTES}-byte limit"
            ) from error
        except (AuthoredContentReadError, OSError, RuntimeError, UnicodeDecodeError) as error:
            raise ValueError(
                f"{path}: SKILL.md cannot be read as stable UTF-8"
            ) from error
        frontmatter = parse_skill_frontmatter(source_text, path)
        relative_path = skill_relative_path(root, path)
        records.append(
            SkillRecord(
                name=frontmatter["name"],
                group=relative_path.parts[0],
                path=path,
                root=path.parent,
                frontmatter=frontmatter,
                source_text=source_text,
                source_signature=source_signature,
            )
        )
    return records


def read_stable_skill_document(
    path: Path,
    root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> tuple[bytes, tuple[int, ...]]:
    """Read one exact SKILL.md while binding bytes to its named file identity."""
    before = _skill_document_signature(path)
    content = read_bounded_authored_bytes(
        AuthoredFile(
            logical_path=path,
            resolved_path=path.resolve(strict=True),
        ),
        maximum_bytes=MAXIMUM_SKILL_DOCUMENT_BYTES,
        allowed_root=path.parent,
        containment_root=root,
        budget=budget,
    )
    after = _skill_document_signature(path)
    if after != before:
        raise AuthoredContentReadError(
            "SKILL.md changed while its source snapshot was captured"
        )
    return content, after


def skill_source_matches_record(
    skill: SkillRecord,
    root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> bool:
    """Return whether the current SKILL.md is the exact discovered source."""
    content, signature = read_stable_skill_document(
        skill.path,
        root,
        budget=budget,
    )
    return (
        signature == skill.source_signature
        and content == skill.source_text.encode("utf-8")
    )


def _is_contained_non_symlink_directory(path: Path, resolved_root: Path) -> bool:
    if path.is_symlink() or not path.is_dir():
        return False
    try:
        return path.resolve(strict=True).is_relative_to(resolved_root)
    except (OSError, RuntimeError):
        return False


def _skill_document_signature(path: Path) -> tuple[int, ...]:
    try:
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise AuthoredContentReadError(
                "SKILL.md is not a regular non-symlink file"
            )
    except AuthoredContentReadError:
        raise
    except (OSError, RuntimeError) as error:
        raise AuthoredContentReadError(
            "SKILL.md cannot be inspected safely"
        ) from error
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _exact_regular_skill_document(
    skill_root: Path,
    *,
    budget: AuthoredRepositoryBudget | None = None,
) -> Path | None:
    try:
        exact_matches = tuple(
            path
            for path in _stable_directory_entries(skill_root, budget=budget)
            if path.name == "SKILL.md"
        )
        if len(exact_matches) != 1:
            return None
        skill_file = exact_matches[0]
        if not stat.S_ISREG(skill_file.lstat().st_mode):
            return None
    except OSError:
        return None
    return skill_file


def _stable_directory_entries(
    directory: Path,
    *,
    budget: AuthoredRepositoryBudget | None,
) -> tuple[Path, ...]:
    """Enumerate one non-symlink directory through a stable open handle."""
    descriptor: int | None = None
    try:
        observed = directory.lstat()
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode):
            raise ValueError("authored directory must be a non-symlink directory")
        descriptor = os.open(
            directory,
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0),
        )
        opened = os.fstat(descriptor)
        if _directory_signature(opened) != _directory_signature(observed):
            raise ValueError("authored directory changed while being opened")
        names: list[str] = []
        with os.scandir(descriptor) as entries:
            for entry in entries:
                if budget is not None:
                    budget.inspect_entry()
                names.append(entry.name)
        final = os.fstat(descriptor)
        named_final = directory.lstat()
        expected = _directory_signature(observed)
        if (
            _directory_signature(final) != expected
            or _directory_signature(named_final) != expected
        ):
            raise ValueError("authored directory changed during enumeration")
        return tuple(directory / name for name in sorted(names))
    except ValueError:
        raise
    except OSError as error:
        raise ValueError("authored directory cannot be enumerated safely") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _directory_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )
