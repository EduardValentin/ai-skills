#!/usr/bin/env bash
set -euo pipefail

session_base="${DB_WORK_SESSION_BASE:-${TMPDIR:-/tmp}/db-work-${USER:-user}}"
session_dir="${DB_WORK_SESSION_DIR:-}"
clean_all=0
targets=()

usage() {
  cat <<'USAGE'
Usage: cleanup_session.sh [--session-dir DIR] [--all] [--session-base DIR]

Removes db-work temporary session directories. A directory is removed only when
it contains the .db-work-session marker created by start_session.sh.

Options:
  --session-dir DIR       Cleanup this session.
  --all                   Cleanup all marked sessions under the session base.
  --session-base DIR      Defaults to $DB_WORK_SESSION_BASE or /tmp/db-work-$USER.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --session-dir)
      session_dir="${2:?--session-dir requires a value}"
      shift 2
      ;;
    --all)
      clean_all=1
      shift
      ;;
    --session-base)
      session_base="${2:?--session-base requires a value}"
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

if [[ "$clean_all" == "1" ]]; then
  if [[ -d "$session_base" ]]; then
    while IFS= read -r dir; do
      targets+=("$dir")
    done < <(find "$session_base" -maxdepth 1 -type d -name 'session-*' -print)
  fi
else
  if [[ -z "$session_dir" && -L "$session_base/current" ]]; then
    session_dir="$(readlink "$session_base/current")"
  fi
  if [[ -n "$session_dir" ]]; then
    targets+=("$session_dir")
  fi
fi

if ((${#targets[@]} == 0)); then
  echo "No db-work session directories found to clean."
  exit 0
fi

removed=0
for target in "${targets[@]}"; do
  if [[ ! -e "$target/.db-work-session" ]]; then
    echo "Skipping unmarked directory: $target" >&2
    continue
  fi
  rm -rf "$target"
  removed=$((removed + 1))
  echo "Removed db-work session: $target"
done

if [[ -L "$session_base/current" ]]; then
  current_target="$(readlink "$session_base/current")"
  if [[ ! -e "$current_target" ]]; then
    rm -f "$session_base/current"
    echo "Removed stale current session link: $session_base/current"
  fi
fi

if [[ "$removed" == "0" ]]; then
  echo "No marked db-work session directories were removed."
fi
