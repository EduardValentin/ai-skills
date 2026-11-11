"""The router, the four flows, and the command pages agree with the command they describe."""

import json
import re
import shlex
import shutil
from functools import cache

import pytest

from support import SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
FLOWS_DIR = REFERENCES / "flows"
COMMANDS_DIR = REFERENCES / "commands"
FLOW_NAMES = ["baseline", "audit", "change-review", "plan-review"]
REVIEW_FLOWS = ["audit", "change-review", "plan-review"]
COMPARING_FLOWS = ["change-review", "plan-review"]
PAGE_NAMES = ["collect", "check", "applicable", "query", "uncovered", "model", "findings"]
PAGE_SECTIONS = ["## Synopsis", "## Flags", "## Exit codes", "## Output", "## Example"]
MAX_BODY_LINES = 45
MAX_FLOW_LINES = 90
STOP_MESSAGE = (
    "There is no architecture model for this project. Run the baseline flow first "
    "(`inspect-architecture-workflow` with the flow name `baseline`), then run this review again."
)
DESCRIPTION = (
    "Use to record a project's architecture baseline, or for a dedicated architecture audit, an architecture review "
    "of a diff, or an architecture review of an implementation plan or spec before approval, passing the flow name "
    "`baseline`, `audit`, `change-review`, or `plan-review`."
)
READ_ONLY_MODEL_SUBCOMMANDS = {"explain", "explain-thresholds", "validate", "status"}
FAILURE_LINE = "If a command fails"
RETIRED = re.compile(r"\b(ledger|evaluator|coordinator|slices?|packet files?)\b", re.IGNORECASE)
COMMAND_SPAN = re.compile(r"`(arch [^`]+)`")
FLAG = re.compile(r"(?<![\w-])--([a-z][a-z-]*)")
LINK = re.compile(r"\]\(([^)\s]+)\)")
SKILL_PATH = re.compile(r"`((?:scripts|references|assets)/[^`\s]+)`")
NUMBERED_STEP = re.compile(r"^(\d+)\. ")
JSON_BLOCK = re.compile(r"^ *```json\n(.*?)^ *```", re.MULTILINE | re.DOTALL)
PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z |]*>")
OLD_FILES = [
    "references/audit.md", "references/change-review.md", "references/plan-review.md", "references/slicing.md",
    "references/verdicts.md", "references/command.md", "assets/docs", "assets/ledger",
]

SPEC_SCRIPT = """
import { GLOBAL_FLAGS } from "./scripts/lib/cli/flags.mjs";
import { APPLICABLE_MODES, APPLICABLE_SPEC } from "./scripts/lib/commands/applicable.mjs";
import { CHECK_EXCLUSIVE, CHECK_SPEC } from "./scripts/lib/commands/check.mjs";
import { COLLECT_SPEC } from "./scripts/lib/commands/collect.mjs";
import { ADD_REQUIRED, ADD_SPEC, LIST_SPEC } from "./scripts/lib/commands/findings.mjs";
import { MODEL_SPEC, MODEL_SUBCOMMANDS } from "./scripts/lib/commands/model.mjs";
import { QUERY_SPEC } from "./scripts/lib/commands/query.mjs";
import { QUERY_FLAGS, QUERY_REQUIRED_FLAGS } from "./scripts/lib/queries/index.mjs";
import { UNCOVERED_SPEC } from "./scripts/lib/commands/uncovered.mjs";
import { EDITS } from "./scripts/lib/model/edits.mjs";
console.log(JSON.stringify({
  global: GLOBAL_FLAGS,
  top: {
    collect: COLLECT_SPEC, check: CHECK_SPEC, applicable: APPLICABLE_SPEC, query: QUERY_SPEC,
    uncovered: UNCOVERED_SPEC, model: MODEL_SPEC,
  },
  findings: { add: ADD_SPEC, list: LIST_SPEC },
  model: MODEL_SUBCOMMANDS,
  edits: Object.keys(EDITS),
  queryFlags: QUERY_FLAGS,
  queryRequired: QUERY_REQUIRED_FLAGS,
  addRequired: Object.fromEntries(Object.entries(ADD_REQUIRED).map(([key, flags]) => [key, Object.keys(flags)])),
  applicableModes: APPLICABLE_MODES,
  checkExclusive: CHECK_EXCLUSIVE,
}));
"""


@cache
def specs() -> dict:
    result = run_node(SPEC_SCRIPT, SKILL_DIR)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def flow_file(name: str):
    return FLOWS_DIR / f"{name}.md"


def page_file(name: str):
    return COMMANDS_DIR / f"{name}.md"


def flow_files(names=FLOW_NAMES) -> list:
    return [flow_file(name) for name in names]


def page_files() -> list:
    return [page_file(name) for name in PAGE_NAMES]


def body_lines(text: str) -> list[str]:
    _, _, body = text.split("---\n", 2)
    return body.strip("\n").splitlines()


def frontmatter(text: str) -> str:
    return text.split("---\n", 2)[1]


def command_lines(path) -> list[str]:
    lines = []
    in_code = False
    for line in path.read_text().splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        stripped = line.strip().removeprefix("$ ")
        if in_code and stripped.startswith("arch "):
            lines.append(stripped)
        elif not in_code:
            lines.extend(COMMAND_SPAN.findall(line))
    return lines


