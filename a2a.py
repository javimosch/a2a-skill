#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""a2a — agent-to-agent peer messaging over SQLite.

CLI-agnostic. Any agentic CLI (claude, opencode, pi, ...) shells out to this
script to register itself, send messages to peers, and poll for incoming
messages. No central chain of command — each agent decides who to talk to.

Storage: ~/.a2a/{project}/database.db
Project name resolution: --project flag > $A2A_PROJECT > basename($PWD)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import textwrap
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id          TEXT PRIMARY KEY,
    role        TEXT,
    prompt      TEXT,
    cli         TEXT,
    status      TEXT NOT NULL DEFAULT 'active',
    pid         INTEGER,
    created_at  REAL NOT NULL,
    last_seen   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sender      TEXT NOT NULL,
    recipient   TEXT,                  -- NULL = broadcast
    body        TEXT NOT NULL,
    thread_id   TEXT,
    ttl_seconds INTEGER,               -- NULL = never expire
    created_at  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reads (
    agent_id    TEXT NOT NULL,
    message_id  INTEGER NOT NULL,
    read_at     REAL NOT NULL,
    PRIMARY KEY (agent_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient);
CREATE INDEX IF NOT EXISTS idx_messages_thread    ON messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_messages_created   ON messages(created_at);
"""


# ---------- paths & db ----------

# Column list used in all message queries (avoids repetition and drift)
MSG_COLS = "id, sender, recipient, body, thread_id, created_at"
MSG_COLS_M = "m.id, m.sender, m.recipient, m.body, m.thread_id, m.created_at"

def project_name(explicit: str | None) -> str:
    if explicit:
        return explicit
    env = os.environ.get("A2A_PROJECT")
    if env:
        return env
    return Path.cwd().name or "default"


def project_dir(name: str) -> Path:
    return Path.home() / ".a2a" / name


def db_path(name: str) -> Path:
    return project_dir(name) / "database.db"


def connect(name: str, create: bool = False) -> sqlite3.Connection:
    path = db_path(name)
    if not path.exists() and not create:
        die(f"no a2a project at '{path}'. run: a2a init --project '{name}'")
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    # migrate: add ttl_seconds if missing (older dbs)
    try:
        conn.execute("SELECT ttl_seconds FROM messages WHERE 1=0")
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE messages ADD COLUMN ttl_seconds INTEGER")
    return conn


def die(msg: str, code: int = 1) -> None:
    print(f"a2a: {msg}", file=sys.stderr)
    sys.exit(code)


def now() -> float:
    return time.time()


def _open(args: argparse.Namespace, *, create: bool = False) -> tuple[str, sqlite3.Connection]:
    """Resolve project name and open database connection."""
    name = project_name(args.project)
    conn = connect(name, create=create)
    return name, conn


def cleanup_expired(conn: sqlite3.Connection) -> int:
    """Delete messages past their TTL. Return count deleted."""
    ts = now()
    cur = conn.execute(
        "DELETE FROM messages WHERE ttl_seconds IS NOT NULL "
        "AND created_at + ttl_seconds < ?",
        (ts,)
    )
    return cur.rowcount


def _resolve_agent(args: argparse.Namespace) -> tuple[str, sqlite3.Connection]:
    """Resolve --as agent from args and verify it's registered. Returns (agent_id, conn)."""
    agent = getattr(args, "as_")
    if not agent:
        die("--as <agent-id> is required")
    _, conn = _open(args)
    if not conn.execute("SELECT 1 FROM agents WHERE id=?", (agent,)).fetchone():
        conn.close()
        die(f"unknown agent '{agent}' — register first")
    return agent, conn


# ---------- commands ----------

def cmd_init(args) -> None:
    name, conn = _open(args, create=True)
    conn.close()
    print(f"a2a project '{name}' ready at {db_path(name)}")


def cmd_project(args) -> None:
    name = project_name(args.project)
    path = db_path(name)
    print(json.dumps({
        "project": name,
        "db": str(path),
        "exists": path.exists(),
    }, indent=2))


def cmd_register(args) -> None:
    name, conn = _open(args, create=True)
    ts = now()
    try:
        conn.execute(
            "INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (args.id, args.role, args.prompt, args.cli, "active",
             args.pid, ts, ts),
        )
    except sqlite3.IntegrityError:
        if not args.upsert:
            conn.close()
            die(f"agent '{args.id}' already registered (use --upsert to update)")
        conn.execute(
            "UPDATE agents SET role=COALESCE(?,role), prompt=COALESCE(?,prompt), "
            "cli=COALESCE(?,cli), pid=COALESCE(?,pid), status='active', last_seen=? "
            "WHERE id=?",
            (args.role, args.prompt, args.cli, args.pid, ts, args.id),
        )
    conn.commit()
    conn.close()
    print(f"registered agent '{args.id}' in project '{name}'")


