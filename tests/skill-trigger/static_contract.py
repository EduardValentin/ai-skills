#!/usr/bin/env python3
"""Deterministic contract checks for skill trigger scenarios."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from trigger_scenarios import discover_skill_files, load_scenarios


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
SCENARIOS_PATH = SCRIPT_DIR / "scenarios.toml"


def main() -> int:
    try:
        scenarios = load_scenarios(SCENARIOS_PATH)
        check_scenarios(scenarios)
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(scenarios)} skill trigger scenarios satisfy static contracts")
    return 0


def check_scenarios(scenarios: list[dict[str, object]]) -> None:
    if not scenarios:
        raise ValueError(f"no trigger scenarios found in {SCENARIOS_PATH}")

    seen_ids: set[str] = set()
    covered_skills: set[str] = set()
    skill_files = discover_skill_files(REPO_ROOT)

    for scenario in scenarios:
        scenario_id = str(scenario["id"])
        skill = str(scenario["skill"])

        if scenario_id in seen_ids:
            raise ValueError(f"duplicate scenario id: {scenario_id}")
        seen_ids.add(scenario_id)

        skill_file = skill_files.get(skill)
        if skill_file is None:
            raise ValueError(f"{scenario_id} references missing skill: {skill}")

        skill_doc = skill_file.read_text(encoding="utf-8")
        frontmatter = parse_frontmatter(skill_file, skill_doc)
        declared_name = frontmatter.get("name", "")

        if declared_name != skill:
            raise ValueError(
                f"{scenario_id} expected skill name {skill!r} but SKILL.md declares {declared_name!r}"
            )

        if is_manual_invocation(frontmatter):
            raise ValueError(
                f"{scenario_id} references manual-invocation skill {skill}: "
                "procedural skills must not have trigger scenarios"
            )

        covered_skills.add(skill)

    for skill, skill_file in sorted(skill_files.items()):
        frontmatter = parse_frontmatter(skill_file, skill_file.read_text(encoding="utf-8"))
        if is_manual_invocation(frontmatter):
            continue

        if skill not in covered_skills:
            raise ValueError(
                f"skill missing trigger scenario: {skill} ({skill_file.relative_to(REPO_ROOT)})"
            )


def parse_frontmatter(skill_file: Path, skill_doc: str) -> dict[str, str]:
    match = re.match(r"^---\n(?P<body>.*?)\n---\n", skill_doc, re.DOTALL)
    if not match:
        raise ValueError(f"{skill_file} is missing YAML frontmatter")

    values: dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip().strip('"')
    return values


def is_manual_invocation(frontmatter: dict[str, str]) -> bool:
    if frontmatter.get("disable-model-invocation", "").lower() == "true":
        return True
    if frontmatter.get("ai-skills-category", "").lower() == "procedural":
        return True
    return frontmatter.get("ai-skills-invocation", "").lower() == "manual"


if __name__ == "__main__":
    raise SystemExit(main())
