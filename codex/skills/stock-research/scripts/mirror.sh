#!/usr/bin/env bash
# Mirror this skill tree to the corresponding install directory.
# Auto-detects target based on script location:
#   <repo>/claude/skills/stock-research/scripts/mirror.sh  -> ~/.claude/skills/stock-research/
#   <repo>/codex/skills/stock-research/scripts/mirror.sh   -> ~/.codex/skills/stock-research/
#
# Usage:
#   ./mirror.sh           refresh install dir from worktree
#   ./mirror.sh --dry     show what would be copied
#
# Excluded from sync: .venv/, .pytest_cache/, __pycache__/, .git
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SKILL_NAME="$(basename "$SKILL_DIR")"
PLATFORM_DIR="$(basename "$(dirname "$(dirname "$SKILL_DIR")")")"

case "$PLATFORM_DIR" in
  claude) TARGET="$HOME/.claude/skills/$SKILL_NAME" ;;
  codex)  TARGET="$HOME/.codex/skills/$SKILL_NAME"  ;;
  *)
    echo "error: cannot determine target install dir from path $SKILL_DIR" >&2
    echo "       expected to live under .../{claude,codex}/skills/$SKILL_NAME/" >&2
    exit 2
    ;;
esac

DRY=""
[[ "${1:-}" == "--dry" ]] && DRY="--dry-run"

echo "Mirroring $SKILL_DIR -> $TARGET"
mkdir -p "$TARGET"
rsync -av --delete $DRY \
  --exclude='.venv/' \
  --exclude='.pytest_cache/' \
  --exclude='__pycache__/' \
  --exclude='.git' \
  --exclude='.DS_Store' \
  "$SKILL_DIR/" "$TARGET/"

echo "Done."