def cmd_unregister(args) -> None:
    _, conn = _open(args)
    cur = conn.execute("DELETE FROM agents WHERE id=?", (args.id,))
    conn.commit()
    n = cur.rowcount
    conn.close()
    print(f"removed {n} agent(s)")


def cmd_list(args) -> None:
    _, conn = _open(args)
    rows = conn.execute(
        "SELECT id, role, prompt, cli, status, pid, created_at, last_seen FROM agents "
        "ORDER BY created_at"
    ).fetchall()
    conn.close()
    if args.json:
        print(json.dumps([dict(r) for r in rows], indent=2))
        return
    if not rows:
        print("(no agents registered)")
        return
    print(f"{'ID':<20} {'ROLE':<20} {'CLI':<10} {'STATUS':<10} {'PID':<8}")
    for r in rows:
        print(f"{r['id']:<20} {(r['role'] or '-'):<20} {(r['cli'] or '-'):<10} "
              f"{r['status']:<10} {(r['pid'] or '-')!s:<8}")


def cmd_status(args) -> None:
    _, conn = _open(args)
    agent_id = getattr(args, "as_")
    ts = now()
    cur = conn.execute(
        "UPDATE agents SET status=?, last_seen=? WHERE id=?",
        (args.state, ts, agent_id),
    )
    conn.commit()
    n = cur.rowcount
    conn.close()
    if n == 0:
        die(f"no such agent: '{agent_id}'")
    if getattr(args, "json", False):
        print(json.dumps({
            "agent": agent_id,
            "status": args.state,
            "last_seen": ts,
        }, indent=2))
    else:
        print(f"agent '{agent_id}' status -> {args.state}")


def _touch(conn: sqlite3.Connection, agent_id: str) -> None:
    conn.execute("UPDATE agents SET last_seen=? WHERE id=?", (now(), agent_id))


def cmd_send(args) -> None:
    sender = getattr(args, "from_")
    if not sender:
        die("--from <agent-id> is required")
    _, conn = _open(args)
    # verify sender exists
    if not conn.execute("SELECT 1 FROM agents WHERE id=?", (sender,)).fetchone():
        conn.close()
        die(f"unknown sender '{sender}' — register first: a2a register {sender}")
    # recipient: "all" or "*" or "broadcast" => NULL
    recipient = None if args.to.lower() in ("all", "*", "broadcast") else args.to
    if recipient is not None:
        if not conn.execute("SELECT 1 FROM agents WHERE id=?", (recipient,)).fetchone():
            conn.close()
            die(f"unknown recipient '{recipient}'")
    body = args.body
    if body == "-":
        body = sys.stdin.read()
    ttl = getattr(args, "ttl", None)
    cur = conn.execute(
        "INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (sender, recipient, body, args.thread, ttl, now()),
    )
    _touch(conn, sender)
    conn.commit()
    mid = cur.lastrowid
    conn.close()
    target = recipient if recipient else "ALL"
    if getattr(args, "json", False):
        print(json.dumps({
            "id": mid,
            "sender": sender,
            "recipient": target,
        }, indent=2))
    else:
        print(f"#{mid} {sender} -> {target}")


