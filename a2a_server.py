#!/usr/bin/env python3
"""
a2a REST API Server — HTTP interface for a2a messaging
Provides REST endpoints for all core operations over HTTP.
Runs on localhost:5000 (configurable).
"""

import json
import argparse
import sqlite3
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import time

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
        else:
            self.respond_json({'error': f'Not found: {path}'}, 404)

    def handle_send(self, data):
        """POST /send - Send a message"""
        to = data.get('to')
        message = data.get('message')
        ttl = data.get('ttl_seconds')

        if not to or not message:
            self.respond_json({'error': 'Missing to or message'}, 400)
            return

        try:
            db = self.get_db()
            cursor = db.execute(
                'INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) VALUES (?,?,?,?,?)',
                ('http-client', None if to.lower() in ('all', '*') else to, message, ttl, time.time())
            )
            db.commit()
            self.respond_json({'id': cursor.lastrowid, 'status': 'sent'})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def handle_recv(self, data):
        """POST /recv - Receive messages"""
        agent = data.get('agent', 'http-client')
        wait = data.get('wait', 0)
        limit = data.get('limit', 10)

        try:
            db = self.get_db()
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
        limit = int(query.get('limit', ['20'])[0])
        try:
            db = self.get_db()
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
        q = query.get('q', [''])[0]
        limit = int(query.get('limit', ['50'])[0])
        
        if not q:
            self.respond_json({'error': 'Missing q parameter'}, 400)
            return

        try:
            db = self.get_db()
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

        try:
            db = self.get_db()
            db.execute('UPDATE agents SET status = ?, last_seen = ? WHERE id = ?',
                      (status, time.time(), agent))
            db.commit()
            self.respond_json({'agent': agent, 'status': status})
        except Exception as e:
            self.respond_json({'error': str(e)}, 500)

    def get_db(self):
        """Get database connection"""
        project = self.server.project
        db_path = Path.home() / '.a2a' / project / 'database.db'
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
