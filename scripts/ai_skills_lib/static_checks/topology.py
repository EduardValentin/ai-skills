"""Repository layout and skill-root topology checks."""

from __future__ import annotations

from collections.abc import Iterator
from collections import Counter
from pathlib import Path
import stat

from scripts.ai_skills_lib.authored_content import (
    AuthoredContentReadError,
    AuthoredRepositoryBudget,
    AuthoredTreeEntry,
    find_static_secret_issues,
    snapshot_authored_tree,
)
from scripts.ai_skills_lib.core import (
    PUBLIC_INSTALLER_EXCLUDED_DIRECTORY_NAMES,
    PUBLIC_INSTALLER_EXCLUDED_FILE_NAMES,
    SkillRecord,
    inspect_skill_layout,
)
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    render_safe_diagnostic_path,
    render_safe_diagnostic_text,
    skill_scope,
)


_ALLOWED_SKILL_ROOT_ENTRIES = frozenset(
    {"SKILL.md", "scripts", "references", "assets", "evals"}
)
_DIRECTORY_ENTRIES = _ALLOWED_SKILL_ROOT_ENTRIES - {"SKILL.md"}


def validate_repository_shape(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    skills_directory = root / "skills"
    layout = inspect_skill_layout(root, budget=budget)
    if not skills_directory.exists() and not skills_directory.is_symlink():
        issues.append(
            ValidationIssue(
                scope="repository",
                message="missing canonical skills/ directory",
            )
        )
    for path in layout.invalid_boundaries:
        issues.append(
            ValidationIssue(
                scope="repository",
                message=(
                    f"{render_safe_diagnostic_path(path, relative_to=root)} "
                    "must be a contained non-symlink directory"
                ),
            )
        )
    for path in layout.installer_excluded_boundaries:
        issues.append(
            ValidationIssue(
                scope="repository",
                message=(
                    "public installer discovery excludes directory "
                    f"{render_safe_diagnostic_path(path, relative_to=root)}"
                ),
            )
        )
    if (
        skills_directory not in layout.invalid_boundaries
        and skills_directory.exists()
    ):
        skill_documents = sorted(
            path
            for path in _iter_skill_tree(skills_directory, budget=budget)
            if path.name.casefold() == "skill.md"
        )
        for path in skill_documents:
            if path.name != "SKILL.md":
                issues.append(
                    ValidationIssue(
                        scope="repository",
                        message=(
                            f"{render_safe_diagnostic_path(path, relative_to=root)} "
                            "must be named SKILL.md"
                        ),
                    )
                )
                continue
            relative = path.relative_to(skills_directory)
            if len(relative.parts) != 3:
                issues.append(
                    ValidationIssue(
                        scope="repository",
                        message=(
                            f"{render_safe_diagnostic_path(path, relative_to=root)} "
                            "must use "
                            "skills/<group>/<skill>/SKILL.md"
                        ),
                        )
                    )

    for path in _iter_skill_tree(
        root,
        budget=budget,
        excluded_directories=frozenset({".git"}),
    ):
        if (
            path.name.casefold() == "skill.md"
            and not path.is_relative_to(skills_directory)
        ):
            issues.append(
                ValidationIssue(
                    scope="repository",
                    message=(
                        f"{render_safe_diagnostic_path(path, relative_to=root)} "
                        "is outside the canonical "
                        "skills/<group>/<skill>/SKILL.md source tree"
                    ),
                )
            )

    return issues


def validate_discovered_layout(context: ValidationContext) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not context.skills:
        issues.append(
            ValidationIssue(
                scope="repository",
                message="canonical skills/ directory contains no discoverable skills",
            )
        )
    name_counts = Counter(skill.name for skill in context.skills)
    for name, count in sorted(name_counts.items()):
        if count > 1:
            issues.append(
                ValidationIssue(
                    scope="repository",
                    message=(
                        "duplicate skill name "
                        f"'{render_safe_diagnostic_text(name)}' appears {count} times"
                    ),
                )
            )

    for skill in context.skills:
        if skill.root.name != skill.name:
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        f"folder name '{render_safe_diagnostic_text(skill.root.name)}' "
                        "must match skill name "
                        f"'{render_safe_diagnostic_text(skill.name)}'"
                    ),
                )
            )
    return issues


