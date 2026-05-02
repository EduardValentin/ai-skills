#!/usr/bin/env bash
set -euo pipefail

base_ref="master"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      base_ref="${2:?--base requires a ref}"
      shift 2
      ;;
    -h|--help)
      cat <<'USAGE'
Usage: inspect_changes.sh [--base master]

Print Oracode-oriented git context: branch, inferred ticket, changed SQL files,
changed changelogs, and generated DEV sandbox files.
USAGE
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

branch="$(git branch --show-current || true)"
ticket=""
if [[ "$branch" =~ ([A-Z][A-Z0-9]+-[0-9]+) ]]; then
  ticket="${BASH_REMATCH[1]}"
fi

tmp_file="$(mktemp)"
trap 'rm -f "$tmp_file"' EXIT

if git rev-parse --verify "$base_ref" >/dev/null 2>&1; then
  git diff --name-only "$base_ref"...HEAD >>"$tmp_file" || true
fi
git diff --name-only >>"$tmp_file" || true
git diff --name-only --cached >>"$tmp_file" || true
git ls-files --others --exclude-standard >>"$tmp_file" || true

changed=()
while IFS= read -r file; do
  changed+=("$file")
done < <(sort -u "$tmp_file" | sed '/^$/d')

echo "repo_root: $repo_root"
echo "branch: ${branch:-unknown}"
echo "ticket: ${ticket:-unknown}"
echo "base_ref: $base_ref"
echo

echo "changed_sql_files:"
for file in "${changed[@]}"; do
  if [[ "$file" == *.sql && "$file" != util/*/dev_sandbox/* ]]; then
    echo "  - $file"
  fi
done
echo

echo "changed_changelogs:"
for file in "${changed[@]}"; do
  if [[ "$file" == *_changelog.xml || "$file" == root_changelog.xml ]]; then
    echo "  - $file"
  fi
done
echo

echo "generated_dev_sandbox_files:"
for file in "${changed[@]}"; do
  if [[ "$file" == util/*/dev_sandbox/* ]]; then
    echo "  - $file"
  fi
done
