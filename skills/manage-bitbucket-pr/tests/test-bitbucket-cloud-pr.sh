#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(cd "$SCRIPT_DIR/.." && pwd)
SCRIPT="$SKILL_DIR/scripts/bitbucket-cloud-pr.sh"

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

printf 'PASS: bitbucket-cloud-pr dry-run contract\n'
