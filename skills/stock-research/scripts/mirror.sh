#!/usr/bin/env bash
# Sync this canonical skill to both agent install directories.
#
# Canonical location:  <repo>/skills/stock-research/
# Install dirs synced: ~/.claude/skills/stock-research/  AND  ~/.codex/skills/stock-research/
#
# Both install dirs receive the same content. Each host agent reads what it
# recognizes (Claude Code reads commands/, Codex reads agents/openai.yaml,
# the rest is shared). Per repo rule 2 in AGENTS.md, every skill change is
# synced to both install dirs in the same flow.
#
# Usage:
#   ./mirror.sh           sync to both install dirs
#   ./mirror.sh --dry     show what would change in each install dir
#
# Excluded from sync: .venv/, .pytest_cache/, __pycache__/, .git, .DS_Store
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"
SKILL_NAME="$(basename "$SKILL_DIR")"

# Sanity check: we should live under .../skills/<name>/scripts/mirror.sh in
# the canonical layout. Refuse rather than silently sync the wrong thing.
PARENT_DIR_NAME="$(basename "$(dirname "$SKILL_DIR")")"
if [[ "$PARENT_DIR_NAME" != "skills" ]]; then
  echo "error: this script must live in <repo>/skills/<name>/scripts/mirror.sh" >&2
  echo "       current SKILL_DIR=$SKILL_DIR (parent=$PARENT_DIR_NAME)" >&2
  exit 2
fi

TARGETS=(
  "$HOME/.claude/skills/$SKILL_NAME"
  "$HOME/.codex/skills/$SKILL_NAME"
)

DRY=""
[[ "${1:-}" == "--dry" ]] && DRY="--dry-run"

for TARGET in "${TARGETS[@]}"; do
  echo "Mirroring $SKILL_DIR -> $TARGET"
  mkdir -p "$TARGET"
  rsync -av --delete $DRY \
    --exclude='.venv/' \
    --exclude='.pytest_cache/' \
    --exclude='__pycache__/' \
    --exclude='.git' \
    --exclude='.DS_Store' \
    "$SKILL_DIR/" "$TARGET/"
  echo
done

echo "Done — synced to both install directories."
