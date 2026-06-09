# Bot Identity (Personal Workflow)

Read this when ticket-start is handling a personal project and a GitHub write may be needed. This file owns the bot-identity contract: how the bot is set up, how the skill activates the bot before GitHub writes, and what to do when something fails.

The bot identity applies **only** to the personal workflow. Job-workflow tickets continue to use the user's personal credentials.

**Scope:** GitHub only. Commits, branch pushes, PR creation, PR updates, PR comments, review comments, review-thread replies, issue comments, labels, merges, and direct `gh api` mutations are attributed to the bot. Linear MCP continues to authenticate as you — Linear ticket reads, transitions, and comments stay under your personal Linear identity.

## Overview

When the agent works on a personal-project ticket:

- **GitHub** — a GitHub App you installed on your personal repos. The bot opens PRs, authors commits, and posts GitHub comments/review replies. You do not appear in the commit history, PR metadata, or PR comment threads for the agent's work.
- **Linear** — your personal Linear identity (via the hosted Linear MCP). Ticket interactions are attributed to you.
- **Credentials** — GitHub App credentials live in macOS Keychain. Keep an out-of-band copy (e.g., NordPass) for disaster recovery.

The skill is **fail-closed**: if any expected Keychain entry is missing or the GitHub token mint fails, the workflow halts with a pointer to the relevant runbook section. The skill never silently substitutes personal GitHub credentials.

## Setup runbook (one-time, manual)

Run this once per machine. After it's done, ticket-start can pick up the bot identity automatically on every personal-project ticket.

### Step A — GitHub App

1. Go to `https://github.com/settings/apps/new` and create a new GitHub App:
   - **GitHub App name:** pick one (e.g., `eduard-agent`). This name appears on PRs and commits as `<name>[bot]`.
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
   security add-generic-password -U -s "ai-skills.gh-bot.app-id" -a "$USER" -w "<APP_ID>"
   security add-generic-password -U -s "ai-skills.gh-bot.installation-id" -a "$USER" -w "<INSTALLATION_ID>"
   security add-generic-password -U -s "ai-skills.gh-bot.private-key" -a "$USER" -w "$(cat /path/to/private-key.pem)"
   ```
   Replace `<APP_ID>`, `<INSTALLATION_ID>`, and the path to the downloaded `.pem`.
5. Pick the bot's git author identity and store it in Keychain too:
   - **Name:** `eduard-agent` (or whatever you named the App).
   - **Email:** GitHub renders commits as the App when the commit email matches the pattern `<APP_ID>+<bot-slug>[bot]@users.noreply.github.com`. The bot-slug is the App's name converted to lowercase with hyphens. Example: App ID `12345` and App name `eduard-agent` → email `12345+eduard-agent[bot]@users.noreply.github.com`.
   ```bash
   security add-generic-password -U -s "ai-skills.gh-bot.git-name" -a "$USER" -w "eduard-agent"
   security add-generic-password -U -s "ai-skills.gh-bot.git-email" -a "$USER" -w "12345+eduard-agent[bot]@users.noreply.github.com"
   ```
6. (Recommended) Save copies of `<APP_ID>`, `<INSTALLATION_ID>`, the `.pem` file, and both git identity strings to your password manager (NordPass) as a backup. The Keychain is local to this machine; if it's lost, this backup is what regenerates it.

After the `.pem` is in Keychain and backed up, securely delete the downloaded `.pem` file from `~/Downloads/` (it's no longer needed at runtime):
```bash
rm -P ~/Downloads/<App-name>.YYYY-MM-DD.private-key.pem
```

### Step B — Defaults the skill assumes

These don't require any setup; they're documented here for reference:

- **Activation:** always-on for personal workflow.
- **Helper-script stack:** bash + `openssl` + `python3` (no `jq`, no npm, no pip).
- **Token mint:** activation and every GitHub write action mint a fresh GitHub installation token. Auto-retry-once with a fresh token if `gh` returns 401 mid-session.
- **Per-worktree git config:** the activation step sets `user.name` and `user.email` per-worktree, so your global git config and other repos are unaffected.

## Activation (two checks, fail-closed)

The main agent runs these two checks before any GitHub write in a personal project, preferably during ticket context gathering after the worktree is available. If either check fails, the workflow halts with the pointer named.

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

Expected output: the value of `ai-skills.gh-bot.git-email` (e.g., `12345+eduard-agent[bot]@users.noreply.github.com`).

If `security find-generic-password` fails on either entry: **halt**. Point at runbook Step A.5.

### After both checks pass

Continue the ticket-start workflow normally.

## Commit author identity

The per-worktree git config set in Check 2 automatically applies to every `git commit` invocation in the worktree. The existing `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer pattern is preserved. No new commit-time machinery.

