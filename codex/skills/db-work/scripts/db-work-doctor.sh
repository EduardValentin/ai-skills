#!/usr/bin/env bash
# db-work-doctor.sh — single-shot machine readiness check + auto-fix.
#
# Exit codes:
#   0  all green
#   1  at least one red item
#   2  unsupported platform for --fix
#
# Flags:
#   --fix              attempt to auto-install missing components
#   --setup-wallet     run setup_oracle_wallet.sh after baseline tools are present
#   --alias NAME       alias to verify (defaults to DB_WORK_DEV_CONNECT or /@DEVDB_ALIAS)
#   --tns-descriptor S non-secret TNS descriptor for --setup-wallet when alias is new

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FIX=0
SETUP_WALLET=0
ALIAS=""
TNS_DESCRIPTOR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fix)             FIX=1; shift ;;
    --setup-wallet)    SETUP_WALLET=1; shift ;;
    --alias)           ALIAS="$2"; shift 2 ;;
    --tns-descriptor)  TNS_DESCRIPTOR="$2"; shift 2 ;;
    -h|--help)         sed -n '2,16p' "$0" | sed 's/^# //; s/^#//'; exit 0 ;;
    *)                 echo "unknown flag: $1" >&2; exit 64 ;;
  esac
done

red=0
ok()          { printf "[ok]   %s\n" "$*"; }
fix_needed()  { printf "[fix]  %s\n" "$*"; red=$((red+1)); }
fail()        { printf "[fail] %s\n" "$*"; red=$((red+1)); }

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
  if [[ "$FIX" == 1 ]]; then
    if [[ -x "$SKILL_DIR/scripts/ensure_sqlplus.sh" ]]; then
      "$SKILL_DIR/scripts/ensure_sqlplus.sh" || fail "ensure_sqlplus.sh failed"
    else
      fail "ensure_sqlplus.sh missing or not executable"
    fi
  fi
fi

# 3. mkstore (only required for wallet setup)
if command -v mkstore >/dev/null 2>&1 || [[ -x "$HOME/.oracle/mkstore/bin/mkstore" ]]; then
  ok "mkstore available"
else
  fix_needed "mkstore not available (needed only for wallet setup)"
  if [[ "$FIX" == 1 ]]; then
    if [[ -x "$SKILL_DIR/scripts/ensure_sqlplus.sh" ]]; then
      "$SKILL_DIR/scripts/ensure_sqlplus.sh" --wallet-tools || fail "wallet-tools install failed"
    else
      fail "ensure_sqlplus.sh missing or not executable"
    fi
  fi
fi

# 4. DB_WORK_DEV_CONNECT
if [[ -z "$ALIAS" ]]; then
  ALIAS="${DB_WORK_DEV_CONNECT:-}"
fi
if [[ -z "$ALIAS" ]]; then
  fix_needed "DB_WORK_DEV_CONNECT not set; expected /@DEVDB_ALIAS"
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
      fail "alias '$alias_name_check' does not match ^DEV[_-]; set DB_WORK_ALLOW_NON_DEV='$alias_name_check' in your shell to override (per-alias one-shot)"
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
    if [[ "$SETUP_WALLET" == 1 ]]; then
      args=(--alias "$alias_name")
      [[ -n "$TNS_DESCRIPTOR" ]] && args+=(--tns-descriptor "$TNS_DESCRIPTOR")
      if [[ -x "$SKILL_DIR/scripts/setup_oracle_wallet.sh" ]]; then
        "$SKILL_DIR/scripts/setup_oracle_wallet.sh" "${args[@]}" || fail "wallet setup failed"
      else
        fail "setup_oracle_wallet.sh missing or not executable"
      fi
    fi
  fi
fi

# 6. live connect
if [[ -n "$ALIAS" ]] && command -v sqlplus >/dev/null 2>&1; then
  if echo "exit;" | sqlplus -L -S "$ALIAS" >/dev/null 2>&1; then
    ok "sqlplus -L $ALIAS connects without prompt"
  else
    fix_needed "sqlplus -L $ALIAS does not connect"
  fi
fi

echo
if [[ "$red" -eq 0 ]]; then
  echo "doctor: all green"
  exit 0
else
  echo "doctor: $red item(s) need attention. Re-run with --fix to attempt auto-install or --setup-wallet for wallet creation."
  exit 1
fi
