# Ticket-Start Bot Identity — Design Spec

**Date:** 2026-05-11
**Status:** Approved design, pending implementation plan
**Skill being extended:** `ticket-start` (lives at `codex/skills/ticket-start/` and `claude/skills/ticket-start/`)
**Predecessor:** `2026-05-10-ticket-start-redesign-design.md` (the orchestrator redesign, now merged)

## 1. Goals and non-goals

### Goals

When the agent works on a **personal-workflow** ticket, all external actions (GitHub PR creation, git commits, Linear ticket reads and state transitions) surface in those platforms attributed to a **dedicated bot identity**, never to the user's personal account. The bot is a real first-class actor on both platforms with proper attribution:

- **GitHub:** a GitHub App that owns its identity in PRs, commits, and comments. Real attribution separation in PR lists, audit logs, and `git blame`.
- **Linear:** an OAuth application that acts with `actor=app` on mutations, so ticket transitions and comments show as the bot in Linear's activity feed.

Credentials live in macOS Keychain; the user maintains a personal backup in NordPass. The skill fails closed when bot creds are missing (it does not silently fall back to personal creds).

### Non-goals

- Not changing the job workflow. Job tickets continue to use the user's personal credentials. Bot identity is personal-only.
- Not building a generic "agent runs as different identities per project" framework. This is a single dedicated bot for personal projects.
- Not automating bot account *creation*. The user creates the GitHub App and Linear OAuth App manually (one-time setup). The skill assumes they exist.
- Not changing the skill's phase order, agent roster, dispatch points, bug-fix loop, or self-improvement loop. The six agent role-prompts don't touch credentials.
- Not introducing a new MCP server. The existing Linear MCP is reconfigured to authenticate as the bot.
- Not designing for credential rotation as a workflow. Token rotation is a manual user action covered briefly in the runbook; the skill doesn't proactively rotate.
- Not handling multi-machine setup. Keychain is per-machine. If the user wants the bot identity on a second machine, they re-run the runbook there.

## 2. Architecture summary

The bot identity engages at **three concrete points** during a personal-workflow ticket session. The skill's existing phase structure is untouched; bot identity is a new sub-step in Setup, a per-worktree git config, and a token refresh in Ship.

```
Setup phase
  └─ (after worktree creation, before Scoping dispatch)
      ├─ Mint GitHub installation token via scripts/get-bot-gh-token.sh
      ├─ Set per-worktree git config (user.name / user.email = bot)
      └─ Probe Linear MCP, verify viewer is the bot (not the user)
      → Any failure: stop, point at runbook, fail-closed.

Implement phase
  └─ (no new logic)
      └─ Commits auto-author as bot via the per-worktree git config

Ship phase
  └─ (before `gh pr create`)
      └─ Re-mint installation token, export as GH_TOKEN for the gh invocation
      └─ Linear MCP transitions are already bot-attributed (MCP reconfigured at runbook time)
```

The skill stays a hybrid orchestrator. Main agent owns the activation check at Setup, the token refresh at Ship, and the failure-mode surfaces.

## 3. Identity choices (locked from brainstorm)