def read_flags(spec_flags: dict, args: list[str], allowed=None) -> tuple[list[str], list[str], dict]:
    kinds = {**spec_flags, **specs()["global"]}
    names = set(kinds) if allowed is None else set(allowed) | set(specs()["global"])
    problems, positional, given = [], [], {}
    index = 0
    while index < len(args):
        arg = args[index]
        if not arg.startswith("--"):
            positional.append(arg)
        elif arg[2:] not in names:
            problems.append(f"unknown flag {arg}")
        elif kinds[arg[2:]] == "boolean":
            given[arg[2:]] = True
        elif index + 1 >= len(args) or args[index + 1].startswith("--"):
            problems.append(f"{arg} has no value")
        else:
            given[arg[2:]] = args[index + 1]
            index += 1
        index += 1
    return problems, positional, given


def missing(required, given: dict) -> list[str]:
    return [f"--{name} is required" for name in required if name not in given]


def check_model_line(rest: list[str]) -> list[str]:
    subcommand = specs()["model"].get(rest[0])
    if subcommand is None:
        return [f"unknown model subcommand {rest[0]}"]
    if len(rest) == 1:
        return []
    problems, positional, given = read_flags(specs()["top"]["model"]["flags"], rest[1:], subcommand["flags"])
    keys = [arg.split("=", 1)[0] for arg in positional if re.match(r"^[a-z][a-z-]*=", arg)]
    plain = [arg for arg in positional if not re.match(r"^[a-z][a-z-]*=", arg)]
    allowed_keys = subcommand["required"] + subcommand["optional"]
    problems += [f"unknown argument {key}=" for key in keys if key not in allowed_keys]
    problems += [f"missing {key}=" for key in subcommand["required"] if key not in keys]
    problems += missing(subcommand["requiredFlags"], given)
    if len(plain) != subcommand["positional"]:
        problems.append(f"{len(plain)} positional arguments, expected {subcommand['positional']}")
    return problems


def check_findings_line(rest: list[str]) -> list[str]:
    if rest[0] not in specs()["findings"]:
        return [f"unknown findings subcommand {rest[0]}"]
    problems, positional, given = read_flags(specs()["findings"][rest[0]]["flags"], rest[1:])
    problems += [f"unexpected arguments {positional}"] if positional else []
    if rest[0] == "add" and len(rest) > 1:
        required = specs()["addRequired"]
        problems += missing(required["always"], given)
        problems += missing(required.get(given.get("flow"), {}), given)
    return problems


def mode_problems(name: str, rest: list[str], given: dict) -> list[str]:
    if name == "applicable" and rest:
        modes = [mode for mode in specs()["applicableModes"] if mode in given]
        return [] if len(modes) == 1 else [f"needs exactly one of {specs()['applicableModes']}, got {modes}"]
    if name == "check" and all(flag in given for flag in specs()["checkExclusive"]):
        return [f"combines {specs()['checkExclusive']}"]
    if name == "query" and rest:
        return missing(specs()["queryRequired"].get(rest[0], []), given)
    return []


def check_top_line(name: str, rest: list[str]) -> list[str]:
    spec = specs()["top"][name]
    allowed = specs()["queryFlags"].get(rest[0], []) if name == "query" and rest else None
    problems, positional, given = read_flags(spec["flags"], rest, allowed)
    low, high = spec["positional"].get("min", 0), spec["positional"].get("max", 0)
    if rest and not low <= len(positional) <= high:
        problems.append(f"{len(positional)} positional arguments, expected {low} to {high}")
    return problems + mode_problems(name, rest, given)


def line_problems(line: str) -> list[str]:
    tokens = shlex.split(line.replace("[", "").replace("]", ""))
    name, rest = tokens[1], tokens[2:]
    if name == "findings":
        return check_findings_line(rest) if rest else []
    if name == "model":
        return check_model_line(rest) if rest else []
    if name not in specs()["top"]:
        return [f"unknown subcommand {name}"]
    return check_top_line(name, rest)


def unparsable(paths) -> list[str]:
    return [
        f"{path.relative_to(SKILL_DIR)}: `{line}`: {problem}"
        for path in paths
        for line in command_lines(path)
        for problem in line_problems(line)
    ]


def numbered_steps(text: str) -> dict[int, str]:
    steps, current = {}, None
    for line in text.splitlines():
        match = NUMBERED_STEP.match(line)
        if match:
            current = int(match.group(1))
            steps[current] = line
        elif current is not None and line.startswith("   "):
            steps[current] += " " + line.strip()
        else:
            current = None
    return steps


def table_flags(text: str) -> set[str]:
    flags = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("| Flag |"):
            continue
        for row in lines[index + 2:]:
            if not row.startswith("|"):
                break
            flags.update(FLAG.findall(row.strip("|").split("|")[0]))
    return flags


def declared_flags(page: str) -> set[str]:
    data = specs()
    if page == "findings":
        own = {**data["findings"]["add"]["flags"], **data["findings"]["list"]["flags"]}
    else:
        own = data["top"][page]["flags"]
    return set(own) | set(data["global"])


