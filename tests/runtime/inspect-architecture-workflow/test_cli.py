from pathlib import Path

from support import run_arch


def test_unknown_subcommand_exits_one(tmp_path: Path):
    result = run_arch(["frobnicate"], tmp_path)
    assert result.returncode == 1
    assert "unknown subcommand: frobnicate" in result.stderr


def test_no_subcommand_prints_usage(tmp_path: Path):
    result = run_arch([], tmp_path)
    assert result.returncode == 1
    assert "usage: arch <graph|diff|query|assess|uncovered|model|readme-summary>" in result.stderr
