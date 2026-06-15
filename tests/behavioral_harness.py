"""Shared runner for loaded-skill behavioral pressure tests."""

from __future__ import annotations

import os
import sys
import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback is not expected here.
    tomllib = None  # type: ignore[assignment]

from semantic_judge import (  # noqa: E402
    SemanticCriterion,
    assert_forbidden_terms,
    judge_response,
    resolve_judge_command,
    run_command,
)


REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BehavioralScenario:
    scenario_id: str
    user_request: str
    criteria: tuple[SemanticCriterion, ...]
    forbidden_terms: tuple[str, ...] = ()


@dataclass(frozen=True)
class BehavioralSuiteConfig:
    suite_name: str
    skill_name: str
    skill_path: Path
    scenario_filter_env_var: str
    prompt_instructions: str
    judge_context: str


PromptBuilder = Callable[[str, BehavioralScenario], str]
AGENT_COMMAND_ENV_VAR = "SKILL_TRIGGER_AGENT_COMMAND"
GLOBAL_SCENARIO_FILTER_ENV_VAR = "BEHAVIORAL_SCENARIO"
CAPABILITY_ACCOUNTING_INSTRUCTIONS = (
    "Before choosing a path, account for native runtime capabilities from the scenario facts. "
    "If a scenario says a native capability is available, treat it as available. "
    "If a scenario says a capability is missing, unavailable, or policy-blocked, "
    "report that blocker before substituting another path. "
    "Do not ask for separate permission solely to use an available capability unless "
    "the scenario states that the runtime policy requires it."
)


def load_behavioral_scenarios(scenarios_path: Path) -> tuple[BehavioralScenario, ...]:
    payload = load_behavioral_scenario_payload(scenarios_path)

    scenarios = payload.get("scenario", [])
    if not isinstance(scenarios, list):
        raise ValueError(f"{scenarios_path} must define [[scenario]] tables")

    return tuple(build_behavioral_scenario(scenarios_path, raw_scenario) for raw_scenario in scenarios)


def load_behavioral_suite_config(scenarios_path: Path) -> BehavioralSuiteConfig:
    payload = load_behavioral_scenario_payload(scenarios_path)
    suite = payload.get("suite")
    if not isinstance(suite, dict):
        raise ValueError(f"{scenarios_path} must define a [suite] table")

    inferred_skill_path = infer_colocated_skill_path(scenarios_path)
    skill_path_value = str(suite.get("skill_path", "")).strip()
    if skill_path_value:
        skill_path = Path(skill_path_value)
    elif inferred_skill_path is not None:
        skill_path = inferred_skill_path
    else:
        skill_name_for_default = require_string(scenarios_path, suite, "skill")
        skill_path = Path(f"skills/{skill_name_for_default}/SKILL.md")
    if not skill_path.is_absolute():
        skill_path = REPO_ROOT / skill_path
    skill_name = optional_string(suite, "skill") or frontmatter_name(skill_path)

    return BehavioralSuiteConfig(
        suite_name=optional_string(suite, "name") or skill_name,
        skill_name=skill_name,
        skill_path=skill_path,
        scenario_filter_env_var=optional_string(suite, "scenario_env") or default_scenario_env(skill_name),
        prompt_instructions=require_string(scenarios_path, suite, "prompt_instructions"),
        judge_context=require_string(scenarios_path, suite, "judge_context"),
    )


def run_behavioral_suite_from_path(
    scenarios_path: Path,
    *,
    scenario_filter: str | None = None,
) -> int:
    config = load_behavioral_suite_config(scenarios_path)
    return run_loaded_skill_behavioral_suite(
        suite_name=config.suite_name,
        skill_name=config.skill_name,
        skill_path=config.skill_path,
        scenarios=load_behavioral_scenarios(scenarios_path),
        scenario_filter_env_var=config.scenario_filter_env_var,
        prompt_instructions=config.prompt_instructions,
        judge_context=config.judge_context,
        scenario_filter=scenario_filter,
    )


def load_behavioral_scenario_payload(scenarios_path: Path) -> dict[str, object]:
    if tomllib is not None:
        with scenarios_path.open("rb") as handle:
            return tomllib.load(handle)
    return load_behavioral_scenario_payload_with_fallback(scenarios_path)


