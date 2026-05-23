/**
 * Tests for a2a_client.js — Node.js client library.
 * Uses node:test (built-in, Node 18+) and node:sqlite (Node 22+).
 * Run: node test_a2a_client.js
 */

const { test, before, after } = require('node:test');
const assert = require('node:assert');
const { DatabaseSync } = require('node:sqlite');
const path = require('path');
const os = require('os');
const fs = require('fs');

const A2AClient = require('./a2a_client.js');

const DB_SCHEMA = `
CREATE TABLE IF NOT EXISTS agents (
  id TEXT PRIMARY KEY, role TEXT, prompt TEXT, cli TEXT,
  status TEXT NOT NULL DEFAULT 'active', pid INTEGER,
  created_at REAL NOT NULL, last_seen REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, sender TEXT NOT NULL,
  recipient TEXT, body TEXT NOT NULL, thread_id TEXT,
  ttl_seconds INTEGER, created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reads (
  agent_id TEXT NOT NULL, message_id INTEGER NOT NULL,
  read_at REAL NOT NULL, PRIMARY KEY (agent_id, message_id)
);
`;

let tmpDir;

function makeClients(project) {
  const dir = path.join(tmpDir, '.a2a', project);
  fs.mkdirSync(dir, { recursive: true });
  const dbPath = path.join(dir, 'database.db');

  const db = new DatabaseSync(dbPath);
  db.exec(DB_SCHEMA);
  const now = Date.now() / 1000;
  db.prepare('INSERT OR IGNORE INTO agents VALUES (?,?,?,?,?,?,?,?)').run('alice','tester',null,'node','active',null,now,now);
  db.prepare('INSERT OR IGNORE INTO agents VALUES (?,?,?,?,?,?,?,?)').run('bob','tester',null,'node','active',null,now,now);
  db.close();

  function client(id) {
    const c = new A2AClient(project, id);
    c.dbDir = dir;
    c.dbPath = dbPath;
    return c;
  }

  return { alice: client('alice'), bob: client('bob'), dbPath, dir };
}

before(() => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-js-test-'));
});

after(() => {
  fs.rmSync(tmpDir, { recursive: true, force: true });
});

// --- WAL invariant ---

test('_connect() enables WAL journal mode', () => {
  const { alice, dbPath } = makeClients('wal-test');
  alice._connect().close();
  const db = new DatabaseSync(dbPath);
  const mode = db.prepare('PRAGMA journal_mode').get().journal_mode;
  db.close();
  assert.strictEqual(mode, 'wal');
});

test('_connect() sets busy_timeout=5000', () => {
  const { alice } = makeClients('busy-test');
  const db = alice._connect();
  const timeout = db.prepare('PRAGMA busy_timeout').get().timeout;
  db.close();
  assert.strictEqual(timeout, 5000);
});

test('_connect() creates parent directory', () => {
  const project = `mkdir-test-${Date.now()}`;
  const dir = path.join(tmpDir, '.a2a', project);
  assert.strictEqual(fs.existsSync(dir), false);

  const c = new A2AClient(project, 'agent');
  c.dbDir = dir;
  c.dbPath = path.join(dir, 'database.db');
  try { c._connect().close(); } catch (_) {}

  assert.strictEqual(fs.existsSync(dir), true);
});

// --- send ---

test('send() returns positive message ID', async () => {
  const { alice } = makeClients('send-1');
  const id = await alice.send('bob', 'Hello');
  assert.ok(Number(id) > 0, `id=${id} should be > 0`);
});

test('send() with thread_id stores thread_id', async () => {
  const { alice, dbPath } = makeClients('send-thread');
  await alice.send('bob', 'Threaded msg', null, 'thread-abc');
  const db = new DatabaseSync(dbPath);
  const row = db.prepare('SELECT thread_id FROM messages WHERE body=?').get('Threaded msg');
  db.close();
  assert.strictEqual(row.thread_id, 'thread-abc');
});

