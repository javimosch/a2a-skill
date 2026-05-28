
<!-- PRODUCT CHANGELOG — May 2026 — AI-maintained, do not edit manually -->

<div class="product-intro">
  <p class="product-summary">May 2026 was the founding month of a2a-skill. In 10 days the project went from nothing to a production-grade peer messaging framework: a zero-config SQLite bus, a 14-command CLI, five language clients, and over 800 automated tests. Every release this month was a hardening lap or a new capability layered on top of a stable core.</p>
</div>

<section class="product-milestone">
  <div class="milestone-badge">May 18</div>
  <h3>The Bus Launches</h3>
  <p>a2a-skill starts with a single Python file and a clear idea: AI agents should talk to each other directly, without an orchestrator. The initial release ships 14 CLI commands — <code>init</code>, <code>register</code>, <code>send</code>, <code>recv</code>, <code>peek</code>, and more — backed by a WAL-mode SQLite database that handles concurrent writes without a daemon.</p>
  <ul>
    <li>14 commands, zero servers to run</li>
    <li>Per-agent read tracking — each agent sees only its own unread messages</li>
    <li>Message TTL with automatic expiry</li>
    <li>Agent presence tracking (status, PID)</li>
    <li>72 tests on day one</li>
  </ul>
</section>

<section class="product-milestone">
  <div class="milestone-badge">May 19 · v1.1–v1.3</div>
  <h3>Search, Threading, and the Python Client</h3>
  <p>Within hours of the initial release, a2a grows search and threading: agents can now query the bus by keyword, follow conversations by thread ID, and check bus health with <code>a2a stats</code>. A native Python client lands — direct SQLite access, no subprocess overhead.</p>
  <ul>
    <li>Full-text search across all messages (LIKE, later upgraded to FTS5)</li>
    <li>Thread views — see a full back-and-forth conversation in one command</li>
    <li>Bus statistics: agent count, message totals, unread counts</li>
    <li>A2AClient Python library with full method parity to the CLI</li>
  </ul>
</section>

<section class="product-milestone">
  <div class="milestone-badge">May 19 · v1.2</div>
  <h3>Every Language on the Same Bus</h3>
  <p>Go, Node.js, and Rust clients ship the same day. A Go-based REST API server adds 10 HTTP endpoints, making the bus reachable from anything that speaks JSON. Python, Go, JS, and Rust agents can now collaborate in the same team — sharing the same bus file, no protocol translation needed.</p>
  <ul>
    <li>Go client with full API parity</li>
    <li>Node.js client (built-in <code>node:sqlite</code>, Node 22+)</li>
    <li>Rust crate + binary</li>
    <li>REST API server: 10 endpoints, JSON responses</li>
  </ul>
</section>

<section class="product-milestone">
  <div class="milestone-badge">May 19 · v1.3</div>
  <h3>Enterprise-Grade Capabilities</h3>
  <p>The biggest feature release of the month ships six major capabilities in a single version: encryption, full-text search with FTS5, audit logging, message prioritization, smart routing, and async Python clients. Each has its own documentation guide.</p>
  <ul>
    <li><strong>End-to-End Encryption</strong> — Fernet (AES-128) + RSA-2048. Messages encrypted before storage, decrypted on retrieval. Transparent to the agent calling send/recv.</li>
    <li><strong>FTS5 Full-Text Search</strong> — Boolean operators (AND, OR, NOT), phrase queries, prefix matching. LIKE fallback for older SQLite builds.</li>
    <li><strong>Audit Logging</strong> — Complete message lifecycle tracking. GDPR, HIPAA, SOC 2, PCI DSS aligned. Export to compliance reports.</li>
    <li><strong>Priority Queue</strong> — CRITICAL, HIGH, NORMAL, LOW. Incident alerts cut the line; background tasks wait their turn.</li>
    <li><strong>Smart Routing</strong> — Rule-based distribution: Deliver, Forward, Discard, Queue, Escalate. Rules persist across restarts. Async router matches sync API.</li>
    <li><strong>Async Clients</strong> — PriorityClientAsync and RoutingClientAsync. 10× throughput versus sync (1K → 10K msg/sec). aiosqlite backend.</li>
  </ul>
</section>

<section class="product-milestone">
  <div class="milestone-badge">May 19–27 · v1.3.1–v1.3.9</div>
  <h3>Hardening Sprint — WAL, FTS5, Cross-Client Parity</h3>
  <p>After the v1.3 feature push, the team runs a week-long hardening sprint. Every client gets WAL mode enforced on every connection. FTS5 search is fixed to not rebuild on every query. Cross-client parity gaps — missing methods, divergent error messages, validation inconsistencies — are closed one by one. The test suite grows from 95 to 800+ tests.</p>
  <ul>
    <li>WAL mode + busy timeout enforced on all Python, Go, JS, and Rust connections</li>
    <li>FTS5 rebuild-on-every-search bug fixed; LIKE path also corrected for boolean operators</li>
    <li>Go and Rust clients get <code>register()</code> and <code>unregister()</code> (previously absent — send was impossible without them)</li>
    <li><code>a2a-spawn</code> now uses <code>nohup</code> + <code>disown</code> — spawned agents survive parent shell exit</li>
    <li><code>a2a-spawn</code> shell quoting bug fixed — kit prompts now passed via file reference, not inline shell string</li>
    <li>Async client: <code>recv()</code>, <code>recv_by_priority()</code>, <code>recv_above_priority()</code> now mark messages read (were silently re-delivering on every call)</li>
    <li>Routing async: <code>recv_with_routing()</code> SQL column fix (referenced non-existent <code>m.priority</code> column)</li>
    <li>Go client: connection pooling fixed — <code>Wait()</code> was opening a new SQLite connection every 500ms</li>
    <li>Rust client: <code>touch()</code> method added; <code>recv()</code> now reuses connection across poll loop</li>
  </ul>
</section>

<section class="product-milestone">
  <div class="milestone-badge">May 27–28 · v1.3.10–v1.3.17</div>
  <h3>Final Parity Pass — Validation, Stubs, and wait_for_messages</h3>
  <p>The last stretch of May closes the remaining cross-client gaps: type stub files are brought into sync with their implementations, empty message body rejection is standardized across all five clients, and <code>wait_for_messages()</code> is added to Go and Rust to match Python and JS.</p>
  <ul>
    <li><strong>Empty body rejection</strong> — Python, Go, JS, and Rust all refuse to send empty strings. Same error message across all four.</li>
    <li><strong>wait_for_messages()</strong> — Go and Rust gain this method, matching the Python and JS API. Blocks until N unread messages arrive or timeout.</li>
    <li><strong>Type stubs</strong> — <code>a2a_client.pyi</code> and <code>a2a_client_async.pyi</code> had 8 missing public methods. All added. <code>wait_for_messages</code> return type corrected from <code>List</code> to <code>bool</code>.</li>
    <li><strong>Go semantic drift</strong> — 10 behavioral gaps vs Python closed: <code>GetStatus()</code> returns <code>*string</code> (nil for not-found), <code>Recv()</code> partial-read bug fixed, <code>Register()</code> upsert wrapped in transaction, <code>RecvSimple()</code> wait parameter changed from <code>int</code> to <code>float64</code>.</li>
    <li><strong>Async routing limit fix</strong> — <code>recv_with_routing(limit=N)</code> was applying the limit at SQL level, restricting routing decisions. Now fetches all, routes all, truncates per-category after.</li>
  </ul>
</section>
