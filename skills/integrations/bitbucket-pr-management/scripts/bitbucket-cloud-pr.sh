#!/usr/bin/env bash
set -euo pipefail

BASE_URL="https://api.bitbucket.org/2.0"
DRY_RUN=0

usage() {
  cat <<'USAGE'
Usage:
  bitbucket-cloud-pr.sh [--dry-run] pr-details <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] find-prs-for-branch <workspace> <repo_slug> <branch_name> [state]
  bitbucket-cloud-pr.sh [--dry-run] read-comments <workspace> <repo_slug> <pull_request_id>
  bitbucket-cloud-pr.sh [--dry-run] post-comment <workspace> <repo_slug> <pull_request_id> <comment text>
  bitbucket-cloud-pr.sh [--dry-run] update-description <workspace> <repo_slug> <pull_request_id> <description text>
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

json_string() {
  local value=$1
  value=${value//\\/\\\\}
  value=${value//\"/\\\"}
  value=${value//$'\n'/\\n}
  value=${value//$'\r'/\\r}
  value=${value//$'\t'/\\t}
  printf '"%s"' "$value"
}

url_encode() {
  local value=$1
  local encoded=""
  local char

  for ((i = 0; i < ${#value}; i++)); do
    char=${value:i:1}
    case "$char" in
      [a-zA-Z0-9.~_-]) encoded+="$char" ;;
      " ") encoded+="+" ;;
      *) printf -v encoded '%s%%%02X' "$encoded" "'$char" ;;
    esac
  done

  printf '%s' "$encoded"
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

  if [[ -n "${BITBUCKET_TOKEN-}" ]]; then
    curl_args+=(--oauth2-bearer "${BITBUCKET_TOKEN}")
  elif [[ -n "${BITBUCKET_EMAIL-}" && -n "${BITBUCKET_API_TOKEN-}" ]]; then
    curl_args+=(--user "${BITBUCKET_EMAIL}:${BITBUCKET_API_TOKEN}")
  else
    die "Set BITBUCKET_TOKEN or BITBUCKET_EMAIL + BITBUCKET_API_TOKEN"
  fi

  if [[ -n "$body" ]]; then
    curl_args+=(--header "Content-Type: application/json" --data "$body")
  fi

  curl "${curl_args[@]}" "$url"
}

comments_next_url() {
  local expected_path=$1

  python3 -c '
import json
import sys
from urllib.parse import urlsplit

expected_path = sys.argv[1]

try:
    page = json.load(sys.stdin)
except (UnicodeDecodeError, json.JSONDecodeError) as error:
    print(f"Error: Invalid JSON in Bitbucket comments response: {error}", file=sys.stderr)
    raise SystemExit(1)

if not isinstance(page, dict) or not isinstance(page.get("values"), list):
    print("Error: Invalid Bitbucket comments page shape", file=sys.stderr)
    raise SystemExit(1)

next_url = page.get("next")
if next_url is None:
    raise SystemExit(0)
if not isinstance(next_url, str) or not next_url:
    print("Error: Invalid next URL in Bitbucket comments response", file=sys.stderr)
    raise SystemExit(1)

try:
    parsed = urlsplit(next_url)
    port = parsed.port
except ValueError:
    print("Error: Refusing untrusted comments pagination URL", file=sys.stderr)
    raise SystemExit(1)

is_trusted = (
    parsed.scheme == "https"
    and parsed.hostname == "api.bitbucket.org"
    and port in (None, 443)
    and parsed.username is None
    and parsed.password is None
    and parsed.path == expected_path
    and not parsed.fragment
)
if not is_trusted:
    print("Error: Refusing untrusted comments pagination URL", file=sys.stderr)
    raise SystemExit(1)

sys.stdout.write(next_url)
' "$expected_path"
}

combine_comment_pages() {
  python3 -c '
import json
import sys

raw_pages = [raw for raw in sys.stdin.buffer.read().split(b"\0") if raw]
if not raw_pages:
    print("Error: Bitbucket returned no comments pages", file=sys.stderr)
    raise SystemExit(1)

pages = []
for raw_page in raw_pages:
    try:
        page = json.loads(raw_page)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"Error: Invalid JSON in Bitbucket comments response: {error}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(page, dict) or not isinstance(page.get("values"), list):
        print("Error: Invalid Bitbucket comments page shape", file=sys.stderr)
        raise SystemExit(1)
    pages.append(page)

combined = dict(pages[0])
combined["values"] = [value for page in pages for value in page["values"]]
combined.pop("next", None)
combined.pop("previous", None)
combined["page"] = 1
combined["pagelen"] = len(combined["values"])
combined.setdefault("size", len(combined["values"]))
json.dump(combined, sys.stdout, separators=(",", ":"))
'
}

read_all_comments() {
  local workspace=$1
  local repo_slug=$2
  local pull_request_id=$3
  local expected_path="/2.0/repositories/$workspace/$repo_slug/pullrequests/$pull_request_id/comments"
  local url="$BASE_URL/repositories/$workspace/$repo_slug/pullrequests/$pull_request_id/comments"
  local page
  local next_url
  local seen_url
  local page_count=0
  local pages=()
  local seen_urls=()

  command -v python3 >/dev/null 2>&1 || die "read-comments requires Python 3"

  while true; do
    if [[ "$page_count" -gt 0 ]]; then
      for seen_url in "${seen_urls[@]}"; do
        [[ "$url" != "$seen_url" ]] || die "Bitbucket comments pagination repeated a URL"
      done
    fi
    seen_urls+=("$url")
    page_count=$((page_count + 1))
    [[ "$page_count" -le 1000 ]] || die "Bitbucket comments pagination exceeded 1000 pages"

    page=$(request GET "$url")
    pages+=("$page")
    next_url=$(printf '%s' "$page" | comments_next_url "$expected_path")
    [[ -n "$next_url" ]] || break
    url=$next_url
  done

  printf '%s\0' "${pages[@]}" | combine_comment_pages
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
  find-prs-for-branch)
    require_args 3 "$#"
    workspace=$1
    repo_slug=$2
    branch_name=$3
    state=${4:-OPEN}
    query=$(url_encode "source.branch.name = \"$branch_name\" AND state = \"$state\"")
    request GET "$BASE_URL/repositories/$workspace/$repo_slug/pullrequests?q=$query"
    ;;
  read-comments)
    require_args 3 "$#"
    if [[ "$DRY_RUN" == "1" ]]; then
      request GET "$BASE_URL/repositories/$1/$2/pullrequests/$3/comments"
    else
      read_all_comments "$1" "$2" "$3"
    fi
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
  update-description)
    require_args 4 "$#"
    workspace=$1
    repo_slug=$2
    pull_request_id=$3
    shift 3
    description=$*
    [[ -n "$description" ]] || die "Description text is required"
    body="{\"description\":$(json_string "$description")}"
    request PUT "$BASE_URL/repositories/$workspace/$repo_slug/pullrequests/$pull_request_id" "$body"
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