def _fetch_messages(conn: sqlite3.Connection, agent_id: str, unread_only: bool, since: float | None, limit: int | None, mark_read: bool, include_self: bool = False) -> list[sqlite3.Row]:
    # messages addressed to agent OR broadcast (recipient IS NULL)
    base = (
        f"SELECT {MSG_COLS_M} "
        "FROM messages m "
        "WHERE (m.recipient = ? OR m.recipient IS NULL) "
    )
    params = [agent_id]
    if not include_self:
        base += "AND m.sender != ? "
        params.append(agent_id)
    if unread_only:
        base += (
            "AND NOT EXISTS (SELECT 1 FROM reads r "
            "WHERE r.agent_id = ? AND r.message_id = m.id) "
        )
        params.append(agent_id)
    if since is not None:
        base += "AND m.created_at > ? "
        params.append(since)
    base += "ORDER BY m.created_at ASC"
    if limit:
        base += " LIMIT ?"
        params.append(limit)
    rows = conn.execute(base, params).fetchall()
    if mark_read and rows:
        ts = now()
        conn.executemany(
            "INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)",
            [(agent_id, r["id"], ts) for r in rows],
        )
    return rows


def _print_messages(rows: list[sqlite3.Row], as_json: bool) -> None:
    if as_json:
        print(json.dumps([dict(r) for r in rows], indent=2))
        return
    if not rows:
        return
    for r in rows:
        tgt = r["recipient"] or "ALL"
        ts = time.strftime("%H:%M:%S", time.localtime(r["created_at"]))
        thread = f" [thread:{r['thread_id']}]" if r["thread_id"] else ""
        print(f"[{ts}] #{r['id']} {r['sender']} -> {tgt}{thread}")
        # indent body
        for line in r["body"].splitlines() or [""]:
            print(f"    {line}")


def cmd_recv(args) -> None:
    agent, conn = _resolve_agent(args)

    deadline = now() + args.wait if args.wait else None
    poll_interval = 0.5
    while True:
        cleanup_expired(conn)
        rows = _fetch_messages(
            conn, agent,
            unread_only=not args.all,
            since=args.since,
            limit=args.limit,
            mark_read=not args.peek,
            include_self=args.include_self,
        )
        if rows or not args.wait:
            _touch(conn, agent)
            conn.commit()
            _print_messages(rows, args.json)
            conn.close()
            return
        # waiting for new messages
        conn.commit()
        if now() >= deadline:
            _print_messages([], args.json)
            conn.close()
            return
        time.sleep(poll_interval)


def cmd_peek(args) -> None:
    """Show recent messages without marking them read; visible to all observers."""
    _, conn = _open(args)
    cleanup_expired(conn)
    conn.commit()
    rows = conn.execute(
        f"SELECT {MSG_COLS} FROM messages "
        "ORDER BY created_at DESC LIMIT ?",
        (args.limit,),
    ).fetchall()
    conn.close()
    rows = list(reversed(rows))
    _print_messages(rows, args.json)


def cmd_thread(args) -> None:
    """Show all messages in a thread."""
    _, conn = _open(args)
    rows = conn.execute(
        f"SELECT {MSG_COLS} FROM messages "
        "WHERE thread_id = ? ORDER BY created_at ASC",
        (args.id,),
    ).fetchall()
    conn.close()
    if not rows:
        print(f"(no messages in thread '{args.id}')")
    else:
        _print_messages(rows, args.json)


def cmd_clear(args) -> None:
    name = project_name(args.project)
    path = db_path(name)
    if not path.exists():
        print("(nothing to clear)")
        return
    if not args.yes:
        die("refusing without --yes")
    # Remove the database and any WAL-related files
    for suffix in ("", "-wal", "-shm"):
        p = path.with_suffix(path.suffix + suffix)
        if p.exists():
            p.unlink()
    print(f"cleared {name} project database")


