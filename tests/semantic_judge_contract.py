#!/usr/bin/env python3
"""Contract tests for the shared semantic judge helper."""

from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

from semantic_judge import SemanticCriterion, assert_forbidden_terms, judge_response


def main() -> int:
    try:
        test_accepts_passing_judgment()
        test_rejects_failed_criterion()
        test_rejects_non_json_judgment()
        test_ignores_empty_forbidden_terms()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: semantic judge contract")
    return 0


def test_accepts_passing_judgment() -> None:
    command = fake_judge_command(
        '{"passes": true, "criteria": {"delegates_work": true}, "failures": []}'
    )
    result = judge_response(
        judge_command=command,
        scenario_id="passing",
        scenario_prompt="Coordinate approved work.",
        response="I will delegate implementation.",
        criteria=(SemanticCriterion("delegates_work", "Implementation is delegated."),),
    )
    assert result.passes is True


def test_rejects_failed_criterion() -> None:
    command = fake_judge_command(
        '{"passes": false, "criteria": {"delegates_work": false}, "failures": ["implemented inline"]}'
    )
    try:
        judge_response(
            judge_command=command,
            scenario_id="failing",
            scenario_prompt="Coordinate approved work.",
            response="I will implement inline.",
            criteria=(SemanticCriterion("delegates_work", "Implementation is delegated."),),
        )
    except AssertionError as error:
        message = str(error)
        assert "delegates_work" in message
        assert "implemented inline" in message
        return
    raise AssertionError("expected failed criterion to raise")


def test_rejects_non_json_judgment() -> None:
    command = fake_judge_command("looks fine")
    try:
        judge_response(
            judge_command=command,
            scenario_id="invalid-json",
            scenario_prompt="Coordinate approved work.",
            response="I will delegate implementation.",
            criteria=(SemanticCriterion("delegates_work", "Implementation is delegated."),),
        )
    except AssertionError as error:
        assert "valid JSON" in str(error)
        return
    raise AssertionError("expected non-JSON judgment to raise")


def test_ignores_empty_forbidden_terms() -> None:
    assert_forbidden_terms("anything at all", ("",), "empty term")


def fake_judge_command(output: str) -> str:
    handle, path_text = tempfile.mkstemp(prefix="semantic-judge-", suffix=".py")
    path = Path(path_text)
    with os.fdopen(handle, "w", encoding="utf-8") as script:
        script.write(
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "sys.stdin.read()\n"
            f"print({output!r})\n"
        )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return f"{sys.executable} {path}"


if __name__ == "__main__":
    raise SystemExit(main())
