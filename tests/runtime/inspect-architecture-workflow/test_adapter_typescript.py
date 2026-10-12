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