def load_behavioral_scenario_payload_with_fallback(scenarios_path: Path) -> dict[str, object]:
    suite: dict[str, object] = {}
    scenarios: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_scenario: dict[str, object] | None = None
    multiline_key: str | None = None
    multiline_target: dict[str, object] | None = None
    multiline_value: list[str] = []

    for line_number, raw_line in enumerate(
        scenarios_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if multiline_key is not None:
            if line.endswith('"""'):
                multiline_value.append(raw_line[: raw_line.rfind('"""')])
                assert multiline_target is not None
                multiline_target[multiline_key] = "\n".join(multiline_value).strip()
                multiline_key = None
                multiline_target = None
                multiline_value = []
            else:
                multiline_value.append(raw_line)
            continue

        if line == "[suite]":
            current = suite
            continue

        if line == "[[scenario]]":
            current_scenario = {}
            scenarios.append(current_scenario)
            current = current_scenario
            continue

        if line == "[[scenario.criteria]]":
            if current_scenario is None:
                raise ValueError(f"{scenarios_path}:{line_number}: criteria without scenario")
            criteria = current_scenario.setdefault("criteria", [])
            if not isinstance(criteria, list):
                raise ValueError(f"{scenarios_path}:{line_number}: criteria must be a list")
            criterion: dict[str, object] = {}
            criteria.append(criterion)
            current = criterion
            continue

        if current is None:
            raise ValueError(f"{scenarios_path}:{line_number}: expected [[scenario]] before field")

        if "=" not in line:
            raise ValueError(f"{scenarios_path}:{line_number}: expected key = value")

        key, raw_value = [part.strip() for part in line.split("=", 1)]
        if raw_value.startswith('"""'):
            content = raw_value[3:]
            if content.endswith('"""'):
                current[key] = content[:-3].strip()
            else:
                multiline_key = key
                multiline_target = current
                multiline_value = [content] if content else []
            continue

        current[key] = parse_behavioral_toml_scalar(scenarios_path, line_number, raw_value)

    if multiline_key is not None:
        raise ValueError(f"{scenarios_path}: unterminated multiline string for {multiline_key!r}")

    return {"suite": suite, "scenario": scenarios}


def parse_behavioral_toml_scalar(path: Path, line_number: int, raw_value: str) -> object:
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    try:
        return ast.literal_eval(raw_value)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"{path}:{line_number}: unsupported value {raw_value!r}") from error


def build_behavioral_scenario(path: Path, raw_scenario: object) -> BehavioralScenario:
    if not isinstance(raw_scenario, dict):
        raise ValueError(f"{path}: scenario entries must be tables")

    criteria = raw_scenario.get("criteria", [])
    if not isinstance(criteria, list):
        raise ValueError(f"{path}: scenario criteria must be a list")

    return BehavioralScenario(
        scenario_id=require_string(path, raw_scenario, "id"),
        user_request=require_string(path, raw_scenario, "user_request"),
        criteria=tuple(build_semantic_criterion(path, criterion) for criterion in criteria),
        forbidden_terms=tuple(require_string_list(path, raw_scenario, "forbidden_terms")),
    )


def build_semantic_criterion(path: Path, raw_criterion: object) -> SemanticCriterion:
    if not isinstance(raw_criterion, dict):
        raise ValueError(f"{path}: criteria entries must be tables")
    return SemanticCriterion(
        key=require_string(path, raw_criterion, "key"),
        description=require_string(path, raw_criterion, "description"),
    )


