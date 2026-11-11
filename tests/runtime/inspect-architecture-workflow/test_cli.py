import json
from pathlib import Path

from support import SKILL_DIR, run_arch, run_node


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


FLAGS_MODULE = (SKILL_DIR / "scripts" / "lib" / "cli" / "flags.mjs").as_uri()


def parse(argv: list[str], flags: dict) -> dict:
    script = (
        f"import {{ parseArgs }} from {json.dumps(FLAGS_MODULE)};"
        f"console.log(JSON.stringify(parseArgs({{ flags: {json.dumps(flags)} }}, {json.dumps(argv)}).flags));"
    )
    result = run_node(script, SKILL_DIR)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_list_flag_collects_every_repetition_in_order():
    flags = parse(["--upcoming", "a second store", "--upcoming", "another team"], {"upcoming": "list"})
    assert flags == {"upcoming": ["a second store", "another team"]}


def test_list_flag_needs_a_value(tmp_path: Path):
    result = run_arch(["findings", "add", "--upcoming"], tmp_path)
    assert result.returncode == 2 and "--upcoming needs a value" in result.stderr


def test_findings_without_a_subcommand_is_a_usage_error(tmp_path: Path):
    result = run_arch(["findings"], tmp_path)
    assert result.returncode == 2 and "add" in result.stderr and "list" in result.stderr
