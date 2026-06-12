#!/usr/bin/env bash
# get-bot-gh-token.sh - mint a fresh GitHub App installation access token.
#
# Reads App ID, Installation ID, and the App's private key from macOS Keychain
# (entries: ai-skills.gh-bot.{app-id,installation-id,private-key}). Mints a
# 9-minute RS256 JWT, exchanges it for an installation access token, prints the
# token to stdout, and exits non-zero with useful stderr on failure.
#
# Usage:
#   GH_TOKEN=$(./get-bot-gh-token.sh) gh pr create ...

set -euo pipefail

KEYCHAIN_PREFIX="ai-skills.gh-bot"

read_keychain() {
  local service="$1"
  local raw
  if ! raw=$(security find-generic-password -s "$service" -a "$USER" -w 2>/dev/null); then
    echo "Missing Keychain entry: $service (account: $USER)" >&2
    echo "Configure the ai-skills.gh-bot Keychain entries before GitHub writes." >&2
    exit 1
  fi
  # macOS `security ... -w` returns hex-encoded output (no leading 0x) when the
  # stored value contains non-printable bytes such as newlines — which happens
  # for PEM-encoded private keys. Detect (long, all-hex, even-length) and decode.
  # Short alphanumeric IDs (App ID, Installation ID, etc.) come back as-is.
  if [[ "$raw" =~ ^[0-9a-f]+$ ]] && (( ${#raw} >= 200 )) && (( ${#raw} % 2 == 0 )); then
    printf '%s' "$raw" | xxd -r -p
  else
    printf '%s' "$raw"
  fi
}

APP_ID=$(read_keychain "${KEYCHAIN_PREFIX}.app-id")
INSTALLATION_ID=$(read_keychain "${KEYCHAIN_PREFIX}.installation-id")
PRIVATE_KEY=$(read_keychain "${KEYCHAIN_PREFIX}.private-key")

# Sanity-check the private key shape before we ask openssl to sign with it.
# A common footgun is pasting the .pem contents with escaped \n literals
# (instead of real newlines) into `security add-generic-password`. Catch
# that here with a targeted error pointing at the runbook rather than
# letting openssl emit a generic "Unable to load Private Key".
if ! printf '%s' "$PRIVATE_KEY" | grep -q "BEGIN .* PRIVATE KEY"; then
  echo "Private key in Keychain does not look like a PEM block." >&2
  echo "Re-import ai-skills.gh-bot.private-key from the GitHub App PEM file." >&2
  echo "Hint: pass the file contents in unquoted via \"\$(cat /path/to/key.pem)\", not as an escaped string." >&2
  exit 2
fi

# Mint a 9-minute JWT. GitHub App JWT lifetime hard ceiling is 10 minutes;
# 9 minutes gives a small buffer for clock skew between this host and GitHub.
NOW=$(date +%s)
EXP=$((NOW + 540))

b64url() {
  python3 -c 'import sys, base64; sys.stdout.write(base64.urlsafe_b64encode(sys.stdin.buffer.read()).rstrip(b"=").decode())'
}

HEADER_B64=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
PAYLOAD_B64=$(printf '{"iat":%d,"exp":%d,"iss":"%s"}' "$NOW" "$EXP" "$APP_ID" | b64url)
SIGNING_INPUT="${HEADER_B64}.${PAYLOAD_B64}"

# Sign with openssl. The private key is fed via process substitution so it
# never lands on disk as a temp file. Wrap in an `if !` so set -e doesn't
# short-circuit the friendly diagnostic; let openssl's own error reach
# stderr (it complains about PEM format, never echoes key material).
if ! SIG=$(printf '%s' "$SIGNING_INPUT" \
  | openssl dgst -sha256 -sign <(printf '%s' "$PRIVATE_KEY") -binary \
  | b64url); then
  echo "JWT signing failed. Is the private key in Keychain a valid PEM-encoded RSA private key?" >&2
  exit 2
fi

if [[ -z "$SIG" ]]; then
  echo "JWT signing produced empty signature." >&2
  exit 2
fi

JWT="${SIGNING_INPUT}.${SIG}"

# Exchange the JWT for an installation access token (~1h lifetime).
# --connect-timeout caps the TCP handshake; --max-time caps total request
# time. Without these, a flaky network can hang the agent indefinitely.
RESPONSE=$(curl -sS -X POST \
  --connect-timeout 10 \
  --max-time 30 \
  -H "Authorization: Bearer $JWT" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/app/installations/${INSTALLATION_ID}/access_tokens")

# Extract the token via python3 (no jq dependency).
TOKEN=$(printf '%s' "$RESPONSE" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception as e:
    print(f"Failed to parse GitHub response: {e}", file=sys.stderr)
    sys.exit(1)
if "token" not in data:
    print("GitHub did not return a token. Response:", file=sys.stderr)
    print(json.dumps(data, indent=2), file=sys.stderr)
    sys.exit(1)
print(data["token"])
') || exit 3

if [[ -z "$TOKEN" ]]; then
  echo "Empty token from GitHub. Raw response:" >&2
  echo "$RESPONSE" >&2
  exit 3
fi

printf '%s\n' "$TOKEN"