def every_flag() -> set[str]:
    data = specs()
    flags = set(data["global"])
    for spec in [*data["top"].values(), *data["findings"].values()]:
        flags |= set(spec["flags"])
    return flags


def skill_markdown() -> list:
    return [SKILL_MD, *sorted(REFERENCES.rglob("*.md"))]


def test_skill_body_is_a_short_router():
    text = SKILL_MD.read_text()
    head = frontmatter(text)
    assert "name: inspect-architecture-workflow" in head
    assert " ".join(head.split("description: >-", 1)[1].split("compatibility:", 1)[0].split()) == DESCRIPTION
    assert "architecture-reviewer" in head and "architecture-classifier" in head
    assert len(body_lines(text)) <= MAX_BODY_LINES, f"SKILL.md body has {len(body_lines(text))} lines"
    for name in FLOW_NAMES:
        assert f"(references/flows/{name}.md)" in text, f"SKILL.md does not route to {name}"


def test_each_flow_fits_its_budget():
    for path in flow_files():
        lines = path.read_text().splitlines()
        assert len(lines) <= MAX_FLOW_LINES, f"{path.name} has {len(lines)} lines"
        assert numbered_steps(path.read_text()), f"{path.name} has no numbered steps"


def mentions_of_flow(text: str, name: str) -> list[str]:
    pattern = rf"`{re.escape(name)}`|{re.escape(name)}\.md|\b{re.escape(name)} flow\b"
    return re.findall(pattern, text, re.IGNORECASE)


def test_a_flow_names_another_flow_only_in_the_stop_message():
    for path in flow_files():
        text = " ".join(path.read_text().split())
        outside_stop = text.replace(STOP_MESSAGE, "")
        for other in FLOW_NAMES:
            if other != path.stem:
                assert not mentions_of_flow(outside_stop, other), f"{path.name} names the {other} flow"
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        for line in lines[:-1]:
            assert "commands/" not in line, f"{path.name} names a command page outside its last line: {line}"
        assert lines[-1].startswith(FAILURE_LINE), f"{path.name} does not end with '{FAILURE_LINE}'"


def test_flow_command_lines_use_declared_flags():
    problems = unparsable(flow_files())
    assert not problems, "\n".join(problems)


def test_review_flows_never_create_a_model():
    for name in REVIEW_FLOWS:
        for line in command_lines(flow_file(name)):
            assert not line.startswith(("arch model init", "arch model migrate", "arch model set-adapter")), line
    for name in COMPARING_FLOWS:
        for line in command_lines(flow_file(name)):
            assert not line.startswith("arch collect"), f"{name}: {line}"


def test_plan_review_never_edits_the_model():
    for line in command_lines(flow_file("plan-review")):
        tokens = line.split()
        if tokens[1] == "model" and len(tokens) > 2:
            assert tokens[2] in READ_ONLY_MODEL_SUBCOMMANDS, f"plan review edits the model: {line}"
        assert tokens[1] != "collect", f"plan review rewrites the current picture: {line}"


