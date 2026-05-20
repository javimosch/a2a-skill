# Smoke Test Recipe

This is the canonical end-to-end check for Pattern 3 (auto-spawn). Drop it into a scratch dir and run.

```bash
# Auto-locate a2a (resolves from PATH or common locations)
A2A="$(command -v a2a 2>/dev/null)"
[ -z "$A2A" ] && [ -x "$HOME/.agents/skills/a2a/a2a" ] && A2A="$HOME/.agents/skills/a2a/a2a"
[ -z "$A2A" ] && [ -x "$HOME/.claude/skills/a2a/a2a" ] && A2A="$HOME/.claude/skills/a2a/a2a"
[ -z "$A2A" ] && { echo "a2a not found"; exit 1; }

PROJECT=a2a-smoke-$$
export A2A_PROJECT=$PROJECT

"$A2A" init
"$A2A" register alice --role planner \
  --prompt "Propose a one-line plan for greeting the team, then ask bob to critique."
"$A2A" register bob   --role critic  \
  --prompt "Critique alice's plan in one sentence. Then mark yourself done."

KIT() {  # build kit prompt for a given id/role/prompt
  cat <<EOF
You are agent "$1" on an a2a peer bus (project=$PROJECT).
Role: $2
Instruction: $3
Use: $A2A --project $PROJECT recv --as $1 --wait 15
     $A2A --project $PROJECT send <peer> "msg" --from $1
     $A2A --project $PROJECT status done --as $1
Peers: $($A2A list --json)
Stay terse. After 2 empty recvs, mark done and exit.
EOF
}

claude -p --model haiku --dangerously-skip-permissions \
  --append-system-prompt "$(KIT alice planner 'introduce yourself and ask bob to critique your one-line plan')" \
  "Begin." > /tmp/$PROJECT-alice.log 2>&1 &
ALICE_PID=$!

claude -p --model haiku --dangerously-skip-permissions \
  --append-system-prompt "$(KIT bob critic 'wait for alice, critique in one sentence, then status done')" \
  "Begin." > /tmp/$PROJECT-bob.log 2>&1 &
BOB_PID=$!

# tail the bus
for i in 1 2 3 4 5 6; do sleep 5; "$A2A" peek --limit 20; echo "---"; done
wait $ALICE_PID $BOB_PID 2>/dev/null
"$A2A" peek --limit 50
```

Success = there are messages from `alice` to `bob` *and* from `bob` to `alice`
on the bus, and both agents end with `status='done'`.
