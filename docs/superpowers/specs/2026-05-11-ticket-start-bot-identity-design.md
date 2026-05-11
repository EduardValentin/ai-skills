# Ticket-Start Bot Identity — Design Spec

**Date:** 2026-05-11
**Status:** Approved design, pending implementation plan
**Skill being extended:** `ticket-start` (lives at `codex/skills/ticket-start/` and `claude/skills/ticket-start/`)
**Predecessor:** `2026-05-10-ticket-start-redesign-design.md` (the orchestrator redesign, now merged)

## 1. Goals and non-goals

### Goals

When the agent works on a **personal-workflow** ticket, GitHub-side actions (PR creation, commits) surface attributed to a **dedicated GitHub App identity** (`eduard-agent`), never to the user's personal GitHub account. The bot is a real first-class actor on GitHub with proper attribution:

- A GitHub App that owns its identity in PRs, commits, and comments.
- Real attribution separation in PR lists, audit logs, and `git blame`.

Credentials live in macOS Keychain; the user maintains a personal backup in NordPass. The skill fails closed when bot creds are missing (it does not silently fall back to personal creds).

Linear MCP continues to authenticate as the user — Linear's identity model doesn't have first-class AI-agent primitives, and adapting its backend OAuth-app primitive to a local-agent context creates more friction than the audit-trail benefit is worth for personal projects. Linear ticket reads, transitions, and comments stay under the user's personal Linear identity.

### Non-goals

- Not changing the job workflow. Job tickets continue to use the user's personal credentials. Bot identity is personal-only.
- Not building a generic "agent runs as different identities per project" framework. This is a single dedicated GitHub bot for personal projects.
- Not automating bot account *creation*. The user creates the GitHub App manually (one-time setup). The skill assumes it exists.
- Not changing the skill's phase order, agent roster, dispatch points, bug-fix loop, or self-improvement loop. The six agent role-prompts don't touch credentials.
- Not changing the Linear MCP configuration. It remains user-attributed via the hosted `mcp.linear.app`.
- Not designing for credential rotation as a workflow. GitHub App private-key rotation is a manual user action covered briefly in the runbook; the skill doesn't proactively rotate.
- Not handling multi-machine setup. Keychain is per-machine. If the user wants the bot identity on a second machine, they re-run the runbook there.

## 2. Architecture summary

The bot identity engages at **two concrete points** during a personal-workflow ticket session. The skill's existing phase structure is untouched; bot identity is a new sub-step in Setup, a per-worktree git config, and a token refresh in Ship.

```
Setup phase
  └─ (after worktree creation, before Scoping dispatch)
      ├─ Mint GitHub installation token via scripts/get-bot-gh-token.sh
      └─ Set per-worktree git config (user.name / user.email = bot)
      → Any failure: stop, point at runbook, fail-closed.

Implement phase
  └─ (no new logic)
      └─ Commits auto-author as bot via the per-worktree git config

Ship phase
  └─ (before `gh pr create`)
      └─ Re-mint installation token, export as GH_TOKEN for the gh invocation
```

The skill stays a hybrid orchestrator. Main agent owns the activation checks at Setup, the token refresh at Ship, and the failure-mode surfaces.

## 3. Identity choices (locked from brainstorm)

