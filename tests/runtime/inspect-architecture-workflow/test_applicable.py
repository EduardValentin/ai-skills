import json
import re
from pathlib import Path

from support import SKILL_DIR, assert_needs_baseline, copy_fixture, git, init_repo, run_arch, run_node

CHECKS_DIR = SKILL_DIR / "scripts" / "lib" / "checks"
REGISTRY_MODULE = (CHECKS_DIR / "registry.mjs").as_uri()
DEFAULTS_MODULE = (SKILL_DIR / "scripts" / "lib" / "model" / "defaults.mjs").as_uri()
ADAPTER = "adapter.json"
EMPLOYEE = "src/domain/employee.ts"
CONTROLLER = "src/web/payroll-controller.ts"
CLOCK = "src/adapters/system-clock.ts"
MAIN = "src/web/main.ts"
STRAY = "src/stray/helper.ts"
MODEL = "docs/architecture/architecture.json"
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


def judgment_ids(out: dict, group: str) -> list[str]:
    return [entry["id"] for entry in out["judgments"].get(group, [])]


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


NO_ADDS = {"components": [], "ports": [], "componentEdges": [], "externals": []}


def condition_count(out: dict) -> int:
    return sum(len(entries) for entries in out["judgments"].values())


def test_change_inside_one_component_lists_its_judgment_conditions(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    assert "model" not in out
    assert not {"review", "reasons", "notReviewed"} & set(out)
    assert out["units"] == [{"path": EMPLOYEE, "kind": "entity", "component": "domain"}]
    assert out["components"] == ["domain"] and out["uncovered"] == []
    assert out["adds"] == NO_ADDS
    assert "entity-carries-framework-traits" in judgment_ids(out, "business-rule-placement")
    assert out["inScope"] == condition_count(out) > 0


def test_prose_opens_with_the_scope_of_the_review(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    result = run_arch(["applicable", "--base", "HEAD"], root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == (
        f"Scope of the review: 1 unit in 1 component (domain); {out['inScope']} judgment conditions in "
        f"{len(out['groups'])} rule groups"
    )
    assert lines[1:3] == ["Adds:", "- none"]
    assert not any("Review needed" in line or "not reviewed" in line for line in lines)


def test_the_full_flag_no_longer_exists(tmp_path: Path):
    root = repo(tmp_path)
    result = run_arch(["applicable", "--base", "HEAD", "--full"], root)
    assert result.returncode == 2 and "--full" in result.stderr


def test_every_rule_off_leaves_no_judgment_condition(tmp_path: Path):
    root = repo(tmp_path)
    for number in range(1, 42):
        result = run_arch(["model", "set-rule", f"R{number}", "off", "reason=all off"], root)
        assert result.returncode == 0, result.stderr
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    assert out["groups"] == [] and out["judgments"] == {} and out["inScope"] == 0
    assert out["units"] == [{"path": EMPLOYEE, "kind": "entity", "component": "domain"}]


def test_custom_kind_stands_in_for_default_kinds_of_its_role(tmp_path: Path):
    root = repo(tmp_path)

    def custom_kind(document: dict) -> None:
        document["kinds"] = {"rule-set": {"role": "policy", "ring": "entities"}}
        document["components"][0]["classify"][-1] = ["**", "rule-set"]

    edit_json(root / MODEL, custom_kind)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    placement = judgment_ids(out, "business-rule-placement")
    assert "entity-carries-framework-traits" in placement and "critical-rule-in-use-case" in placement
    assert "device-unit-holds-logic" not in judgment_ids(out, "humble-objects")


def test_a_neutral_custom_kind_still_brings_the_cross_cutting_conditions(tmp_path: Path):
    root = repo(tmp_path)

    def neutral_kind(document: dict) -> None:
        document["kinds"] = {"notes": {"role": "neutral", "ring": "entities"}}
        document["components"][0]["classify"][-1] = ["**", "notes"]

    edit_json(root / MODEL, neutral_kind)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    assert out["groups"] == ["cross-cutting"]
    assert judgment_ids(out, "cross-cutting") == ["shape-mismatch-hidden"]


def test_a_new_cross_component_edge_is_listed_under_adds(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CLOCK)
    add_adapter_edge(root, {"from": CLOCK, "to": MAIN, "kind": "import"})
    out = applicable(root, "--base", "HEAD")
    assert out["adds"] == {**NO_ADDS, "componentEdges": ["adapters -> web"]}
    assert "components-and-stability" in out["groups"]


def test_a_new_external_is_listed_under_adds(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CLOCK)
    add_adapter_edge(root, {"from": CLOCK, "external": {"name": "luxon", "tag": "vendor"}})
    assert applicable(root, "--base", "HEAD")["adds"] == {**NO_ADDS, "externals": ["luxon"]}


def test_a_new_port_and_component_are_listed_under_adds(tmp_path: Path):
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
    adds = applicable(root, "--base", "HEAD")["adds"]
    assert adds["components"] == ["billing"] and adds["ports"] == ["src/billing/invoices.ts#Invoices"]


def test_groups_follow_touched_kinds(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CONTROLLER)
    out = applicable(root, "--base", "HEAD")
    assert "humble-objects" in out["groups"]
    assert "handler-holds-business-logic" in judgment_ids(out, "humble-objects")
    assert set(out["groups"]) == set(out["judgments"])
    assert "test-power-behind-flag" in judgment_ids(out, "tests")
    assert "rule-tested-through-volatile-surface" not in judgment_ids(out, "tests")


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


def test_a_touched_uncovered_unit_is_listed_and_brings_the_cross_cutting_conditions(tmp_path: Path):
    root = repo(tmp_path)
    add_stray_module(root)
    out = applicable(root, "--base", "HEAD")
    assert out["uncovered"] == [STRAY] and out["units"] == []
    assert out["groups"] == ["cross-cutting"]
    assert judgment_ids(out, "cross-cutting") == ["shape-mismatch-hidden"]


def test_a_change_that_touches_no_unit_has_nothing_in_scope(tmp_path: Path):
    root = repo(tmp_path)
    (root / "NOTES.md").write_text("notes\n")
    out = applicable(root, "--base", "HEAD")
    assert out["units"] == [] and out["uncovered"] == [] and out["components"] == []
    assert out["judgments"] == {} and out["inScope"] == 0
    prose = run_arch(["applicable", "--base", "HEAD"], root).stdout.splitlines()
    assert prose[0] == "Scope of the review: no unit touched; 0 judgment conditions in 0 rule groups"


def test_files_mode_lists_the_units_and_components_without_additions(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    add_adapter_edge(root, {"from": CLOCK, "to": MAIN, "kind": "import"})
    single = applicable(root, "--files", f"{EMPLOYEE},src/domain/clock.ts")
    assert [unit["path"] for unit in single["units"]] == [EMPLOYEE, "src/domain/clock.ts"]
    assert single["components"] == ["domain"] and single["adds"] == NO_ADDS
    spread = applicable(root, "--files", f"{EMPLOYEE},{MAIN}")
    assert spread["components"] == ["domain", "web"]
    assert "humble-objects" in spread["groups"]
    stray = applicable(root, "--files", "docs/notes.md")
    assert stray["uncovered"] == ["docs/notes.md"] and stray["units"] == []


def test_files_mode_treats_an_unclassified_path_as_uncovered(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d["components"][2].update(
        classify=[["main.ts", "composition-root"], ["*-controller.ts", "controller"]]))
    out = applicable(root, "--files", "src/web/notes.txt")
    assert out["uncovered"] == ["src/web/notes.txt"]
    assert out["units"] == []


def test_no_model_exits_2_naming_the_baseline_flow(tmp_path: Path):
    assert_needs_baseline(run_arch(["applicable", "--files", "a.ts", "--json"], tmp_path))
    assert_needs_baseline(run_arch(["applicable", "--files", "a.ts"], tmp_path))


def test_plain_output_is_short_prose(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, CONTROLLER, EMPLOYEE)
    add_stray_module(root)
    result = run_arch(["applicable", "--base", "HEAD"], root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith("Scope of the review: 2 units in 2 components (")
    assert ", 1 uncovered file; " in lines[0]
    assert "Adds:" in lines
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


def test_audit_and_unpublished_judgments_reuse_the_check_defects():
    data = registry()
    judgments = {j["id"]: j for j in data["judgments"]}
    expected = {
        "change-history-spans-groups": ("R27", "major", "change-spans-groups"),
        "change-history-without-groups": ("R28", "minor", "no-cohesion-groups"),
        "thin-use-of-unpublished-component": ("R27", "minor", "thin-component-use"),
        "unconsumed-export-of-unpublished-component": ("R38", "major", "published-without-consumer"),
    }
    for identifier, (rule, severity, defect) in expected.items():
        entry = judgments[identifier]
        assert (entry["rules"], entry["severity"], entry["defect"], entry["targets"]) == (
            [rule], severity, defect, ["component"]), identifier
    assert "{historyWindow}" in judgments["change-history-spans-groups"]["condition"]
    assert "{componentUseShare}" in judgments["thin-use-of-unpublished-component"]["condition"]
    assert judgments["structure-consequence-unstated"]["condition"].startswith("A plan ")


def write_proposal(root: Path, **document) -> str:
    path = root / ".architecture/work/proposal.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1, **document}))
    return str(path.relative_to(root))


def test_exactly_one_of_the_four_modes_is_required(tmp_path: Path):
    root = repo(tmp_path)
    for args in ([], ["--base", "HEAD", "--all"], ["--files", EMPLOYEE, "--all"], ["--all", "--proposal", "p.json"]):
        result = run_arch(["applicable", *args], root)
        assert result.returncode == 2 and "--proposal" in result.stderr and "--all" in result.stderr, args


def test_all_puts_every_unit_and_component_in_scope(tmp_path: Path):
    root = repo(tmp_path)
    out = applicable(root, "--all")
    assert set(out["groups"]) == set(out["judgments"]) and len(out["groups"]) > 0
    modules = [module["path"] for module in json.loads((root / ADAPTER).read_text())["modules"]]
    assert out["units"] == len(applicable(root, "--files", ",".join(modules))["units"]) > 0
    assert out["components"] == ["domain", "adapters", "web"] and out["adds"] == NO_ADDS
    assert "entity-carries-framework-traits" in judgment_ids(out, "business-rule-placement")
    assert "handler-holds-business-logic" in judgment_ids(out, "humble-objects")
    assert "components-and-stability" in out["groups"]


def test_all_has_nothing_in_scope_when_every_rule_is_off(tmp_path: Path):
    root = repo(tmp_path)
    for number in range(1, 42):
        assert run_arch(["model", "set-rule", f"R{number}", "off", "reason=all off"], root).returncode == 0
    out = applicable(root, "--all")
    assert out["groups"] == [] and out["inScope"] == 0


def test_proposal_scope_is_its_modules_edges_and_components(tmp_path: Path):
    root = repo(tmp_path)
    plain = write_proposal(root, modules=[{"path": EMPLOYEE}], edges=[])
    contained = applicable(root, "--proposal", plain)
    assert contained["adds"] == NO_ADDS and contained["inScope"] > 0
    crossing = write_proposal(
        root, modules=[{"path": CLOCK}], edges=[{"from": CLOCK, "to": MAIN, "kind": "import"}]
    )
    out = applicable(root, "--proposal", crossing)
    assert out["adds"]["componentEdges"] == ["adapters -> web"]
    assert "components-and-stability" in out["groups"]


PLAN_JUDGMENTS = {"structure-consequence-unstated": "cross-cutting", "plan-names-no-falsifying-tests": "tests",
                  "plan-sequences-io-first": "deferral-and-boundaries"}


def test_proposal_brings_the_plan_judgments_into_scope(tmp_path: Path):
    root = repo(tmp_path)
    contained = write_proposal(root, modules=[{"path": EMPLOYEE}], edges=[])
    out = applicable(root, "--proposal", contained)
    for judgment, group in PLAN_JUDGMENTS.items():
        assert judgment in judgment_ids(out, group), judgment
    audit = applicable(root, "--all")
    assert not [j for j, group in PLAN_JUDGMENTS.items() if j in judgment_ids(audit, group)]


def test_every_judgment_carries_its_targets_and_condition(tmp_path: Path):
    root = repo(tmp_path)
    proposal = write_proposal(root, modules=[{"path": EMPLOYEE}], edges=[])
    for args in (["--all"], ["--files", EMPLOYEE], ["--proposal", proposal]):
        out = applicable(root, *args)
        assert out["judgments"], args
        for entries in out["judgments"].values():
            for entry in entries:
                assert set(entry) == {"id", "targets", "condition"}, entry
                assert entry["targets"] and entry["condition"].endswith("."), entry
                assert "{" not in entry["condition"], entry
    spans = next(e for e in applicable(root, "--all")["judgments"]["components-and-stability"]
                 if e["id"] == "change-history-spans-groups")
    assert "within 6 months" in spans["condition"] and spans["targets"] == ["component"]


def test_all_lists_the_cross_cutting_judgments_once_under_their_own_group(tmp_path: Path):
    out = applicable(repo(tmp_path), "--all")
    ids = [entry["id"] for entries in out["judgments"].values() for entry in entries]
    assert len(ids) == len(set(ids))
    assert judgment_ids(out, "cross-cutting") == ["shape-mismatch-hidden"]


def test_proposal_file_follows_the_work_placement_rule(tmp_path: Path):
    root = repo(tmp_path)
    (root / "proposal.json").write_text(json.dumps({"version": 1}))
    result = run_arch(["applicable", "--proposal", "proposal.json"], root)
    assert result.returncode == 2 and ".architecture/" in result.stderr


def test_out_writes_the_json_and_prints_the_scope(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    result = run_arch(["applicable", "--base", "HEAD", "--out", ".architecture/work/applicable.json"], root)
    assert result.returncode == 0, result.stderr
    written = json.loads((root / ".architecture/work/applicable.json").read_text())
    assert written == applicable(root, "--base", "HEAD")
    assert result.stdout.strip() == (
        f"wrote .architecture/work/applicable.json: 1 unit in 1 component (domain); {written['inScope']} judgment "
        f"conditions in {len(written['groups'])} rule groups"
    )
    refused = run_arch(["applicable", "--base", "HEAD", "--out", "applicable.json"], root)
    assert refused.returncode == 2 and ".architecture/work/" in refused.stderr


def test_in_scope_counts_the_listed_judgments(tmp_path: Path):
    out = applicable(repo(tmp_path), "--all")
    assert out["inScope"] == condition_count(out)


def test_the_output_records_the_run_it_was_made_for(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    run = applicable(root, "--base", "HEAD")["run"]
    assert run["mode"] == "base" and run["proposal"] is None
    assert run["base"] == git(["rev-parse", "HEAD"], root).stdout.strip()
    assert run["state"]
    assert applicable(root, "--all")["run"]["mode"] == "audit"
