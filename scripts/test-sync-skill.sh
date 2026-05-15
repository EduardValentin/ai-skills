#!/usr/bin/env bash

set -euo pipefail

SCRIPT_UNDER_TEST="${1:-scripts/sync-skill.sh}"

assert_file_contains() {
  local file="$1"
  local expected="$2"

  if ! grep -Fq "$expected" "$file"; then
    printf 'expected %s to contain: %s\n' "$file" "$expected" >&2
    exit 1
  fi
}

assert_missing() {
  local path="$1"

  if [ -e "$path" ]; then
    printf 'expected missing path: %s\n' "$path" >&2
    exit 1
  fi
}

tmp_root="$(mktemp -d)"
trap 'rm -rf "$tmp_root"' EXIT

repo="$tmp_root/repo"
home_dir="$tmp_root/home"
skill="demo-skill"

mkdir -p "$repo/skills/$skill/tests" "$home_dir"
printf 'canonical v1\n' > "$repo/skills/$skill/SKILL.md"
printf 'do not sync\n' > "$repo/skills/$skill/tests/.gitkeep"

AI_SKILLS_REPO="$repo" HOME="$home_dir" bash "$SCRIPT_UNDER_TEST" push "$skill"

assert_file_contains "$home_dir/.claude/skills/$skill/SKILL.md" "canonical v1"
assert_file_contains "$home_dir/.codex/skills/$skill/SKILL.md" "canonical v1"
assert_missing "$home_dir/.claude/skills/$skill/tests/.gitkeep"
assert_missing "$home_dir/.codex/skills/$skill/tests/.gitkeep"

printf 'codex v2\n' > "$home_dir/.codex/skills/$skill/SKILL.md"

AI_SKILLS_REPO="$repo" HOME="$home_dir" bash "$SCRIPT_UNDER_TEST" pull "$skill" codex

assert_file_contains "$repo/skills/$skill/SKILL.md" "codex v2"
assert_file_contains "$home_dir/.claude/skills/$skill/SKILL.md" "codex v2"

if AI_SKILLS_REPO="$repo" HOME="$home_dir" bash "$SCRIPT_UNDER_TEST" push "missing-skill" 2>"$tmp_root/missing.err"; then
  printf 'expected missing skill push to fail\n' >&2
  exit 1
fi

assert_file_contains "$tmp_root/missing.err" "missing canonical skill"
