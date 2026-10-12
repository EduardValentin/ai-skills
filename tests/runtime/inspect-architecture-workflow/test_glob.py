from pathlib import Path

from support import SKILL_DIR, run_node

GLOB = SKILL_DIR / "scripts" / "lib" / "glob.mjs"


def matches(path: str, glob: str) -> bool:
    script = (
        f"import {{ matchesAny }} from '{GLOB.as_posix()}';"
        f"process.stdout.write(String(matchesAny({path!r}, [{glob!r}])));"
    )
    result = run_node(script, Path.cwd())
    assert result.returncode == 0, result.stderr
    return result.stdout == "true"


def test_double_star_spans_directories():
    assert matches("packages/domain/src/orders/order.ts", "packages/domain/src/**")
    assert matches("packages/domain/src/order.ts", "packages/domain/src/**")


def test_single_star_stays_in_one_segment():
    assert matches("packages/domain/src/order.ts", "packages/domain/src/*.ts")
    assert not matches("packages/domain/src/orders/order.ts", "packages/domain/src/*.ts")


def test_brace_alternatives():
    assert matches("packages/db/src/index.ts", "packages/{db,config}/src/**")
    assert not matches("packages/ui/src/index.ts", "packages/{db,config}/src/**")


def test_suffix_pattern():
    assert matches("a/b/get-user-use-case.ts", "**/*-use-case.ts")
    assert not matches("a/b/get-user.ts", "**/*-use-case.ts")


def test_regex_characters_are_literal():
    assert matches("a/b.c/d.ts", "a/b.c/*.ts")
    assert not matches("a/bxc/d.ts", "a/b.c/*.ts")
