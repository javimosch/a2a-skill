/**
 * a2a Client Library for Node.js
 * Zero external dependencies — uses node:sqlite (built-in, Node 22+) and node:fs.
 *
 * Applies the WAL invariant on every connection:
 *   PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;
 * Parent directory is created before connecting (no prior `a2a init` required).
 */

const { DatabaseSync } = require('node:sqlite');
const path = require('path');
const os = require('os');
const fs = require('fs');

const _MAX_BODY_LENGTH = 100_000;
const _MAX_THREAD_ID_LENGTH = 256;
const _MAX_AGENT_ID_LENGTH = 256;

class A2AClient {
  /**
   * @param {string} project  - Project name
   * @param {string} agentId  - This agent's ID
   */
  constructor(project, agentId) {
    if (!project || !project.trim()) {
      throw new Error('project must not be empty');
    }
    if (project.includes('/') || project.includes('\\') || project.startsWith('.')) {
      throw new Error(`invalid project name — must not contain path separators or start with '.'`);
    }
    if (!agentId || !agentId.trim()) {
      throw new Error('agent_id must not be empty');
    }
    if (agentId.length > _MAX_AGENT_ID_LENGTH) {
      throw new Error(`agent_id too long (${agentId.length} chars, max ${_MAX_AGENT_ID_LENGTH})`);
    }
    this.project = project;
    this.agentId = agentId;
    this.dbDir = path.join(os.homedir(), '.a2a', project);
    this.dbPath = path.join(this.dbDir, 'database.db');
  }

  /**
   * Open a connection with WAL mode and busy_timeout applied.
   * Creates the parent directory if it does not exist.
   * @private
   * @returns {DatabaseSync}
   */
  _connect() {
    fs.mkdirSync(this.dbDir, { recursive: true });
    const db = new DatabaseSync(this.dbPath);
    db.exec('PRAGMA journal_mode=WAL');
    db.exec('PRAGMA busy_timeout=5000');
    return db;
  }

  /**
   * Delete TTL-expired messages from the bus.
   * Must be called before any message-fetching method (recv, peek).
   * @private
   * @param {DatabaseSync} db
   */
  _cleanupExpired(db) {
    db.prepare(
      'DELETE FROM messages WHERE ttl_seconds IS NOT NULL AND created_at + ttl_seconds < ?'
    ).run(Date.now() / 1000);
  }

  /**
   * Send a message.
   * @param {string}  to            - Recipient ID or "all"/"*" for broadcast
   * @param {string}  message       - Message body
   * @param {number}  [ttlSeconds]  - Optional TTL
   * @param {string}  [threadId]     - Optional thread ID
   * @returns {Promise<number>} Message ID
   */
  async send(to, message, ttlSeconds = null, threadId = null) {
    if (!to || !to.trim()) {
      throw new Error('recipient must not be empty');
    }
    if (!message || !message.trim()) {
      throw new Error('message body must not be empty');
    }
    if (typeof message === 'string' && message.length > _MAX_BODY_LENGTH) {
      throw new Error(`message body too long (${message.length} chars, max ${_MAX_BODY_LENGTH})`);
    }
    if (ttlSeconds !== null && ttlSeconds !== undefined) {
      if (typeof ttlSeconds !== 'number' || !Number.isFinite(ttlSeconds) || ttlSeconds <= 0) {
        throw new Error('ttl_seconds must be a positive number');
      }
    }
    if (threadId !== null && threadId !== undefined) {
      if (!threadId.trim()) {
        throw new Error('thread_id must not be empty');
      }
      if (threadId.length > _MAX_THREAD_ID_LENGTH) {
        throw new Error(`thread_id too long (${threadId.length} chars, max ${_MAX_THREAD_ID_LENGTH})`);
      }
    }
    const db = this._connect();
    // Validate sender exists
    const senderRow = db.prepare('SELECT 1 FROM agents WHERE id=?').get(this.agentId);
    if (!senderRow) {
      db.close();
      throw new Error(`unknown sender '${this.agentId}' — register first`);
    }
    const recipient = ['all', '*', 'broadcast'].includes(to.toLowerCase()) ? null : to;
    // Validate recipient exists (for non-broadcast)
    if (recipient !== null) {
      const recipRow = db.prepare('SELECT 1 FROM agents WHERE id=?').get(recipient);
      if (!recipRow) {
        db.close();
        throw new Error(`unknown recipient '${recipient}' — register them first`);
      }
    }
    const now = Date.now() / 1000;
    const stmt = db.prepare(
      'INSERT INTO messages(sender, recipient, body, thread_id, ttl_seconds, created_at) VALUES (?, ?, ?, ?, ?, ?)'
    );
    const result = stmt.run(this.agentId, recipient, message, threadId, ttlSeconds, now);
    db.close();
    return result.lastInsertRowid;
  }

