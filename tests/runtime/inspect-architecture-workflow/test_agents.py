"""The two architecture agents keep the house structure and return what the command reads."""

import json
import re
import tomllib

from support import REPO_ROOT, SKILL_DIR, run_node
from test_agnostic_guard import WORD_PATTERN

AGENTS_DIR = REPO_ROOT / "agents"
REVIEWER = AGENTS_DIR / "architecture-reviewer.md"
CLASSIFIER = AGENTS_DIR / "architecture-classifier.md"
NEW_AGENTS = ["architecture-reviewer", "architecture-classifier"]
HOUSE_SECTIONS = [
    "## Identity", "## Mandate", "## Inputs You May Receive", "## Output Format", "## Forbidden Behaviors",
    "## Escalation",
]
REMOVED_NAMES = [
    "architecture-coordinator", "architecture-evaluator", "architecture-code-auditor",
    "software-architecture-principles",
]
CALLER_GROUPS = ["ticket-workflow", "implementation-workflow", "inspect-architecture-workflow"]
READ_ONLY_TOOLS = ["Read", "Glob", "Grep", "Bash"]
JSON_BLOCK = re.compile(r"^```json\n(.*?)^```", re.MULTILINE | re.DOTALL)

SCHEMA_SCRIPT = """
import { JUDGED_SCHEMA } from "./scripts/lib/findings/intake.mjs";
import { proposalSchema } from "./scripts/lib/checks/proposal.mjs";
import { validateShape } from "./scripts/lib/model/validate-shape.mjs";
const documents = JSON.parse(process.argv[1]);
const schemaOf = (document) => ("findings" in document ? JUDGED_SCHEMA : proposalSchema());
console.log(JSON.stringify({
  findingFields: Object.keys(JUDGED_SCHEMA.properties.findings.items.properties),
  problems: documents.map((document) => validateShape(document, schemaOf(document))),
}));
"""


def schema_report(documents: list[dict]) -> dict:
    result = run_node(SCHEMA_SCRIPT, SKILL_DIR, json.dumps(documents))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def json_blocks(path) -> list[dict]:
    return [json.loads(block) for block in JSON_BLOCK.findall(path.read_text())]


def test_both_agents_keep_the_house_sections():
    for path in [REVIEWER, CLASSIFIER]:
        text = path.read_text()
        positions = [text.find(f"\n{section}\n") for section in HOUSE_SECTIONS]
        assert all(position > 0 for position in positions), f"{path.name} lacks a house section"
        assert positions == sorted(positions), f"{path.name} orders its house sections differently"


def test_both_agents_name_no_language_or_tool():
    for path in [REVIEWER, CLASSIFIER]:
        for index, line in enumerate(path.read_text().splitlines(), start=1):
            assert not WORD_PATTERN.search(line), f"{path.name}:{index}: {line.strip()}"


def test_both_agents_find_their_queries_on_the_query_page():
    for path in [REVIEWER, CLASSIFIER]:
        assert "`references/commands/query.md`" in path.read_text(), path.name


def test_reviewer_shapes_are_the_ones_the_command_reads():
    blocks = json_blocks(REVIEWER)
    assert {"findings" in block for block in blocks} == {True, False}, "expected a judged and a proposal shape"
    report = schema_report(blocks)
    assert report["problems"] == [[] for _ in blocks], report["problems"]
    judged = next(block for block in blocks if "findings" in block)
    text = REVIEWER.read_text()
    for field in report["findingFields"]:
        assert f'"{field}"' in text or f"`{field}`" in text, f"the reviewer never names the field {field}"
    assert set(judged["findings"][0]) <= set(report["findingFields"])


def test_reviewer_never_supplies_what_the_judgment_sets():
    for block in json_blocks(REVIEWER):
        for finding in block.get("findings", []):
            assert not {"rules", "defect", "severity"} & set(finding), finding


def test_classifier_returns_model_commands_with_reasons():
    text = CLASSIFIER.read_text()
    for command in ["arch model add-component", "arch model classify", "arch model add-port"]:
        assert command in text, f"the classifier never proposes {command}"
    assert "## Open questions" in text


def test_manifest_declares_the_two_agents_read_only_without_a_preloaded_skill():
    manifest = tomllib.loads((AGENTS_DIR / "manifest.toml").read_text())
    agents = {agent["id"]: agent for agent in manifest["agent"]}
    for name in NEW_AGENTS:
        agent = agents[name]
        assert agent["source"] == f"{name}.md" and (AGENTS_DIR / agent["source"]).is_file()
        assert agent["groups"] == CALLER_GROUPS
        assert "preload_skills" not in agent
        assert agent["claude"]["tools"] == READ_ONLY_TOOLS
        assert agent["codex"]["sandbox_mode"] == "read-only"
    assert not set(REMOVED_NAMES) & set(agents)


