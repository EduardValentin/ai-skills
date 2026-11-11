from pathlib import Path

from support import run_arch


def test_unknown_flag_is_a_usage_error(tmp_path: Path):
    result = run_arch(["check", "--bsae", "main"], tmp_path)
    assert result.returncode == 2
    assert "unknown flag --bsae" in result.stderr and "--base" in result.stderr


def test_value_flag_without_value_is_a_usage_error(tmp_path: Path):
    result = run_arch(["check", "--base", "--json"], tmp_path)
    assert result.returncode == 2 and "--base needs a value" in result.stderr


def test_unknown_subcommand_lists_the_known_ones(tmp_path: Path):
    result = run_arch(["grph"], tmp_path)
    assert result.returncode == 2 and "collect" in result.stderr


def test_missing_subcommand_is_a_usage_error(tmp_path: Path):
    result = run_arch([], tmp_path)
    assert result.returncode == 2 and "usage: arch" in result.stderr


def test_unbuilt_subcommand_reports_not_implemented(tmp_path: Path):
    result = run_arch(["findings"], tmp_path)
    assert result.returncode == 2 and "not implemented" in result.stderr