  /**
   * Receive messages addressed to this agent.
   * @param {number}  [wait=0]        - Block up to N seconds
   * @param {boolean} [unreadOnly]    - Only return unread messages
   * @param {boolean} [includeSelf]   - Include messages from self
   * @param {number}  [limit=0]       - Max results (0 = unlimited)
   * @returns {Promise<Array>}
   */
  async recv(wait = 0, unreadOnly = true, includeSelf = false, limit = 0) {
    if (wait !== 0 && (typeof wait !== 'number' || !Number.isFinite(wait) || wait < 0)) {
      throw new Error('wait must be a non-negative number');
    }
    if (limit !== 0 && (typeof limit !== 'number' || !Number.isInteger(limit) || limit < 0)) {
      throw new Error('limit must be a non-negative integer');
    }
    const deadline = wait ? Date.now() + wait * 1000 : null;

    while (true) {
      const db = this._connect();
      this._cleanupExpired(db);
      let query = `
        SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.created_at
        FROM messages m
        WHERE (m.recipient = ? OR m.recipient IS NULL)
      `;
      const params = [this.agentId];

      if (!includeSelf) {
        query += ' AND m.sender != ?';
        params.push(this.agentId);
      }
      if (unreadOnly) {
        query += `
          AND NOT EXISTS (
            SELECT 1 FROM reads r WHERE r.agent_id = ? AND r.message_id = m.id
          )
        `;
        params.push(this.agentId);
      }
      query += ' ORDER BY m.created_at ASC';
      if (limit) {
        query += ' LIMIT ?';
        params.push(limit);
      }

      const rows = db.prepare(query).all(...params);

      if (rows.length > 0) {
        const ts = Date.now() / 1000;
        const readStmt = db.prepare(
          'INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?, ?, ?)'
        );
        for (const r of rows) {
          readStmt.run(this.agentId, r.id, ts);
        }
        db.close();
        return rows;
      }

      db.close();

      if (!wait || (deadline && Date.now() >= deadline)) {
        return [];
      }
      await new Promise(r => setTimeout(r, 100));
    }
  }

  /**
   * Peek at recent messages without marking them read.
   * @param {number} [limit=20]
   * @returns {Promise<Array>}
   */
  async peek(limit = 20) {
    if (typeof limit !== 'number' || !Number.isInteger(limit) || limit <= 0) {
      throw new Error('limit must be a positive integer');
    }
    const db = this._connect();
    this._cleanupExpired(db);
    const rows = db.prepare(
      'SELECT id, sender, recipient, body, thread_id, created_at FROM messages ORDER BY created_at DESC LIMIT ?'
    ).all(limit);
    db.close();
    return rows.reverse();
  }

  /**
   * List registered agents (alias for listPeers).
   * @returns {Promise<Array>}
   */
  async list() {
    return this.listPeers();
  }

  /**
   * List registered agents.
   * @returns {Promise<Array>}
   */
  async listPeers() {
    const db = this._connect();
    const rows = db.prepare(
      'SELECT id, role, cli, status, pid FROM agents ORDER BY created_at'
    ).all();
    db.close();
    return rows;
  }

  /**
   * Get or set status — matches EXPECTED API.
   * @param {string} [arg] - Status to set, or agent ID to query, or empty to get own
   * @returns {Promise<string|null>}
   */
  async status(arg) {
    if (arg === undefined || arg === null) {
      return this.getStatus();
    }
    if (['active', 'idle', 'done', 'blocked'].includes(arg)) {
      await this.setStatus(arg);
      return null;
    }
    return this.getStatus(arg);
  }

