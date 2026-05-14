#!/usr/bin/env bash
# Mirror this canonical skill to both agent install dirs.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${AI_SKILLS_REPO:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
SKILL_NAME="frontend-pr-test"

CANONICAL="$REPO_ROOT/skills/$SKILL_NAME"
INSTALL_CLAUDE="$HOME/.claude/skills/$SKILL_NAME"
INSTALL_CODEX="$HOME/.codex/skills/$SKILL_NAME"

usage() {
  printf 'Usage:\n  %s push\n  %s pull claude|codex\n' "$0" "$0" >&2
  exit 1
}

rsync_clone() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  rsync -a --delete --exclude=".gitkeep" "$src/" "$dst/"
  printf 'synced: %s -> %s\n' "$src" "$dst"
}

cmd="${1:-}"
case "$cmd" in
  push)
    [ -d "$CANONICAL" ] || { printf 'missing: %s\n' "$CANONICAL" >&2; exit 2; }
    rsync_clone "$CANONICAL" "$INSTALL_CLAUDE"
    rsync_clone "$CANONICAL" "$INSTALL_CODEX"
    ;;
  pull)
    agent="${2:-}"
    case "$agent" in
      claude)
        [ -d "$INSTALL_CLAUDE" ] || { printf 'missing: %s\n' "$INSTALL_CLAUDE" >&2; exit 2; }
        rsync_clone "$INSTALL_CLAUDE" "$CANONICAL"
        rsync_clone "$INSTALL_CLAUDE" "$INSTALL_CODEX"
        ;;
      codex)
        [ -d "$INSTALL_CODEX" ] || { printf 'missing: %s\n' "$INSTALL_CODEX" >&2; exit 2; }
        rsync_clone "$INSTALL_CODEX" "$CANONICAL"
        rsync_clone "$INSTALL_CODEX" "$INSTALL_CLAUDE"
        ;;
      *) usage ;;
    esac
    ;;
  *) usage ;;
esac
