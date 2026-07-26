#!/usr/bin/env bash
set -euo pipefail

API_ORIGIN="https://api.bitbucket.org"
DRY_RUN=0
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PYTHON_HELPER="$SCRIPT_DIR/bitbucket-cloud-api.py"

usage() {
  cat <<'USAGE'
Usage:
  bitbucket-cloud-pr.sh [--dry-run] pr-details <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] find-prs-for-branch <workspace> <repo_slug> <branch_name> [state]
  bitbucket-cloud-pr.sh [--dry-run] read-comments <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] post-comment <workspace> <repo_slug> <pull_request_id>  # text from stdin
  bitbucket-cloud-pr.sh [--dry-run] update-description <workspace> <repo_slug> <pull_request_id>  # text from stdin
  bitbucket-cloud-pr.sh [--dry-run] merge <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] merge-status <workspace> <repo_slug> <pull_request_id> <task_id>

Auth:
  OAuth 2 access token: set BITBUCKET_TOKEN
  API-token Basic auth: set BITBUCKET_EMAIL to the Atlassian account email
    and set BITBUCKET_API_TOKEN to its scoped API token
USAGE
}

die() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

python_helper() {
  command -v python3 >/dev/null 2>&1 || die "This command requires Python 3"
  [[ -r "$PYTHON_HELPER" ]] || die "Bundled Python helper is unavailable"
  python3 -I -B -S "$PYTHON_HELPER" "$@"
}

require_args() {
  local expected=$1
  local actual=$2
  [[ "$actual" -ge "$expected" ]] || {
    usage >&2
    exit 2
  }
}

require_exact_args() {
  local expected=$1
  local actual=$2
  [[ "$actual" -eq "$expected" ]] || {
    usage >&2
    exit 2
  }
}

repository_path() {
  local workspace
  local repo_slug
  workspace=$(printf '%s' "$1" | python_helper encode-slug workspace)
  repo_slug=$(printf '%s' "$2" | python_helper encode-slug repository)
  printf '/2.0/repositories/%s/%s' "$workspace" "$repo_slug"
}

pull_request_path() {
  local repo_path
  local pull_request_id
  repo_path=$(repository_path "$1" "$2")
  pull_request_id=$(
    printf '%s' "$3" | python_helper positive-integer "pull request ID"
  )
  printf '%s/pullrequests/%s' "$repo_path" "$pull_request_id"
}

request() {
  local method=$1
  local url=$2
  local expected_path=$3
  local body=${4-}

  python_helper validate-url "$url" "$expected_path"
  if [[ "$DRY_RUN" == "1" ]]; then
    printf 'METHOD=%s\n' "$method"
    printf 'URL=%s\n' "$url"
    [[ -z "$body" ]] || printf 'BODY=%s\n' "$body"
    return 0
  fi

  printf '%s' "$body" | python_helper request "$method" "$url" "$expected_path"
}

read_all_comments() {
  local expected_path=$1
  local url="$API_ORIGIN$expected_path"
  local page
  local next_url
  local seen_url
  local page_count=0
  local pages=()
  local seen_urls=()

  while true; do
    if [[ "$page_count" -gt 0 ]]; then
      for seen_url in "${seen_urls[@]}"; do
        [[ "$url" != "$seen_url" ]] || die "Bitbucket comments pagination repeated a URL"
      done
    fi
    seen_urls+=("$url")
    page_count=$((page_count + 1))
    [[ "$page_count" -le 1000 ]] || die "Bitbucket comments pagination exceeded 1000 pages"

    page=$(request GET "$url" "$expected_path")
    pages+=("$page")
    next_url=$(
      printf '%s' "$page" | python_helper comments-next-url "$expected_path"
    )
    [[ -n "$next_url" ]] || break
    url=$next_url
  done

  printf '%s\0' "${pages[@]}" | python_helper combine-comment-pages
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  shift
fi

command=${1:-}
[[ -n "$command" ]] || {
  usage >&2
  exit 2
}
shift

case "$command" in
  pr-details)
    require_args 3 "$#"
    path=$(pull_request_path "$1" "$2" "$3")
    request GET "$API_ORIGIN$path" "$path"
    ;;
  find-prs-for-branch)
    require_args 3 "$#"
    path="$(repository_path "$1" "$2")/pullrequests"
    query=$(
      printf '%s\0%s' "$3" "${4:-OPEN}" | python_helper build-query
    )
    request GET "$API_ORIGIN$path?$query" "$path"
    ;;
  read-comments)
    require_args 3 "$#"
    path="$(pull_request_path "$1" "$2" "$3")/comments"
    if [[ "$DRY_RUN" == "1" ]]; then
      request GET "$API_ORIGIN$path" "$path"
    else
      read_all_comments "$path"
    fi
    ;;
  post-comment)
    require_exact_args 3 "$#"
    workspace=$1
    repo_slug=$2
    pull_request_id=$3
    path="$(pull_request_path "$workspace" "$repo_slug" "$pull_request_id")/comments"
    body=$(python_helper json-body comment)
    request POST "$API_ORIGIN$path" "$path" "$body"
    ;;
  update-description)
    require_exact_args 3 "$#"
    workspace=$1
    repo_slug=$2
    pull_request_id=$3
    path=$(pull_request_path "$workspace" "$repo_slug" "$pull_request_id")
    body=$(python_helper json-body description)
    request PUT "$API_ORIGIN$path" "$path" "$body"
    ;;
  merge)
    require_args 3 "$#"
    path="$(pull_request_path "$1" "$2" "$3")/merge"
    request POST "$API_ORIGIN$path" "$path"
    ;;
  merge-status)
    require_exact_args 4 "$#"
    task_id=$(printf '%s' "$4" | python_helper encode-task-identifier)
    path="$(pull_request_path "$1" "$2" "$3")/merge/task-status/$task_id"
    request GET "$API_ORIGIN$path" "$path"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
