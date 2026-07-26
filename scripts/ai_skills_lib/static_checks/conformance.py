"""Pinned official conformance and dependency preflight."""

from __future__ import annotations

import hashlib
import importlib
from importlib import metadata as importlib_metadata
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType

from scripts.ai_skills_lib.issues import ValidationIssue
from scripts.ai_skills_lib.static_checks.context import (
    ValidationContext,
    render_safe_diagnostic_text,
    skill_scope,
)


SKILLS_REF_INSTALL_COMMAND = "python3 -m pip install -r requirements-test.txt"
EXPECTED_SKILLS_REF_COMMIT = "38a2ff82958afee88dadf4831509e6f7e9d8ef4e"
_EXPECTED_SKILLS_REF_URL = "https://github.com/agentskills/agentskills.git"
_EXPECTED_SKILLS_REF_SUBDIRECTORY = "skills-ref"
_EXPECTED_SKILLS_REF_REQUIREMENT = (
    "skills-ref @ git+"
    f"{_EXPECTED_SKILLS_REF_URL}@{EXPECTED_SKILLS_REF_COMMIT}"
    f"#subdirectory={_EXPECTED_SKILLS_REF_SUBDIRECTORY}"
)
_EXPECTED_SKILLS_REF_SOURCES = {
    "__init__.py": (
        449,
        "a3da705c4847ac19c016f67e3a6c56a94e160986a823d148c21dca4c9b312b4a",
    ),
    "cli.py": (
        2697,
        "cdcc2cc418cac2e47340455b406e39a73c0906d6184e0920d12e8c341ce5b139",
    ),
    "errors.py": (
        572,
        "5780d314db735400c3959d20ed19a8c59445786d35a1a1b7cf368f01576d91f4",
    ),
    "models.py": (
        1461,
        "c6645fcfc04c78e773657856e8c6058e43951ce283e9b303ca721df1acac6a7b",
    ),
    "parser.py": (
        3413,
        "9a74c9a90eb217b82bec27570332eab74547acfbee2973c0a8bcd23f6c7bc211",
    ),
    "prompt.py": (
        1724,
        "8ed90a61685b84050a8fde32e63d5f3f04c205b05bfc5f8ef4bb2f101cc9cf15",
    ),
    "validator.py": (
        5154,
        "b5ee3d8537c83c959c31c2cb080a5227646ede5aea545f1ac835ed3c4645f6c5",
    ),
}
_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_verified_skills_ref_module: ModuleType | None = None
_verified_skills_ref_sources: tuple[tuple[str, str], ...] | None = None
_verified_skills_ref_snapshot: tempfile.TemporaryDirectory[str] | None = None


