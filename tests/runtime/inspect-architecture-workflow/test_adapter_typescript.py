import json
import os
import subprocess
from pathlib import Path

import pytest

from support import SKILL_DIR, copy_fixture, install_fake_tooling, node_path, run_node

TEMPLATE = SKILL_DIR / "assets" / "adapter-templates" / "typescript" / "adapter.mjs"
REQUEST = {"version": 1, "frameworks": ["express"], "ports": []}


def run_template(root: Path, source_root: Path | str | None = None, request: dict | None = None):
    env = {**os.environ, "ARCH_SOURCE_ROOT": str(source_root or root)}
    return subprocess.run(
        [node_path(), str(TEMPLATE)], cwd=root, env=env, input=json.dumps(request or REQUEST),
        capture_output=True, text=True, timeout=120, check=False,
    )


def typescript_resolvable(root: Path) -> bool:
    probe = ("import {createRequire} from 'node:module';"
             "try{createRequire(process.cwd()+'/x.js').resolve('typescript');process.stdout.write('yes')}"
             "catch{process.stdout.write('no')}")
    return run_node(probe, root).stdout == "yes"


def install_cruise_shim(root: Path) -> None:
    shim = root / "node_modules/.bin/depcruise"
    shim.parent.mkdir(parents=True, exist_ok=True)
    shim.write_text("#!/bin/sh\ncat cruise.json\n")
    shim.chmod(0o755)


def write_project(root: Path, files: dict[str, str], cruise: dict) -> None:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "cruise.json").write_text(json.dumps(cruise))
    (root / "tsconfig.json").write_text(json.dumps({"compilerOptions": {"strict": True, "target": "ES2022"}}))
    install_cruise_shim(root)


def cruise_of(*pairs: tuple[str, str | None]) -> dict:
    sources: dict[str, list[dict]] = {}
    for source, target in pairs:
        sources.setdefault(source, [])
        if target:
            sources.setdefault(target, [])
            sources[source].append({"module": target, "resolved": target, "dependencyTypes": ["local", "import"],
                                    "dynamic": False, "couldNotResolve": False})
    return {"modules": [{"source": name, "dependencies": deps} for name, deps in sources.items()]}


