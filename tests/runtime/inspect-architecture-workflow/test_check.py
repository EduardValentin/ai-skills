import json
import shutil
from pathlib import Path

from support import SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

CHECKS_DIR = SKILL_DIR / "scripts" / "lib" / "checks"
RUN_MODULE = (CHECKS_DIR / "run.mjs").as_uri()
REGISTRY_MODULE = (CHECKS_DIR / "registry.mjs").as_uri()
CONTEXT_MODULE = (CHECKS_DIR / "context.mjs").as_uri()
ESCALATE_MODULE = (CHECKS_DIR / "escalate.mjs").as_uri()
DEFAULTS_MODULE = (SKILL_DIR / "scripts" / "lib" / "model" / "defaults.mjs").as_uri()
MODEL = "docs/architecture/architecture.json"
ADAPTER = "adapter.json"
CONTROLLER = "src/web/payroll-controller.ts"
EMPLOYEE = "src/domain/employee.ts"
CLOCK = "src/adapters/system-clock.ts"
MAIN = "src/web/main.ts"
PG = "src/adapters/pg-payroll-repository.ts"
USE_CASE = "src/domain/payroll-use-case.ts"
COLUMNS = "| Rule | Target | Severity | Status | Origin | Evidence | Correction |"
CONSTRUCTION_ROWS = [(f"{CONTROLLER} -> {PG}", "R7"), (f"{CONTROLLER} -> {CLOCK}", "R7")]
CHECK_IDS = [
    "policy-imports-detail", "policy-imports-external", "outward-ring-edge", "detail-constructed-outside-root",
    "component-cycle", "module-cycle", "unstable-dependency", "zone-of-pain", "unused-abstractions",
    "no-cohesion-groups", "change-spans-groups",
]


def edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def seed_edge(root: Path, source: str, target: str, kind: str = "import") -> None:
    edit_json(root / ADAPTER, lambda d: d["edges"].append({"from": source, "to": target, "kind": kind}))


def touch(root: Path, *paths: str) -> None:
    for path in paths:
        (root / path).write_text((root / path).read_text() + "\n// changed\n")


def repo(tmp_path: Path) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    (root / ".gitignore").write_text(".architecture/\n")
    return root


def model_edit(root: Path, *args: str) -> None:
    result = run_arch(["model", *args], root)
    assert result.returncode == 0, result.stderr


def check_output(root: Path, *args: str, exit_code: int | None = None) -> dict:
    result = run_arch(["check", *args, "--json"], root)
    if exit_code is not None:
        assert result.returncode == exit_code, result.stderr + result.stdout
    assert result.returncode in (0, 1), result.stderr
    return json.loads(result.stdout)


def check_rows(root: Path, *args: str) -> list[dict]:
    return check_output(root, *args)["rows"]


def keys(rows: list[dict]) -> list[tuple[str, str]]:
    return [(r["target"], rule) for r in rows for rule in r["rules"]]


def find(rows: list[dict], target: str, rule: str) -> dict:
    matches = [r for r in rows if r["target"] == target and rule in r["rules"]]
    assert len(matches) == 1, rows
    return matches[0]


def two_component_change(tmp_path: Path) -> Path:
    root = repo(tmp_path)
    init_repo(root)
    touch(root, EMPLOYEE, MAIN)
    return root


def run_checks(tmp_path: Path, graph: dict, touched: dict | None = None, model: dict | None = None) -> dict:
    script = (
        f"import {{ runChecks }} from {json.dumps(RUN_MODULE)};"
        f"import {{ DEFAULT_KINDS, DEFAULT_THRESHOLDS }} from {json.dumps(DEFAULTS_MODULE)};"
        "const model = { kinds: DEFAULT_KINDS, thresholds: DEFAULT_THRESHOLDS, rules: {}, forbidden: [],"
        f" exceptions: [], groups: [], components: [], ...{json.dumps(model or {})} }};"
        f"console.log(JSON.stringify(runChecks({{ graph: {json.dumps(graph)}, model, baseGraph: null,"
        f" touched: {json.dumps(touched)} }})));"
    )
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def component(name: str, fan_in: int, fan_out: int, instability, abstractness, zone) -> dict:
    return {"name": name, "fanIn": fan_in, "fanOut": fan_out, "instability": instability,
            "abstractness": abstractness, "distance": None, "zone": zone}


def empty_graph(components: list[dict]) -> dict:
    return {"capabilities": {"exports": True, "constructs": True},
            "rings": ["entities", "use-cases", "adapters", "frameworks"],
            "units": [], "edges": [], "externals": [], "uncovered": [], "components": components, "componentEdges": [],
            "cycles": {"modules": [], "components": []}}


def touched_scope(*components: str) -> dict:
    return {"units": [], "added": [], "components": list(components), "uncovered": []}


