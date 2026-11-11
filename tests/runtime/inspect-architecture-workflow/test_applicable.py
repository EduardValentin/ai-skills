import json
import re
from pathlib import Path

from support import SKILL_DIR, copy_fixture, init_repo, run_arch, run_node

CHECKS_DIR = SKILL_DIR / "scripts" / "lib" / "checks"
REGISTRY_MODULE = (CHECKS_DIR / "registry.mjs").as_uri()
DEFAULTS_MODULE = (SKILL_DIR / "scripts" / "lib" / "model" / "defaults.mjs").as_uri()
ADAPTER = "adapter.json"
EMPLOYEE = "src/domain/employee.ts"
CONTROLLER = "src/web/payroll-controller.ts"
CLOCK = "src/adapters/system-clock.ts"
MAIN = "src/web/main.ts"
STRAY = "src/stray/helper.ts"
NO_MODEL_LINE = "no architecture model; run a baseline audit to enable the full review"
GROUPS = [
    "dependency-direction", "reasons-to-change", "business-rule-placement", "humble-objects",
    "deferral-and-boundaries", "components-and-stability", "tests", "enforcement-and-organization",
]


def edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def touch(root: Path, *paths: str) -> None:
    for path in paths:
        (root / path).write_text((root / path).read_text() + "\n// changed\n")


