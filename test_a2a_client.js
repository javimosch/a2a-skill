/**
 * Tests for a2a_client.js — Node.js client library.
 * Uses node:test (built-in, Node 18+) and node:sqlite (Node 22+).
 * Run: node test_a2a_client.js
 */

const { test, before, after } = require('node:test');
const assert = require('node:assert');
let DatabaseSync;
try {
  DatabaseSync = require('node:sqlite').DatabaseSync;
} catch (e) {
  console.error('WARN: node:sqlite unavailable (Node < 22) — skipping all tests');
  process.exit(0);
}
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
  db.exec('PRAGMA journal_mode=WAL');
  db.exec('PRAGMA busy_timeout=5000');
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

// --- register ---

test('register() registers agent on bus', async () => {
  const project = 'register-test';
  const dir = path.join(tmpDir, '.a2a', project);
  fs.mkdirSync(dir, { recursive: true });
  const dbPath = path.join(dir, 'database.db');
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode=WAL');
  db.exec(DB_SCHEMA);
  db.close();

  const c = new A2AClient(project, 'charlie');
  c.dbDir = dir;
  c.dbPath = dbPath;
  const ok = await c.register('tester', 'testing', 'node', 456, false);
  assert.strictEqual(ok, true);

  const db2 = new DatabaseSync(dbPath);
  const row = db2.prepare("SELECT id, role, prompt, cli, pid, status FROM agents WHERE id='charlie'").get();
  db2.close();
  assert.ok(row);
  assert.strictEqual(row.role, 'tester');
  assert.strictEqual(row.pid, 456);
  assert.strictEqual(row.status, 'active');
});

test('register() with negative PID rejects', async () => {
  const project = 'register-pid';
  const dir = path.join(tmpDir, '.a2a', project);
  fs.mkdirSync(dir, { recursive: true });
  const dbPath = path.join(dir, 'database.db');
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode=WAL');
  db.exec(DB_SCHEMA);
  db.close();

  const c = new A2AClient(project, 'dave');
  c.dbDir = dir;
  c.dbPath = dbPath;
  try {
    await c.register('tester', '', '', -1, false);
    assert.fail('expected error for negative PID');
  } catch (e) {
    assert.ok(e.message.includes('pid must be a positive integer'));
  }
});

test('register() without upsert fails on duplicate', async () => {
  const project = 'register-no-upsert';
  const dir = path.join(tmpDir, '.a2a', project);
  fs.mkdirSync(dir, { recursive: true });
  const dbPath = path.join(dir, 'database.db');
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode=WAL');
  db.exec(DB_SCHEMA);
  db.close();

  const c = new A2AClient(project, 'eve');
  c.dbDir = dir;
  c.dbPath = dbPath;
  await c.register('first', '', '', null, false);
  try {
    await c.register('second', '', '', null, false);
    assert.fail('expected error for duplicate register without upsert');
  } catch (e) {
    assert.ok(e);
  }
});