def construction_graph(constructing_kind: str, constructed_kind: str) -> dict:
    graph = empty_graph([])
    graph["units"] = [
        {"path": "src/a.ts", "component": None, "ring": "adapters", "kind": constructing_kind},
        {"path": "src/b.ts", "component": None, "ring": "adapters", "kind": constructed_kind},
    ]
    graph["edges"] = [{"from": "src/a.ts", "to": "src/b.ts", "kind": "constructs", "direction": "same"}]
    return graph


def test_registry_declares_each_check_with_the_contract():
    script = (
        f"import {{ CHECKS }} from {json.dumps(REGISTRY_MODULE)};"
        "console.log(JSON.stringify(CHECKS.map((c) => ({ id: c.id, rules: c.rules, group: c.group, defect: c.defect,"
        " severity: c.severity, facts: c.facts, needsBase: c.needsBase, runs: typeof c.run }))));"
    )
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    checks = json.loads(result.stdout)
    assert [c["id"] for c in checks] == CHECK_IDS
    by_id = {c["id"]: c for c in checks}
    assert by_id["zone-of-pain"] == {"id": "zone-of-pain", "rules": ["R31", "R32"], "group": "components-and-stability",
                                     "defect": "zone-of-pain", "severity": "major", "facts": ["exports"],
                                     "needsBase": True, "runs": "function"}
    assert by_id["detail-constructed-outside-root"]["facts"] == ["constructs"]
    assert by_id["policy-imports-external"]["defect"] == "policy-depends-on-detail"
    assert {c["runs"] for c in checks} == {"function"}


def test_every_rule_has_a_short_plain_title():
    script = (
        f"import {{ RULE_TITLES }} from {json.dumps(REGISTRY_MODULE)};"
        "console.log(JSON.stringify(RULE_TITLES));"
    )
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    titles = json.loads(result.stdout)
    assert list(titles) == [f"R{n}" for n in range(1, 42)]
    assert all(1 <= len(title.split()) <= 6 for title in titles.values()), titles
    assert titles["R4"] == "Dependencies point toward policy" and titles["R30"] == "No dependency cycles"


def test_unseeded_fixture_has_only_the_construction_rows_without_a_base(tmp_path: Path):
    out = check_output(copy_fixture("payroll", tmp_path / "p"), exit_code=1)
    assert keys(out["rows"]) == CONSTRUCTION_ROWS
    row = out["rows"][0]
    assert (row["check"], row["defect"], row["severity"], row["baseSeverity"]) == (
        "detail-constructed-outside-root", "detail-constructed-outside-root", "blocker", "blocker")
    assert (row["status"], row["origin"], row["lifts"]) == ("enforced", "none", [])
    assert set(out) == {"model", "rows", "incomplete", "notRun", "skipped", "covered"}
    assert out["model"] is True and out["incomplete"] == [] and out["covered"] == 0
    assert out["skipped"] == [{"rule": "R6", "status": "off", "component": None,
                               "reason": "one delivery mechanism; controllers call use cases directly"}]


def test_markdown_table_has_the_documented_columns_and_titled_rules(tmp_path: Path):
    result = run_arch(["check"], copy_fixture("payroll", tmp_path / "p"))
    assert result.returncode == 1, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == COLUMNS
    assert lines[2].startswith("| R7 Lower-level components are plugins | ")
    assert "\n## Incomplete\n\nNone\n" in result.stdout
    assert "## Rules not enforced\n\n- R6 Use cases own their boundaries: off (one delivery mechanism" in result.stdout


def test_printed_rule_carries_its_title(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, EMPLOYEE, CONTROLLER)
    result = run_arch(["check"], root)
    assert "R4 Dependencies point toward policy" in result.stdout
    assert "R30 No dependency cycles" in result.stdout


def test_markdown_says_none_for_empty_sections(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "add-exception", "web", "adapters", "reason=tolerated for now")
    result = run_arch(["check"], root)
    assert result.returncode == 0, result.stderr
    assert "## Incomplete\n\nNone" in result.stdout


def test_seeded_component_cycle_yields_cycle_rows(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, EMPLOYEE, CONTROLLER)
    rows = check_rows(root)
    component_cycle = find(rows, "adapters -> domain -> web", "R30")
    assert component_cycle["severity"] == "blocker" and component_cycle["defect"] == "cycle"
    members = sorted([PG, CLOCK, EMPLOYEE, "src/domain/index.ts", "src/domain/payroll-repository.ts", USE_CASE, CONTROLLER])
    assert find(rows, " -> ".join(members), "R30")["severity"] == "blocker"
    assert find(rows, f"{EMPLOYEE} -> {CONTROLLER}", "R4")["defect"] == "policy-depends-on-detail"


def test_cycle_targets_sort_members_numerically(tmp_path: Path):
    graph = empty_graph([component("svc2", 1, 1, 0.5, None, None), component("svc10", 1, 1, 0.5, None, None)])
    graph["cycles"]["components"] = [["svc2", "svc10"]]
    assert keys(run_checks(tmp_path, graph)["rows"]) == [("svc2 -> svc10", "R30")]


