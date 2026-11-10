import json
from pathlib import Path

from support import SKILL_DIR, copy_fixture, run_node

LIB = SKILL_DIR / "scripts" / "lib" / "model"


def node_json(body: str, cwd: Path):
    script = (
        f"import {{ loadModel }} from '{(LIB / 'load.mjs').as_posix()}';"
        f"import {{ createClassifier }} from '{(LIB / 'classify.mjs').as_posix()}';"
        "const out = async (value) => process.stdout.write(JSON.stringify(value ?? null));"
        "const refused = async (run) => { try { await run(); } catch (error) {"
        " return { name: error.constructor.name, exitCode: error.exitCode, message: error.message }; } };"
        f"{body}"
    )
    result = run_node(script, cwd)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def payroll(tmp_path: Path) -> Path:
    return copy_fixture("payroll", tmp_path / "p")


def write_model(root: Path, mutate) -> None:
    path = root / "docs/architecture/architecture.json"
    model = json.loads(path.read_text())
    mutate(model)
    path.write_text(json.dumps(model))


def classify(root: Path, *paths: str):
    body = (
        "const model = await loadModel(process.cwd(), {});"
        f"const classify = createClassifier(model); await out({list(paths)!r}.map(classify));"
    )
    return node_json(body, root)


def load_error(root: Path):
    return node_json("await out(await refused(() => loadModel(process.cwd(), {})));", root)


def test_payroll_model_loads_with_defaults(tmp_path: Path):
    root = payroll(tmp_path)
    model = node_json("await out(await loadModel(process.cwd(), {}));", root)
    assert model["thresholds"]["escalationFanIn"] == 3
    assert model["rules"] == {"R6": {"status": "off", "reason": "one delivery mechanism; controllers call use cases directly"}}
    assert model["rings"] == ["entities", "use-cases", "adapters", "frameworks"]
    assert model["components"][0]["classify"][0] == {"pattern": "**/*-use-case.ts", "kind": "use-case", "valueType": False}
    assert model["ports"][1] == {"at": "src/domain/clock.ts#Clock", "path": "src/domain/clock.ts", "symbol": "Clock", "owner": "domain"}


def test_missing_model_returns_null(tmp_path: Path):
    assert node_json("await out(await loadModel(process.cwd(), {}));", tmp_path) is None


def test_record_flag_and_environment_choose_the_directory(tmp_path: Path):
    root = payroll(tmp_path)
    (root / "alt").mkdir()
    (root / "docs/architecture/architecture.json").rename(root / "alt/architecture.json")
    assert node_json("await out(await loadModel(process.cwd(), {}));", root) is None
    found = node_json("await out((await loadModel(process.cwd(), { record: 'alt' })).version);", root)
    assert found == 2


def test_kind_implies_ring(tmp_path: Path):
    result = classify(payroll(tmp_path), "src/domain/employee.ts")[0]
    assert result["kind"] == "entity" and result["ring"] == "entities" and result["component"] == "domain"


def test_pattern_is_relative_to_the_component(tmp_path: Path):
    root = payroll(tmp_path)
    inside, elsewhere = classify(root, "src/domain/clock.ts", "src/domain/nested/clock.ts")
    assert inside["kind"] == "port"
    assert elsewhere["kind"] == "entity"


def test_first_matching_pair_wins(tmp_path: Path):
    result = classify(payroll(tmp_path), "src/domain/index.ts")[0]
    assert result["kind"] == "barrel" and result["matched"] == {"component": "domain", "index": 3}


def test_unstated_actors_are_unknown(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][0]["classify"].insert(0, ["finance.ts", "entity", {"actors": ["finance"]}]))
    stated, unstated = classify(root, "src/domain/finance.ts", "src/domain/employee.ts")
    assert stated["actors"] == ["finance"]
    assert unstated["actors"] is None


def test_unclassified_path_returns_nulls(tmp_path: Path):
    result = classify(payroll(tmp_path), "scripts/build.ts")[0]
    assert result == {"component": None, "kind": None, "ring": None, "actors": None, "matched": None}


def test_explicit_ring_overrides_the_kind_default(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][1]["classify"].insert(0, ["odd.ts", "adapter", {"ring": "frameworks"}]))
    assert classify(root, "src/adapters/odd.ts")[0]["ring"] == "frameworks"


def test_unknown_rule_key_is_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["rules"].update({"R99": ["off", "no such rule"]}))
    error = load_error(root)
    assert error["name"] == "ModelError" and error["exitCode"] == 2
    assert "rules.R99" in error["message"] and "R1 to R41" in error["message"]


def test_rule_for_unknown_component_is_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["rules"].update({"R6@nowhere": ["off", "x"]}))
    assert "rules.R6@nowhere" in load_error(root)["message"]


