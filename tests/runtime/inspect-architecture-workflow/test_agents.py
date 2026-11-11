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
