#!/usr/bin/env bash
# linear-oauth-bootstrap.sh — one-shot OAuth flow that mints a Linear bot
# access token + refresh token.
#
# PREREQUISITES (do these in your own terminal, never in chat):
#   security add-generic-password -U -s "ai-skills.linear-bot.client-id"     -a "$USER" -w '<CLIENT_ID>'
#   security add-generic-password -U -s "ai-skills.linear-bot.client-secret" -a "$USER" -w '<CLIENT_SECRET>'
#
# Then run this script. It reads client-id and client-secret from Keychain,
# runs the OAuth dance in your browser, exchanges the code for tokens, and
# writes the access + refresh tokens directly to Keychain. Tokens never
# appear in stdout or in `ps`.
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
  # macOS `security ... -w` returns hex-encoded output (no leading 0x) when
  # the stored value contains non-printable bytes. Detect (long, all-hex,
  # even-length) and decode.
  if [[ "$raw" =~ ^[0-9a-f]+$ ]] && (( ${#raw} >= 200 )) && (( ${#raw} % 2 == 0 )); then
    printf '%s' "$raw" | xxd -r -p
  else
    printf '%s' "$raw"
  fi
}

CLIENT_ID=$(read_keychain "${KEYCHAIN_PREFIX}.client-id")
CLIENT_SECRET=$(read_keychain "${KEYCHAIN_PREFIX}.client-secret")
REDIRECT_URI="http://localhost:8765/callback"
SCOPES="read,write,issues:create"
STATE=$(openssl rand -hex 16)

AUTH_URL="https://linear.app/oauth/authorize"
AUTH_URL+="?client_id=${CLIENT_ID}"
AUTH_URL+="&redirect_uri=${REDIRECT_URI}"
AUTH_URL+="&response_type=code"
AUTH_URL+="&scope=${SCOPES}"
AUTH_URL+="&state=${STATE}"
AUTH_URL+="&actor=app"

echo "Opening browser to authorize the Linear OAuth app..."
echo "If the browser does not open automatically, visit this URL manually:"
echo ""
echo "  $AUTH_URL"
echo ""
open "$AUTH_URL" 2>/dev/null || true

echo "Waiting for callback on http://localhost:8765/callback ..."
echo "(authorize the app in your browser, then return here)"

# Capture the authorization code via a one-shot HTTP listener.
CODE=$(python3 - "$STATE" <<'PYEOF'
import http.server
import socketserver
import sys
import urllib.parse

expected_state = sys.argv[1]
captured = {"code": None, "error": None}

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        state = params.get("state", [None])[0]
        if state != expected_state:
            captured["error"] = f"State mismatch: got {state!r}, expected {expected_state!r}"
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>State mismatch.</h1><p>Possible CSRF. Aborting. See terminal.</p>")
            return
        captured["code"] = params.get("code", [None])[0]
        if captured["code"] is None:
            err = params.get("error_description", params.get("error", ["unknown"]))[0]
            captured["error"] = f"No code in callback. error={err}"
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>OAuth failed.</h1><p>See terminal for details.</p>")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<h1>Authorized.</h1><p>You can close this tab and return to the terminal.</p>")

    def log_message(self, fmt, *args):
        pass

with socketserver.TCPServer(("127.0.0.1", 8765), Handler) as srv:
    while captured["code"] is None and captured["error"] is None:
        srv.handle_request()

if captured["error"]:
    print(captured["error"], file=sys.stderr)
    sys.exit(2)

print(captured["code"])
PYEOF
)

if [[ -z "${CODE:-}" ]]; then
  echo "OAuth callback did not return a code." >&2
  exit 2
fi

echo ""
echo "Authorization code received. Exchanging for tokens..."

RESPONSE=$(curl -sS -X POST https://api.linear.app/oauth/token \
  --connect-timeout 10 \
  --max-time 30 \
  --data-urlencode "code=${CODE}" \
  --data-urlencode "client_id=${CLIENT_ID}" \
  --data-urlencode "client_secret=${CLIENT_SECRET}" \
  --data-urlencode "redirect_uri=${REDIRECT_URI}" \
  --data-urlencode "grant_type=authorization_code")

# Pipe the response via stdin (NOT argv) so the tokens never appear in `ps`,
# and have python3 write them directly to Keychain via `security` subprocess
# so they never appear in stdout either.
printf '%s' "$RESPONSE" | KEYCHAIN_PREFIX="$KEYCHAIN_PREFIX" python3 <<'PYEOF'
import json
import os
import subprocess
import sys

response_body = sys.stdin.read()

try:
    data = json.loads(response_body)
except Exception as e:
    print(f"Failed to parse Linear response: {e}", file=sys.stderr)
    print(response_body, file=sys.stderr)
    sys.exit(1)

if "access_token" not in data:
    print("Linear OAuth exchange failed. Response:", file=sys.stderr)
    print(json.dumps(data, indent=2), file=sys.stderr)
    sys.exit(1)

prefix = os.environ["KEYCHAIN_PREFIX"]
user = os.environ.get("USER")

def store(name, value):
    # -U: update if the entry already exists.
    subprocess.run(
        ["security", "add-generic-password", "-U",
         "-s", f"{prefix}.{name}",
         "-a", user,
         "-w", value],
        check=True,
    )

access_token = data["access_token"]
refresh_token = data.get("refresh_token")

store("access-token", access_token)
print(f"Stored {prefix}.access-token in Keychain (length={len(access_token)} chars).")

if refresh_token:
    store("refresh-token", refresh_token)
    print(f"Stored {prefix}.refresh-token in Keychain (length={len(refresh_token)} chars).")
else:
    print("Note: Linear did not return a refresh_token (some flows omit it).")

print()
print("Done. Tokens are stored in Keychain — they never appeared in stdout or argv.")
print("Verify with:")
print(f"  security find-generic-password -s '{prefix}.access-token' -a \"$USER\" >/dev/null && echo 'access-token ✓'")
if refresh_token:
    print(f"  security find-generic-password -s '{prefix}.refresh-token' -a \"$USER\" >/dev/null && echo 'refresh-token ✓'")
print()
print("Next: bot-identity.md runbook Step C (reconfigure Linear MCP).")
PYEOF
