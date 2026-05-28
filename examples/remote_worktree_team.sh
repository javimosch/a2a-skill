#!/usr/bin/env bash
# remote_worktree_team.sh
#
# Pattern: spawn a multi-role a2a team on a REMOTE machine, working in a
# fresh git worktree. Demonstrated with 4 Claude agents (2 haiku, 2 sonnet)
# adding the agent-groups feature to a2a-skill.
#
# Usage:
#   ./examples/remote_worktree_team.sh [remote_host] [repo_path] [branch_name] [project_name]
#
# Defaults shown in the script body.
#
# Prerequisites on the remote host:
#   - a2a CLI on PATH (or at /usr/local/bin/a2a)
#   - a2a-spawn at a known path (e.g. /root/projects/a2a-skill/a2a-spawn)
#   - claude at ~/.local/bin/claude (may not be on PATH in non-login SSH sessions)
#   - git repo at REPO_PATH with a clean HEAD (no stale rebases)

set -e

REMOTE="${1:-rbm2}"
REPO_PATH="${2:-/root/projects/a2a-skill}"
BRANCH="${3:-feature/a2a-team-features}"
PROJECT="${4:-a2a-feat}"

WORKTREE_PATH="$(dirname "$REPO_PATH")/$(basename "$REPO_PATH")-team"

echo "=== Remote a2a team spawn ==="
echo "  Remote:   $REMOTE"
echo "  Repo:     $REPO_PATH"
echo "  Worktree: $WORKTREE_PATH"
echo "  Branch:   $BRANCH"
echo "  Project:  $PROJECT"
echo ""

ssh "$REMOTE" bash << REMOTE_SCRIPT
set -e

REPO="$REPO_PATH"
WORKTREE="$WORKTREE_PATH"
BRANCH="$BRANCH"
PROJ="$PROJECT"

# ── Resolve the a2a binary ────────────────────────────────────────────────────
A2A=""
for cand in "\$(command -v a2a 2>/dev/null)" /usr/local/bin/a2a "\$HOME/.agents/skills/a2a/a2a"; do
  if [ -x "\$cand" ]; then A2A="\$cand"; break; fi
done
[ -z "\$A2A" ] && { echo "ERROR: a2a not found"; exit 1; }

# ── Resolve a2a-spawn ─────────────────────────────────────────────────────────
# a2a-spawn is typically NOT on PATH in non-login SSH sessions.
# Look in the repo itself and common skill paths.
SPAWN=""
for cand in "\$REPO/a2a-spawn" "\$HOME/.agents/skills/a2a/a2a-spawn" "\$HOME/.claude/skills/a2a/a2a-spawn"; do
  if [ -x "\$cand" ]; then SPAWN="\$cand"; break; fi
done
[ -z "\$SPAWN" ] && { echo "ERROR: a2a-spawn not found"; exit 1; }

echo "a2a:       \$A2A"
echo "a2a-spawn: \$SPAWN"

# ── Clean up stale git state ──────────────────────────────────────────────────
# A stale rebase in progress will block worktree creation.
cd "\$REPO"
if [ -d ".git/rebase-merge" ] || [ -d ".git/rebase-apply" ]; then
  echo "WARNING: stale rebase detected — aborting it"
  git rebase --abort || true
fi

# Ensure main is aligned with origin before branching a worktree from it.
# If local diverged from origin (e.g. a previous session pushed a different
# version of the same commit), reset to origin rather than trying to rebase.
CURRENT_BRANCH=\$(git rev-parse --abbrev-ref HEAD)
if git fetch origin "\$CURRENT_BRANCH" 2>/dev/null; then
  LOCAL_SHA=\$(git rev-parse HEAD)
  REMOTE_SHA=\$(git rev-parse "origin/\$CURRENT_BRANCH")
  if [ "\$LOCAL_SHA" != "\$REMOTE_SHA" ]; then
    echo "WARNING: local diverged from origin — resetting to origin/\$CURRENT_BRANCH"
    git reset --hard "origin/\$CURRENT_BRANCH"
  fi
fi

# ── Create worktree ───────────────────────────────────────────────────────────
if [ -d "\$WORKTREE" ]; then
  echo "Worktree already exists at \$WORKTREE"
else
  git worktree add "\$WORKTREE" -b "\$BRANCH"
  echo "Worktree created: \$WORKTREE (branch: \$BRANCH)"
fi

# ── Init bus ──────────────────────────────────────────────────────────────────
export A2A_PROJECT="\$PROJ"
"\$A2A" init
echo "Bus ready: \$PROJ"

