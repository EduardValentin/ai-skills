#!/usr/bin/env bash
# get-bot-gh-token.sh - mint a fresh GitHub App installation access token.
#
# Prefers GH_BOT_APP_ID, GH_BOT_INSTALLATION_ID, and a private key read from
# GH_BOT_PRIVATE_KEY_PATH. Unset values fall back to macOS Keychain entries
# ai-skills.gh-bot.{app-id,installation-id,private-key}, using
# GH_BOT_KEYCHAIN_ACCOUNT or USER as the account. Mints a 9-minute RS256 JWT,
# exchanges it for an installation token, and prints only that token to stdout.
#
# Usage: capture stdout in an ephemeral variable and expose it to one GitHub
# write command without printing or persisting it.

set -euo pipefail

KEYCHAIN_PREFIX="ai-skills.gh-bot"

read_keychain() {
  local service="$1"
  local env_name="$2"
  local account="${GH_BOT_KEYCHAIN_ACCOUNT:-${USER:-}}"
  local raw
  if [[ -z "$account" ]]; then
    echo "$env_name is unset and no Keychain account is available." >&2
    echo "Set $env_name or GH_BOT_KEYCHAIN_ACCOUNT before GitHub writes." >&2
    exit 1
  fi
  if ! raw=$(security find-generic-password -s "$service" -a "$account" -w 2>/dev/null); then
    echo "$env_name is unset and Keychain fallback is unavailable for $service (account: $account)." >&2
    echo "Set $env_name explicitly or configure the current ai-skills.gh-bot Keychain entry." >&2
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

APP_ID="${GH_BOT_APP_ID:-}"
if [[ -z "$APP_ID" ]]; then
  APP_ID=$(read_keychain "${KEYCHAIN_PREFIX}.app-id" "GH_BOT_APP_ID")
fi

INSTALLATION_ID="${GH_BOT_INSTALLATION_ID:-}"
if [[ -z "$INSTALLATION_ID" ]]; then
  INSTALLATION_ID=$(read_keychain "${KEYCHAIN_PREFIX}.installation-id" "GH_BOT_INSTALLATION_ID")
fi

if [[ -n "${GH_BOT_PRIVATE_KEY_PATH:-}" ]]; then
  if [[ ! -f "$GH_BOT_PRIVATE_KEY_PATH" || ! -r "$GH_BOT_PRIVATE_KEY_PATH" ]]; then
    echo "GH_BOT_PRIVATE_KEY_PATH must name a readable private-key file." >&2
    exit 1
  fi
  PRIVATE_KEY=$(<"$GH_BOT_PRIVATE_KEY_PATH")
  PRIVATE_KEY_SOURCE="GH_BOT_PRIVATE_KEY_PATH"
else
  PRIVATE_KEY=$(read_keychain "${KEYCHAIN_PREFIX}.private-key" "GH_BOT_PRIVATE_KEY_PATH")
  PRIVATE_KEY_SOURCE="Keychain fallback"
fi

# Sanity-check the private key shape before we ask openssl to sign with it.
# A common footgun is pasting the .pem contents with escaped \n literals
# (instead of real newlines) into `security add-generic-password`. Catch
# that here with a targeted error pointing at the runbook rather than
# letting openssl emit a generic "Unable to load Private Key".
if ! printf '%s' "$PRIVATE_KEY" | grep -q "BEGIN .* PRIVATE KEY"; then
  echo "Private key from $PRIVATE_KEY_SOURCE does not look like a PEM block." >&2
  echo "Point GH_BOT_PRIVATE_KEY_PATH at the GitHub App PEM file or repair the Keychain fallback entry." >&2
  exit 2
fi

# Mint a 9-minute JWT. GitHub App JWT lifetime hard ceiling is 10 minutes;
# 9 minutes gives a small buffer for clock skew between this host and GitHub.
NOW=$(date +%s)
EXP=$((NOW + 540))

b64url() {
  python3 -I -S -c 'import sys, base64; sys.stdout.write(base64.urlsafe_b64encode(sys.stdin.buffer.read()).rstrip(b"=").decode())'
}

SIGNING_INPUT=$(
  GH_BOT_JWT_IAT="$NOW" \
    GH_BOT_JWT_EXP="$EXP" \
    GH_BOT_JWT_ISS="$APP_ID" \
    python3 -I -S -c '
import base64
import json
import os

def encode(value):
    raw = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")

header = {"alg": "RS256", "typ": "JWT"}
payload = {
    "iat": int(os.environ["GH_BOT_JWT_IAT"]),
    "exp": int(os.environ["GH_BOT_JWT_EXP"]),
    "iss": os.environ["GH_BOT_JWT_ISS"],
}
print(f"{encode(header)}.{encode(payload)}", end="")
'
)

# Sign with openssl. The private key is fed via process substitution so it
# never lands on disk as a temp file. Wrap in an `if !` so set -e doesn't
# short-circuit the friendly diagnostic; let openssl's own error reach
# stderr (it complains about PEM format, never echoes key material).
if ! SIG=$(printf '%s' "$SIGNING_INPUT" \
  | openssl dgst -sha256 -sign <(printf '%s' "$PRIVATE_KEY") -binary \
  | b64url); then
  echo "JWT signing failed. The configured file or Keychain fallback must contain a valid PEM-encoded RSA private key." >&2
  exit 2
fi

if [[ -z "$SIG" ]]; then
  echo "JWT signing produced empty signature." >&2
  exit 2
fi

JWT="${SIGNING_INPUT}.${SIG}"

# Exchange the JWT for an installation access token (~1h lifetime).
# Python reads the JWT from stdin, keeping it out of the child process argv.
RESPONSE=$(
  printf '%s' "$JWT" \
    | GH_BOT_HTTP_INSTALLATION_ID="$INSTALLATION_ID" python3 -I -S -c '
import base64
import http.client
import json
import os
import re
import sys
import urllib.error
import urllib.request

installation_id = os.environ["GH_BOT_HTTP_INSTALLATION_ID"]
if re.fullmatch(r"[1-9][0-9]*", installation_id, flags=re.ASCII) is None:
    print(
        "GH_BOT_INSTALLATION_ID must be a positive decimal integer.",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    jwt = sys.stdin.buffer.read().decode("ascii")
except UnicodeDecodeError:
    print("Generated GitHub App JWT was not ASCII.", file=sys.stderr)
    raise SystemExit(1)
if not jwt:
    print("Generated GitHub App JWT was empty.", file=sys.stderr)
    raise SystemExit(1)


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise urllib.error.HTTPError(
            request.full_url,
            code,
            "GitHub token exchange redirects are disabled",
            headers,
            response,
        )


request = urllib.request.Request(
    f"https://api.github.com/app/installations/{installation_id}/access_tokens",
    data=b"",
    headers={
        "Authorization": f"Bearer {jwt}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-skills-github-app-token-helper/1",
        "X-GitHub-Api-Version": "2022-11-28",
    },
    method="POST",
)
opener = urllib.request.build_opener(RejectRedirects())
try:
    with opener.open(request, timeout=30) as response:
        status = response.status
        response_body = response.read()
except urllib.error.HTTPError as error:
    status = error.code
    response_body = error.read()
    error.close()
except (OSError, urllib.error.URLError, http.client.HTTPException):
    print("GitHub token exchange request failed.", file=sys.stderr)
    raise SystemExit(1)

# Frame status and bytes so the structured parser can reject token-like error bodies.
envelope = {
    "status": status,
    "body": base64.b64encode(response_body).decode("ascii"),
}
sys.stdout.write(json.dumps(envelope, separators=(",", ":")))
'
)

# Extract the token via python3 (no jq dependency).
TOKEN=$(printf '%s' "$RESPONSE" | python3 -I -S -c '
import base64
import json
import sys

try:
    envelope = json.load(sys.stdin)
    status = envelope["status"]
    encoded_body = envelope["body"]
    if type(status) is not int or not isinstance(encoded_body, str):
        raise ValueError("invalid response envelope shape")
    response_body = base64.b64decode(encoded_body, validate=True)
except Exception as e:
    print(f"Failed to parse GitHub response envelope: {e}", file=sys.stderr)
    sys.exit(1)

if not 200 <= status < 300:
    print(
        f"GitHub token exchange returned HTTP {status}; "
        "no installation token was accepted.",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    data = json.loads(response_body)
except (UnicodeDecodeError, json.JSONDecodeError) as e:
    print(f"Failed to parse GitHub response: {e}", file=sys.stderr)
    sys.exit(1)

token = data.get("token") if isinstance(data, dict) else None
if not isinstance(token, str) or not token:
    print(
        "GitHub token exchange successful response did not contain a usable token.",
        file=sys.stderr,
    )
    sys.exit(1)
print(token)
') || exit 3

if [[ -z "$TOKEN" ]]; then
  echo "Empty token from GitHub." >&2
  exit 3
fi

printf '%s\n' "$TOKEN"