| Surface | Choice | Why |
|---|---|---|
| GitHub | **GitHub App** | Real attribution in PRs / commits / comments. Scoped permissions per-repo. Proper for "serious projects." |
| Linear | **OAuth Application** | The only Linear option that surfaces a separate identity in the activity feed when mutations use `actor=app`. |
| Credentials storage | **macOS Keychain** (primary), **NordPass** (user's personal backup) | OS-managed encrypted store. No additional tooling required. User maintains an out-of-band copy. |
| Git commit author | **Bot is author** (per-worktree `git config`). `Co-Authored-By: Claude` trailer preserved. User does not appear in commit history. | Matches "its own identity." |
| Linear MCP reconfiguration | **Reconfigure the existing MCP** to use the bot's OAuth token | All Linear interactions via MCP are bot-attributed, not just ticket-start ones. Simpler skill, fewer code paths. |
| Activation rule | **Always-on for personal workflow.** Bot creds missing → fail-closed at Setup. | Prevents accidental use of personal creds. |
| Helper-script stack | **bash + `openssl` + `python3`** (no `jq`, no npm, no pip deps) | All three are on macOS by default. Zero install. |
| Token refresh cadence | **At Setup and again at Ship.** Inside the bug-fix loop, no refresh unless `gh` returns 401 — then auto-retry once. | GitHub installation tokens last 1h; Setup+Ship covers a typical ticket session. |

## 4. Setup runbook (one-time, manual user action)

The runbook lives in full in `codex/skills/ticket-start/bot-identity.md` (and its claude mirror). This spec summarizes the four steps.

### Step A — GitHub App

1. Create a GitHub App at `https://github.com/settings/apps/new`:
   - **Name:** user-chosen (e.g., `eduard-bot`).
   - **Homepage URL:** any.
   - **Webhook:** disabled.
   - **Repository permissions:** Contents (RW), Pull requests (RW), Issues (RW), Metadata (R, automatic).
   - **User permissions:** none.
   - **Where can this be installed:** "Only on this account."
2. Generate the App's **private key** (downloads as `.pem`). Note the **App ID**.
3. Install the App on the personal repos. Note the **Installation ID** (visible in the URL of the install-confirmation page).
4. Store in Keychain:
   ```bash
   security add-generic-password -s "ai-skills.gh-bot.app-id" -a "$USER" -w "<APP_ID>"
   security add-generic-password -s "ai-skills.gh-bot.installation-id" -a "$USER" -w "<INSTALLATION_ID>"
   security add-generic-password -s "ai-skills.gh-bot.private-key" -a "$USER" -w "$(cat /path/to/private-key.pem)"
   ```
5. Pick the bot's git author identity:
   - `BOT_GIT_NAME` (e.g., `eduard-bot`)
   - `BOT_GIT_EMAIL` — follow GitHub's standard pattern for App-authored commits: `<APP_ID>+<bot-handle>[bot]@users.noreply.github.com`. This makes commits attribute to the App in GitHub's UI.
   - Store both:
     ```bash
     security add-generic-password -s "ai-skills.gh-bot.git-name" -a "$USER" -w "<BOT_GIT_NAME>"
     security add-generic-password -s "ai-skills.gh-bot.git-email" -a "$USER" -w "<BOT_GIT_EMAIL>"
     ```

### Step B — Linear OAuth App

1. Create an OAuth Application at `https://linear.app/<workspace>/settings/api/applications/new`:
   - **Name:** match the GitHub bot (e.g., `eduard-bot`).
   - **Redirect URI:** `http://localhost:8765/callback` (matches the bootstrap helper below).
2. Note the **Client ID** and **Client Secret**.
3. Store the App credentials in Keychain:
   ```bash
   security add-generic-password -s "ai-skills.linear-bot.client-id" -a "$USER" -w "<CLIENT_ID>"
   security add-generic-password -s "ai-skills.linear-bot.client-secret" -a "$USER" -w "<CLIENT_SECRET>"
   ```
4. Run the one-shot OAuth bootstrap:
   ```bash
   bash ~/.codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh <CLIENT_ID> <CLIENT_SECRET>
   # (or the ~/.claude/skills/ticket-start/scripts/ equivalent — same script, mirrored)
   ```
   The script:
   - Spins up `127.0.0.1:8765`.
   - Opens the browser to Linear's authorize URL with `scope=read,write,issues:create` and `actor=app`.
   - User authorizes in the browser.
   - Captures the code, exchanges for tokens, prints them along with the exact `security add-generic-password` commands to paste them into Keychain.
5. Paste the printed commands to store:
   - `ai-skills.linear-bot.access-token`
   - `ai-skills.linear-bot.refresh-token`

### Step C — Reconfigure the Linear MCP

The existing Linear MCP currently authorizes as the user via OAuth. Reconfigure it to use the bot's OAuth access token. Exact instructions depend on the MCP server in use:

- **Official `mcp.linear.app` (hosted):** disconnect the existing OAuth connection in Linear settings, then re-add it but during the OAuth flow authorize as the bot account (i.e., either log into Linear as the bot member first, or use the bot's OAuth app's tokens directly via custom MCP configuration if the hosted server supports it).
- **Self-hosted Linear MCP:** update the MCP server's config (often `~/.config/linear-mcp/config.json` or similar) to use `ai-skills.linear-bot.access-token` from Keychain. Restart the MCP server.

After reconfiguration, the agent's first Linear MCP call should report the bot as `viewer` — verified by the Setup activation probe (Section 5.1).

### Step D — Defaults the skill assumes

Documented inline in `bot-identity.md`:

- **Activation:** always-on for personal workflow. Fail-closed if any Keychain entry is missing.
- **Helper-script stack:** bash + `openssl` + `python3`.
- **Token refresh:** Setup + Ship, with auto-retry-once on mid-session 401.

## 5. Skill activation and runtime flow

### 5.1 Setup phase — new activation sub-step (personal workflow only)

After the worktree is created and before the Scoping subagent is dispatched, the main agent runs three checks **in order**. Each failure halts the workflow with a pointer to the runbook section that fixes it.

1. **Mint a fresh GitHub installation token.** Invoke `<skill-root>/scripts/get-bot-gh-token.sh`. The script reads App ID, Installation ID, and the private key from Keychain, mints a 10-minute JWT signed with the App's private key, exchanges it for an installation access token via `POST /app/installations/<id>/access_tokens`, and prints the token to stdout. The token's ~1-hour validity covers Setup through Ship in a single session. The main agent verifies the token works with a no-op API call (e.g., `GET /installation/repositories`).
2. **Set the worktree's git author identity to the bot.** Read `ai-skills.gh-bot.git-name` and `ai-skills.gh-bot.git-email` from Keychain, then:
   ```bash
   git -C <worktree> config user.name "<BOT_GIT_NAME>"
   git -C <worktree> config user.email "<BOT_GIT_EMAIL>"
   ```
   Per-worktree, so the user's global git config and other repos are unaffected.
3. **Probe the Linear MCP** for `viewer` identity. Call Linear MCP's `me`/`viewer` query (exact field depends on the MCP server schema; the skill's `bot-identity.md` enumerates known shapes). If the viewer is the user's personal account, the MCP was not reconfigured per Step C — halt and point at the runbook.

