"""Shared runner for workflow-dispatch behavioral pressure tests."""

from __future__ import annotations

import ast
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:
    tomllib = None  # type: ignore[assignment]


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
TESTS_DIR = REPO_ROOT / "tests"
sys.path.append(str(TESTS_DIR))
sys.path.append(str(SCRIPT_DIR))

from auto_discovery import action_lines, assert_auto_discovers  # noqa: E402
from behavioral_harness import (  # noqa: E402
    AGENT_COMMAND_ENV_VAR,
    BehavioralScenario,
    CAPABILITY_ACCOUNTING_INSTRUCTIONS,
    check_semantic_response,
    run_agent,
    select_scenarios,
)
from semantic_judge import SemanticCriterion, resolve_judge_command  # noqa: E402


ResponseCheck = Callable[[str], None]


@dataclass(frozen=True)
class WorkflowDispatchScenario(BehavioralScenario):
    prompt_instructions: str = ""
    expected_auto_discovery: tuple[str, ...] = ()
    require_action_ledger: bool = False
    first_action_contains: tuple[str, ...] = ()
    required_action_contains: tuple[tuple[str, ...], ...] = ()
    response_checks: tuple[ResponseCheck, ...] = ()


@dataclass(frozen=True)
class WorkflowDispatchSuiteConfig:
    suite_name: str
    parent_skill_name: str
    skill_path: Path
    scenario_filter_env_var: str


def run_workflow_dispatch_suite(
    *,
    suite_name: str,
    parent_skill_name: str,
    skill_path: Path,
    scenarios: tuple[WorkflowDispatchScenario, ...],
    scenario_filter_env_var: str,
) -> int:
    if "--help" in sys.argv:
        print_usage(scenario_filter_env_var, sys.argv[0])
        return 0

    agent_command = os.environ.get(AGENT_COMMAND_ENV_VAR, "").strip()
    if not agent_command:
        print_usage(scenario_filter_env_var, sys.argv[0])
        print(f"FAIL: {AGENT_COMMAND_ENV_VAR} is required", file=sys.stderr)
        return 1

    try:
        selected = select_scenarios(
            scenarios,
            os.environ.get(scenario_filter_env_var, "").strip(),
        )
        skill_text = skill_path.read_text(encoding="utf-8")
        judge_command = resolve_judge_command(agent_command)
        for scenario in selected:
            response = run_agent(
                agent_command,
                build_workflow_prompt(
                    parent_skill_name=parent_skill_name,
                    skill_text=skill_text,
                    scenario=scenario,
                ),
            )
            check_workflow_response(
                response=response,
                scenario=scenario,
                agent_command=agent_command,
                judge_command=judge_command,
                parent_skill_name=parent_skill_name,
            )
            print(f"PASS: {scenario.scenario_id}")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: {len(selected)} {suite_name}")
    return 0


def run_workflow_dispatch_suite_from_path(
    scenarios_path: Path,
    *,
    response_checks: dict[str, ResponseCheck] | None = None,
) -> int:
    config = load_workflow_suite_config(scenarios_path)
    return run_workflow_dispatch_suite(
        suite_name=config.suite_name,
        parent_skill_name=config.parent_skill_name,
        skill_path=config.skill_path,
        scenarios=load_workflow_scenarios(
            scenarios_path,
            response_checks=response_checks,
        ),
        scenario_filter_env_var=config.scenario_filter_env_var,
    )


def load_workflow_suite_config(scenarios_path: Path) -> WorkflowDispatchSuiteConfig:
    payload = load_workflow_scenario_payload(scenarios_path)
    suite = payload.get("suite")
    if suite is not None and not isinstance(suite, dict):
        raise ValueError(f"{scenarios_path} [suite] must be a table")
    suite_payload = suite if isinstance(suite, dict) else {}

    inferred_skill_path = infer_colocated_skill_path(scenarios_path)
    skill_path_value = str(suite_payload.get("skill_path", "")).strip()
    if skill_path_value:
        skill_path = Path(skill_path_value)
    elif inferred_skill_path is not None:
        skill_path = inferred_skill_path
    else:
        parent_name = scenarios_path.parent.name
        skill_path = REPO_ROOT / "skills" / parent_name / "SKILL.md"

    if not skill_path.is_absolute():
        skill_path = REPO_ROOT / skill_path

    parent_skill_name = optional_string(suite_payload, "skill") or frontmatter_name(skill_path)
    return WorkflowDispatchSuiteConfig(
        suite_name=optional_string(suite_payload, "name")
        or f"{parent_skill_name} workflow dispatch scenarios",
        parent_skill_name=parent_skill_name,
        skill_path=skill_path,
        scenario_filter_env_var=optional_string(suite_payload, "scenario_env")
        or f"{parent_skill_name.upper().replace('-', '_')}_WORKFLOW_DISPATCH_SCENARIO",
    )


