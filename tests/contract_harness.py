"""Generic TOML-backed deterministic contract checks."""

from __future__ import annotations

import re
import ast
from pathlib import Path
from typing import Any

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover - Python <3.11 fallback is not expected here.
    tomllib = None  # type: ignore[assignment]


REPO_ROOT = Path(__file__).resolve().parent.parent


def run_contract_suite(path: Path) -> None:
    payload = load_contract_payload(path)
    assertions = payload.get("assertion", [])
    if not isinstance(assertions, list):
        raise ValueError(f"{path}: expected [[assertion]] tables")

    for assertion in assertions:
        if not isinstance(assertion, dict):
            raise ValueError(f"{path}: assertion entries must be tables")
        run_assertion(path, assertion)


def load_contract_payload(path: Path) -> dict[str, Any]:
    return load_toml_payload(path)


def load_toml_payload(path: Path) -> dict[str, Any]:
    if tomllib is not None:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    return load_toml_payload_with_fallback(path)


def load_toml_payload_with_fallback(path: Path) -> dict[str, Any]:
    suite: dict[str, Any] = {}
    assertions: list[dict[str, Any]] = []
    scenarios: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_scenario: dict[str, Any] | None = None
    array_key: str | None = None
    array_target: dict[str, Any] | None = None
    array_lines: list[str] = []
    multiline_key: str | None = None
    multiline_target: dict[str, Any] | None = None
    multiline_lines: list[str] = []

    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if multiline_key is not None:
            if line.endswith('"""'):
                multiline_lines.append(raw_line[: raw_line.rfind('"""')])
                assert multiline_target is not None
                multiline_target[multiline_key] = "\n".join(multiline_lines).strip()
                multiline_key = None
                multiline_target = None
                multiline_lines = []
            else:
                multiline_lines.append(raw_line)
            continue

        if array_key is not None:
            array_lines.append(line)
            if line == "]":
                assert array_target is not None
                array_target[array_key] = parse_contract_scalar(
                    path,
                    line_number,
                    " ".join(array_lines),
                )
                array_key = None
                array_target = None
                array_lines = []
            continue

        if line == "[suite]":
            current = suite
            continue

        if line == "[[assertion]]":
            current = {}
            assertions.append(current)
            continue

        if line == "[[scenario]]":
            current_scenario = {}
            scenarios.append(current_scenario)
            current = current_scenario
            continue

        if line == "[[scenario.criteria]]":
            if current_scenario is None:
                raise ValueError(f"{path}:{line_number}: criteria without scenario")
            criteria = current_scenario.setdefault("criteria", [])
            if not isinstance(criteria, list):
                raise ValueError(f"{path}:{line_number}: criteria must be a list")
            current = {}
            criteria.append(current)
            continue

        if current is None:
            raise ValueError(
                f"{path}:{line_number}: expected [suite], [[assertion]], or [[scenario]] before field"
            )
        if "=" not in line:
            raise ValueError(f"{path}:{line_number}: expected key = value")

        key, raw_value = [part.strip() for part in line.split("=", 1)]
        if raw_value.startswith('"""'):
            content = raw_value[3:]
            if content.endswith('"""'):
                current[key] = content[:-3].strip()
            else:
                multiline_key = key
                multiline_target = current
                multiline_lines = [content] if content else []
            continue
        if raw_value == "[":
            array_key = key
            array_target = current
            array_lines = ["["]
            continue
        current[key] = parse_contract_scalar(path, line_number, raw_value)

    if array_key is not None:
        raise ValueError(f"{path}: unterminated array for {array_key!r}")
    if multiline_key is not None:
        raise ValueError(f"{path}: unterminated multiline string for {multiline_key!r}")

    return {"suite": suite, "assertion": assertions, "scenario": scenarios}


def parse_contract_scalar(path: Path, line_number: int, raw_value: str) -> Any:
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    try:
        return ast.literal_eval(raw_value)
    except (SyntaxError, ValueError) as error:
        raise ValueError(f"{path}:{line_number}: unsupported value {raw_value!r}") from error


