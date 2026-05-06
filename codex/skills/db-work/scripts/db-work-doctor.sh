#!/usr/bin/env bash
# db-work-doctor.sh — single-shot machine readiness check + plan-and-approve auto-fix.
#
# Three modes:
#   (default)         read-only checks. exit 0 if green, 1 otherwise.
#   --plan            read-only checks + concise plan of what --fix would do.
#                     does not install anything. exits 0 if green, 1 otherwise.
#   --fix             read-only checks, print plan, ask for approval, run installs.
#                     use --yes to skip the approval prompt (after agent has
#                     already shown the user the plan via --plan).
#
# Other flags:
#   --alias NAME            alias to verify (defaults to DB_WORK_DEV_CONNECT)
#   --tns-descriptor STR    non-secret TNS descriptor to register if alias is new
#   --setup-wallet          alias for --fix (legacy)
#
# Exit codes:
#   0  all green (or --plan with all green)
#   1  at least one red item (or --plan with red, or --fix aborted)
#   64 bad usage

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FIX=0
PLAN=0
YES=0
ALIAS=""
TNS_DESCRIPTOR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix)            FIX=1; shift ;;
    --plan)           PLAN=1; shift ;;
    --yes)            YES=1; shift ;;
    --setup-wallet)   FIX=1; shift ;;
    --alias)          ALIAS="$2"; shift 2 ;;
    --tns-descriptor) TNS_DESCRIPTOR="$2"; shift 2 ;;
    -h|--help)        sed -n '2,22p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *) echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done

red=0
declare -a installs           # items the doctor will auto-install
declare -a agent_inputs       # items the agent needs from the user in chat
declare -a terminal_inputs    # items the local terminal will prompt for during install
declare -a actions            # ordered list of actions to perform under --fix
declare -a plugin_install_cmds # exact install commands the user must run in their harness (not auto-fixable)

ok()         { printf "[ok]   %s\n" "$*"; }
fix_needed() { printf "[fix]  %s\n" "$*"; red=$((red+1)); }
fail()       { printf "[fail] %s\n" "$*"; red=$((red+1)); }

# ---------- Pass 1: read-only checks ----------

# 1. SKILL_DIR
if [[ -d "$SKILL_DIR/scripts" ]]; then
  ok "DB_WORK_SKILL_DIR=$SKILL_DIR"
else
  fail "skill scripts directory missing at $SKILL_DIR"
  exit 1
fi

# 2. sqlplus
if command -v sqlplus >/dev/null 2>&1; then
  ver=$(sqlplus -v 2>/dev/null | head -n1 || echo "version unknown")
  ok "sqlplus on PATH ($ver)"
else
  fix_needed "sqlplus not on PATH"
  installs+=("Oracle Instant Client Basic + SQL*Plus (macOS DMG, ~150 MB from Oracle)")
  actions+=("install_sqlplus")
fi

# 3. mkstore (only required for wallet setup)
if command -v mkstore >/dev/null 2>&1 || [[ -x "$HOME/.oracle/mkstore/bin/mkstore" ]]; then
  ok "mkstore available"
else
  fix_needed "mkstore not available (needed only for wallet setup)"
  installs+=("mkstore Java launcher (~5 MB jar from Maven Central)")
  actions+=("install_mkstore")
fi

# 4. DB_WORK_DEV_CONNECT
if [[ -z "$ALIAS" ]]; then
  ALIAS="${DB_WORK_DEV_CONNECT:-}"
fi
alias_blocked=0
if [[ -z "$ALIAS" ]]; then
  fix_needed "DB_WORK_DEV_CONNECT not set; expected /@<DEV-alias>"
  agent_inputs+=("DEV TNS alias name (e.g. DEVDB_ALIAS) — pass via --alias <name>; the user must export DB_WORK_DEV_CONNECT='/@<name>' in their shell after setup")
  alias_blocked=1
else
  ok "DB_WORK_DEV_CONNECT=$ALIAS"
  alias_name_check="${ALIAS#/@}"
  if [[ "$alias_name_check" =~ ^DEV[_-] ]]; then
    ok "alias '$alias_name_check' matches ^DEV[_-]"
  else
    override="${DB_WORK_ALLOW_NON_DEV:-}"
    if [[ -n "$override" && "$override" == "$alias_name_check" ]]; then
      ok "non-DEV alias '$alias_name_check' explicitly authorized via DB_WORK_ALLOW_NON_DEV"
    else
      fail "alias '$alias_name_check' does not match ^DEV[_-]; set DB_WORK_ALLOW_NON_DEV='$alias_name_check' in your shell to override (per-alias one-shot, not auto-fixable)"
    fi
  fi
