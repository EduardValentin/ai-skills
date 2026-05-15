#!/usr/bin/env python3
"""Load skill trigger scenarios from TOML without third-party dependencies."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Optional


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
    optional_lists = ("description_terms", "skill_terms", "forbidden_terms")

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

        current[key] = ast.literal_eval(raw_value)

    if multiline_key is not None:
        raise ValueError(f"{path}: unterminated multiline string for {multiline_key!r}")

    return scenarios
