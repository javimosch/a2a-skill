#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
a2a REST API Server — HTTP interface for a2a messaging
Provides REST endpoints for all core operations over HTTP.
Runs on localhost:5000 (configurable).
"""

import json
import argparse
import math
import sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import time

VALID_STATUSES = frozenset({"active", "idle", "done", "blocked"})

class A2ARequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for a2a REST API"""

    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        # Route to handler
        if path == '/health':
            self.respond_json({'status': 'ok'})
        elif path == '/peers':
            self.handle_list_peers(query)
        elif path == '/messages':
            self.handle_peek(query)
        elif path.startswith('/search'):
            self.handle_search(query)
        elif path.startswith('/thread'):
            self.handle_thread(query)
        elif path == '/stats':
            self.handle_stats(query)
        elif path == '/agent':
            self.handle_get_status(query)
        else:
            self.respond_json({'error': f'Not found: {path}'}, 404)

    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        # Read request body
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode('utf-8')
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.respond_json({'error': 'Invalid JSON'}, 400)
            return

        # Route to handler
        if path == '/send':
            self.handle_send(data)
        elif path == '/recv':
            self.handle_recv(data)
        elif path == '/status':
            self.handle_set_status(data)
        elif path == '/register':
            self.handle_register(data)
        elif path == '/unregister':
            self.handle_unregister(data)
        else:
            self.respond_json({'error': f'Not found: {path}'}, 404)

    def handle_send(self, data):
        """POST /send - Send a message"""
        to = data.get('to')
        message = data.get('message')
        ttl = data.get('ttl_seconds')
        thread_id = data.get('thread_id')
        sender = data.get('from') or data.get('sender') or 'http-client'

        if not to or (isinstance(to, str) and to.strip() == ''):
            self.respond_json({'error': 'Missing to'}, 400)
            return
        if not isinstance(to, str):
            self.respond_json({'error': 'Invalid "to" — must be a string'}, 400)
            return
        if not message or (isinstance(message, str) and message.strip() == ''):
            self.respond_json({'error': 'Missing message'}, 400)
            return
        if thread_id is not None and thread_id.strip() == '':
            self.respond_json({'error': 'thread_id cannot be empty'}, 400)
            return
        if thread_id is not None and len(thread_id) > 256:
            self.respond_json({'error': 'thread_id too long (max 256)'}, 400)
            return
        if len(message) > 100_000:
            self.respond_json({'error': 'Message body too long (max 100K)'}, 400)
            return
        if ttl is not None and not isinstance(ttl, (int, float)):
            self.respond_json({'error': 'ttl_seconds must be a number'}, 400)
            return
        if ttl is not None and ttl <= 0:
            self.respond_json({'error': 'ttl_seconds must be a positive number of seconds'}, 400)
            return
        if ttl is not None and (math.isnan(ttl) or math.isinf(ttl)):
            self.respond_json({'error': 'ttl_seconds must be a finite number'}, 400)
            return

        try:
            db = self.get_db()
            cursor = db.execute(
                'INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) VALUES (?,?,?,?,?,?)',
                (sender, None if to.lower() in ('all', '*') else to, message, thread_id, ttl, time.time())
            )
            db.commit()
            self.respond_json({'message_id': cursor.lastrowid, 'status': 'sent'})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_recv(self, data):
        """POST /recv - Receive messages"""
        agent = data.get('agent', 'http-client')
        wait = data.get('wait', 0)
        limit = data.get('limit', 10)
        include_self = data.get('include_self', False)

        try:
            db = self.get_db()
            # Clean up expired messages before fetching
            db.execute(
                "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
                (time.time(),),
            )
            db.commit()
            if include_self:
                rows = db.execute(
                    'SELECT id, sender, recipient, body, thread_id, created_at FROM messages '
                    'WHERE (recipient = ? OR recipient IS NULL) '
                    'AND NOT EXISTS (SELECT 1 FROM reads WHERE agent_id = ? AND message_id = messages.id) '
                    'ORDER BY created_at LIMIT ?',
                    (agent, agent, limit)
                ).fetchall()
            else:
                rows = db.execute(
                    'SELECT id, sender, recipient, body, thread_id, created_at FROM messages '
                    'WHERE (recipient = ? OR recipient IS NULL) AND sender != ? '
                    'AND NOT EXISTS (SELECT 1 FROM reads WHERE agent_id = ? AND message_id = messages.id) '
                    'ORDER BY created_at LIMIT ?',
                    (agent, agent, agent, limit)
                ).fetchall()

            # Mark as read
            ts = time.time()
            for row in rows:
                db.execute('INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)',
                          (agent, row[0], ts))
            db.commit()

            messages = [
                {'id': r[0], 'sender': r[1], 'recipient': r[2], 'body': r[3], 'thread_id': r[4], 'created_at': r[5]}
                for r in rows
            ]
            self.respond_json({'messages': messages})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_list_peers(self, query):
        """GET /peers - List agents"""
        try:
            db = self.get_db()
            rows = db.execute('SELECT id, role, status FROM agents ORDER BY created_at').fetchall()
            peers = [{'id': r[0], 'role': r[1], 'status': r[2]} for r in rows]
            self.respond_json({'peers': peers})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_peek(self, query):
        """GET /messages - Peek at recent messages"""
        try:
            limit = int(query.get('limit', ['20'])[0])
        except (ValueError, IndexError):
            self.respond_json({'error': 'Invalid limit parameter'}, 400)
            return
        if limit <= 0:
            self.respond_json({'error': 'limit must be a positive integer'}, 400)
            return
        try:
            db = self.get_db()
            # Clean up expired messages before fetching
            db.execute(
                "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
                (time.time(),),
            )
            db.commit()
            rows = db.execute(
                'SELECT id, sender, recipient, body, created_at FROM messages '
                'ORDER BY created_at DESC LIMIT ?',
                (limit,)
            ).fetchall()
            messages = [{'id': r[0], 'sender': r[1], 'recipient': r[2], 'body': r[3], 'created_at': r[4]} for r in reversed(rows)]
            self.respond_json({'messages': messages})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_search(self, query):
        """GET /search - Search messages"""
        q = (query.get('q', [''])[0] or '').strip()
        try:
            limit = int(query.get('limit', ['50'])[0])
        except (ValueError, IndexError):
            self.respond_json({'error': 'Invalid limit parameter'}, 400)
            return
        if limit <= 0:
            self.respond_json({'error': 'limit must be a positive integer'}, 400)
            return
        if not q:
            self.respond_json({'error': 'Missing q parameter'}, 400)
            return

        try:
            db = self.get_db()
            # Clean up expired messages before searching
            db.execute(
                "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
                (time.time(),),
            )
            db.commit()
            rows = db.execute(
                'SELECT id, sender, body, created_at FROM messages WHERE body LIKE ? ORDER BY created_at DESC LIMIT ?',
                (f'%{q}%', limit)
            ).fetchall()
            messages = [{'id': r[0], 'sender': r[1], 'body': r[2], 'created_at': r[3]} for r in rows]
            self.respond_json({'query': q, 'results': messages})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_thread(self, query):
        """GET /thread - Get thread messages"""
        thread_id = query.get('id', [None])[0]
        
        if not thread_id:
            self.respond_json({'error': 'Missing id parameter'}, 400)
            return

        try:
            db = self.get_db()
            # Clean up expired messages before fetching thread
            db.execute(
                "DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?",
                (time.time(),),
            )
            db.commit()
            rows = db.execute(
                'SELECT id, sender, body, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC',
                (thread_id,)
            ).fetchall()
            messages = [{'id': r[0], 'sender': r[1], 'body': r[2], 'created_at': r[3]} for r in rows]
            self.respond_json({'thread_id': thread_id, 'messages': messages})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_stats(self, query):
        """GET /stats - Get bus statistics"""
        try:
            db = self.get_db()
            msg_count = db.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
            broadcast_count = db.execute('SELECT COUNT(*) FROM messages WHERE recipient IS NULL').fetchone()[0]
            thread_count = db.execute('SELECT COUNT(DISTINCT thread_id) FROM messages WHERE thread_id IS NOT NULL').fetchone()[0]
            agent_count = db.execute('SELECT COUNT(*) FROM agents').fetchone()[0]

            stats = {
                'messages': msg_count,
                'broadcasts': broadcast_count,
                'direct': msg_count - broadcast_count,
                'threads': thread_count,
                'agents': agent_count
            }
            self.respond_json(stats)
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_get_status(self, query):
        """GET /agent - Get agent status"""
        agent = query.get('id', [None])[0]
        
        if not agent:
            self.respond_json({'error': 'Missing id parameter'}, 400)
            return

        try:
            db = self.get_db()
            row = db.execute('SELECT status FROM agents WHERE id = ?', (agent,)).fetchone()
            if row:
                self.respond_json({'agent': agent, 'status': row[0]})
            else:
                self.respond_json({'error': 'Agent not found'}, 404)
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_set_status(self, data):
        """POST /status - Set agent status"""
        agent = data.get('agent', 'http-client')
        status = data.get('status')

        if not status:
            self.respond_json({'error': 'Missing status'}, 400)
            return

        if status not in VALID_STATUSES:
            self.respond_json(
                {'error': f"Invalid status '{status}' — must be one of: {', '.join(sorted(VALID_STATUSES))}"},
                400,
            )
            return

        try:
            db = self.get_db()
            db.execute('UPDATE agents SET status = ?, last_seen = ? WHERE id = ?',
                      (status, time.time(), agent))
            db.commit()
            self.respond_json({'agent': agent, 'status': status})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_register(self, data):
        """POST /register - Register an agent"""
        agent_id = data.get('agent_id')
        role = data.get('role', '')
        if not agent_id:
            self.respond_json({'error': 'Missing agent_id'}, 400)
            return
        if len(role) > 512:
            self.respond_json({'error': 'role too long (max 512)'}, 400)
            return
        cli = data.get('cli', '')
        if len(cli) > 128:
            self.respond_json({'error': 'cli too long (max 128)'}, 400)
            return
        prompt = data.get('prompt', '')
        if len(prompt) > 100_000:
            self.respond_json({'error': 'prompt too long (max 100K)'}, 400)
            return
        pid = data.get('pid', 0)
        if pid is not None and pid != 0 and pid != '':
            try:
                pid_int = int(pid)
                if pid_int <= 0:
                    self.respond_json({'error': 'pid must be a positive integer'}, 400)
                    return
            except (ValueError, TypeError):
                self.respond_json({'error': 'pid must be a positive integer'}, 400)
                return
        try:
            db = self.get_db()
            now = time.time()
            db.execute(
                "INSERT OR IGNORE INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (agent_id, role, prompt, cli,
                 'active', pid, now, now),
            )
            db.execute(
                "UPDATE agents SET role=?, prompt=?, cli=?, status=?, pid=?, last_seen=? WHERE id=?",
                (role, prompt, cli, 'active', pid, now, agent_id),
            )
            db.commit()
            self.respond_json({'agent_id': agent_id, 'role': role, 'status': 'active'})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_unregister(self, data):
        """POST /unregister - Unregister an agent"""
        agent_id = data.get('agent_id')
        if not agent_id:
            self.respond_json({'error': 'Missing agent_id'}, 400)
            return
        try:
            db = self.get_db()
            db.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
            db.commit()
            self.respond_json({'agent_id': agent_id, 'unregistered': True})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def get_db(self):
        """Get database connection"""
        # Use precomputed absolute path so HOME changes in tests don't affect routing.
        db_path = Path(self.server.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def respond_json(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))

    def log_message(self, format, *args):
        """Suppress default logging"""
        pass