def test_every_review_flow_probes_the_model_first_and_stops_without_one(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    for name in REVIEW_FLOWS:
        steps = numbered_steps(flow_file(name).read_text())
        assert COMMAND_SPAN.findall(steps[1]) == ["arch model status --json"], name
        probe = FlowRunner(name, root, {}).run_step(1)
        assert probe.returncode == 0 and json.loads(probe.stdout)["model"] is False, name
        stop = " ".join(steps[2].split())
        assert stop.startswith("2. If `model` is `false`, stop here"), name
        assert f'"{STOP_MESSAGE}"' in stop, name
        assert not COMMAND_SPAN.findall(stop), f"{name}: the no-model branch runs a command"
        for word in ["`architecture-reviewer`", "`architecture-classifier`", "go to step", "Verdict", "`OK`"]:
            assert word not in stop, f"{name}: the no-model branch mentions {word}"
    assert list((root).iterdir()) == []


def test_flows_name_their_agents():
    for name in REVIEW_FLOWS:
        assert "architecture-reviewer" in flow_file(name).read_text(), name
    for name in ["baseline", "audit", "change-review"]:
        assert "architecture-classifier" in flow_file(name).read_text(), name
    assert "architecture-reviewer" not in flow_file("baseline").read_text()
    plan = flow_file("plan-review").read_text()
    assert "planFixRounds" in plan and "arch model explain-thresholds" in plan


def test_every_subcommand_has_a_complete_command_page():
    for path in page_files():
        text = path.read_text()
        for section in PAGE_SECTIONS:
            assert f"\n{section}\n" in text, f"{path.name} has no {section} section"


def test_command_pages_document_exactly_the_declared_flags():
    known = every_flag()
    for name in PAGE_NAMES:
        text = page_file(name).read_text()
        assert table_flags(text) == declared_flags(name), f"{name}.md flags table differs from the flag spec"
        stray = set(FLAG.findall(text)) - known
        assert not stray, f"{name}.md names flags that do not exist: {sorted(stray)}"


def test_flows_name_only_flags_that_exist():
    for path in flow_files():
        stray = set(FLAG.findall(path.read_text())) - every_flag()
        assert not stray, f"{path.name} names flags that do not exist: {sorted(stray)}"


def test_command_page_lines_use_declared_flags():
    problems = unparsable(page_files())
    assert not problems, "\n".join(problems)


def test_model_page_lists_every_subcommand_with_its_usage():
    text = page_file("model").read_text()
    for name, subcommand in specs()["model"].items():
        assert f"`{subcommand['usage']}`" in text, f"model.md lacks the usage line of {name}"
    assert set(specs()["edits"]) <= set(specs()["model"])


def test_flows_and_pages_name_no_retired_mechanism():
    for path in [*flow_files(), *page_files(), SKILL_MD]:
        match = RETIRED.search(path.read_text())
        assert not match, f"{path.name} mentions {match.group(0)!r}"


def test_skill_text_has_no_em_dash():
    for path in skill_markdown():
        assert "—" not in path.read_text(), f"{path.relative_to(SKILL_DIR)} has an em dash"


def test_every_link_and_skill_path_resolves():
    for path in skill_markdown():
        text = path.read_text()
        for target in LINK.findall(text):
            if "://" in target or target.startswith("#"):
                continue
            resolved = (path.parent / target.split("#", 1)[0]).resolve()
            assert resolved.is_file(), f"{path.relative_to(SKILL_DIR)}: link {target} does not resolve"
        for target in SKILL_PATH.findall(text):
            assert (SKILL_DIR / target).is_file(), f"{path.relative_to(SKILL_DIR)}: {target} is not a skill file"


def test_old_reference_files_are_gone():
    for name in OLD_FILES:
        assert not (SKILL_DIR / name).exists(), name


SCHEMA_SCRIPT = """
import { JUDGED_SCHEMA } from "./scripts/lib/findings/intake.mjs";
import { proposalSchema } from "./scripts/lib/checks/proposal.mjs";
import { validateShape } from "./scripts/lib/model/validate-shape.mjs";
const examples = JSON.parse(process.argv[1] ?? "[]");
const schemaOf = (document) => ("findings" in document ? JUDGED_SCHEMA : proposalSchema());
console.log(JSON.stringify(examples.map(({ where, document }) => ({ where, problems: validateShape(document, schemaOf(document)) }))));
"""


def json_examples() -> list[dict]:
    examples = []
    for path in [*flow_files(), page_file("check"), page_file("findings")]:
        for index, block in enumerate(JSON_BLOCK.findall(path.read_text())):
            examples.append({"where": f"{path.name} block {index + 1}", "document": json.loads(block)})
    return examples


def test_every_json_example_matches_the_schema_the_command_reads():
    examples = json_examples()
    kinds = {"findings" in example["document"] for example in examples}
    assert kinds == {True, False}, "expected both judged findings and proposal examples"
    script = SCHEMA_SCRIPT.replace('process.argv[1] ?? "[]"', json.dumps(json.dumps(examples)))
    result = run_node(script, SKILL_DIR)
    assert result.returncode == 0, result.stderr
    problems = [f"{entry['where']}: {entry['problems']}" for entry in json.loads(result.stdout) if entry["problems"]]
    assert not problems, "\n".join(problems)


def test_every_review_flow_shows_judged_findings_in_a_code_block():
    for path in flow_files(REVIEW_FLOWS):
        blocks = [json.loads(block) for block in JSON_BLOCK.findall(path.read_text())]
        assert any("findings" in block for block in blocks), f"{path.name} shows no judged findings shape"


def judged(judgment: str, target: str, evidence: str, **extra) -> dict:
    return {
        "judgment": judgment, "target": target, "consequence": "A pay rule change means editing this unit.",
        "correction": "Move the rule into the payroll use case.", "evidence": [evidence], **extra,
    }


CHANGE_REVIEW_JUDGED = {
    "findings": [
        judged("handler-holds-business-logic", "src/web/payroll-controller.ts", "src/web/payroll-controller.ts:1",
               origin="introduced"),
        judged("consumer-uses-few-interface-members", "src/domain/clock.ts#Clock", "src/domain/clock.ts:1",
               origin="introduced"),
    ],
    "questions": [],
}


def payroll_repository(tmp_path):
    root = copy_fixture("payroll", tmp_path / "payroll")
    init_repo(root)
    return root


def add_to_adapter(root, *, modules=(), edges=()):
    adapter = json.loads((root / "adapter.json").read_text())
    adapter["modules"].extend(modules)
    adapter["edges"].extend(edges)
    (root / "adapter.json").write_text(json.dumps(adapter, indent=2))


def change_with_a_new_external(tmp_path):
    root = payroll_repository(tmp_path)
    git(["checkout", "-q", "-b", "feature"], root)
    add_to_adapter(root, edges=[{"from": "src/web/payroll-controller.ts", "external": {"name": "zod", "tag": "vendor"}}])
    controller = root / "src/web/payroll-controller.ts"
    controller.write_text('import { z } from "zod";\n' + controller.read_text())
    clock = root / "src/domain/clock.ts"
    clock.write_text(clock.read_text() + "// read by the payroll controller\n")
    git(["commit", "-q", "-am", "controller imports a validation library"], root)
    return root


def project_with_an_unclassified_module(tmp_path):
    root = payroll_repository(tmp_path)
    add_to_adapter(root, modules=[{"path": "src/reports/summary.ts", "exports": {"abstract": 0, "concrete": 1}}])
    git(["commit", "-q", "-am", "a report module no component covers"], root)
    return root


APPLICABLE_FILE = ".architecture/work/applicable.json"


class FlowRunner:
    """Runs a flow's own command lines, substituting only the placeholders."""

    def __init__(self, flow: str, root, values: dict):
        self.root = root
        self.values = values
        self.steps = numbered_steps(flow_file(flow).read_text())

    def commands(self, step: int) -> list[str]:
        return COMMAND_SPAN.findall(self.steps[step])

    def substituted(self, line: str, extra: dict) -> list[str]:
        values = {**self.values, **extra}
        text = line.replace("[@<component>]", "")
        for placeholder in set(PLACEHOLDER.findall(text)):
            assert placeholder in values, f"no value for {placeholder} in `{line}`"
            text = text.replace(placeholder, values[placeholder])
        return shlex.split(text)[1:]

    def run(self, line: str, **extra):
        return run_arch(self.substituted(line, extra), self.root)

    def run_step(self, step: int, **extra):
        return self.run(self.commands(step)[0], **extra)

    def command_in(self, step: int, fragment: str) -> str:
        return next(line for line in self.commands(step) if fragment in line)

    def judged_path(self, step: int, **extra):
        args = self.substituted(self.command_in(step, "--judged"), extra)
        return self.root / args[args.index("--judged") + 1]


def test_the_change_review_flow_runs_as_written_through_acceptances(tmp_path):
    root = change_with_a_new_external(tmp_path)
    flow = FlowRunner("change-review", root, {
        "<ref>": "main", "<upcoming change>": "a second payroll form", "<text>": "accepted by the user",
    })
    assert json.loads(flow.run_step(1).stdout)["model"] is True
    assert flow.run_step(3).returncode == 0
    applicable = json.loads((root / APPLICABLE_FILE).read_text())
    assert applicable["adds"]["externals"] == ["zod"] and "humble-objects" in applicable["groups"]
    assert flow.run_step(5).returncode in (0, 1)
    flow.judged_path(10).write_text(json.dumps(CHANGE_REVIEW_JUDGED))
    assert "Verdict: SHOULD_CHANGE: 0 blocker, 2 major" in flow.run_step(10).stdout

    star = flow.command_in(11, "'*'")
    assert flow.run(star, **{"<target>": "src/web/payroll-controller.ts", "<R>": "R20"}).returncode == 0
    assert flow.run(star, **{"<target>": "src/domain/clock.ts#Clock", "<R>": "R13"}).returncode == 0
    flow.run_step(3)
    flow.run_step(5)
    accepted = flow.run_step(10).stdout
    assert "Dropped: 2 (2 covered by an exception)" in accepted
    assert "Verdict: INCOMPLETE" in accepted

    assert flow.run(flow.command_in(11, "set-rule"), **{"<R>": "R13"}).returncode == 0
    flow.run_step(3)
    flow.run_step(5)
    assert "Verdict: OK" in flow.run_step(10).stdout


def change_inside_one_component(tmp_path):
    root = payroll_repository(tmp_path)
    git(["checkout", "-q", "-b", "feature"], root)
    employee = root / "src/domain/employee.ts"
    employee.write_text(employee.read_text() + "export const PAY_DAY = 25;\n")
    git(["commit", "-q", "-am", "a pay day constant"], root)
    return root


STOP_CONDITION = "If `inScope` in `applicable.json` is 0"


def flow_reaches_the_reviewer(step: str, applicable: dict) -> bool:
    assert STOP_CONDITION in step, step
    return applicable["inScope"] > 0


def without_judged(args: list[str]) -> list[str]:
    index = args.index("--judged")
    return args[:index] + args[index + 2:]


def assert_reviewed(flow: FlowRunner, applicable: dict) -> None:
    assert flow_reaches_the_reviewer(flow.steps[6], applicable)
    assert flow.steps[7].startswith("7. Dispatch one `architecture-reviewer`, once")
    assert flow.run_step(5).returncode in (0, 1)
    flow.judged_path(10).write_text(json.dumps({"findings": [], "questions": []}))
    reviewed = flow.run_step(10).stdout
    assert f"Judgment conditions: {applicable['inScope']} in scope, {applicable['inScope']} reviewed" in reviewed


def test_the_change_review_flow_reaches_the_reviewer_for_a_change_inside_one_component(tmp_path):
    root = change_inside_one_component(tmp_path)
    flow = FlowRunner("change-review", root, {"<ref>": "main", "<upcoming change>": "a second payroll form"})
    assert flow.run_step(3).returncode == 0
    applicable = json.loads((root / APPLICABLE_FILE).read_text())
    assert applicable["components"] == ["domain"] and not any(applicable["adds"].values())
    assert "shape-mismatch-hidden" in [entry["id"] for entry in applicable["judgments"]["cross-cutting"]]
    assert_reviewed(flow, applicable)


def test_the_change_review_flow_reaches_the_reviewer_when_only_a_dependency_changes(tmp_path):
    root = payroll_repository(tmp_path)
    git(["checkout", "-q", "-b", "feature"], root)
    add_to_adapter(root, edges=[{"from": "src/adapters/system-clock.ts", "to": "src/web/main.ts", "kind": "import"}])
    git(["commit", "-q", "-am", "an import alias now resolves the clock to the web entry point"], root)
    flow = FlowRunner("change-review", root, {"<ref>": "main", "<upcoming change>": "a second payroll form"})
    assert flow.run_step(3).returncode == 0
    applicable = json.loads((root / APPLICABLE_FILE).read_text())
    assert applicable["units"] == [] and applicable["uncovered"] == []
    assert applicable["adds"]["componentEdges"] == ["adapters -> web"]
    assert_reviewed(flow, applicable)


def test_the_change_review_flow_dispatches_nobody_when_no_condition_applies(tmp_path):
    root = payroll_repository(tmp_path)
    git(["checkout", "-q", "-b", "feature"], root)
    (root / "NOTES.md").write_text("release notes\n")
    git(["add", "NOTES.md"], root)
    git(["commit", "-q", "-m", "notes only"], root)
    flow = FlowRunner("change-review", root, {"<ref>": "main", "<upcoming change>": "a second payroll form"})
    assert flow.run_step(3).returncode == 0
    applicable = json.loads((root / APPLICABLE_FILE).read_text())
    assert not flow_reaches_the_reviewer(flow.steps[6], applicable)
    assert "no judgment condition in scope; no reviewer dispatched" in flow.steps[6]
    assert flow.run_step(5).returncode == 0
    result = run_arch(without_judged(flow.substituted(flow.command_in(10, "--judged"), {})), root)
    assert result.returncode == 0, result.stderr
    assert "Judgment conditions: 0 in scope, 0 reviewed" in result.stdout and "judgment-review" not in result.stdout


def test_the_change_review_flow_judges_again_only_while_a_condition_applies():
    step = " ".join(numbered_steps(flow_file("change-review").read_text())[12].split())
    assert "If `inScope` is now 0" in step and "the same reviewer judges again" in step


def test_no_flow_lets_a_precheck_skip_the_selected_review():
    for name in FLOW_NAMES:
        text = flow_text(name)
        for phrase in ["`review` is", "skip to step", "notReviewed", "--full", "units` and `uncovered"]:
            assert phrase not in text, f"{name}: {phrase}"


def test_the_audit_flow_classifies_every_module_before_collecting(tmp_path):
    root = project_with_an_unclassified_module(tmp_path)
    flow = FlowRunner("audit", root, {
        "<name>": "reports", "<globs>": "src/reports/**", "<component>": "reports", "<pattern>": "**",
        "<kind>": "presenter", "<group>": "humble-objects", "<upcoming change>": "a second payroll form",
    })
    assert json.loads(flow.run_step(1).stdout)["model"] is True
    assert flow.run_step(3).returncode == 0, "validate passes although a module is unclassified"
    uncovered = flow.run_step(4)
    assert uncovered.returncode == 1 and uncovered.stdout.split() == ["src/reports/summary.ts"]

    for fragment in ["add-component", "classify"]:
        assert flow.run(flow.command_in(5, fragment)).returncode == 0
    assert flow.run_step(3).returncode == 0
    reclassified = flow.run_step(4)
    assert reclassified.returncode == 0 and reclassified.stdout.strip() == ""

    assert flow.run_step(6).returncode == 0
    assert flow.run_step(7).returncode in (0, 1)
    assert flow.run_step(8).returncode == 0
    assert json.loads((root / APPLICABLE_FILE).read_text())["inScope"] > 0
    flow.judged_path(12).write_text(json.dumps({"findings": [], "questions": []}))
    audited = flow.run_step(12).stdout
    assert "# Architecture audit" in audited and "Judgment conditions: " in audited
    assert "Judgment conditions: not reported" not in audited
    assert "## Ranked by change volatility" in flow.run_step(14).stdout


SOUND_SMALL_CLASSIFICATION = {
    "billing": ("src/billing/**", [("invoice-store.ts", "port"), ("**/*-use-case.ts", "use-case"), ("**", "entity")]),
    "storage": ("src/storage/**", [("**", "adapter")]),
    "app": ("src/app/**", [("main.ts", "composition-root"), ("config.ts", "config"), ("**", "entry-point")]),
}


def project_without_a_model(tmp_path):
    root = copy_fixture("sound-small", tmp_path / "sound-small")
    shutil.rmtree(root / "docs")
    init_repo(root)
    return root


def test_the_baseline_flow_runs_as_written_and_records_no_findings(tmp_path):
    root = project_without_a_model(tmp_path)
    flow = FlowRunner("baseline", root, {
        "<greenfield|legacy>": "legacy", "<committed|local>": "committed", "<command>": "cat adapter.json",
    })
    assert json.loads(flow.run_step(1).stdout)["model"] is False
    assert flow.run(flow.command_in(4, "arch model init")).returncode == 0
    assert flow.run(flow.command_in(4, "arch model set-adapter")).returncode == 0
    empty = flow.run_step(5)
    assert empty.returncode == 2 and "the model has no components" in empty.stderr
    assert flow.run_step(6).returncode == 1

    for component, (globs, pairs) in SOUND_SMALL_CLASSIFICATION.items():
        named = {"<name>": component, "<globs>": globs, "<component>": component}
        assert flow.run(flow.command_in(7, "add-component"), **named).returncode == 0
        for pattern, kind in pairs:
            classified = flow.run(flow.command_in(7, "classify"), **named, **{"<pattern>": pattern, "<kind>": kind})
            assert classified.returncode == 0, classified.stderr
    assert flow.run_step(5).returncode == 0
    covered = flow.run_step(6)
    assert covered.returncode == 0 and covered.stdout.strip() == ""

    collected = flow.run_step(8)
    assert collected.returncode == 0 and collected.stdout.startswith("collect: 9 units")
    assert (root / "docs/architecture/current.md").is_file()
    checked = flow.run_step(9)
    assert checked.returncode in (0, 1) and "## Rules not enforced" in checked.stdout
    assert not (root / ".architecture/findings.json").exists()
    assert not (root / ".architecture/work").exists()
    assert json.loads((root / "docs/architecture/architecture.json").read_text())["record"] == "committed"


def test_the_baseline_flow_says_its_check_is_not_a_review():
    text = flow_text("baseline")
    assert "dispatches no reviewer and records no findings" in text
    step = " ".join(numbered_steps(flow_file("baseline").read_text())[9].split())
    assert "this is not a review" in step and "no agent judged anything" in step
    assert not [line for line in command_lines(flow_file("baseline")) if line.startswith(
        ("arch findings", "arch applicable"))]


EMPLOYEE = "src/domain/employee.ts"


def audit_judged(judgment: str, correction: str) -> dict:
    return {"findings": [{
        "judgment": judgment, "target": EMPLOYEE, "consequence": "Payroll and reporting changes edit the same unit.",
        "correction": correction, "evidence": [f"{EMPLOYEE}:1"],
    }], "questions": []}


def test_the_audit_flow_reconciles_overlapping_findings_of_parallel_reviewers(tmp_path):
    root = payroll_repository(tmp_path)
    flow = FlowRunner("audit", root, {"<upcoming change>": "a second payroll form"})
    assert flow.run_step(7).returncode in (0, 1)
    assert flow.run_step(8).returncode == 0
    parallel = {
        "reasons-to-change": audit_judged("unit-serves-several-actors", "Split the reporting behavior out."),
        "business-rule-placement": audit_judged("entity-carries-framework-traits", "Remove the framework base class."),
    }
    command = flow.command_in(12, "--judged")
    paths = [flow.judged_path(12, **{"<group>": group}) for group in parallel]
    for path, document in zip(paths, parallel.values()):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document))
    both = flow.substituted(command, {"<group>": "reasons-to-change"})
    both += ["--judged", str(paths[1].relative_to(root))]
    overlapping = run_arch(both, root).stdout
    assert "Overlapping findings:" in overlapping
    assert all(f"(from {path.relative_to(root)})" in overlapping for path in paths)

    reconciled = flow.judged_path(12, **{"<group>": "reconciled"})
    shared = "Move the reporting behavior and its framework base class out of the entity."
    findings = [{**document["findings"][0], "correction": shared} for document in parallel.values()]
    reconciled.write_text(json.dumps({"findings": findings, "questions": []}))
    assert reconciled.name in numbered_steps(flow_file("audit").read_text())[13]
    rerun = flow.run(command, **{"<group>": "reconciled"}).stdout
    assert "Overlapping findings:" not in rerun
    assert f"{EMPLOYEE}; {EMPLOYEE}: Payroll and reporting changes edit the same unit. Fix: {shared}" in rerun


