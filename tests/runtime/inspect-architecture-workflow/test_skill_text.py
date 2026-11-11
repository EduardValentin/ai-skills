"""The router, the three flows, and the command pages agree with the command they describe."""

import json
import re
import shlex
from functools import cache

from support import SKILL_DIR, copy_fixture, git, init_repo, run_arch, run_node

SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES = SKILL_DIR / "references"
FLOWS_DIR = REFERENCES / "flows"
COMMANDS_DIR = REFERENCES / "commands"
FLOW_NAMES = ["audit", "change-review", "plan-review"]
REVIEW_FLOWS = ["change-review", "plan-review"]
PAGE_NAMES = ["collect", "check", "applicable", "query", "uncovered", "model", "findings"]
PAGE_SECTIONS = ["## Synopsis", "## Flags", "## Exit codes", "## Output", "## Example"]
MAX_BODY_LINES = 45
MAX_FLOW_LINES = 90
NO_MODEL_LINE = "no architecture model; run a baseline audit to enable the full review"
DESCRIPTION = (
    "Use for a dedicated architecture audit, an architecture review of a diff, or an architecture review of an "
    "implementation plan or spec before approval, passing the flow name `audit`, `change-review`, or `plan-review`."
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
PLACEHOLDER = re.compile(r"<[A-Za-z][A-Za-z ]*>")
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


def flow_files() -> list:
    return [flow_file(name) for name in FLOW_NAMES]


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


def test_flows_do_not_reference_each_other():
    for path in flow_files():
        lines = [line for line in path.read_text().splitlines() if line.strip()]
        for other in FLOW_NAMES:
            if other != path.stem:
                assert f"{other}.md" not in path.read_text(), f"{path.name} names {other}.md"
        for line in lines[:-1]:
            assert "commands/" not in line, f"{path.name} names a command page outside its last line: {line}"
        assert lines[-1].startswith(FAILURE_LINE), f"{path.name} does not end with '{FAILURE_LINE}'"


def test_flow_command_lines_use_declared_flags():
    problems = unparsable(flow_files())
    assert not problems, "\n".join(problems)


def test_review_flows_never_run_model_init_or_collect():
    for name in REVIEW_FLOWS:
        for line in command_lines(flow_file(name)):
            assert not line.startswith(("arch model init", "arch model migrate", "arch collect")), f"{name}: {line}"


def test_plan_review_never_edits_the_model():
    for line in command_lines(flow_file("plan-review")):
        tokens = line.split()
        if tokens[1] == "model" and len(tokens) > 2:
            assert tokens[2] in READ_ONLY_MODEL_SUBCOMMANDS, f"plan review edits the model: {line}"
        assert tokens[1] != "collect", f"plan review rewrites the current picture: {line}"


def test_review_flows_stop_with_ok_without_a_model():
    for name in REVIEW_FLOWS:
        step = numbered_steps(flow_file(name).read_text()).get(2, "")
        assert NO_MODEL_LINE in step and "`OK`" in step, f"{name}: step 2 does not stop with OK without a model"


def test_flows_name_their_agents():
    for name in FLOW_NAMES:
        assert "architecture-reviewer" in flow_file(name).read_text(), name
    for name in ["audit", "change-review"]:
        assert "architecture-classifier" in flow_file(name).read_text(), name
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


def test_every_flow_shows_judged_findings_in_a_code_block():
    for path in flow_files():
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
    applicable = json.loads(flow.run_step(3).stdout)
    assert applicable["review"] is True and "humble-objects" in applicable["groups"]
    assert flow.run_step(5).returncode in (0, 1)
    flow.judged_path(10).write_text(json.dumps(CHANGE_REVIEW_JUDGED))
    assert "Verdict: SHOULD_CHANGE: 0 blocker, 2 major" in flow.run_step(10).stdout

    star = flow.command_in(11, "'*'")
    assert flow.run(star, **{"<target>": "src/web/payroll-controller.ts", "<R>": "R20"}).returncode == 0
    assert flow.run(star, **{"<target>": "src/domain/clock.ts#Clock", "<R>": "R13"}).returncode == 0
    flow.run_step(5)
    accepted = flow.run_step(10).stdout
    assert "Dropped: 2 (2 covered by an exception)" in accepted
    assert "Verdict: INCOMPLETE" in accepted

    assert flow.run(flow.command_in(11, "set-rule"), **{"<R>": "R13"}).returncode == 0
    flow.run_step(5)
    assert "Verdict: OK" in flow.run_step(10).stdout


def test_the_audit_flow_classifies_every_module_before_collecting(tmp_path):
    root = project_with_an_unclassified_module(tmp_path)
    flow = FlowRunner("audit", root, {
        "<name>": "reports", "<globs>": "src/reports/**", "<component>": "reports", "<pattern>": "**",
        "<kind>": "presenter", "<group>": "humble-objects", "<upcoming change>": "a second payroll form",
    })
    assert json.loads(flow.run_step(1).stdout)["model"] is True
    assert flow.run_step(5).returncode == 0, "validate passes although a module is unclassified"
    uncovered = flow.run_step(6)
    assert uncovered.returncode == 1 and uncovered.stdout.split() == ["src/reports/summary.ts"]

    for fragment in ["add-component", "classify"]:
        assert flow.run(flow.command_in(7, fragment)).returncode == 0
    assert flow.run_step(5).returncode == 0
    reclassified = flow.run_step(6)
    assert reclassified.returncode == 0 and reclassified.stdout.strip() == ""

    assert flow.run_step(8).returncode == 0
    assert flow.run_step(9).returncode in (0, 1)
    assert json.loads(flow.run_step(10).stdout)["review"] is True
    flow.judged_path(13).write_text(json.dumps({"findings": [], "questions": []}))
    assert "# Architecture audit" in flow.run_step(13).stdout
    assert "## Ranked by change volatility" in flow.run_step(14).stdout


WORKING_FILES_SENTENCE = "Working files live under `.architecture/work/`"


def test_flows_and_pages_state_where_working_files_live_in_one_sentence():
    for path in [*flow_files(), page_file("findings"), page_file("check"), page_file("applicable")]:
        text = " ".join(path.read_text().split())
        assert WORKING_FILES_SENTENCE in text, f"{path.name} does not say: {WORKING_FILES_SENTENCE}"
