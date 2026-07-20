"""Read-only diagnostics for repository skills installed into local harnesses."""

from __future__ import annotations

from collections import deque
import configparser
from contextlib import contextmanager, ExitStack
from dataclasses import dataclass
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Iterable, Iterator, Mapping
from urllib.parse import urlparse

from scripts.ai_skills_lib.frontmatter import parse_skill_frontmatter
from scripts.ai_skills_lib.issues import ValidationIssue, print_grouped_issues


_MAX_LOCK_BYTES = 4 * 1024 * 1024
_MAX_SKILL_FILE_BYTES = 64 * 1024 * 1024
_MAX_SKILL_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_AGGREGATE_READ_BYTES = 512 * 1024 * 1024
_MAX_AGGREGATE_MANIFEST_ENTRIES = 8192
_MAX_ROOT_ENTRIES = 8192
_MAX_SOURCE_ENTRIES = 8192
_MAX_DIRECTORY_DEPTH = 64
_MAX_FRONTMATTER_BYTES = 1024 * 1024
_MAX_GIT_PATH_BYTES = 64 * 1024
_MAX_GIT_CONFIG_BYTES = 4 * 1024 * 1024
_MAX_SYMLINK_TRAVERSALS = 40
_READ_CHUNK_BYTES = 1024 * 1024
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0)
_DIRECTORY_NOFOLLOW_FLAGS = _DIRECTORY_FLAGS | getattr(os, "O_NOFOLLOW", 0)
_FILE_NOFOLLOW_FLAGS = (
    os.O_RDONLY
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
    | getattr(os, "O_NONBLOCK", 0)
)
_GITHUB_SCP = re.compile(r"git@github\.com:(?P<repo>[^/]+/[^/]+)\Z", re.IGNORECASE)


@dataclass
class _OpenRoot:
    descriptor: int
    aliases: list[Path]


@dataclass(frozen=True)
class _RootEntry:
    root: _OpenRoot
    name: str


@dataclass
class _OpenCandidate:
    descriptor: int
    aliases: list[Path]

    @property
    def display_path(self) -> Path:
        return min(self.aliases, key=str)


@dataclass
class _ReadBudget:
    limit: int
    consumed: int = 0

    def consume(self, count: int) -> None:
        if count < 0 or self.consumed + count > self.limit:
            raise _InspectionError("diagnostic exceeds the aggregate read limit")
        self.consumed += count


@dataclass
class _EntryBudget:
    limit: int
    consumed: int = 0

    def consume(self) -> None:
        if self.consumed >= self.limit:
            raise _InspectionError(
                "diagnostic exceeds the aggregate manifest entry limit"
            )
        self.consumed += 1


@dataclass(frozen=True)
class _DirectoryAnchor:
    path: Path
    canonical_path: Path
    descriptor: int
    identity: tuple[int, int]
    label: str


@dataclass
class _RepositoryContext:
    root: _DirectoryAnchor
    resources: ExitStack
    anchors: list[_DirectoryAnchor]


@dataclass(frozen=True)
class _RepositorySkillSnapshot:
    name: str
    root: Path
    manifest: dict[str, tuple[str, int]]


@dataclass(frozen=True)
class LocalInstallReport:
    expected_count: int
    current: tuple[tuple[str, Path], ...]
    issues: tuple[ValidationIssue, ...]


class _InspectionError(ValueError):
    pass


class _NotRegularFile(_InspectionError):
    pass