def test_blocker_rows_record_no_lift(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, EMPLOYEE, USE_CASE)
    row = find(check_rows(root), f"{EMPLOYEE} -> {USE_CASE}", "R4")
    assert row["severity"] == "blocker" and row["lifts"] == [] and row["defect"] == "outward-dependency"


def test_outward_edge_between_components_yields_the_stability_row(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, CLOCK, MAIN)
    rows = check_rows(root)
    assert find(rows, f"{CLOCK} -> {MAIN}", "R4")["lifts"] == []
    assert find(rows, "web -> adapters", "R31")["severity"] == "major"


def test_policy_role_comes_from_the_model(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, USE_CASE, PG)
    target = f"{USE_CASE} -> {PG}"
    assert find(check_rows(root), target, "R4")["defect"] == "policy-depends-on-detail"

    def reclassify(document: dict) -> None:
        document["kinds"] = {"saga": {"role": "neutral", "ring": "use-cases"}}
        domain = document["components"][0]
        domain["classify"][0][1] = "saga"

    edit_json(root / MODEL, reclassify)
    rows = check_rows(root)
    assert not [r for r in rows if r["target"] == target and r["defect"] == "policy-depends-on-detail"]
    edit_json(root / MODEL, lambda d: d["kinds"]["saga"].update(role="policy"))
    assert find(check_rows(root), target, "R4")["defect"] == "policy-depends-on-detail"


def test_same_defect_from_two_rules_is_one_row(tmp_path: Path):
    script = (
        f"import {{ mergeRows }} from {json.dumps(RUN_MODULE)};"
        "const row = (check, rule, severity, evidence) => ({ check, defect: 'policy-depends-on-detail', rules: [rule],"
        " severity, target: 'a.ts -> b.ts', evidence, correction: 'route it', units: ['a.ts', 'b.ts'],"
        " components: [], originKey: { type: 'edge', from: 'a.ts', to: 'b.ts' }, edge: null });"
        "console.log(JSON.stringify(mergeRows(["
        "row('one', 'R17', 'major', 'entity imports a detail'), row('two', 'R4', 'blocker', 'policy imports detail'),"
        "{ ...row('three', 'R4', 'blocker', 'policy imports detail'), defect: 'other' }])));"
    )
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    merged = json.loads(result.stdout)
    assert len(merged) == 2
    row = merged[0]
    assert row["rules"] == ["R4", "R17"] and row["severity"] == "blocker"
    assert row["evidence"] == "entity imports a detail; policy imports detail"
    assert row["check"] == "one, two"
    assert merged[1]["defect"] == "other"


def test_escalation_rules_lift_but_never_lower(tmp_path: Path):
    graph = empty_graph([component("core", 4, 0, 0, 0.5, None), component("leaf", 1, 1, 0.5, 0.5, None)])
    graph["units"] = [
        {"path": "core/a.ts", "component": "core", "ring": "entities", "kind": "entity"},
        {"path": "core/b.ts", "component": "core", "ring": "adapters", "kind": "adapter"},
        {"path": "leaf/c.ts", "component": "leaf", "ring": "adapters", "kind": "adapter"},
    ]
    script = (
        f"import {{ createContext }} from {json.dumps(CONTEXT_MODULE)};"
        f"import {{ escalateRow }} from {json.dumps(ESCALATE_MODULE)};"
        f"import {{ DEFAULT_KINDS, DEFAULT_THRESHOLDS }} from {json.dumps(DEFAULTS_MODULE)};"
        "const model = { kinds: DEFAULT_KINDS, thresholds: DEFAULT_THRESHOLDS };"
        f"const context = createContext({{ graph: {json.dumps(graph)}, model }});"
        "const row = (extra) => ({ severity: 'minor', defect: 'x', units: [], components: [], edge: null, ...extra });"
        "const unitEdge = (from, to) => ({ level: 'unit', from, to });"
        "console.log(JSON.stringify([escalateRow(row({ edge: unitEdge('core/a.ts', 'core/b.ts') }), context),"
        "escalateRow(row({ edge: unitEdge('leaf/c.ts', 'leaf/c.ts') }), context),"
        "escalateRow(row({ edge: unitEdge('leaf/c.ts', 'core/a.ts') }), context),"
        "escalateRow(row({ components: ['core'] }), context),"
        "escalateRow(row({ components: ['leaf'] }), context),"
        "escalateRow(row({ defect: 'cycle' }), context),"
        "escalateRow(row({ severity: 'blocker', components: ['core'], edge: unitEdge('core/a.ts', 'core/b.ts') }),"
        " context)]));"
    )
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    policy_edge, detail_edge, to_side, fan_in, low_fan_in, cycle, blocker = json.loads(result.stdout)
    assert policy_edge == {"severity": "major", "lifts": [1]}
    assert detail_edge == {"severity": "minor", "lifts": []}
    assert to_side == {"severity": "major", "lifts": [3]}
    assert fan_in == {"severity": "major", "lifts": [3]}
    assert low_fan_in == {"severity": "minor", "lifts": []}
    assert cycle == {"severity": "blocker", "lifts": [4]}
    assert blocker == {"severity": "blocker", "lifts": []}