def _init_fts(conn: sqlite3.Connection) -> bool:
    """Initialize FTS5 virtual table and sync existing messages.

    Returns True if FTS5 is available and initialized.
    """
    try:
        already_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages_fts'"
        ).fetchone() is not None
        conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5("
            f"{MSG_COLS},"
            f"content=messages, content_rowid=id)"
        )
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN"
            "  INSERT INTO messages_fts(rowid, id, sender, recipient, body, thread_id, created_at)"
            "  VALUES (new.rowid, new.id, new.sender, new.recipient, new.body, new.thread_id, new.created_at);"
            " END"
        )
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN"
            "  DELETE FROM messages_fts WHERE rowid = old.id;"
            " END"
        )
        conn.execute(
            "CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN"
            "  DELETE FROM messages_fts WHERE rowid = old.id;"
            "  INSERT INTO messages_fts(rowid, id, sender, recipient, body, thread_id, created_at)"
            "  VALUES (new.rowid, new.id, new.sender, new.recipient, new.body, new.thread_id, new.created_at);"
            " END"
        )
        if not already_exists:
            conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        conn.commit()
        return True
    except sqlite3.OperationalError:
        return False


def cmd_search(args) -> None:
    """Search messages by content."""
    _, conn = _open(args)
    fts_ready = _init_fts(conn)
    use_fts = args.fts or fts_ready
    if use_fts:
        try:
            rows = conn.execute(
                f"SELECT {MSG_COLS_M} "
                "FROM messages_fts JOIN messages m ON messages_fts.rowid = m.rowid "
                "WHERE messages_fts MATCH ? ORDER BY rank LIMIT ?",
                (args.query, args.limit or 50),
            ).fetchall()
        except sqlite3.OperationalError:
            use_fts = False
    if not use_fts:
        rows = conn.execute(
            f"SELECT {MSG_COLS} FROM messages "
            "WHERE lower(body) LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{args.query.lower()}%", args.limit or 50),
        ).fetchall()
    conn.close()
    if not rows:
        if args.json:
            print("[]")
        else:
            print(f"(no messages matching '{args.query}')")
    else:
        _print_messages(rows, args.json)


def cmd_stats(args) -> None:
    """Show bus statistics."""
    name, conn = _open(args)

    # Count messages and threads
    msg_count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
    thread_count = conn.execute(
        "SELECT COUNT(DISTINCT thread_id) FROM messages WHERE thread_id IS NOT NULL"
    ).fetchone()[0]
    broadcast_count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE recipient IS NULL"
    ).fetchone()[0]
    direct_count = msg_count - broadcast_count

    # Count agents and their statuses
    agents = conn.execute("SELECT status, COUNT(*) FROM agents GROUP BY status").fetchall()
    agent_status = {row[0]: row[1] for row in agents}
    active_count = agent_status.get("active", 0)
    done_count = agent_status.get("done", 0)

    # Top senders
    top_senders = conn.execute(
        "SELECT sender, COUNT(*) as count FROM messages GROUP BY sender ORDER BY count DESC LIMIT 5"
    ).fetchall()

    conn.close()

    stats = {
        "project": name,
        "messages": msg_count,
        "direct_messages": direct_count,
        "broadcasts": broadcast_count,
        "threads": thread_count,
        "agents_active": active_count,
        "agents_done": done_count,
        "top_senders": [{"agent": row[0], "count": row[1]} for row in top_senders],
    }

    if args.json:
        print(json.dumps(stats, indent=2))
    else:
        print(f"Project: {stats['project']}")
        print(f"  Messages: {msg_count} total ({direct_count} direct + {broadcast_count} broadcast)")
        print(f"  Threads: {thread_count}")
        print(f"  Agents: {active_count} active, {done_count} done")
        if top_senders:
            print("  Top senders:")
            for sender, count in top_senders:
                print(f"    {sender}: {count} messages")


def cmd_wait(args) -> None:
    """Block until N messages exist for agent, or timeout."""
    agent, conn = _resolve_agent(args)
    deadline = now() + args.timeout
    while True:
        rows = _fetch_messages(conn, agent, unread_only=True, since=None,
                               limit=None, mark_read=False)
        if len(rows) >= args.count:
            conn.close()
            print(f"ok: {len(rows)} unread")
            return
        if now() >= deadline:
            conn.close()
            die(f"timeout: only {len(rows)} unread (wanted {args.count})", code=2)
        time.sleep(0.5)


