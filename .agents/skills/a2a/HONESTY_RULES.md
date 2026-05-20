# Honesty Rules

- Agents only know what's on the bus. If they invent peers, that's a bug.
- The database is the source of truth — never claim a message was sent without
  checking it appears in `peek`.
- If a spawned CLI never produces messages within ~60s, dump its log
  (`/tmp/a2a-$PROJECT-<id>.log`) and tell the user what went wrong.
- Do not run a2a in production-touching projects without an explicit user ok —
  agents can run shell commands.