def mentions_of_removed_names(root) -> list[str]:
    mentions = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        text = path.read_text(errors="ignore")
        mentions += [f"{path.relative_to(REPO_ROOT)}: {name}" for name in REMOVED_NAMES if name in text]
    return mentions


def test_no_agent_mentions_a_removed_agent():
    mentions = mentions_of_removed_names(AGENTS_DIR)
    assert not mentions, "\n".join(mentions)


def test_no_skill_mentions_a_removed_agent_or_skill():
    assert not (REPO_ROOT / "skills" / "abilities" / "software-architecture-principles").exists()
    mentions = mentions_of_removed_names(REPO_ROOT / "skills")
    assert not mentions, "\n".join(mentions)


DROP_VERBS = r"(?:drop|discard|omit|remove|delete|skip|hide)s?"
DROP = re.compile(
    rf"\b{DROP_VERBS}(?:,? (?:or |and )?(?:accept|downgrade|{DROP_VERBS}),?)* (?:the |a |any |each |this )?"
    r"(?:judged )?findings?\b",
    re.IGNORECASE,
)
PROHIBITION = re.compile(r"\b(do not|never)\b", re.IGNORECASE)
SINGLE_OBJECT = "Return exactly one JSON object and nothing after it."
PROPOSAL_OBJECT = "the proposal is the one JSON object, and nothing comes after it"


def test_neither_agent_is_told_to_drop_a_finding():
    for path in [REVIEWER, CLASSIFIER]:
        for sentence in re.split(r"(?<=[.:])\s", path.read_text()):
            if DROP.search(sentence):
                assert PROHIBITION.search(sentence), f"{path.name}: {sentence.strip()}"


def test_reviewer_returns_one_json_object_and_nothing_after_it():
    text = " ".join(REVIEWER.read_text().split())
    assert SINGLE_OBJECT in text
    assert PROPOSAL_OBJECT in text
    assert "Do not read the skill's scripts." in text


def test_reviewer_holds_every_structural_correction_to_r8():
    text = " ".join(REVIEWER.read_text().split())
    for element in ["an interface", "a layer", "a component", "a factory", "a request or response model",
                    "a published surface", "a forbidden edge", "a recorded group"]:
        assert element in text, element
    order = ["remove what is unneeded", "use what already exists", "record a decision in the model", "add structure"]
    positions = [text.find(step) for step in order]
    assert all(position > 0 for position in positions) and positions == sorted(positions), positions


def test_classifier_returns_only_commands_and_open_questions():
    text = CLASSIFIER.read_text()
    output = text[text.index("## Output Format"):text.index("## Forbidden Behaviors")]
    assert re.findall(r"^## (\w[\w ]*)$", output, re.MULTILINE) == ["Output Format", "Commands", "Open questions"]
    assert "`references/classification.md` gives the full syntax of `arch model classify`" in text


def test_reviewer_returns_disputes_inside_its_one_object():
    text = " ".join(REVIEWER.read_text().split())
    assert "Write nothing before it either: classification disputes go inside that object, never beside it." in text
    assert '"disputes": [ { "path": "<unit path>", "reason":' in text
    assert "under the heading `Classification disputes`" not in text


def test_reviewer_never_counts_the_port_r4_requires_as_unjustified():
    text = " ".join(REVIEWER.read_text().split())
    assert ("The port R4 (Dependencies point toward policy) requires in front of a store, a vendor, or another "
            "external agency is never an abstraction without reason") in text


def test_reviewer_skips_each_unrecorded_concept_on_its_own():
    text = " ".join(REVIEWER.read_text().split())
    for clause in ["no published-surface judgment on a project whose model declares no published surface",
                   "no forbidden-edge judgment on one that records no forbidden edge",
                   "no cohesion-group judgment on one that records no cohesion group"]:
        assert clause in text, clause


GATE_FILES = [
    *sorted(path for path in SKILL_DIR.rglob("*") if path.is_file() and "__pycache__" not in path.parts),
    REVIEWER, CLASSIFIER,
    *(REPO_ROOT / "skills" / "workflows" / name / "SKILL.md"
      for name in ["implementation-workflow", "ticket-requirements-gathering", "ticket-workflow"]),
]
RETIRED_GATE = re.compile(
    r"notReviewed|arch applicable[^\n]*--full|Review needed|`review` is|not reviewed for a contained change"
)


def test_no_architecture_text_mentions_the_retired_review_gate():
    mentions = [
        f"{path.relative_to(REPO_ROOT)}:{index}: {line.strip()}"
        for path in GATE_FILES
        for index, line in enumerate(path.read_text(errors="ignore").splitlines(), start=1)
        if RETIRED_GATE.search(line)
    ]
    assert not mentions, "\n".join(mentions)
