#!/usr/bin/env bash
set -euo pipefail

author=""
user_suffix=""
default_team=""
dev_connect=""
grant_execute_to="${DB_WORK_GRANT_EXECUTE_TO:-ye_dev}"
session_base="${DB_WORK_SESSION_BASE:-${TMPDIR:-/tmp}/db-work-${USER:-user}}"

usage() {
  cat <<'USAGE'
Usage: start_session.sh [options]

Creates a temporary db-work session directory and writes a non-secret
.db-work.yml there. The project repo is not modified.

Options:
  --author NAME
  --user-suffix SUFFIX
  --default-team TEAM
  --dev-connect /@DEV_ALIAS
  --grant-execute-to USER
  --session-base DIR      Defaults to $DB_WORK_SESSION_BASE or /tmp/db-work-$USER.

After creation, use the printed DB_WORK_SESSION_DIR and DB_WORK_CONFIG exports
for db-work commands in this shell/session.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --author)
      author="${2:?--author requires a value}"
      shift 2
      ;;
    --user-suffix)
      user_suffix="${2:?--user-suffix requires a value}"
      shift 2
      ;;
    --default-team)
      default_team="${2:?--default-team requires a value}"
      shift 2
      ;;
    --dev-connect)
      dev_connect="${2:?--dev-connect requires a value}"
      shift 2
      ;;
    --grant-execute-to)
      grant_execute_to="${2:?--grant-execute-to requires a value}"
      shift 2
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

mkdir -p "$session_base"
chmod 700 "$session_base" 2>/dev/null || true

session_dir="$(mktemp -d "$session_base/session-$(date +%Y%m%d%H%M%S).XXXXXX")"
tmp_dir="$session_dir/tmp"
mkdir -p "$tmp_dir"
chmod 700 "$session_dir" "$tmp_dir" 2>/dev/null || true
touch "$session_dir/.db-work-session"

config_file="$session_dir/.db-work.yml"
{
  echo "# Temporary db-work config. Do not put secrets here."
  if [[ -n "$author" ]]; then
    printf 'author: %s\n' "$author"
  else
    echo "# author: Your Name"
  fi
  if [[ -n "$user_suffix" ]]; then
    printf 'user_suffix: %s\n' "$user_suffix"
  else
    echo "# user_suffix: ABC"
  fi
  if [[ -n "$default_team" ]]; then
    printf 'default_team: %s\n' "$default_team"
  else
    echo "# default_team: visual-analytics"
  fi
  if [[ -n "$dev_connect" ]]; then
    printf 'dev_connect: %s\n' "$dev_connect"
  else
    echo "# dev_connect: /@ORACODE_DEV"
  fi
  if [[ -n "$grant_execute_to" ]]; then
    printf 'grant_execute_to: %s\n' "$grant_execute_to"
  else
    echo "# grant_execute_to: ye_dev"
  fi
  cat <<'YAML'

teams:
  visual-analytics:
    changelog: visualanalytics_changelog.xml
    aliases:
      - visual analytics
      - va
      - visual_analytics
      - visualanalytics_changelog.xml
  dataops:
    changelog: dataops_changelog.xml
    aliases:
      - data ops
      - dataops
YAML
} > "$config_file"
chmod 600 "$config_file"

ln -sfn "$session_dir" "$session_base/current"

env_file="$session_dir/session.env"
{
  printf 'export DB_WORK_SESSION_DIR=%q\n' "$session_dir"
  printf 'export DB_WORK_CONFIG=%q\n' "$config_file"
  printf 'export DB_WORK_TEMP_DIR=%q\n' "$tmp_dir"
} > "$env_file"
chmod 600 "$env_file"

cat <<EOF
db-work session created:
  $session_dir

Temporary config:
  $config_file

For this shell/session:
  source "$env_file"

Or pass the config explicitly:
  DB_WORK_CONFIG="$config_file"
EOF