def load_workflow_scenarios(
    scenarios_path: Path,
    *,
    response_checks: dict[str, ResponseCheck] | None = None,
) -> tuple[WorkflowDispatchScenario, ...]:
    checks_by_name = {**builtin_response_checks(), **(response_checks or {})}
    payload = load_workflow_scenario_payload(scenarios_path)

    scenarios = payload.get("scenario", [])
    if not isinstance(scenarios, list):
        raise ValueError(f"{scenarios_path} must define [[scenario]] tables")

    return tuple(
        build_workflow_scenario(scenarios_path, raw_scenario, checks_by_name)
        for raw_scenario in scenarios
    )


def load_workflow_scenario_payload(scenarios_path: Path) -> dict[str, object]:
    if tomllib is not None:
        with scenarios_path.open("rb") as handle:
            return tomllib.load(handle)
    return load_workflow_scenario_payload_with_fallback(scenarios_path)


def load_workflow_scenario_payload_with_fallback(scenarios_path: Path) -> dict[str, object]:
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

        current[key] = parse_workflow_toml_scalar(scenarios_path, line_number, raw_value)

    if multiline_key is not None:
        raise ValueError(f"{scenarios_path}: unterminated multiline string for {multiline_key!r}")

    return {"suite": suite, "scenario": scenarios}


def parse_workflow_toml_scalar(path: Path, line_number: int, raw_value: str) -> object:
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    try:
        return ast.literal_eval(raw_value)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"{path}:{line_number}: unsupported value {raw_value!r}") from error


def build_workflow_scenario(
    scenarios_path: Path,
    raw_scenario: dict[str, object],
    checks_by_name: dict[str, ResponseCheck],
) -> WorkflowDispatchScenario:
    scenario_id = require_string(scenarios_path, raw_scenario, "id")
    check_names = tuple(require_string_list(scenarios_path, raw_scenario, "response_checks"))
    unknown_checks = [name for name in check_names if name not in checks_by_name]
    if unknown_checks:
        raise ValueError(
            f"{scenarios_path}: {scenario_id} has unknown response checks: {unknown_checks}"
        )

    criteria = raw_scenario.get("criteria", [])
    if not isinstance(criteria, list):
        raise ValueError(f"{scenarios_path}: {scenario_id} criteria must be a list")

    return WorkflowDispatchScenario(
        scenario_id=scenario_id,
        user_request=require_string(scenarios_path, raw_scenario, "user_request"),
        prompt_instructions=require_string(scenarios_path, raw_scenario, "prompt_instructions"),
        criteria=tuple(
            build_semantic_criterion(scenarios_path, scenario_id, criterion)
            for criterion in criteria
        ),
        forbidden_terms=tuple(require_string_list(scenarios_path, raw_scenario, "forbidden_terms")),
        expected_auto_discovery=tuple(
            require_string_list(scenarios_path, raw_scenario, "expected_auto_discovery")
        ),
        require_action_ledger=bool(raw_scenario.get("require_action_ledger", False)),
        first_action_contains=tuple(
            require_string_list(scenarios_path, raw_scenario, "first_action_contains")
        ),
        required_action_contains=tuple(
            tuple(group) for group in require_nested_string_list(
                scenarios_path,
                raw_scenario,
                "required_action_contains",
            )
        ),
        response_checks=tuple(checks_by_name[name] for name in check_names),
    )


def build_semantic_criterion(path: Path, scenario_id: str, raw_criterion: object) -> SemanticCriterion:
    if not isinstance(raw_criterion, dict):
        raise ValueError(f"{path}: {scenario_id} criteria entries must be tables")
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