test('send() with empty thread_id rejects', async () => {
  const { alice } = makeClients('send-thread-empty');
  try {
    await alice.send('bob', 'msg', null, '');
    assert.fail('expected error for empty thread_id');
  } catch (e) {
    assert.ok(e.message.includes('thread_id must not be empty'));
  }
  // Also test whitespace-only
  try {
    await alice.send('bob', 'msg', null, '   ');
    assert.fail('expected error for whitespace thread_id');
  } catch (e) {
    assert.ok(e.message.includes('thread_id must not be empty'));
  }
});

// --- send with TTL ---

test('send() with TTL stores ttl_seconds', async () => {
  const { alice, dbPath } = makeClients('send-ttl');
  await alice.send('bob', 'TTL msg', 300);
  const db = new DatabaseSync(dbPath);
  const row = db.prepare('SELECT ttl_seconds FROM messages WHERE body=?').get('TTL msg');
  db.close();
  assert.strictEqual(row.ttl_seconds, 300);
});

test('send() with non-positive TTL rejects', async () => {
  const { alice } = makeClients('send-ttl-bad');
  for (const ttl of [0, -1, -100]) {
    try {
      await alice.send('bob', 'bad', ttl);
      assert.fail('expected error for TTL=' + ttl);
    } catch (e) {
      assert.ok(e.message.includes('ttl_seconds must be a positive number'));
    }
  }
});

test('send() to "all" creates broadcast (recipient=null)', async () => {
  const { alice, dbPath } = makeClients('send-broadcast');
  await alice.send('all', 'Broadcast!');
  const db = new DatabaseSync(dbPath);
  const row = db.prepare('SELECT recipient FROM messages WHERE body=?').get('Broadcast!');
  db.close();
  assert.strictEqual(row.recipient, null);
});

test('send() to "*" also creates broadcast', async () => {
  const { alice, dbPath } = makeClients('send-star');
  await alice.send('*', 'Star broadcast');
  const db = new DatabaseSync(dbPath);
  const row = db.prepare('SELECT recipient FROM messages WHERE body=?').get('Star broadcast');
  db.close();
  assert.strictEqual(row.recipient, null);
});

test('send() to unknown recipient rejects', async () => {
  const { alice } = makeClients('send-unknown-recip');
  try {
    await alice.send('nonexistent', 'hello');
    assert.fail('expected error for unknown recipient');
  } catch (e) {
    assert.ok(e.message.includes('unknown recipient'));
  }
});

test('send() from unregistered sender rejects', async () => {
  const { alice, dir, dbPath } = makeClients('send-ghost-sender');
  const ghost = new A2AClient('send-ghost-sender', 'ghost');
  ghost.dbDir = dir;
  ghost.dbPath = dbPath;
  try {
    await ghost.send('alice', 'hello');
    assert.fail('expected error for unregistered sender');
  } catch (e) {
    assert.ok(e.message.includes('register first'));
  }
});

// --- recv ---

test('recv() returns direct message', async () => {
  const { alice, bob } = makeClients('recv-direct');
  await alice.send('bob', 'Hello Bob');
  const msgs = await bob.recv(1);
  assert.strictEqual(msgs.length, 1);
  assert.strictEqual(msgs[0].sender, 'alice');
  assert.strictEqual(msgs[0].body, 'Hello Bob');
});

test('recv() marks messages as read on second call', async () => {
  const { alice, bob } = makeClients('recv-read');
  await alice.send('bob', 'Once');
  await bob.recv(1);
  const second = await bob.recv(0);
  assert.strictEqual(second.length, 0);
});

test('recv() excludes self by default', async () => {
  const { alice } = makeClients('recv-self');
  await alice.send('alice', 'To self');
  const msgs = await alice.recv(0, true, false);
  assert.strictEqual(msgs.length, 0);
});

test('recv() includes self with includeSelf=true', async () => {
  const { alice } = makeClients('recv-include-self');
  await alice.send('alice', 'Self message');
  const msgs = await alice.recv(1, true, true);
  assert.ok(msgs.length >= 1);
  assert.ok(msgs.some(m => m.body === 'Self message'));
});

test('recv() gets broadcast', async () => {
  const { alice, bob } = makeClients('recv-broadcast');
  await alice.send('all', 'Broadcast msg');
  const msgs = await bob.recv(1);
  assert.strictEqual(msgs.length, 1);
  assert.strictEqual(msgs[0].recipient, null);
});

