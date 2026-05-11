#!/usr/bin/env bash
# _sync.sh — mirror skill between repo and install dirs.
#
# Usage:
#   _sync.sh push                 # repo → both install dirs (~/.claude, ~/.codex)
#   _sync.sh pull claude          # ~/.claude install dir → repo + ~/.codex install dir
#   _sync.sh pull codex           # ~/.codex install dir → repo + ~/.claude install dir
#
# Resolves repo root via $AI_SKILLS_REPO env var, fallback to a hardcoded path.

set -euo pipefail

REPO_ROOT="${AI_SKILLS_REPO:-/Users/trocaneduard/Documents/Personal/ai-skills}"
SKILL_NAME="declaratia-unica-romania"

REPO_CLAUDE="$REPO_ROOT/claude/skills/$SKILL_NAME"
REPO_CODEX="$REPO_ROOT/codex/skills/$SKILL_NAME"
INSTALL_CLAUDE="$HOME/.claude/skills/$SKILL_NAME"
INSTALL_CODEX="$HOME/.codex/skills/$SKILL_NAME"

usage() {
  cat >&2 <<USAGE
Usage:
  $0 push                 # repo → both install dirs
  $0 pull claude|codex    # named install dir → repo + other install dir
USAGE
  exit 1
}

rsync_clone() {
  local src="$1"; local dst="$2"
  mkdir -p "$dst"
  rsync -a --delete --exclude=".gitkeep" "$src/" "$dst/"
  echo "synced: $src → $dst"
}

cmd="${1:-}"
case "$cmd" in
  push)
    [ -d "$REPO_CLAUDE" ] || { echo "missing: $REPO_CLAUDE" >&2; exit 2; }
    [ -d "$REPO_CODEX" ]  || { echo "missing: $REPO_CODEX"  >&2; exit 2; }
    rsync_clone "$REPO_CLAUDE" "$INSTALL_CLAUDE"
    rsync_clone "$REPO_CODEX"  "$INSTALL_CODEX"
    ;;
  pull)
    agent="${2:-}"
    case "$agent" in
      claude)
        [ -d "$INSTALL_CLAUDE" ] || { echo "missing: $INSTALL_CLAUDE" >&2; exit 2; }
        rsync_clone "$INSTALL_CLAUDE" "$REPO_CLAUDE"
        rsync_clone "$INSTALL_CLAUDE" "$REPO_CODEX"
        rsync_clone "$INSTALL_CLAUDE" "$INSTALL_CODEX"
        echo "remember: commit and push the repo changes"
        ;;
      codex)
        [ -d "$INSTALL_CODEX" ] || { echo "missing: $INSTALL_CODEX" >&2; exit 2; }
        rsync_clone "$INSTALL_CODEX" "$REPO_CODEX"
        rsync_clone "$INSTALL_CODEX" "$REPO_CLAUDE"
        rsync_clone "$INSTALL_CODEX" "$INSTALL_CLAUDE"
        echo "remember: commit and push the repo changes"
        ;;
      *) usage ;;
    esac
    ;;
  *) usage ;;
esac
