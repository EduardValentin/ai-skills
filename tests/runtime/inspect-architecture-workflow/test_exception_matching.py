import json
from pathlib import Path

import pytest

from support import copy_fixture, run_arch

COMPONENT_ROW = "reports"
COMPONENT_RULE = "R32"
PORT_ROW = "src/catalog/api/search.ts#SuggestionSource"
PORT_UNIT = "src/catalog/api/search.ts"
CYCLE_ROW = "lending -> notify -> storage"


def fixture_root(tmp_path: Path) -> Path:
    return copy_fixture("known-defects", tmp_path / "p")


def model_edit(root: Path, *args: str) -> None:
    result = run_arch(["model", *args], root)
    assert result.returncode == 0, result.stderr


def check_output(root: Path) -> dict:
    result = run_arch(["check", "--json"], root)
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def targets(output: dict) -> list[str]:
    return [row["target"] for row in output["rows"]]


def validates(root: Path) -> bool:
    return run_arch(["model", "validate"], root).returncode == 0


def test_component_row_is_covered_by_a_star_exception_naming_it(tmp_path: Path):
    root = fixture_root(tmp_path)
    before = check_output(root)
    assert COMPONENT_ROW in targets(before)
    model_edit(root, "add-exception", COMPONENT_ROW, "*", f"rule={COMPONENT_RULE}", "reason=accepted")
    after = check_output(root)
    assert COMPONENT_ROW not in targets(after)
    assert after["covered"] == before["covered"] + 1


def test_component_row_exception_for_another_rule_does_not_cover(tmp_path: Path):
    root = fixture_root(tmp_path)
    model_edit(root, "add-exception", COMPONENT_ROW, "*", "rule=R31", "reason=other rule")
    assert COMPONENT_ROW in targets(check_output(root))


def test_component_row_without_a_rule_is_covered(tmp_path: Path):
    root = fixture_root(tmp_path)
    model_edit(root, "add-exception", COMPONENT_ROW, "*", "reason=accepted")
    assert COMPONENT_ROW not in targets(check_output(root))


def test_port_exception_covers_the_port_row_and_validates(tmp_path: Path):
    root = fixture_root(tmp_path)
    assert PORT_ROW in targets(check_output(root))
    model_edit(root, "add-exception", PORT_ROW, "*", "reason=accepted")
    assert validates(root)
    assert PORT_ROW not in targets(check_output(root))


def test_port_exception_covers_only_its_own_port(tmp_path: Path):
    root = fixture_root(tmp_path)
    model_edit(root, "add-exception", f"{PORT_UNIT}#OtherSymbol", "*", "reason=another port")
    assert PORT_ROW in targets(check_output(root))


def test_unit_exception_covers_the_ports_of_that_unit(tmp_path: Path):
    root = fixture_root(tmp_path)
    model_edit(root, "add-exception", PORT_UNIT, "*", "reason=accepted")
    assert validates(root)
    assert PORT_ROW not in targets(check_output(root))


def test_star_exception_never_covers_a_cycle(tmp_path: Path):
    root = fixture_root(tmp_path)
    for member in ("lending", "notify", "storage", "lending -> notify -> storage"):
        model_edit(root, "add-exception", member, "*", "reason=accepted")
    assert CYCLE_ROW in targets(check_output(root))


def test_port_exception_whose_unit_matches_no_module_fails_validate(tmp_path: Path):
    root = fixture_root(tmp_path)
    model_edit(root, "add-exception", "src/gone.ts#Thing", "*", "reason=x")
    result = run_arch(["model", "validate"], root)
    assert result.returncode == 2 and "src/gone.ts#Thing" in result.stderr