If you need to verify a specific commit's author identity:
```bash
git -C <worktree> log -1 --format='%an <%ae>'
```

Expected: the bot's name and email.

## GitHub write actions — bot token required

Before any GitHub write action, mint a fresh installation token and scope it to that one command. Do this for PR creation, PR body edits, PR comments, review comments, review-thread replies, issue comments, labels, merges, branch pushes performed through `gh`, and any `gh api` mutation.

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh) gh <write-subcommand> ...
```

For direct REST calls through `gh api`:

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh) gh api --method POST ...
```

For `git push`, do not rely on the local credential helper. Use a fresh installation token as the HTTPS credential for that push:

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh)
BASIC_AUTH=$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')
git -c credential.helper= \
  -c "http.https://github.com/.extraheader=AUTHORIZATION: basic $BASIC_AUTH" \
  push origin <branch>
```

Do not run `gh pr comment`, `gh pr review`, `gh api --method POST/PATCH/PUT/DELETE`, or any other GitHub write through ambient `gh` authentication. `gh auth status` showing a logged-in user is a hazard signal, not permission to write. If the bot token cannot be minted or the bot lacks permission for that operation, halt and draft the exact intended GitHub text in chat instead of posting it through the user's personal account.

Read-only GitHub operations may use ambient credentials if needed. Writes may not.

## PR readiness handoff — PR creation

Before invoking `gh pr create`, follow the GitHub write-action guard above. `<skill-root>` is the same value as in Check 1 (`~/.codex/skills/ticket-start` on Codex or `~/.claude/skills/ticket-start` on Claude Code):

```bash
GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh) gh pr create --title "..." --body "..."
```

The `GH_TOKEN` env var is scoped to the single `gh` invocation. It does not pollute the shell.

## Failure-mode catalog

| Failure | Detection | Action |
|---|---|---|
| Keychain entry missing | `security find-generic-password` exits non-zero | Halt. Stderr names which key. Point at runbook Step A. |
| First-call Keychain access prompt (macOS) | `security` call blocks for the OS prompt | Wait for the user to approve. One-time per session per item. Surface that you're waiting. |
| GitHub token mint fails (4xx/5xx) | `get-bot-gh-token.sh` exits non-zero with the GitHub error body on stderr | Halt. Surface the error verbatim. Point at runbook Step A. Common causes: App revoked, key deleted, repo install removed. |
| `gh pr create` returns 401 mid-session | `gh` exit code non-zero + stderr "401" | Auto-retry **once** with a freshly-minted token (call `get-bot-gh-token.sh` again, re-issue `gh pr create`). If still 401, halt and surface. |
| Bot installed but no permission on this repo | `gh pr create` returns 403/404 | Halt. The App was not installed on this specific repo → runbook Step A.3, install it on the repo. |
| Any GitHub write would use ambient personal `gh` auth | The planned command lacks `GH_TOKEN=$(<skill-root>/scripts/get-bot-gh-token.sh)` scoped to the command | Do not run it. Rebuild the command with a fresh bot token; if that cannot work, draft the intended write in chat and halt. |

All failures are fail-closed: the skill never silently substitutes personal credentials.

## Token rotation (for completeness)

This skill does not proactively rotate tokens. If you want to rotate the GitHub App's private key:

- Generate a new private key on the App's settings page.
- Replace the Keychain entry:
  ```bash
  security delete-generic-password -s "ai-skills.gh-bot.private-key" -a "$USER"
  security add-generic-password -U -s "ai-skills.gh-bot.private-key" -a "$USER" -w "$(cat /path/to/new-private-key.pem)"
  ```
- Revoke the old key from the App settings page after confirming the new one works (mint a token with `get-bot-gh-token.sh` and call any GitHub API endpoint).

Rotation is out of scope for the skill's runtime behavior. The skill assumes whatever's in Keychain is current.