All three checks pass → Setup continues normally (Scoping subagent dispatch and onward).

### 5.2 Implement phase — no new logic

The per-worktree git config from Setup automatically applies to every `git commit` invocation in the worktree. The existing `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer is preserved. No new commit-time machinery is needed.

### 5.3 Ship phase — token refresh + scoped `GH_TOKEN`

1. Before `gh pr create`, invoke `scripts/get-bot-gh-token.sh` again. Fresh 1-hour token, even if the session has been short.
2. Export the token as `GH_TOKEN` for the duration of the `gh` invocation:
   ```bash
   GH_TOKEN=$("<skill-root>/scripts/get-bot-gh-token.sh") gh pr create --title "…" --body "…"
   ```
3. Linear state transitions (In Progress at Implement start, In Review at PR open, Completed at merge) flow through the already-reconfigured Linear MCP. No change to the transition logic in `personal-workflow.md`.

### 5.4 Failure modes and recovery

| Failure | Detection | Skill behavior |
|---|---|---|
| Keychain entry missing | `security find-generic-password` exits non-zero | Stop. Surface which key is missing. Point at runbook Step A or B. |
| First-call Keychain access prompt (macOS) | `security` call blocks for OS prompt | Wait for user approval; one-time per session per item. Surface that we're waiting. |
| GitHub token mint fails (4xx) | Script exits non-zero with API error body | Stop. Surface the error. Point at runbook Step A. Common causes: revoked App, deleted private key, missing repo install. |
| Linear MCP viewer is the user | Probe returns user's account identity | Stop. Point at runbook Step C. |
| `gh pr create` returns 401 mid-session | `gh` exit code + stderr | Auto-retry once with a freshly-minted token. If still failing, stop and report. |
| Linear OAuth token revoked | MCP call returns auth error | Stop. Point at runbook Step B (rerun the bootstrap). |

All failures are fail-closed. The skill never silently substitutes personal credentials.

## 6. File structure and mirroring

### 6.1 New files (created in both trees)

| File | Purpose |
|---|---|
| `codex/skills/ticket-start/bot-identity.md` | Full runbook (Section 4), activation flow (Section 5.1), runtime contracts (5.2–5.3), failure-mode catalog (5.4). Loaded by `personal-workflow.md` when the workflow is selected. |
| `codex/skills/ticket-start/scripts/get-bot-gh-token.sh` | Runtime helper. Reads Keychain → mints JWT → exchanges for installation token → echoes token. Exit non-zero on any failure with the API error body on stderr. |
| `codex/skills/ticket-start/scripts/linear-oauth-bootstrap.sh` | One-time setup helper. Takes `CLIENT_ID CLIENT_SECRET` args. Runs the local-listener OAuth dance, prints tokens + Keychain-storage commands. |
| `claude/skills/ticket-start/bot-identity.md` | Mirror of the codex file (identical content). |
| `claude/skills/ticket-start/scripts/get-bot-gh-token.sh` | Mirror. |
| `claude/skills/ticket-start/scripts/linear-oauth-bootstrap.sh` | Mirror. |

Both scripts ship with `chmod +x` set.

### 6.2 Modified files

| File | Change |
|---|---|
| `codex/skills/ticket-start/personal-workflow.md` | Add a "Bot Identity (REQUIRED for this workflow)" section right after "Ticket Intake (Linear)" pointing at `bot-identity.md`. |
| `codex/skills/ticket-start/SKILL.md` | Add a single sub-step in the Setup phase (after worktree creation, before Scoping dispatch): "Activate bot identity (personal workflow only). Run the three checks in `bot-identity.md` → `## Setup activation`. Fail-closed on any check." |
| `claude/skills/ticket-start/personal-workflow.md` | Same as codex (mirror). |
| `claude/skills/ticket-start/SKILL.md` | Same as codex (mirror). |

