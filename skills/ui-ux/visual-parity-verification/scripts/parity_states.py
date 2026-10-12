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
ACTIONS_DIR = "parity-actions"
MIN_SHARED_PREFIX = 3
REFERENCE_PATTERN = re.compile(r"\(([A-Za-z0-9_-]+)\.json\)")


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
    if kind == "wait" and not (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
        return '"wait" expects milliseconds'
    if kind != "fill" and kind != "wait" and not (isinstance(value, str) and value):
        return f'"{kind}" expects a non-empty string'
    return None


MAX_CHAIN_DEPTH = 64


def resolve_state(states: dict[str, Any], name: str, side: str, chain: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    if name in chain:
        raise StatesError("use cycle: " + " -> ".join(chain + (name,)))
    if len(chain) >= MAX_CHAIN_DEPTH:
        raise StatesError(f'use chain deeper than {MAX_CHAIN_DEPTH} at "{name}"')
    if name not in states:
        raise StatesError(f'state "{name}" is not defined')
    resolved: list[dict[str, Any]] = []
    for step in side_steps(states[name], side):
        if isinstance(step, dict) and isinstance(step.get("use"), str):
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
    for name, definition in states.items():
        declared_sides = ("prototype",) if isinstance(definition, list) else SIDES
        for side in declared_sides:
            try:
                resolved = resolve_state(states, name, side)
            except StatesError as error:
                if "cycle" in str(error) or "chain deeper than" in str(error):
                    problems.append(f'state "{name}": {error}')
                continue
            if len(resolved) > LENGTH_WARNING:
                warnings.append(f'state "{name}": {side} resolves to {len(resolved)} steps; split it or shorten it')
    return problems, warnings


def strip_readiness(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = 0
    while start < len(steps) and set(steps[start]) <= {"waitFor", "wait"} and start < 2:
        start += 1
    end = len(steps)
    while end > start and "wait" in steps[end - 1]:
        end -= 1
    return steps[start:end]


def recipe_name(file: Path) -> tuple[str | None, str]:
    stem = file.stem
    for side, prefix in (("prototype", "proto-"), ("real", "real-")):
        if stem.startswith(prefix):
            return side, stem[len(prefix):]
    return None, stem


def read_recipes(folder: Path) -> dict[str, Any]:
    states: dict[str, Any] = {}
    sources: dict[str, list[str]] = {}
    stems: dict[str, str] = {}
    for file in sorted(folder.glob("*.json")):
        side, name = recipe_name(file)
        steps = strip_readiness(json.loads(file.read_text(encoding="utf-8")))
        sources.setdefault(name, []).append(file.name)
        stems[file.stem] = name
        if side is None:
            states[name] = steps
        else:
            entry = states.setdefault(name, {"prototype": [], "real": []})
            if isinstance(entry, list):
                entry = {"prototype": entry, "real": entry}
                states[name] = entry
            entry[side] = steps
    return {"states": states, "sources": sources, "stems": stems}


def shared_prefix(a: list[Any], b: list[Any]) -> int:
    count = 0
    for x, y in zip(a, b):
        if x != y:
            break
        count += 1
    return count


def extract_fragments(states: dict[str, Any]) -> list[str]:
    report: list[str] = []
    lists = {name: steps for name, steps in states.items() if isinstance(steps, list)}
    names = sorted(lists, key=lambda n: (-len(lists[n]), n))
    for index, longer in enumerate(names):
        for shorter in names[index + 1:]:
            if not isinstance(states[longer], list) or not isinstance(states[shorter], list):
                continue
            length = shared_prefix(states[longer], states[shorter])
            if length < MIN_SHARED_PREFIX or any("use" in step for step in states[longer][:length]):
                continue
            fragment = f"{longer}-{length}"
            states[fragment] = list(states[longer][:length])
            for name in (longer, shorter):
                states[name] = [{"use": fragment}] + states[name][length:]
            report.append(f"fragment {fragment}: {length} shared steps from {longer} and {shorter}")
    return report


def rewrite_map_references(map_path: Path, stems: dict[str, str]) -> int:
    text = map_path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        stem = match.group(1)
        return f"({stems.get(stem, stem)})"

    rewritten, count = REFERENCE_PATTERN.subn(replace, text)
    map_path.write_text(rewritten, encoding="utf-8")
    return count


def migrate_actions(map_path: Path) -> list[str]:
    folder = map_path.parent / ACTIONS_DIR
    target = map_path.parent / STATES_FILE
    if not folder.is_dir():
        raise StatesError(f"{folder}: no {ACTIONS_DIR} folder to migrate")
    if target.exists():
        raise StatesError(f"{target} already exists; remove it to migrate again")
    read = read_recipes(folder)
    states = read["states"]
    report = [f"state {name}: {' + '.join(files)}" for name, files in sorted(read["sources"].items())]
    report.extend(extract_fragments(states))
    target.write_text(json.dumps(states, indent=2) + "\n", encoding="utf-8")
    report.append(f"wrote {target} with {len(states)} entries")
    report.append(f"rewrote {rewrite_map_references(map_path, read['stems'])} references in {map_path}")
    report.append(f"{folder} left in place; delete it after check passes")
    return report
    return problems, warnings