// --- peek ---

test('peek() does not mark messages read', async () => {
  const { alice, bob } = makeClients('peek-test');
  await alice.send('bob', 'Peekable');
  await bob.peek(10);
  const msgs = await bob.recv(1);
  assert.strictEqual(msgs.length, 1);
  assert.strictEqual(msgs[0].body, 'Peekable');
});

test('peek() returns messages in chronological order', async () => {
  const { alice } = makeClients('peek-order');
  await alice.send('bob', 'First');
  await alice.send('bob', 'Second');
  const msgs = await alice.peek(10);
  assert.ok(msgs.length >= 2);
  const idx = body => msgs.findIndex(m => m.body === body);
  assert.ok(idx('First') < idx('Second'));
});

// --- listPeers ---

test('listPeers() returns all agents', async () => {
  const { alice } = makeClients('peers-test');
  const peers = await alice.listPeers();
  const ids = peers.map(p => p.id);
  assert.ok(ids.includes('alice'));
  assert.ok(ids.includes('bob'));
});

// --- setStatus / getStatus ---

test('setStatus() + getStatus() roundtrip', async () => {
  const { alice } = makeClients('status-test');
  await alice.setStatus('idle');
  const status = await alice.getStatus();
  assert.strictEqual(status, 'idle');
});

test('getStatus() for another agent', async () => {
  const { alice } = makeClients('status-other');
  const status = await alice.getStatus('bob');
  assert.strictEqual(status, 'active');
});

test('getStatus() returns null for unknown agent', async () => {
  const { alice } = makeClients('status-unknown');
  const status = await alice.getStatus('nobody');
  assert.strictEqual(status, null);
});

// --- search ---

test('search() finds messages by keyword', async () => {
  const { alice } = makeClients('search-test');
  await alice.send('bob', 'unique-search-term-xyz');
  const results = await alice.search('unique-search-term-xyz');
  assert.ok(results.length >= 1);
  assert.ok(results[0].body.includes('unique-search-term-xyz'));
});

test('search() is case-insensitive', async () => {
  const { alice } = makeClients('search-case');
  await alice.send('bob', 'MixedCaseSearch');
  const results = await alice.search('mixedcasesearch');
  assert.ok(results.length >= 1);
});

test('search() returns empty for no matches', async () => {
  const { alice } = makeClients('search-empty');
  const results = await alice.search('zzznomatch99999');
  assert.strictEqual(results.length, 0);
});

// --- thread ---

test('thread() returns messages in thread order', async () => {
  const { alice, dbPath } = makeClients('thread-test');
  const db = new DatabaseSync(dbPath);
  const now = Date.now() / 1000;
  db.prepare('INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)').run('alice', 'bob', 'Msg1', 'thread-abc', now);
  db.prepare('INSERT INTO messages(sender, recipient, body, thread_id, created_at) VALUES (?,?,?,?,?)').run('bob', 'alice', 'Msg2', 'thread-abc', now + 1);
  db.close();

  const msgs = await alice.thread('thread-abc');
  assert.strictEqual(msgs.length, 2);
  assert.strictEqual(msgs[0].body, 'Msg1');
  assert.strictEqual(msgs[1].body, 'Msg2');
});

// --- stats ---

test('stats() returns required fields', async () => {
  const { alice, bob } = makeClients('stats-test');
  await alice.send('bob', 'Direct');
  await alice.send('all', 'Broadcast');
  await bob.send('alice', 'Reply');

  const s = await alice.stats();
  assert.ok('messages' in s);
  assert.ok('broadcasts' in s);
  assert.ok('direct_messages' in s);
  assert.ok('agents_active' in s);
  assert.ok('top_senders' in s);
});

test('stats() message counts are accurate', async () => {
  const { alice, bob } = makeClients('stats-counts');
  await alice.send('bob', 'D1');
  await alice.send('all', 'B1');
  await bob.send('alice', 'D2');

  const s = await alice.stats();
  assert.ok(s.messages >= 3);
  assert.ok(s.broadcasts >= 1);
  assert.ok(s.direct_messages >= 2);
});
