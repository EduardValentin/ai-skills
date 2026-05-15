#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
SCENARIOS="$SCRIPT_DIR/scenarios.tsv"
AGENT_COMMAND=${SKILL_TRIGGER_AGENT_COMMAND:-}
SCENARIO_FILTER=${SKILL_TRIGGER_SCENARIO:-}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

usage() {
  cat <<'USAGE'
Usage:
  SKILL_TRIGGER_AGENT_COMMAND='<command reading stdin>' tests/skill-trigger/behavioral-pressure.sh

Optional:
  SKILL_TRIGGER_SCENARIO='<scenario-id>' to run one scenario.

The agent command receives a prompt on stdin and must print its response on stdout.
The response must include the expected skill name from the scenario registry.
USAGE
}

[[ "${1:-}" != "--help" ]] || {
  usage
  exit 0
}

[[ -n "$AGENT_COMMAND" ]] || {
  usage >&2
  fail "SKILL_TRIGGER_AGENT_COMMAND is required for behavioral pressure tests"
}

[[ -f "$SCENARIOS" ]] || fail "missing trigger scenario registry: $SCENARIOS"

skill_index() {
  while IFS= read -r skill_file; do
    name=$(awk '
      NR == 1 && $0 == "---" { in_fm = 1; next }
      in_fm && $0 == "---" { exit }
      in_fm && /^name:/ {
        value = substr($0, 6)
        sub(/^[[:space:]]+/, "", value)
        print value
      }
    ' "$skill_file")
    description=$(awk '
      NR == 1 && $0 == "---" { in_fm = 1; next }
      in_fm && $0 == "---" { exit }
      in_fm && /^description:/ {
        value = substr($0, 13)
        sub(/^[[:space:]]+/, "", value)
        gsub(/^"|"$/, "", value)
        print value
      }
    ' "$skill_file")
    printf -- '- %s: %s\n' "$name" "$description"
  done < <(find "$REPO_ROOT/skills" -mindepth 2 -maxdepth 2 -name SKILL.md -type f | sort)
}

make_prompt() {
  local scenario_id=$1
  local expected_skill=$2
  local user_prompt=$3

  cat <<PROMPT
You are testing skill-trigger selection before any task work begins.

Available skills:
$(skill_index)

User request:
$user_prompt

Return only this format:
SELECTED_SKILLS: comma-separated skill names
RATIONALE: one short sentence

Select every skill that should be loaded before acting. Do not perform the user request.
The expected regression guard for this scenario is that "$expected_skill" appears in SELECTED_SKILLS.
Scenario id: $scenario_id
PROMPT
}

scenario_count=0

while IFS=$'\t' read -r id skill prompt description_terms skill_terms forbidden_terms; do
  [[ -z "${id:-}" || "${id:0:1}" == "#" ]] && continue
  [[ -z "$SCENARIO_FILTER" || "$SCENARIO_FILTER" == "$id" ]] || continue

  scenario_count=$((scenario_count + 1))
  request=$(make_prompt "$id" "$skill" "$prompt")
  response=$(printf '%s\n' "$request" | sh -c "$AGENT_COMMAND")

  [[ "$response" == *"$skill"* ]] || {
    printf 'Response for %s:\n%s\n' "$id" "$response" >&2
    fail "$id did not select expected skill: $skill"
  }

  while IFS= read -r term; do
    [[ -z "$term" ]] && continue
    [[ "$response" != *"$term"* ]] || {
      printf 'Response for %s:\n%s\n' "$id" "$response" >&2
      fail "$id repeated forbidden rationalization term: $term"
    }
  done < <(printf '%s' "${forbidden_terms:-}" | tr '|' '\n')

  printf 'PASS: %s selected %s\n' "$id" "$skill"
done < "$SCENARIOS"

[[ "$scenario_count" -gt 0 ]] || fail "no behavioral scenarios matched"

printf 'PASS: %s behavioral skill trigger scenarios\n' "$scenario_count"