fi

# 5. tnsnames.ora has the alias
if [[ -n "$ALIAS" ]]; then
  alias_name="${ALIAS#/@}"
  tns_admin="${TNS_ADMIN:-$HOME/.oracle/network/admin}"
  if [[ -f "$tns_admin/tnsnames.ora" ]] && grep -qE "^[[:space:]]*${alias_name}[[:space:]]*=" "$tns_admin/tnsnames.ora"; then
    ok "tnsnames.ora contains $alias_name (TNS_ADMIN=$tns_admin)"
  else
    fix_needed "tnsnames.ora missing $alias_name (TNS_ADMIN=$tns_admin)"
    if [[ -z "$TNS_DESCRIPTOR" ]]; then
      agent_inputs+=("DEV TNS descriptor (host, port, service) — pass via --tns-descriptor; only needed if alias is not already in $tns_admin/tnsnames.ora")
    fi
    terminal_inputs+=("DEV database username")
    terminal_inputs+=("DEV database password")
    terminal_inputs+=("Oracle wallet password")
    actions+=("setup_wallet")
  fi
fi

# 6. live connect
if [[ -n "$ALIAS" ]] && command -v sqlplus >/dev/null 2>&1; then
  if echo "exit;" | sqlplus -L -S "$ALIAS" >/dev/null 2>&1; then
    ok "sqlplus -L $ALIAS connects without prompt"
  else
    fix_needed "sqlplus -L $ALIAS does not connect"
    # No new action; this is a downstream consequence of checks 2/3/5.
  fi
fi

# 7. Required cross-skill plugins resolvable.
# Detect harness from SKILL_DIR; probe each required skill's expected install paths.
# Never auto-installed — print the exact command for the detected harness so the
# user can run it in an interactive session. See references/01-machine-setup.md.
detect_harness() {
  case "$SKILL_DIR" in
    *"/.codex/"*|*"/codex/"*)   echo codex ;;
    *"/.claude/"*|*"/claude/"*) echo claude ;;
    *)                          echo unknown ;;
  esac
}

resolve_skill_path() {
  local skill="$1" pat
  for pat in \
      "$HOME/.codex/skills/$skill/SKILL.md" \
      "$HOME/.codex/plugins/cache/"*"/"*"/"*"/skills/$skill/SKILL.md" \
      "$HOME/.claude/skills/$skill/SKILL.md" \
      "$HOME/.claude/plugins/cache/"*"/"*"/"*"/skills/$skill/SKILL.md"; do
    [[ -f "$pat" ]] && { echo "$pat"; return 0; }
  done
  return 1
}

emit_install_hint() {
  local skill="$1" harness="$2" plugin="$3"
  local qualified
  if [[ "$plugin" == "superpowers" ]]; then
    qualified="superpowers:$skill"
  else
    qualified="$skill"
  fi
  case "$harness" in
    claude)
      printf "       install (Claude Code): /plugin install %s@claude-plugins-official  # provides %s\n" "$plugin" "$qualified"
      plugin_install_cmds+=("Claude Code: /plugin install $plugin@claude-plugins-official  # provides $qualified")
      ;;
    codex)
      printf "       install (Codex): launch 'codex' interactively → /plugins → install '%s' from 'openai-curated'  # provides %s\n" "$plugin" "$qualified"
      plugin_install_cmds+=("Codex: 'codex' → /plugins → install '$plugin' from 'openai-curated'  # provides $qualified")
      ;;
    *)
      printf "       install (Claude Code): /plugin install %s@claude-plugins-official\n" "$plugin"
      printf "       install (Codex):       launch 'codex' interactively → /plugins → install '%s' from 'openai-curated'\n" "$plugin"
      plugin_install_cmds+=("Claude Code: /plugin install $plugin@claude-plugins-official  # provides $qualified")
      plugin_install_cmds+=("Codex: 'codex' → /plugins → install '$plugin' from 'openai-curated'  # provides $qualified")
      ;;
  esac
}

HARNESS="$(detect_harness)"
REQUIRED_SUPERPOWERS=(brainstorming writing-plans executing-plans)
OPTIONAL_SUPERPOWERS=(subagent-driven-development)
OPTIONAL_STANDALONE=(ticket-start)

