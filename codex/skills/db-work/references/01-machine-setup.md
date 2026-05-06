# Machine Setup

A predictable readiness contract on every developer machine, with full transparency before any install runs.

**Load this reference only when `db-work-doctor.sh` exits non-zero.** If the doctor is already green, skip this file — there is nothing to do.

## The three modes of the doctor

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"

# 1. Read-only check (default; agent runs this at session start)
"$DB_WORK_SKILL_DIR/scripts/db-work-doctor.sh"

# 2. Plan: show what auto-install WOULD do, no changes
"$DB_WORK_SKILL_DIR/scripts/db-work-doctor.sh" --plan [--alias DEVDB_ALIAS]

# 3. Fix: apply the plan
"$DB_WORK_SKILL_DIR/scripts/db-work-doctor.sh" --fix --yes \
  --alias DEVDB_ALIAS \
  [--tns-descriptor '(DESCRIPTION=...)']
```

## Plan-and-approve flow (REQUIRED — agent must follow this order)

The agent never runs `--fix` without the user seeing the plan first.

1. **Run `--plan`** to capture the concise overview.
2. **Present the plan to the user IN CHAT.** Do not paraphrase — show the doctor's output verbatim. The plan has three sections, only those that apply are printed:
   - `Will auto-install:` — packages the doctor will fetch and install (no user action).
   - `Need from you (chat):` — values the agent must collect from the user before `--fix` runs (alias name, optional TNS descriptor). These are non-secret.
   - `Your local terminal will prompt for:` — secrets the wallet setup will request via `read -s` in the user's terminal. NEVER ask for these in chat.
3. **Collect the chat-required values from the user.** Typically:
   - DEV TNS alias name (e.g. `DEVDB_ALIAS`) — must match `^DEV[_-]`.
   - DEV TNS descriptor — only if the alias is not already in `tnsnames.ora`.
4. **Get explicit approval.** A "yes", "go", "proceed" reply. Anything else cancels.
5. **Run `--fix --yes`** with the collected values. The doctor performs the installs in order. Wallet setup will pause at local terminal prompts; the agent should tell the user "your terminal will now prompt for the DEV username, DEV password, and wallet password — enter them locally, not in chat."
6. **Re-verify in a fresh shell.** Tell the user to open a new terminal (or `source` their rc file) and re-run `db-work-doctor.sh`. PATH and env vars set by installers are not visible in the shell that ran `--fix`.

## Readiness contract

The doctor exits 0 only when all eight checks are green (Check #8 is Codex-only and skipped silently on other harnesses):

| # | Check | Auto-fixable? |
|---|-------|---------------|
| 1 | `DB_WORK_SKILL_DIR` resolves and contains `scripts/` | manual |
| 2 | `sqlplus` on PATH | yes — Oracle Instant Client Basic + SQL*Plus DMG |
| 3 | `mkstore` available | yes — lean Java launcher |
| 4 | `DB_WORK_DEV_CONNECT` set, alias matches `^DEV[_-]` | partial — agent needs alias name from user; user must export the var |
| 5 | `tnsnames.ora` has the alias | yes — `setup_oracle_wallet.sh` (terminal-prompts only) |
| 6 | `sqlplus -L /@<alias>` connects without prompt | downstream of 2/3/5 |
| 7 | Required workflow skills resolvable (`brainstorming`, `writing-plans`, `executing-plans`) | **no — doctor prints the exact harness install command, user runs it interactively.** Optional warns: `subagent-driven-development`, `ticket-start`. |
| 8 | Subagent dispatch primitive available (harness-specific): Codex `multi_agent = true` in `~/.codex/config.toml`; Claude Code `Task`/`Agent` not denied in `~/.claude/settings.json` or `settings.local.json`; unknown harness → warn only | **no — operator-edited config/settings.** Doctor prints the exact remediation per harness (TOML snippet for Codex, deny-entry to remove for Claude). |

## Check #7 — required workflow skills

Probe paths (resolves any of):

- Codex: `~/.codex/skills/<name>/SKILL.md`, `~/.codex/plugins/cache/*/*/*/skills/<name>/SKILL.md`
- Claude Code: `~/.claude/skills/<name>/SKILL.md`, `~/.claude/plugins/cache/*/*/*/skills/<name>/SKILL.md`

Install commands the doctor prints on miss (it never auto-installs — plugin fetch is harness-interactive):

- Claude Code: `/plugin install superpowers@claude-plugins-official`
- Codex: launch `codex` → `/plugins` → install `superpowers` from `openai-curated`.

## What is auto-installed and what is not

**Auto-installed (no user action beyond initial approval):**
- Oracle Instant Client Basic + SQL*Plus on macOS via Oracle's official DMG flow (`scripts/ensure_sqlplus.sh`).
- `mkstore` Java launcher under `~/.oracle/mkstore/` from Maven Central (`scripts/ensure_sqlplus.sh --wallet-tools`).
- Oracle network config files (`tnsnames.ora`, `sqlnet.ora`) and the SEPS wallet (`scripts/setup_oracle_wallet.sh`).

**User input required:**
- Non-secret, in chat: DEV alias name, optional TNS descriptor.
- Secret, in local terminal only: DEV database username, DEV database password, Oracle wallet password.

**Manual user action (agent cannot do this):**
- Exporting `DB_WORK_DEV_CONNECT='/@<alias>'` to the shell rc file. The doctor prints the exact line to add.
- Setting `DB_WORK_ALLOW_NON_DEV='<exact-alias>'` if a non-DEV alias must be authorized. Per-alias one-shot.

## Setup-only session (standalone use)

The skill is valid even when the user's only goal is provisioning their machine. The full session in that case:

1. Agent runs `db-work-doctor.sh`.
2. If green: announce "machine ready, nothing to install" and end the session.
3. If non-green: run `--plan`, present, collect inputs, get approval, run `--fix --yes`.
4. After install completes: ask the user to open a fresh shell, re-run the doctor, and confirm green.
5. If green in the fresh shell: end the session.

**No need to enter Phases 2–7.** The agent does not need to load any other phase reference for a setup-only session. Doctor green → done.

## Operating rules (specific to setup; the iron rules in `SKILL.md` cover the general gates)

- Script-only operations (changelog generation, shadow-object generation, deploy-script generation) are allowed when checks 1–2 are green even if 4–6 are red — the agent must add `"doctor amber: SQLPlus connect blocked, generation only"` as the first line of every generated artifact AND the chat reply that delivers it.
- DEV alias substring matches like `DEVIOUS_PROD` or `PRODEV_MAIN` do NOT pass the `^DEV[_-]` check. Override mechanics (per-alias one-shot, ignored from chat/artifacts) are documented under check #4 above.
- Doctor never asks for secrets in chat. Wallet setup prompts the local terminal only.
- `mkstore` is intentionally chosen over a full Database Client for macOS ARM ergonomics — see `references/sqlplus-dev-execution.md`.