WORKING_FILES_SENTENCE = "Working files live under `.architecture/work/`"


def test_flows_and_pages_state_where_working_files_live_in_one_sentence():
    for path in [*flow_files(REVIEW_FLOWS), page_file("findings"), page_file("check"), page_file("applicable")]:
        text = " ".join(path.read_text().split())
        assert WORKING_FILES_SENTENCE in text, f"{path.name} does not say: {WORKING_FILES_SENTENCE}"


PACKET_PATHS = "Every packet opens with the absolute paths of the project root and the skill folder."
CONDITION_FIELDS = "(`id`, `targets`, `condition`)"


def flow_text(name: str) -> str:
    return " ".join(flow_file(name).read_text().split())


def test_every_flow_names_the_packet_paths_and_every_review_flow_the_judgment_conditions():
    for name in FLOW_NAMES:
        text = flow_text(name)
        assert PACKET_PATHS in text and "two levels above this file" in text, name
    for name in REVIEW_FLOWS:
        text = flow_text(name)
        assert CONDITION_FIELDS in text, f"{name} does not pass the judgment conditions"
        assert "Never edit a judged file by hand" in text, name
        assert "open question" in text, f"{name} does not return a late classification dispute"


def test_only_the_first_audit_reviewer_judges_the_cross_cutting_conditions():
    step = numbered_steps(flow_file("audit").read_text())[9]
    assert "Only the first reviewer dispatched also gets `references/rules/cross-cutting.md`" in step