def test_change_across_components_without_groups_asks_for_them_until_a_group_covers_it(tmp_path: Path):
    root = two_component_change(tmp_path)
    rows = check_rows(root, "--base", "HEAD")
    assert [(r["rules"], r["severity"], r["origin"], r["defect"]) for r in rows] == [
        (["R28"], "minor", "introduced", "no-cohesion-groups")]
    model_edit(root, "add-group", "payroll", "members=domain,web", "absorbs=payroll rules")
    assert check_rows(root, "--base", "HEAD") == []


def test_r27_rows_are_the_touched_components_that_share_no_group_with_some_other_touched_component(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    touch(root, EMPLOYEE, CLOCK, MAIN)
    model_edit(root, "add-group", "storage", "members=domain,adapters", "absorbs=storage")
    model_edit(root, "add-group", "delivery", "members=adapters,web", "absorbs=delivery")
    rows = [r for r in check_rows(root, "--base", "HEAD") if "R27" in r["rules"]]
    assert keys(rows) == [("domain", "R27"), ("web", "R27")]
    assert rows[0]["evidence"] == "domain shares no recorded group with web; groups holding domain: storage"
    assert rows[1]["evidence"] == "web shares no recorded group with domain; groups holding web: delivery"
    assert {r["severity"] for r in rows} == {"major"}


def test_r27_evidence_says_none_when_no_group_holds_the_component(tmp_path: Path):
    root = two_component_change(tmp_path)
    model_edit(root, "add-group", "core", "members=domain,adapters", "absorbs=storage")
    rows = check_rows(root, "--base", "HEAD")
    assert keys(rows) == [("domain", "R27"), ("web", "R27")]
    assert rows[1]["evidence"] == "web shares no recorded group with domain; groups holding web: none"


def test_edge_origin_follows_the_pair_against_the_base(tmp_path: Path):
    root = repo(tmp_path)
    seed_edge(root, CLOCK, MAIN)
    init_repo(root)
    seed_edge(root, "src/adapters/memory-payroll-repository.ts", MAIN)
    seed_edge(root, CLOCK, MAIN, kind="dynamic")
    touch(root, CLOCK, "src/adapters/memory-payroll-repository.ts")
    rows = check_rows(root, "--base", "HEAD")
    assert find(rows, f"{CLOCK} -> {MAIN}", "R4")["origin"] == "inherited"
    assert find(rows, f"src/adapters/memory-payroll-repository.ts -> {MAIN}", "R4")["origin"] == "introduced"


def cycle_target() -> str:
    return " -> ".join([EMPLOYEE, "src/domain/payroll-repository.ts", USE_CASE])


def test_a_cycle_the_change_only_shrinks_is_inherited(tmp_path: Path):
    root = repo(tmp_path)
    pristine = (root / ADAPTER).read_text()
    seed_edge(root, EMPLOYEE, USE_CASE)
    seed_edge(root, EMPLOYEE, CONTROLLER)
    init_repo(root)
    (root / ADAPTER).write_text(pristine)
    seed_edge(root, EMPLOYEE, USE_CASE)
    touch(root, EMPLOYEE)
    assert find(check_rows(root, "--base", "HEAD"), cycle_target(), "R30")["origin"] == "inherited"


def test_a_cycle_closed_by_an_added_edge_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    seed_edge(root, EMPLOYEE, USE_CASE)
    touch(root, EMPLOYEE)
    assert find(check_rows(root, "--base", "HEAD"), cycle_target(), "R30")["origin"] == "introduced"


def test_a_new_edge_inside_an_existing_cycle_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    seed_edge(root, EMPLOYEE, USE_CASE)
    init_repo(root)
    touch(root, EMPLOYEE)
    assert find(check_rows(root, "--base", "HEAD"), cycle_target(), "R30")["origin"] == "inherited"
    seed_edge(root, EMPLOYEE, "src/domain/payroll-repository.ts")
    assert find(check_rows(root, "--base", "HEAD"), cycle_target(), "R30")["origin"] == "introduced"


def test_a_renamed_unit_keeps_its_inherited_edge(tmp_path: Path):
    root = repo(tmp_path)
    seed_edge(root, CLOCK, MAIN)
    init_repo(root)
    renamed = "src/adapters/clock-source.ts"
    git(["mv", CLOCK, renamed], root)

    def rename_in_adapter(document: dict) -> None:
        for module in document["modules"]:
            if module["path"] == CLOCK:
                module["path"] = renamed
        for edge in document["edges"]:
            for end in ("from", "to"):
                if edge.get(end) == CLOCK:
                    edge[end] = renamed

    edit_json(root / ADAPTER, rename_in_adapter)
    git(["add", "-A"], root)
    rows = check_rows(root, "--base", "HEAD")
    assert find(rows, f"{renamed} -> {MAIN}", "R4")["origin"] == "inherited"


def test_rows_outside_the_change_are_not_emitted_with_a_base(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    seed_edge(root, CLOCK, MAIN)
    touch(root, EMPLOYEE)
    assert check_rows(root, "--base", "HEAD") == []
    touch(root, CLOCK)
    assert (f"{CLOCK} -> {MAIN}", "R4") in keys(check_rows(root, "--base", "HEAD"))


def test_a_base_that_predates_the_model_is_compared_with_the_current_model(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    saved = tmp_path / "docs"
    shutil.move(root / "docs", saved)
    init_repo(root)
    shutil.move(saved, root / "docs")
    seed_edge(root, CLOCK, MAIN)
    touch(root, EMPLOYEE, MAIN, CLOCK)
    result = run_arch(["check", "--base", "HEAD", "--json"], root)
    assert result.returncode == 1, result.stderr
    rows = json.loads(result.stdout)["rows"]
    assert {(r["rules"][0], r["origin"]) for r in rows} == {
        ("R4", "introduced"), ("R28", "introduced"), ("R30", "introduced"), ("R31", "introduced"),
        ("R7", "inherited")}


def test_rule_off_drops_its_rows_and_is_listed_as_skipped(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "set-rule", "R7", "off", "reason=composition happens in the controller on purpose")
    out = check_output(root, exit_code=0)
    assert out["rows"] == []
    assert {"rule": "R7", "status": "off", "component": None,
            "reason": "composition happens in the controller on purpose"} in out["skipped"]


def test_advisory_row_is_printed_and_exits_0(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "set-rule", "R7", "advisory", "reason=under review")
    out = check_output(root, exit_code=0)
    assert keys(out["rows"]) == CONSTRUCTION_ROWS and {r["status"] for r in out["rows"]} == {"advisory"}
    assert any(entry["rule"] == "R7" and entry["status"] == "advisory" for entry in out["skipped"])


def test_rule_off_for_one_component_only(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "set-rule", "R7@adapters", "off", "reason=adapters are built anywhere")
    assert keys(check_rows(root)) == CONSTRUCTION_ROWS
    model_edit(root, "set-rule", "R7@web", "off", "reason=the controller composes on purpose")
    out = check_output(root, exit_code=0)
    assert out["rows"] == []
    assert {"rule": "R7", "status": "off", "component": "web",
            "reason": "the controller composes on purpose"} in out["skipped"]


def test_a_component_cycle_is_as_strict_as_its_strictest_member(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, EMPLOYEE, CONTROLLER)
    cycle = "adapters -> domain -> web"
    model_edit(root, "set-rule", "R30@domain", "off", "reason=legacy cycle")
    assert find(check_rows(root), cycle, "R30")["status"] == "enforced"
    model_edit(root, "set-rule", "R30", "advisory", "reason=cycles are being removed")
    model_edit(root, "set-rule", "R30@adapters", "off", "reason=legacy cycle")
    assert find(check_rows(root), cycle, "R30")["status"] == "advisory"
    model_edit(root, "set-rule", "R30@web", "off", "reason=legacy cycle")
    assert [r for r in check_rows(root) if r["target"] == cycle] == []


def test_exception_covers_a_row(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "add-exception", "web", "adapters", "reason=composition happens in the controller")
    out = check_output(root, exit_code=0)
    assert out["rows"] == [] and out["covered"] == 2


def test_an_exception_with_a_rule_covers_only_rows_carrying_it(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "add-exception", "web", "ring:adapters", "rule=R4", "reason=not about construction")
    assert check_output(root)["covered"] == 0
    model_edit(root, "remove-exception", "web", "ring:adapters", "rule=R4")
    model_edit(root, "add-exception", CONTROLLER, PG, "rule=R7", "reason=one construction is tolerated")
    out = check_output(root, exit_code=1)
    assert keys(out["rows"]) == [CONSTRUCTION_ROWS[1]] and out["covered"] == 1


def test_missing_fact_is_incomplete_not_passing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(constructs=False))
    out = check_output(root, exit_code=0)
    assert out["rows"] == []
    assert [(e["check"], e["rules"]) for e in out["incomplete"]] == [("detail-constructed-outside-root", ["R7"])]
    assert "constructs" in out["incomplete"][0]["reason"]


def test_strict_fails_on_incomplete_enforced_rule(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(constructs=False))
    assert run_arch(["check", "--strict"], root).returncode == 1
    model_edit(root, "set-rule", "R7", "advisory", "reason=construction is not reported yet")
    assert run_arch(["check", "--strict"], root).returncode == 0


def test_a_rule_that_is_off_does_not_report_a_missing_fact(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(constructs=False))
    model_edit(root, "set-rule", "R7", "off", "reason=not applicable")
    assert check_output(root, exit_code=0)["incomplete"] == []


def test_touched_uncovered_file_is_incomplete(tmp_path: Path):
    root = repo(tmp_path)
    (root / "tools").mkdir()
    (root / "tools/helper.ts").write_text("export const helper = 1;\n")

    def add_module(document: dict) -> None:
        document["modules"].append({"path": "tools/helper.ts", "exports": {"abstract": 0, "concrete": 1},
                                    "implements": [], "constructs": [], "signatures": []})

    edit_json(root / ADAPTER, add_module)
    init_repo(root)
    touch(root, "tools/helper.ts")
    out = check_output(root, "--base", "HEAD")
    entries = [e for e in out["incomplete"] if e["target"] == "tools/helper.ts"]
    assert len(entries) == 1 and "arch model classify" in entries[0]["reason"]
    assert run_arch(["check", "--base", "HEAD", "--strict"], root).returncode == 1
    assert run_arch(["check", "--base", "HEAD"], root).returncode == 0


def test_without_base_any_enforced_breach_exits_1(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    assert run_arch(["check"], root).returncode == 1


def test_with_base_only_introduced_breach_exits_1(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    touch(root, CONTROLLER)
    out = check_output(root, "--base", "HEAD", exit_code=0)
    assert keys(out["rows"]) == CONSTRUCTION_ROWS and {r["origin"] for r in out["rows"]} == {"inherited"}
    seed_edge(root, EMPLOYEE, CONTROLLER)
    touch(root, EMPLOYEE)
    out = check_output(root, "--base", "HEAD", exit_code=1)
    assert find(out["rows"], f"{EMPLOYEE} -> {CONTROLLER}", "R4")["origin"] == "introduced"


def test_no_model_exits_0_with_the_baseline_line(tmp_path: Path):
    result = run_arch(["check"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "no architecture model; run a baseline audit to enable the full review"
    as_json = run_arch(["check", "--json"], tmp_path)
    assert as_json.returncode == 0 and json.loads(as_json.stdout) == {"model": False}


def test_unknown_base_exits_2_naming_it(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    result = run_arch(["check", "--base", "nope"], root)
    assert result.returncode == 2 and '"nope"' in result.stderr


def test_zone_of_pain_is_checked_only_when_the_change_touches_the_component(tmp_path: Path):
    graph = empty_graph([component("domain", 5, 0, 0, 0.1, "pain"), component("web", 0, 3, 1, 0, None)])
    assert run_checks(tmp_path, graph)["rows"] == []
    assert run_checks(tmp_path, graph, touched_scope("web"))["rows"] == []
    row = find(run_checks(tmp_path, graph, touched_scope("domain"))["rows"], "domain", "R31")
    assert row["severity"] == "major" and row["lifts"] == [] and row["rules"] == ["R31", "R32"]
    assert row["defect"] == "zone-of-pain"


def test_zone_of_pain_without_the_exports_fact_is_incomplete(tmp_path: Path):
    graph = empty_graph([component("domain", 5, 0, 0, 0.1, "pain")])
    graph["capabilities"]["exports"] = False
    out = run_checks(tmp_path, graph, touched_scope("domain"))
    assert out["rows"] == []
    assert {e["check"] for e in out["incomplete"]} == {"zone-of-pain", "unused-abstractions"}


def test_abstract_component_without_outside_consumers_is_a_minor_row(tmp_path: Path):
    graph = empty_graph([component("svc", 0, 2, 1, 0.9, "uselessness")])
    graph["units"] = [{"path": "svc/a.ts", "component": "svc", "ring": "entities", "kind": "port",
                       "exports": {"abstract": 3, "concrete": 0}}]
    row = find(run_checks(tmp_path, graph)["rows"], "svc", "R31")
    assert row["severity"] == "minor" and row["lifts"] == [] and row["defect"] == "unused-abstraction"
    assert "3 abstract exports" in row["evidence"]


def test_construction_of_a_policy_kind_is_not_a_row_under_custom_rings(tmp_path: Path):
    graph = empty_graph([])
    graph["rings"] = ["entities", "use-cases", "adapters"]
    graph["units"] = [
        {"path": "web/controller.ts", "component": None, "ring": "adapters", "kind": "controller"},
        {"path": "app/use-case.ts", "component": None, "ring": "use-cases", "kind": "use-case"},
        {"path": "db/gateway.ts", "component": None, "ring": "adapters", "kind": "gateway"},
    ]
    graph["edges"] = [
        {"from": "web/controller.ts", "to": "app/use-case.ts", "kind": "constructs", "direction": "inward"},
        {"from": "web/controller.ts", "to": "db/gateway.ts", "kind": "constructs", "direction": "same"},
    ]
    assert keys(run_checks(tmp_path, graph)["rows"]) == [("web/controller.ts -> db/gateway.ts", "R7")]


def test_construction_by_a_test_config_or_composition_root_is_not_a_row(tmp_path: Path):
    for kind in ("test", "config", "composition-root"):
        assert run_checks(tmp_path, construction_graph(kind, "adapter"))["rows"] == [], kind


def test_construction_of_a_unit_that_is_not_a_detail_kind_is_not_a_row(tmp_path: Path):
    for kind in ("mixed", "test", "config", "composition-root", "entity"):
        assert run_checks(tmp_path, construction_graph("controller", kind))["rows"] == [], kind
    rows = run_checks(tmp_path, construction_graph("controller", "gateway"))["rows"]
    assert keys(rows) == [("src/a.ts -> src/b.ts", "R7")]


def test_corrections_name_the_move(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, EMPLOYEE, CLOCK)
    seed_edge(root, "src/domain/clock.ts", CLOCK)
    rows = check_rows(root)
    ring_corrections = {r["correction"] for r in rows if "R4" in r["rules"] and r["target"].endswith(f"-> {CLOCK}")}
    assert len(ring_corrections) == 1 and CLOCK in ring_corrections.pop()
    construction = {r["correction"] for r in rows if "R7" in r["rules"]}
    assert len(construction) == 1 and CONTROLLER in construction.pop()


BARREL = "src/domain/index.ts"


def test_an_outward_edge_through_a_barrel_is_not_a_crossing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, BARREL, "src/adapters/memory-payroll-repository.ts")
    assert not any("R4" in r["rules"] and BARREL in r["target"] for r in check_rows(root))


def test_an_outward_edge_not_through_a_barrel_is_still_a_crossing(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    seed_edge(root, EMPLOYEE, "src/adapters/memory-payroll-repository.ts")
    target = f"{EMPLOYEE} -> src/adapters/memory-payroll-repository.ts"
    assert find(check_rows(root), target, "R4")["severity"] == "blocker"


def test_ring_and_construction_rows_skip_an_edge_with_a_barrel_at_either_end(tmp_path: Path):
    for constructing, constructed in (("controller", "barrel"), ("barrel", "gateway")):
        assert run_checks(tmp_path, construction_graph(constructing, constructed))["rows"] == [], (constructing, constructed)
    graph = construction_graph("entity", "barrel")
    graph["edges"] = [{"from": "src/a.ts", "to": "src/b.ts", "kind": "import", "direction": "outward"}]
    assert run_checks(tmp_path, graph)["rows"] == []


def set_exports(root: Path, exports: dict[str, tuple[int, int]]) -> None:
    def change(document: dict) -> None:
        for module in document["modules"]:
            if module["path"] in exports:
                abstract, concrete = exports[module["path"]]
                module["exports"] = {"abstract": abstract, "concrete": concrete}

    edit_json(root / ADAPTER, change)


def rename_unit(root: Path, old: str, new: str) -> None:
    git(["mv", old, new], root)

    def rename(document: dict) -> None:
        for module in document["modules"]:
            if module["path"] == old:
                module["path"] = new
        for edge in document["edges"]:
            for end in ("from", "to"):
                if edge.get(end) == old:
                    edge[end] = new
        for module in document["modules"]:
            for constructed in module["constructs"]:
                if constructed["path"] == old:
                    constructed["path"] = new

    edit_json(root / ADAPTER, rename)
    git(["add", "-A"], root)


def test_a_file_that_imported_a_detail_and_now_constructs_it_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    pristine = (root / ADAPTER).read_text()
    edit_json(root / ADAPTER, lambda d: [m.update(constructs=[]) for m in d["modules"] if m["path"] == CONTROLLER])
    init_repo(root)
    (root / ADAPTER).write_text(pristine)
    touch(root, CONTROLLER)
    out = check_output(root, "--base", "HEAD", exit_code=1)
    assert keys(out["rows"]) == CONSTRUCTION_ROWS and {r["origin"] for r in out["rows"]} == {"introduced"}


def test_moving_a_touched_component_into_the_zone_of_pain_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    set_exports(root, {"src/domain/payroll-repository.ts": (0, 1), "src/domain/clock.ts": (0, 1)})
    touch(root, EMPLOYEE)
    row = find(check_rows(root, "--base", "HEAD"), "domain", "R31")
    assert row["defect"] == "zone-of-pain" and row["origin"] == "introduced"


def test_removing_the_last_outside_consumer_of_an_abstract_component_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    set_exports(root, {"src/adapters/memory-payroll-repository.ts": (1, 0)})
    init_repo(root)
    def cut_consumers(document: dict) -> None:
        document["edges"] = [e for e in document["edges"]
                             if not (e["from"] == CONTROLLER and str(e.get("to", "")).startswith("src/adapters/"))]
        for module in document["modules"]:
            if module["path"] == CONTROLLER:
                module["constructs"] = []

    edit_json(root / ADAPTER, cut_consumers)
    touch(root, CLOCK)
    row = find(check_rows(root, "--base", "HEAD"), "adapters", "R31")
    assert row["defect"] == "unused-abstraction" and row["origin"] == "introduced"


def test_a_unit_moved_so_an_import_becomes_policy_to_detail_is_introduced(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    moved = "src/domain/payroll-controller-use-case.ts"
    rename_unit(root, CONTROLLER, moved)
    rows = check_rows(root, "--base", "HEAD")
    assert find(rows, f"{moved} -> {PG}", "R4")["origin"] == "introduced"


def test_a_renamed_file_with_an_unchanged_construction_breach_is_inherited(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    renamed = "src/web/pay-controller.ts"
    rename_unit(root, CONTROLLER, renamed)
    out = check_output(root, "--base", "HEAD", exit_code=0)
    assert keys(out["rows"]) == [(f"{renamed} -> {PG}", "R7"), (f"{renamed} -> {CLOCK}", "R7")]
    assert {r["origin"] for r in out["rows"]} == {"inherited"}


def test_rows_that_describe_the_change_are_always_introduced(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    touch(root, EMPLOYEE, MAIN)
    assert {r["origin"] for r in check_rows(root, "--base", "HEAD") if "R28" in r["rules"]} == {"introduced"}
    model_edit(root, "add-group", "split", "members=domain", "absorbs=domain only")
    rows = [r for r in check_rows(root, "--base", "HEAD") if "R27" in r["rules"]]
    assert rows and {r["origin"] for r in rows} == {"introduced"}


def test_a_merged_row_is_introduced_when_any_contributing_row_is(tmp_path: Path):
    script = (
        f"import {{ mergeRows }} from {json.dumps(RUN_MODULE)};"
        "const row = (rule, origin) => ({ check: rule, defect: 'd', rules: [rule], severity: 'major', target: 't',"
        " evidence: rule, correction: 'c', units: [], components: [], origin });"
        "console.log(JSON.stringify([mergeRows([row('R4', 'inherited'), row('R17', 'introduced')])[0].origin,"
        " mergeRows([row('R4', 'inherited'), row('R17', 'inherited')])[0].origin]));"
    )
    result = run_node(script, tmp_path)
    assert json.loads(result.stdout) == ["introduced", "inherited"]


def test_a_check_runs_when_a_rule_is_off_for_the_project_but_enforced_for_a_component(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    model_edit(root, "set-rule", "R7", "off", "reason=not applicable")
    model_edit(root, "set-rule", "R7@web", "enforced", "reason=the web component must stay clean")
    out = check_output(root, exit_code=1)
    assert keys(out["rows"]) == CONSTRUCTION_ROWS and {r["status"] for r in out["rows"]} == {"enforced"}


def test_checks_that_need_a_base_are_listed_as_not_run_without_one(tmp_path: Path):
    root = repo(tmp_path)
    init_repo(root)
    out = check_output(root)
    assert [(e["check"], e["rules"]) for e in out["notRun"]] == [
        ("zone-of-pain", ["R31", "R32"]), ("no-cohesion-groups", ["R28"]), ("change-spans-groups", ["R27"])]
    assert out["incomplete"] == []
    text = run_arch(["check"], root).stdout
    assert "## Not run without --base\n\n- zone-of-pain (R31 Depend toward stability; R32 Use metrics as a screen)" in text
    assert check_output(root, "--base", "HEAD")["notRun"] == []


def test_every_uncovered_unit_is_incomplete_without_a_base(tmp_path: Path):
    root = repo(tmp_path)

    def add_module(document: dict) -> None:
        document["modules"].append({"path": "tools/helper.ts", "exports": {"abstract": 0, "concrete": 1},
                                    "implements": [], "constructs": [], "signatures": []})

    edit_json(root / ADAPTER, add_module)
    out = check_output(root)
    assert [e["target"] for e in out["incomplete"]] == ["tools/helper.ts"]
    assert run_arch(["check", "--strict"], root).returncode == 1


def test_a_unit_without_exports_makes_the_abstractness_checks_incomplete(tmp_path: Path):
    graph = empty_graph([component("svc", 0, 2, 1, None, None)])
    graph["units"] = [{"path": "svc/a.ts", "component": "svc", "ring": "entities", "kind": "port", "exports": None}]
    out = run_checks(tmp_path, graph, touched_scope("svc"))
    assert out["rows"] == []
    assert {(e["check"], e["target"]) for e in out["incomplete"]} == {
        ("zone-of-pain", "svc/a.ts"), ("unused-abstractions", "svc/a.ts")}
