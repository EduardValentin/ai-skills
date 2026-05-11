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

We use Linear's **`client_credentials` OAuth grant**, not the browser-based `authorization_code` grant. The resulting token is an "app actor token" — Linear automatically attributes every action to the OAuth app, not to a user. No browser dance, no callback URL, just one curl. Tokens are valid ~30 days; the script re-mints whenever invoked.

1. Go to `https://linear.app/<your-workspace>/settings/api/applications/new` and create a new OAuth application:
   - **Application name:** match the GitHub bot name (e.g., `eduard-agent`).
   - **Description:** anything.
   - **Developer URL:** any.
   - **GitHub username:** `<bot-name>[bot]` (e.g., `eduard-agent[bot]`) — ties Linear cross-posts to the GitHub App identity.
   - **Callback URLs:** `http://localhost:8765/callback` — required by Linear's form even though we never use it. This exact URL.
2. **Enable client credentials tokens.** In the app's settings page, find the **"Client credentials tokens"** toggle and turn it on. Without this, Linear will reject the grant with `Client does not support the client_credentials grant type`.
3. After creating it, note the **Client ID** and **Client Secret** on the application's settings page.
4. Store the app credentials in Keychain. **Run these in your own terminal** so the client secret never enters any chat log or process arg list. For the secret, use `read -rs` so it doesn't land in shell history:
   ```bash
   # Client ID (not sensitive — inline is fine):
   security add-generic-password -U -s "ai-skills.linear-bot.client-id" -a "$USER" -w '<CLIENT_ID>'

   # Client Secret (sensitive — paste into prompt, nothing echoes back):
   read -rs LINEAR_CLIENT_SECRET
   security add-generic-password -U -s "ai-skills.linear-bot.client-secret" -a "$USER" -w "$LINEAR_CLIENT_SECRET"
   unset LINEAR_CLIENT_SECRET
   ```
   `-U` updates the entry if it already exists (safe to re-run).
5. Run the bootstrap script. It reads `client-id` and `client-secret` from Keychain, POSTs to Linear's `/oauth/token` with `grant_type=client_credentials`, and writes the resulting `access-token` directly back to Keychain. The token never appears on stdout or in `ps`:
   ```bash
   # On Codex:
   bash ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
   # On Claude Code:
   bash ~/.claude/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
   ```
   On success, the script stores `ai-skills.linear-bot.access-token` in Keychain. **No refresh token is issued** — `client_credentials` doesn't include one. To renew (or rotate), re-run the script; Linear invalidates the previous token and returns a fresh 30-day one.
6. Verify the token is stored and works:
   ```bash
   security find-generic-password -s "ai-skills.linear-bot.access-token" -a "$USER" >/dev/null && echo "access-token ✓"

   # Probe Linear API — should return your bot's name, not your personal user.
   ACCESS_TOKEN=$(security find-generic-password -s "ai-skills.linear-bot.access-token" -a "$USER" -w)
   curl -sS -X POST https://api.linear.app/graphql \
     -H "Authorization: $ACCESS_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"query":"{ viewer { name email } }"}'
   unset ACCESS_TOKEN
   ```
   Expected: `name` is your bot's name; `email` ends with `@oauthapp.linear.app` (Linear's marker for OAuth-app actors).
7. (Recommended) Save the **Client ID** and **Client Secret** to NordPass as a backup. The access token is regenerable from those — don't bother backing it up.

### Step C — Reconfigure the Linear MCP server

The Linear MCP server currently authenticates as you (interactive OAuth at first connection). The hosted server at `mcp.linear.app` accepts a pre-authenticated **`Authorization: Bearer <token>`** header — when this header is present, the server uses it directly and skips the interactive OAuth flow. We inject the bot's `client_credentials` access token from Keychain into both Codex and Claude Code MCP configs.

