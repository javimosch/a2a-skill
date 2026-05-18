#!/usr/bin/env bash
# Install a2a-skill: links the CLI onto PATH and the skill into both
# ~/.claude/skills (Claude Code) and ~/.agents/skills (cross-CLI global).
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${A2A_BIN_DIR:-$HOME/.local/bin}"
CLAUDE_SKILL_DIR="${A2A_CLAUDE_SKILL_DIR:-$HOME/.claude/skills}"
AGENTS_SKILL_DIR="${A2A_AGENTS_SKILL_DIR:-$HOME/.agents/skills}"

mkdir -p "$BIN_DIR" "$CLAUDE_SKILL_DIR" "$AGENTS_SKILL_DIR"

ln -sfn "$DIR/a2a"  "$BIN_DIR/a2a"
ln -sfn "$DIR"      "$CLAUDE_SKILL_DIR/a2a"
ln -sfn "$DIR"      "$AGENTS_SKILL_DIR/a2a"

echo "linked $BIN_DIR/a2a              -> $DIR/a2a"
echo "linked $CLAUDE_SKILL_DIR/a2a     -> $DIR"
echo "linked $AGENTS_SKILL_DIR/a2a     -> $DIR"
echo
echo "Make sure $BIN_DIR is on your PATH, then run:"
echo "  a2a init"
echo "Restart Claude Code (or your CLI) to pick up the /a2a skill."
