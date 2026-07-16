"""Deterministic local and official validation for repository skills."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Iterator
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any

try:
    import skills_ref
except ImportError:  # pragma: no cover - exercised by an environment without test dependencies
    skills_ref = None

from scripts.ai_skills_lib.core import SkillRecord, discover_testable_skills
from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.secret_patterns import SECRET_PATTERNS, SecretMatch, SecretPattern


_APPROVED_STATUSES = frozenset(
    {"public-ready", "config-required", "local-required", "experimental"}
)
_ALLOWED_SKILL_ROOT_ENTRIES = frozenset(
    {"SKILL.md", "scripts", "references", "assets", "evals"}
)
_DIRECTORY_ENTRIES = _ALLOWED_SKILL_ROOT_ENTRIES - {"SKILL.md"}
_REPETITION_KEYS = frozenset(
    {"runs", "run_count", "run-count", "repetitions", "repeat", "repeats", "attempts"}
)
_SKILLS_REF_INSTALL_COMMAND = "python3 -m pip install -r requirements-test.txt"

_PERSONAL_PATH_PATTERN = re.compile(
    r"(?:/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)"
)
_CONFIG_VARIABLE_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9_]*(?:_API_KEY|_TOKEN|_SECRET|_PATH|_FILE|_DIR|_CONFIG|_HOME)\b"
)
_MARKDOWN_LINK_PATTERN = re.compile(
    r"!?\[[^\]]*\]\((?P<target><[^>]+>|[^)\s]+)(?:\s+[^)]*)?\)"
)
_BUNDLED_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])(?P<target>(?:scripts|references|assets|evals/fixtures)/"
    r"[A-Za-z0-9._/-]+)"
)
_SKILL_REFERENCE_PATTERNS = (
    re.compile(r"`(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)`\s+skill\b", re.IGNORECASE),
    re.compile(r"\b(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)\s+skill\b", re.IGNORECASE),
    re.compile(r"\$(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)\b"),
    re.compile(r"skill://(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)\b", re.IGNORECASE),
    re.compile(
        r"skills/(?:[a-z0-9-]+/)?(?P<name>[a-z0-9]+(?:-[a-z0-9]+)*)/SKILL\.md",
        re.IGNORECASE,
    ),
)
_GENERIC_SKILL_WORDS = frozenset(
    {"another", "agent", "local", "other", "public", "repository", "retained", "this"}
)
_COLLABORATOR_PATTERN = re.compile(
    r"(?:\b(?:native\s+)?agents?\b|\b(?:codex|claude|antigravity|cursor|gemini)\s+harness\b|"
    r"\bharness(?:es)?\b|\btools?\b|\bmcp__[a-z0-9_]+|\b[a-z][a-z0-9_]*__"
    r"[a-z0-9_]+|\bspawn_agent\b)",
    re.IGNORECASE,
)
_COLLABORATION_BEHAVIOR_PATTERN = re.compile(
    r"\b(?:requires?|required|needs?|available|unavailable|fallback|without|optional|configured|"
    r"installed)\b",
    re.IGNORECASE,
)


def find_static_secret_issues(text: str, source: Path) -> list[SecretMatch]:
    """Return value-free findings for authored high-confidence secrets."""
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
            column = start - last_newline
            findings.append(
                SecretMatch(
                    pattern=pattern.name,
                    category=pattern.category,
                    confidence=pattern.confidence,
                    source=source,
                    line=line,
                    column=column,
                )
            )
    return findings


def run_static_validation(root: Path) -> list[ValidationIssue]:
    """Apply repository policy uniformly to every discovered public skill."""
    root = root.resolve()
    issues = _validate_repository_shape(root)
    try:
        skills = discover_testable_skills(root)
    except (OSError, ValueError) as error:
        issues.append(ValidationIssue(scope="static", message=str(error)))
        return _deduplicate_issues(issues)

    issues.extend(_validate_discovered_layout(root, skills))
    public_names = {skill.name for skill in skills}
    for skill in skills:
        issues.extend(_validate_skill(root, skill, public_names))
    return _deduplicate_issues(issues)


def run_reference_conformance(root: Path) -> list[ValidationIssue]:
    """Map pinned official validator problems into repository issues."""
    if skills_ref is None:
        raise RuntimeError(_SKILLS_REF_INSTALL_COMMAND)

    try:
        skills = discover_testable_skills(root.resolve())
    except (OSError, ValueError) as error:
        return [ValidationIssue(scope="reference conformance", message=str(error))]

    issues: list[ValidationIssue] = []
    for skill in skills:
        scope = _skill_scope(root, skill)
        for problem in skills_ref.validate(skill.root):
            issues.append(ValidationIssue(scope=scope, message=problem))
    return issues


def _validate_repository_shape(root: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    skills_directory = root / "skills"
    if skills_directory.exists():
        for path in sorted(skills_directory.rglob("SKILL.md")):
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
        for path in sorted(skills_directory.rglob("skill.md")):
            issues.append(
                ValidationIssue(
                    scope="repository",
                    message=f"{path.relative_to(root)} must be named SKILL.md",
                )
            )

    duplicate_patterns = (
        "plugins/*/skills/*/SKILL.md",
        "codex/skills/*/SKILL.md",
        "claude/skills/*/SKILL.md",
    )
    for pattern in duplicate_patterns:
        for path in sorted(root.glob(pattern)):
            if ".system" in path.parts:
                continue
            issues.append(
                ValidationIssue(
                    scope="repository",
                    message=f"duplicate public skill source: {path.relative_to(root)}",
                )
            )

    if (root / "dist").exists():
        issues.append(ValidationIssue(scope="repository", message="dist/ must not exist"))
    return issues


def _validate_discovered_layout(root: Path, skills: list[SkillRecord]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    name_counts = Counter(skill.name for skill in skills)
    for name, count in sorted(name_counts.items()):
        if count > 1:
            issues.append(
                ValidationIssue(
                    scope="repository",
                    message=f"duplicate skill name '{name}' appears {count} times",
                )
            )

    for skill in skills:
        if skill.root.name != skill.name:
            issues.append(
                ValidationIssue(
                    scope=_skill_scope(root, skill),
                    message=f"folder name '{skill.root.name}' must match skill name '{skill.name}'",
                )
            )
    return issues


def _validate_skill(
    root: Path, skill: SkillRecord, public_names: set[str]
) -> list[ValidationIssue]:
    scope = _skill_scope(root, skill)
    issues = _validate_skill_tree(skill, scope)
    metadata = skill.frontmatter.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    status = metadata.get("status")
    if status is None:
        issues.append(ValidationIssue(scope=scope, message="metadata.status is required"))
    elif status not in _APPROVED_STATUSES:
        approved = ", ".join(sorted(_APPROVED_STATUSES))
        issues.append(
            ValidationIssue(scope=scope, message=f"metadata.status must be one of: {approved}")
        )

    allows_tool_references = metadata.get("allows_tool_references")
    if allows_tool_references not in (None, "true", "false"):
        issues.append(
            ValidationIssue(
                scope=scope,
                message="metadata.allows_tool_references must be 'true' or 'false'",
            )
        )

    compatibility = skill.frontmatter.get("compatibility")
    compatibility_text = compatibility if isinstance(compatibility, str) else ""
    if status in {"config-required", "local-required"} and not compatibility_text.strip():
        issues.append(
            ValidationIssue(
                scope=scope,
                message=f"metadata.status '{status}' requires non-empty compatibility",
            )
        )
    if (
        status == "config-required"
        and compatibility_text.strip()
        and not _CONFIG_VARIABLE_PATTERN.search(compatibility_text)
    ):
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "config-required compatibility must name an environment variable or "
                    "config-file path variable"
                ),
            )
        )

    skill_text, read_issues = _read_text(skill.path, scope)
    issues.extend(read_issues)
    if skill_text is not None:
        other_skill_references = _explicit_skill_references(skill_text) - {skill.name}
        mentions_collaborator = bool(other_skill_references) or bool(
            _COLLABORATOR_PATTERN.search(skill_text)
        )
        if mentions_collaborator and allows_tool_references != "true":
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="collaborator reference requires metadata.allows_tool_references: 'true'",
                )
            )
        if allows_tool_references == "true" and not _documents_collaboration(
            compatibility_text
        ):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        "metadata.allows_tool_references: 'true' must document collaborator "
                        "requirements or fallback behavior in compatibility"
                    ),
                )
            )
        for referenced_name in sorted(other_skill_references - public_names):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"references unknown public skill '{referenced_name}'",
                )
            )
        issues.extend(_validate_authored_text(root, skill, skill.path, skill_text))

    issues.extend(_validate_reference_files(root, skill))
    issues.extend(_validate_script_files(root, skill))
    issues.extend(_validate_eval_files(root, skill))
    return issues


def _validate_skill_tree(skill: SkillRecord, scope: str) -> list[ValidationIssue]:
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
            try:
                target = path.resolve(strict=True)
            except (FileNotFoundError, OSError):
                issues.append(
                    ValidationIssue(scope=scope, message=f"broken symlink: {relative}")
                )
                continue
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
                    ValidationIssue(scope=scope, message=f"empty directory is not allowed: {relative}")
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


def _validate_reference_files(root: Path, skill: SkillRecord) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    references_root = skill.root / "references"
    if not references_root.is_dir() or not _is_contained_path(references_root, skill.root):
        return issues
    for source in sorted(references_root.rglob("*.md")):
        if not _is_contained_path(source, skill.root):
            continue
        text, read_issues = _read_text(source, _skill_scope(root, skill))
        issues.extend(read_issues)
        if text is not None:
            issues.extend(_validate_authored_text(root, skill, source, text))
    return issues


def _validate_script_files(root: Path, skill: SkillRecord) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    scope = _skill_scope(root, skill)
    scripts_root = skill.root / "scripts"
    if not scripts_root.is_dir() or not _is_contained_path(scripts_root, skill.root):
        return issues
    for source in sorted(scripts_root.rglob("*")):
        if source.is_dir() or not _is_contained_path(source, skill.root):
            continue
        if not os.access(source, os.X_OK):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"{source.relative_to(skill.root)} must be executable",
                )
            )
        text, read_issues = _read_text(source, scope)
        issues.extend(read_issues)
        if text is not None:
            issues.extend(_personal_path_issues(root, skill, source, text))
            issues.extend(_secret_issues(root, skill, source, text))
    return issues


def _validate_eval_files(root: Path, skill: SkillRecord) -> list[ValidationIssue]:
    scope = _skill_scope(root, skill)
    issues: list[ValidationIssue] = []
    evals_root = skill.root / "evals"
    evals_path = evals_root / "evals.json"
    triggers_path = evals_root / "triggers.json"

    if not evals_path.is_file():
        issues.append(ValidationIssue(scope=scope, message="missing evals/evals.json"))
    if not triggers_path.is_file():
        issues.append(ValidationIssue(scope=scope, message="missing evals/triggers.json"))

    parsed: dict[Path, Any] = {}
    if evals_root.is_dir() and _is_contained_path(evals_root, skill.root):
        for path in sorted(evals_root.rglob("*.json")):
            if not _is_contained_path(path, skill.root):
                continue
            data, parse_issues = _load_json(root, skill, path)
            issues.extend(parse_issues)
            if data is not None:
                parsed[path] = data
                text = path.read_text(encoding="utf-8")
                issues.extend(_secret_issues(root, skill, path, text))

        for path in sorted(evals_root.rglob("*")):
            if path.is_dir() or not _is_contained_path(path, skill.root):
                continue
            text = _read_text_fixture(path)
            if text is not None:
                issues.extend(_secret_issues(root, skill, path, text))

    if evals_path in parsed:
        evals_data = parsed[evals_path]
        evals = evals_data.get("evals") if isinstance(evals_data, dict) else None
        if not isinstance(evals, list) or not evals:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message="evals/evals.json must contain an 'evals' list",
                )
            )
        else:
            for index, item in enumerate(evals):
                if not isinstance(item, dict):
                    issues.append(
                        ValidationIssue(
                            scope=scope,
                            message=f"evals/evals.json eval {index} must be an object",
                        )
                    )
                    continue
                issues.extend(_fixture_path_issues(skill, scope, item))

    if triggers_path in parsed:
        issues.extend(_trigger_schema_issues(scope, parsed[triggers_path]))
    return issues


def _load_json(
    root: Path, skill: SkillRecord, path: Path
) -> tuple[Any | None, list[ValidationIssue]]:
    scope = _skill_scope(root, skill)
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return None, [
            ValidationIssue(
                scope=scope,
                message=f"{path.relative_to(skill.root)} contains invalid JSON: {error}",
            )
        ]


def _trigger_schema_issues(scope: str, data: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(data, dict):
        return [
            ValidationIssue(
                scope=scope,
                message="evals/triggers.json must contain a 'queries' list",
            )
        ]

    repetition_key = next(
        (key for key in _iter_mapping_keys(data) if key.lower() in _REPETITION_KEYS), None
    )
    if repetition_key is not None:
        issues.append(
            ValidationIssue(
                scope=scope,
                message=(
                    "evals/triggers.json must not contain runner repetition configuration "
                    f"('{repetition_key}')"
                ),
            )
        )

    queries = data.get("queries")
    if not isinstance(queries, list) or not queries:
        issues.append(
            ValidationIssue(
                scope=scope,
                message="evals/triggers.json must contain a 'queries' list",
            )
        )
        return issues

    decisions: list[bool] = []
    for index, query in enumerate(queries):
        if (
            not isinstance(query, dict)
            or not isinstance(query.get("query"), str)
            or not query["query"].strip()
            or not isinstance(query.get("should_trigger"), bool)
        ):
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=(
                        f"evals/triggers.json query {index} requires non-empty 'query' and "
                        "boolean 'should_trigger'"
                    ),
                )
            )
            continue
        decisions.append(query["should_trigger"])

    if True not in decisions:
        issues.append(
            ValidationIssue(
                scope=scope,
                message="evals/triggers.json requires a should_trigger: true query",
            )
        )
    if False not in decisions:
        issues.append(
            ValidationIssue(
                scope=scope,
                message="evals/triggers.json requires a should_trigger: false query",
            )
        )
    return issues


def _iter_mapping_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str):
                yield key
            yield from _iter_mapping_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_mapping_keys(child)


def _fixture_path_issues(skill: SkillRecord, scope: str, value: Any) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if isinstance(key, str) and "fixture" in key.lower():
                for fixture in _string_values(child):
                    issues.extend(_validate_fixture_path(skill, scope, fixture))
            else:
                issues.extend(_fixture_path_issues(skill, scope, child))
    elif isinstance(value, list):
        for child in value:
            issues.extend(_fixture_path_issues(skill, scope, child))
    return issues


def _string_values(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str):
                yield child


def _validate_fixture_path(
    skill: SkillRecord, scope: str, fixture: str
) -> list[ValidationIssue]:
    if _is_external_reference(fixture):
        return []
    pure_path = PurePosixPath(fixture)
    if pure_path.is_absolute() or ".." in pure_path.parts or "\\" in fixture:
        return [
            ValidationIssue(
                scope=scope,
                message=f"fixture path must stay inside the skill: {fixture}",
            )
        ]
    if fixture.startswith("evals/"):
        path = skill.root / pure_path
    elif fixture.startswith("fixtures/"):
        path = skill.root / "evals" / pure_path
    else:
        path = skill.root / "evals" / pure_path
    if not path.exists():
        return [
            ValidationIssue(scope=scope, message=f"fixture path does not exist: {fixture}")
        ]
    try:
        contained = path.resolve(strict=True).is_relative_to(skill.root.resolve())
    except OSError:
        contained = False
    if not contained:
        return [
            ValidationIssue(
                scope=scope,
                message=f"fixture path must stay inside the skill: {fixture}",
            )
        ]
    return []


def _validate_authored_text(
    root: Path, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    issues = _personal_path_issues(root, skill, source, text)
    issues.extend(_secret_issues(root, skill, source, text))
    issues.extend(_local_reference_issues(root, skill, source, text))
    return issues


def _personal_path_issues(
    root: Path, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    scope = _skill_scope(root, skill)
    issues: list[ValidationIssue] = []
    for match in _PERSONAL_PATH_PATTERN.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        issues.append(
            ValidationIssue(
                scope=scope,
                message=f"{source.relative_to(skill.root)}:{line} contains a personal absolute path",
            )
        )
    return issues


def _secret_issues(
    root: Path, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    scope = _skill_scope(root, skill)
    return [
        ValidationIssue(
            scope=scope,
            message=(
                f"{source.relative_to(skill.root)}:{finding.line}:{finding.column}: "
                f"high-confidence secret {finding.pattern} ({finding.category}); value redacted"
            ),
        )
        for finding in find_static_secret_issues(text, source)
    ]


def _local_reference_issues(
    root: Path, skill: SkillRecord, source: Path, text: str
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    targets = [match.group("target") for match in _MARKDOWN_LINK_PATTERN.finditer(text)]
    targets.extend(match.group("target") for match in _BUNDLED_PATH_PATTERN.finditer(text))
    for target in targets:
        issues.extend(_validate_local_target(root, skill, source, target))
    return issues


def _validate_local_target(
    root: Path, skill: SkillRecord, source: Path, raw_target: str
) -> list[ValidationIssue]:
    target = raw_target[1:-1] if raw_target.startswith("<") and raw_target.endswith(">") else raw_target
    if _is_external_reference(target) or target.startswith("#"):
        return []
    target = target.split("#", 1)[0].split("?", 1)[0]
    if not target:
        return []

    scope = _skill_scope(root, skill)
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

    referenced_path = skill.root / pure_path
    if not referenced_path.is_file():
        return [
            ValidationIssue(
                scope=scope,
                message=f"referenced local file does not exist: {target}",
            )
        ]
    try:
        contained = referenced_path.resolve(strict=True).is_relative_to(skill.root.resolve())
    except OSError:
        contained = False
    if not contained:
        return [
            ValidationIssue(
                scope=scope,
                message=f"referenced local file must stay inside the skill: {target}",
            )
        ]
    return []


def _is_external_reference(target: str) -> bool:
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)) or target.startswith("//")


def _explicit_skill_references(text: str) -> set[str]:
    references: set[str] = set()
    for pattern in _SKILL_REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group("name").lower()
            if name not in _GENERIC_SKILL_WORDS:
                references.add(name)
    return references


def _documents_collaboration(compatibility: str) -> bool:
    if not compatibility.strip() or not _COLLABORATION_BEHAVIOR_PATTERN.search(compatibility):
        return False
    return bool(
        _COLLABORATOR_PATTERN.search(compatibility)
        or _explicit_skill_references(compatibility)
        or re.search(r"\b(?:fallback|unavailable|without)\b", compatibility, re.IGNORECASE)
    )


def _read_text(path: Path, scope: str) -> tuple[str | None, list[ValidationIssue]]:
    try:
        return path.read_text(encoding="utf-8"), []
    except (OSError, UnicodeDecodeError) as error:
        return None, [ValidationIssue(scope=scope, message=f"cannot read {path.name}: {error}")]


def _read_text_fixture(path: Path) -> str | None:
    try:
        content = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _is_contained_path(path: Path, skill_root: Path) -> bool:
    try:
        return path.resolve(strict=True).is_relative_to(skill_root.resolve(strict=True))
    except OSError:
        return False


def _has_fake_prefix(text: str, start: int) -> bool:
    return text[max(0, start - len("FAKE_")) : start] == "FAKE_"


def _is_safe_assigned_value(raw_value: str) -> bool:
    value = raw_value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1].strip()
    if not value:
        return True
    if value.startswith("FAKE_"):
        return True
    if value.startswith("$") or value.startswith("{{") and value.endswith("}}"):
        return True
    if re.fullmatch(r"(?:os\.environ|process\.env)(?:\[[^\]]+\]|\.[A-Z][A-Z0-9_]*)", value):
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
    if re.fullmatch(r"(?:X{3,}|\*{3,})", normalized):
        return True
    return False


def _skill_scope(root: Path, skill: SkillRecord) -> str:
    try:
        return str(skill.root.relative_to(root.resolve()))
    except ValueError:
        return str(skill.root)


def _deduplicate_issues(issues: Iterable[ValidationIssue]) -> list[ValidationIssue]:
    deduplicated: list[ValidationIssue] = []
    seen: set[tuple[str, str, str]] = set()
    for issue in issues:
        key = (issue.scope, issue.message, issue.severity)
        if key not in seen:
            seen.add(key)
            deduplicated.append(issue)
    return deduplicated


__all__ = [
    "SecretMatch",
    "SecretPattern",
    "find_static_secret_issues",
    "run_reference_conformance",
    "run_static_validation",
]