# ── Register agents ───────────────────────────────────────────────────────────
"\$A2A" register pm        --role "product-manager" --prompt "Pick and drive a new big feature" --cli claude
"\$A2A" register architect --role "architect"        --prompt "Design, spec, review" --cli claude
"\$A2A" register dev1      --role "developer"        --prompt "Implement per spec" --cli claude
"\$A2A" register qa        --role "qa"               --prompt "Test, verify, sign off" --cli claude

# ── Write kit prompts ─────────────────────────────────────────────────────────
# IMPORTANT: Write prompts to files, never inline in spawn commands.
# Shell escaping is fragile with multi-line prompts containing single quotes.

cat > /tmp/a2a-\$PROJ-pm.kit << 'KIT'
You are agent "pm" on an a2a peer bus (project=a2a-feat).
Your role: product-manager
Your working directory: WORKTREE_PLACEHOLDER

## Goal mode
1. Pick ONE big new feature for this codebase. Broadcast: GOAL: <name> — <description>
2. Coordinate: ask architect to design it, dev1 to implement it, qa to test it.
3. Check in once per loop. Announce DONE when qa gives QA-APPROVED.

== Peers: architect (design), dev1 (implement), qa (test) ==

== a2a locator ==
  A2A="\${A2A_BIN:-}"; [ -z "\$A2A" ] && A2A="\$(command -v a2a 2>/dev/null)"
  [ -z "\$A2A" ] && [ -x "\$HOME/.agents/skills/a2a/a2a" ] && A2A="\$HOME/.agents/skills/a2a/a2a"
  echo "a2a: \$A2A"

export A2A_PROJECT=a2a-feat
== Commands: \$A2A recv/send/list/status ==

Hard cap: 10 iterations then status done --as pm.
Do NOT call a2a clear or a2a unregister.
Begin: run locator, broadcast GOAL, enter recv loop.
KIT
sed -i "s|WORKTREE_PLACEHOLDER|\$WORKTREE|g" /tmp/a2a-\$PROJ-pm.kit

cat > /tmp/a2a-\$PROJ-architect.kit << 'KIT'
You are agent "architect" on an a2a peer bus (project=a2a-feat).
Your role: architect
Your working directory: WORKTREE_PLACEHOLDER

## Goal mode
Wait for pm to announce GOAL. Then:
1. Read relevant source files to understand the existing structure.
2. Send dev1 a DESIGN spec: files to change, schema, function signatures, invariants.
3. Send qa a TESTPLAN: happy paths, edge cases, regression list.
4. Review IMPL-DONE from dev1. Approve or send REVIEW comments.
5. After qa approves, send pm ARCH-DONE and mark status done.

Key constraint: existing commands (send/recv/list/register/init/status/wait/peek/stats/clear/search/thread) must remain unaffected.

== Peers: pm (goal), dev1 (implements), qa (tests) ==

== a2a locator ==
  A2A="\${A2A_BIN:-}"; [ -z "\$A2A" ] && A2A="\$(command -v a2a 2>/dev/null)"
  [ -z "\$A2A" ] && [ -x "\$HOME/.agents/skills/a2a/a2a" ] && A2A="\$HOME/.agents/skills/a2a/a2a"
  echo "a2a: \$A2A"

export A2A_PROJECT=a2a-feat
Hard cap: 10 iterations then status done --as architect.
Do NOT call a2a clear or a2a unregister.
Begin: run locator, recv --as architect --wait 30, wait for GOAL.
KIT
sed -i "s|WORKTREE_PLACEHOLDER|\$WORKTREE|g" /tmp/a2a-\$PROJ-architect.kit

cat > /tmp/a2a-\$PROJ-dev1.kit << 'KIT'
You are agent "dev1" on an a2a peer bus (project=a2a-feat).
Your role: developer
Your working directory: WORKTREE_PLACEHOLDER

## Goal mode
Wait for architect to send DESIGN spec. Then:
1. ACK receipt immediately: "DESIGN received, starting implementation"
2. Read the named files.
3. Implement exactly as specified. No extra abstractions.
4. When done: send IMPL-DONE: <list of changed files> to both architect and qa.
5. Apply REVIEW fixes promptly.

== Peers: pm (goal), architect (reviews), qa (tests) ==

== a2a locator ==
  A2A="\${A2A_BIN:-}"; [ -z "\$A2A" ] && A2A="\$(command -v a2a 2>/dev/null)"
  [ -z "\$A2A" ] && [ -x "\$HOME/.agents/skills/a2a/a2a" ] && A2A="\$HOME/.agents/skills/a2a/a2a"
  echo "a2a: \$A2A"

