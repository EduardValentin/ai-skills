#!/usr/bin/env python3
"""Contract tests for the efficient Codex behavioral-test command shim."""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from codex_agent_command import build_command


def main() -> int:
    try:
        test_default_command_uses_efficient_model_and_reasoning()
        test_role_specific_overrides_win()
        test_shared_overrides_apply_when_role_specific_absent()
    except Exception as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print("PASS: Codex agent command contract")
    return 0


def test_default_command_uses_efficient_model_and_reasoning() -> None:
    with clean_env():
        command = build_command("judge")

    assert "-m" in command
    assert command[command.index("-m") + 1] == "gpt-5.4-mini"
    assert '-c' in command
    assert 'model_reasoning_effort="low"' in command
    assert "--ephemeral" in command


def test_role_specific_overrides_win() -> None:
    with clean_env(), patched_env(
        CODEX_TEST_MODEL="gpt-5.4-mini",
        CODEX_JUDGE_MODEL="gpt-5.4",
        CODEX_TEST_REASONING_EFFORT="low",
        CODEX_JUDGE_REASONING_EFFORT="medium",
    ):
        command = build_command("judge")

    assert command[command.index("-m") + 1] == "gpt-5.4"
    assert 'model_reasoning_effort="medium"' in command


def test_shared_overrides_apply_when_role_specific_absent() -> None:
    with clean_env(), patched_env(
        CODEX_TEST_MODEL="gpt-5.4",
        CODEX_TEST_REASONING_EFFORT="medium",
    ):
        command = build_command("actor")

    assert command[command.index("-m") + 1] == "gpt-5.4"
    assert 'model_reasoning_effort="medium"' in command


@contextmanager
def clean_env() -> Iterator[None]:
    keys = [key for key in os.environ if key.startswith(("CODEX_ACTOR_", "CODEX_JUDGE_", "CODEX_TEST_"))]
    original = {key: os.environ[key] for key in keys}
    for key in keys:
        os.environ.pop(key, None)
    try:
        yield
    finally:
        for key in keys:
            os.environ.pop(key, None)
        os.environ.update(original)


@contextmanager
def patched_env(**values: str) -> Iterator[None]:
    original = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == "__main__":
    raise SystemExit(main())
