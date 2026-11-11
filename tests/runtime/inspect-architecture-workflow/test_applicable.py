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
CONTAINED = "contained in one component; adds no component, port, cross-component edge, or external"
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


def test_change_inside_one_component_needs_no_review(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD")
    assert out["model"] is True
    assert out["review"] is False
    assert out["reasons"] == [CONTAINED]
    assert out["groups"] == [] and out["judgments"] == {}
    assert out["uncovered"] == []
    assert out["notReviewed"] == len([j for entries in applicable(root, "--base", "HEAD", "--full")["judgments"].values()
                                      for j in entries])
    assert out["notReviewed"] > 0


def test_contained_change_prose_counts_what_was_not_reviewed(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    result = run_arch(["applicable", "--base", "HEAD"], root)
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "Review needed: no"
    assert f"- {CONTAINED}" in lines
    count = applicable(root, "--base", "HEAD")["notReviewed"]
    assert lines[-1] == f"Judgment conditions not reviewed for a contained change: {count}. Pass --full to review them."


def test_full_reviews_a_contained_change_with_judgments_in_scope(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD", "--full")
    assert out["review"] is True
    assert "business-rule-placement" in out["groups"]
    assert "entity-carries-framework-traits" in judgment_ids(out, "business-rule-placement")
    assert out["notReviewed"] == 0
    assert len(out["reasons"]) == 1 and "--full" in out["reasons"][0]


def test_full_with_nothing_in_scope_is_not_a_review(tmp_path: Path):
    root = repo(tmp_path)
    for number in range(1, 42):
        result = run_arch(["model", "set-rule", f"R{number}", "off", "reason=all off"], root)
        assert result.returncode == 0, result.stderr
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD", "--full")
    assert out["review"] is False
    assert out["reasons"] == [CONTAINED]
    assert out["notReviewed"] == 0


def test_custom_kind_stands_in_for_default_kinds_of_its_role(tmp_path: Path):
    root = repo(tmp_path)

    def custom_kind(document: dict) -> None:
        document["kinds"] = {"rule-set": {"role": "policy", "ring": "entities"}}
        document["components"][0]["classify"][-1] = ["**", "rule-set"]

    edit_json(root / MODEL, custom_kind)
    touch(root, EMPLOYEE)
    out = applicable(root, "--base", "HEAD", "--full")
    placement = judgment_ids(out, "business-rule-placement")
    assert "entity-carries-framework-traits" in placement and "critical-rule-in-use-case" in placement
    assert "device-unit-holds-logic" not in judgment_ids(out, "humble-objects")


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
    out = applicable(root, "--base", "HEAD", "--full")
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
    out = applicable(root, "--base", "HEAD", "--full")
    assert "humble-objects" not in out["groups"]
    assert "humble-objects" not in out["judgments"]


def test_component_rule_off_drops_only_that_component(tmp_path: Path):
    root = repo(tmp_path)
    for rule in ("R20", "R21", "R22"):
        result = run_arch(["model", "set-rule", f"{rule}@web", "off", "reason=thin controllers"], root)
        assert result.returncode == 0, result.stderr
    touch(root, CONTROLLER)
    assert "humble-objects" not in applicable(root, "--base", "HEAD", "--full")["groups"]
    touch(root, CLOCK)
    assert "humble-objects" in applicable(root, "--base", "HEAD", "--full")["groups"]


def test_touched_uncovered_file_is_listed_and_needs_review(tmp_path: Path):
    root = repo(tmp_path)
    add_stray_module(root)
    out = applicable(root, "--base", "HEAD")
    assert out["uncovered"] == [STRAY]
    assert out["review"] is True
    assert out["notReviewed"] == 0


def test_files_mode_uses_component_spread_only(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    add_adapter_edge(root, {"from": CLOCK, "to": MAIN, "kind": "import"})
    single = applicable(root, "--files", f"{EMPLOYEE},src/domain/clock.ts")
    assert single["review"] is False
    assert single["reasons"] == [CONTAINED]
    spread = applicable(root, "--files", f"{EMPLOYEE},{MAIN}")
    assert spread["review"] is True
    assert any("domain" in reason and "web" in reason for reason in spread["reasons"])
    assert "humble-objects" in spread["groups"]
    stray = applicable(root, "--files", "docs/notes.md")
    assert stray["uncovered"] == ["docs/notes.md"]
    assert stray["review"] is True


def test_files_mode_treats_an_unclassified_path_as_uncovered(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / MODEL, lambda d: d["components"][2].update(
        classify=[["main.ts", "composition-root"], ["*-controller.ts", "controller"]]))
    out = applicable(root, "--files", "src/web/notes.txt")
    assert out["uncovered"] == ["src/web/notes.txt"]
    assert out["review"] is True


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
    assert out["review"] is True
    assert set(out["groups"]) == set(out["judgments"]) and len(out["groups"]) > 0
    assert "entity-carries-framework-traits" in judgment_ids(out, "business-rule-placement")
    assert "handler-holds-business-logic" in judgment_ids(out, "humble-objects")
    assert "components-and-stability" in out["groups"]
    assert out["notReviewed"] == 0


def test_all_is_not_a_review_when_every_rule_is_off(tmp_path: Path):
    root = repo(tmp_path)
    for number in range(1, 42):
        assert run_arch(["model", "set-rule", f"R{number}", "off", "reason=all off"], root).returncode == 0
    out = applicable(root, "--all")
    assert out["review"] is False and out["groups"] == []


def test_proposal_scope_is_its_modules_edges_and_components(tmp_path: Path):
    root = repo(tmp_path)
    plain = write_proposal(root, modules=[{"path": EMPLOYEE}], edges=[])
    contained = applicable(root, "--proposal", plain)
    assert contained["review"] is False and contained["reasons"] == [CONTAINED]
    assert applicable(root, "--proposal", plain, "--full")["review"] is True
    crossing = write_proposal(
        root, modules=[{"path": CLOCK}], edges=[{"from": CLOCK, "to": MAIN, "kind": "import"}]
    )
    out = applicable(root, "--proposal", crossing)
    assert out["review"] is True
    assert any("adapters -> web" in reason for reason in out["reasons"]), out["reasons"]
    assert "components-and-stability" in out["groups"]


PLAN_JUDGMENTS = {"structure-consequence-unstated": "cross-cutting", "plan-names-no-falsifying-tests": "tests",
                  "plan-sequences-io-first": "deferral-and-boundaries"}


def test_proposal_brings_the_plan_judgments_into_scope(tmp_path: Path):
    root = repo(tmp_path)
    contained = write_proposal(root, modules=[{"path": EMPLOYEE}], edges=[])
    out = applicable(root, "--proposal", contained, "--full")
    for judgment, group in PLAN_JUDGMENTS.items():
        assert judgment in judgment_ids(out, group), judgment
    audit = applicable(root, "--all")
    assert not [j for j, group in PLAN_JUDGMENTS.items() if j in judgment_ids(audit, group)]


def test_every_judgment_carries_its_targets_and_condition(tmp_path: Path):
    root = repo(tmp_path)
    proposal = write_proposal(root, modules=[{"path": EMPLOYEE}], edges=[])
    for args in (["--all"], ["--files", EMPLOYEE, "--full"], ["--proposal", proposal, "--full"]):
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


def test_out_writes_the_json_and_prints_the_counts(tmp_path: Path):
    root = repo(tmp_path)
    touch(root, EMPLOYEE)
    result = run_arch(["applicable", "--base", "HEAD", "--out", ".architecture/work/applicable.json"], root)
    assert result.returncode == 0, result.stderr
    written = json.loads((root / ".architecture/work/applicable.json").read_text())
    assert written == applicable(root, "--base", "HEAD")
    assert written["inScope"] == written["notReviewed"] > 0
    assert result.stdout.strip() == (
        f"wrote .architecture/work/applicable.json: review no, {written['inScope']} judgment conditions in scope, "
        f"{written['notReviewed']} not reviewed"
    )
    refused = run_arch(["applicable", "--base", "HEAD", "--out", "applicable.json"], root)
    assert refused.returncode == 2 and ".architecture/work/" in refused.stderr


def test_in_scope_counts_the_listed_judgments_and_those_left_out(tmp_path: Path):
    root = repo(tmp_path)
    out = applicable(root, "--all")
    assert out["inScope"] == sum(len(entries) for entries in out["judgments"].values()) and out["notReviewed"] == 0
