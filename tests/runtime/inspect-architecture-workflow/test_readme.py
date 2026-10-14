from pathlib import Path

from support import FIXTURE_FLAGS, copy_fixture, run_arch


def test_readme_summary_is_replaced_between_markers(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    readme = root / "docs/architecture/README.md"
    readme.write_text("# Architecture\n\nintro\n\n<!-- arch:summary -->\nold\n<!-- /arch:summary -->\n\ntail\n")
    result = run_arch(["readme-summary", *FIXTURE_FLAGS], root)
    assert result.returncode == 0, result.stderr
    text = readme.read_text()
    assert "old" not in text
    assert "Components: 3, units: 9, edges: 15," in text
    assert "| C1 domain | 4 | 4 | 0 |" in text
    assert text.endswith("<!-- /arch:summary -->\n\ntail\n")
    # idempotent
    run_arch(["readme-summary", *FIXTURE_FLAGS], root)
    assert readme.read_text() == text


def test_readme_without_markers_fails(tmp_path: Path):
    root = copy_fixture("payroll", tmp_path / "p")
    (root / "docs/architecture/README.md").write_text("# Architecture\n")
    result = run_arch(["readme-summary", *FIXTURE_FLAGS], root)
    assert result.returncode == 1 and "no arch:summary markers" in result.stderr
