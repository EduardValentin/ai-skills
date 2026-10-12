import json
from pathlib import Path

import pytest

from support import SKILL_DIR, copy_fixture, run_node

ADAPTER = SKILL_DIR / "scripts" / "lib" / "adapters" / "typescript.mjs"


def test_normalize_cruise_classifies_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    script = (f"import {{ normalizeCruise }} from '{ADAPTER.as_posix()}';import {{ readFile }} from 'node:fs/promises';"
              "const j = JSON.parse(await readFile('cruise.json','utf8'));const n = normalizeCruise(j, ['express']);"
              "process.stdout.write(JSON.stringify({modules:[...n.modules].sort(), edges:n.edges}));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "src/domain/payroll-use-case.ts" in out["modules"]
    internal = {(e["from"], e["to"], e["kind"]) for e in out["edges"] if "to" in e}
    assert ("src/web/payroll-controller.ts", "src/domain/payroll-use-case.ts", "import") in internal
    assert ("src/adapters/system-clock.ts", "src/domain/clock.ts", "type-import") in internal
    externals = {(e["from"], e["external"]["name"], e["external"]["tag"]) for e in out["edges"] if "external" in e}
    assert ("src/web/payroll-controller.ts", "express", "framework") in externals
    assert ("src/adapters/pg-payroll-repository.ts", "pg", "vendor") in externals


def test_normalize_cruise_treats_npm_dev_and_node_modules_entries_as_external():
    cruise = {
        "modules": [
            {
                "source": "src/a.ts",
                "dependencies": [
                    {"module": "x", "resolved": "node_modules/x/index.js", "dependencyTypes": ["npm-dev", "import"], "dynamic": False, "couldNotResolve": False},
                ],
            },
            {"source": "node_modules/x/index.js", "dependencies": []},
        ],
    }
    script = (f"import {{ normalizeCruise }} from '{ADAPTER.as_posix()}';"
              f"const n = normalizeCruise({json.dumps(cruise)}, []);"
              "process.stdout.write(JSON.stringify({modules:[...n.modules].sort(), edges:n.edges}));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "node_modules/x/index.js" not in out["modules"]
    assert "src/a.ts" in out["modules"]
    externals = [e for e in out["edges"] if "external" in e]
    assert externals == [{"from": "src/a.ts", "external": {"name": "x", "tag": "vendor"}}]
    assert not any(e.get("to") == "node_modules/x/index.js" for e in out["edges"])


def test_extract_uses_saved_cruise_and_counts_exports(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    has_ts = run_node("import {createRequire} from 'node:module';try{createRequire(process.cwd()+'/x.js').resolve('typescript');process.stdout.write('yes')}catch{process.stdout.write('no')}", root).stdout == "yes"
    if not has_ts:
        pytest.skip("typescript not resolvable from the fixture")
    script = (f"import {{ createTypescriptAdapter }} from '{ADAPTER.as_posix()}';"
              "const a = createTypescriptAdapter({root: process.cwd(), tooling: {language:'typescript', roots:['src']}});"
              "const r = await a.extract({roots:['src'], cruiseJsonPath:'cruise.json'});process.stdout.write(JSON.stringify(r));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    by_path = {m["path"]: m for m in out["modules"]}
    assert by_path["src/domain/clock.ts"]["exports"] == {"abstract": 1, "concrete": 0}
    assert by_path["src/domain/employee.ts"]["exports"] == {"abstract": 0, "concrete": 1}
    assert by_path["src/adapters/system-clock.ts"]["implements"] == ["Clock"]


def test_missing_typescript_is_a_clear_error(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    script = (f"import {{ createTypescriptAdapter }} from '{ADAPTER.as_posix()}';"
              "const a = createTypescriptAdapter({root: '/nonexistent-root', tooling: {language:'typescript', roots:['src']}});"
              "try { await a.extract({roots:['src'], cruiseJsonPath: process.cwd()+'/cruise.json'}); } catch (e) { process.stdout.write(e.message); }")
    result = run_node(script, root)
    assert "typescript is not installed in /nonexistent-root" in result.stdout


def _locate(root: Path) -> "subprocess.CompletedProcess[str]":
    script = (f"import {{ locateCruiserBin }} from '{ADAPTER.as_posix()}';"
              f"try {{ process.stdout.write(await locateCruiserBin({json.dumps(str(root))})); }}"
              "catch (e) { process.stderr.write('ERR:' + e.message); }")
    return run_node(script, root)


def test_locate_cruiser_bin_prefers_the_bin_shim(tmp_path: Path):
    shim = tmp_path / "node_modules/.bin/depcruise"
    shim.parent.mkdir(parents=True)
    shim.write_text("")
    result = _locate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(shim)


def test_locate_cruiser_bin_walks_up_from_the_resolved_main_entry(tmp_path: Path):
    pkg_dir = tmp_path / "node_modules/dependency-cruiser"
    (pkg_dir / "src/main").mkdir(parents=True)
    (pkg_dir / "src/main/index.mjs").write_text("")
    (pkg_dir / "package.json").write_text(json.dumps({
        "name": "dependency-cruiser",
        "exports": {".": "./src/main/index.mjs"},
        "bin": {"dependency-cruise": "bin/dependency-cruise.mjs"},
    }))
    result = _locate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(pkg_dir / "bin/dependency-cruise.mjs")


def test_locate_cruiser_bin_missing_is_a_clear_error(tmp_path: Path):
    result = _locate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stderr == f"ERR:dependency-cruiser is not installed in {tmp_path}; the TypeScript adapter needs it"


def _normalize(cruise: dict) -> dict:
    script = (f"import {{ normalizeCruise }} from '{ADAPTER.as_posix()}';"
              f"const n = normalizeCruise({json.dumps(cruise)}, []);"
              "process.stdout.write(JSON.stringify({modules:[...n.modules].sort(), edges:n.edges, warnings:n.warnings}));")
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_unresolved_import_is_a_warning_and_never_an_edge():
    cruise = {"modules": [
        {"source": "src/a.ts", "dependencies": [
            {"module": "@app/missing", "resolved": "@app/missing", "dependencyTypes": ["unknown"], "couldNotResolve": True},
            {"module": "./gone", "resolved": "./gone", "dependencyTypes": ["local"], "couldNotResolve": True},
        ]},
        {"source": "@app/missing", "couldNotResolve": True, "dependencies": []},
        {"source": "./gone", "couldNotResolve": True, "dependencies": []},
    ]}
    out = _normalize(cruise)
    assert out["edges"] == []
    assert out["modules"] == ["src/a.ts"]
    assert "unresolved import @app/missing in src/a.ts" in out["warnings"]
    assert "unresolved import ./gone in src/a.ts" in out["warnings"]


def test_dependency_outside_the_root_is_an_external_with_a_warning():
    cruise = {"modules": [
        {"source": "src/a.ts", "dependencies": [
            {"module": "../../sibling/x", "resolved": "../sibling/x.ts", "dependencyTypes": ["local"], "couldNotResolve": False},
        ]},
        {"source": "../sibling/x.ts", "dependencies": []},
    ]}
    out = _normalize(cruise)
    assert out["modules"] == ["src/a.ts"]
    assert out["edges"] == [{"from": "src/a.ts", "external": {"name": "sibling", "tag": "vendor"}}]
    assert "module outside the root: ../sibling/x.ts" in out["warnings"]


def test_cruise_arguments_pass_the_tsconfig_only_with_the_bundled_config(tmp_path: Path):
    (tmp_path / "tsconfig.json").write_text("{}")
    (tmp_path / "tsconfig.app.json").write_text("{}")
    script = (f"import {{ cruiseArguments, DEFAULT_CONFIG }} from '{ADAPTER.as_posix()}';"
              f"const root = {json.dumps(str(tmp_path))};"
              "const out = [await cruiseArguments(root, {}, DEFAULT_CONFIG, ['src']),"
              " await cruiseArguments(root, {tsConfig: 'tsconfig.app.json'}, DEFAULT_CONFIG, ['src']),"
              " await cruiseArguments(root, {}, root + '/.dependency-cruiser.cjs', ['src'])];"
              "process.stdout.write(JSON.stringify(out));")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    bundled, named, own = json.loads(result.stdout)
    assert bundled[bundled.index("--ts-config") + 1] == str(tmp_path / "tsconfig.json")
    assert named[named.index("--ts-config") + 1] == str(tmp_path / "tsconfig.app.json")
    assert "--ts-config" not in own


def test_locate_cruiser_bin_skips_a_malformed_package_json(tmp_path: Path):
    pkg_dir = tmp_path / "node_modules/dependency-cruiser"
    (pkg_dir / "src/main").mkdir(parents=True)
    (pkg_dir / "src/main/index.mjs").write_text("")
    (pkg_dir / "src/main/package.json").write_text("{not json")
    (pkg_dir / "package.json").write_text(json.dumps({
        "name": "dependency-cruiser",
        "exports": {".": "./src/main/index.mjs"},
        "bin": {"dependency-cruise": "bin/dependency-cruise.mjs"},
    }))
    result = _locate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == str(pkg_dir / "bin/dependency-cruise.mjs")