def run_local_install_check(
    repository_root: Path,
    *,
    harness: str,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Inspect local harness state without modifying it."""
    if harness != "codex":
        print(f"check-local-installs {harness}: unsupported harness")
        return 2

    environment = os.environ if environ is None else environ
    try:
        home = _absolute_home(environment)
        codex_home = _codex_home(environment, home)
        report = inspect_codex_local_installs(
            repository_root,
            home=home,
            codex_home=codex_home,
            lock_path=_skill_lock_path(environment, home),
        )
    except (OSError, ValueError) as error:
        print(f"check-local-installs codex: FAILED: {error}")
        return 2

    for name, path in report.current:
        print(f"{name}: current ({path})")
    if report.issues:
        print_grouped_issues(report.issues)
        print(f"check-local-installs codex: FAILED ({len(report.issues)} issues)")
        return 1
    print(f"check-local-installs codex: OK ({report.expected_count} skills)")
    return 0


def inspect_codex_local_installs(
    repository_root: Path,
    *,
    home: Path,
    codex_home: Path,
    lock_path: Path,
    inspection_hook: Callable[[str, Path], None] | None = None,
) -> LocalInstallReport:
    """Compare repository skills with Codex's global active skill roots."""
    repository_root = _absolute_path(repository_root, "repository root")
    home = _absolute_path(home, "home")
    codex_home = _absolute_path(codex_home, "CODEX_HOME")
    lock_path = _absolute_path(lock_path, "skill lock")
    codex_skills = codex_home / "skills"
    canonical_skills = home / ".agents" / "skills"
    roots = (codex_skills, canonical_skills)
    issues: list[ValidationIssue] = []
    read_budget = _ReadBudget(_MAX_AGGREGATE_READ_BYTES)
    entry_budget = _EntryBudget(_MAX_AGGREGATE_MANIFEST_ENTRIES)
    with _repository_context(repository_root, inspection_hook) as repository:
        repository_sources = _repository_source_identifiers(repository, read_budget)
        _notify(
            inspection_hook,
            "repository-identifiers-derived",
            repository_root,
        )
        attributed_names = _repository_lock_names(
            lock_path,
            repository_sources,
            home,
            issues,
            inspection_hook,
        )
        expected = _discover_repository_skills(
            repository.root.descriptor,
            repository.root.path,
            read_budget,
            entry_budget,
            inspection_hook,
        )
        _notify(inspection_hook, "repository-skills-discovered", repository_root)
        inspected_names = set(expected) | set(attributed_names)
        current: list[tuple[str, Path]] = []
        with ExitStack() as root_resources:
            open_roots = _open_skill_roots(roots, issues, root_resources)
            indexed_entries = _index_relevant_root_entries(
                open_roots,
                inspected_names,
                issues,
            )
            for name in sorted(inspected_names):
                with ExitStack() as candidate_resources:
                    candidates = _open_installed_candidates(
                        name,
                        indexed_entries.get(name, ()),
                        issues,
                        candidate_resources,
                        inspection_hook,
                    )
                    valid_candidates: list[_OpenCandidate] = []
                    for candidate in candidates:
                        try:
                            declared_name = _installed_name(candidate, read_budget)
                        except _InspectionError as error:
                            issues.append(ValidationIssue(name, str(error)))
                            continue
                        if declared_name != name:
                            issues.append(
                                ValidationIssue(
                                    name,
                                    f"installed SKILL.md at {candidate.display_path} "
                                    f"declares name {declared_name!r}",
                                )
                            )
                            continue
                        valid_candidates.append(candidate)

                    if name not in expected:
                        for candidate in valid_candidates:
                            issues.append(
                                ValidationIssue(
                                    name,
                                    "extra active install attributed to this repository: "
                                    f"{candidate.display_path}",
                                )
                            )
                        continue
                    if not valid_candidates:
                        issues.append(
                            ValidationIssue(name, "missing from Codex skill roots")
                        )
                        continue
                    if len(valid_candidates) > 1:
                        paths = ", ".join(
                            str(candidate.display_path) for candidate in valid_candidates
                        )
                        issues.append(
                            ValidationIssue(name, f"duplicate active installs: {paths}")
                        )
                        continue

                    candidate = valid_candidates[0]
                    try:
                        installed_manifest = _skill_manifest(
                            candidate.descriptor,
                            candidate.display_path,
                            label=f"installed skill {name}",
                            read_budget=read_budget,
                            entry_budget=entry_budget,
                            inspection_hook=inspection_hook,
                        )
                    except _InspectionError as error:
                        issues.append(ValidationIssue(name, str(error)))
                        continue
                    if installed_manifest != expected[name].manifest:
                        issues.append(
                            ValidationIssue(
                                name,
                                f"stale content at {candidate.display_path}",
                            )
                        )
                        continue
                    current.append((name, candidate.display_path))

        report = LocalInstallReport(
            expected_count=len(expected),
            current=tuple(sorted(current)),
            issues=tuple(sorted(issues, key=lambda issue: (issue.scope, issue.message))),
        )
    return report


def repository_source_identifiers(repository_root: Path) -> frozenset[str]:
    """Return normalized local and remote identifiers for this repository."""
    root = _absolute_path(repository_root, "repository root")
    with _repository_context(root, None) as repository:
        return _repository_source_identifiers(repository, None)


@contextmanager
def _repository_context(
    root: Path,
    inspection_hook: Callable[[str, Path], None] | None,
) -> Iterator[_RepositoryContext]:
    with ExitStack() as resources:
        descriptor = _open_nofollow_directory(root, label="repository root")
        resources.callback(os.close, descriptor)
        opened = os.fstat(descriptor)
        _notify(inspection_hook, "repository-directory-opened", root)
        root_anchor = _directory_anchor_from_descriptor(
            root,
            descriptor,
            opened,
            label="repository root",
        )
        context = _RepositoryContext(
            root=root_anchor,
            resources=resources,
            anchors=[root_anchor],
        )
        try:
            yield context
        finally:
            _verify_directory_anchors(context.anchors)


def _repository_source_identifiers(
    repository: _RepositoryContext,
    read_budget: _ReadBudget | None,
) -> frozenset[str]:
    identifiers = {f"path:{repository.root.canonical_path}"}
    common_directory = _repository_common_git_directory(repository, read_budget)
    if common_directory is None:
        return frozenset(identifiers)

    main_checkout = _proven_main_checkout(repository, common_directory)
    if main_checkout is not None:
        identifiers.add(f"path:{main_checkout.canonical_path}")
    origin = _git_origin(common_directory, read_budget)
    if origin is not None:
        identifiers.add(
            _normalize_git_remote_source(
                origin,
                repository.root.canonical_path,
            )
        )
    return frozenset(identifier for identifier in identifiers if identifier)


def _repository_common_git_directory(
    repository: _RepositoryContext,
    read_budget: _ReadBudget | None,
) -> _DirectoryAnchor | None:
    try:
        observed = os.stat(
            ".git",
            dir_fd=repository.root.descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    git_path = repository.root.canonical_path / ".git"
    if stat.S_ISDIR(observed.st_mode):
        common = _open_relative_directory_anchor(
            repository,
            repository.root.descriptor,
            ".git",
            observed,
            git_path,
            label="repository git directory",
        )
        repository.anchors.append(common)
        return common
    if not stat.S_ISREG(observed.st_mode):
        raise _InspectionError(
            "repository git metadata must be a regular file or directory"
        )

    raw_git_path = _read_regular_child(
        repository.root.descriptor,
        ".git",
        limit=_MAX_GIT_PATH_BYTES,
        label="git directory metadata",
        read_budget=read_budget,
    )
    git_directory_path = _resolve_git_metadata_path(
        repository.root.canonical_path,
        _parse_git_path(raw_git_path, label="git directory metadata", prefix="gitdir:"),
    )
    git_directory = _open_directory_anchor(
        repository,
        git_directory_path,
        label="git directory",
    )
    repository.anchors.append(git_directory)

    raw_common_path = _read_optional_regular_child(
        git_directory.descriptor,
        "commondir",
        limit=_MAX_GIT_PATH_BYTES,
        label="git common directory metadata",
        read_budget=read_budget,
    )
    if raw_common_path is None:
        return git_directory
    common_path = _resolve_git_metadata_path(
        git_directory.canonical_path,
        _parse_git_path(
            raw_common_path,
            label="git common directory metadata",
        ),
    )
    common = _open_directory_anchor(
        repository,
        common_path,
        label="git common directory",
    )
    if common.identity == git_directory.identity:
        return git_directory
    repository.anchors.append(common)
    return common


def _proven_main_checkout(
    repository: _RepositoryContext,
    common_directory: _DirectoryAnchor,
) -> _DirectoryAnchor | None:
    if common_directory.canonical_path.name != ".git":
        return None
    candidate_path = common_directory.canonical_path.parent
    if candidate_path == repository.root.canonical_path:
        return repository.root
    try:
        candidate = _open_directory_anchor(
            repository,
            candidate_path,
            label="main checkout",
        )
        observed = os.stat(
            ".git",
            dir_fd=candidate.descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISDIR(observed.st_mode):
            return None
        descriptor = _open_observed_directory(
            candidate.descriptor,
            ".git",
            observed,
        )
        try:
            if _descriptor_identity(os.fstat(descriptor)) != common_directory.identity:
                return None
        finally:
            os.close(descriptor)
    except (OSError, _InspectionError):
        return None
    repository.anchors.append(candidate)
    return candidate


def _git_origin(
    common_directory: _DirectoryAnchor,
    read_budget: _ReadBudget | None,
) -> str | None:
    raw = _read_optional_regular_child(
        common_directory.descriptor,
        "config",
        limit=_MAX_GIT_CONFIG_BYTES,
        label="git config",
        read_budget=read_budget,
    )
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8")
        parser = configparser.ConfigParser(interpolation=None, strict=False)
        parser.read_string(text)
        value = parser.get('remote "origin"', "url", fallback="").strip()
    except (UnicodeError, configparser.Error):
        return None
    return value or None


def _parse_git_path(
    raw: bytes,
    *,
    label: str,
    prefix: str | None = None,
) -> str:
    try:
        text = raw.decode("utf-8")
    except UnicodeError as error:
        raise _InspectionError(f"{label} is not valid UTF-8") from error
    if text.endswith("\n"):
        text = text[:-1]
    if text.endswith("\r"):
        text = text[:-1]
    if not text or "\n" in text or "\r" in text or "\x00" in text:
        raise _InspectionError(f"{label} must contain exactly one path")
    if prefix is not None:
        if not text.startswith(prefix):
            raise _InspectionError(f"{label} must start with {prefix}")
        text = text[len(prefix) :].strip()
    if not text:
        raise _InspectionError(f"{label} must contain a path")
    return text


def _resolve_git_metadata_path(base: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = base / path
    return Path(os.path.abspath(path))


def _read_optional_regular_child(
    directory_descriptor: int,
    name: str,
    *,
    limit: int,
    label: str,
    read_budget: _ReadBudget | None,
) -> bytes | None:
    try:
        observed = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(observed.st_mode):
        raise _InspectionError(f"{label} must be a regular non-symlink file")
    return _read_regular_child(
        directory_descriptor,
        name,
        limit=limit,
        label=label,
        read_budget=read_budget,
    )


def _open_relative_directory_anchor(
    repository: _RepositoryContext,
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
    path: Path,
    *,
    label: str,
) -> _DirectoryAnchor:
    descriptor = _open_observed_directory(parent_descriptor, name, observed)
    repository.resources.callback(os.close, descriptor)
    return _directory_anchor_from_descriptor(
        path,
        descriptor,
        os.fstat(descriptor),
        label=label,
    )


def _open_directory_anchor(
    repository: _RepositoryContext,
    path: Path,
    *,
    label: str,
) -> _DirectoryAnchor:
    descriptor = _open_nofollow_directory(path, label=label)
    repository.resources.callback(os.close, descriptor)
    return _directory_anchor_from_descriptor(
        path,
        descriptor,
        os.fstat(descriptor),
        label=label,
    )


def _directory_anchor_from_descriptor(
    path: Path,
    descriptor: int,
    opened: os.stat_result,
    *,
    label: str,
) -> _DirectoryAnchor:
    try:
        canonical_path = path.resolve(strict=True)
        verification = _open_nofollow_directory(canonical_path, label=label)
    except (OSError, RuntimeError, _InspectionError) as error:
        raise _InspectionError(f"{label} changed while being inspected") from error
    try:
        if _descriptor_identity(os.fstat(verification)) != _descriptor_identity(opened):
            raise _InspectionError(f"{label} changed while being inspected")
    finally:
        os.close(verification)
    return _DirectoryAnchor(
        path=path,
        canonical_path=canonical_path,
        descriptor=descriptor,
        identity=_descriptor_identity(opened),
        label=label,
    )


def _verify_directory_anchors(anchors: Iterable[_DirectoryAnchor]) -> None:
    for anchor in anchors:
        verification: int | None = None
        try:
            if _descriptor_identity(os.fstat(anchor.descriptor)) != anchor.identity:
                raise _InspectionError(
                    f"{anchor.label} changed while being inspected"
                )
            if anchor.path.resolve(strict=True) != anchor.canonical_path:
                raise _InspectionError(
                    f"{anchor.label} changed while being inspected"
                )
            verification = _open_nofollow_directory(anchor.path, label=anchor.label)
            if _descriptor_identity(os.fstat(verification)) != anchor.identity:
                raise _InspectionError(
                    f"{anchor.label} changed while being inspected"
                )
        except (OSError, RuntimeError, _InspectionError) as error:
            if isinstance(error, _InspectionError) and str(error).endswith(
                "changed while being inspected"
            ):
                raise
            raise _InspectionError(
                f"{anchor.label} changed while being inspected"
            ) from error
        finally:
            if verification is not None:
                os.close(verification)


def _absolute_home(environ: Mapping[str, str]) -> Path:
    raw = environ.get("HOME")
    if raw is None or not raw.strip():
        raise _InspectionError("HOME must be set")
    return _absolute_path(Path(raw), "HOME")


def _codex_home(environ: Mapping[str, str], home: Path) -> Path:
    raw = environ.get("CODEX_HOME")
    return _absolute_path(Path(raw), "CODEX_HOME") if raw else home / ".codex"


def _skill_lock_path(environ: Mapping[str, str], home: Path) -> Path:
    raw = environ.get("XDG_STATE_HOME")
    if raw is not None and raw.strip():
        state_home = _absolute_path(Path(raw), "XDG_STATE_HOME")
        return state_home / "skills" / ".skill-lock.json"
    return home / ".agents" / ".skill-lock.json"


def _absolute_path(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise _InspectionError(f"{label} must be an absolute path")
    return Path(os.path.abspath(path))


def _discover_repository_skills(
    root_descriptor: int,
    repository_root: Path,
    read_budget: _ReadBudget,
    entry_budget: _EntryBudget,
    inspection_hook: Callable[[str, Path], None] | None,
) -> dict[str, _RepositorySkillSnapshot]:
    discovered: dict[str, _RepositorySkillSnapshot] = {}
    entry_count = 0
    with ExitStack() as resources:
        skills_root = repository_root / "skills"
        skills_descriptor = _open_optional_repository_directory(
            root_descriptor,
            "skills",
            skills_root,
        )
        if skills_descriptor is None:
            return discovered
        resources.callback(os.close, skills_descriptor)

        try:
            with os.scandir(skills_descriptor) as groups:
                for group in groups:
                    entry_count += 1
                    if entry_count > _MAX_SOURCE_ENTRIES:
                        raise _InspectionError(
                            "repository source exceeds the entry limit"
                        )
                    group_root = skills_root / group.name
                    observed_group = os.stat(
                        group.name,
                        dir_fd=skills_descriptor,
                        follow_symlinks=False,
                    )
                    _notify(
                        inspection_hook,
                        "repository-group-entry-observed",
                        group_root,
                    )
                    if not stat.S_ISDIR(observed_group.st_mode):
                        raise _InspectionError(
                            f"repository source boundary must be a non-symlink "
                            f"directory: {group_root}"
                        )
                    group_descriptor = _open_observed_directory(
                        skills_descriptor,
                        group.name,
                        observed_group,
                    )
                    try:
                        with os.scandir(group_descriptor) as skill_entries:
                            for skill_entry in skill_entries:
                                entry_count += 1
                                if entry_count > _MAX_SOURCE_ENTRIES:
                                    raise _InspectionError(
                                        "repository source exceeds the entry limit"
                                    )
                                skill_root = group_root / skill_entry.name
                                observed_skill = os.stat(
                                    skill_entry.name,
                                    dir_fd=group_descriptor,
                                    follow_symlinks=False,
                                )
                                _notify(
                                    inspection_hook,
                                    "repository-skill-entry-observed",
                                    skill_root,
                                )
                                if not stat.S_ISDIR(observed_skill.st_mode):
                                    raise _InspectionError(
                                        "repository source boundary must be a "
                                        f"non-symlink directory: {skill_root}"
                                    )
                                skill_descriptor = _open_observed_directory(
                                    group_descriptor,
                                    skill_entry.name,
                                    observed_skill,
                                )
                                try:
                                    snapshot = _snapshot_repository_skill(
                                        skill_descriptor,
                                        skill_root,
                                        read_budget,
                                        entry_budget,
                                        inspection_hook,
                                    )
                                finally:
                                    os.close(skill_descriptor)
                                if snapshot.name in discovered:
                                    raise _InspectionError(
                                        "repository skill names must be unique: "
                                        f"{snapshot.name}"
                                    )
                                discovered[snapshot.name] = snapshot
                    finally:
                        os.close(group_descriptor)
        except _InspectionError:
            raise
        except OSError as error:
            raise _InspectionError(
                f"repository source cannot be read safely: {error}"
            ) from error
    return discovered


def _open_optional_repository_directory(
    parent_descriptor: int,
    name: str,
    display_path: Path,
) -> int | None:
    try:
        observed = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISDIR(observed.st_mode):
        raise _InspectionError(
            f"repository source boundary must be a non-symlink directory: "
            f"{display_path}"
        )
    return _open_observed_directory(parent_descriptor, name, observed)


def _snapshot_repository_skill(
    skill_descriptor: int,
    skill_root: Path,
    read_budget: _ReadBudget,
    entry_budget: _EntryBudget,
    inspection_hook: Callable[[str, Path], None] | None,
) -> _RepositorySkillSnapshot:
    skill_path = skill_root / "SKILL.md"
    try:
        observed = os.stat(
            "SKILL.md",
            dir_fd=skill_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError as error:
        raise _InspectionError(
            f"repository skill {skill_root} requires a regular non-symlink SKILL.md"
        ) from error
    if not stat.S_ISREG(observed.st_mode):
        raise _InspectionError(
            f"repository skill {skill_root} requires a regular non-symlink SKILL.md"
        )
    if observed.st_size > _MAX_FRONTMATTER_BYTES:
        raise _InspectionError("SKILL.md exceeds the diagnostic size limit")

    captured: dict[str, bytes] = {}
    manifest = _skill_manifest(
        skill_descriptor,
        skill_root,
        label=f"repository skill {skill_root.name}",
        read_budget=read_budget,
        entry_budget=entry_budget,
        inspection_hook=inspection_hook,
        capture_limits={"SKILL.md": _MAX_FRONTMATTER_BYTES},
        captured_files=captured,
    )
    raw = captured.get("SKILL.md")
    if raw is None:
        raise _InspectionError(
            f"repository skill {skill_root} requires a regular non-symlink SKILL.md"
        )
    try:
        frontmatter = parse_skill_frontmatter(raw.decode("utf-8"), skill_path)
    except (UnicodeError, ValueError) as error:
        raise _InspectionError(f"invalid repository SKILL.md at {skill_path}: {error}") from error
    return _RepositorySkillSnapshot(
        name=str(frontmatter["name"]),
        root=skill_root,
        manifest=manifest,
    )


def _open_skill_roots(
    root_paths: tuple[Path, ...],
    issues: list[ValidationIssue],
    resources: ExitStack,
) -> tuple[_OpenRoot, ...]:
    direct_roots: dict[tuple[int, int], _OpenRoot] = {}
    aliases: list[tuple[Path, int, tuple[int, int]]] = []
    for root_path in root_paths:
        try:
            descriptor, is_alias = _open_configured_root(root_path)
        except FileNotFoundError:
            continue
        except (OSError, _InspectionError) as error:
            issues.append(
                ValidationIssue(
                    str(root_path),
                    f"cannot safely read Codex skill root: {error}",
                )
            )
            continue
        identity = _descriptor_identity(os.fstat(descriptor))
        if is_alias:
            aliases.append((root_path, descriptor, identity))
            continue
        existing = direct_roots.get(identity)
        if existing is None:
            root = _OpenRoot(descriptor=descriptor, aliases=[root_path])
            direct_roots[identity] = root
            resources.callback(os.close, descriptor)
        else:
            existing.aliases.append(root_path)
            os.close(descriptor)

    for root_path, descriptor, identity in aliases:
        target = direct_roots.get(identity)
        if target is None:
            issues.append(
                ValidationIssue(
                    str(root_path),
                    "Codex skill root must be a non-symlink directory or alias "
                    "another configured skill root",
                )
            )
        else:
            target.aliases.append(root_path)
        os.close(descriptor)

    for root in direct_roots.values():
        root.aliases[:] = sorted(set(root.aliases), key=str)
    return tuple(sorted(direct_roots.values(), key=lambda root: str(root.aliases[0])))


def _open_configured_root(path: Path) -> tuple[int, bool]:
    parent_descriptor = _open_directory_path(path.parent)
    try:
        observed = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISDIR(observed.st_mode):
            return _open_observed_directory(parent_descriptor, path.name, observed), False
        if stat.S_ISLNK(observed.st_mode):
            return _open_observed_symlink_directory(
                parent_descriptor,
                path.name,
                observed,
            ), True
        raise _InspectionError("path is not a directory")
    finally:
        os.close(parent_descriptor)


def _index_relevant_root_entries(
    roots: tuple[_OpenRoot, ...],
    inspected_names: set[str],
    issues: list[ValidationIssue],
) -> dict[str, tuple[_RootEntry, ...]]:
    indexed: dict[str, list[_RootEntry]] = {}
    for root in roots:
        count = 0
        try:
            with os.scandir(root.descriptor) as entries:
                for entry in entries:
                    count += 1
                    if count > _MAX_ROOT_ENTRIES:
                        issues.append(
                            ValidationIssue(
                                str(root.aliases[0]),
                                "skill root exceeds the entry limit",
                            )
                        )
                        break
                    if entry.name in inspected_names:
                        indexed.setdefault(entry.name, []).append(
                            _RootEntry(root=root, name=entry.name)
                        )
        except OSError as error:
            issues.append(
                ValidationIssue(
                    str(root.aliases[0]),
                    f"cannot read skill root: {error}",
                )
            )
    return {name: tuple(entries) for name, entries in indexed.items()}


def _open_installed_candidates(
    name: str,
    entries: Iterable[_RootEntry],
    issues: list[ValidationIssue],
    resources: ExitStack,
    inspection_hook: Callable[[str, Path], None] | None,
) -> tuple[_OpenCandidate, ...]:
    direct: dict[tuple[int, int], _OpenCandidate] = {}
    aliases: list[tuple[int, tuple[int, int], list[Path]]] = []
    for entry in entries:
        paths = [root_path / name for root_path in entry.root.aliases]
        display_path = min(paths, key=str)
        try:
            observed = os.stat(
                entry.name,
                dir_fd=entry.root.descriptor,
                follow_symlinks=False,
            )
            _notify(inspection_hook, "candidate-entry-observed", display_path)
            if stat.S_ISDIR(observed.st_mode):
                descriptor = _open_observed_directory(
                    entry.root.descriptor,
                    entry.name,
                    observed,
                )
                resources.callback(os.close, descriptor)
                _notify(inspection_hook, "candidate-directory-opened", display_path)
                identity = _descriptor_identity(os.fstat(descriptor))
                existing = direct.get(identity)
                if existing is None:
                    direct[identity] = _OpenCandidate(descriptor, paths)
                else:
                    existing.aliases.extend(paths)
                continue
            if stat.S_ISLNK(observed.st_mode):
                descriptor = _open_observed_symlink_directory(
                    entry.root.descriptor,
                    entry.name,
                    observed,
                )
                resources.callback(os.close, descriptor)
                aliases.append(
                    (descriptor, _descriptor_identity(os.fstat(descriptor)), paths)
                )
                continue
            raise _InspectionError("entry is not a directory")
        except (OSError, _InspectionError):
            issues.append(
                ValidationIssue(name, f"unsafe installed path: {display_path}")
            )

    for _, identity, paths in aliases:
        target = direct.get(identity)
        if target is None:
            issues.append(
                ValidationIssue(
                    name,
                    f"unsafe installed path: {min(paths, key=str)}",
                )
            )
        else:
            target.aliases.extend(paths)

    for candidate in direct.values():
        candidate.aliases[:] = sorted(set(candidate.aliases), key=str)
    return tuple(sorted(direct.values(), key=lambda candidate: str(candidate.display_path)))


def _installed_name(candidate: _OpenCandidate, read_budget: _ReadBudget) -> str:
    skill_path = candidate.display_path / "SKILL.md"
    try:
        raw = _read_regular_child(
            candidate.descriptor,
            "SKILL.md",
            limit=_MAX_FRONTMATTER_BYTES,
            label=f"installed SKILL.md at {skill_path}",
            read_budget=read_budget,
        )
    except _NotRegularFile as error:
        raise _InspectionError(
            f"missing regular SKILL.md at {candidate.display_path}"
        ) from error
    except _InspectionError as error:
        raise _InspectionError(f"invalid installed SKILL.md: {error}") from error
    try:
        text = raw.decode("utf-8")
        return str(parse_skill_frontmatter(text, skill_path)["name"])
    except (UnicodeError, ValueError) as error:
        raise _InspectionError(f"invalid installed SKILL.md: {error}") from error


def _read_regular_child(
    directory_descriptor: int,
    name: str,
    *,
    limit: int,
    label: str,
    read_budget: _ReadBudget | None,
) -> bytes:
    try:
        observed = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError as error:
        raise _NotRegularFile(f"{label} is missing") from error
    if not stat.S_ISREG(observed.st_mode):
        raise _NotRegularFile(f"{label} is not a regular file")
    try:
        descriptor, opened = _open_observed_regular_file(
            directory_descriptor,
            name,
            observed,
        )
    except OSError as error:
        if error.errno in (errno.ELOOP, errno.ENXIO, errno.ENOTDIR):
            raise _NotRegularFile(f"{label} is not a regular file") from error
        raise
    try:
        return _read_bounded_descriptor(
            descriptor,
            opened,
            limit=limit,
            label=label,
            read_budget=read_budget,
        )
    finally:
        os.close(descriptor)


def _skill_manifest(
    root_descriptor: int,
    display_root: Path,
    *,
    label: str,
    read_budget: _ReadBudget,
    entry_budget: _EntryBudget,
    inspection_hook: Callable[[str, Path], None] | None,
    capture_limits: Mapping[str, int] | None = None,
    captured_files: dict[str, bytes] | None = None,
) -> dict[str, tuple[str, int]]:
    manifest: dict[str, tuple[str, int]] = {}
    state = {"bytes": 0}
    descriptor = os.open(".", _DIRECTORY_NOFOLLOW_FLAGS, dir_fd=root_descriptor)
    try:
        _walk_manifest_directory(
            descriptor,
            (),
            display_root,
            label,
            manifest,
            state,
            read_budget,
            entry_budget,
            inspection_hook,
            {} if capture_limits is None else capture_limits,
            {} if captured_files is None else captured_files,
            depth=0,
        )
    finally:
        os.close(descriptor)
    return manifest


def _walk_manifest_directory(
    directory_descriptor: int,
    relative_parts: tuple[str, ...],
    display_root: Path,
    label: str,
    manifest: dict[str, tuple[str, int]],
    state: dict[str, int],
    read_budget: _ReadBudget,
    entry_budget: _EntryBudget,
    inspection_hook: Callable[[str, Path], None] | None,
    capture_limits: Mapping[str, int],
    captured_files: dict[str, bytes],
    *,
    depth: int,
) -> None:
    if depth > _MAX_DIRECTORY_DEPTH:
        raise _InspectionError(f"{label} exceeds the directory depth limit")
    try:
        with os.scandir(directory_descriptor) as entries:
            for entry in entries:
                entry_budget.consume()
                parts = (*relative_parts, entry.name)
                relative = "/".join(parts)
                display_path = display_root.joinpath(*parts)
                observed = os.stat(
                    entry.name,
                    dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                _notify(inspection_hook, "manifest-entry-observed", display_path)
                if stat.S_ISLNK(observed.st_mode):
                    raise _InspectionError(f"{label} contains a symlink: {relative}")
                if stat.S_ISDIR(observed.st_mode):
                    try:
                        child_descriptor = _open_observed_directory(
                            directory_descriptor,
                            entry.name,
                            observed,
                        )
                    except OSError as error:
                        if error.errno == errno.ELOOP:
                            raise _InspectionError(
                                f"{label} contains a symlink: {relative}"
                            ) from error
                        raise
                    try:
                        _walk_manifest_directory(
                            child_descriptor,
                            parts,
                            display_root,
                            label,
                            manifest,
                            state,
                            read_budget,
                            entry_budget,
                            inspection_hook,
                            capture_limits,
                            captured_files,
                            depth=depth + 1,
                        )
                    finally:
                        os.close(child_descriptor)
                    continue
                if not stat.S_ISREG(observed.st_mode):
                    raise _InspectionError(
                        f"{label} contains a special file: {relative}"
                    )
                try:
                    file_descriptor, opened = _open_observed_regular_file(
                        directory_descriptor,
                        entry.name,
                        observed,
                    )
                except OSError as error:
                    if error.errno == errno.ELOOP:
                        raise _InspectionError(
                            f"{label} contains a symlink: {relative}"
                        ) from error
                    raise
                try:
                    if state["bytes"] + opened.st_size > _MAX_SKILL_TOTAL_BYTES:
                        raise _InspectionError(f"{label} exceeds the total size limit")
                    _notify(inspection_hook, "manifest-file-opened", display_path)
                    digest, read_bytes, captured = _digest_regular_file(
                        file_descriptor,
                        opened,
                        relative,
                        label,
                        read_budget,
                        capture_limit=capture_limits.get(relative),
                    )
                finally:
                    os.close(file_descriptor)
                state["bytes"] += read_bytes
                if state["bytes"] > _MAX_SKILL_TOTAL_BYTES:
                    raise _InspectionError(f"{label} exceeds the total size limit")
                manifest[relative] = (
                    digest,
                    stat.S_IMODE(opened.st_mode) & 0o111,
                )
                if captured is not None:
                    captured_files[relative] = captured
    except _InspectionError:
        raise
    except OSError as error:
        raise _InspectionError(f"{label} cannot be read: {error}") from error


def _digest_regular_file(
    descriptor: int,
    opened: os.stat_result,
    relative: str,
    label: str,
    read_budget: _ReadBudget,
    *,
    capture_limit: int | None,
) -> tuple[str, int, bytes | None]:
    if opened.st_size > _MAX_SKILL_FILE_BYTES:
        raise _InspectionError(f"{label} file exceeds the size limit: {relative}")
    if capture_limit is not None and opened.st_size > capture_limit:
        raise _InspectionError(f"{relative} exceeds the diagnostic size limit")
    digest = hashlib.sha256()
    captured = bytearray() if capture_limit is not None else None
    read_bytes = 0
    while read_bytes <= opened.st_size:
        request = min(_READ_CHUNK_BYTES, opened.st_size + 1 - read_bytes)
        if request <= 0:
            break
        chunk = os.read(descriptor, request)
        if not chunk:
            break
        read_budget.consume(len(chunk))
        read_bytes += len(chunk)
        if read_bytes > opened.st_size:
            raise _InspectionError(f"{label} changed while being read: {relative}")
        digest.update(chunk)
        if captured is not None:
            captured.extend(chunk)
            if len(captured) > capture_limit:
                raise _InspectionError(
                    f"{relative} exceeds the diagnostic size limit"
                )
    after = os.fstat(descriptor)
    if read_bytes != opened.st_size or not _stable_file_metadata(opened, after):
        raise _InspectionError(f"{label} changed while being read: {relative}")
    return (
        digest.hexdigest(),
        read_bytes,
        None if captured is None else bytes(captured),
    )


def _read_bounded_descriptor(
    descriptor: int,
    opened: os.stat_result,
    *,
    limit: int,
    label: str,
    read_budget: _ReadBudget | None,
) -> bytes:
    if opened.st_size > limit:
        raise _InspectionError(f"{label} exceeds the size limit")
    contents = bytearray()
    while len(contents) <= limit:
        request = min(_READ_CHUNK_BYTES, limit + 1 - len(contents))
        if request <= 0:
            break
        chunk = os.read(descriptor, request)
        if not chunk:
            break
        if read_budget is not None:
            read_budget.consume(len(chunk))
        contents.extend(chunk)
    if len(contents) > limit:
        raise _InspectionError(f"{label} exceeds the size limit")
    after = os.fstat(descriptor)
    if not _stable_file_metadata(opened, after) or len(contents) != opened.st_size:
        raise _InspectionError(f"{label} changed while being read")
    return bytes(contents)


def _open_nofollow_directory(path: Path, *, label: str) -> int:
    try:
        parent_descriptor = _open_directory_path(path.parent)
    except (OSError, _InspectionError) as error:
        raise _InspectionError(f"{label} cannot be opened safely: {error}") from error
    try:
        observed = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISDIR(observed.st_mode):
            raise _InspectionError(f"{label} is not a non-symlink directory")
        return _open_observed_directory(parent_descriptor, path.name, observed)
    except (OSError, _InspectionError) as error:
        if isinstance(error, _InspectionError):
            raise
        raise _InspectionError(f"{label} cannot be opened safely: {error}") from error
    finally:
        os.close(parent_descriptor)


def _open_directory_path(path: Path) -> int:
    if not path.is_absolute():
        raise _InspectionError("descriptor traversal requires an absolute path")
    descriptor = os.open(os.sep, _DIRECTORY_NOFOLLOW_FLAGS)
    return _walk_directory_components(descriptor, deque(path.parts[1:]))


def _walk_directory_components(descriptor: int, pending: deque[str]) -> int:
    symlink_count = 0
    try:
        while pending:
            component = pending.popleft()
            if component in ("", ".", os.sep):
                continue
            if component == "..":
                next_descriptor = os.open(
                    "..",
                    _DIRECTORY_NOFOLLOW_FLAGS,
                    dir_fd=descriptor,
                )
                os.close(descriptor)
                descriptor = next_descriptor
                continue
            observed = os.stat(
                component,
                dir_fd=descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(observed.st_mode):
                symlink_count += 1
                if symlink_count > _MAX_SYMLINK_TRAVERSALS:
                    raise _InspectionError("too many symlinks while opening path")
                target = os.readlink(component, dir_fd=descriptor)
                after = os.stat(
                    component,
                    dir_fd=descriptor,
                    follow_symlinks=False,
                )
                if not _same_observed_entry(observed, after):
                    raise _InspectionError("path changed while following a symlink")
                target_path = Path(target)
                target_parts = (
                    target_path.parts[1:]
                    if target_path.is_absolute()
                    else target_path.parts
                )
                if target_path.is_absolute():
                    next_descriptor = os.open(os.sep, _DIRECTORY_NOFOLLOW_FLAGS)
                    os.close(descriptor)
                    descriptor = next_descriptor
                pending.extendleft(reversed(target_parts))
                continue
            next_descriptor = _open_observed_directory(
                descriptor,
                component,
                observed,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _open_observed_directory(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
) -> int:
    if not stat.S_ISDIR(observed.st_mode):
        raise _InspectionError("path component is not a directory")
    descriptor = os.open(name, _DIRECTORY_NOFOLLOW_FLAGS, dir_fd=parent_descriptor)
    try:
        opened = os.fstat(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    if not _same_observed_entry(observed, opened):
        os.close(descriptor)
        raise _InspectionError("directory changed while being opened")
    return descriptor


def _open_observed_symlink_directory(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
) -> int:
    if not stat.S_ISLNK(observed.st_mode):
        raise _InspectionError("path entry is not a symlink")
    target = os.readlink(name, dir_fd=parent_descriptor)
    after = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if not _same_observed_entry(observed, after):
        raise _InspectionError("symlink changed while being opened")
    target_path = Path(target)
    if target_path.is_absolute():
        descriptor = os.open(os.sep, _DIRECTORY_NOFOLLOW_FLAGS)
        parts = target_path.parts[1:]
    else:
        descriptor = os.dup(parent_descriptor)
        parts = target_path.parts
    return _walk_directory_components(descriptor, deque(parts))


def _open_observed_regular_file(
    parent_descriptor: int,
    name: str,
    observed: os.stat_result,
) -> tuple[int, os.stat_result]:
    descriptor = os.open(name, _FILE_NOFOLLOW_FLAGS, dir_fd=parent_descriptor)
    try:
        opened = os.fstat(descriptor)
    except BaseException:
        os.close(descriptor)
        raise
    if not stat.S_ISREG(opened.st_mode):
        os.close(descriptor)
        raise _NotRegularFile("path entry is not a regular file")
    if not _same_observed_entry(observed, opened):
        os.close(descriptor)
        raise _InspectionError("file changed while being opened")
    return descriptor, opened


def _same_observed_entry(first: os.stat_result, second: os.stat_result) -> bool:
    return (
        first.st_dev,
        first.st_ino,
        stat.S_IFMT(first.st_mode),
    ) == (
        second.st_dev,
        second.st_ino,
        stat.S_IFMT(second.st_mode),
    )


def _stable_file_metadata(first: os.stat_result, second: os.stat_result) -> bool:
    return _same_observed_entry(first, second) and (
        first.st_size,
        first.st_mtime_ns,
        first.st_ctime_ns,
    ) == (
        second.st_size,
        second.st_mtime_ns,
        second.st_ctime_ns,
    )


def _descriptor_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _notify(
    inspection_hook: Callable[[str, Path], None] | None,
    event: str,
    path: Path,
) -> None:
    if inspection_hook is not None:
        inspection_hook(event, path)


def _repository_lock_names(
    lock_path: Path,
    repository_sources: Iterable[str],
    home: Path,
    issues: list[ValidationIssue],
    inspection_hook: Callable[[str, Path], None] | None,
) -> frozenset[str]:
    try:
        raw = _read_absolute_regular_file(
            lock_path,
            limit=_MAX_LOCK_BYTES,
            label="skill lock",
            inspection_hook=inspection_hook,
        )
        document = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
        if not isinstance(document, dict) or not isinstance(document.get("skills"), dict):
            raise _InspectionError("skill lock must contain a skills object")
        version = document.get("version")
        if isinstance(version, bool) or not isinstance(version, int) or version < 3:
            raise _InspectionError(
                "skill lock version must be an integer greater than or equal to 3"
            )
    except FileNotFoundError:
        return frozenset()
    except (OSError, UnicodeError, json.JSONDecodeError, _InspectionError) as error:
        issues.append(ValidationIssue(str(lock_path), f"invalid skill lock: {error}"))
        return frozenset()

    normalized_sources = {
        _normalize_lock_descriptor_source(source, lock_path.parent, home=home)
        for source in repository_sources
    }
    names: set[str] = set()
    for name, entry in document["skills"].items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        if not _safe_entry_name(name):
            issues.append(
                ValidationIssue(
                    str(lock_path),
                    f"invalid skill lock: unsafe skill name {name!r}",
                )
            )
            continue
        sources = (entry.get("source"), entry.get("sourceUrl"))
        if any(
            isinstance(source, str)
            and _normalize_lock_descriptor_source(
                source,
                lock_path.parent,
                home=home,
            )
            in normalized_sources
            for source in sources
        ):
            names.add(name)
    return frozenset(names)


def _read_absolute_regular_file(
    path: Path,
    *,
    limit: int,
    label: str,
    inspection_hook: Callable[[str, Path], None] | None,
) -> bytes:
    parent_descriptor = _open_directory_path(path.parent)
    try:
        observed = os.stat(path.name, dir_fd=parent_descriptor, follow_symlinks=False)
        if not stat.S_ISREG(observed.st_mode):
            raise _NotRegularFile(f"{label} must be a regular non-symlink file")
        _notify(inspection_hook, "lock-entry-observed", path)
        descriptor, opened = _open_observed_regular_file(
            parent_descriptor,
            path.name,
            observed,
        )
    finally:
        os.close(parent_descriptor)
    try:
        _notify(inspection_hook, "lock-file-opened", path)
        return _read_bounded_descriptor(
            descriptor,
            opened,
            limit=limit,
            label=label,
            read_budget=None,
        )
    finally:
        os.close(descriptor)


def _safe_entry_name(name: str) -> bool:
    return bool(name) and name not in (".", "..") and "/" not in name and "\x00" not in name


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _InspectionError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _normalize_git_remote_source(source: str, repository_root: Path) -> str:
    return _normalize_source(
        source,
        repository_root,
        home=None,
        allow_github_shorthand=False,
    )


def _normalize_lock_descriptor_source(
    source: str,
    base: Path,
    *,
    home: Path,
) -> str:
    return _normalize_source(
        source,
        base,
        home=home,
        allow_github_shorthand=True,
    )


def _normalize_source(
    source: str,
    base: Path,
    *,
    home: Path | None,
    allow_github_shorthand: bool,
) -> str:
    value = source.strip().rstrip("/")
    match = _GITHUB_SCP.fullmatch(value)
    if match:
        return f"github:{match.group('repo').removesuffix('.git').lower()}"
    parsed = urlparse(value)
    if parsed.hostname and parsed.hostname.lower() == "github.com":
        repo = parsed.path.strip("/").removesuffix(".git")
        return f"github:{repo.lower()}" if repo.count("/") == 1 else value
    if parsed.scheme == "file":
        return f"path:{Path(parsed.path).resolve(strict=False)}"
    if (
        allow_github_shorthand
        and not parsed.scheme
        and not value.startswith((".", "~", "/"))
        and value.count("/") == 1
    ):
        return f"github:{value.removesuffix('.git').lower()}"
    if not parsed.scheme and (
        not allow_github_shorthand
        or value.startswith((".", "~", "/"))
        or os.sep in value
    ):
        if value == "~" or value.startswith("~/"):
            if home is None:
                return value
            path = home if value == "~" else home / value[2:]
        else:
            path = Path(value)
        if not path.is_absolute():
            path = base / path
        return f"path:{path.resolve(strict=False)}"
    return value