def validate_skill_root(
    context: ValidationContext, skill: SkillRecord
) -> list[ValidationIssue]:
    scope = skill_scope(context, skill)
    issues: list[ValidationIssue] = []
    try:
        tree = snapshot_authored_tree(
            skill.root,
            budget=context.budget,
        )
    except AuthoredContentReadError as error:
        return [ValidationIssue(scope=scope, message=f"cannot inspect skill root: {error}")]

    root_entries = tuple(
        entry for entry in tree if entry.logical_path.parent == skill.root
    )
    issues.extend(_authored_path_secret_issues(context, skill, tree))
    for entry in root_entries:
        name = entry.logical_path.name
        if name not in _ALLOWED_SKILL_ROOT_ENTRIES:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "unsupported skill-root entry: "
                        f"{render_safe_diagnostic_text(name)}"
                    ),
                )
            )
        elif name in _DIRECTORY_ENTRIES and not entry.is_directory:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"{render_safe_diagnostic_text(name)} must be a directory",
                )
            )

    resolved_root = skill.root.resolve()
    for entry in tree:
        path = entry.logical_path
        if path.name in PUBLIC_INSTALLER_EXCLUDED_FILE_NAMES:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "public installer excludes entry "
                        f"{path.name}: "
                        f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                    ),
                )
            )
        elif (
            (
                entry.is_directory
                or (
                    entry.is_symlink
                    and entry.target_mode is not None
                    and stat.S_ISDIR(entry.target_mode)
                )
            )
            and path.name in PUBLIC_INSTALLER_EXCLUDED_DIRECTORY_NAMES
        ):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "public installer excludes directory "
                        f"{path.name}: "
                        f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                    ),
                )
            )
        if path.name == ".gitkeep":
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        ".gitkeep placeholders are not allowed: "
                        f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                    ),
                )
            )
        if entry.is_symlink:
            target = entry.resolved_path
            if target is None:
                kind = entry.symlink_error or "invalid"
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            f"{kind} symlink: "
                            f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                        ),
                    )
                )
                continue
            if not target.is_relative_to(resolved_root):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            "symlink target must stay inside the skill: "
                            f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                        ),
                    )
                )
        elif entry.is_directory and entry.child_count == 0:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "empty directory is not allowed: "
                        f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                    ),
                )
            )
        elif not entry.is_directory and not entry.is_regular_file:
            if not stat.S_ISLNK(entry.mode):
                issues.append(
                    ValidationIssue(
                        scope=scope,
                        message=(
                            "unsupported special file: "
                            f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                        ),
                    )
                )
    for path in _cyclic_directory_symlinks(tree, skill.root):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "directory symlink cycle is not installable: "
                    f"{render_safe_diagnostic_path(path, relative_to=skill.root)}"
                ),
            )
        )
    return issues


def _authored_path_secret_issues(
    context: ValidationContext,
    skill: SkillRecord,
    tree: tuple[AuthoredTreeEntry, ...],
) -> list[ValidationIssue]:
    representative_paths: dict[str, Path] = {}
    skills_root = context.root / "skills"
    current = skills_root
    for component in skill.root.relative_to(skills_root).parts:
        current /= component
        representative_paths.setdefault(component, current)
    for entry in tree:
        for component in entry.logical_path.relative_to(skill.root).parts:
            representative_paths.setdefault(component, entry.logical_path)

    issues: list[ValidationIssue] = []
    source = Path("authored-path-component")
    for component, path in sorted(representative_paths.items()):
        for finding in find_static_secret_issues(component, source):
            issues.append(
                ValidationIssue(
                    scope=skill_scope(context, skill),
                    message=(
                        f"{render_safe_diagnostic_path(path, relative_to=skill.root)} "
                        "contains a high-confidence secret in an authored path "
                        f"component ({finding.pattern}; {finding.category}); "
                        "value redacted"
                    ),
                )
            )
    return issues


def _cyclic_directory_symlinks(
    tree: tuple[AuthoredTreeEntry, ...],
    skill_root: Path,
) -> tuple[Path, ...]:
    resolved_root = skill_root.resolve()
    logical_directories = {
        skill_root: resolved_root,
        **{
            entry.logical_path: entry.resolved_path
            for entry in tree
            if entry.is_directory and entry.resolved_path is not None
        },
    }
    edges: dict[Path, list[tuple[Path, Path | None]]] = {
        resolved: [] for resolved in logical_directories.values()
    }
    for entry in tree:
        parent = logical_directories.get(entry.logical_path.parent)
        if parent is None or entry.resolved_path is None:
            continue
        if entry.is_directory:
            edges.setdefault(parent, []).append((entry.resolved_path, None))
            edges.setdefault(entry.resolved_path, [])
        elif (
            entry.is_symlink
            and entry.target_mode is not None
            and stat.S_ISDIR(entry.target_mode)
        ):
            edges.setdefault(parent, []).append(
                (entry.resolved_path, entry.logical_path)
            )
            edges.setdefault(entry.resolved_path, [])

    state: dict[Path, int] = {}
    cycles: set[Path] = set()

    def outgoing(
        directory: Path,
    ) -> tuple[tuple[Path, Path | None], ...]:
        return tuple(
            sorted(
                edges.get(directory, ()),
                key=lambda edge: (
                    str(edge[0]),
                    str(edge[1]) if edge[1] is not None else "",
                ),
            )
        )

    state[resolved_root] = 1
    stack: list[tuple[Path, Iterator[tuple[Path, Path | None]]]] = [
        (resolved_root, iter(outgoing(resolved_root)))
    ]
    while stack:
        directory, iterator = stack[-1]
        try:
            target, symlink = next(iterator)
        except StopIteration:
            state[directory] = 2
            stack.pop()
            continue
        else:
            target_state = state.get(target, 0)
            if target_state == 0:
                state[target] = 1
                stack.append((target, iter(outgoing(target))))
            elif target_state == 1 and symlink is not None:
                cycles.add(symlink)

    return tuple(sorted(cycles, key=str))


def _iter_skill_tree(
    root: Path,
    *,
    budget: AuthoredRepositoryBudget,
    excluded_directories: frozenset[str] = frozenset(),
) -> tuple[Path, ...]:
    try:
        entries = snapshot_authored_tree(
            root,
            budget=budget,
            excluded_directories=excluded_directories,
        )
    except AuthoredContentReadError as error:
        raise ValueError(
            f"cannot enumerate authored directory {root}"
        ) from error
    return tuple(entry.logical_path for entry in entries)