def test_component_scoped_rule_is_normalized(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["rules"].update({"R6@web": ["advisory", "migrating"]}))
    model = node_json("await out(await loadModel(process.cwd(), {}));", root)
    assert model["rules"]["R6@web"] == {"status": "advisory", "reason": "migrating", "component": "web"}


def test_unknown_threshold_is_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m.update({"thresholds": {"distanceMaxx": 1}}))
    message = load_error(root)["message"]
    assert "thresholds.distanceMaxx" in message and "distanceMax" not in message.replace("distanceMaxx", "")
    assert "painMinFanIn" in message


def test_threshold_overrides_one_default(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m.update({"thresholds": {"escalationFanIn": 5}}))
    thresholds = node_json("await out((await loadModel(process.cwd(), {})).thresholds);", root)
    assert thresholds["escalationFanIn"] == 5 and thresholds["planFixRounds"] == 2


def test_custom_kind_declares_role_and_ring(tmp_path: Path):
    root = payroll(tmp_path)

    def add(model):
        model["kinds"] = {"saga": {"role": "policy", "ring": "use-cases"}}
        model["components"][0]["classify"].insert(0, ["**/*-saga.ts", "saga"])

    write_model(root, add)
    assert classify(root, "src/domain/pay-saga.ts")[0]["ring"] == "use-cases"


def test_unknown_kind_in_a_pair_is_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][0]["classify"].insert(0, ["x.ts", "saga"]))
    message = load_error(root)["message"]
    assert "components[0].classify[0]" in message and "saga" in message


def test_barrel_without_derivable_ring_is_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][0]["classify"].__setitem__(3, ["index.ts", "barrel"]))
    assert "ring" in load_error(root)["message"]


def test_barrel_takes_the_single_ring_of_its_siblings(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][1]["classify"].insert(0, ["index.ts", "barrel"]))
    assert classify(root, "src/adapters/index.ts")[0]["ring"] == "adapters"


def test_duplicate_component_names_are_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][1].update({"name": "domain"}))
    assert "duplicate component name" in load_error(root)["message"]


def test_port_owner_must_be_a_component(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["ports"][0].update({"owner": "ghost"}))
    assert "ports[0].owner" in load_error(root)["message"]


def test_group_members_must_be_components(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m.update({"groups": [{"name": "core", "members": ["domain", "ghost"]}]}))
    assert "groups[0].members" in load_error(root)["message"]


def test_overlapping_component_paths_are_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][1].update({"paths": ["src/**"]}))
    assert "overlap" in load_error(root)["message"]


def test_identical_component_globs_are_refused(tmp_path: Path):
    root = payroll(tmp_path)
    write_model(root, lambda m: m["components"][1].update({"paths": ["src/domain/*.ts"]}) or
                m["components"][0].update({"paths": ["src/domain/*.ts"]}))
    assert "overlap" in load_error(root)["message"]


def test_every_schema_problem_is_listed(tmp_path: Path):
    root = payroll(tmp_path)

    def break_it(model):
        model["adapter"] = 3
        model["components"][0]["paths"] = "src"

    write_model(root, break_it)
    message = load_error(root)["message"]
    assert "adapter" in message and "components[0].paths" in message


def test_invalid_json_is_a_model_error(tmp_path: Path):
    root = payroll(tmp_path)
    (root / "docs/architecture/architecture.json").write_text("{nope")
    error = load_error(root)
    assert error["name"] == "ModelError" and "architecture.json" in error["message"]


def test_defaults_module_exposes_the_documented_values(tmp_path: Path):
    body = (
        f"import * as d from '{(LIB / 'defaults.mjs').as_posix()}';"
        "await out({ rings: d.DEFAULT_RINGS, entity: d.DEFAULT_KINDS.entity, barrel: d.DEFAULT_KINDS.barrel,"
        " thresholds: d.DEFAULT_THRESHOLDS, greenfield: d.DEFAULT_STATUSES.greenfield, legacy: d.DEFAULT_STATUSES.legacy });"
    )
    out = node_json(body, tmp_path)
    assert out["entity"] == {"role": "policy", "ring": "entities"}
    assert out["barrel"]["role"] == "neutral"
    assert out["thresholds"]["historyWindow"] == "6 months" and out["thresholds"]["painMaxInstability"] == 0.2
    assert out["greenfield"]["R3"] == "advisory" and out["greenfield"]["R6"] == "enforced"
    assert out["legacy"]["R6"] == "advisory" and out["legacy"]["R22"] == "advisory" and out["legacy"]["R1"] == "enforced"


def test_model_template_loads(tmp_path: Path):
    target = tmp_path / "docs/architecture"
    target.mkdir(parents=True)
    (target / "architecture.json").write_text((SKILL_DIR / "assets" / "architecture.json").read_text())
    assert classify(tmp_path, "src/domain/a.ts")[0]["ring"] == "entities"
