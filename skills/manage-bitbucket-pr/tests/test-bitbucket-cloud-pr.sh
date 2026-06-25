#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
SCRIPT="$SKILL_DIR/scripts/bitbucket-cloud-pr.sh"
SKILL_DOC="$SKILL_DIR/SKILL.md"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local haystack=$1
  local needle=$2
  [[ "$haystack" == *"$needle"* ]] || fail "expected output to contain: $needle"
}

help_output=$("$SCRIPT" --help)
assert_contains "$help_output" "Usage:"
assert_contains "$help_output" "bitbucket-cloud-pr.sh [--dry-run] pr-details"
assert_contains "$help_output" "find-prs-for-branch"
assert_contains "$help_output" "update-description"
assert_contains "$help_output" "BITBUCKET_TOKEN"

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

output=$("$SCRIPT" --dry-run update-description acme widget 42 "Updated PR description")
assert_contains "$output" "METHOD=PUT"
assert_contains "$output" "URL=https://api.bitbucket.org/2.0/repositories/acme/widget/pullrequests/42"
assert_contains "$output" 'BODY={"description":"Updated PR description"}'

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
assert_contains "$skill_doc" "find-prs-for-branch"
assert_contains "$skill_doc" "Bitbucket-hosted pull request/repository"
assert_contains "$skill_doc" "testing or verifying PR behavior"
assert_contains "$skill_doc" "Git credential helper for \`bitbucket.org\`"
assert_contains "$skill_doc" "printf 'protocol=https\\nhost=bitbucket.org\\n\\n' | git credential fill"
assert_contains "$skill_doc" "codex-bitbucket-api-token"
assert_contains "$skill_doc" "try the next approved source before reporting a blocker"
assert_contains "$skill_doc" "testing or verifying PR behavior"
assert_contains "$skill_doc" "Do not nest fenced code blocks inside numbered or bulleted lists"
assert_contains "$skill_doc" "## Supported Hosts"
assert_contains "$skill_doc" "For self-hosted Bitbucket URLs, do not reuse Cloud mutation routes"

printf 'PASS: bitbucket-cloud-pr dry-run contract\n'
