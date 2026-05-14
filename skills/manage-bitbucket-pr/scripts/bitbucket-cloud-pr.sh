#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://api.bitbucket.org/2.0"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage:
  bitbucket-cloud-pr.sh [--dry-run] pr-details <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] read-comments <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] post-comment <workspace> <repo_slug> <pull_request_id> <comment text>
  bitbucket-cloud-pr.sh [--dry-run] merge <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] merge-status <workspace> <repo_slug> <pull_request_id> <task_id>

Auth:
  Bearer token: set BITBUCKET_TOKEN
  Basic auth: set BITBUCKET_EMAIL and BITBUCKET_API_TOKEN
USAGE
}

die() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

json_string() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  value=${value//$'\t'/\\t}
  printf '"%s"' "$value"
}

require_args() {
  local expected=$1
  local actual=$2
  [[ "$actual" -ge "$expected" ]] || {
    usage >&2
    exit 2
  }
}

request() {
  local method=$1
  local url=$2
  local body=${3:-}

  if [[ "$DRY_RUN" == "1" ]]; then
    printf 'METHOD=%s\n' "$method"
    printf 'URL=%s\n' "$url"
    [[ -z "$body" ]] || printf 'BODY=%s\n' "$body"
    return 0
  fi

  local curl_args=(
    --fail
    --silent
    --show-error
    --location
    --request "$method"
    --header "Accept: application/json"
  )

  if [[ -n "${BITBUCKET_TOKEN:-}" ]]; then
    curl_args+=(--header "Authorization: Bearer ${BITBUCKET_TOKEN}")
  elif [[ -n "${BITBUCKET_EMAIL:-}" && -n "${BITBUCKET_API_TOKEN:-}" ]]; then
    curl_args+=(--user "${BITBUCKET_EMAIL}:${BITBUCKET_API_TOKEN}")
  else
    die "Set BITBUCKET_TOKEN or BITBUCKET_EMAIL + BITBUCKET_API_TOKEN"
  fi

  if [[ -n "$body" ]]; then
    curl_args+=(--header "Content-Type: application/json" --data "$body")
  fi

  curl "${curl_args[@]}" "$url"
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
    request GET "$BASE_URL/repositories/$1/$2/pullrequests/$3"
    ;;
  read-comments)
    require_args 3 "$#"
    request GET "$BASE_URL/repositories/$1/$2/pullrequests/$3/comments"
    ;;
  post-comment)
    require_args 4 "$#"
    workspace=$1
    repo_slug=$2
    pull_request_id=$3
    shift 3
    comment=$*
    [[ -n "$comment" ]] || die "Comment text is required"
    body="{\"content\":{\"raw\":$(json_string "$comment")}}"
    request POST "$BASE_URL/repositories/$workspace/$repo_slug/pullrequests/$pull_request_id/comments" "$body"
    ;;
  merge)
    require_args 3 "$#"
    request POST "$BASE_URL/repositories/$1/$2/pullrequests/$3/merge"
    ;;
  merge-status)
    require_args 4 "$#"
    request GET "$BASE_URL/repositories/$1/$2/pullrequests/$3/merge/task-status/$4"
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