def require_string(path: Path, payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: missing non-empty string field {key!r}")
    return value.strip()


def optional_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if isinstance(value, str):
        return value.strip()
    return ""


def require_string_list(path: Path, payload: dict[str, object], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{path}: field {key!r} must be a string list")
    return value


def infer_colocated_skill_path(scenarios_path: Path) -> Path | None:
    if scenarios_path.parent.name != "tests":
        return None

    candidate = scenarios_path.parent.parent / "SKILL.md"
    if candidate.exists():
        return candidate
    return None


def frontmatter_name(skill_path: Path) -> str:
    text = skill_path.read_text(encoding="utf-8")
    in_frontmatter = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_frontmatter:
                in_frontmatter = True
                continue
            break
        if in_frontmatter and line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"')
    raise ValueError(f"{skill_path.relative_to(REPO_ROOT)} is missing name frontmatter")


def default_scenario_env(skill_name: str) -> str:
    return f"{skill_name.upper().replace('-', '_')}_SCENARIO"


def run_loaded_skill_behavioral_suite(
    *,
    suite_name: str,
    skill_name: str,
    skill_path: Path,
    scenarios: tuple[BehavioralScenario, ...],
    scenario_filter_env_var: str,
    prompt_instructions: str,
    judge_context: str,
    prompt_builder: PromptBuilder | None = None,
    scenario_filter: str | None = None,
) -> int:
    if "--help" in sys.argv:
        print_usage(scenario_filter_env_var, sys.argv[0])
        return 0

    agent_command = resolve_behavioral_agent_command()
    if not agent_command:
        print_usage(scenario_filter_env_var, sys.argv[0])
        print(
            f"FAIL: {AGENT_COMMAND_ENV_VAR} is required",
            file=sys.stderr,
        )
        return 1

    selected_filter = (
        scenario_filter
        if scenario_filter is not None
        else os.environ.get(scenario_filter_env_var, "").strip()
        or os.environ.get(GLOBAL_SCENARIO_FILTER_ENV_VAR, "").strip()
    )
    try:
        selected = select_scenarios(scenarios, selected_filter)
        skill_text = skill_path.read_text(encoding="utf-8")
        judge_command = resolve_judge_command(agent_command)
        builder = prompt_builder or (
            lambda text, scenario: build_loaded_skill_prompt(
                skill_name=skill_name,
                skill_text=text,
                scenario=scenario,
                prompt_instructions=prompt_instructions,
            )
        )

        for scenario in selected:
            response = run_agent(agent_command, builder(skill_text, scenario))
            check_semantic_response(
                scenario=scenario,
                response=response,
                judge_command=judge_command,
                judge_context=judge_context,
            )
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(selected)} {suite_name} behavioral scenarios")
    return 0


def resolve_behavioral_agent_command() -> str:
    return os.environ.get(AGENT_COMMAND_ENV_VAR, "").strip()


def build_loaded_skill_prompt(
    *,
    skill_name: str,
    skill_text: str,
    scenario: BehavioralScenario,
    prompt_instructions: str,
) -> str:
    return f"""You are pressure-testing whether an agent follows the {skill_name} skill.

Loaded skill: {skill_name}

<skill>
{skill_text}
</skill>

User request:
{scenario.user_request}

{CAPABILITY_ACCOUNTING_INSTRUCTIONS}

{prompt_instructions}
"""


def select_scenarios(
    scenarios: tuple[BehavioralScenario, ...],
    scenario_filter: str,
) -> tuple[BehavioralScenario, ...]:
    if not scenario_filter:
        return scenarios

    selected = tuple(scenario for scenario in scenarios if scenario.scenario_id == scenario_filter)
    if not selected:
        raise ValueError(f"no scenario matched {scenario_filter!r}")
    return selected


def run_agent(agent_command: str, prompt: str) -> str:
    return run_command(agent_command, prompt, "agent")


def check_semantic_response(
    *,
    scenario: BehavioralScenario,
    response: str,
    judge_command: str,
    judge_context: str,
) -> None:
    try:
        assert_forbidden_terms(response, scenario.forbidden_terms, scenario.scenario_id)
        judge_response(
            judge_command=judge_command,
            scenario_id=scenario.scenario_id,
            scenario_prompt=scenario.user_request,
            response=response,
            criteria=scenario.criteria,
            context=judge_context,
        )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


def print_usage(scenario_filter_env_var: str, script_path: str) -> None:
    print(
        f"""Usage:
  {AGENT_COMMAND_ENV_VAR}='<command reading stdin>' python3 {script_path}

Optional:
  {scenario_filter_env_var}='<scenario-id>' to run one scenario.
  {GLOBAL_SCENARIO_FILTER_ENV_VAR}='<scenario-id>' to run one scenario.
"""
    )
