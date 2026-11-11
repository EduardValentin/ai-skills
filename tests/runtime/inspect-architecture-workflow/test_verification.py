import json
import re
from pathlib import Path

import pytest

from support import FIXTURES, SKILL_DIR, copy_fixture, git, run_arch, run_node
from test_check_conditions import ADAPTER, MODEL, edit_json, ids_of, seeded

REGISTRY_MODULE = (SKILL_DIR / "scripts" / "lib" / "checks" / "registry.mjs").as_uri()
STRUCTURE_REQUEST = re.compile(
    r"\b(add|introduce|create|define|declare|extract)\s+(?:(?:a|an|one|the|new)\s+)?(?:[\w-]+\s+)?"
    r"(port|interface|layer|component|factory|boundary)s?\b",
    re.IGNORECASE,
)
OVER_ENGINEERED_TARGETS = ["contracts", "hooks"]
FACTS = ["exports", "implements", "constructs", "signatures", "symbolImports", "typeChecks"]


def check_json(root: Path, *args: str) -> tuple[int, dict]:
    result = run_arch(["check", *args, "--json"], root)
    assert result.returncode in (0, 1), result.stderr
    return result.returncode, json.loads(result.stdout)


def enforced_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if row["status"] == "enforced"]


def registry_entries() -> dict[str, list]:
    script = (
        f"import {{ CHECKS, JUDGMENTS }} from {json.dumps(REGISTRY_MODULE)};"
        "console.log(JSON.stringify({ checks: CHECKS.map((c) => ({ id: c.id, facts: c.facts })),"
        " judgments: JUDGMENTS.map((j) => j.id) }));"
    )
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_sound_small_has_no_finding(tmp_path: Path):
    root = copy_fixture("sound-small", tmp_path / "p")
    code, out = check_json(root, "--strict")
    assert code == 0 and out["rows"] == [] and out["incomplete"] == []
    assert run_arch(["model", "validate"], root).returncode == 0
    assert run_arch(["uncovered"], root).returncode == 0
    applicable = run_arch(["applicable", "--all"], root)
    assert applicable.returncode == 0, applicable.stderr


def test_sound_small_output_asks_for_no_more_structure(tmp_path: Path):
    root = copy_fixture("sound-small", tmp_path / "p")
    for command in (["check"], ["applicable", "--all"]):
        text = run_arch(command, root).stdout
        assert not STRUCTURE_REQUEST.search(text), text


def test_known_defects_reports_each_defect_once(tmp_path: Path):
    root = copy_fixture("known-defects", tmp_path / "p")
    _, out = check_json(root)
    expected = seeded()
    reported = {(row["target"], check): row for row in out["rows"] for check in ids_of(row)}
    assert set(reported) == {(entry["target"], entry["check"]) for entry in expected}
    assert len(out["rows"]) == len({(row["target"], row["defect"]) for row in out["rows"]})
    for entry in expected:
        row = reported[(entry["target"], entry["check"])]
        assert set(entry["rules"]) <= set(row["rules"]) and row["defect"] == entry["defect"]
    assert out["incomplete"] == []


def test_over_engineered_asks_for_no_more_structure(tmp_path: Path):
    root = copy_fixture("over-engineered", tmp_path / "p")
    code, out = check_json(root)
    assert code == 0
    assert [(row["check"], row["target"], row["severity"]) for row in out["rows"]] == [
        ("unused-abstractions", target, "minor") for target in OVER_ENGINEERED_TARGETS]
    assert out["incomplete"] == []
    for row in out["rows"]:
        assert not STRUCTURE_REQUEST.search(row["correction"]), row
    assert check_json(root, "--strict")[0] == 1
    facade = (root / "src/facade/default-note-facade.ts").read_text()
    assert "this.useCase.add(" in facade
    readme = (FIXTURES / "over-engineered" / "README.md").read_text()
    listed = set(re.findall(r"`([a-z]+(?:-[a-z]+)+)`", readme)) & set(registry_entries()["judgments"])
    assert {"abstraction-without-reason", "boundary-defers-nothing"} <= listed


