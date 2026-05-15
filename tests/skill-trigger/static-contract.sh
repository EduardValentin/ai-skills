#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
SCENARIOS="$SCRIPT_DIR/scenarios.tsv"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

contains() {
  local haystack=$1
  local needle=$2
  [[ "$haystack" == *"$needle"* ]]
}

assert_contains() {
  local haystack=$1
  local needle=$2
  local context=$3
  if ! contains "$haystack" "$needle"; then
    fail "$context must contain: $needle"
  fi
}

assert_not_contains() {
  local haystack=$1
  local needle=$2
  local context=$3
  if contains "$haystack" "$needle"; then
    fail "$context must not contain: $needle"
  fi
}

field_terms() {
  local field=$1
  [[ -n "$field" ]] || return 0
  printf '%s' "$field" | tr '|' '\n'
}

extract_frontmatter_value() {
  local key=$1
  local file=$2
  awk -v key="$key" '
    NR == 1 && $0 == "---" { in_fm = 1; next }
    in_fm && $0 == "---" { exit }
    in_fm && index($0, key ":") == 1 {
      value = substr($0, length(key) + 2)
      sub(/^[[:space:]]+/, "", value)
      gsub(/^"|"$/, "", value)
      print value
      exit
    }
  ' "$file"
}

[[ -f "$SCENARIOS" ]] || fail "missing trigger scenario registry: $SCENARIOS"

seen_ids=$(mktemp)
covered_skills=$(mktemp)
trap 'rm -f "$seen_ids" "$covered_skills"' EXIT
scenario_count=0

while IFS=$'\t' read -r id skill prompt description_terms skill_terms forbidden_terms; do
  [[ -z "${id:-}" || "${id:0:1}" == "#" ]] && continue

  [[ -n "${skill:-}" ]] || fail "$id is missing skill"
  [[ -n "${prompt:-}" ]] || fail "$id is missing prompt"

  ! grep -Fxq "$id" "$seen_ids" || fail "duplicate scenario id: $id"
  printf '%s\n' "$id" >> "$seen_ids"

  skill_file="$REPO_ROOT/skills/$skill/SKILL.md"
  [[ -f "$skill_file" ]] || fail "$id references missing canonical skill: skills/$skill/SKILL.md"

  frontmatter_name=$(extract_frontmatter_value name "$skill_file")
  [[ "$frontmatter_name" == "$skill" ]] || fail "$id expected skill name '$skill' but SKILL.md declares '$frontmatter_name'"

  description=$(extract_frontmatter_value description "$skill_file")
  [[ "$description" == Use\ when* || "$description" == \"Use\ when* ]] || fail "$skill description must start with 'Use when'"

  skill_doc=$(cat "$skill_file")

  while IFS= read -r term; do
    [[ -z "$term" ]] && continue
    assert_contains "$description" "$term" "$id description"
  done < <(field_terms "${description_terms:-}")

  while IFS= read -r term; do
    [[ -z "$term" ]] && continue
    assert_contains "$skill_doc" "$term" "$id skill document"
  done < <(field_terms "${skill_terms:-}")

  while IFS= read -r term; do
    [[ -z "$term" ]] && continue
    assert_not_contains "$skill_doc" "$term" "$id skill document"
    assert_not_contains "$prompt" "$term" "$id prompt"
  done < <(field_terms "${forbidden_terms:-}")

  printf '%s\n' "$skill" >> "$covered_skills"
  scenario_count=$((scenario_count + 1))
done < "$SCENARIOS"

[[ "$scenario_count" -gt 0 ]] || fail "no trigger scenarios found in $SCENARIOS"

while IFS= read -r skill_file; do
  skill_dir=$(dirname "$skill_file")
  skill=$(basename "$skill_dir")
  grep -Fxq "$skill" "$covered_skills" || fail "canonical skill missing trigger scenario: $skill"
done < <(find "$REPO_ROOT/skills" -mindepth 2 -maxdepth 2 -name SKILL.md -type f | sort)

printf 'PASS: %s skill trigger scenarios satisfy static contracts\n' "$scenario_count"
