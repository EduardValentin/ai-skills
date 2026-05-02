#!/usr/bin/env bash
set -euo pipefail

alias_name=""
tns_descriptor=""
wallet_dir="${DB_WORK_WALLET_DIR:-$HOME/.oracle/wallets/oracode-dev}"
tns_admin="${TNS_ADMIN:-$HOME/.oracle/network/admin}"
db_username=""
run_test=1

tool_path() {
  local tool="$1"
  local candidate override
  local search_dirs=()

  case "$tool" in
    sqlplus)
      override="${DB_WORK_SQLPLUS_BIN:-}"
      ;;
    mkstore)
      override="${DB_WORK_MKSTORE_BIN:-}"
      ;;
    *)
      override=""
      ;;
  esac

  if [[ -n "$override" ]]; then
    if [[ -x "$override" ]]; then
      printf '%s\n' "$override"
      return 0
    fi
    echo "$tool override is not executable: $override" >&2
    return 1
  fi

  if command -v "$tool" >/dev/null 2>&1; then
    command -v "$tool"
    return 0
  fi

  if [[ -n "${DB_WORK_ORACLE_HOME:-}" ]]; then
    search_dirs+=("$DB_WORK_ORACLE_HOME" "$DB_WORK_ORACLE_HOME/bin")
  fi
  if [[ -n "${ORACLE_HOME:-}" ]]; then
    search_dirs+=("$ORACLE_HOME" "$ORACLE_HOME/bin")
  fi

  search_dirs+=("$HOME/.local/bin" "$HOME/.oracle/mkstore/bin")

  for candidate in \
    "$HOME"/Downloads/instantclient_* \
    /opt/oracle/instantclient_* \
    /usr/local/instantclient_* \
    /usr/local/lib/instantclient_* \
    /opt/homebrew/lib/instantclient_*; do
    [[ -d "$candidate" ]] || continue
    search_dirs+=("$candidate" "$candidate/bin")
  done

  if ((${#search_dirs[@]} > 0)); then
    for candidate in "${search_dirs[@]}"; do
      [[ -n "$candidate" && -x "$candidate/$tool" ]] || continue
      printf '%s\n' "$candidate/$tool"
      return 0
    done
  fi

  return 1
}

usage() {
  cat <<'USAGE'
Usage: setup_oracle_wallet.sh --alias DEVDB_ALIAS [options]

Creates the local Oracle network/admin folder, optional tnsnames.ora entry,
sqlnet.ora wallet configuration, Oracle auto-login wallet, and wallet
credential entry for /@DEVDB_ALIAS.

Options:
  --alias NAME              Required TNS alias, for example ORACODE_DEV.
  --tns-descriptor TEXT     Optional non-secret connect descriptor for NAME.
                            If NAME is already in tnsnames.ora, omit this.
  --wallet-dir PATH         Wallet directory. Defaults to
                            $DB_WORK_WALLET_DIR or ~/.oracle/wallets/oracode-dev.
  --tns-admin PATH          Oracle network config directory. Defaults to
                            $TNS_ADMIN or ~/.oracle/network/admin.
  --no-test                 Skip final sqlplus -L /@NAME validation.

Secrets are never accepted as arguments. Oracle prompts for wallet/database
passwords locally in the terminal when needed.
USAGE
}

mkstore_is_usable() {
  local mkstore_bin="$1"
  "$mkstore_bin" -help 2>&1 | grep -q -- '-createCredential'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --alias)
      alias_name="${2:?--alias requires a value}"
      shift 2
      ;;
    --tns-descriptor)
      tns_descriptor="${2:?--tns-descriptor requires a value}"
      shift 2
      ;;
    --wallet-dir)
      wallet_dir="${2:?--wallet-dir requires a value}"
      shift 2
      ;;
    --tns-admin)
      tns_admin="${2:?--tns-admin requires a value}"
      shift 2
      ;;
    --no-test)
      run_test=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$alias_name" ]]; then
  echo "Missing --alias." >&2
  usage >&2
  exit 2
fi

if [[ "$alias_name" != *[Dd][Ee][Vv]* ]]; then
  echo "Refusing wallet setup: alias does not look like DEV: $alias_name" >&2
  echo "Use a DEV-specific alias such as ORACODE_DEV." >&2
  exit 2
fi

skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if ! tool_path mkstore >/dev/null 2>&1 || { [[ "$run_test" == "1" ]] && ! tool_path sqlplus >/dev/null 2>&1; }; then
  if [[ -x "$skill_dir/scripts/ensure_sqlplus.sh" ]]; then
    "$skill_dir/scripts/ensure_sqlplus.sh" --wallet-tools
  fi
fi

mkstore_bin="$(tool_path mkstore || true)"
if [[ -z "$mkstore_bin" ]]; then
  echo "mkstore was not found after the install check." >&2
  exit 127