CORRECTION_FIXTURES = ["sound-small", "known-defects", "over-engineered", "payroll"]
NEW_PORT = re.compile(
    r"\b(a|an|new|separate)\s+(?:[\w-]+\s+)?(port|interface|boundary)\b|\bports?\b[^;]*\bdeclares\b",
    re.IGNORECASE,
)
ABSTRACT_ONLY = re.compile(r"\bmore abstract\b|\bshield", re.IGNORECASE)
EXTERNAL_END = "external:"


def adapter_facts(root: Path) -> tuple[dict[str, list[str]], dict[str, set[str]]]:
    document = json.loads((root / ADAPTER).read_text())
    implements = {module["path"]: module.get("implements") or [] for module in document["modules"]}
    importers: dict[str, set[str]] = {}
    for edge in document["edges"]:
        if "external" in edge:
            importers.setdefault(edge["external"]["name"], set()).add(edge["from"])
    return implements, importers


def existing_ports(row: dict, root: Path) -> list[str]:
    declared = {port["at"].split("#")[1] for port in json.loads((root / MODEL).read_text()).get("ports", [])}
    implements, importers = adapter_facts(root)
    ends = row["target"].split(" -> ")
    if len(ends) != 2:
        return []
    detail = ends[1]
    holders = importers.get(detail[len(EXTERNAL_END):], set()) if detail.startswith(EXTERNAL_END) else {detail}
    return sorted({symbol for path in holders for symbol in implements.get(path, []) if symbol in declared})


@pytest.mark.parametrize("fixture", CORRECTION_FIXTURES)
def test_no_correction_proposes_a_new_port_where_one_exists(tmp_path: Path, fixture: str):
    root = copy_fixture(fixture, tmp_path / "p")
    _, out = check_json(root)
    for row in out["rows"]:
        existing = existing_ports(row, root)
        assert not ABSTRACT_ONLY.search(row["correction"]), row
        if not existing:
            continue
        assert not NEW_PORT.search(row["correction"]), row
        if re.search(r"\bport\b", row["correction"]):
            assert any(f"`{symbol}`" in row["correction"] for symbol in existing), row


@pytest.mark.parametrize("fixture", CORRECTION_FIXTURES)
def test_every_row_states_its_consequence_in_one_sentence(tmp_path: Path, fixture: str):
    _, out = check_json(copy_fixture(fixture, tmp_path / "p"))
    for row in out["rows"]:
        consequence = row.get("consequence", "")
        assert consequence.endswith(".") and consequence.count(". ") == 0, row


def test_an_external_import_is_removed_or_recorded_before_a_port_is_proposed(tmp_path: Path):
    _, out = check_json(copy_fixture("known-defects", tmp_path / "p"))
    (row,) = [r for r in out["rows"] if r["target"] == "src/lending/loan-use-case.ts -> external:pg"]
    correction = row["correction"]
    assert correction.startswith("Remove the import of pg from src/lending/loan-use-case.ts")
    assert "arch model add-exception lending external:pg reason=" in correction
    assert correction.index("add-exception") < re.search(r"\bport\b", correction).start()


def recorded_root(tmp_path: Path) -> Path:
    return copy_fixture("recorded-exceptions", tmp_path / "p")


def test_recorded_exceptions_raise_nothing_covered(tmp_path: Path):
    root = recorded_root(tmp_path)
    code, out = check_json(root, "--strict")
    assert code == 0 and enforced_rows(out["rows"]) == [] and out["incomplete"] == []
    advisory = [row for row in out["rows"] if row["status"] == "advisory"]
    assert advisory and {row["status"] for row in out["rows"]} == {"advisory"}
    assert {entry["status"] for entry in out["skipped"]} == {"off", "advisory"}
    assert all(entry["reason"] for entry in out["skipped"])
    assert any(entry["status"] == "off" and entry["component"] for entry in out["skipped"])

    bare = copy_fixture("recorded-exceptions", tmp_path / "bare")
    edit_json(bare / MODEL, lambda d: d.pop("exceptions"))
    _, uncovered = check_json(bare)
    assert out["covered"] == len(enforced_rows(uncovered["rows"])) > 0


def exception_entries(root: Path) -> list[dict]:
    return json.loads((root / MODEL).read_text())["exceptions"]


