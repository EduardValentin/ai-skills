#!/usr/bin/env bash
set -euo pipefail

connect="${DB_WORK_DEV_CONNECT:-}"
script=""
repo_root="$(pwd)"

session_config_path() {
  local base current config

  if [[ -n "${DB_WORK_CONFIG:-}" && -f "${DB_WORK_CONFIG:-}" ]]; then
    printf '%s\n' "$DB_WORK_CONFIG"
    return 0
  fi

  if [[ -n "${DB_WORK_SESSION_DIR:-}" && -f "$DB_WORK_SESSION_DIR/.db-work.yml" ]]; then
    printf '%s\n' "$DB_WORK_SESSION_DIR/.db-work.yml"
    return 0
  fi

  base="${DB_WORK_SESSION_BASE:-${TMPDIR:-/tmp}/db-work-${USER:-user}}"
  current="$base/current"
  if [[ -L "$current" ]]; then
    config="$(readlink "$current")/.db-work.yml"
    if [[ -f "$config" ]]; then
      printf '%s\n' "$config"
      return 0
    fi
  fi

  if [[ -f .db-work.yml ]]; then
    printf '%s\n' ".db-work.yml"
    return 0
  fi

  return 1
}

tool_path() {
  local tool="$1"
  local candidate
  local search_dirs=()

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
Usage: run_sqlplus_dev.sh --script path/to/script.sql [--connect /@DEVDB_ALIAS] [--repo-root /path/to/oracode]

Runs a SQLPlus script against a DEV alias. Credentials must come from an Oracle
wallet or another local SQLPlus-safe mechanism. Do not pass username/password.

Environment:
  DB_WORK_DEV_CONNECT=/@DEVDB_ALIAS
  DB_WORK_AUTO_INSTALL_SQLPLUS=0
                              Disable automatic SQLPlus installation when missing.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --connect)
      connect="${2:?--connect requires a value}"
      shift 2
      ;;
    --script)
      script="${2:?--script requires a path}"
      shift 2
      ;;
    --repo-root)
      repo_root="${2:?--repo-root requires a path}"
      shift 2
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

cd "$repo_root"

if [[ -z "$connect" ]]; then
  config_path="$(session_config_path || true)"
  if [[ -n "${config_path:-}" ]]; then
    connect="$(awk -F': *' '/^dev_connect:/ {print $2; exit}' "$config_path" | tr -d "'\"")"
  fi
fi

if [[ -z "$script" ]]; then
  echo "Missing --script." >&2
  exit 2
fi

if [[ ! -f "$script" ]]; then
  echo "SQL script not found: $script" >&2
  exit 2
fi

if [[ -z "$connect" ]]; then
  echo "Missing DEV connect alias. Set DB_WORK_DEV_CONNECT, temp .db-work.yml dev_connect, or pass --connect." >&2
  exit 2
fi

if [[ "$connect" != /@* ]]; then
  echo "Refusing to run: connect value must use wallet-style /@ALIAS, not username/password." >&2
  exit 2
fi

sqlplus_bin="$(tool_path sqlplus || true)"
if [[ -z "$sqlplus_bin" ]]; then
  skill_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  if [[ -x "$skill_dir/scripts/ensure_sqlplus.sh" ]]; then
    "$skill_dir/scripts/ensure_sqlplus.sh"
  else
    echo "sqlplus was not found in PATH, and ensure_sqlplus.sh is unavailable." >&2
    exit 127
  fi
fi

sqlplus_bin="$(tool_path sqlplus || true)"
if [[ -z "$sqlplus_bin" ]]; then
  echo "sqlplus was not found in PATH after install check." >&2
  exit 127
fi

echo "Running SQLPlus against configured DEV alias."
"$sqlplus_bin" -L -S "$connect" "@$script"