def test_accepting_by_threshold_drops_check_findings_and_has_judged_ones_judged_again():
    for name in ["audit", "change-review"]:
        text = flow_text(name)
        assert "After a threshold, a finding from `check` no longer appears on the rerun" in text, name
        assert "whose condition names that knob is judged again by" in text, name
        assert "covering some rules leaves it with the rest" in text, name
        assert "arch model explain-thresholds" in text, name
        assert "no longer appears at all" not in text, name
    assert "condition names that knob needs the same reviewer to judge it again" in flow_text("plan-review")


def test_every_reviewer_reply_is_one_json_object_carrying_its_disputes():
    for name in REVIEW_FLOWS:
        text = flow_text(name)
        assert "returns one JSON object" in text, name
        assert "returns classification disputes, if any, then" not in text, name
        assert "on the run's first judged pass" in text.lower() or "on the first judged pass" in text, name
        assert "open questions" in text, name
        blocks = [json.loads(block) for block in JSON_BLOCK.findall(flow_file(name).read_text())]
        assert any("disputes" in block for block in blocks), name
    assert "only report its commands to the user" in flow_text("plan-review")


def test_the_audit_flow_names_the_reconciliation_packet_and_its_order():
    step = " ".join(numbered_steps(flow_file("audit").read_text())[13].split())
    for part in ["Reconcile before any acceptance", "a fresh `architecture-reviewer`, same prompt",
                 "the section as printed", "`.architecture/work/check.json`", "with its group's file",
                 "Its one JSON object"]:
        assert part in step, part