def run_assertion(suite_path: Path, assertion: dict[str, Any]) -> None:
    assertion_type = require_string(suite_path, assertion, "type")
    if assertion_type == "exists":
        assert_exists(resolve_path(render_path(assertion, "path", {})))
    elif assertion_type == "line_count_at_most":
        assert_line_count_at_most(
            suite_path,
            resolve_path(render_path(assertion, "path", {})),
            require_int(suite_path, assertion, "max"),
        )
    elif assertion_type == "exists_for_each":
        for variables in iterate_variables(suite_path, assertion):
            assert_exists(resolve_path(render_path(assertion, "path", variables)))
    elif assertion_type == "line_count_at_most_for_each":
        for variables in iterate_variables(suite_path, assertion):
            assert_line_count_at_most(
                suite_path,
                resolve_path(render_path(assertion, "path", variables)),
                require_int(suite_path, assertion, "max"),
            )
    elif assertion_type == "toml_suite_require_fields":
        assert_toml_suite_require_fields(
            suite_path,
            resolve_path(render_path(assertion, "path", {})),
            require_string_list(suite_path, assertion, "fields"),
            bool(assertion.get("non_empty", True)),
        )
    elif assertion_type == "toml_suite_require_fields_for_each":
        for variables in iterate_variables(suite_path, assertion):
            assert_toml_suite_require_fields(
                suite_path,
                resolve_path(render_path(assertion, "path", variables)),
                require_string_list(suite_path, assertion, "fields"),
                bool(assertion.get("non_empty", True)),
            )
    elif assertion_type == "toml_scenarios_require_field":
        assert_toml_scenarios_require_field(
            suite_path,
            resolve_path(render_path(assertion, "path", {})),
            require_string(suite_path, assertion, "field"),
            bool(assertion.get("non_empty", True)),
        )
    elif assertion_type == "toml_scenarios_require_field_for_each":
        for variables in iterate_variables(suite_path, assertion):
            assert_toml_scenarios_require_field(
                suite_path,
                resolve_path(render_path(assertion, "path", variables)),
                require_string(suite_path, assertion, "field"),
                bool(assertion.get("non_empty", True)),
            )
    elif assertion_type == "toml_scenario_criteria_require_field":
        assert_toml_scenario_criteria_require_field(
            suite_path,
            resolve_path(render_path(assertion, "path", {})),
            require_string(suite_path, assertion, "field"),
            bool(assertion.get("non_empty", True)),
        )
    elif assertion_type == "toml_scenario_criteria_require_field_for_each":
        for variables in iterate_variables(suite_path, assertion):
            assert_toml_scenario_criteria_require_field(
                suite_path,
                resolve_path(render_path(assertion, "path", variables)),
                require_string(suite_path, assertion, "field"),
                bool(assertion.get("non_empty", True)),
            )
    else:
        raise ValueError(f"{suite_path}: unknown contract assertion type {assertion_type!r}")


def iterate_variables(suite_path: Path, assertion: dict[str, Any]) -> list[dict[str, str]]:
    pattern = require_string(suite_path, assertion, "glob")
    matches = sorted(REPO_ROOT.glob(pattern))
    if not matches:
        raise AssertionError(f"{suite_path}: glob matched no files: {pattern}")
    return [variables_for_path(path) for path in matches]


def variables_for_path(path: Path) -> dict[str, str]:
    relpath = path.relative_to(REPO_ROOT)
    parent = relpath.parent
    variables = {
        "path": str(relpath),
        "relpath": str(relpath),
        "stem": path.stem,
        "name": path.name,
        "parent": str(parent),
        "parent_relpath": str(parent),
        "parent_name": path.parent.name,
    }
    if path.name == "SKILL.md":
        variables["frontmatter_name"] = frontmatter_name(path)
    return variables


def render_path(assertion: dict[str, Any], key: str, variables: dict[str, str]) -> str:
    return render_template(str(assertion.get(key, "")), variables)


def render_template(template: str, variables: dict[str, str]) -> str:
    try:
        return template.format(**variables)
    except KeyError as error:
        raise ValueError(f"unknown contract template variable: {error.args[0]}") from error