# ---------- arg parsing ----------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="a2a",
        description="agent-to-agent peer messaging over SQLite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Project layout:
              ~/.a2a/{project}/database.db    one db per project

            Project resolution:
              --project NAME  >  $A2A_PROJECT  >  basename($PWD)

            Quick start:
              a2a init
              a2a register alice --role researcher
              a2a register bob   --role critic
              a2a send bob "hi"     --from alice
              a2a recv --as bob --wait 10
              a2a thread <id>                    # thread view (v1.1)
              a2a search <query>    --json      # search bus (FTS5 + LIKE fallback)
              a2a stats            --json       # bus statistics (v1.1)
        """),
    )
    p.add_argument("--project", help="project name (overrides $A2A_PROJECT and cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create project database")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("project", help="show resolved project info")
    s.set_defaults(func=cmd_project)

    s = sub.add_parser("register", help="register an agent")
    s.add_argument("id")
    s.add_argument("--role")
    s.add_argument("--prompt", help="initial customization prompt")
    s.add_argument("--cli", help="cli being used (claude/opencode/pi/...)")
    s.add_argument("--pid", type=int)
    s.add_argument("--upsert", action="store_true",
                   help="update if already registered")
    s.set_defaults(func=cmd_register)

    s = sub.add_parser("unregister", help="remove an agent")
    s.add_argument("id")
    s.set_defaults(func=cmd_unregister)

    s = sub.add_parser("list", help="list agents")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("status", help="update agent status")
    s.add_argument("state", choices=["active", "idle", "done", "blocked"])
    s.add_argument("--as", dest="as_", required=True)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("send", help="send a message")
    s.add_argument("to", help="recipient agent id, or 'all' for broadcast")
    s.add_argument("body", help="message body, or '-' to read from stdin")
    s.add_argument("--from", dest="from_", required=True)
    s.add_argument("--thread", help="optional thread/topic id")
    s.add_argument("--ttl", type=int, help="message expires after N seconds (default: never)")
    s.add_argument("--json", action="store_true", help="output as JSON")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("recv", help="receive messages")
    s.add_argument("--as", dest="as_", required=True)
    s.add_argument("--wait", type=float, default=0,
                   help="block up to N seconds for at least one message")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--since", type=float)
    s.add_argument("--all", action="store_true",
                   help="include already-read messages")
    s.add_argument("--include-self", action="store_true",
                   help="include messages sent by this agent")
    s.add_argument("--peek", action="store_true",
                   help="do not mark as read")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_recv)

    s = sub.add_parser("peek", help="show recent messages (no read-tracking)")
    s.add_argument("--limit", type=int, default=20)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_peek)

    s = sub.add_parser("thread", help="show all messages in a thread")
    s.add_argument("id", help="thread id")
    s.add_argument("--json", action="store_true", help="output as JSON")
    s.set_defaults(func=cmd_thread)

    s = sub.add_parser("search", help="search messages by content")
    s.add_argument("query", help="search query (FTS5 syntax or substring)")
    s.add_argument("--limit", type=int, default=50, help="max results (default: 50)")
    s.add_argument("--json", action="store_true", help="output as JSON")
    s.add_argument("--fts", action="store_true", help="force FTS5 full-text search")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("stats", help="show bus statistics")
    s.add_argument("--json", action="store_true", help="output as JSON")
    s.set_defaults(func=cmd_stats)

    s = sub.add_parser("wait", help="block until N unread messages or timeout")
    s.add_argument("--as", dest="as_", required=True)
    s.add_argument("--count", type=int, default=1)
    s.add_argument("--timeout", type=float, default=60)
    s.set_defaults(func=cmd_wait)

    s = sub.add_parser("clear", help="delete the project database")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_clear)

    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