### 6.3 Unchanged files (mirrored as-is)

- All six agent role-prompts (`agents/*.md`)
- `bug-fix-loop.md`
- `self-improvement.md`
- `react-parity.md`
- `verification.md`
- `job-workflow.md`
- `agents/openai.yaml`

### 6.4 Mirroring requirements

Per the user's standing sync rule:
- Every edit under `codex/skills/` mirrors to `~/.codex/skills/` in the same flow.
- Every edit under `claude/skills/` mirrors to `~/.claude/skills/` in the same flow.

Scripts must preserve executable bit through rsync (use `rsync -av`).

### 6.5 Skill-root path resolution

The agent invokes helper scripts via the absolute path of the currently-loaded skill. The path differs by host platform:

- Codex: `~/.codex/skills/ticket-start/scripts/get-bot-gh-token.sh`
- Claude Code: `~/.claude/skills/ticket-start/scripts/get-bot-gh-token.sh`

`bot-identity.md` documents both paths explicitly. The agent uses whichever matches its host. (No env var or runtime detection needed — the agent knows where it loaded the skill from.)

## 7. Deferred to implementation plan

These are plan-level decisions, not design-level:

- Exact JWT signing implementation in `get-bot-gh-token.sh` (which `openssl` invocation, base64url encoding helper in `python3 -c`).
- Exact local-listener implementation in `linear-oauth-bootstrap.sh` (CSRF `state` parameter shape, error-page rendering for failed auth).
- Exact Linear MCP `viewer` query shape (depends on MCP server in use; the implementation must accommodate at least the official `mcp.linear.app` server and surface a clear error if the schema differs).
- The exact wording of the activation step in `SKILL.md` Setup section (one line referencing `bot-identity.md`).
- Whether to extract the three Setup activation checks into a single wrapper script `verify-bot-identity.sh` or keep them as three discrete steps the agent orchestrates directly. Brainstorm landed on the latter (Linear MCP probe can't run inside a shell script — it needs the agent's MCP tool), but a wrapper for the script-able checks (steps 1 and 2) may be worthwhile.
- Whether `bot-identity.md` should embed the full runbook inline or link out to a separate `bot-identity-runbook.md`. Brainstorm landed on inline (single file for the whole feature); revisit if the file grows past ~400 lines during implementation.

## 8. Migration and scope

- **In scope:** new `bot-identity.md`, new `scripts/` directory with two scripts, updates to `personal-workflow.md` and `SKILL.md` in both trees, mirroring to install paths.
- **Out of scope:** any change to job workflow, agent role-prompts, or the bug-fix / self-improvement loops. Pre-populating Keychain entries (the user does that as part of the runbook).
- **Backward compat:** if Keychain entries don't exist, the skill fails closed at Setup with clear pointers. Existing job-workflow ticket sessions are unaffected. Personal-workflow sessions that previously ran under the user's credentials will now require the runbook to be completed first — this is the intended behavior change.
- **Rollback path:** if the user wants to revert to personal-credential personal workflow, remove the activation step from SKILL.md, remove the "Bot Identity" section from personal-workflow.md, and remove the new files. The Linear MCP reconfiguration (Step C) is reversible by re-OAuth'ing as the user.