fi

if ! mkstore_is_usable "$mkstore_bin"; then
  echo "Found mkstore, but it does not support -createCredential: $mkstore_bin" >&2
  exit 127
fi

sqlplus_bin=""
if [[ "$run_test" == "1" ]]; then
  sqlplus_bin="$(tool_path sqlplus || true)"
  if [[ -z "$sqlplus_bin" ]]; then
    echo "sqlplus was not found after the install check. Install SQLPlus or pass --no-test." >&2
    exit 127
  fi
fi

mkdir -p "$tns_admin" "$wallet_dir"
chmod 700 "$HOME/.oracle" "$HOME/.oracle/network" "$tns_admin" "$HOME/.oracle/wallets" "$wallet_dir" 2>/dev/null || true

wallet_abs="$(cd "$wallet_dir" && pwd -P)"
tns_admin_abs="$(cd "$tns_admin" && pwd -P)"
tnsnames_file="$tns_admin_abs/tnsnames.ora"
sqlnet_file="$tns_admin_abs/sqlnet.ora"

touch "$tnsnames_file" "$sqlnet_file"
chmod 600 "$tnsnames_file" "$sqlnet_file" 2>/dev/null || true

if ! grep -Eiq "^[[:space:]]*${alias_name}[[:space:]]*=" "$tnsnames_file"; then
  if [[ -z "$tns_descriptor" ]]; then
    cat >&2 <<EOF
TNS alias '$alias_name' was not found in:
  $tnsnames_file

Provide a non-secret descriptor with --tns-descriptor, or add the alias to
tnsnames.ora and re-run this script.
EOF
    exit 2
  fi

  {
    printf '\n%s =\n' "$alias_name"
    printf '%s\n' "$tns_descriptor"
  } >> "$tnsnames_file"
  echo "Added $alias_name to $tnsnames_file"
else
  echo "Found $alias_name in $tnsnames_file"
fi

tmp_sqlnet="$(mktemp)"
cleanup_tmp_sqlnet() {
  if [[ -n "${tmp_sqlnet:-}" && -f "$tmp_sqlnet" ]]; then
    rm -f "$tmp_sqlnet"
  fi
}
trap cleanup_tmp_sqlnet EXIT
awk '
  /^# BEGIN DB_WORK_SEPS$/ { skip = 1; next }
  /^# END DB_WORK_SEPS$/ { skip = 0; next }
  /^# BEGIN DB_WORK_WALLET$/ { skip = 1; next }
  /^# END DB_WORK_WALLET$/ { skip = 0; next }
  skip != 1 { print }
' "$sqlnet_file" > "$tmp_sqlnet"

cat >> "$tmp_sqlnet" <<EOF

# BEGIN DB_WORK_WALLET
WALLET_LOCATION =
  (SOURCE =
    (METHOD = FILE)
    (METHOD_DATA =
      (DIRECTORY = $wallet_abs)
    )
  )

SQLNET.WALLET_OVERRIDE = TRUE
NAMES.DIRECTORY_PATH = (TNSNAMES, EZCONNECT)
# END DB_WORK_WALLET
EOF

mv "$tmp_sqlnet" "$sqlnet_file"
tmp_sqlnet=""
chmod 600 "$sqlnet_file" 2>/dev/null || true
echo "Updated $sqlnet_file"

if [[ ! -f "$wallet_abs/cwallet.sso" && ! -f "$wallet_abs/ewallet.p12" ]]; then
  echo "Creating Oracle auto-login wallet in $wallet_abs"
  echo "Oracle may prompt for a wallet password locally in this terminal."
  "$mkstore_bin" -wrl "$wallet_abs" -create
else
  echo "Wallet already exists in $wallet_abs"
fi

printf 'Database username for %s: ' "$alias_name" >&2
IFS= read -r -s db_username
printf '\n' >&2

if [[ -z "$db_username" ]]; then
  echo "Database username cannot be empty." >&2
  exit 2
fi

echo "Creating wallet credential for $alias_name."
echo "Oracle will prompt locally for wallet/database passwords as needed."
"$mkstore_bin" -wrl "$wallet_abs" -createCredential "$alias_name" "$db_username"

if [[ "$run_test" == "1" ]]; then
  echo "Testing /@$alias_name with SQLPlus..."
  "$sqlplus_bin" -L -S "/@$alias_name" <<'SQL'
set heading off feedback off pagesize 0
select 'DB_WORK_WALLET_OK ' || sys_context('USERENV', 'CURRENT_SCHEMA') from dual;
exit
SQL
fi

cat <<EOF
Wallet setup complete.

Use this non-secret value for db-work:
  DB_WORK_DEV_CONNECT=/@$alias_name

If needed, add this to your shell profile:
  export TNS_ADMIN="$tns_admin_abs"
EOF
