import json
from pathlib import Path

from support import SKILL_DIR, copy_fixture, node_path, run_node

RUN = (SKILL_DIR / "scripts/lib/adapter/run.mjs").as_posix()
LOAD = (SKILL_DIR / "scripts/lib/model/load.mjs").as_posix()
MODEL_FILE = "docs/architecture/architecture.json"

DOCUMENT = {"version": 1, "capabilities": {"exports": True}, "modules": [], "edges": [], "warnings": []}

ECHO_REQUEST = """let text = '';
process.stdin.on('data', (chunk) => { text += chunk; });
process.stdin.on('end', () => {
  const document = { version: 1, modules: [], edges: [], warnings: [text] };
  process.stdout.write(JSON.stringify(document));
});
"""


REPORT_PLACE = """const place = `${process.cwd()}|${process.env.ARCH_SOURCE_ROOT}`;
process.stdout.write(JSON.stringify({ version: 1, warnings: [place] }));
"""


def project(tmp_path: Path, adapter: str) -> Path:
    root = copy_fixture("payroll", tmp_path / "p")
    model_path = root / MODEL_FILE
    model = json.loads(model_path.read_text())
    model["adapter"] = adapter
    model["frameworks"] = ["express"]
    model_path.write_text(json.dumps(model))
    return root


def run_adapter(root: Path):
    script = (
        f"import {{ loadModel }} from '{LOAD}';import {{ runAdapter }} from '{RUN}';"
        "try {"
        "  const model = loadModel(process.cwd(), {});"
        "  const document = await runAdapter(model, process.cwd(), process.cwd());"
        "  process.stdout.write(JSON.stringify(document));"
        "} catch (error) {"
        "  process.stderr.write(`${error.constructor.name}: ${error.message}`);"
        "  process.exit(error.exitCode ?? 1);"
        "}"
    )
    return run_node(script, root)


def adapter_printing(root: Path, document: object) -> None:
    (root / "out.json").write_text(json.dumps(document))


def test_missing_adapter_command_exits_2(tmp_path: Path):
    root = project(tmp_path, "no-such-command")
    result = run_adapter(root)
    assert result.returncode == 2
    assert "ToolingError" in result.stderr
    assert "no-such-command" in result.stderr


def test_adapter_non_zero_exit_reports_status_and_stderr(tmp_path: Path):
    command = "sh -c 'for n in 1 2 3 4 5 6 7; do echo line$n >&2; done; exit 3'"
    root = project(tmp_path, command)
    result = run_adapter(root)
    assert result.returncode == 2
    assert command in result.stderr
    assert "status 3" in result.stderr
    assert "line7" in result.stderr
    assert "line3" in result.stderr
    assert "line2" not in result.stderr
    assert "from the project root" in result.stderr


def test_adapter_non_json_output_exits_2(tmp_path: Path):
    root = project(tmp_path, "echo not-json")
    result = run_adapter(root)
    assert result.returncode == 2
    assert "not valid JSON" in result.stderr


def test_document_schema_problem_names_the_path(tmp_path: Path):
    document = {**DOCUMENT, "edges": [{"from": "src/a.ts", "to": "src/b.ts", "kind": "require"}]}
    root = project(tmp_path, "cat out.json")
    adapter_printing(root, document)
    result = run_adapter(root)
    assert result.returncode == 2
    assert "edges[0].kind" in result.stderr


def test_adapter_receives_ports_and_frameworks_on_stdin(tmp_path: Path):
    root = project(tmp_path, f'"{node_path()}" echo-request.mjs')
    (root / "echo-request.mjs").write_text(ECHO_REQUEST)
    result = run_adapter(root)
    assert result.returncode == 0, result.stderr
    request = json.loads(json.loads(result.stdout)["warnings"][0])
    assert request["version"] == 1
    assert request["frameworks"] == ["express"]
    assert {"path": "src/domain/clock.ts", "symbol": "Clock"} in request["ports"]


def test_adapter_runs_in_the_tree_with_the_source_root_variable(tmp_path: Path):
    root = project(tmp_path, f'"{node_path()}" report-place.mjs')
    (root / "report-place.mjs").write_text(REPORT_PLACE)
    result = run_adapter(root)
    assert result.returncode == 0, result.stderr
    tree, source = json.loads(result.stdout)["warnings"][0].split("|")
    assert Path(tree).resolve() == root.resolve()
    assert Path(source).resolve() == root.resolve()


def test_capability_left_out_is_false(tmp_path: Path):
    document = {
        "version": 1,
        "capabilities": {"exports": True},
        "modules": [{"path": "src/a.ts", "exports": {"abstract": 1, "concrete": 2}, "implements": ["Clock"]}],
        "edges": [{"from": "src/a.ts", "to": "src/b.ts", "kind": "import", "symbols": ["S"]}],
        "warnings": [],
    }
    root = project(tmp_path, "cat out.json")
    adapter_printing(root, document)
    result = run_adapter(root)
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    assert out["capabilities"] == {
        "exports": True, "implements": False, "constructs": False,
        "signatures": False, "symbolImports": False, "typeChecks": False,
    }
    module = out["modules"][0]
    assert module["exports"] == {"abstract": 1, "concrete": 2}
    assert module["implements"] == []
    assert "symbols" not in out["edges"][0]