def test_normalize_cruise_classifies_edges(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    script = (f"import {{ normalizeCruise }} from '{TEMPLATE.as_posix()}';import {{ readFile }} from 'node:fs/promises';"
              "const j = JSON.parse(await readFile('cruise.json','utf8'));const n = normalizeCruise(j, ['express']);"
              "process.stdout.write(JSON.stringify({modules:[...n.modules].sort(), edges:n.edges}));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert "src/domain/payroll-use-case.ts" in out["modules"]
    internal = {(e["from"], e["to"], e["kind"]) for e in out["edges"] if "to" in e}
    assert ("src/web/payroll-controller.ts", "src/domain/payroll-use-case.ts", "import") in internal
    assert ("src/adapters/system-clock.ts", "src/domain/index.ts", "type-import") in internal
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
    script = (f"import {{ normalizeCruise }} from '{TEMPLATE.as_posix()}';"
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
    if not typescript_resolvable(root):
        pytest.skip("typescript not resolvable from the fixture")
    install_cruise_shim(root)
    result = run_template(root)
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    by_path = {m["path"]: m for m in document["modules"]}
    assert by_path["src/domain/clock.ts"]["exports"] == {"abstract": 1, "concrete": 0}
    assert by_path["src/domain/employee.ts"]["exports"] == {"abstract": 0, "concrete": 1}
    assert by_path["src/adapters/system-clock.ts"]["implements"] == ["Clock"]


def test_template_prints_a_document_from_the_saved_cruise(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    install_fake_tooling(root)
    result = run_template(root)
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["version"] == 1
    assert document["capabilities"]["exports"] is True
    assert document["capabilities"]["signatures"] is False
    assert document["capabilities"]["symbolImports"] is False
    assert "src/domain/payroll-use-case.ts" in {m["path"] for m in document["modules"]}
    externals = {(e["from"], e["external"]["name"], e["external"]["tag"]) for e in document["edges"] if "external" in e}
    assert ("src/web/payroll-controller.ts", "express", "framework") in externals
    assert any("cannot build a TypeScript program" in warning for warning in document["warnings"])


def test_missing_typescript_is_a_clear_error(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    result = run_template(root, source_root="/nonexistent-root")
    assert result.returncode != 0
    assert "typescript is not installed in /nonexistent-root" in result.stderr


def test_tree_without_packages_sees_the_source_roots_packages_during_the_run(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    install_fake_tooling(source)
    shim = source / "node_modules/.bin/depcruise"
    shim.write_text("#!/bin/sh\ntest -d node_modules/typescript && cat cruise.json\n")
    tree = copy_fixture("payroll", tmp_path / "base-tree")
    result = run_template(tree, source_root=source)
    assert result.returncode == 0, result.stderr
    assert "src/domain/clock.ts" in {m["path"] for m in json.loads(result.stdout)["modules"]}
    assert not (tree / "node_modules").exists()


def test_source_root_falls_back_to_the_current_directory(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    install_fake_tooling(root)
    env = {key: value for key, value in os.environ.items() if key != "ARCH_SOURCE_ROOT"}
    result = subprocess.run([node_path(), str(TEMPLATE)], cwd=root, env=env, input=json.dumps(REQUEST),
                            capture_output=True, text=True, timeout=120, check=False)
    assert result.returncode == 0, result.stderr


def _locate(root: Path) -> "subprocess.CompletedProcess[str]":
    script = (f"import {{ locateCruiserBin }} from '{TEMPLATE.as_posix()}';"
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
    script = (f"import {{ normalizeCruise }} from '{TEMPLATE.as_posix()}';"
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


def test_cruise_arguments_pass_the_tsconfig_only_when_it_exists(tmp_path: Path):
    (tmp_path / "tsconfig.app.json").write_text("{}")
    script = (f"import {{ cruiseArguments }} from '{TEMPLATE.as_posix()}';"
              f"const root = {json.dumps(str(tmp_path))};"
              "const settings = { roots: ['src'], dependencyCruiserConfig: '/cfg.cjs' };"
              "const out = [await cruiseArguments(root, { ...settings, tsConfig: 'tsconfig.app.json' }),"
              " await cruiseArguments(root, { ...settings, tsConfig: 'tsconfig.json' })];"
              "process.stdout.write(JSON.stringify(out));")
    result = run_node(script, tmp_path)
    assert result.returncode == 0, result.stderr
    named, absent = json.loads(result.stdout)
    assert named[named.index("--ts-config") + 1] == str(tmp_path / "tsconfig.app.json")
    assert named[named.index("--config") + 1] == "/cfg.cjs"
    assert "--ts-config" not in absent


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


def test_package_resolved_outside_the_root_keeps_its_package_name():
    cruise = {"modules": [
        {"source": "src/a.ts", "dependencies": [
            {"module": "react", "resolved": "../../main/node_modules/.pnpm/react@19/node_modules/react/index.js", "dependencyTypes": ["npm"], "couldNotResolve": False},
        ]},
    ]}
    out = _normalize(cruise)
    assert out["edges"] == [{"from": "src/a.ts", "external": {"name": "react", "tag": "vendor"}}]
    assert out["warnings"] == []


SOURCE_B = "export class Foo {}\n"
SOURCE_A = (
    'import { Foo } from "./b";\n'
    "export function isFoo(value: unknown): boolean {\n"
    "  return value instanceof Foo;\n"
    "}\n"
)


def real_typescript_project(tmp_path: Path) -> Path:
    root = tmp_path / "ts-project"
    root.mkdir()
    if not typescript_resolvable(root):
        pytest.skip("typescript not resolvable from the project")
    write_project(root, {"src/a.ts": SOURCE_A, "src/b.ts": SOURCE_B}, cruise_of(("src/a.ts", "src/b.ts")))
    return root


def test_template_reports_symbol_imports(tmp_path: Path):
    root = real_typescript_project(tmp_path)
    result = run_template(root)
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["capabilities"]["symbolImports"] is True
    edge = next(e for e in document["edges"] if e.get("to") == "src/b.ts")
    assert edge["symbols"] == ["Foo"]


def test_template_reports_type_checks(tmp_path: Path):
    root = real_typescript_project(tmp_path)
    result = run_template(root)
    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["capabilities"]["typeChecks"] is True
    module = next(m for m in document["modules"] if m["path"] == "src/a.ts")
    assert module["typeChecks"] == [{"symbol": "Foo", "path": "src/b.ts", "line": 3}]


def test_links_are_removed_after_a_failing_run(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    install_fake_tooling(source)
    (source / "node_modules/.bin/depcruise").write_text("#!/bin/sh\ntest -d node_modules && echo boom-detail >&2; exit 1\n")
    tree = copy_fixture("payroll", tmp_path / "base-tree")
    result = run_template(tree, source_root=source)
    assert result.returncode != 0
    assert "boom-detail" in result.stderr
    assert not (tree / "node_modules").exists()


def test_unsupported_compiler_version_is_a_clear_error(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    install_fake_tooling(root)
    (root / "node_modules/typescript/index.js").write_text('module.exports = { version: "7.0.2" };\n')
    result = run_template(root)
    assert result.returncode != 0
    assert "version 7.0.2" in result.stderr
    assert "5.x and 6.x" in result.stderr


OLD_ADAPTER = SKILL_DIR / "scripts" / "lib" / "adapters" / "typescript.mjs"


# Removed together with the old adapter in the next task.
def test_fixture_adapter_json_equals_what_the_old_adapter_produced(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    script = (f"import {{ createTypescriptAdapter }} from '{OLD_ADAPTER.as_posix()}';"
              "const adapter = createTypescriptAdapter({root: process.cwd(), tooling: {roots: ['src']}});"
              "const result = await adapter.extract({roots: ['src'], dependenciesJsonPath: 'cruise.json',"
              " factsJsonPath: 'facts.json', frameworks: []});"
              "process.stdout.write(JSON.stringify(result));")
    result = run_node(script, root)
    assert result.returncode == 0, result.stderr
    old = json.loads(result.stdout)
    fixture = json.loads((root / "adapter.json").read_text())
    assert fixture["modules"] == old["modules"]
    assert fixture["edges"] == old["edges"]
    assert fixture["warnings"] == old["warnings"]
    old_capabilities = {name: True for name in old["capabilities"] if old["capabilities"][name]}
    assert {name: fixture["capabilities"][name] for name in old_capabilities} == old_capabilities
    assert fixture["capabilities"]["symbolImports"] is False
    assert fixture["capabilities"]["typeChecks"] is False
