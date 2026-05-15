#!/usr/bin/env bash
# Sync one canonical skill between this repo and local agent install dirs.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AI_SKILLS_REPO:-$(cd "$SCRIPT_DIR/.." && pwd)}"

usage() {
  cat >&2 <<USAGE
Usage:
  $0 push <skill-name>               # canonical repo copy -> Claude + Codex install dirs
  $0 pull <skill-name> claude|codex   # named install dir -> canonical repo copy + other install dir
USAGE
  exit 1
}

validate_skill_name() {
  local skill_name="$1"

  case "$skill_name" in
    ""|.*|*/*)
      printf 'invalid skill name: %s\n' "$skill_name" >&2
      exit 2
      ;;
  esac
}

rsync_clone() {
  local src="$1"
  local dst="$2"

  mkdir -p "$dst"
  rsync -a --delete --exclude=".gitkeep" "$src/" "$dst/"
  printf 'synced: %s -> %s\n' "$src" "$dst"
}

sync_from_to_both() {
  local src="$1"
  local first_dst="$2"
  local second_dst="$3"

  [ -d "$src" ] || { printf 'missing source: %s\n' "$src" >&2; exit 2; }
  rsync_clone "$src" "$first_dst"
  rsync_clone "$src" "$second_dst"
}

cmd="${1:-}"
skill_name="${2:-}"

[ -n "$cmd" ] || usage
[ -n "$skill_name" ] || usage
validate_skill_name "$skill_name"

canonical="$REPO_ROOT/skills/$skill_name"
install_claude="$HOME/.claude/skills/$skill_name"
install_codex="$HOME/.codex/skills/$skill_name"

case "$cmd" in
  push)
    [ -d "$canonical" ] || { printf 'missing canonical skill: %s\n' "$canonical" >&2; exit 2; }
    sync_from_to_both "$canonical" "$install_claude" "$install_codex"
    ;;
  pull)
    agent="${3:-}"
    case "$agent" in
      claude)
        sync_from_to_both "$install_claude" "$canonical" "$install_codex"
        ;;
      codex)
        sync_from_to_both "$install_codex" "$canonical" "$install_claude"
        ;;
      *) usage ;;
    esac
    printf 'remember: review, commit, and push the repo changes\n'
    ;;
  *) usage ;;
esac
