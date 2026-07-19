#!/usr/bin/env bash
# Install a2a-skill: links the CLI onto PATH and the skill into both
# ~/.claude/skills (Claude Code) and ~/.agents/skills (cross-CLI global).
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${A2A_BIN_DIR:-$HOME/.local/bin}"
CLAUDE_SKILL_DIR="${A2A_CLAUDE_SKILL_DIR:-$HOME/.claude/skills}"
AGENTS_SKILL_DIR="${A2A_AGENTS_SKILL_DIR:-$HOME/.agents/skills}"

mkdir -p "$BIN_DIR" "$CLAUDE_SKILL_DIR" "$AGENTS_SKILL_DIR"

ln -sfn "$DIR/a2a"          "$BIN_DIR/a2a"
ln -sfn "$DIR/a2a-spawn"     "$BIN_DIR/a2a-spawn"
ln -sfn "$DIR/a2a-watchdog"  "$BIN_DIR/a2a-watchdog"
ln -sfn "$DIR/a2a-lease"     "$BIN_DIR/a2a-lease"

# Never ln -sfn "$DIR" "$DIR" — that replaces a checkout with a self-symlink
# and destroys the tree (happened when the repo already lived at
# ~/.agents/skills/a2a). Skip when source and destination resolve equal.
_link_skill_dir() {
    local dest="$1"
    local dest_resolved
    dest_resolved="$(readlink -f "$dest" 2>/dev/null || true)"
    if [ "$dest_resolved" = "$DIR" ] || [ "$dest" = "$DIR" ]; then
        echo "skip skill link $dest (already the install source)"
        return 0
    fi
    # If dest is a broken self-symlink or other dead link, remove it first.
    if [ -L "$dest" ] && [ ! -e "$dest" ]; then
        rm -f "$dest"
    fi
    ln -sfn "$DIR" "$dest"
}
_link_skill_dir "$CLAUDE_SKILL_DIR/a2a"
_link_skill_dir "$AGENTS_SKILL_DIR/a2a"

echo "linked $BIN_DIR/a2a              -> $(readlink "$BIN_DIR/a2a")"
echo "linked $BIN_DIR/a2a-spawn        -> $(readlink "$BIN_DIR/a2a-spawn")"
echo "linked $BIN_DIR/a2a-watchdog     -> $(readlink "$BIN_DIR/a2a-watchdog")"
echo "linked $BIN_DIR/a2a-lease        -> $(readlink "$BIN_DIR/a2a-lease")"
echo "skill  $CLAUDE_SKILL_DIR/a2a     -> $(readlink -f "$CLAUDE_SKILL_DIR/a2a" 2>/dev/null || echo "$DIR")"
echo "skill  $AGENTS_SKILL_DIR/a2a     -> $(readlink -f "$AGENTS_SKILL_DIR/a2a" 2>/dev/null || echo "$DIR")"
echo
echo "Make sure $BIN_DIR is on your PATH, then run:"
echo "  a2a init"
echo "Restart Claude Code (or your CLI) to pick up the /a2a skill."
