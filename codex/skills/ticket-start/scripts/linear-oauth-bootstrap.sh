#!/usr/bin/env bash
# linear-oauth-bootstrap.sh — one-shot OAuth flow that mints a Linear
# bot access token + refresh token. Run once during initial setup
# (bot-identity.md runbook Step B), then run the printed
# `security add-generic-password` commands to store the tokens in
# macOS Keychain.
#
# Usage:
#   bash linear-oauth-bootstrap.sh <CLIENT_ID> <CLIENT_SECRET>

set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 <CLIENT_ID> <CLIENT_SECRET>" >&2
  echo "" >&2
  echo "Create the Linear OAuth app first at:" >&2
  echo "  https://linear.app/<workspace>/settings/api/applications/new" >&2
  echo "Set the redirect URI to http://localhost:8765/callback." >&2
  exit 1
fi

CLIENT_ID="$1"
CLIENT_SECRET="$2"
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

# Parse and present the tokens.
python3 - "$RESPONSE" <<'PYEOF'
import json
import shlex
import sys

try:
    data = json.loads(sys.argv[1])
except Exception as e:
    print(f"Failed to parse Linear response: {e}", file=sys.stderr)
    print(sys.argv[1], file=sys.stderr)
    sys.exit(1)

if "access_token" not in data:
    print("Linear OAuth exchange failed. Response:", file=sys.stderr)
    print(json.dumps(data, indent=2), file=sys.stderr)
    sys.exit(1)

access_token = data["access_token"]
refresh_token = data.get("refresh_token")

print("=" * 72)
print("Linear OAuth bootstrap succeeded.")
print("=" * 72)
print()
print(f"Access token  (first 12 / last 4): {access_token[:12]}...{access_token[-4:]}")
if refresh_token:
    print(f"Refresh token (first 12 / last 4): {refresh_token[:12]}...{refresh_token[-4:]}")
print()
print("Run these commands to store the tokens in macOS Keychain:")
print()
print(f"  security add-generic-password -s \"ai-skills.linear-bot.access-token\" -a \"$USER\" -w {shlex.quote(access_token)}")
if refresh_token:
    print(f"  security add-generic-password -s \"ai-skills.linear-bot.refresh-token\" -a \"$USER\" -w {shlex.quote(refresh_token)}")
print()
print("After storing, verify with:")
print()
print("  security find-generic-password -s \"ai-skills.linear-bot.access-token\" -a \"$USER\" -w")
print()
print("Then proceed to bot-identity.md runbook Step C (reconfigure Linear MCP).")
PYEOF