def repo(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    init_repo(root)
    return root


def applicable(root: Path, *args: str) -> dict:
    result = run_arch(["applicable", *args, "--json"], root)
    assert result.returncode == 0, result.stderr + result.stdout
    return json.loads(result.stdout)


def add_adapter_edge(root: Path, edge: dict) -> None:
    edit_json(root / ADAPTER, lambda document: document["edges"].append(edge))


def add_stray_module(root: Path) -> None:
    (root / STRAY).parent.mkdir(parents=True)
    (root / STRAY).write_text("export const helper = 1;\n")

    def add_module(document: dict) -> None:
        template = next(module for module in document["modules"] if module["path"] == EMPLOYEE)
        document["modules"].append({**template, "path": STRAY})

    edit_json(root / ADAPTER, add_module)


def registry() -> dict:
    script = (
        f"import {{ CHECKS, JUDGMENTS, RULE_TITLES }} from {json.dumps(REGISTRY_MODULE)};"
        f"import {{ DEFAULT_KINDS, DEFAULT_THRESHOLDS }} from {json.dumps(DEFAULTS_MODULE)};"
        "console.log(JSON.stringify({ checks: CHECKS.map(({ id, rules }) => ({ id, rules })), judgments: JUDGMENTS,"
        " titles: RULE_TITLES, kinds: Object.keys(DEFAULT_KINDS), knobs: Object.keys(DEFAULT_THRESHOLDS) }));"
    )
    result = run_node(script, SKILL_DIR)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_change_inside_one_component_needs_no_review(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    assert out["model"] is True
    assert out["review"] is False
    assert out["reasons"] == []
    assert out["uncovered"] == []


def test_new_cross_component_edge_needs_review(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CLOCK)
    add_adapter_edge(root, {"from": CLOCK, "to": MAIN, "kind": "import"})
    out = applicable(root, "--base", "HEAD")
    assert out["review"] is True
    assert any("adapters -> web" in reason for reason in out["reasons"]), out["reasons"]


def test_new_external_needs_review(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CLOCK)
    add_adapter_edge(root, {"from": CLOCK, "external": {"name": "luxon", "tag": "vendor"}})
    out = applicable(root, "--base", "HEAD")
    assert out["review"] is True
    assert any("luxon" in reason for reason in out["reasons"]), out["reasons"]


def test_new_port_and_component_need_review(tmp_path: Path):
    root = repo(tmp_path)

    def declare(document: dict) -> None:
        document["components"].append({"name": "billing", "paths": ["src/billing/**"],
                                       "classify": [["**", "port"]]})
        document["ports"].append({"at": "src/billing/invoices.ts#Invoices", "owner": "billing"})

    edit_json(root / "docs/architecture/architecture.json", declare)
    (root / "src/billing").mkdir()
    (root / "src/billing/invoices.ts").write_text("export interface Invoices {}\n")
    template = json.loads((root / ADAPTER).read_text())["modules"][0]
    edit_json(root / ADAPTER, lambda d: d["modules"].append({**template, "path": "src/billing/invoices.ts"}))
    reasons = " | ".join(applicable(root, "--base", "HEAD")["reasons"])
    assert "billing" in reasons and "src/billing/invoices.ts#Invoices" in reasons


def test_groups_follow_touched_kinds(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CONTROLLER)
    out = applicable(root, "--base", "HEAD")
    assert "humble-objects" in out["groups"]
    assert "handler-holds-business-logic" in out["judgments"]["humble-objects"]
    assert set(out["groups"]) == set(out["judgments"])
    assert "test-power-behind-flag" in out["judgments"]["tests"]
    assert "rule-tested-through-volatile-surface" not in out["judgments"]["tests"]


def test_group_is_dropped_when_its_rules_are_off(tmp_path: Path):
    root = repo(tmp_path)
    for rule in ("R20", "R21", "R22"):
        result = run_arch(["model", "set-rule", rule, "off", "reason=no humble objects here"], root)
        assert result.returncode == 0, result.stderr
    touch(root, CONTROLLER)
    out = applicable(root, "--base", "HEAD")
    assert "humble-objects" not in out["groups"]
    assert "humble-objects" not in out["judgments"]


def test_component_rule_off_drops_only_that_component(tmp_path: Path):
    root = repo(tmp_path)
    for rule in ("R20", "R21", "R22"):
        result = run_arch(["model", "set-rule", f"{rule}@web", "off", "reason=thin controllers"], root)
        assert result.returncode == 0, result.stderr
    touch(root, CONTROLLER)
    assert "humble-objects" not in applicable(root, "--base", "HEAD")["groups"]
    touch(root, CLOCK)
    assert "humble-objects" in applicable(root, "--base", "HEAD")["groups"]


def test_touched_uncovered_file_is_listed_and_needs_review(tmp_path: Path):
    root = repo(tmp_path)
    add_stray_module(root)
    out = applicable(root, "--base", "HEAD")
    assert out["uncovered"] == [STRAY]
    assert out["review"] is True


def test_files_mode_uses_component_spread_only(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    add_adapter_edge(root, {"from": CLOCK, "to": MAIN, "kind": "import"})
    single = applicable(root, "--files", f"{EMPLOYEE},src/domain/clock.ts")
    assert single["review"] is False
    assert single["reasons"] == []
    spread = applicable(root, "--files", f"{EMPLOYEE},{MAIN}")
    assert spread["review"] is True
    assert any("domain" in reason and "web" in reason for reason in spread["reasons"])
    assert "humble-objects" in spread["groups"]
    stray = applicable(root, "--files", "docs/notes.md")
    assert stray["uncovered"] == ["docs/notes.md"]
    assert stray["review"] is True


def test_no_model_is_not_a_review(tmp_path: Path):
    result = run_arch(["applicable", "--files", "a.ts", "--json"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"model": False, "review": False, "reasons": [NO_MODEL_LINE]}
    plain = run_arch(["applicable", "--files", "a.ts"], tmp_path)
    assert plain.returncode == 0
    assert plain.stdout.strip() == NO_MODEL_LINE


def test_plain_output_is_short_prose(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CONTROLLER, EMPLOYEE)
    add_stray_module(root)
    result = run_arch(["applicable", "--base", "HEAD"], root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "Review needed: yes"
    assert "Reasons:" in lines
    assert "Rule groups with judgment conditions:" in lines
    assert "Uncovered files:" in lines
    assert any(line.startswith("- humble-objects: ") and "R20 Split humble from testable units" in line
               for line in lines), lines
    assert f"- {STRAY}" in lines


def test_applicable_needs_exactly_one_scope(tmp_path: Path):
    root = repo(tmp_path)
    neither = run_arch(["applicable"], root)
    both = run_arch(["applicable", "--base", "HEAD", "--files", EMPLOYEE], root)
    assert neither.returncode == 2 and "--base" in neither.stderr and "--files" in neither.stderr
    assert both.returncode == 2


def test_ref_values_starting_with_a_dash_are_usage_errors(tmp_path: Path):
    root = repo(tmp_path)
    for args in (["check", "--base", "-p"], ["collect", "--ref", "-p"], ["query", "touched", "--base", "-p"],
                 ["query", "volatility", "--since", "-p"], ["applicable", "--base", "-p"]):
        result = run_arch(args, root)
        assert result.returncode == 2, args
        assert "-p" in result.stderr and "option" in result.stderr, (args, result.stderr)


def test_touched_query_checks_base_before_building_the_graph(tmp_path: Path):
    root = repo(tmp_path)
    edit_json(root / "docs/architecture/architecture.json", lambda d: d.update(adapter="false"))
    result = run_arch(["query", "touched"], root)
    assert result.returncode == 2
    assert "usage: arch query touched --base <ref>" in result.stderr


def test_every_rule_but_r3_has_a_check_or_a_judgment():
    data = registry()
    covered = {rule for entry in data["checks"] + data["judgments"] for rule in entry["rules"]}
    expected = {f"R{number}" for number in range(1, 42)} - {"R3"}
    assert expected - covered == set()
    assert "R3" not in covered


def test_check_and_judgment_ids_are_unique():
    data = registry()
    ids = [entry["id"] for entry in data["checks"] + data["judgments"]]
    assert len(ids) == len(set(ids))


def test_judgment_conditions_name_only_known_knobs():
    data = registry()
    for judgment in data["judgments"]:
        knobs = re.findall(r"\{([^}]*)\}", judgment["condition"])
        assert set(knobs) <= set(data["knobs"]), judgment["id"]
        assert not re.search(r"\d", re.sub(r"\{[^}]*\}", "", judgment["condition"])), judgment["id"]


def test_judgment_entries_are_well_formed():
    data = registry()
    allowed_targets = set(data["kinds"]) | {"component", "plan", "test-suite"}
    for judgment in data["judgments"]:
        assert judgment["group"] in GROUPS + ["cross-cutting"], judgment["id"]
        assert judgment["severity"] in ("blocker", "major", "minor"), judgment["id"]
        assert judgment["targets"] and set(judgment["targets"]) <= allowed_targets, judgment["id"]
        assert all(rule in data["titles"] for rule in judgment["rules"]), judgment["id"]
        assert re.fullmatch(r"[a-z]+(-[a-z]+)*", judgment["id"]), judgment["id"]
        assert re.fullmatch(r"[a-z]+(-[a-z]+)*", judgment["defect"]), judgment["id"]
        assert judgment["condition"].endswith("."), judgment["id"]
    plan_only = {j["id"] for j in data["judgments"] if j["targets"] == ["plan"]}
    assert {"plan-sequences-io-first", "component-map-fixed-upfront", "structure-consequence-unstated"} <= plan_only