| Surface | Choice | Why |
|---|---|---|
| GitHub | **GitHub App** | Real attribution in PRs / commits / comments. Scoped permissions per-repo. Proper for "serious projects." Standard pattern for production GitHub automation. |
| Linear | **User identity (no change)** | Linear lacks first-class AI-agent identity primitives. The closest (OAuth app + `actor=app`) is designed for backend services with their own auth infrastructure, not local agents. Adapting it requires custom proxy code and operational overhead disproportionate to the audit-trail benefit on personal projects. Industry standard for local AI agents (Claude Code, Cursor, Aider, GitHub Copilot Workspace) is to act as the user; we follow suit on Linear. |
| Credentials storage | **macOS Keychain** (primary), **NordPass** (user's personal backup) | OS-managed encrypted store. No additional tooling required. User maintains an out-of-band copy. |
| Git commit author | **Bot is author** (per-worktree `git config`). `Co-Authored-By: Claude` trailer preserved. User does not appear in commit history for agent's work. | Matches "its own identity" on GitHub. |
| Activation rule | **Always-on for personal workflow.** GitHub bot creds missing → fail-closed at Setup. | Prevents accidental use of personal GitHub creds on the agent's work. |
| Helper-script stack | **bash + `openssl` + `python3`** (no `jq`, no npm, no pip deps) | All three are on macOS by default. Zero install. |
| Token refresh cadence | **Every Setup and every Ship.** Inside the bug-fix loop, no refresh unless `gh` returns 401 — then auto-retry once. | GitHub installation tokens last 1h; Setup+Ship covers a typical ticket session. |

## 4. Setup runbook (one-time, manual user action)

The runbook lives in full in `codex/skills/ticket-start/bot-identity.md` (and its claude mirror). This spec summarizes the GitHub App setup; refer to the full runbook for exact `security` commands.

### Step A — GitHub App

1. Create a GitHub App at `https://github.com/settings/apps/new`:
   - **Name:** user-chosen (e.g., `eduard-agent`).
   - **Homepage URL:** any.
   - **Webhook:** disabled.
   - **Repository permissions:** Contents (RW), Pull requests (RW), Issues (RW), Metadata (R, automatic).
   - **User permissions:** none.
   - **Where can this be installed:** "Only on this account."
2. Generate the App's **private key** (downloads as `.pem`). Note the **App ID**.
3. Install the App on the personal repos. Note the **Installation ID** (visible in the URL of the install-confirmation page).
4. Store in Keychain:
   - `ai-skills.gh-bot.app-id`
   - `ai-skills.gh-bot.installation-id`
   - `ai-skills.gh-bot.private-key` (PEM contents)
5. Pick the bot's git author identity:
   - `BOT_GIT_NAME` (e.g., `eduard-agent`)
   - `BOT_GIT_EMAIL` — follows GitHub's pattern for App-authored commits: `<APP_ID>+<bot-handle>[bot]@users.noreply.github.com`. Makes commits attribute to the App in GitHub's UI.
   - Store both:
     - `ai-skills.gh-bot.git-name`
     - `ai-skills.gh-bot.git-email`

After the `.pem` is in Keychain (and backed up to NordPass), securely delete the downloaded `.pem` from `~/Downloads/`. Runtime depends only on Keychain.

### Step B — Defaults the skill assumes

Documented inline in `bot-identity.md`:

- **Activation:** always-on for personal workflow. Fail-closed if any Keychain entry is missing.
- **Helper-script stack:** bash + `openssl` + `python3`.
- **Token mint:** every Setup phase and every Ship phase. Auto-retry-once on mid-session 401.

## 5. Skill activation and runtime flow

### 5.1 Setup phase — new activation sub-step (personal workflow only)

After the worktree is created and before the Scoping subagent is dispatched, the main agent runs two checks **in order**. Each failure halts the workflow with a pointer to the runbook section that fixes it.

1. **Mint a fresh GitHub installation token.** Invoke `<skill-root>/scripts/get-bot-gh-token.sh`. The script reads App ID, Installation ID, and the private key from Keychain, mints a 9-minute JWT signed with the App's private key, exchanges it for an installation access token via `POST /app/installations/<id>/access_tokens`, and prints the token to stdout. The token's ~1-hour validity covers Setup through Ship in a single session. The main agent verifies the token works with a no-op API call (e.g., `GET /installation/repositories`).
2. **Set the worktree's git author identity to the bot.** Read `ai-skills.gh-bot.git-name` and `ai-skills.gh-bot.git-email` from Keychain, then:
   ```bash
   git -C <worktree> config user.name "<BOT_GIT_NAME>"
   git -C <worktree> config user.email "<BOT_GIT_EMAIL>"
   ```
   Per-worktree, so the user's global git config and other repos are unaffected.

Both checks pass → Setup continues normally (Scoping subagent dispatch and onward).

### 5.2 Implement phase — no new logic

The per-worktree git config from Setup automatically applies to every `git commit` invocation in the worktree. The existing `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` trailer is preserved. No new commit-time machinery is needed.

### 5.3 Ship phase — token refresh + scoped `GH_TOKEN`

1. Before `gh pr create`, invoke `scripts/get-bot-gh-token.sh` again. Fresh 1-hour token, even if the session has been short.
2. Export the token as `GH_TOKEN` for the duration of the `gh` invocation:
   ```bash
   GH_TOKEN=$("<skill-root>/scripts/get-bot-gh-token.sh") gh pr create --title "…" --body "…"
   ```
3. Linear state transitions (In Progress at Implement start, In Review at PR open, Completed at merge) continue to flow through the existing Linear MCP under your personal identity. No bot-identity logic on the Linear side.

### 5.4 Failure modes and recovery

| Failure | Detection | Skill behavior |
|---|---|---|
| Keychain entry missing | `security find-generic-password` exits non-zero | Stop. Surface which key is missing. Point at runbook Step A. |
| First-call Keychain access prompt (macOS) | `security` call blocks for OS prompt | Wait for user approval; one-time per session per item. Surface that we're waiting. |
| GitHub token mint fails (4xx) | Script exits non-zero with API error body | Stop. Surface the error. Point at runbook Step A. Common causes: revoked App, deleted private key, missing repo install. |
| `gh pr create` returns 401 mid-session | `gh` exit code + stderr | Auto-retry once with a freshly-minted token. If still failing, stop and report. |

All failures are fail-closed. The skill never silently substitutes personal GitHub credentials.

## 6. File structure and mirroring

### 6.1 New files (created in both trees)

| File | Purpose |
|---|---|
| `codex/skills/ticket-start/bot-identity.md` | Full runbook (Section 4), activation flow (Section 5.1), runtime contracts (5.2–5.3), failure-mode catalog (5.4). Loaded by `personal-workflow.md` when the workflow is selected. |
| `codex/skills/ticket-start/scripts/get-bot-gh-token.sh` | Runtime helper. Reads Keychain → mints JWT → exchanges for installation token → echoes token. Exit non-zero on any failure with the API error body on stderr. |
| `claude/skills/ticket-start/bot-identity.md` | Mirror of the codex file (identical content). |
| `claude/skills/ticket-start/scripts/get-bot-gh-token.sh` | Mirror. |

The script ships with `chmod +x` set.

### 6.2 Modified files

| File | Change |
|---|---|
| `codex/skills/ticket-start/personal-workflow.md` | Add a "Bot Identity (REQUIRED for this workflow)" section right after "Ticket Intake (Linear)" pointing at `bot-identity.md`. |
| `codex/skills/ticket-start/SKILL.md` | Add a single sub-step in the Setup phase (after worktree creation, before Scoping dispatch): "Activate bot identity (personal workflow only). Run the two checks in `bot-identity.md` → `## Setup activation`. Fail-closed on any check." |
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
- Exact GitHub-bot-email format that GitHub renders as the App (the `<APP_ID>+<slug>[bot]@users.noreply.github.com` pattern — verify with a test commit during implementation).
- The exact wording of the activation step in `SKILL.md` Setup section (one line referencing `bot-identity.md`).
- Whether to extract the two Setup activation checks into a single wrapper script `verify-bot-identity.sh` or keep them as discrete steps the agent orchestrates directly.

## 8. Migration and scope

- **In scope:** new `bot-identity.md`, new `scripts/get-bot-gh-token.sh`, updates to `personal-workflow.md` and `SKILL.md` in both trees, mirroring to install paths.
- **Out of scope:** any change to job workflow, agent role-prompts, the bug-fix / self-improvement loops, or Linear MCP. Pre-populating Keychain entries (the user does that as part of the runbook). Any Linear-side bot identity work (Linear MCP stays as user-attributed).
- **Backward compat:** if GitHub bot Keychain entries don't exist, the skill fails closed at Setup with clear pointers. Existing job-workflow ticket sessions are unaffected. Personal-workflow sessions that previously ran under the user's GitHub credentials will now require the runbook to be completed first — this is the intended behavior change.
- **Rollback path:** if the user wants to revert to personal-GitHub-credential personal workflow, remove the activation step from SKILL.md, remove the "Bot Identity" section from personal-workflow.md, and remove the new files.

## 9. Design history — Linear identity considered

Linear-side bot identity was originally part of this spec. During implementation, we explored:

1. **Linear OAuth app + `authorization_code` grant** with the bot's access token injected into MCP client configs as a `Bearer` header. Worked, but required manual token rotation every 30 days plus app restart to pick up the new token.
2. **Linear OAuth app + `client_credentials` grant** with the same Bearer-header injection. Cleaner credential model but identical operational friction.
3. **Local Linear MCP proxy** that injects + auto-refreshes the bot's token in front of the hosted `mcp.linear.app`. Eliminates rotation friction at the cost of a long-running local process, custom code, and ongoing maintenance.

The fundamental issue is that Linear's identity model doesn't have a first-class "AI agent" primitive. The closest available primitive (`actor=app` via OAuth applications) was designed for backend services with their own deployment infrastructure — not for local LLM-driven agents. Every approach to fit it into our context required either non-trivial custom infrastructure (option 3) or manual operational steps that defeat the "set it and forget it" goal (options 1 and 2).

Industry standard for local AI agents (Claude Code, Cursor, Aider, GitHub Copilot Workspace) is to act as the user. We follow that convention on Linear. The user remains responsible for distinguishing their own work from the agent's via git history (where the bot's GitHub identity provides clean separation) and chat logs.

The Linear-side work was reverted as part of the same PR that introduces the GitHub-side bot identity. See commit history on the `ticket-start-bot-identity` branch for the full rationale.