for s in "${REQUIRED_SUPERPOWERS[@]}"; do
  if path="$(resolve_skill_path "$s")"; then
    ok "skill superpowers:$s resolvable ($path)"
  else
    fail "required skill superpowers:$s not installed"
    emit_install_hint "$s" "$HARNESS" superpowers
  fi
done
for s in "${OPTIONAL_SUPERPOWERS[@]}"; do
  if path="$(resolve_skill_path "$s")"; then
    ok "skill superpowers:$s resolvable ($path)"
  else
    printf "[warn] optional skill superpowers:%s not installed (used only on the subagent-driven Phase 5 path)\n" "$s"
    emit_install_hint "$s" "$HARNESS" superpowers
  fi
done
for s in "${OPTIONAL_STANDALONE[@]}"; do
  if path="$(resolve_skill_path "$s")"; then
    ok "skill $s resolvable ($path)"
  else
    printf "[warn] optional skill %s not installed (intake falls back to direct ask)\n" "$s"
    emit_install_hint "$s" "$HARNESS" "$s"
  fi
done

# 8. Subagent dispatch primitive available (harness-specific).
# Phase 2 scope-research and Phase 5 per-variant subagents both depend on this primitive.
# Codex: multi_agent flag in config.toml. Claude: Task/Agent tool not denied in settings.
case "$HARNESS" in
  codex)
    codex_config="${CODEX_CONFIG:-$HOME/.codex/config.toml}"
    if [[ -f "$codex_config" ]] && grep -qE '^[[:space:]]*multi_agent[[:space:]]*=[[:space:]]*true\b' "$codex_config"; then
      ok "codex multi_agent=true in $codex_config (spawn_agent available)"
    elif [[ -f "$codex_config" ]]; then
      fail "codex multi_agent flag not enabled in $codex_config; add '[features]\nmulti_agent = true' so spawn_agent is available for Phase 2 scope-research and Phase 5 per-variant subagents (not auto-fixable — operator-edited config)"
    else
      fail "codex config $codex_config not found; create it with '[features]\nmulti_agent = true' so spawn_agent is available (not auto-fixable — operator-edited config)"
    fi
    ;;
  claude)
    # Task/Agent dispatch is available by default in Claude Code. Flag only if a settings file
    # explicitly denies it. Use python3 (already a project dependency for generate_*.py scripts)
    # so multi-line JSON parsing stays robust.
    blocked_in=""
    blocked_entry=""
    for cfg in "$HOME/.claude/settings.json" "$HOME/.claude/settings.local.json"; do
      [[ -f "$cfg" ]] || continue
      hit="$(python3 - "$cfg" <<'PY' 2>/dev/null
import json, sys
try:
    with open(sys.argv[1]) as f:
        cfg = json.load(f)
except Exception:
    sys.exit(0)
deny = (cfg.get("permissions") or {}).get("deny") or []
for entry in deny:
    if not isinstance(entry, str):
        continue
    head = entry.split("(", 1)[0].strip()
    if head in ("Task", "Agent"):
        print(entry)
        break
PY
)"
      if [[ -n "$hit" ]]; then
        blocked_in="$cfg"
        blocked_entry="$hit"
        break
      fi
    done
    if [[ -n "$blocked_in" ]]; then
      fail "claude Task/Agent dispatch denied in $blocked_in (deny entry: '$blocked_entry'); remove or scope the entry so subagent dispatch works for Phase 2 scope-research and Phase 5 per-variant subagents (not auto-fixable — user-edited settings)"
    else
      ok "claude Task/Agent dispatch available (no deny entries in ~/.claude/settings.json or settings.local.json)"
    fi
    ;;
  *)
    # Unknown harness: cannot probe the dispatch primitive. Don't fail — the operator may be
    # running the skill outside the two supported harnesses; just surface that the gate cannot
    # be verified, so the agent knows Phase 2 may silently fall back to parent-side reads.
    printf "[warn] unknown harness; cannot verify subagent dispatch primitive — Phase 2 scope-research may silently fall back to parent-side reads\n"
    ;;
esac

# ---------- Pass 2: print plan if requested ----------