export A2A_PROJECT=a2a-feat
Hard cap: 10 iterations then status done --as dev1.
Do NOT call a2a clear or a2a unregister.
Begin: run locator, introduce yourself to architect, recv --as dev1 --wait 30.
KIT
sed -i "s|WORKTREE_PLACEHOLDER|\$WORKTREE|g" /tmp/a2a-\$PROJ-dev1.kit

cat > /tmp/a2a-\$PROJ-qa.kit << 'KIT'
You are agent "qa" on an a2a peer bus (project=a2a-feat).
Your role: qa
Your working directory: WORKTREE_PLACEHOLDER

## Goal mode
Wait for architect's TESTPLAN and dev1's IMPL-DONE. Then:
1. Run: cd WORKTREE_PLACEHOLDER && python3 test_a2a.py -v 2>&1 | tail -20
2. Run: python3 test_integration.py -v 2>&1 | tail -20
3. Test new feature manually per TESTPLAN.
4. Report TEST-PASS or TEST-FAIL: <details> to architect + pm.
5. On pass: send QA-APPROVED to pm and architect, then status done --as qa.

== Peers: pm (goal), architect (design), dev1 (implemented) ==

== a2a locator ==
  A2A="\${A2A_BIN:-}"; [ -z "\$A2A" ] && A2A="\$(command -v a2a 2>/dev/null)"
  [ -z "\$A2A" ] && [ -x "\$HOME/.agents/skills/a2a/a2a" ] && A2A="\$HOME/.agents/skills/a2a/a2a"
  echo "a2a: \$A2A"

export A2A_PROJECT=a2a-feat
Hard cap: 10 iterations then status done --as qa.
Do NOT call a2a clear or a2a unregister.
Begin: run locator, introduce yourself to architect, recv --as qa --wait 30.
KIT
sed -i "s|WORKTREE_PLACEHOLDER|\$WORKTREE|g" /tmp/a2a-\$PROJ-qa.kit

# ── Spawn agents ──────────────────────────────────────────────────────────────
# NOTE: spawning 4 agents simultaneously will make the remote host unresponsive
# to SSH for 60-90s while the claude processes start and hit the API. This is
# normal — the agents are running. Wait before checking the bus.

PM_PID=\$("\$SPAWN" --cli claude --id pm --model haiku \
  --project "\$PROJ" --log /tmp/a2a-\$PROJ-pm.log \
  --kit-file /tmp/a2a-\$PROJ-pm.kit)
"\$A2A" register pm --pid "\$PM_PID" --upsert
echo "pm spawned (PID \$PM_PID)"

ARCH_PID=\$("\$SPAWN" --cli claude --id architect --model sonnet \
  --project "\$PROJ" --log /tmp/a2a-\$PROJ-architect.log \
  --kit-file /tmp/a2a-\$PROJ-architect.kit)
"\$A2A" register architect --pid "\$ARCH_PID" --upsert
echo "architect spawned (PID \$ARCH_PID)"

DEV1_PID=\$("\$SPAWN" --cli claude --id dev1 --model sonnet \
  --project "\$PROJ" --log /tmp/a2a-\$PROJ-dev1.log \
  --kit-file /tmp/a2a-\$PROJ-dev1.kit)
"\$A2A" register dev1 --pid "\$DEV1_PID" --upsert
echo "dev1 spawned (PID \$DEV1_PID)"

QA_PID=\$("\$SPAWN" --cli claude --id qa --model haiku \
  --project "\$PROJ" --log /tmp/a2a-\$PROJ-qa.log \
  --kit-file /tmp/a2a-\$PROJ-qa.kit)
"\$A2A" register qa --pid "\$QA_PID" --upsert
echo "qa spawned (PID \$QA_PID)"

echo ""
echo "=== Team live ==="
A2A_PROJECT="\$PROJ" "\$A2A" list

echo ""
echo "Monitor (run from your local machine):"
echo "  ssh $REMOTE 'A2A_PROJECT=\$PROJ \$A2A peek --limit 50'"
echo "  ssh $REMOTE 'A2A_PROJECT=\$PROJ \$A2A list'"
echo ""
echo "Logs:"
echo "  ssh $REMOTE 'tail -f /tmp/a2a-\$PROJ-pm.log'"
echo "  ssh $REMOTE 'tail -f /tmp/a2a-\$PROJ-dev1.log'"
echo ""
echo "Worktree: \$WORKTREE (branch: \$BRANCH)"
REMOTE_SCRIPT

echo ""
echo "Done. SSH may be slow for 60-90s while agents initialize."
echo "Check progress: ssh $REMOTE \"A2A_PROJECT=$PROJECT /usr/local/bin/a2a peek --limit 50\""