def require_nested_string_list(path: Path, payload: dict[str, object], key: str) -> list[list[str]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{path}: field {key!r} must be a list of string lists")
    for item in value:
        if not isinstance(item, list) or not all(isinstance(term, str) for term in item):
            raise ValueError(f"{path}: field {key!r} must be a list of string lists")
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


def builtin_response_checks() -> dict[str, ResponseCheck]:
    return {
        "no_dispatch_request": assert_no_dispatch_request,
        "scoping_before_local_mapping": assert_scoping_before_local_mapping,
        "ticket_coordinator_handoff": assert_ticket_coordinator_handoff,
    }


def assert_no_dispatch_request(response: str) -> None:
    for line in response.splitlines():
        normalized = line.casefold()
        if normalized.lstrip().startswith("action:") and "dispatch_request" in normalized:
            raise AssertionError("execution-phase handoff must use PHASE_CONTRACT, not DISPATCH_REQUEST")


def assert_scoping_before_local_mapping(response: str) -> None:
    scoping_index = first_index(response, "dispatch_request", "scoping")
    if scoping_index < 0:
        scoping_index = first_index(response, "dispatch_request", "scope")
    if scoping_index < 0:
        raise AssertionError("Scoping dispatch request action is required")

    prefix = response[:scoping_index].lower()
    local_scoping_markers = (
        "local scope map",
        "local scoping",
        "map the code",
        "map code",
        "codebase map",
        "scope map",
        "affected surfaces",
    )
    if any(marker in prefix for marker in local_scoping_markers):
        raise AssertionError("performed local scoping before Scoping dispatch")


def assert_ticket_coordinator_handoff(response: str) -> None:
    dispatch_lines = []
    for line in action_lines(response):
        normalized = line.casefold()
        if "dispatch_request" in normalized:
            dispatch_lines.append(normalized)

    if not dispatch_lines:
        raise AssertionError("ticket coordinator dispatch request is required")

    first_dispatch = dispatch_lines[0]
    missing = [
        term
        for term in ("ticket coordinator", "approved execution packet")
        if term not in first_dispatch
    ]
    if missing:
        raise AssertionError(f"ticket coordinator handoff missing terms: {missing}")

    deeper_terms = ("implementation", "review", "qa")
    if not all(term in first_dispatch for term in deeper_terms):
        raise AssertionError(
            "ticket coordinator handoff must mention deeper implementation, review, and QA coordination"
        )


def first_index(haystack: str, *needles: str) -> int:
    normalized_needles = tuple(needle.lower() for needle in needles)
    for line in haystack.splitlines():
        normalized_line = line.lower()
        if all(needle in normalized_line for needle in normalized_needles):
            return haystack.find(line)
    return -1


def build_workflow_prompt(
    *,
    parent_skill_name: str,
    skill_text: str,
    scenario: WorkflowDispatchScenario,
) -> str:
    return f"""You are testing workflow compliance for a loaded skill.

Loaded skill: {parent_skill_name}

<skill>
{skill_text}
</skill>

User request:
{scenario.user_request}

{CAPABILITY_ACCOUNTING_INSTRUCTIONS}

{scenario.prompt_instructions}
"""


def check_workflow_response(
    *,
    response: str,
    scenario: WorkflowDispatchScenario,
    agent_command: str,
    judge_command: str,
    parent_skill_name: str,
) -> None:
    try:
        if scenario.require_action_ledger:
            require_action_lines(
                response,
                first_action_contains=scenario.first_action_contains,
                required_action_contains=scenario.required_action_contains,
            )
        for check in scenario.response_checks:
            check(response)
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise
    check_semantic_response(
        scenario=scenario,
        response=response,
        judge_command=judge_command,
        judge_context=(
            f"Loaded parent skill under test: {parent_skill_name}. "
            "Judge workflow dispatch behavior, not exact wording."
        ),
    )
    try:
        for expected_skill in scenario.expected_auto_discovery:
            assert_auto_discovers(
                agent_command,
                auto_discovery_request_text(response),
                expected_skill,
            )
    except AssertionError:
        print(f"Response for {scenario.scenario_id}:\n{response}", file=sys.stderr)
        raise


def auto_discovery_request_text(response: str) -> str:
    dispatch_lines = [
        line for line in action_lines(response)
        if "dispatch_request" in line.casefold()
    ]
    if dispatch_lines:
        return "\n".join(dispatch_lines)

    lines = action_lines(response)
    if not lines:
        raise AssertionError("missing ACTION line for auto-discovery")
    return "\n".join(lines)


def require_action_lines(
    response: str,
    *,
    first_action_contains: tuple[str, ...] = (),
    required_action_contains: tuple[tuple[str, ...], ...] = (),
) -> list[str]:
    lines = action_lines(response)
    if not lines:
        raise AssertionError("missing ACTION lines")

    if first_action_contains:
        first_action = lines[0].casefold()
        missing = [term for term in first_action_contains if term.casefold() not in first_action]
        if missing:
            raise AssertionError(f"first action missing terms: {missing}")

    for required_terms in required_action_contains:
        if not any(all(term.casefold() in line.casefold() for term in required_terms) for line in lines):
            raise AssertionError(f"missing ACTION line containing terms: {required_terms}")

    return lines


def print_usage(scenario_filter_env_var: str, script_path: str) -> None:
    print(
        f"""Usage:
  {AGENT_COMMAND_ENV_VAR}='<command reading stdin>' python3 {script_path}

Optional:
  {scenario_filter_env_var}='<scenario-id>' to run one scenario.
"""
    )
