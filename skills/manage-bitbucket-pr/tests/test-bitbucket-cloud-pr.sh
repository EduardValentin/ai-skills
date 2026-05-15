#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
SCRIPT="$SKILL_DIR/scripts/bitbucket-cloud-pr.sh"
SKILL_DOC="$SKILL_DIR/SKILL.md"
REFERENCE_DOC="$SKILL_DIR/references/cloud-capabilities-reference.md"
PRESSURE_SCENARIOS="$SKILL_DIR/tests/pressure-scenarios.md"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local haystack=$1
  local needle=$2
  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain: $needle"
}

output=$("$SCRIPT" --dry-run pr-details acme widget 42)
assert_contains "$output" "METHOD=GET"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests/42"

output=$("$SCRIPT" --dry-run find-prs-for-branch acme widget "feature/auth")
assert_contains "$output" "METHOD=GET"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests?q=source.branch.name+%3D+%22feature%2Fauth%22+AND+state+%3D+%22OPEN%22"

output=$("$SCRIPT" --dry-run read-comments acme widget 42)
assert_contains "$output" "METHOD=GET"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests/42/comments"

output=$("$SCRIPT" --dry-run post-comment acme widget 42 "QA passed on staging")
assert_contains "$output" "METHOD=POST"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests/42/comments"
assert_contains "$output" 'BODY={"content":{"raw":"QA passed on staging"}}'

output=$("$SCRIPT" --dry-run merge acme widget 42)
assert_contains "$output" "METHOD=POST"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests/42/merge"

output=$("$SCRIPT" --dry-run merge-status acme widget 42 abc123)
assert_contains "$output" "METHOD=GET"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests/42/merge/task-status/abc123"

output=$(BITBUCKET_TOKEN=secret-token "$SCRIPT" --dry-run pr-details acme widget 42)
[[ "$output" != *"secret-token"* ]] || fail "dry-run output must not expose token values"

auth_output=$(mktemp)
trap 'rm -f "$auth_output"' EXIT
if "$SCRIPT" pr-details acme widget 42 >"$auth_output" 2>&1; then
  fail "expected non-dry-run without credentials to fail"
fi
assert_contains "$(cat "$auth_output")" "Set BITBUCKET_TOKEN or BITBUCKET_EMAIL + BITBUCKET_API_TOKEN"

skill_doc=$(cat "$SKILL_DOC")
reference_doc=$(cat "$REFERENCE_DOC")
pressure_scenarios=$(cat "$PRESSURE_SCENARIOS")
docs_text="${skill_doc}
${reference_doc}"
assert_contains "$skill_doc" "find-prs-for-branch"
assert_contains "$skill_doc" "Bitbucket-hosted pull request/repository"
assert_contains "$skill_doc" "testing or verifying PR behavior"
assert_contains "$skill_doc" "Git credential helper for \`bitbucket.org\`"
assert_contains "$skill_doc" "direct HTTPS request"
assert_contains "$reference_doc" "Basic auth"
assert_contains "$pressure_scenarios" "Testing a Bitbucket PR"
assert_contains "$pressure_scenarios" "Bitbucket repository context should trigger the skill"
assert_contains "$pressure_scenarios" "test, verify, review, summarize, inspect comments"

credential_helper_count=$(printf '%s' "$docs_text" | rg -o "Git credential helper" | wc -l | tr -d ' ')
[[ "$credential_helper_count" == "1" ]] || fail "credential-helper fallback should be documented once across skill and reference"

[[ "$skill_doc" != *"Basic auth"* ]] || fail "skill should delegate Basic/Bearer auth mechanics to the Cloud reference"

printf 'PASS: bitbucket-cloud-pr dry-run contract\n'