def test_each_recorded_exception_covers_a_row(tmp_path: Path):
    entries = exception_entries(recorded_root(tmp_path / "count"))
    assert len(entries) >= 4
    for index in range(len(entries)):
        root = copy_fixture("recorded-exceptions", tmp_path / f"without-{index}")
        edit_json(root / MODEL, lambda d: d["exceptions"].pop(index))
        _, out = check_json(root)
        assert enforced_rows(out["rows"]), entries[index]


def test_recorded_exceptions_cover_each_kind_of_end(tmp_path: Path):
    entries = exception_entries(recorded_root(tmp_path))
    assert any(entry["to"] == "*" and "#" in entry["from"] for entry in entries)
    assert any(entry["to"] == "*" and "#" not in entry["from"] and "/" in entry["from"] for entry in entries)
    assert any(entry["to"].startswith("external:") for entry in entries)
    assert any("/" in entry["from"] and "/" in entry["to"] for entry in entries)


def rows_of(out: dict, check: str) -> list[dict]:
    return [row for row in out["rows"] if check in ids_of(row)]


def test_recorded_off_rule_hides_its_rows_only_while_it_is_off(tmp_path: Path):
    root = recorded_root(tmp_path)
    assert not rows_of(check_json(root)[1], "unenforced-component")
    assert run_arch(["model", "unset-rule", "R38@reports"], root).returncode == 0
    (row,) = rows_of(check_json(root)[1], "unenforced-component")
    assert row["target"] == "reports" and row["status"] == "enforced"


def test_recorded_advisory_rule_makes_its_row_gate_only_when_enforced(tmp_path: Path):
    root = recorded_root(tmp_path)
    assert [row["status"] for row in rows_of(check_json(root)[1], "thin-component-use")] == ["advisory"]
    assert run_arch(["model", "unset-rule", "R27"], root).returncode == 0
    code, out = check_json(root)
    assert code == 0 and [row["status"] for row in rows_of(out, "thin-component-use")] == ["enforced"]
    assert check_json(root, "--strict")[0] == 1


def test_recorded_threshold_hides_a_row_until_it_is_reset(tmp_path: Path):
    root = recorded_root(tmp_path)
    assert not rows_of(check_json(root)[1], "distance-over-threshold")
    assert run_arch(["model", "unset-threshold", "distanceDeviations"], root).returncode == 0
    (row,) = rows_of(check_json(root)[1], "distance-over-threshold")
    assert row["target"] == "reports"


@pytest.mark.parametrize("fact", FACTS)
def test_removing_a_capability_makes_its_conditions_incomplete(tmp_path: Path, fact: str):
    listing = [entry["id"] for entry in registry_entries()["checks"] if fact in entry["facts"]]
    assert listing
    root = copy_fixture("known-defects", tmp_path / "p")
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update({fact: False}))
    code, out = check_json(root, "--strict")
    assert code == 1
    awaiting_base = {entry["check"] for entry in out["notRun"] if entry["reason"] == "needs --base"}
    incomplete = {entry["check"] for entry in out["incomplete"]}
    assert incomplete & set(listing)
    for check in listing:
        assert check in incomplete or check in awaiting_base, check
        assert not [row for row in out["rows"] if check in ids_of(row)], check


def snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_no_model_in_an_empty_repository_reports_it_and_writes_only_inside_the_work_folder(tmp_path: Path):
    git(["init", "-q", "-b", "main"], tmp_path)
    status = run_arch(["model", "status"], tmp_path)
    assert status.returncode == 0 and "absent" in status.stdout
    plain = run_arch(["check"], tmp_path)
    assert plain.returncode == 0 and "no architecture model" in plain.stdout
    written = run_arch(["check", "--out", ".architecture/work/check.json"], tmp_path)
    assert written.returncode == 0, written.stderr
    assert json.loads((tmp_path / ".architecture/work/check.json").read_text()) == {"model": False}
    applicable = run_arch(["applicable", "--all"], tmp_path)
    assert applicable.returncode == 0 and "no architecture model" in applicable.stdout
    added = run_arch(["findings", "add", "--flow", "change-review", "--base", "main",
                      "--check", ".architecture/work/check.json"], tmp_path)
    assert added.returncode == 0, added.stderr
    assert "no architecture model" in added.stdout
    outside = [name for name in snapshot(tmp_path) if not name.startswith(".architecture/")]
    assert outside == []