def test_every_review_flow_shows_the_non_blocking_sections():
    for name in REVIEW_FLOWS:
        assert "`Wider observations`" in flow_text(name) and "non-blocking" in flow_text(name), name
    for name in COMPARING_FLOWS:
        assert "`Inherited findings`" in flow_text(name), name
        assert "The verdict line is what the caller returns" in flow_text(name), name


def test_every_review_flow_hands_the_applicable_counts_to_findings_add():
    for name in REVIEW_FLOWS:
        lines = command_lines(flow_file(name))
        assert any(line.startswith("arch applicable") and f"--out {APPLICABLE_FILE}" in line for line in lines), name
        adds = [line for line in lines if line.startswith("arch findings add --flow")]
        assert adds and all(f"--applicable {APPLICABLE_FILE}" in line for line in adds), name


def test_an_acceptance_by_model_edit_validates_the_model_before_the_rerun():
    assert "then `arch model validate`, then steps 6, 7, 8, 12, and 14 again" in flow_text("audit")
    assert "Then run `arch model validate`, and steps 3, 5, and 10 again" in flow_text("change-review")


CLASSIFY_LOOPS = [("baseline", 5, 6, 7, 8), ("audit", 3, 4, 5, 6)]


def test_the_classify_loops_stop_only_when_a_pass_changes_neither_validate_nor_uncovered():
    for name, validate, _, loop, _ in CLASSIFY_LOOPS:
        steps = numbered_steps(flow_file(name).read_text())
        step = " ".join(steps[loop].split())
        assert "the list `arch uncovered` printed" in step, name
        assert f"go back to step {validate}" in step, name
        assert "The loop goes on while `validate` keeps a message or `uncovered` lists modules" in step, name
        assert "exactly as they were" in step and "the flow ends there" in step, name
        assert "unchanged, as what needs their decision" in step, name
        assert "`warning:`" in " ".join(steps[validate].split()), name