  /**
   * Update this agent's status.
   * @param {string} status
   */
  async setStatus(status) {
    const validStatuses = ['active', 'idle', 'done', 'blocked'];
    if (!validStatuses.includes(status)) {
      throw new Error(`invalid status '${status}'. Must be one of ${validStatuses.join(', ')}`);
    }
    const db = this._connect();
    db.prepare('UPDATE agents SET status=?, last_seen=? WHERE id=?').run(
      status, Date.now() / 1000, this.agentId
    );
    db.close();
  }

  /**
   * Get an agent's status.
   * @param {string} [agentId] - Defaults to this agent
   * @returns {Promise<string|null>}
   */
  async getStatus(agentId = null) {
    const agent = agentId || this.agentId;
    const db = this._connect();
    const row = db.prepare('SELECT status FROM agents WHERE id=?').get(agent);
    db.close();
    return row ? row.status : null;
  }

  /**
   * Block until N unread messages arrive or timeout (alias for waitForMessages).
   * @param {number} [count=1]
   * @param {number} [timeout=60]
   * @returns {Promise<boolean>}
   */
  async wait(count = 1, timeout = 60) {
    return this.waitForMessages(count, timeout);
  }

  /**
   * Block until N unread messages arrive or timeout.
   * @param {number} [count=1]
   * @param {number} [timeout=60]
   * @returns {Promise<boolean>}
   */
  async waitForMessages(count = 1, timeout = 60) {
    if (!Number.isInteger(count) || count <= 0) {
      throw new Error('count must be a positive integer');
    }
    if (typeof timeout !== 'number' || !Number.isFinite(timeout) || timeout < 0) {
      throw new Error('timeout must be a non-negative number');
    }
    const deadline = Date.now() + timeout * 1000;
    while (Date.now() < deadline) {
      const messages = await this.recv(1, true);
      if (messages.length >= count) return true;
      await new Promise(r => setTimeout(r, 500));
    }
    return false;
  }

  /**
   * Search messages by content (case-insensitive LIKE).
   * @param {string} query
   * @param {number} [limit=50]
   * @returns {Promise<Array>}
   */
  async search(query, limit = 50) {
    if (!query || !query.trim()) {
      throw new Error('search query must not be empty');
    }
    if (limit !== undefined && limit !== null && limit <= 0) {
      throw new Error('limit must be a positive integer');
    }
    const db = this._connect();
    const rows = db.prepare(
      'SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE LOWER(body) LIKE ? ORDER BY created_at DESC LIMIT ?'
    ).all(`%${query.toLowerCase()}%`, limit);
    db.close();
    return rows;
  }

  /**
   * Get all messages in a thread.
   * @param {string} threadId
   * @returns {Promise<Array>}
   */
  async thread(threadId) {
    if (!threadId || !threadId.trim()) {
      throw new Error('thread id must not be empty');
    }
    const db = this._connect();
    const rows = db.prepare(
      'SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC'
    ).all(threadId);
    db.close();
    return rows;
  }

  /**
   * Get aggregated bus statistics.
   * @returns {Promise<Object>}
   */
  async stats() {
    const db = this._connect();
    const msgCount = db.prepare('SELECT COUNT(*) as c FROM messages').get().c;
    const broadcastCount = db.prepare('SELECT COUNT(*) as c FROM messages WHERE recipient IS NULL').get().c;
    const threadCount = db.prepare('SELECT COUNT(DISTINCT thread_id) as c FROM messages WHERE thread_id IS NOT NULL').get().c;
    const statusRows = db.prepare('SELECT status, COUNT(*) as c FROM agents GROUP BY status').all();
    const senderRows = db.prepare('SELECT sender, COUNT(*) as c FROM messages GROUP BY sender ORDER BY c DESC LIMIT 5').all();
    db.close();

    const statusMap = {};
    for (const r of statusRows) statusMap[r.status] = r.c;

    return {
      messages: msgCount,
      direct_messages: msgCount - broadcastCount,
      broadcasts: broadcastCount,
      threads: threadCount,
      agents_active: statusMap['active'] || 0,
      agents_done: statusMap['done'] || 0,
      top_senders: senderRows.map(r => ({ agent: r.sender, count: r.c })),
    };
  }

