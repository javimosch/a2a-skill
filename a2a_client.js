/**
 * a2a Client Library for Node.js
 * Provides object-oriented access to a2a messaging without shell invocation.
 * Zero external dependencies - uses only Node.js built-ins (sqlite3, path, fs).
 */

const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const os = require('os');

class A2AClient {
  /**
   * Initialize a2a client
   * @param {string} project - Project name (or env A2A_PROJECT)
   * @param {string} agentId - This agent's ID
   */
  constructor(project, agentId) {
    this.project = project;
    this.agentId = agentId;
    const dbDir = path.join(os.homedir(), '.a2a', project);
    this.dbPath = path.join(dbDir, 'database.db');
  }

  /**
   * Connect to project database
   * @private
   */
  _connect() {
    return new Promise((resolve, reject) => {
      const db = new sqlite3.Database(this.dbPath, sqlite3.OPEN_READWRITE, (err) => {
        if (err) reject(err);
        else resolve(db);
      });
    });
  }

  /**
   * Send a message
   * @param {string} to - Recipient agent ID, or "all" for broadcast
   * @param {string} message - Message body
   * @param {number} ttlSeconds - Optional time-to-live in seconds
   * @returns {Promise<number>} Message ID
   */
  async send(to, message, ttlSeconds = null) {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      const recipient = ['all', '*', 'broadcast'].includes(to.toLowerCase()) ? null : to;
      const now = Date.now() / 1000;

      db.run(
        'INSERT INTO messages(sender, recipient, body, ttl_seconds, created_at) VALUES (?, ?, ?, ?, ?)',
        [this.agentId, recipient, message, ttlSeconds, now],
        function(err) {
          db.close();
          if (err) reject(err);
          else resolve(this.lastID);
        }
      );
    });
  }

  /**
   * Receive messages addressed to this agent
   * @param {number} wait - Block up to N seconds for messages
   * @param {boolean} unreadOnly - Only return unread messages
   * @param {boolean} includeSelf - Include messages sent by this agent
   * @param {number} limit - Max messages to return (0 = unlimited)
   * @returns {Promise<Array>} List of message dicts
   */
  async recv(wait = 0, unreadOnly = true, includeSelf = false, limit = 0) {
    const db = await this._connect();
    const deadline = wait ? Date.now() + (wait * 1000) : null;
    const pollInterval = 100;

    return new Promise((resolve, reject) => {
      const poll = () => {
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
            AND NOT EXISTS (SELECT 1 FROM reads r
            WHERE r.agent_id = ? AND r.message_id = m.id)
          `;
          params.push(this.agentId);
        }

        query += ' ORDER BY m.created_at ASC';
        if (limit) {
          query += ' LIMIT ?';
          params.push(limit);
        }

        db.all(query, params, (err, rows) => {
          if (err) {
            db.close();
            reject(err);
            return;
          }

          if (rows && rows.length > 0) {
            // Mark as read
            const ts = Date.now() / 1000;
            const readStmt = db.prepare(
              'INSERT OR IGNORE INTO reads(agent_id, message_id, read_at) VALUES (?,?,?)'
            );
            rows.forEach(r => {
              readStmt.run([this.agentId, r.id, ts]);
            });
            readStmt.finalize();
            db.close();
            resolve(rows);
          } else if (!wait || (deadline && Date.now() >= deadline)) {
            db.close();
            resolve([]);
          } else {
            setTimeout(poll, pollInterval);
          }
        });
      };

      poll();
    });
  }

  /**
   * Peek at recent messages without marking read
   * @param {number} limit - Max messages to return
   * @returns {Promise<Array>} List of message dicts
   */
  async peek(limit = 20) {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      db.all(
        'SELECT id, sender, recipient, body, thread_id, created_at FROM messages ORDER BY created_at DESC LIMIT ?',
        [limit],
        (err, rows) => {
          db.close();
          if (err) reject(err);
          else resolve((rows || []).reverse());
        }
      );
    });
  }

  /**
   * Get list of registered agents
   * @returns {Promise<Array>} List of agent dicts
   */
  async listPeers() {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      db.all(
        'SELECT id, role, cli, status, pid FROM agents ORDER BY created_at',
        (err, rows) => {
          db.close();
          if (err) reject(err);
          else resolve(rows || []);
        }
      );
    });
  }

  /**
   * Update this agent's status
   * @param {string} status - One of 'active', 'idle', 'done', 'blocked'
   */
  async setStatus(status) {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      const now = Date.now() / 1000;
      db.run(
        'UPDATE agents SET status=?, last_seen=? WHERE id=?',
        [status, now, this.agentId],
        (err) => {
          db.close();
          if (err) reject(err);
          else resolve();
        }
      );
    });
  }

  /**
   * Get an agent's status
   * @param {string} agentId - Agent ID (defaults to self.agentId)
   * @returns {Promise<string|null>} Status string or null if not found
   */
  async getStatus(agentId = null) {
    const agent = agentId || this.agentId;
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      db.get(
        'SELECT status FROM agents WHERE id=?',
        [agent],
        (err, row) => {
          db.close();
          if (err) reject(err);
          else resolve(row ? row.status : null);
        }
      );
    });
  }

  /**
   * Block until N unread messages or timeout
   * @param {number} count - Number of unread messages to wait for
   * @param {number} timeout - Max seconds to wait
   * @returns {Promise<boolean>} True if got N messages, false on timeout
   */
  async waitForMessages(count = 1, timeout = 60) {
    const deadline = Date.now() + (timeout * 1000);
    while (Date.now() < deadline) {
      const messages = await this.recv(1, true);
      if (messages.length >= count) return true;
      await new Promise(r => setTimeout(r, 500));
    }
    return false;
  }

  /**
   * Search messages by content
   * @param {string} query - Search substring (case-insensitive)
   * @param {number} limit - Max messages to return
   * @returns {Promise<Array>} List of matching message dicts
   */
  async search(query, limit = 50) {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      db.all(
        'SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE body LIKE ? ORDER BY created_at DESC LIMIT ?',
        [`%${query.toLowerCase()}%`, limit],
        (err, rows) => {
          db.close();
          if (err) reject(err);
          else resolve(rows || []);
        }
      );
    });
  }

  /**
   * Get all messages in a thread
   * @param {number} threadId - Thread ID
   * @returns {Promise<Array>} List of message dicts in thread
   */
  async thread(threadId) {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      db.all(
        'SELECT id, sender, recipient, body, thread_id, created_at FROM messages WHERE thread_id = ? ORDER BY created_at ASC',
        [threadId],
        (err, rows) => {
          db.close();
          if (err) reject(err);
          else resolve(rows || []);
        }
      );
    });
  }

  /**
   * Get aggregated bus statistics
   * @returns {Promise<Object>} Dict with message counts, agent stats, etc.
   */
  async stats() {
    const db = await this._connect();
    return new Promise((resolve, reject) => {
      db.get('SELECT COUNT(*) as count FROM messages', [], (err, msgRow) => {
        if (err) {
          db.close();
          reject(err);
          return;
        }

        db.get('SELECT COUNT(DISTINCT thread_id) as count FROM messages WHERE thread_id IS NOT NULL', [], (err, threadRow) => {
          if (err) {
            db.close();
            reject(err);
            return;
          }

          db.get('SELECT COUNT(*) as count FROM messages WHERE recipient IS NULL', [], (err, broadcastRow) => {
            if (err) {
              db.close();
              reject(err);
              return;
            }

            db.all('SELECT status, COUNT(*) as count FROM agents GROUP BY status', [], (err, statusRows) => {
              if (err) {
                db.close();
                reject(err);
                return;
              }

              db.all('SELECT sender, COUNT(*) as count FROM messages GROUP BY sender ORDER BY count DESC LIMIT 5', [], (err, senderRows) => {
                db.close();
                if (err) {
                  reject(err);
                  return;
                }

                const msgCount = msgRow.count;
                const threadCount = threadRow.count;
                const broadcastCount = broadcastRow.count;
                const directCount = msgCount - broadcastCount;

                const statusMap = {};
                (statusRows || []).forEach(r => {
                  statusMap[r.status] = r.count;
                });

                resolve({
                  messages: msgCount,
                  direct_messages: directCount,
                  broadcasts: broadcastCount,
                  threads: threadCount,
                  agents_active: statusMap['active'] || 0,
                  agents_done: statusMap['done'] || 0,
                  top_senders: (senderRows || []).map(r => ({
                    agent: r.sender,
                    count: r.count
                  }))
                });
              });
            });
          });
        });
      });
    });
  }
}

module.exports = A2AClient;

// Example usage
if (require.main === module) {
  const project = process.argv[2];
  const agentId = process.argv[3];

  if (!project || !agentId) {
    console.log('Usage: node a2a_client.js <project> <agent-id>');
    console.log('');
    console.log('Example:');
    console.log('  const A2AClient = require("./a2a_client");');
    console.log('  const client = new A2AClient("my-project", "alice");');
    console.log('  await client.send("bob", "Hello");');
    process.exit(1);
  }

  const client = new A2AClient(project, agentId);
  console.log('A2A Client initialized');
  console.log(`  Project: ${project}`);
  console.log(`  Agent: ${agentId}`);
  console.log(`  Database: ${client.dbPath}`);
  console.log('');
  console.log('Available methods:');
  console.log('  await client.send(to, message, ttlSeconds)');
  console.log('  await client.recv(wait, unreadOnly, includeSelf, limit)');
  console.log('  await client.peek(limit)');
  console.log('  await client.listPeers()');
  console.log('  await client.setStatus(status)');
  console.log('  await client.getStatus(agentId)');
  console.log('  await client.waitForMessages(count, timeout)');
  console.log('  await client.search(query, limit)');
  console.log('  await client.thread(threadId)');
  console.log('  await client.stats()');
}
