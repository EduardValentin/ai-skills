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
3. Store the app credentials in Keychain. **Run these in your own terminal** so the client secret never enters any chat log or process arg list:
   ```bash
   security add-generic-password -U -s "ai-skills.linear-bot.client-id" -a "$USER" -w '<CLIENT_ID>'
   security add-generic-password -U -s "ai-skills.linear-bot.client-secret" -a "$USER" -w '<CLIENT_SECRET>'
   ```
   `-U` updates the entry if it already exists (so this is safe to re-run).
4. Run the one-shot OAuth bootstrap script. It reads `client-id` and `client-secret` from Keychain, runs the browser dance, and writes the resulting access + refresh tokens directly back to Keychain. Tokens never appear on stdout or in `ps`:
   ```bash
   # On Codex:
   bash ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
   # On Claude Code:
   bash ~/.claude/skills/ticket-start/scripts/linear-oauth-bootstrap.sh
   ```
   The script opens your browser to Linear's authorize URL with `actor=app` set, listens on `127.0.0.1:8765` for the OAuth callback, captures the authorization code, exchanges it for tokens, and writes them to Keychain:
   - `ai-skills.linear-bot.access-token`
   - `ai-skills.linear-bot.refresh-token`
5. Verify the tokens are stored:
   ```bash
   security find-generic-password -s "ai-skills.linear-bot.access-token" -a "$USER" >/dev/null && echo "access-token ✓"
   security find-generic-password -s "ai-skills.linear-bot.refresh-token" -a "$USER" >/dev/null && echo "refresh-token ✓"
   ```
6. (Recommended) Save the client ID, client secret, and both tokens to NordPass as a backup.

### Step C — Reconfigure the Linear MCP server

The Linear MCP server currently authenticates as you. Reconfigure it to use the bot's OAuth access token. The exact instructions depend on which Linear MCP server you're using:

- **Official hosted server (`mcp.linear.app`):** in your MCP client (Claude Code or Codex), disconnect the existing Linear OAuth connection. Reconnect — but during the OAuth authorization step in your browser, log out of Linear first (or use a private window) and log back in as the **bot's** Linear member if you also created a Linear member for the bot. If the hosted server only supports user-attributed OAuth, you can instead use the self-hosted-server path below. **Detection:** after reconfiguring, if Check 3 (Setup activation) still reports your personal account as the `viewer`, the hosted server is giving user-attributed OAuth — switch to the self-hosted path before proceeding with any personal-workflow ticket.
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
- **Linear OAuth tokens:** revoke the existing OAuth grant in Linear's settings, re-run `linear-oauth-bootstrap.sh`, replace the Keychain entries.

Rotation is out of scope for the skill's runtime behavior. The skill assumes whatever's in Keychain is current.
