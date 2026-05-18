/**
 * Unit tests for a2a_client.js
 * Run with: npm test (requires jest or mocha)
 * Or with node-sqlite3 installed: node test_a2a_client.js
 */

const A2AClient = require('./a2a_client');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const os = require('os');
const fs = require('fs');
const { promisify } = require('util');
const exec = promisify(require('child_process').exec);

class TestRunner {
  constructor() {
    this.passed = 0;
    this.failed = 0;
    this.testHome = path.join(os.tmpdir(), `a2a-test-${Date.now()}`);
    fs.mkdirSync(this.testHome, { recursive: true });
    process.env.HOME = this.testHome;
  }

  async setupDb(project) {
    const projectDir = path.join(this.testHome, '.a2a', project);
    fs.mkdirSync(projectDir, { recursive: true });
    
    const dbPath = path.join(projectDir, 'database.db');
    return new Promise((resolve, reject) => {
      const db = new sqlite3.Database(dbPath, (err) => {
        if (err) reject(err);
        
        db.exec(`
          CREATE TABLE agents (
            id TEXT PRIMARY KEY,
            role TEXT,
            cli TEXT,
            status TEXT DEFAULT 'active',
            pid INTEGER,
            created_at REAL NOT NULL,
            last_seen REAL NOT NULL
          );
          
          CREATE TABLE messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender TEXT NOT NULL,
            recipient TEXT,
            body TEXT NOT NULL,
            thread_id TEXT,
            ttl_seconds INTEGER,
            created_at REAL NOT NULL
          );
          
          CREATE TABLE reads (
            agent_id TEXT NOT NULL,
            message_id INTEGER NOT NULL,
            read_at REAL NOT NULL,
            PRIMARY KEY (agent_id, message_id)
          );
        `, (err) => {
          if (err) {
            db.close();
            reject(err);
            return;
          }
          
          const now = Date.now() / 1000;
          db.run('INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)', 
            ['alice', 'active', now, now], () => {
            db.run('INSERT INTO agents(id, status, created_at, last_seen) VALUES (?,?,?,?)',
              ['bob', 'active', now, now], () => {
              db.close();
              resolve(project);
            });
          });
        });
      });
    });
  }

  async test(name, fn) {
    try {
      await fn();
      console.log(`✓ ${name}`);
      this.passed++;
    } catch (err) {
      console.log(`✗ ${name}`);
      console.log(`  ${err.message}`);
      this.failed++;
    }
  }

  assert(condition, message) {
    if (!condition) throw new Error(message);
  }

  assertEqual(actual, expected, message) {
    if (actual !== expected) {
      throw new Error(`${message} (got ${actual}, expected ${expected})`);
    }
  }

  cleanup() {
    // Clean up test directory
    const rimraf = (dir) => {
      if (fs.existsSync(dir)) {
        fs.readdirSync(dir).forEach(f => {
          const p = path.join(dir, f);
          if (fs.lstatSync(p).isDirectory()) rimraf(p);
          else fs.unlinkSync(p);
        });
        fs.rmdirSync(dir);
      }
    };
    rimraf(this.testHome);
  }

  async run() {
    console.log('Running a2a Node.js Client Tests\n');

    // Test send and recv
    await this.test('send direct message', async () => {
      const project = `test-send-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const msgId = await alice.send('bob', 'Hello Bob');
      this.assert(msgId > 0, 'Message ID should be positive');
    });

    // Test broadcast
    await this.test('send broadcast', async () => {
      const project = `test-broadcast-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const msgId = await alice.send('all', 'Team message');
      this.assert(msgId > 0, 'Broadcast should have positive ID');
    });

    // Test recv
    await this.test('receive direct message', async () => {
      const project = `test-recv-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const bob = new A2AClient(project, 'bob');
      
      await alice.send('bob', 'Hello from Alice');
      const messages = await bob.recv(1);
      
      this.assertEqual(messages.length, 1, 'Should have 1 message');
      this.assertEqual(messages[0].sender, 'alice', 'Sender should be alice');
      this.assertEqual(messages[0].body, 'Hello from Alice', 'Body should match');
    });

    // Test peek
    await this.test('peek messages', async () => {
      const project = `test-peek-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const bob = new A2AClient(project, 'bob');
      
      await alice.send('bob', 'Message 1');
      await alice.send('bob', 'Message 2');
      
      const messages = await bob.peek(10);
      this.assertEqual(messages.length, 2, 'Should have 2 messages');
    });

    // Test search
    await this.test('search messages', async () => {
      const project = `test-search-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const bob = new A2AClient(project, 'bob');
      
      await alice.send('bob', 'Hello world');
      await alice.send('bob', 'Hello universe');
      
      const results = await alice.search('hello', 10);
      this.assertEqual(results.length, 2, 'Should find 2 messages');
    });

    // Test stats
    await this.test('get stats', async () => {
      const project = `test-stats-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const bob = new A2AClient(project, 'bob');
      
      await alice.send('bob', 'Direct');
      await alice.send('all', 'Broadcast');
      
      const stats = await alice.stats();
      this.assertEqual(stats.messages, 2, 'Should have 2 messages');
      this.assertEqual(stats.direct_messages, 1, 'Should have 1 direct');
      this.assertEqual(stats.broadcasts, 1, 'Should have 1 broadcast');
    });

    // Test status
    await this.test('set and get status', async () => {
      const project = `test-status-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      await alice.setStatus('done');
      const status = await alice.getStatus('alice');
      this.assertEqual(status, 'done', 'Status should be done');
    });

    // Test list peers
    await this.test('list peers', async () => {
      const project = `test-list-${Date.now()}`;
      await this.setupDb(project);
      
      const alice = new A2AClient(project, 'alice');
      const peers = await alice.listPeers();
      this.assertEqual(peers.length, 2, 'Should have 2 agents');
    });

    console.log(`\n${this.passed} passed, ${this.failed} failed`);
    this.cleanup();
    process.exit(this.failed > 0 ? 1 : 0);
  }
}

// Run tests
const runner = new TestRunner();
runner.run().catch(err => {
  console.error('Test error:', err);
  process.exit(1);
});