def refreshed_model_with_a_stale_port(tmp_path):
    root = copy_fixture("sound-small", tmp_path / "sound-small")
    model = root / "docs/architecture/architecture.json"
    document = json.loads(model.read_text())
    document["ports"].append({"at": "src/billing/gone.ts#Gone", "owner": "billing"})
    model.write_text(json.dumps(document, indent=2))
    init_repo(root)
    return root


@pytest.mark.parametrize("name, validate, uncovered, loop, collect", CLASSIFY_LOOPS)
def test_a_stale_port_the_classifier_removes_lets_the_flow_reach_collect(tmp_path, name, validate, uncovered,
                                                                         loop, collect):
    root = refreshed_model_with_a_stale_port(tmp_path)
    flow = FlowRunner(name, root, {"<path>": "src/billing/gone.ts", "<Symbol>": "Gone"})
    assert json.loads(flow.run_step(1).stdout)["model"] is True
    stale = flow.run_step(validate)
    assert stale.returncode == 2 and "model does not fit the code:" in stale.stderr
    listed = flow.run_step(uncovered)
    assert listed.returncode == 0 and listed.stdout.strip() == ""
    assert flow.run(flow.command_in(loop, "remove-port")).returncode == 0
    assert flow.run_step(validate).returncode == 0
    assert flow.run_step(uncovered).returncode == 0
    collected = flow.run_step(collect)
    assert collected.returncode == 0 and collected.stdout.startswith("collect: ")


def test_plan_review_reads_clarification_requests_from_the_printed_result():
    step = " ".join(numbered_steps(flow_file("plan-review").read_text())[10].split())
    assert "- clarification: <task>: <reason>" in step
    assert "check.json" not in step and '"clarification": true' not in step


def test_suggested_commands_quote_a_published_glob():
    text = (REFERENCES / "classification.md").read_text()
    assert "published='orders.*'" in text
    assert not re.search(r"published=[^'<\s`]*\*", text)
