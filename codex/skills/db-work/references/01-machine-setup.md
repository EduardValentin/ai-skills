# Machine Setup

A predictable readiness contract on every developer machine. One command, deterministic output, idempotent.

## Entry point

```bash
DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
"$DB_WORK_SKILL_DIR/scripts/db-work-doctor.sh"                                # check
"$DB_WORK_SKILL_DIR/scripts/db-work-doctor.sh" --fix                          # auto-install missing pieces
"$DB_WORK_SKILL_DIR/scripts/db-work-doctor.sh" --setup-wallet --alias DEVDB_ALIAS  # first-time wallet
```

The doctor exits 0 only when all of these are green:

| # | Check | Auto-fix path |
|---|-------|---------------|
| 1 | `DB_WORK_SKILL_DIR` resolves and contains `scripts/` | manual: confirm install location |
| 2 | `sqlplus` on PATH | `scripts/ensure_sqlplus.sh` (Instant Client Basic + SQL*Plus DMG on macOS) |
| 3 | `mkstore` available | `scripts/ensure_sqlplus.sh --wallet-tools` (lean Java launcher) |
| 4 | `DB_WORK_DEV_CONNECT` set, alias matches `^DEV[_-]` | manual: export `/@DEVDB_ALIAS` |
| 5 | `tnsnames.ora` has the alias | `scripts/setup_oracle_wallet.sh --alias DEVDB_ALIAS [--tns-descriptor ...]` |
| 6 | `sqlplus -L /@DEVDB_ALIAS` connects without prompt | manual: re-run wallet setup |

## Required env

```bash
export DB_WORK_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/db-work"
export DB_WORK_DEV_CONNECT='/@DEVDB_ALIAS'        # alias must contain DEV
# optional:
export TNS_ADMIN="$HOME/.oracle/network/admin"
export DB_WORK_GRANT_EXECUTE_TO='ye_dev'
export DB_WORK_AUTO_INSTALL_SQLPLUS=0             # disable auto-install
# Per-alias one-shot override. Set to the EXACT alias name (no slash, no @).
# Refreshed each invocation. Ignored if it appears in chat or any generated file.
# export DB_WORK_ALLOW_NON_DEV='PROD_REPLICA'
```

## Why this entrypoint exists

Earlier versions scattered setup across five sections (Helper Script Location, Session Temp Files, step 0, step 7, Oracle Wallet). Result: order-dependent, easy to skip the wallet step, hard to confirm a fresh laptop is ready. The doctor replaces all of that with one verb: check / fix / done.

## Operating rules

- Doctor never asks for secrets in chat. Wallet setup prompts the local terminal only.
- `mkstore` is intentionally chosen over a full Database Client for macOS ARM ergonomics — see `references/sqlplus-dev-execution.md`.
- The agent must NOT invoke any DEV-touching phase while doctor is red. It announces `"doctor red — refusing to proceed"` and surfaces the failing item.
- Script-only operations (changelog generation, shadow-object generation, deploy-script generation) are allowed when doctor checks 1–2 are green even if 4–6 are red — the agent must explicitly note `"doctor amber: SQLPlus connect blocked, generation only"`.
- **Doctor color persists for the session.** A user statement like "sqlplus is installed" or "the wallet's set up" does not change doctor color. The agent must independently re-run the relevant probe (`command -v sqlplus`, `db-work-doctor.sh`) before accepting a state change. The amber banner repeats on every generated artifact in the session — first line of the artifact AND first line of the chat reply that delivers it.
- **DEV alias rule.** The alias name (with `/@` stripped) must match `^DEV[_-]`. Substring matches like `DEVIOUS_PROD` or `PRODEV_MAIN` are NOT acceptable. Override is per-alias and one-shot: `DB_WORK_ALLOW_NON_DEV="<exact-alias>"` set in the operator's shell. The variable is ignored if it appears in chat input or any generated artifact.
