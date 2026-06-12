#!/usr/bin/env python3
"""Contract checks for UIUX plugin behavioral test standardization."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SKILLS_DIR = REPO_ROOT / "plugins" / "uiux" / "skills"
TESTS_DIR = REPO_ROOT / "tests"


def main() -> int:
    try:
        check_uiux_skills_have_repo_level_scenarios()
        check_uiux_skill_dirs_do_not_have_manual_pressure_docs()
        check_plugin_level_manual_evaluations_removed()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: uiux plugin uses TOML-backed behavioral pressure tests")
    return 0


def check_uiux_skills_have_repo_level_scenarios() -> None:
    missing: list[str] = []
    stale: list[str] = []

    for skill_file in sorted(PLUGIN_SKILLS_DIR.glob("*/SKILL.md")):
        skill_name = skill_file.parent.name
        scenarios_path = TESTS_DIR / f"uiux-{skill_name}" / "scenarios.toml"
        if not scenarios_path.exists():
            missing.append(f"{skill_name} ({skill_file.relative_to(REPO_ROOT)})")
            continue

        source = scenarios_path.read_text(encoding="utf-8")
        expected = (
            "[suite]",
            f'skill = "{frontmatter_name(skill_file)}"',
            f'skill_path = "plugins/uiux/skills/{skill_name}/SKILL.md"',
            "agent_env = ",
            "scenario_env = ",
            "prompt_instructions = ",
            "judge_context = ",
            "[[scenario]]",
            "[[scenario.criteria]]",
        )
        missing_terms = [term for term in expected if term not in source]
        if missing_terms:
            stale.append(f"{scenarios_path.relative_to(REPO_ROOT)} missing {missing_terms}")

    if missing:
        raise AssertionError("UIUX skills missing repo-level behavioral scenarios: " + ", ".join(missing))
    if stale:
        raise AssertionError("UIUX behavioral scenario metadata is incomplete: " + ", ".join(stale))


def check_uiux_skill_dirs_do_not_have_manual_pressure_docs() -> None:
    leftovers = [
        path.relative_to(REPO_ROOT)
        for path in sorted(PLUGIN_SKILLS_DIR.glob("*/tests/pressure-scenarios.md"))
    ]
    if leftovers:
        raise AssertionError(
            "UIUX pressure scenarios should live in tests/uiux-*/scenarios.toml: "
            + ", ".join(str(path) for path in leftovers)
        )


def check_plugin_level_manual_evaluations_removed() -> None:
    evaluations = REPO_ROOT / "plugins" / "uiux" / "tests" / "evaluations.md"
    if evaluations.exists():
        raise AssertionError(
            "UIUX plugin evaluations should be represented by repo-level TOML scenarios, not "
            f"{evaluations.relative_to(REPO_ROOT)}"
        )


def frontmatter_name(skill_file: Path) -> str:
    text = skill_file.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"{skill_file.relative_to(REPO_ROOT)} is missing name frontmatter")


if __name__ == "__main__":
    raise SystemExit(main())
