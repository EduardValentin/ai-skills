"""Every script loads, and none breaks the line-length rule."""

from support import SKILL_DIR, run_node

SCRIPTS = SKILL_DIR / "scripts"
MAX_LINE = 120


def library_scripts():
    return sorted((SCRIPTS / "lib").rglob("*.mjs"))


def test_every_library_script_loads():
    failures = []
    for script in library_scripts():
        result = run_node(f"await import({script.as_uri()!r});", SCRIPTS)
        if result.returncode != 0:
            failures.append(f"{script.relative_to(SCRIPTS)}: {result.stderr.strip().splitlines()[0]}")
    assert not failures, "scripts that fail to load:\n" + "\n".join(failures)


def test_no_script_line_exceeds_the_limit():
    long_lines = [
        f"{script.relative_to(SCRIPTS)}:{number}: {len(line)} characters"
        for script in sorted(SCRIPTS.rglob("*.mjs"))
        for number, line in enumerate(script.read_text().splitlines(), start=1)
        if len(line) > MAX_LINE
    ]
    assert not long_lines, "lines over 120 characters:\n" + "\n".join(long_lines)
