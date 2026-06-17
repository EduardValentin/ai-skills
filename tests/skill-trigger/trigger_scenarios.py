#!/usr/bin/env python3
"""Load skill trigger scenarios from TOML without third-party dependencies."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Optional


def discover_skill_files(repo_root: Path) -> dict[str, Path]:
    """Return canonical and plugin skill files keyed by declared skill name."""

    skill_files = [
        *sorted((repo_root / "skills").glob("*/SKILL.md")),
        *sorted((repo_root / "plugins").glob("*/skills/*/SKILL.md")),
    ]
    discovered: dict[str, Path] = {}

    for skill_file in skill_files:
        frontmatter = parse_frontmatter(skill_file.read_text(encoding="utf-8"))
        skill_name = frontmatter.get("name", skill_file.parent.name)
        existing = discovered.get(skill_name)
        if existing is not None:
            raise ValueError(
                f"duplicate skill name {skill_name!r}: {existing.relative_to(repo_root)} "
                f"and {skill_file.relative_to(repo_root)}"
            )
        discovered[skill_name] = skill_file

    return discovered


def parse_frontmatter(skill_doc: str) -> dict[str, str]:
    if not skill_doc.startswith("---\n"):
        return {}

    try:
        _, body, _ = skill_doc.split("---\n", 2)
    except ValueError:
        return {}

    values: dict[str, str] = {}
    for raw_line in body.splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    try:
        import tomllib  # type: ignore[attr-defined]
    except ModuleNotFoundError:
        scenarios = _load_with_fallback_parser(path)
    else:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        scenarios = data.get("scenario", [])

    if not isinstance(scenarios, list):
        raise ValueError(f"{path} must define [[scenario]] tables")

    return [_normalize_scenario(path, scenario) for scenario in scenarios]


def _normalize_scenario(path: Path, scenario: dict[str, Any]) -> dict[str, Any]:
    required_strings = ("id", "skill", "prompt")
    optional_lists = ("forbidden_terms", "response_forbidden_terms")

    for key in required_strings:
        value = scenario.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{path}: scenario is missing non-empty string field {key!r}")
        scenario[key] = value.strip()

    for key in optional_lists:
        value = scenario.get(key, [])
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError(f"{path}: scenario {scenario['id']} field {key!r} must be a string list")
        scenario[key] = value

    should_trigger = scenario.get("should_trigger", True)
    if not isinstance(should_trigger, bool):
        raise ValueError(f"{path}: scenario {scenario['id']} field 'should_trigger' must be a boolean")
    scenario["should_trigger"] = should_trigger

    return scenario


def _load_with_fallback_parser(path: Path) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    multiline_key: Optional[str] = None
    multiline_value: list[str] = []

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if multiline_key is not None:
            if line.endswith('"""'):
                multiline_value.append(raw_line[: raw_line.rfind('"""')])
                assert current is not None
                current[multiline_key] = "\n".join(multiline_value).strip()
                multiline_key = None
                multiline_value = []
            else:
                multiline_value.append(raw_line)
            continue

        if line == "[[scenario]]":
            current = {}
            scenarios.append(current)
            continue

        if current is None:
            raise ValueError(f"{path}:{line_number}: expected [[scenario]] before field assignment")

        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected key = value")

        key, raw_value = [part.strip() for part in line.split("=", 1)]
        if raw_value.startswith('"""'):
            content = raw_value[3:]
            if content.endswith('"""'):
                current[key] = content[:-3].strip()
            else:
                multiline_key = key
                multiline_value = [content] if content else []
            continue

        if raw_value == "true":
            current[key] = True
        elif raw_value == "false":
            current[key] = False
        else:
            current[key] = ast.literal_eval(raw_value)

    if multiline_key is not None:
        raise ValueError(f"{path}: unterminated multiline string for {multiline_key!r}")

    return scenarios