def resolve_path(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def assert_exists(path: Path) -> None:
    if not path.exists():
        raise AssertionError(f"expected file to exist: {path.relative_to(REPO_ROOT)}")


def assert_line_count_at_most(suite_path: Path, path: Path, max_lines: int) -> None:
    line_count = len(read_text(path).splitlines())
    if line_count > max_lines:
        raise AssertionError(
            f"{suite_path}: {path.relative_to(REPO_ROOT)} has {line_count} lines, "
            f"expected at most {max_lines}"
        )


def assert_toml_suite_require_fields(
    suite_path: Path,
    path: Path,
    fields: list[str],
    non_empty: bool,
) -> None:
    payload = load_toml_payload(path)
    suite = payload.get("suite")
    if not isinstance(suite, dict):
        raise AssertionError(f"{path.relative_to(REPO_ROOT)} must define a [suite] table")

    for field in fields:
        value = suite.get(field)
        if field not in suite:
            raise AssertionError(
                f"{suite_path}: {path.relative_to(REPO_ROOT)} suite missing {field!r}"
            )
        if non_empty and is_empty_value(value):
            raise AssertionError(
                f"{suite_path}: {path.relative_to(REPO_ROOT)} suite must set {field!r}"
            )


def assert_toml_scenarios_require_field(
    suite_path: Path,
    path: Path,
    field: str,
    non_empty: bool,
) -> None:
    payload = load_toml_payload(path)
    scenarios = payload.get("scenario", [])
    if not isinstance(scenarios, list):
        raise AssertionError(f"{path.relative_to(REPO_ROOT)} must define [[scenario]] tables")

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise AssertionError(f"{path.relative_to(REPO_ROOT)} scenario must be a table")
        scenario_id = str(scenario.get("id", "<missing-id>"))
        value = scenario.get(field)
        if field not in scenario:
            raise AssertionError(
                f"{suite_path}: {path.relative_to(REPO_ROOT)}:{scenario_id} missing {field!r}"
            )
        if non_empty and is_empty_value(value):
            raise AssertionError(
                f"{suite_path}: {path.relative_to(REPO_ROOT)}:{scenario_id} must set {field!r}"
            )


def assert_toml_scenario_criteria_require_field(
    suite_path: Path,
    path: Path,
    field: str,
    non_empty: bool,
) -> None:
    payload = load_toml_payload(path)
    scenarios = payload.get("scenario", [])
    if not isinstance(scenarios, list):
        raise AssertionError(f"{path.relative_to(REPO_ROOT)} must define [[scenario]] tables")

    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise AssertionError(f"{path.relative_to(REPO_ROOT)} scenario must be a table")
        scenario_id = str(scenario.get("id", "<missing-id>"))
        criteria = scenario.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise AssertionError(
                f"{suite_path}: {path.relative_to(REPO_ROOT)}:{scenario_id} "
                "must define [[scenario.criteria]] tables"
            )
        for index, criterion in enumerate(criteria, start=1):
            if not isinstance(criterion, dict):
                raise AssertionError(
                    f"{suite_path}: {path.relative_to(REPO_ROOT)}:{scenario_id} "
                    f"criterion {index} must be a table"
                )
            value = criterion.get(field)
            if field not in criterion:
                raise AssertionError(
                    f"{suite_path}: {path.relative_to(REPO_ROOT)}:{scenario_id} "
                    f"criterion {index} missing {field!r}"
                )
            if non_empty and is_empty_value(value):
                raise AssertionError(
                    f"{suite_path}: {path.relative_to(REPO_ROOT)}:{scenario_id} "
                    f"criterion {index} must set {field!r}"
                )


def is_empty_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict, tuple, set)):
        return not value
    return False


def read_text(path: Path) -> str:
    if not path.exists():
        raise AssertionError(f"missing file: {path.relative_to(REPO_ROOT)}")
    return path.read_text(encoding="utf-8")


def frontmatter_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(?P<body>.*?)\n---\n", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path.relative_to(REPO_ROOT)} is missing YAML frontmatter")

    for raw_line in match.group("body").splitlines():
        if raw_line.startswith("name:"):
            return raw_line.split(":", 1)[1].strip().strip('"')
    raise ValueError(f"{path.relative_to(REPO_ROOT)} is missing name frontmatter")


def require_string(path: Path, payload: dict[str, Any], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: missing non-empty string field {key!r}")
    return value.strip()


def require_string_list(path: Path, payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{path}: field {key!r} must be a string list")
    return value


def require_int(path: Path, payload: dict[str, Any], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{path}: field {key!r} must be an integer")
    return value