test('register() with upsert updates existing', async () => {
  const project = 'register-upsert';
  const dir = path.join(tmpDir, '.a2a', project);
  fs.mkdirSync(dir, { recursive: true });
  const dbPath = path.join(dir, 'database.db');
  const db = new DatabaseSync(dbPath);
  db.exec('PRAGMA journal_mode=WAL');
  db.exec(DB_SCHEMA);
  db.close();

  const c = new A2AClient(project, 'frank');
  c.dbDir = dir;
  c.dbPath = dbPath;
  await c.register('first', '', '', null, false);
  const ok = await c.register('second', '', '', 999, true);
  assert.strictEqual(ok, true);

  const db2 = new DatabaseSync(dbPath);
  const row = db2.prepare("SELECT role, pid FROM agents WHERE id='frank'").get();
  db2.close();
  assert.strictEqual(row.role, 'second');
  assert.strictEqual(row.pid, 999);
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

// --- touch ---

test('touch() updates last_seen', async () => {
  const { alice, dbPath } = makeClients('touch-test');
  const db = new DatabaseSync(dbPath);
  const before = db.prepare("SELECT last_seen FROM agents WHERE id='alice'").get().last_seen;
  db.close();
  await new Promise(r => setTimeout(r, 10));
  await alice.touch();
  const db2 = new DatabaseSync(dbPath);
  const after = db2.prepare("SELECT last_seen FROM agents WHERE id='alice'").get().last_seen;
  db2.close();
  assert.ok(after > before, 'last_seen should increase after touch()');
});

test('touch() on unknown agent does not throw', async () => {
  const { dir, dbPath } = makeClients('touch-ghost');
  const ghost = new A2AClient('touch-ghost', 'ghost');
  ghost.dbDir = dir;
  ghost.dbPath = dbPath;
  // Should not throw
  await ghost.touch();
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

// --- task tests (phase 2) ---

test('createTask returns positive ID', async () => {
  const { alice } = makeClients('task-create-basic');
  const id = await alice.createTask('Test task');
  assert.ok(typeof id === 'number');
  assert.ok(id > 0);
});

test('createTask stores title and status', async () => {
  const { alice } = makeClients('task-create-store');
  await alice.createTask('Test task');
  const tasks = await alice.listTasks();
  assert.strictEqual(tasks.length, 1);
  assert.strictEqual(tasks[0].title, 'Test task');
  assert.strictEqual(tasks[0].status, 'planned');
});

test('createTask with description, assignee, priority', async () => {
  const { alice } = makeClients('task-create-full');
  await alice.createTask('Build feature', 'Implement X', 'bob', 1);
  const tasks = await alice.listTasks();
  assert.strictEqual(tasks.length, 1);
  assert.strictEqual(tasks[0].title, 'Build feature');
  assert.strictEqual(tasks[0].description, 'Implement X');
  assert.strictEqual(tasks[0].assigned_to, 'bob');
  assert.strictEqual(tasks[0].priority, 1);
});

test('createTask with dependencies', async () => {
  const { alice } = makeClients('task-create-deps');
  const t1 = await alice.createTask('First');
  const t2 = await alice.createTask('Second', '', '', 3, [t1]);
  const tasks = await alice.listTasks();
  const second = tasks.find(t => t.id === t2);
  assert.ok(second);
  assert.ok(second.dependencies);
});

test('createTask empty title throws', async () => {
  const { alice } = makeClients('task-create-empty');
  await assert.rejects(() => alice.createTask(''), /must not be empty/);
  await assert.rejects(() => alice.createTask('   '), /must not be empty/);
});

test('createTask invalid priority throws', async () => {
  const { alice } = makeClients('task-create-prio');
  await assert.rejects(() => alice.createTask('test', '', '', 5));
  await assert.rejects(() => alice.createTask('test', '', '', 0));
});

test('listTasks empty returns empty array', async () => {
  const { alice } = makeClients('list-empty');
  const tasks = await alice.listTasks();
  assert.deepStrictEqual(tasks, []);
});

test('listTasks filter by status', async () => {
  const { alice } = makeClients('list-status');
  await alice.createTask('Task A');
  await alice.createTask('Task B');
  const planned = await alice.listTasks('planned');
  assert.strictEqual(planned.length, 2);
  const done = await alice.listTasks('done');
  assert.strictEqual(done.length, 0);
});

test('listTasks filter by assigned', async () => {
  const { alice } = makeClients('list-assigned');
  await alice.createTask('Alice task', '', 'alice');
  await alice.createTask('Bob task', '', 'bob');
  const aliceTasks = await alice.listTasks(null, 'alice');
  assert.strictEqual(aliceTasks.length, 1);
  assert.strictEqual(aliceTasks[0].title, 'Alice task');
});

test('updateTaskStatus valid transitions', async () => {
  const { alice } = makeClients('update-valid');
  const tid = await alice.createTask('Workflow');
  await alice.updateTaskStatus(tid, 'in_progress');
  await alice.updateTaskStatus(tid, 'review_pending');
  await alice.updateTaskStatus(tid, 'approved');
  await alice.updateTaskStatus(tid, 'done');
  const tasks = await alice.listTasks();
  assert.strictEqual(tasks[0].status, 'done');
});

test('updateTaskStatus invalid transition throws', async () => {
  const { alice } = makeClients('update-invalid');
  const tid = await alice.createTask('Test');
  await assert.rejects(() => alice.updateTaskStatus(tid, 'done'));
  await assert.rejects(() => alice.updateTaskStatus(tid, 'blocked'));
});

test('updateTaskStatus done is terminal', async () => {
  const { alice } = makeClients('update-terminal');
  const tid = await alice.createTask('Test');
  await alice.updateTaskStatus(tid, 'in_progress');
  await alice.updateTaskStatus(tid, 'done');
  await assert.rejects(() => alice.updateTaskStatus(tid, 'in_progress'));
});

test('updateTaskStatus blocked then unblock', async () => {
  const { alice } = makeClients('update-blocked');
  const tid = await alice.createTask('Test');
  await alice.updateTaskStatus(tid, 'in_progress');
  await alice.updateTaskStatus(tid, 'blocked');
  await alice.updateTaskStatus(tid, 'in_progress');
  const tasks = await alice.listTasks();
  assert.strictEqual(tasks[0].status, 'in_progress');
});

test('updateTaskStatus not found throws', async () => {
  const { alice } = makeClients('update-notfound');
  await assert.rejects(() => alice.updateTaskStatus(9999, 'in_progress'));
});

test('claimTask sets in_progress and assigns', async () => {
  const { alice, bob } = makeClients('claim-ok');
  const tid = await alice.createTask('Claimable', '', 'alice');
  await bob.claimTask(tid);
  const tasks = await alice.listTasks();
  assert.strictEqual(tasks[0].status, 'in_progress');
  assert.strictEqual(tasks[0].assigned_to, 'bob');
});

test('claimTask already done throws', async () => {
  const { alice } = makeClients('claim-done');
  const tid = await alice.createTask('Done task');
  await alice.updateTaskStatus(tid, 'in_progress');
  await alice.updateTaskStatus(tid, 'done');
  await assert.rejects(() => alice.claimTask(tid));
});

test('claimTask assigned to other throws', async () => {
  const { alice, bob } = makeClients('claim-other');
  const tid = await alice.createTask('Others task', '', 'alice');
  await assert.rejects(() => bob.claimTask(tid));
});

test('claimTask not found throws', async () => {
  const { alice } = makeClients('claim-notfound');
  await assert.rejects(() => alice.claimTask(9999));
});

test('completeTask sets done with result', async () => {
  const { alice } = makeClients('complete-result');
  const tid = await alice.createTask('Completable', '', 'alice');
  await alice.claimTask(tid);
  await alice.completeTask(tid, 'All done!');
  const tasks = await alice.listTasks();
  assert.strictEqual(tasks[0].status, 'done');
  assert.strictEqual(tasks[0].result, 'All done!');
});

test('completeTask not found throws', async () => {
  const { alice } = makeClients('complete-notfound');
  await assert.rejects(() => alice.completeTask(9999, 'nope'));
});
