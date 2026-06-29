#!/usr/bin/env python3
"""Contract checks for the generic TOML contract harness."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT / "tests"))

from contract_harness import load_toml_payload, run_contract_suite  # noqa: E402


def main() -> int:
    try:
        check_toml_payload_parser()
        check_toml_structural_assertions()
        run_contract_suite(REPO_ROOT / "tests" / "contracts" / "behavioral-coverage.toml")
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: contract harness contract")
    return 0


def check_toml_payload_parser() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sample.toml"
        path.write_text(
            '''
[suite]
name = "sample"

[[assertion]]
type = "toml_suite_require_fields"
path = "README.md"
fields = [
  "name",
  "skill",
]

[[scenario]]
id = "demo"
user_request = """
Line one.
Line two.
"""
expected_auto_discovery = ["demo-skill"]

[[scenario.criteria]]
key = "does_demo"
description = "The response does the demo."
'''.lstrip(),
            encoding="utf-8",
        )
        payload = load_toml_payload(path)

    if payload["suite"]["name"] != "sample":
        raise AssertionError("suite table did not parse")
    if payload["assertion"][0]["fields"] != ["name", "skill"]:
        raise AssertionError("assertion array did not parse")
    scenario = payload["scenario"][0]
    if scenario["user_request"].rstrip("\n") != "Line one.\nLine two.":
        raise AssertionError("multiline scenario string did not parse")
    if scenario["criteria"][0]["key"] != "does_demo":
        raise AssertionError("scenario criteria did not parse")


def check_toml_structural_assertions() -> None:
    with tempfile.TemporaryDirectory(dir=REPO_ROOT) as tmpdir:
        tmp_path = Path(tmpdir)
        sample = tmp_path / "sample-behavioral.toml"
        sample.write_text(
            '''
[suite]
name = "sample"
skill = "demo-skill"
judge_context = "Judge the demo skill."

[[scenario]]
id = "demo"
user_request = "Demo."

[[scenario.criteria]]
key = "demo_key"
description = "Demo criterion."
'''.lstrip(),
            encoding="utf-8",
        )

        contract = tmp_path / "contract.toml"
        contract.write_text(
            f'''
[[assertion]]
type = "toml_suite_require_fields_for_each"
glob = "{sample.relative_to(REPO_ROOT)}"
path = "{{path}}"
fields = [
  "name",
  "skill",
  "judge_context",
]

[[assertion]]
type = "toml_scenarios_require_field_for_each"
glob = "{sample.relative_to(REPO_ROOT)}"
path = "{{path}}"
field = "user_request"

[[assertion]]
type = "toml_scenario_criteria_require_field_for_each"
glob = "{sample.relative_to(REPO_ROOT)}"
path = "{{path}}"
field = "description"
'''.lstrip(),
            encoding="utf-8",
        )
        run_contract_suite(contract)


if __name__ == "__main__":
    raise SystemExit(main())
