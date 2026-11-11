import json
from pathlib import Path

from support import copy_fixture, git, init_repo, run_arch

MODEL = "docs/architecture/architecture.json"
ADAPTER = "adapter.json"
OLD_DATE = {"GIT_COMMITTER_DATE": "2020-01-01T00:00:00", "GIT_AUTHOR_DATE": "2020-01-01T00:00:00"}


def edit_json(path: Path, change) -> None:
    document = json.loads(path.read_text())
    change(document)
    path.write_text(json.dumps(document))


def payroll(tmp_path: Path) -> Path:
    return copy_fixture("payroll", tmp_path / "p")


def q(root: Path, *args: str) -> dict:
    result = run_arch(["query", *args, "--json"], root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def add_module(root: Path, path: str, abstract: int = 0, concrete: int = 1) -> None:
    module = {"path": path, "exports": {"abstract": abstract, "concrete": concrete},
              "implements": [], "constructs": [], "signatures": []}
    edit_json(root / ADAPTER, lambda d: d["modules"].append(module))


def test_metrics_table(tmp_path: Path):
    out = q(payroll(tmp_path), "metrics")
    assert out["columns"] == ["Component", "Units", "Fan-in", "Fan-out", "I", "A", "D", "Zone"]
    domain = next(r for r in out["rows"] if r[0] == "domain")
    assert domain[1:] == [5, 4, 0, 0, 0.5, 0.5, "none"]


def test_component_graph_lists_component_pairs_by_name(tmp_path: Path):
    out = q(payroll(tmp_path), "component-graph")
    assert out["columns"] == ["From", "To", "Importing modules"]
    assert out["rows"] == [["adapters", "domain", 3], ["web", "adapters", 1], ["web", "domain", 1]]


def test_ring_crossings_outward_is_empty_and_inward_lists_edges(tmp_path: Path):
    root = payroll(tmp_path)
    assert q(root, "ring-crossings")["rows"] == []
    inward = q(root, "ring-crossings", "--direction", "inward")["rows"]
    row = ["src/adapters/pg-payroll-repository.ts", "adapters", "src/domain/payroll-repository.ts", "entities",
           "type-import"]
    assert row in inward


def test_fan_in_and_units(tmp_path: Path):
    root = payroll(tmp_path)
    importers = {r[0] for r in q(root, "fan-in", "src/domain/clock.ts")["rows"]}
    assert importers == {"src/domain/payroll-use-case.ts", "src/domain/index.ts"}
    ports = {r[0] for r in q(root, "units", "--component", "domain", "--kind", "port")["rows"]}
    assert ports == {"src/domain/clock.ts", "src/domain/payroll-repository.ts"}


def test_ports_derive_implementers_and_consumers(tmp_path: Path):
    out = q(payroll(tmp_path), "ports")
    assert out["columns"] == ["Port", "Owner", "Humble side", "Implementers", "Consumers (by component)"]
    repository = next(r for r in out["rows"] if r[0] == "src/domain/payroll-repository.ts:PayrollRepository")
    assert repository[1] == "domain" and repository[2] == "adapters"
    assert repository[3] == "src/adapters/memory-payroll-repository.ts, src/adapters/pg-payroll-repository.ts"
    assert repository[4] == "adapters (1)"
    clock = next(r for r in out["rows"] if r[0] == "src/domain/clock.ts:Clock")
    assert clock[3] == "src/adapters/system-clock.ts" and clock[4] == ""


def test_touched_lists_changed_units_with_neighbors(tmp_path: Path):
    root = payroll(tmp_path)
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(root, "touched", "--base", "HEAD")
    row = next(r for r in out["rows"] if r[0] == "src/domain/employee.ts")
    assert row[4] == "modified"
    assert "src/domain/payroll-use-case.ts" in row[5]


def test_volatility_with_since_counts_commits_per_component(tmp_path: Path):
    root = payroll(tmp_path)
    init_repo(root)
    base = git(["rev-parse", "HEAD"], root).stdout.strip()
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export {};\n")
    git(["commit", "-qam", "touch web"], root)
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export const x = 1;\n")
    git(["commit", "-qam", "touch web again"], root)
    out = q(root, "volatility", "--since", base)
    assert out["columns"] == ["Component", "Commits", "Modules touched"]
    assert ["web", 2, 1] in out["rows"]


def history_in_two_eras(root: Path) -> None:
    git(["init", "-q", "-b", "main"], root)
    git(["add", "-A"], root)
    git(["commit", "-q", "-m", "fixture"], root, env=OLD_DATE)
    (root / "src/web/main.ts").write_text("import './payroll-controller.js'; export {};\n")
    git(["commit", "-qam", "touch web"], root)


def test_volatility_defaults_to_the_history_window(tmp_path: Path):
    root = payroll(tmp_path)
    history_in_two_eras(root)
    rows = q(root, "volatility")["rows"]
    assert ["web", 1, 1] in rows and ["domain", 0, 0] in rows


def test_volatility_uses_the_history_window_knob(tmp_path: Path):
    root = payroll(tmp_path)
    history_in_two_eras(root)
    edit_json(root / MODEL, lambda d: d.update(thresholds={"historyWindow": "30 years"}))
    rows = q(root, "volatility")["rows"]
    assert ["web", 2, 3] in rows and ["domain", 1, 5] in rows


def test_uncovered_exit_code(tmp_path: Path):
    root = payroll(tmp_path)
    assert run_arch(["uncovered"], root).returncode == 0
    add_module(root, "src/scripts/seed.ts")
    (root / "src/scripts").mkdir()
    (root / "src/scripts/seed.ts").write_text("export const s = 1;\n")
    result = run_arch(["uncovered"], root)
    assert result.returncode == 1 and result.stdout.strip() == "src/scripts/seed.ts"
    as_json = run_arch(["uncovered", "--json"], root)
    assert json.loads(as_json.stdout) == ["src/scripts/seed.ts"]


def test_touched_from_a_subdirectory_root_uses_relative_paths(tmp_path: Path):
    repo = tmp_path / "repo"
    sub = repo / "sub"
    copy_fixture("payroll", sub)
    init_repo(repo)
    (sub / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    row = next(r for r in q(sub, "touched", "--base", "HEAD")["rows"] if r[0] == "src/domain/employee.ts")
    assert row[4] == "modified"


def test_touched_without_base_prints_usage(tmp_path: Path):
    result = run_arch(["query", "touched"], payroll(tmp_path))
    assert result.returncode == 2
    assert result.stderr.strip() == "usage: arch query touched --base <ref>"


def test_edges_without_path_prints_usage(tmp_path: Path):
    result = run_arch(["query", "edges"], payroll(tmp_path))
    assert result.returncode == 2
    assert result.stderr.strip() == "usage: arch query edges <path> | --kind <kind>"


def test_signatures_without_path_prints_usage(tmp_path: Path):
    result = run_arch(["query", "signatures"], payroll(tmp_path))
    assert result.returncode == 2
    assert result.stderr.strip() == "usage: arch query signatures <path>"


def test_markdown_rendering(tmp_path: Path):
    result = run_arch(["query", "metrics"], payroll(tmp_path))
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "| Component | Units | Fan-in | Fan-out | I | A | D | Zone |"
    assert lines[1] == "|---|---|---|---|---|---|---|---|"
    assert any(line.startswith("| domain | 5 | 4 | 0 | 0 | 0.5 | 0.5 | none |") for line in lines)


def test_entry_point_globs_expand_to_one_row_per_unit(tmp_path: Path):
    root = payroll(tmp_path)
    web = lambda d: next(c for c in d["components"] if c["name"] == "web").update(entry=["*.ts"])
    edit_json(root / MODEL, web)
    assert q(root, "entry-points")["rows"] == [
        ["src/web/main.ts", "web", ["src/web/payroll-controller.ts"]],
        ["src/web/payroll-controller.ts", "web",
         ["src/adapters/pg-payroll-repository.ts", "src/adapters/system-clock.ts", "src/domain/payroll-use-case.ts"]],
    ]


def test_externals_query_lists_importers_by_component(tmp_path: Path):
    root = payroll(tmp_path)
    assert ["pg", "vendor", ["adapters"], ["src/adapters/pg-payroll-repository.ts"]] in q(root, "externals")["rows"]
    assert all(r[1] == "vendor" for r in q(root, "externals", "--tag", "vendor")["rows"])


def test_cycles_query_lists_module_and_component_cycles(tmp_path: Path):
    root = payroll(tmp_path)
    assert q(root, "cycles")["rows"] == []
    edge = {"from": "src/domain/employee.ts", "to": "src/web/payroll-controller.ts", "kind": "import"}
    edit_json(root / ADAPTER, lambda d: d["edges"].append(edge))
    rows = q(root, "cycles")["rows"]
    assert ["component", ["adapters", "domain", "web"]] in rows
    assert any(r[0] == "module" and "src/domain/employee.ts" in r[1] for r in rows)


def test_edges_query_lists_outgoing_and_incoming_edges(tmp_path: Path):
    root = payroll(tmp_path)
    out = q(root, "edges", "src/domain/clock.ts")
    assert out["columns"] == ["Direction", "Other", "Kind", "Ring direction"]
    assert sorted(out["rows"]) == [
        ["in", "src/domain/index.ts", "import", "through-barrel"],
        ["in", "src/domain/payroll-use-case.ts", "import", "inward"],
    ]
    rows = q(root, "edges", "src/web/payroll-controller.ts")["rows"]
    assert ["out", "src/domain/payroll-use-case.ts", "import", "inward"] in rows
    assert ["in", "src/web/main.ts", "import", "inward"] in rows


def test_boolean_flags_never_consume_the_next_argument(tmp_path: Path):
    result = run_arch(["query", "fan-in", "--json", "src/domain/clock.ts"], payroll(tmp_path))
    assert result.returncode == 0, result.stderr
    importers = {r[0] for r in json.loads(result.stdout)["rows"]}
    assert importers == {"src/domain/payroll-use-case.ts", "src/domain/index.ts"}


def test_null_cells_render_empty_except_metric_columns(tmp_path: Path):
    root = payroll(tmp_path)
    island = {"name": "island", "paths": ["src/island/**"], "classify": [["**", "entity"]]}
    edit_json(root / MODEL, lambda d: d["components"].append(island))
    metrics = run_arch(["query", "metrics"], root)
    assert "| island | 0 | 0 | 0 | not defined | not defined | not defined | none |" in metrics.stdout.splitlines()
    ports = run_arch(["query", "ports"], root)
    clock = next(line for line in ports.stdout.splitlines() if line.startswith("| src/domain/clock.ts:Clock"))
    assert clock.startswith("| src/domain/clock.ts:Clock | domain |  | ")
    assert "not defined" not in ports.stdout
    as_json = q(root, "metrics")
    assert set(as_json) == {"columns", "rows"}
    assert next(r for r in as_json["rows"] if r[0] == "island")[4:7] == [None, None, None]


def test_touched_lists_untracked_units_and_skips_deleted_non_units(tmp_path: Path):
    root = payroll(tmp_path)
    (root / "src/domain/notes.md").write_text("notes\n")
    init_repo(root)
    (root / "src/domain/notes.md").unlink()
    (root / "src/domain/payslip.ts").write_text("export class Payslip {}\n")
    add_module(root, "src/domain/payslip.ts")
    changes = {r[0]: r[4] for r in q(root, "touched", "--base", "HEAD")["rows"]}
    assert changes.get("src/domain/payslip.ts") == "added"
    assert "src/domain/notes.md" not in changes


def test_touched_lists_a_deleted_unit(tmp_path: Path):
    root = payroll(tmp_path)
    init_repo(root)
    (root / "src/web/main.ts").unlink()
    edit_json(root / ADAPTER, lambda d: d.update(modules=[m for m in d["modules"] if m["path"] != "src/web/main.ts"]))
    rows = q(root, "touched", "--base", "HEAD")["rows"]
    assert ["src/web/main.ts", "web", "composition-root", "frameworks", "deleted", ""] in rows


def test_ring_crossings_same_lists_edges_within_one_ring(tmp_path: Path):
    root = payroll(tmp_path)
    rows = q(root, "ring-crossings", "--direction", "same")["rows"]
    assert sorted(rows) == [
        ["src/domain/payroll-repository.ts", "entities", "src/domain/employee.ts", "entities", "type-import"],
        ["src/web/legacy-router.js", "adapters", "src/web/payroll-controller.ts", "adapters", "import"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/pg-payroll-repository.ts", "adapters", "constructs"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/pg-payroll-repository.ts", "adapters", "import"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/system-clock.ts", "adapters", "constructs"],
        ["src/web/payroll-controller.ts", "adapters", "src/adapters/system-clock.ts", "adapters", "import"],
    ]


def test_touched_with_neighbors_adds_untouched_neighbor_unit_rows(tmp_path: Path):
    root = payroll(tmp_path)
    init_repo(root)
    (root / "src/domain/employee.ts").write_text("export class Employee { name = 'x'; }\n")
    out = q(root, "touched", "--base", "HEAD", "--with-neighbors")
    assert set(out) == {"touched", "neighbors"}
    assert [r[0] for r in out["touched"]["rows"]] == ["src/domain/employee.ts"]
    assert out["neighbors"]["columns"] == ["Path", "Component", "Kind", "Ring", "Actors", "Abstract", "Concrete"]
    assert [r[0] for r in out["neighbors"]["rows"]] == [
        "src/adapters/memory-payroll-repository.ts", "src/adapters/pg-payroll-repository.ts",
        "src/domain/index.ts", "src/domain/payroll-repository.ts", "src/domain/payroll-use-case.ts"]
    assert out["neighbors"]["rows"][4][1:4] == ["domain", "use-case", "use-cases"]
    markdown = run_arch(["query", "touched", "--base", "HEAD", "--with-neighbors"], root).stdout
    assert "| Path | Component | Kind | Ring | Change | Neighbors |" in markdown
    assert "| Path | Component | Kind | Ring | Actors | Abstract | Concrete |" in markdown


def test_groups_query_lists_groups_added_to_the_model(tmp_path: Path):
    root = payroll(tmp_path)
    assert q(root, "groups")["rows"] == []
    group = {"name": "core", "members": ["domain", "adapters"], "absorbs": "domain rule changes"}
    edit_json(root / MODEL, lambda d: d.update(groups=[group]))
    out = q(root, "groups")
    assert out["columns"] == ["Group", "Members", "Absorbs"]
    assert out["rows"] == [["core", ["domain", "adapters"], "domain rule changes"]]


def test_components_query_lists_the_component_record(tmp_path: Path):
    out = q(payroll(tmp_path), "components")
    assert out["columns"] == ["Component", "Enforcement", "Release", "Entry points", "Published", "Units"]
    assert out["rows"] == [
        ["domain", "boundary-lint", "", [], [], 5],
        ["adapters", "boundary-lint", "", [], [], 3],
        ["web", "boundary-lint", "", ["main.ts"], [], 3],
    ]


def test_edges_by_kind_without_a_path_lists_every_edge_of_that_kind(tmp_path: Path):
    out = q(payroll(tmp_path), "edges", "--kind", "constructs")
    assert out["columns"] == ["From", "To", "Kind", "Ring direction"]
    assert [r[:2] for r in out["rows"]] == [
        ["src/web/payroll-controller.ts", "src/adapters/pg-payroll-repository.ts"],
        ["src/web/payroll-controller.ts", "src/adapters/system-clock.ts"],
        ["src/web/payroll-controller.ts", "src/domain/payroll-use-case.ts"],
    ]
    assert {r[2] for r in out["rows"]} == {"constructs"}


BARREL = "src/domain/index.ts"


def test_barrel_edges_are_through_barrel(tmp_path: Path):
    rows = q(payroll(tmp_path), "edges", BARREL)["rows"]
    assert sorted(rows) == [
        ["in", "src/adapters/system-clock.ts", "type-import", "through-barrel"],
        ["out", "src/domain/clock.ts", "import", "through-barrel"],
        ["out", "src/domain/employee.ts", "import", "through-barrel"],
        ["out", "src/domain/payroll-repository.ts", "import", "through-barrel"],
        ["out", "src/domain/payroll-use-case.ts", "import", "through-barrel"],
    ]


def test_ring_crossings_leave_out_barrel_edges(tmp_path: Path):
    root = payroll(tmp_path)
    for direction in ("outward", "inward", "same"):
        rows = q(root, "ring-crossings", "--direction", direction)["rows"]
        assert not any(BARREL in (r[0], r[2]) for r in rows), direction


def test_ring_crossings_include_barrel_edges_by_their_rings_when_asked(tmp_path: Path):
    root = payroll(tmp_path)
    assert q(root, "ring-crossings", "--include-barrels")["rows"] == [
        [BARREL, "entities", "src/domain/payroll-use-case.ts", "use-cases", "import"],
    ]
    inward = q(root, "ring-crossings", "--include-barrels", "--direction", "inward")["rows"]
    assert ["src/adapters/system-clock.ts", "adapters", BARREL, "entities", "type-import"] in inward


def test_signatures_lists_types_named_in_the_public_interface(tmp_path: Path):
    out = q(payroll(tmp_path), "signatures", "src/domain/payroll-use-case.ts")
    assert out["columns"] == ["Symbol", "Type", "From"]
    assert ["PayrollUseCase", "PayrollRepository", "src/domain/payroll-repository.ts"] in out["rows"]


def test_a_fact_the_adapter_did_not_provide_is_reported_not_failed(tmp_path: Path):
    root = payroll(tmp_path)
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(signatures=False))
    result = run_arch(["query", "signatures", "src/domain/payroll-use-case.ts"], root)
    assert result.returncode == 0 and result.stdout.strip() == "not provided by the adapter"
    as_json = json.loads(run_arch(["query", "signatures", "src/domain/payroll-use-case.ts", "--json"], root).stdout)
    assert as_json == {"notProvided": "signatures"}


def test_implementers_cell_says_when_the_adapter_gave_no_implements_fact(tmp_path: Path):
    root = payroll(tmp_path)
    edit_json(root / ADAPTER, lambda d: d["capabilities"].update(implements=False))
    clock = next(r for r in q(root, "ports")["rows"] if r[0] == "src/domain/clock.ts:Clock")
    assert clock[3] == "not provided by the adapter"


def test_query_and_uncovered_without_a_model_say_how_to_make_one(tmp_path: Path):
    root = payroll(tmp_path)
    (root / MODEL).unlink()
    for args in (["query", "metrics"], ["uncovered"]):
        result = run_arch(args, root)
        assert result.returncode == 2 and "arch model init" in result.stderr


def test_unknown_query_and_unknown_flag_are_usage_errors(tmp_path: Path):
    root = payroll(tmp_path)
    unknown = run_arch(["query", "nonsense"], root)
    assert unknown.returncode == 2 and "metrics" in unknown.stderr
    flag = run_arch(["query", "metrics", "--bse", "main"], root)
    assert flag.returncode == 2 and "--bse" in flag.stderr
    assert run_arch(["query"], root).returncode == 2


def test_a_query_refuses_a_flag_it_does_not_take_and_lists_the_ones_it_takes(tmp_path: Path):
    root = payroll(tmp_path)
    result = run_arch(["query", "metrics", "--kind", "port"], root)
    assert result.returncode == 2 and "--kind" in result.stderr and "metrics" in result.stderr
    result = run_arch(["query", "units", "--tag", "x"], root)
    assert result.returncode == 2
    for accepted in ("--component", "--kind", "--ring"):
        assert accepted in result.stderr
    assert run_arch(["query", "units", "--kind", "port"], root).returncode == 0