  /**
   * Register this agent on the bus.
   * @param {string}  role           - Agent's role description
   * @param {string}  [prompt='']    - System prompt (optional)
   * @param {string}  [cli='']       - CLI tool name (optional)
   * @param {number}  [pid=null]     - Process ID (optional, must be positive if provided)
   * @param {boolean} [upsert=true]  - Update existing registration, preserving created_at
   * @returns {Promise<boolean>}
   */
  async register(role = '', prompt = '', cli = '', pid = null, upsert = true) {
    if (pid !== null && pid !== undefined && (!Number.isInteger(pid) || pid <= 0)) {
      throw new Error('pid must be a positive integer');
    }
    if (typeof role === 'string' && role.length > _MAX_AGENT_ID_LENGTH) {
      throw new Error(`role too long (${role.length} chars, max ${_MAX_AGENT_ID_LENGTH})`);
    }
    if (typeof cli === 'string' && cli.length > 128) {
      throw new Error(`cli too long (${cli.length} chars, max 128)`);
    }
    if (typeof prompt === 'string' && prompt.length > _MAX_BODY_LENGTH) {
      throw new Error(`prompt too long (${prompt.length} chars, max ${_MAX_BODY_LENGTH})`);
    }
    const db = this._connect();
    const now = Date.now() / 1000;
    if (upsert) {
      db.prepare(
        'INSERT OR IGNORE INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
      ).run(this.agentId, role, prompt, cli, 'active', pid, now, now);
      db.prepare(
        "UPDATE agents SET role=COALESCE(?,role), prompt=COALESCE(?,prompt), cli=COALESCE(?,cli), pid=COALESCE(?,pid), status='active', last_seen=? WHERE id=?"
      ).run(role, prompt, cli, pid, now, this.agentId);
    } else {
      db.prepare(
        'INSERT INTO agents(id, role, prompt, cli, status, pid, created_at, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
      ).run(this.agentId, role, prompt, cli, 'active', pid, now, now);
    }
    db.close();
    return true;
  }

  /**
   * Remove this agent from the bus.
   * @returns {Promise<boolean>}
   */
  async unregister() {
    const db = this._connect();
    db.prepare('DELETE FROM agents WHERE id=?').run(this.agentId);
    db.close();
    return true;
  }

  /**
   * Alias for initProject() — matches EXPECTED API.
   */
  init_project() {
    return this.initProject();
  }

  /**
   * Alias for projectInfo() — matches EXPECTED API.
   * @returns {Object}
   */
  project_info() {
    return this.projectInfo();
  }

  /**
   * Initialize the project database, creating tables if they don't exist.
   * Safe to call multiple times — uses CREATE TABLE IF NOT EXISTS.
   */
  initProject() {
    const db = this._connect();
    db.exec(`
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
        recipient   TEXT,
        body        TEXT NOT NULL,
        thread_id   TEXT,
        ttl_seconds INTEGER,
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
    `);
    db.close();
  }

  /**
   * Get resolved project information.
   * @returns {Object} { project, db, exists }
   */
  projectInfo() {
    return {
      project: this.project,
      db: this.dbPath,
      exists: require('fs').existsSync(this.dbPath),
    };
  }

  /**
   * Delete the project database and all WAL-related files.
   * Warning: This permanently deletes all messages and agent registrations.
   */
  clear() {
    for (const suffix of ['', '-wal', '-shm']) {
      const p = this.dbPath + suffix;
      try { require('fs').unlinkSync(p); } catch (e) { /* ignore */ }
    }
  }
}

module.exports = A2AClient;

if (require.main === module) {
  const project = process.argv[2];
  const agentId = process.argv[3];

  if (!project || !agentId) {
    console.log('Usage: node a2a_client.js <project> <agent-id>');
    process.exit(1);
  }

  const client = new A2AClient(project, agentId);
  console.log('A2A Client initialized');
  console.log(`  Project: ${project}`);
  console.log(`  Agent: ${agentId}`);
  console.log(`  Database: ${client.dbPath}`);
}