def run_server(project, host='localhost', port=5000):
    """Run the a2a REST API server"""
    server = HTTPServer((host, port), A2ARequestHandler)
    server.project = project
    # Resolve db_path at startup so HOME changes in tests don't affect routing.
    server.db_path = str(Path.home() / '.a2a' / project / 'database.db')
    
    print(f'a2a REST API Server')
    print(f'  Project: {project}')
    print(f'  URL: http://{host}:{port}')
    print(f'')
    print(f'Endpoints:')
    print(f'  GET  /health                 - Health check')
    print(f'  GET  /peers                  - List agents')
    print(f'  GET  /messages?limit=20      - Peek at messages')
    print(f'  GET  /search?q=keyword       - Search messages')
    print(f'  GET  /thread?id=123          - Get thread')
    print(f'  GET  /stats                  - Bus statistics')
    print(f'  GET  /agent?id=alice         - Get agent status')
    print(f'  POST /send                   - Send message')
    print(f'  POST /recv                   - Receive messages')
    print(f'  POST /status                 - Set agent status')
    print(f'  POST /register               - Register an agent')
    print(f'  POST /unregister             - Unregister an agent')
    print(f'')
    print(f'Try: curl http://{host}:{port}/health')
    print(f'')
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutdown.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='a2a REST API Server')
    parser.add_argument('--project', default='a2a-rest-api', help='Project name')
    parser.add_argument('--host', default='localhost', help='Host to listen on')
    parser.add_argument('--port', type=int, default=5000, help='Port to listen on')
    
    args = parser.parse_args()
    run_server(args.project, args.host, args.port)
