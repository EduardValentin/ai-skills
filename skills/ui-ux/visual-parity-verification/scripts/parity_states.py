#!/usr/bin/env python3
"""Load, validate, resolve and migrate the committed parity-states.json file."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

STATES_FILE = "parity-states.json"
SIDES = ("prototype", "real")
STEP_KINDS = ("click", "hover", "press", "fill", "wait", "waitFor", "use")
LENGTH_WARNING = 12
NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


class StatesError(Exception):
    pass


def load_states(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StatesError(f"{path}: cannot read states file: {error}") from error
    if not isinstance(data, dict):
        raise StatesError(f"{path}: states file must be a JSON object keyed by state name")
    return data


def side_steps(definition: Any, side: str) -> list[Any]:
    if isinstance(definition, list):
        return definition
    if isinstance(definition, dict):
        return definition.get(side, []) or []
    return []


def step_problem(step: Any) -> str | None:
    if not isinstance(step, dict):
        return "is not an object"
    if len(step) != 1:
        return f"has {len(step)} keys"
    kind, value = next(iter(step.items()))
    if kind not in STEP_KINDS:
        return f'unknown kind "{kind}"'
    if kind == "fill" and not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, str) for v in value)):
        return '"fill" expects [selector, text]'
    if kind == "wait" and not (isinstance(value, int) and value >= 0):
        return '"wait" expects milliseconds'
    if kind != "fill" and kind != "wait" and not (isinstance(value, str) and value):
        return f'"{kind}" expects a non-empty string'
    return None


def resolve_state(states: dict[str, Any], name: str, side: str, chain: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    if name in chain:
        raise StatesError("use cycle: " + " -> ".join(chain + (name,)))
    if name not in states:
        raise StatesError(f'state "{name}" is not defined')
    resolved: list[dict[str, Any]] = []
    for step in side_steps(states[name], side):
        if isinstance(step, dict) and "use" in step:
            resolved.extend(resolve_state(states, step["use"], side, chain + (name,)))
        else:
            resolved.append(step)
    return resolved


def state_sides(states: dict[str, Any], name: str) -> dict[str, list[dict[str, Any]]]:
    return {side: resolve_state(states, name, side) for side in SIDES}


def validate_states(states: dict[str, Any]) -> tuple[list[str], list[str]]:
    problems: list[str] = []
    warnings: list[str] = []
    for name, definition in states.items():
        label = f'state "{name}"'
        if not NAME_PATTERN.match(name):
            problems.append(f"{label}: name must match letters, digits, dash or underscore")
        if isinstance(definition, dict):
            for side in definition:
                if side not in SIDES:
                    problems.append(f'{label}: unknown side "{side}"')
        elif not isinstance(definition, list):
            problems.append(f"{label}: must be a step list or an object with prototype and real step lists")
            continue
        declared_sides = ("prototype",) if isinstance(definition, list) else SIDES
        for side in declared_sides:
            for index, step in enumerate(side_steps(definition, side)):
                problem = step_problem(step)
                if problem:
                    problems.append(f"{label}: step {index} {problem}" if problem.startswith(("has", "is")) else f"{label}: step {index}: {problem}")
                elif "use" in step and step["use"] not in states:
                    problems.append(f'{label}: use "{step["use"]}" is not defined')
                elif "wait" in step:
                    warnings.append(f"{label}: step {index} is a fixed wait; prefer waitFor or the capture tool's readiness wait")
    for name in states:
        for side in SIDES:
            try:
                resolved = resolve_state(states, name, side)
            except StatesError as error:
                if "cycle" in str(error):
                    problems.append(f'state "{name}": {error}')
                continue
            if len(resolved) > LENGTH_WARNING:
                warnings.append(f'state "{name}": {side} resolves to {len(resolved)} steps; split it or shorten it')
    return problems, warnings
