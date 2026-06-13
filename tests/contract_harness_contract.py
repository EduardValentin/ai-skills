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
type = "contains"
path = "README.md"
values = [
  "AI Skills",
  "Testing",
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
    if payload["assertion"][0]["values"] != ["AI Skills", "Testing"]:
        raise AssertionError("assertion array did not parse")
    scenario = payload["scenario"][0]
    if scenario["user_request"] != "Line one.\nLine two.":
        raise AssertionError("multiline scenario string did not parse")
    if scenario["criteria"][0]["key"] != "does_demo":
        raise AssertionError("scenario criteria did not parse")


if __name__ == "__main__":
    raise SystemExit(main())