1. Run the config-update helper:
   ```bash
   # On Codex:
   bash ~/.codex/skills/ticket-start/scripts/update-linear-mcp-configs.sh
   # On Claude Code:
   bash ~/.claude/skills/ticket-start/scripts/update-linear-mcp-configs.sh
   ```
   The script reads `ai-skills.linear-bot.access-token` from Keychain and writes the `Authorization: Bearer ...` header into:
   - `~/.codex/config.toml` → `[mcp_servers.linear].http_headers.Authorization`
   - `~/.claude.json` → `mcpServers.linear.headers.Authorization` (global)
   - `~/.claude.json` → `projects.<path>.mcpServers.linear.headers.Authorization` (every project-level Linear MCP entry, if any)

   The token never appears on stdout, in `ps`, or in shell history — it's read inside a single Python process and written straight to the config files.

2. **Restart Codex and Claude Code** so the new MCP config takes effect. Existing sessions still hold the old auth in memory until restart.

3. Verify in a fresh session (see Setup activation Check 3 below): call your MCP client's `get_user` Linear tool with no arguments and confirm the returned identity is `eduard-agent` (the OAuth app), not your personal Linear account.

#### Token rotation

Linear's `client_credentials` tokens expire ~30 days after issuance. To rotate:
1. Re-run `linear-oauth-bootstrap.sh` (mints a fresh token; Linear invalidates the previous one; Keychain entry updated in place).
2. Re-run `update-linear-mcp-configs.sh` (pushes the new token into both MCP configs).
3. Restart Codex and Claude Code.

You can chain steps 1 + 2 in one line:
```bash
bash ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh && \
bash ~/.codex/skills/ticket-start/scripts/update-linear-mcp-configs.sh
```

After reconfiguration, the agent's next Linear MCP call identifies the bot as the `viewer` (see Setup activation Check 3 below).

### Step D — Defaults the skill assumes

These don't require any setup; they're documented here for reference:

- **Activation:** always-on for personal workflow.
- **Helper-script stack:** bash + `openssl` + `python3` (no `jq`, no npm, no pip).
- **Token refresh:** at Setup and again at Ship. Auto-retry-once with a fresh token if `gh` returns 401 mid-session.
- **Per-worktree git config:** the activation step sets `user.name` and `user.email` per-worktree, so your global git config and other repos are unaffected.

## Setup activation (three checks, fail-closed)

The main agent runs these three checks at the start of the Setup phase, after the worktree is created and before the Scoping subagent is dispatched. If any check fails, the workflow halts with the pointer named.

### Check 1 — Mint a fresh GitHub installation token

`<skill-root>` in the snippet below is one of:
- Codex: `~/.codex/skills/ticket-start`
- Claude Code: `~/.claude/skills/ticket-start`

Run:
```bash
GH_TOKEN_PROBE=$(<skill-root>/scripts/get-bot-gh-token.sh)
```

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

Use whichever Linear MCP tool fetches the authenticated user — the exact tool name varies by server:

- **Official `mcp.linear.app`:** the `get_user` tool, called with no arguments, returns the authenticated user. The `list_users` tool also returns the current user implicitly via `viewer` or similar — check the tool's response shape.
- **Self-hosted servers:** typically expose a `get_user`, `get_viewer`, `me`, or `current_user` tool. If uncertain, list the available Linear MCP tools (`mcp/list_tools` or your host's equivalent) and use the one whose description mentions "current user" or "authenticated user."

The returned identity must be the bot's Linear identity (the email or name should match the bot you created in Step B, not your personal Linear account). If the viewer is your personal account, the MCP was not reconfigured per Step C. **Halt.** Point at runbook Step C.

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

Before invoking `gh pr create`, refresh the GitHub installation token. Even if the session has been short, a fresh token guarantees we don't bump into the 1-hour ceiling mid-call. `<skill-root>` is the same value as in Check 1 (`~/.codex/skills/ticket-start` on Codex or `~/.claude/skills/ticket-start` on Claude Code):

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
- **Linear bot access token:** re-run `linear-oauth-bootstrap.sh`. Linear's `client_credentials` grant invalidates the previous active token on every successful issuance and returns a fresh 30-day one. The Keychain entry is updated in place.
- **Linear OAuth app client secret:** in the Linear app's settings, regenerate the secret. Update `ai-skills.linear-bot.client-secret` in Keychain. Re-run `linear-oauth-bootstrap.sh` to mint a new access token with the new credentials.

Rotation is out of scope for the skill's runtime behavior. The skill assumes whatever's in Keychain is current.
