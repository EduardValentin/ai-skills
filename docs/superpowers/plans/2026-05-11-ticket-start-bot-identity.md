# Ticket-Start Bot Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated bot identity (GitHub App + Linear OAuth Application) to the personal-workflow path of the `ticket-start` skill so that PRs, commits, and Linear ticket transitions surface attributed to the bot, not the user.

**Architecture:** Two new helper scripts under `scripts/` mint a GitHub installation token (runtime) and run a one-shot Linear OAuth bootstrap (one-time setup). A new `bot-identity.md` documents the full runbook and the three Setup activation checks. `personal-workflow.md` gets a "Bot Identity" section pointing at `bot-identity.md`. `SKILL.md` gets one new Setup sub-step. Everything mirrors to `claude/skills/ticket-start/` and both install paths (`~/.codex/skills/`, `~/.claude/skills/`).

**Tech Stack:** Markdown, Bash 3+, macOS `security` CLI for Keychain, `openssl` (RS256 JWT signing), `python3` (base64url encoding and HTTP listener for the OAuth dance), `gh` CLI (consumes `GH_TOKEN` env var), Linear OAuth 2.0.

**Spec reference:** `docs/superpowers/specs/2026-05-11-ticket-start-bot-identity-design.md`. Read it before starting Task 1.

---

## Plan-level decisions locked

These are operational details deferred from the spec to this plan:

1. **JWT signing approach.** `openssl dgst -sha256 -sign` with the PEM key piped via process substitution `<(printf '%s' "$KEY")`. Base64url encoding in Python (no `jq`/`npm`/`pip` dep). JWT lifetime: 540 seconds (9 minutes; safely under GitHub's 10-minute hard ceiling, leaves buffer for clock skew).
2. **Linear OAuth listener.** `python3 http.server` with a one-shot `BaseHTTPRequestHandler`, listening on `127.0.0.1:8765`. CSRF protected via `state` parameter (16 random hex bytes from `openssl rand`). Single-handle loop; exits as soon as the callback lands or an error is captured.
3. **Linear MCP `viewer` probe.** Documented in `bot-identity.md` as a procedure the main agent runs; the script set does *not* probe Linear (that needs the agent's MCP tool). The script set only handles GitHub token mint and the OAuth bootstrap.
4. **`personal-workflow.md` "Bot Identity" section placement.** Right after `## Ticket Intake (Linear)`, before `## Scoped Reading`. Short — 3–5 lines — pointing at `bot-identity.md`.
5. **`SKILL.md` Setup sub-step insertion.** Inserted as a new step 2 in the `## Setup` section, between worktree creation (current step 1) and repository-instructions reading (currently step 2). Subsequent steps (currently 2–6) renumber to 3–7.
6. **Script content shared between trees.** Physical copy from codex to claude (no symlinks; install paths break symlinks). Verification via `diff -r` after each mirror operation.
7. **`bot-identity.md` is a single file** (not split into runbook + activation + failure modes). Full content lives inline; the spec's §4 (runbook), §5 (activation flow), and §5.4 (failure modes) all collapse into this one doc.

---

## File structure (what changes)

**New files (created in both trees):**

| File | Purpose |
|---|---|
| `codex/skills/ticket-start/bot-identity.md` | Runbook + activation flow + failure modes |
| `codex/skills/ticket-start/scripts/get-bot-gh-token.sh` | Runtime: mint GitHub installation token |
| `codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh` | One-time: Linear OAuth code-for-token exchange |
| `claude/skills/ticket-start/bot-identity.md` | Mirror |
| `claude/skills/ticket-start/scripts/get-bot-gh-token.sh` | Mirror |
| `claude/skills/ticket-start/scripts/linear-oauth-bootstrap.sh` | Mirror |

**Modified files:**

| File | Change |
|---|---|
| `codex/skills/ticket-start/personal-workflow.md` | Add "Bot Identity (REQUIRED for this workflow)" section after `## Ticket Intake (Linear)` |
| `codex/skills/ticket-start/SKILL.md` | Insert new Setup step 2 ("Activate bot identity"); renumber subsequent steps |
| `claude/skills/ticket-start/personal-workflow.md` | Same as codex (mirror) |
| `claude/skills/ticket-start/SKILL.md` | Same as codex (mirror) |

**Install-path mirrors (every change above):**
- `~/.codex/skills/ticket-start/` ← `codex/skills/ticket-start/`
- `~/.claude/skills/ticket-start/` ← `claude/skills/ticket-start/`

**Unchanged files:** all six agent role-prompts, `bug-fix-loop.md`, `self-improvement.md`, `react-parity.md`, `verification.md`, `job-workflow.md`, `agents/openai.yaml`.

---

## Tasks

### Task 1: Author `scripts/get-bot-gh-token.sh`

**Files:**
- Create: `codex/skills/ticket-start/scripts/get-bot-gh-token.sh`

- [ ] **Step 1: Create scripts directory + write the file**

Working directory: repo root.

```bash
mkdir -p codex/skills/ticket-start/scripts
```

Then create `codex/skills/ticket-start/scripts/get-bot-gh-token.sh` with this EXACT content:

```bash
#!/usr/bin/env bash
# get-bot-gh-token.sh — mint a fresh GitHub App installation access token.
#
# Reads App ID, Installation ID, and the App's private key from macOS Keychain
# (entries: ai-skills.gh-bot.{app-id,installation-id,private-key}; see
# bot-identity.md runbook Step A). Mints a 9-minute RS256 JWT signed with the
# private key, exchanges it for an installation access token, prints the token
# to stdout. Exits non-zero on any failure with the error context on stderr.
#
# Usage:
#   GH_TOKEN=$(./get-bot-gh-token.sh) gh pr create ...

set -euo pipefail

KEYCHAIN_PREFIX="ai-skills.gh-bot"

read_keychain() {
  local service="$1"
  if ! security find-generic-password -s "$service" -a "$USER" -w 2>/dev/null; then
    echo "Missing Keychain entry: $service (account: $USER)" >&2
    echo "See bot-identity.md runbook Step A." >&2
    exit 1
  fi
}

APP_ID=$(read_keychain "${KEYCHAIN_PREFIX}.app-id")
INSTALLATION_ID=$(read_keychain "${KEYCHAIN_PREFIX}.installation-id")
PRIVATE_KEY=$(read_keychain "${KEYCHAIN_PREFIX}.private-key")

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
# never lands on disk as a temp file.
SIG=$(printf '%s' "$SIGNING_INPUT" \
  | openssl dgst -sha256 -sign <(printf '%s' "$PRIVATE_KEY") -binary 2>/dev/null \
  | b64url)

if [[ -z "$SIG" ]]; then
  echo "JWT signing failed. Is the private key in Keychain a valid PEM-encoded RSA private key?" >&2
  exit 2
fi

JWT="${SIGNING_INPUT}.${SIG}"

# Exchange the JWT for an installation access token (~1h lifetime).
RESPONSE=$(curl -sS -X POST \
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
```

- [ ] **Step 2: Set executable bit + verify syntax**

```bash
chmod +x codex/skills/ticket-start/scripts/get-bot-gh-token.sh
bash -n codex/skills/ticket-start/scripts/get-bot-gh-token.sh
```

Expected: `chmod` produces no output. `bash -n` produces no output (syntax OK). Exit code 0 on both.

- [ ] **Step 3: Smoke test — run with no Keychain entries, expect graceful failure**

This script depends on macOS Keychain entries that the user creates as part of the runbook. We can't fully run it without those, but we can verify the failure path is graceful.

Pick a Keychain entry name guaranteed not to exist (the real names are `ai-skills.gh-bot.*`; check none have been created yet on this machine for this test):

```bash
# Verify the script's three Keychain entries are NOT yet set (this is a fresh
# install per the spec; if they ARE set, skip this smoke test and document why).
security find-generic-password -s "ai-skills.gh-bot.app-id" -a "$USER" >/dev/null 2>&1 \
  && echo "WARN: ai-skills.gh-bot.app-id already exists; skip smoke test" \
  || echo "Keychain is clean; running smoke test"
```

If the Keychain is clean, run the script and confirm it exits non-zero with the documented error:

```bash
./codex/skills/ticket-start/scripts/get-bot-gh-token.sh 2>&1 | head -5
echo "Exit: $?"
```

Expected:
```
Missing Keychain entry: ai-skills.gh-bot.app-id (account: <your-username>)
See bot-identity.md runbook Step A.
Exit: 1
```

If the Keychain entries already exist (because the user did the runbook earlier on this machine), skip this smoke test and proceed.

- [ ] **Step 4: Mirror to install dir**

```bash
mkdir -p ~/.codex/skills/ticket-start/scripts
cp codex/skills/ticket-start/scripts/get-bot-gh-token.sh ~/.codex/skills/ticket-start/scripts/get-bot-gh-token.sh
diff -q codex/skills/ticket-start/scripts/get-bot-gh-token.sh ~/.codex/skills/ticket-start/scripts/get-bot-gh-token.sh
```

Expected: `diff -q` produces no output (files identical).

- [ ] **Step 5: Commit**

```bash
git add codex/skills/ticket-start/scripts/get-bot-gh-token.sh
git commit -m "$(cat <<'EOF'
ticket-start: add get-bot-gh-token.sh runtime helper

Mints a fresh GitHub App installation access token by reading the
App ID, Installation ID, and private key from macOS Keychain,
signing a 9-minute RS256 JWT, and exchanging it via GitHub's
/app/installations/<id>/access_tokens endpoint. Echoes the token
to stdout; exits non-zero with a runbook pointer on missing
Keychain entries, JWT-signing failures, or non-2xx GitHub
responses.

Designed for: GH_TOKEN=$(./get-bot-gh-token.sh) gh pr create ...

Dependencies: bash, openssl, curl, python3 (all on macOS by default).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Author `scripts/linear-oauth-bootstrap.sh`

**Files:**
- Create: `codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh`

- [ ] **Step 1: Write the file**

Create `codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh` with this EXACT content:

```bash
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
```

- [ ] **Step 2: Set executable bit + verify syntax**

```bash
chmod +x codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
bash -n codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
```

Expected: no output from either command. Exit 0.

- [ ] **Step 3: Smoke test — wrong arg count, expect usage message**

```bash
./codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh 2>&1 | head -5
echo "Exit: $?"
```

Expected:
```
Usage: ./codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh <CLIENT_ID> <CLIENT_SECRET>

Create the Linear OAuth app first at:
  https://linear.app/<workspace>/settings/api/applications/new
Set the redirect URI to http://localhost:8765/callback.
Exit: 1
```

- [ ] **Step 4: Mirror to install dir**

```bash
cp codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
diff -q codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
```

Expected: no output (identical).

- [ ] **Step 5: Commit**

```bash
git add codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
git commit -m "$(cat <<'EOF'
ticket-start: add linear-oauth-bootstrap.sh one-time setup helper

Runs a one-shot OAuth 2.0 authorization-code flow against Linear,
listening on http://localhost:8765/callback. Opens the user's
browser to Linear's authorize URL with actor=app set so the
resulting tokens identify the bot, not the authorizing user.
After receiving the callback, exchanges the code for an access
token + refresh token and prints the exact security
add-generic-password commands to store both in macOS Keychain.

CSRF-protected via the OAuth state parameter (16 random hex bytes
from openssl rand). One-shot — exits cleanly after the callback or
on state mismatch.

Dependencies: bash, openssl, curl, python3 (all on macOS by default).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Author `bot-identity.md`

**Files:**
- Create: `codex/skills/ticket-start/bot-identity.md`

- [ ] **Step 1: Write the file**

Create `codex/skills/ticket-start/bot-identity.md` with this EXACT content:

````markdown
# Bot Identity (Personal Workflow)

Loaded by `personal-workflow.md` whenever the personal workflow is selected. This file owns the bot-identity contract: how the bot is set up (one-time runbook), how the skill activates the bot at Setup (three checks), how Ship-phase token refresh works, and what to do when something fails.

The bot identity applies **only** to the personal workflow. Job-workflow tickets continue to use the user's personal credentials.

## Overview

When the agent works on a personal-workflow ticket, all external attribution surfaces as a dedicated bot identity:

- **GitHub** — a GitHub App that the user installed on their personal repos. The bot opens PRs and authors commits. The user does not appear in commit history or PR metadata.
- **Linear** — a Linear OAuth application that the user authorized once. The Linear MCP server is reconfigured to authenticate as the bot, so every Linear MCP call surfaces in Linear's activity feed as the bot (`actor=app`).
- **Credentials** — secret material lives in macOS Keychain. The user maintains an out-of-band copy (NordPass or equivalent).

The skill is **fail-closed**: if any expected Keychain entry is missing or the Linear MCP probe shows the user instead of the bot, the workflow halts at Setup with a pointer to the relevant runbook section. The skill never silently substitutes personal credentials.

## Setup runbook (one-time, manual)

Run this once per machine. After it's done, the skill picks up the bot identity automatically on every personal-workflow ticket.

### Step A — GitHub App

1. Go to `https://github.com/settings/apps/new` and create a new GitHub App:
   - **GitHub App name:** pick one (e.g., `eduard-bot`). This name appears on PRs and commits as `<name>[bot]`.
   - **Homepage URL:** any (e.g., a personal repo URL).
   - **Webhook:** **uncheck** "Active". This skill issues requests; it does not receive webhooks.
   - **Repository permissions:**
     - Contents → Read and write
     - Pull requests → Read and write
     - Issues → Read and write
     - Metadata → Read (set automatically)
   - **Organization permissions:** none.
   - **User permissions:** none.
   - **Where can this GitHub App be installed:** Only on this account.
2. After clicking "Create GitHub App", scroll down on the resulting settings page and click **Generate a private key**. A `.pem` file downloads. Note the **App ID** shown at the top of the page.
3. In the left sidebar of the App's settings, click **Install App**, then **Install** next to your account. Choose either "All repositories" or "Only select repositories" with your personal repos selected. Note the **Installation ID** — it's the integer at the end of the URL after the install completes (e.g., `https://github.com/settings/installations/12345678` → installation ID is `12345678`).
4. Store the three pieces of secret/identifier material in macOS Keychain:
   ```bash
   security add-generic-password -s "ai-skills.gh-bot.app-id" -a "$USER" -w "<APP_ID>"
   security add-generic-password -s "ai-skills.gh-bot.installation-id" -a "$USER" -w "<INSTALLATION_ID>"
   security add-generic-password -s "ai-skills.gh-bot.private-key" -a "$USER" -w "$(cat /path/to/private-key.pem)"
   ```
   Replace `<APP_ID>`, `<INSTALLATION_ID>`, and the path to the downloaded `.pem`.
5. Pick the bot's git author identity and store it in Keychain too:
   - **Name:** `eduard-bot` (or whatever you named the App).
   - **Email:** GitHub renders commits as the App when the commit email matches the pattern `<APP_ID>+<bot-slug>[bot]@users.noreply.github.com`. The bot-slug is the App's name converted to lowercase with hyphens. Example: App ID `12345` and App name `eduard-bot` → email `12345+eduard-bot[bot]@users.noreply.github.com`.
   ```bash
   security add-generic-password -s "ai-skills.gh-bot.git-name" -a "$USER" -w "eduard-bot"
   security add-generic-password -s "ai-skills.gh-bot.git-email" -a "$USER" -w "12345+eduard-bot[bot]@users.noreply.github.com"
   ```
6. (Recommended) Save copies of `<APP_ID>`, `<INSTALLATION_ID>`, the `.pem` file, and both git identity strings to your password manager (NordPass) as a backup. The Keychain is local to this machine; if it's lost, this backup is what regenerates it.

### Step B — Linear OAuth Application

1. Go to `https://linear.app/<your-workspace>/settings/api/applications/new` and create a new OAuth application:
   - **Application name:** match the GitHub bot name (e.g., `eduard-bot`).
   - **Description:** anything.
   - **Developer URL:** any.
   - **Callback URLs:** `http://localhost:8765/callback` — this exact URL.
2. After creating it, note the **Client ID** and **Client Secret** on the application's settings page.
3. Store the app credentials in Keychain:
   ```bash
   security add-generic-password -s "ai-skills.linear-bot.client-id" -a "$USER" -w "<CLIENT_ID>"
   security add-generic-password -s "ai-skills.linear-bot.client-secret" -a "$USER" -w "<CLIENT_SECRET>"
   ```
4. Run the one-shot OAuth bootstrap script:
   ```bash
   # On Codex:
   bash ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh "<CLIENT_ID>" "<CLIENT_SECRET>"
   # On Claude Code:
   bash ~/.claude/skills/ticket-start/scripts/linear-oauth-bootstrap.sh "<CLIENT_ID>" "<CLIENT_SECRET>"
   ```
   The script opens your browser to Linear's authorize URL with `actor=app` set, listens on `127.0.0.1:8765` for the OAuth callback, captures the authorization code, exchanges it for an access token + refresh token, and prints two `security add-generic-password` commands.
5. Paste and run the printed commands to store the tokens. After this, the relevant Keychain entries are:
   - `ai-skills.linear-bot.access-token`
   - `ai-skills.linear-bot.refresh-token`
6. (Recommended) Save the client ID, client secret, and both tokens to NordPass as a backup.

### Step C — Reconfigure the Linear MCP server

The Linear MCP server currently authenticates as you. Reconfigure it to use the bot's OAuth access token. The exact instructions depend on which Linear MCP server you're using:

- **Official hosted server (`mcp.linear.app`):** in your MCP client (Claude Code or Codex), disconnect the existing Linear OAuth connection. Reconnect — but during the OAuth authorization step in your browser, log out of Linear first (or use a private window) and log back in as the **bot's** Linear member if you also created a Linear member for the bot. If the hosted server only supports user-attributed OAuth, you can instead use the self-hosted-server path below.
- **Self-hosted Linear MCP** (e.g., `@linear/mcp-server` or a community fork): edit the server's config to read the access token from Keychain. Example for a server that supports a `LINEAR_API_KEY` env var:
  ```bash
  # In your MCP client config:
  env:
    LINEAR_API_KEY: $(security find-generic-password -s "ai-skills.linear-bot.access-token" -a "$USER" -w)
  ```
  Then restart the MCP server.

After reconfiguration, the agent's next Linear MCP call should identify the bot as the `viewer` (see Step 3 of "Setup activation" below).

### Step D — Defaults the skill assumes

These don't require any setup; they're documented here for reference:

- **Activation:** always-on for personal workflow.
- **Helper-script stack:** bash + `openssl` + `python3` (no `jq`, no npm, no pip).
- **Token refresh:** at Setup and again at Ship. Auto-retry-once with a fresh token if `gh` returns 401 mid-session.
- **Per-worktree git config:** the activation step sets `user.name` and `user.email` per-worktree, so your global git config and other repos are unaffected.

## Setup activation (three checks, fail-closed)

The main agent runs these three checks at the start of the Setup phase, after the worktree is created and before the Scoping subagent is dispatched. If any check fails, the workflow halts with the pointer named.

### Check 1 — Mint a fresh GitHub installation token

Run:
```bash
GH_TOKEN_PROBE=$(<skill-root>/scripts/get-bot-gh-token.sh)
```

Where `<skill-root>` is:
- Codex: `~/.codex/skills/ticket-start`
- Claude Code: `~/.claude/skills/ticket-start`

Verify the token works with a no-op API call:
```bash
curl -sf -o /dev/null \
  -H "Authorization: token $GH_TOKEN_PROBE" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/installation/repositories
```

If the script exits non-zero or the verify call fails: **halt**. Point at runbook Step A. Common causes:
- A Keychain entry is missing → the script's stderr says which one.
- The private key is malformed PEM → script exits with code 2.
- The App was revoked or uninstalled → API returns 401/404 → script exits with code 3 carrying the response body.

### Check 2 — Set the worktree's git author to the bot

Read the bot identity from Keychain and apply it to the worktree's local git config:
```bash
BOT_GIT_NAME=$(security find-generic-password -s "ai-skills.gh-bot.git-name" -a "$USER" -w)
BOT_GIT_EMAIL=$(security find-generic-password -s "ai-skills.gh-bot.git-email" -a "$USER" -w)
git -C <worktree> config user.name "$BOT_GIT_NAME"
git -C <worktree> config user.email "$BOT_GIT_EMAIL"
```

Verify with:
```bash
git -C <worktree> config user.email
```

Expected output: the value of `ai-skills.gh-bot.git-email` (e.g., `12345+eduard-bot[bot]@users.noreply.github.com`).

If `security find-generic-password` fails on either entry: **halt**. Point at runbook Step A.5.

### Check 3 — Probe the Linear MCP for `viewer` identity

Use the Linear MCP tool to query the authenticated viewer. Exact MCP method/field depends on the server in use:

- **Official `mcp.linear.app`:** call the `linear:me` or `linear:viewer` tool (the resource shape includes the authenticated identity's `name`, `email`, and `id`).
- **Self-hosted servers:** typically expose a `linear:viewer` or `linear:current_user` tool.

The viewer's identity must be the bot's Linear identity (the email or name should match the bot you created in Step B, not your personal Linear account). If the viewer is your personal account, the MCP was not reconfigured per Step C. **Halt.** Point at runbook Step C.

If the MCP call itself errors (auth failure, network, server unreachable): **halt.** Point at runbook Step B (if the Linear access token is missing or revoked) or Step C (if the MCP isn't reachable).

### After all three checks pass

Setup continues normally: read repository instructions, dispatch the Scoping subagent, etc.

## Implement phase — no new logic

The per-worktree git config set in Check 2 automatically applies to every `git commit` invocation in the worktree. The existing `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer pattern is preserved. No new commit-time machinery.

If you need to verify a specific commit's author identity:
```bash
git -C <worktree> log -1 --format='%an <%ae>'
```

Expected: the bot's name and email.

## Ship phase — token refresh

Before invoking `gh pr create`, refresh the GitHub installation token. Even if the session has been short, a fresh token guarantees we don't bump into the 1-hour ceiling mid-call:

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh) gh pr create --title "..." --body "..."
```

The `GH_TOKEN` env var is scoped to the single `gh` invocation. It does not pollute the shell.

After PR creation, Linear state transitions (In Review, completed) flow through the already-reconfigured Linear MCP. No additional credential handling needed at the transition points — the MCP is the bot.

## Failure-mode catalog

| Failure | Detection | Action |
|---|---|---|
| Keychain entry missing | `security find-generic-password` exits non-zero | Halt. Stderr names which key. Point at runbook Step A or B. |
| First-call Keychain access prompt (macOS) | `security` call blocks for the OS prompt | Wait for the user to approve. One-time per session per item. Surface that you're waiting. |
| GitHub token mint fails (4xx/5xx) | `get-bot-gh-token.sh` exits non-zero with the GitHub error body on stderr | Halt. Surface the error verbatim. Point at runbook Step A. Common causes: App revoked, key deleted, repo install removed. |
| Linear MCP `viewer` is the user, not the bot | Check 3 sees the user's identity | Halt. Point at runbook Step C. |
| Linear MCP call errors (auth) | MCP returns auth error | Halt. Tokens probably revoked → runbook Step B. |
| Linear MCP call errors (unreachable) | MCP returns connection error | Halt. MCP server probably down or misconfigured → runbook Step C. |
| `gh pr create` returns 401 mid-session | `gh` exit code non-zero + stderr "401" | Auto-retry **once** with a freshly-minted token (call `get-bot-gh-token.sh` again, re-issue `gh pr create`). If still 401, halt and surface. |
| Bot installed but no permission on this repo | `gh pr create` returns 403/404 | Halt. The App was not installed on this specific repo → runbook Step A.3, install it on the repo. |

All failures are fail-closed: the skill never silently substitutes personal credentials.

## Token rotation (for completeness)

This skill does not proactively rotate tokens. If you want to rotate:

- **GitHub App private key:** generate a new private key on the App's settings page, replace the Keychain entry (`security delete-generic-password -s "ai-skills.gh-bot.private-key" -a "$USER"`, then `security add-generic-password ...` with the new key). You can revoke the old key from the App settings page after confirming the new one works.
- **Linear OAuth tokens:** revoke the existing OAuth grant in Linear's settings, re-run `linear-oauth-bootstrap.sh`, replace the Keychain entries.

Rotation is out of scope for the skill's runtime behavior. The skill assumes whatever's in Keychain is current.
````

- [ ] **Step 2: Verify the file**

```bash
test -f codex/skills/ticket-start/bot-identity.md && echo "Exists ✓"
grep -c '^## ' codex/skills/ticket-start/bot-identity.md
```
Expected: file exists; section count ≥ 7 (Overview, Setup runbook, Setup activation, Implement phase, Ship phase, Failure-mode catalog, Token rotation, plus any sub-sections that grep counts).

- [ ] **Step 3: Cross-reference check**

The file references `scripts/get-bot-gh-token.sh` and `scripts/linear-oauth-bootstrap.sh`. Both should exist from Tasks 1 and 2.
```bash
test -f codex/skills/ticket-start/scripts/get-bot-gh-token.sh && echo "gh script ✓"
test -f codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh && echo "linear script ✓"
grep -q "scripts/get-bot-gh-token.sh" codex/skills/ticket-start/bot-identity.md && echo "gh ref ✓"
grep -q "scripts/linear-oauth-bootstrap.sh" codex/skills/ticket-start/bot-identity.md && echo "linear ref ✓"
```
Expected: all four checks ✓.

- [ ] **Step 4: Mirror to install dir**

```bash
cp codex/skills/ticket-start/bot-identity.md ~/.codex/skills/ticket-start/bot-identity.md
diff -q codex/skills/ticket-start/bot-identity.md ~/.codex/skills/ticket-start/bot-identity.md
```
Expected: no output (identical).

- [ ] **Step 5: Commit**

```bash
git add codex/skills/ticket-start/bot-identity.md
git commit -m "$(cat <<'EOF'
ticket-start: add bot-identity.md (runbook + activation + failure modes)

Self-contained doc for the personal-workflow bot identity:

  - Overview: GitHub App + Linear OAuth App + Keychain + fail-closed.
  - Setup runbook (Steps A-D): one-time manual user actions to create
    the GitHub App, Linear OAuth app, store credentials in Keychain,
    and reconfigure the Linear MCP server to authenticate as the bot.
  - Setup activation (three checks): the main agent runs at the start
    of every personal-workflow ticket — mint a fresh GitHub token,
    set per-worktree git config, probe Linear MCP viewer. Halt on any
    failure with a pointer to the relevant runbook step.
  - Implement phase: no new logic; the per-worktree git config
    auto-authors commits as the bot.
  - Ship phase: refresh the GitHub installation token, export as
    GH_TOKEN scoped to the gh invocation.
  - Failure-mode catalog: 8 failure paths with detection + action.
  - Token rotation (out of scope for runtime, documented for the user).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Update `personal-workflow.md` — add "Bot Identity" section

**Files:**
- Modify: `codex/skills/ticket-start/personal-workflow.md`

The new section goes right after `## Ticket Intake (Linear)` and before `## Scoped Reading`.

- [ ] **Step 1: Verify current file structure (so we know exactly where to insert)**

```bash
grep -nE '^## ' codex/skills/ticket-start/personal-workflow.md
```
Expected output:
```
5:## Ticket Intake (Linear)
14:## Scoped Reading
22:## React Reference App
33:## Verification — Mode mapping for QA and UI/UX
48:## Hand-off to Brainstorm
52:## Linear State Transitions
65:## Partial Setups
```

- [ ] **Step 2: Add the Bot Identity section**

Use the `Edit` tool to insert the new section. The exact edit:

Find this block:
```
After intake, proceed to Scoped Reading, then dispatch the Scoping subagent as `SKILL.md`'s Setup phase directs.

## Scoped Reading
```

Replace with:
```
After intake, proceed to Scoped Reading, then dispatch the Scoping subagent as `SKILL.md`'s Setup phase directs.

## Bot Identity (REQUIRED for this workflow)

Personal-workflow tickets always run under a dedicated bot identity — a GitHub App for `gh` and commits, a Linear OAuth application for ticket reads and transitions. The skill never uses your personal credentials on personal-workflow tickets.

See `bot-identity.md` for the full one-time setup runbook, the three Setup activation checks the main agent performs, the Ship-phase token refresh, and the failure-mode catalog. If the bot creds are not configured in macOS Keychain, the skill halts at Setup with a pointer to the relevant runbook step. **Fail-closed by design.**

## Scoped Reading
```

- [ ] **Step 3: Verify the section was inserted**

```bash
grep -nE '^## ' codex/skills/ticket-start/personal-workflow.md
```
Expected: the new section appears between Ticket Intake and Scoped Reading. Section count goes from 7 to 8.

```bash
grep -q "Bot Identity (REQUIRED for this workflow)" codex/skills/ticket-start/personal-workflow.md && echo "Section header ✓"
grep -q "Fail-closed by design" codex/skills/ticket-start/personal-workflow.md && echo "Fail-closed mention ✓"
grep -q "See \`bot-identity.md\`" codex/skills/ticket-start/personal-workflow.md && echo "bot-identity ref ✓"
```
Expected: all three ✓.

- [ ] **Step 4: Mirror to install dir**

```bash
cp codex/skills/ticket-start/personal-workflow.md ~/.codex/skills/ticket-start/personal-workflow.md
diff -q codex/skills/ticket-start/personal-workflow.md ~/.codex/skills/ticket-start/personal-workflow.md
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add codex/skills/ticket-start/personal-workflow.md
git commit -m "$(cat <<'EOF'
ticket-start: add Bot Identity section to personal-workflow.md

Inserts a short "Bot Identity (REQUIRED for this workflow)" section
between Ticket Intake and Scoped Reading that points the main agent
at bot-identity.md. The section establishes that personal-workflow
tickets always run under the bot identity (never personal credentials)
and that missing Keychain entries cause the skill to halt at Setup
(fail-closed by design).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Update `SKILL.md` — insert Setup step 2 "Activate bot identity"

**Files:**
- Modify: `codex/skills/ticket-start/SKILL.md`

The current `## Setup` section in SKILL.md has 6 numbered items: 1. Worktree first, 2. Repository instructions, 3. Freshness, 4. Workflow-specific reading, 5. Dispatch Scoping subagent, 6. Clarifications.

We're inserting a new step 2 ("Activate bot identity") between worktree creation and repository instructions. Subsequent steps renumber from 2-6 to 3-7.

- [ ] **Step 1: Verify current numbering**

```bash
awk '/^## Setup$/,/^## /' codex/skills/ticket-start/SKILL.md | grep -E '^[0-9]+\.' | head -10
```
Expected:
```
1. **Worktree first.** Before reading the ticket body, before exploring code, create an isolated worktree from the freshest remote default branch. Do not work in the primary checkout. Identifying which workflow applies (Job vs Personal) requires only knowing the ticket's source system, not its contents — that minimal awareness is allowed before the worktree is in place.
2. **Repository instructions.** Inside the worktree, read the nearest applicable `AGENTS.md` first, then load only the additional instruction files and project docs that materially affect the task.
3. **Freshness — treat memory as stale.** Memory, prior chat context, old plans, and earlier tool results are hints, not facts. Before any substantive answer about scope, status, blockers, related tickets, progress, PR readiness, or git state, fetch current facts from the source of truth:
4. **Workflow-specific reading.** Read the workflow file selected above. Stop when the relevant facts are gathered — do not push past the Brainstorm gate without them.
5. **Dispatch Scoping subagent.** Read `agents/scoping.md` for the role prompt. Invoke a subagent on the host platform's native subagent API with:
6. **Clarifications.** If acceptance criteria are missing, vague, or not testable, stop and ask before continuing. If the Scoping report surfaces a conflict between the ticket and existing architecture, surface the conflict before brainstorming. Ask concise clarifying questions when material ambiguity remains after Scoping.
```

- [ ] **Step 2: Insert the new step 2 (Activate bot identity)**

Use the `Edit` tool. Find this text:
```
2. **Repository instructions.** Inside the worktree, read the nearest applicable `AGENTS.md` first, then load only the additional instruction files and project docs that materially affect the task.
```

Replace with:
```
2. **Activate bot identity (personal workflow only).** Before any further Setup work, run the three checks documented in `bot-identity.md` → `## Setup activation`: (a) mint a fresh GitHub installation token via `scripts/get-bot-gh-token.sh` and verify it with a no-op API call; (b) read the bot's git name and email from Keychain and apply them as per-worktree git config in the worktree; (c) probe the Linear MCP `viewer` and confirm the authenticated identity is the bot, not the user. Any check failure: halt and point at the runbook section in `bot-identity.md` that fixes it. **Fail-closed** — the skill never falls back to personal credentials. Job workflow: skip this step entirely; job-workflow tickets continue to use personal credentials.

3. **Repository instructions.** Inside the worktree, read the nearest applicable `AGENTS.md` first, then load only the additional instruction files and project docs that materially affect the task.
```

- [ ] **Step 3: Renumber subsequent Setup steps (3→4, 4→5, 5→6, 6→7)**

Use the `Edit` tool four times in sequence. Each is a single-line replacement.

Edit 3a — find:
```
3. **Freshness — treat memory as stale.**
```
Replace with:
```
4. **Freshness — treat memory as stale.**
```

Edit 3b — find:
```
4. **Workflow-specific reading.**
```
Replace with:
```
5. **Workflow-specific reading.**
```

Edit 3c — find:
```
5. **Dispatch Scoping subagent.**
```
Replace with:
```
6. **Dispatch Scoping subagent.**
```

Edit 3d — find:
```
6. **Clarifications.**
```
Replace with:
```
7. **Clarifications.**
```

- [ ] **Step 4: Verify the new numbering and content**

```bash
awk '/^## Setup$/,/^## /' codex/skills/ticket-start/SKILL.md | grep -E '^[0-9]+\.' | head -10
```
Expected: seven steps numbered 1 through 7, with "Activate bot identity (personal workflow only)" as step 2.

```bash
grep -q "Activate bot identity (personal workflow only)" codex/skills/ticket-start/SKILL.md && echo "Step header ✓"
grep -q "bot-identity.md\`" codex/skills/ticket-start/SKILL.md && echo "bot-identity ref ✓"
grep -q "Fail-closed" codex/skills/ticket-start/SKILL.md && echo "Fail-closed mention ✓"
```
Expected: all three ✓.

- [ ] **Step 5: Mirror to install dir**

```bash
cp codex/skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
diff -q codex/skills/ticket-start/SKILL.md ~/.codex/skills/ticket-start/SKILL.md
```
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git add codex/skills/ticket-start/SKILL.md
git commit -m "$(cat <<'EOF'
ticket-start: insert Setup step "Activate bot identity"

New Setup step 2 (between worktree creation and repository
instructions) directs the main agent to run the three bot-identity
activation checks documented in bot-identity.md:

  1. Mint a fresh GitHub installation token via
     scripts/get-bot-gh-token.sh and verify it.
  2. Read the bot's git name + email from Keychain and apply them
     as per-worktree git config.
  3. Probe the Linear MCP viewer and confirm it's the bot.

Any failure: halt with a pointer to the runbook. Fail-closed.

Job workflow skips this step entirely. Subsequent Setup steps
renumber from 2-6 to 3-7.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Mirror codex tree to claude/skills/ticket-start/

**Files:**
- Modify (mirror): `claude/skills/ticket-start/` (the entire tree, picking up the new bot-identity.md, the new scripts/ dir, and the modified personal-workflow.md and SKILL.md)

- [ ] **Step 1: Copy the new and modified files**

The claude tree already exists from the previous orchestrator-redesign PR. We're adding two new files and overwriting two existing ones.

```bash
mkdir -p claude/skills/ticket-start/scripts
cp codex/skills/ticket-start/bot-identity.md claude/skills/ticket-start/bot-identity.md
cp codex/skills/ticket-start/scripts/get-bot-gh-token.sh claude/skills/ticket-start/scripts/get-bot-gh-token.sh
cp codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh claude/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
cp codex/skills/ticket-start/personal-workflow.md claude/skills/ticket-start/personal-workflow.md
cp codex/skills/ticket-start/SKILL.md claude/skills/ticket-start/SKILL.md
```

- [ ] **Step 2: Preserve executable bit on the scripts**

`cp` on macOS preserves the executable bit by default, but verify:

```bash
ls -l claude/skills/ticket-start/scripts/
```
Expected: both `.sh` files show `-rwxr-xr-x` (or similar — owner/group/other all have execute). If not:
```bash
chmod +x claude/skills/ticket-start/scripts/*.sh
```

- [ ] **Step 3: Verify tree symmetry (codex ↔ claude)**

```bash
diff -r --brief codex/skills/ticket-start/ claude/skills/ticket-start/
```
Expected output (exactly one line):
```
Only in codex/skills/ticket-start/agents: openai.yaml
```

If any other diff appears, fix it before continuing.

- [ ] **Step 4: Commit**

```bash
git add claude/skills/ticket-start/
git commit -m "$(cat <<'EOF'
ticket-start: mirror bot-identity additions to claude/skills/ tree

Adds the two new files (bot-identity.md, scripts/get-bot-gh-token.sh,
scripts/linear-oauth-bootstrap.sh) and the modified personal-
workflow.md and SKILL.md to the Claude Code copy of the skill.
Tree symmetry preserved — only agents/openai.yaml remains
Codex-only (interface descriptor for Codex's skill registry).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Mirror both trees to install paths

**Files:**
- Sync: `~/.codex/skills/ticket-start/` ← `codex/skills/ticket-start/`
- Sync: `~/.claude/skills/ticket-start/` ← `claude/skills/ticket-start/`

Per the user's standing memory rule, every edit under `codex/skills/` or `claude/skills/` must mirror to its corresponding install path in the same flow. Tasks 1–4 already mirrored the codex changes individually to `~/.codex/skills/`. This task makes the claude install-path catch up and does a full `rsync` sanity-sweep on both.

- [ ] **Step 1: Sync codex tree (idempotent — should be no-op since prior tasks already mirrored)**

```bash
rsync -av --delete codex/skills/ticket-start/ ~/.codex/skills/ticket-start/
```

Expected output: a list of files visited but no actual transfers (since prior tasks mirrored them individually). If any file shows as "newly transferred," that means a prior task missed its mirror step — investigate.

- [ ] **Step 2: Sync claude tree**

```bash
mkdir -p ~/.claude/skills/ticket-start
rsync -av --delete claude/skills/ticket-start/ ~/.claude/skills/ticket-start/
```

Expected output: the new files (`bot-identity.md`, `scripts/get-bot-gh-token.sh`, `scripts/linear-oauth-bootstrap.sh`) plus the two modified files (`personal-workflow.md`, `SKILL.md`) transferred. Other files unchanged.

- [ ] **Step 3: Verify install-path sync**

```bash
diff -r --brief codex/skills/ticket-start/ ~/.codex/skills/ticket-start/ && echo "Codex install ✓"
diff -r --brief claude/skills/ticket-start/ ~/.claude/skills/ticket-start/ && echo "Claude install ✓"
```

Expected: both checks ✓, no diffs.

- [ ] **Step 4: Verify scripts are executable in install paths**

```bash
ls -l ~/.codex/skills/ticket-start/scripts/ ~/.claude/skills/ticket-start/scripts/
```
Expected: all four `.sh` files (2 in each tree) show executable bits set.

- [ ] **Step 5: No commit needed**

Install-path mirrors live outside the repo. No git operation.

---

### Task 8: Lint and cross-reference verification

**Files:**
- Verify: every file in `codex/skills/ticket-start/` and `claude/skills/ticket-start/`

- [ ] **Step 1: Frontmatter check on SKILL.md (both trees)**

```bash
for f in codex/skills/ticket-start/SKILL.md claude/skills/ticket-start/SKILL.md; do
  echo "=== $f ==="
  head -1 "$f" | grep -q '^---$' && echo "Frontmatter starts ✓"
  awk '/^---$/{n++; next} n==1{print}' "$f" | head -5
done
```
Expected: both files start with `---` and have the same `name: ticket-start` / `description: ...` frontmatter.

- [ ] **Step 2: No-placeholder scan**

```bash
grep -rnE '\b(TBD|FIXME|XXX|implement later|fill in)\b' \
  codex/skills/ticket-start/ claude/skills/ticket-start/ 2>/dev/null | \
  grep -v '\.pem' | grep -v 'TODO' || echo "no placeholders found"
```

We exclude the literal word TODO because `bot-identity.md`'s failure-mode catalog uses it in prose form ("If the App was revoked or uninstalled"). Adjust if a real TODO shows up.

Expected: `no placeholders found`. Any line that surfaces is a real issue.

- [ ] **Step 3: Cross-reference resolution**

```bash
for tree in codex/skills/ticket-start claude/skills/ticket-start; do
  echo "=== $tree ==="
  missing=0
  for f in agents/scoping.md agents/architect.md agents/reviewer.md \
           agents/security.md agents/qa.md agents/ui-ux.md \
           bug-fix-loop.md self-improvement.md bot-identity.md \
           job-workflow.md personal-workflow.md \
           react-parity.md verification.md \
           scripts/get-bot-gh-token.sh scripts/linear-oauth-bootstrap.sh \
           SKILL.md; do
    test -f "$tree/$f" || { echo "MISSING: $tree/$f"; missing=$((missing+1)); }
  done
  test "$missing" -eq 0 && echo "All cross-refs resolve ✓"
done
```

Expected: only `=== ... ===` headers and "All cross-refs resolve ✓" twice. No `MISSING:` lines.

- [ ] **Step 4: SKILL.md and personal-workflow.md reference bot-identity.md**

```bash
grep -q "bot-identity.md" codex/skills/ticket-start/SKILL.md && echo "SKILL.md → bot-identity ✓"
grep -q "bot-identity.md" codex/skills/ticket-start/personal-workflow.md && echo "personal-workflow.md → bot-identity ✓"
grep -q "bot-identity.md" claude/skills/ticket-start/SKILL.md && echo "claude SKILL.md → bot-identity ✓"
grep -q "bot-identity.md" claude/skills/ticket-start/personal-workflow.md && echo "claude personal-workflow.md → bot-identity ✓"
```
Expected: all four ✓.

- [ ] **Step 5: bot-identity.md references both scripts**

```bash
grep -q "scripts/get-bot-gh-token.sh" codex/skills/ticket-start/bot-identity.md && echo "gh script ref ✓"
grep -q "scripts/linear-oauth-bootstrap.sh" codex/skills/ticket-start/bot-identity.md && echo "linear script ref ✓"
grep -q "scripts/get-bot-gh-token.sh" claude/skills/ticket-start/bot-identity.md && echo "claude gh script ref ✓"
grep -q "scripts/linear-oauth-bootstrap.sh" claude/skills/ticket-start/bot-identity.md && echo "claude linear script ref ✓"
```
Expected: all four ✓.

- [ ] **Step 6: Tree symmetry final check**

```bash
diff -r --brief codex/skills/ticket-start/ claude/skills/ticket-start/
```
Expected (exactly one line):
```
Only in codex/skills/ticket-start/agents: openai.yaml
```

- [ ] **Step 7: Install-path sync final check**

```bash
diff -r --brief codex/skills/ticket-start/ ~/.codex/skills/ticket-start/ && echo "Codex install in sync ✓"
diff -r --brief claude/skills/ticket-start/ ~/.claude/skills/ticket-start/ && echo "Claude install in sync ✓"
```
Expected: both ✓.

- [ ] **Step 8: No commit needed (verification only)**

This task produces no file changes. If any step fails, return to the originating task and fix.

---

### Task 9: Closeout — branch summary, push, PR

**Files:**
- None directly; this task pushes the branch and opens the PR.

- [ ] **Step 1: Confirm working tree is clean**

```bash
git status
```
Expected: `nothing to commit, working tree clean`. All changes from Tasks 1–6 should already be committed.

- [ ] **Step 2: Confirm commit history shows the implementation + spec**

```bash
git log --oneline origin/main..HEAD
```
Expected (order may vary by execution path):
```
<sha> ticket-start: mirror bot-identity additions to claude/skills/ tree
<sha> ticket-start: insert Setup step "Activate bot identity"
<sha> ticket-start: add Bot Identity section to personal-workflow.md
<sha> ticket-start: add bot-identity.md (runbook + activation + failure modes)
<sha> ticket-start: add linear-oauth-bootstrap.sh one-time setup helper
<sha> ticket-start: add get-bot-gh-token.sh runtime helper
8a8a523 ticket-start: add bot-identity design spec
```

7 commits total: 1 spec + 6 implementation.

- [ ] **Step 3: Final verification sweep**

Re-run Task 8's three core checks:
```bash
diff -r --brief codex/skills/ticket-start/ claude/skills/ticket-start/
diff -r --brief codex/skills/ticket-start/ ~/.codex/skills/ticket-start/
diff -r --brief claude/skills/ticket-start/ ~/.claude/skills/ticket-start/
```
Expected: only the `agents/openai.yaml` difference (Codex-only); install paths quiet.

- [ ] **Step 4: Push the branch**

```bash
git push -u origin ticket-start-bot-identity
```
Expected: push succeeds, branch tracked.

- [ ] **Step 5: Create the PR**

```bash
gh pr create --title "ticket-start: bot identity for personal workflow" --body "$(cat <<'EOF'
## Summary

Adds a dedicated bot identity to the personal-workflow path of `ticket-start`. PRs, commits, and Linear ticket transitions surface attributed to the bot (a GitHub App + a Linear OAuth Application) instead of the user's personal credentials.

- **GitHub:** a user-created GitHub App authors commits and opens PRs via an installation access token minted fresh per session.
- **Linear:** a user-created OAuth Application acts with `actor=app`. The existing Linear MCP server is reconfigured to authenticate as the bot, so all Linear interactions via MCP are bot-attributed.
- **Credentials:** stored in macOS Keychain (`ai-skills.gh-bot.*` and `ai-skills.linear-bot.*`). NordPass holds the user's personal backup. Skill is **fail-closed** if any Keychain entry is missing.
- **Bot is author** on every commit via per-worktree `git config user.name` / `user.email`. Existing Claude `Co-Authored-By:` trailer preserved.
- **Activation:** main agent runs three checks at the start of every personal-workflow Setup — mint+verify GH token, set worktree git config, probe Linear MCP viewer. Job workflow skips this step entirely.
- **Token refresh:** at Setup and Ship; auto-retry-once with a fresh token on a mid-session 401.

Spec at `docs/superpowers/specs/2026-05-11-ticket-start-bot-identity-design.md`. Plan at `docs/superpowers/plans/2026-05-11-ticket-start-bot-identity.md`.

## Test plan

This change requires manual setup before any automated verification because the credentials are user-specific.

- [ ] Run the runbook in `bot-identity.md` Step A (create GitHub App, install on personal repos, store Keychain entries).
- [ ] Run the runbook in `bot-identity.md` Step B (create Linear OAuth App, store client ID/secret, run `linear-oauth-bootstrap.sh`, store tokens).
- [ ] Run the runbook in `bot-identity.md` Step C (reconfigure Linear MCP server to authenticate as the bot).
- [ ] Pick a real Linear ticket in a personal repo and invoke `ticket-start`. Verify Setup activation runs the three checks. Verify the worktree's git author shows as the bot.
- [ ] Run through Implement; verify commits on the branch show the bot as author on GitHub.
- [ ] Open the PR via the skill's Ship phase. Verify the PR is opened by the GitHub App and the Linear ticket transitions to "In Review" with the bot as the actor in Linear's activity feed.
- [ ] Force-revoke the GitHub installation token (e.g., delete a Keychain entry mid-session) and re-invoke the skill; verify fail-closed at Setup with a clear pointer.
- [ ] Confirm a job-workflow ticket still uses personal credentials (no bot activation).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

- [ ] **Step 6: Final summary to the user**

Produce a closeout summary covering:
- PR URL.
- Commits added in this branch (count + range).
- Files created (`bot-identity.md`, `scripts/get-bot-gh-token.sh`, `scripts/linear-oauth-bootstrap.sh` × 2 trees).
- Files modified (`personal-workflow.md`, `SKILL.md` × 2 trees).
- Install-path mirror status (both in sync).
- What is **not** verified by this plan: the runtime behavior on a real ticket. That requires the user to complete the runbook on this machine first. Until then, the skill will fail-closed at Setup for any personal-workflow ticket.
- Next steps for the user: review the PR, optionally run the runbook on this machine, then test the new behavior on a real personal ticket.

---

## Self-review

After writing the complete plan, I checked it against the spec.

### 1. Spec coverage

- **§1 Goals & non-goals** — captured in plan header (Goal, Architecture). ✓
- **§2 Architecture summary** — implemented across Tasks 3, 4, 5 (bot-identity.md content, personal-workflow.md section, SKILL.md Setup step). ✓
- **§3 Identity choices** — encoded in bot-identity.md runbook (Tasks 3 Step 1) and the scripts (Tasks 1, 2). ✓
- **§4 Setup runbook** — Tasks 1, 2, 3 (scripts + the doc that walks through the runbook). ✓
- **§5 Skill activation and runtime flow** — Tasks 3 (Setup activation doc), 5 (SKILL.md step), 4 (personal-workflow.md section). Implement-phase no-op and Ship-phase refresh are documented in Task 3's bot-identity.md content. ✓
- **§6 File structure and mirroring** — Tasks 1–7 produce every file in the spec's table; Task 7 syncs install paths. ✓
- **§7 Deferred to implementation plan** — all seven items addressed in the "Plan-level decisions locked" preamble at the top. ✓
- **§8 Migration and scope** — addressed by the additive nature of every change (no existing files are deleted; the new Setup step is opt-in for personal workflow). ✓

No spec gaps.

### 2. Placeholder scan

I searched for: TBD, FIXME, XXX, "implement later", "fill in", "Similar to Task N." None appear in instruction-bearing parts of the plan. The plan's `<APP_ID>`, `<INSTALLATION_ID>`, `<workspace>`, `<BOT_GIT_NAME>`, `<skill-root>`, `<worktree>`, `<your-username>` placeholders are intentional substitution markers that the user fills in at runtime, not TBDs — same convention the prior plan used.

### 3. Type / name consistency

Cross-checked names used across tasks:

- **Keychain service names:** `ai-skills.gh-bot.{app-id, installation-id, private-key, git-name, git-email}` and `ai-skills.linear-bot.{client-id, client-secret, access-token, refresh-token}` — consistent across Tasks 1 (script reads), 2 (script prints), 3 (runbook + activation doc).
- **Script paths:** `scripts/get-bot-gh-token.sh` and `scripts/linear-oauth-bootstrap.sh` — consistent across Tasks 1, 2, 3, 6, 7.
- **File paths:** `bot-identity.md` (singular, no `.runbook.` infix) — consistent across Tasks 3, 4, 5.
- **Phase names + verbs:** "Setup activation" (not "Setup verification" or "bot bootstrap"), "fail-closed" (consistent), "halt" (consistent verb across failure modes).
- **OAuth redirect URI:** `http://localhost:8765/callback` — consistent across Task 2's script and Task 3's runbook documentation.

No inconsistencies.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-11-ticket-start-bot-identity.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Best fit because every task is self-contained (file creation + verification + commit + mirror) and the per-task review catches issues like a missing `chmod +x` or a broken cross-reference before they propagate.

**2. Inline Execution** — Run tasks in this session via `superpowers:executing-plans` with batch checkpoints. Faster wallclock; no per-task review.

**Which approach?**