if [[ "$red" -gt 0 && ( "$PLAN" -eq 1 || "$FIX" -eq 1 ) ]]; then
  echo
  echo "Setup plan"
  echo "----------"
  if [[ ${#installs[@]} -gt 0 ]]; then
    echo "Will auto-install:"
    for x in "${installs[@]}"; do echo "  - $x"; done
  fi
  if [[ ${#agent_inputs[@]} -gt 0 ]]; then
    [[ ${#installs[@]} -gt 0 ]] && echo
    echo "Need from you (chat):"
    for x in "${agent_inputs[@]}"; do echo "  - $x"; done
  fi
  if [[ ${#terminal_inputs[@]} -gt 0 ]]; then
    echo
    echo "Your local terminal will prompt for (during install — NEVER paste in chat):"
    for x in "${terminal_inputs[@]}"; do echo "  - $x"; done
  fi
  if [[ ${#plugin_install_cmds[@]} -gt 0 ]]; then
    echo
    echo "Plugin/skill installs (run yourself in the harness — doctor will NOT auto-install):"
    for x in "${plugin_install_cmds[@]}"; do echo "  - $x"; done
  fi
fi

# ---------- Pass 3: --plan stops here ----------

if [[ "$PLAN" -eq 1 ]]; then
  echo
  if [[ "$red" -eq 0 ]]; then
    echo "doctor: all green; no setup needed"
    exit 0
  else
    echo "doctor: $red item(s) need attention. Run with --fix --yes to apply the plan above (after presenting it to the user)."
    exit 1
  fi
fi

# ---------- Pass 4: --fix executes the plan ----------

if [[ "$FIX" -eq 1 && "$red" -gt 0 ]]; then
  if [[ "$YES" -ne 1 ]]; then
    echo
    read -r -p "Proceed with auto-install? [y/N] " ans
    case "$ans" in
      y|Y|yes|YES) : ;;
      *) echo "aborted"; exit 1 ;;
    esac
  fi

  if [[ ${#actions[@]} -eq 0 ]]; then
    echo
    echo "doctor: nothing the auto-installer can fix. The remaining red items require manual action (see [fail] lines above)."
    exit 1
  fi

  echo
  echo "Executing plan..."
  for action in "${actions[@]}"; do
    case "$action" in
      install_sqlplus)
        echo "==> Installing SQL*Plus"
        if [[ -x "$SKILL_DIR/scripts/ensure_sqlplus.sh" ]]; then
          "$SKILL_DIR/scripts/ensure_sqlplus.sh" || { echo "ensure_sqlplus.sh failed" >&2; exit 1; }
        else
          echo "ensure_sqlplus.sh missing or not executable" >&2; exit 1
        fi
        ;;
      install_mkstore)
        echo "==> Installing mkstore launcher"
        if [[ -x "$SKILL_DIR/scripts/ensure_sqlplus.sh" ]]; then
          "$SKILL_DIR/scripts/ensure_sqlplus.sh" --wallet-tools || { echo "wallet-tools install failed" >&2; exit 1; }
        else
          echo "ensure_sqlplus.sh missing or not executable" >&2; exit 1
        fi
        ;;
      setup_wallet)
        if [[ "$alias_blocked" -eq 1 ]]; then
          echo "==> Skipping wallet setup: no alias provided. Re-run with --alias <name>." >&2
          exit 1
        fi
        echo "==> Running wallet setup (your local terminal will prompt for credentials)"
        args=(--alias "${ALIAS#/@}")
        [[ -n "$TNS_DESCRIPTOR" ]] && args+=(--tns-descriptor "$TNS_DESCRIPTOR")
        if [[ -x "$SKILL_DIR/scripts/setup_oracle_wallet.sh" ]]; then
          "$SKILL_DIR/scripts/setup_oracle_wallet.sh" "${args[@]}" || { echo "wallet setup failed" >&2; exit 1; }
        else
          echo "setup_oracle_wallet.sh missing or not executable" >&2; exit 1
        fi
        ;;
    esac
  done

  echo
  echo "Plan complete."
  echo "Re-run db-work-doctor.sh in a NEW shell to verify (PATH and env vars set by installers may not be visible in this shell)."
  if [[ -n "$ALIAS" ]]; then
    echo "Reminder: export DB_WORK_DEV_CONNECT='$ALIAS' in your shell rc if not already set."
  fi
  exit 0
fi

# ---------- Final status (no --plan, no --fix, or --fix with red=0) ----------

echo
if [[ "$red" -eq 0 ]]; then
  echo "doctor: all green"
  exit 0
else
  echo "doctor: $red item(s) need attention."
  echo "  --plan        show what auto-install would do"
  echo "  --fix --yes   apply the plan (after agent has shown it to the user)"
  if [[ ${#plugin_install_cmds[@]} -gt 0 ]]; then
    echo "  Note: plugin/skill installs are NOT auto-fixable — see the [fail]/[warn] hint lines above."
  fi
  exit 1
fi
