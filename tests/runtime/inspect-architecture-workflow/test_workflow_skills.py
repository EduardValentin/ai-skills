"""The workflow skills that call the architecture flows stop without a baseline and default to one reviewer."""

import re

from support import REPO_ROOT

WORKFLOWS = REPO_ROOT / "skills" / "workflows"
IMPLEMENTATION = WORKFLOWS / "implementation-workflow" / "SKILL.md"
REQUIREMENTS = WORKFLOWS / "ticket-requirements-gathering" / "SKILL.md"
TICKET = WORKFLOWS / "ticket-workflow" / "SKILL.md"
CALLERS = [IMPLEMENTATION, REQUIREMENTS, TICKET]
NOT_RUN = "`architecture review: not run, no baseline`"
OTHER_REVIEWERS = [
    "`acceptance-criteria-reviewer`", "`design-system-reviewer`", "`security-reviewer`", "`performance-reviewer`",
    "architecture plan review", "architecture change review",
]
NO_MODEL_PASSES = re.compile(
    r"no architecture model; run a baseline audit|no-model line|\"no architecture model\" line|baseline audit",
    re.IGNORECASE,
)


def flat(path) -> str:
    return " ".join(path.read_text().split())


def between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def test_implementation_workflow_selects_only_the_cleanliness_reviewer_by_default():
    defaults = between(flat(IMPLEMENTATION), "ask the user once with these defaults:", "Record the answer")
    assert defaults == "`code-cleanliness-reviewer` selected; every other reviewer offered and not selected."


def test_requirements_gathering_selects_only_the_cleanliness_reviewer_by_default():
    defaults = between(flat(REQUIREMENTS), "Present the list with these defaults:", "The user may change any")
    selected = between(defaults, "selected,", "; not selected,")
    assert selected == "`code-cleanliness-reviewer`"
    not_selected = defaults.split("; not selected,", 1)[1]
    for reviewer in OTHER_REVIEWERS:
        assert reviewer in not_selected, reviewer


def test_no_workflow_preselects_a_reviewer_by_what_the_change_touches():
    for path in [IMPLEMENTATION, REQUIREMENTS]:
        text = flat(path)
        assert "`design-system-reviewer` selected when" not in text, path.parent.name
        assert "selected when the repository keeps a design system" not in text, path.parent.name


def test_every_caller_stops_at_the_no_baseline_gate_and_records_the_choice():
    for path in CALLERS:
        text = flat(path)
        assert "with `baseline` now and then continue with the" in text, path.parent.name
        assert "or continue without an architecture" in text, path.parent.name
        assert NOT_RUN in text, path.parent.name
        assert "never passed silently" in text or "Never pass that gate silently" in text, path.parent.name
        assert "neither re-enter" in text or "neither re-enters" in text, path.parent.name


def test_no_caller_says_a_missing_model_passes():
    for path in CALLERS:
        match = NO_MODEL_PASSES.search(path.read_text())
        assert not match, f"{path.parent.name}: {match.group(0)}"
