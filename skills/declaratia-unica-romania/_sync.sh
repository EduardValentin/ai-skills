#!/usr/bin/env bash
# _sync.sh — mirror this canonical skill to both agent install dirs.
#
# Repo layout (single canonical copy, per AGENTS.md repo rule 1):
#   <repo>/skills/declaratia-unica-romania/   ← canonical source
#
# Install dirs (mirrored to on every edit, per AGENTS.md repo rule 2):
#   ~/.claude/skills/declaratia-unica-romania/
#   ~/.codex/skills/declaratia-unica-romania/
#
# Usage:
#   _sync.sh push            # canonical → both install dirs
#   _sync.sh pull <agent>    # named install dir → canonical + other install dir
#                            #   <agent> is one of: claude, codex
#                            #   use this after a runtime mutation (e.g.,
#                            #   freshness check rewrote schema files in
#                            #   ~/.<agent>/skills/.../schema/)
#
# Repo root via $AI_SKILLS_REPO env var, fallback to a hardcoded path.

set -euo pipefail

REPO_ROOT="${AI_SKILLS_REPO:-/Users/trocaneduard/Documents/Personal/ai-skills}"
SKILL_NAME="declaratia-unica-romania"

CANONICAL="$REPO_ROOT/skills/$SKILL_NAME"
INSTALL_CLAUDE="$HOME/.claude/skills/$SKILL_NAME"
INSTALL_CODEX="$HOME/.codex/skills/$SKILL_NAME"

usage() {
  cat >&2 <<USAGE
Usage:
  $0 push                 # canonical → both install dirs
  $0 pull claude|codex    # named install dir → canonical + other install dir
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
    [ -d "$CANONICAL" ] || { echo "missing: $CANONICAL" >&2; exit 2; }
    rsync_clone "$CANONICAL" "$INSTALL_CLAUDE"
    rsync_clone "$CANONICAL" "$INSTALL_CODEX"
    ;;
  pull)
    agent="${2:-}"
    case "$agent" in
      claude)
        [ -d "$INSTALL_CLAUDE" ] || { echo "missing: $INSTALL_CLAUDE" >&2; exit 2; }
        rsync_clone "$INSTALL_CLAUDE" "$CANONICAL"
        rsync_clone "$INSTALL_CLAUDE" "$INSTALL_CODEX"
        echo "remember: commit and push the repo changes"
        ;;
      codex)
        [ -d "$INSTALL_CODEX" ] || { echo "missing: $INSTALL_CODEX" >&2; exit 2; }
        rsync_clone "$INSTALL_CODEX" "$CANONICAL"
        rsync_clone "$INSTALL_CODEX" "$INSTALL_CLAUDE"
        echo "remember: commit and push the repo changes"
        ;;
      *) usage ;;
    esac
    ;;
  *) usage ;;
esac