def preflight_reference_conformance() -> ModuleType:
    try:
        distribution = importlib_metadata.distribution("skills-ref")
        distribution_root = Path(distribution.locate_file("")).resolve(strict=True)
        direct_url_text = distribution.read_text("direct_url.json")
        if direct_url_text is None:
            raise ValueError("skills-ref direct URL metadata is missing")
        direct_url = json.loads(direct_url_text)
        vcs_info = direct_url.get("vcs_info")
        requirement_lines = (
            _REPOSITORY_ROOT / "requirements-test.txt"
        ).read_text(encoding="utf-8").splitlines()
        if (
            not isinstance(vcs_info, dict)
            or direct_url.get("url") != _EXPECTED_SKILLS_REF_URL
            or direct_url.get("subdirectory") != _EXPECTED_SKILLS_REF_SUBDIRECTORY
            or vcs_info.get("vcs") != "git"
            or vcs_info.get("commit_id") != EXPECTED_SKILLS_REF_COMMIT
            or vcs_info.get("requested_revision") != EXPECTED_SKILLS_REF_COMMIT
            or _EXPECTED_SKILLS_REF_REQUIREMENT not in requirement_lines
        ):
            raise ValueError("skills-ref provenance does not match the reviewed pin")
        verified_sources = _read_verified_skills_ref_sources(distribution_root)
        return _import_verified_skills_ref(verified_sources)
    except (
        AttributeError,
        ImportError,
        importlib_metadata.PackageNotFoundError,
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        raise RuntimeError(SKILLS_REF_INSTALL_COMMAND) from error


def _read_verified_skills_ref_sources(
    distribution_root: Path,
) -> dict[str, bytes]:
    package_root = distribution_root / "skills_ref"
    if package_root.is_symlink() or not package_root.is_dir():
        raise ValueError("skills-ref package root is invalid")

    discovered: dict[str, Path] = {}
    with os.scandir(package_root) as entries:
        for count, entry in enumerate(entries, start=1):
            if count > 32:
                raise ValueError("skills-ref package contains unexpected entries")
            if entry.is_symlink():
                raise ValueError("skills-ref package contains a symlink")
            if entry.is_dir(follow_symlinks=False):
                if entry.name != "__pycache__":
                    raise ValueError("skills-ref package contains an unexpected directory")
                continue
            if not entry.is_file(follow_symlinks=False) or not entry.name.endswith(".py"):
                raise ValueError("skills-ref package contains an unexpected file")
            discovered[entry.name] = Path(entry.path)

    if set(discovered) != set(_EXPECTED_SKILLS_REF_SOURCES):
        raise ValueError("skills-ref source manifest does not match the reviewed pin")

    verified: dict[str, bytes] = {}
    for name, (expected_size, expected_sha256) in _EXPECTED_SKILLS_REF_SOURCES.items():
        path = discovered[name]
        if path.stat().st_size != expected_size:
            raise ValueError("skills-ref source size does not match the reviewed pin")
        with path.open("rb") as source:
            content = source.read(expected_size + 1)
        if (
            len(content) != expected_size
            or hashlib.sha256(content).hexdigest() != expected_sha256
        ):
            raise ValueError("skills-ref source digest does not match the reviewed pin")
        verified[name] = content
    return verified


def _import_verified_skills_ref(sources: dict[str, bytes]) -> ModuleType:
    global _verified_skills_ref_module
    global _verified_skills_ref_snapshot
    global _verified_skills_ref_sources

    source_identity = tuple(
        (name, hashlib.sha256(content).hexdigest())
        for name, content in sorted(sources.items())
    )
    if (
        _verified_skills_ref_module is not None
        and _verified_skills_ref_sources == source_identity
        and sys.modules.get("skills_ref") is _verified_skills_ref_module
    ):
        return _verified_skills_ref_module

    for module_name in tuple(sys.modules):
        if module_name == "skills_ref" or module_name.startswith("skills_ref."):
            sys.modules.pop(module_name, None)
    if _verified_skills_ref_snapshot is not None:
        _verified_skills_ref_snapshot.cleanup()

    snapshot = tempfile.TemporaryDirectory(prefix="ai-skills-skills-ref-")
    snapshot_root = Path(snapshot.name)
    package_root = snapshot_root / "skills_ref"
    package_root.mkdir()
    try:
        for name, content in sources.items():
            (package_root / name).write_bytes(content)
        sys.path.insert(0, str(snapshot_root))
        importlib.invalidate_caches()
        try:
            module = importlib.import_module("skills_ref")
        finally:
            sys.path.remove(str(snapshot_root))
    except BaseException:
        for module_name in tuple(sys.modules):
            if module_name == "skills_ref" or module_name.startswith("skills_ref."):
                sys.modules.pop(module_name, None)
        snapshot.cleanup()
        _verified_skills_ref_module = None
        _verified_skills_ref_snapshot = None
        _verified_skills_ref_sources = None
        raise

    _verified_skills_ref_module = module
    _verified_skills_ref_snapshot = snapshot
    _verified_skills_ref_sources = source_identity
    return module


def validate_reference_conformance(
    context: ValidationContext,
) -> list[ValidationIssue]:
    reference_validator = preflight_reference_conformance()
    issues: list[ValidationIssue] = []
    for skill in context.skills:
        scope = skill_scope(context, skill)
        try:
            with tempfile.TemporaryDirectory(prefix="ai-skills-conformance-") as directory:
                snapshot_root = Path(directory) / skill.name
                snapshot_root.mkdir()
                (snapshot_root / "SKILL.md").write_text(
                    skill.source_text,
                    encoding="utf-8",
                )
                problems = tuple(reference_validator.validate(snapshot_root))
        except (OSError, RuntimeError) as error:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=f"official conformance snapshot failed: {type(error).__name__}",
                )
            )
            continue
        for problem in problems:
            issues.append(
                ValidationIssue(
                    scope=scope,
                    message=render_safe_diagnostic_text(problem),
                )
            )
    return issues
