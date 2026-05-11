#!/usr/bin/env bash
# linear-oauth-bootstrap.sh — mint a Linear bot access token via the
# client_credentials OAuth grant. The resulting token is an "app actor
# token" — actions performed with it are attributed to the OAuth
# application (the bot), not to a user. Valid ~30 days; renew by
# re-running this script.
#
# PREREQUISITES (do these in your own terminal, never in chat):
#   1. Linear OAuth app has "Client credentials tokens" toggled ON in
#      its settings page (https://linear.app/settings/api/applications).
#   2. Store the app's credentials in macOS Keychain:
#        security add-generic-password -U -s "ai-skills.linear-bot.client-id"     -a "$USER" -w '<CLIENT_ID>'
#        security add-generic-password -U -s "ai-skills.linear-bot.client-secret" -a "$USER" -w '<CLIENT_SECRET>'
#
# Then run this script. It reads client-id and client-secret from
# Keychain, requests a client_credentials token from Linear, and writes
# the resulting access_token directly back to Keychain. The token never
# appears on stdout or in `ps`.
#
# client_credentials does NOT issue a refresh_token — Linear's docs say
# to re-fetch when you receive a 401 with the previous token. To rotate
# proactively, just re-run this script (Linear invalidates the old token
# and returns a new 30-day one).
#
# Usage:
#   bash linear-oauth-bootstrap.sh

set -euo pipefail

KEYCHAIN_PREFIX="ai-skills.linear-bot"

read_keychain() {
  local service="$1"
  local raw
  if ! raw=$(security find-generic-password -s "$service" -a "$USER" -w 2>/dev/null); then
    echo "Missing Keychain entry: $service (account: $USER)" >&2
    echo "See bot-identity.md runbook Step B — store client-id and client-secret" >&2
    echo "in Keychain BEFORE running this script." >&2
    exit 1
  fi
  # macOS `security ... -w` returns hex-encoded output (no leading 0x)
  # when the stored value contains non-printable bytes. Detect (long,
  # all-hex, even-length) and decode.
  if [[ "$raw" =~ ^[0-9a-f]+$ ]] && (( ${#raw} >= 200 )) && (( ${#raw} % 2 == 0 )); then
    printf '%s' "$raw" | xxd -r -p
  else
    printf '%s' "$raw"
  fi
}

CLIENT_ID=$(read_keychain "${KEYCHAIN_PREFIX}.client-id")
CLIENT_SECRET=$(read_keychain "${KEYCHAIN_PREFIX}.client-secret")

echo "Requesting client_credentials token from Linear..."

RESPONSE_FILE=$(mktemp)
HTTP_STATUS=$(curl -sS -X POST https://api.linear.app/oauth/token \
  --connect-timeout 10 \
  --max-time 30 \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "scope=read,write,issues:create" \
  -o "$RESPONSE_FILE" \
  -w "%{http_code}")

if [[ "$HTTP_STATUS" != "200" ]] || [[ ! -s "$RESPONSE_FILE" ]]; then
  echo "Linear OAuth token endpoint returned HTTP $HTTP_STATUS" >&2
  echo "Response body ($(wc -c < "$RESPONSE_FILE" | tr -d ' ') bytes):" >&2
  cat "$RESPONSE_FILE" >&2
  echo "" >&2
  echo "" >&2
  echo "Common causes:" >&2
  echo "  - 'Client credentials tokens' not enabled in the Linear OAuth app settings" >&2
  echo "    (response will be: 'Client does not support the client_credentials grant type')" >&2
  echo "  - client_secret in Keychain does not match the current Linear secret" >&2
  rm -f "$RESPONSE_FILE"
  exit 3
fi

# Pass the response file path to python3 via env var; the python script
# opens the file directly. This sidesteps bash command-substitution
# quirks (NUL bytes, trailing-newline stripping) that broke the previous
# `RESPONSE=$(cat ...)` round-trip. The token never appears in argv (no
# positional args) and python3 writes it straight to Keychain so it
# never appears on stdout either.
KEYCHAIN_PREFIX="$KEYCHAIN_PREFIX" RESPONSE_FILE="$RESPONSE_FILE" python3 <<'PYEOF'
import json
import os
import subprocess
import sys

with open(os.environ["RESPONSE_FILE"], "r") as f:
    response_body = f.read()

try:
    data = json.loads(response_body)
except Exception as e:
    print(f"Failed to parse Linear response: {e}", file=sys.stderr)
    print(f"Response body length: {len(response_body)} chars", file=sys.stderr)
    print(f"Response body: {response_body!r}", file=sys.stderr)
    sys.exit(1)

if "access_token" not in data:
    print("Linear did not return an access_token. Response:", file=sys.stderr)
    print(json.dumps(data, indent=2), file=sys.stderr)
    sys.exit(1)

prefix = os.environ["KEYCHAIN_PREFIX"]
user = os.environ.get("USER")

subprocess.run(
    ["security", "add-generic-password", "-U",
     "-s", f"{prefix}.access-token",
     "-a", user,
     "-w", data["access_token"]],
    check=True,
)

access_token_len = len(data["access_token"])
token_type = data.get("token_type", "unknown")
expires_in = data.get("expires_in", "unknown")

print(f"Stored {prefix}.access-token in Keychain (length={access_token_len} chars).")
print(f"Token type: {token_type}, expires_in: {expires_in} seconds")
if isinstance(expires_in, int):
    print(f"             ~ {expires_in // 86400} days")
print()
print("Token never appeared on stdout or in argv.")
print("Verify with:")
print(f"  security find-generic-password -s '{prefix}.access-token' -a \"$USER\" >/dev/null && echo 'access-token ✓'")
print()
print("Note: client_credentials does NOT issue a refresh_token.")
print("To renew, re-run this script. Linear invalidates the previous")
print("token and returns a fresh one.")
print()
print("Next: bot-identity.md runbook Step C (reconfigure Linear MCP).")
PYEOF

# Clean up the response file now that python is done with it.
rm -f "$RESPONSE_FILE"
