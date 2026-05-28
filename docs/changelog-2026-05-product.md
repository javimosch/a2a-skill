
        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-blue-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">🔐</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">End-to-End Encryption</h3>
              <p class="text-slate-400 leading-relaxed">Added message encryption module for secure agent communications. Messages are encrypted before storage and decrypted on retrieval, ensuring privacy in multi-agent environments.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-emerald-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">🔍</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Full-Text Search (FTS5)</h3>
              <p class="text-slate-400 leading-relaxed">Implemented SQLite FTS5 full-text search for advanced message discovery. Search across message bodies with LIKE fallback for broader compatibility. Added regression tests for FTS5 rebuild behavior.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-purple-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">⚡</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Message Prioritization</h3>
              <p class="text-slate-400 leading-relaxed">Added 4-level priority queue system (Critical, High, Medium, Low) for ordered message processing. Includes both sync and async client implementations for high-concurrency scenarios.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-amber-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">🔀</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Rule-Based Routing</h3>
              <p class="text-slate-400 leading-relaxed">Implemented message routing with rule-based distribution. Define custom routing rules to automatically direct messages to specific agents based on content patterns, sender roles, or other criteria.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-red-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">�</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Audit Logging</h3>
              <p class="text-slate-400 leading-relaxed">Added comprehensive audit logging for message lifecycle tracking. Track message creation, delivery, reads, and modifications with context managers for automatic audit scope management.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-slate-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">🌐</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Multi-Language Client Libraries</h3>
              <p class="text-slate-400 leading-relaxed">Expanded language support with Go, Node.js, and Rust client libraries. All clients now include proper WAL mode initialization and directory creation guards for reliable concurrent access.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-green-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">�</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Git-Aware Coordination</h3>
              <p class="text-slate-400 leading-relaxed">Added git-state-aware bus queries to prevent work collisions. Agents can check git branch, commit, and status to coordinate work and avoid duplicate effort across multiple agent sessions.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-orange-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">🐳</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Docker Deployment</h3>
              <p class="text-slate-400 leading-relaxed">Added multi-stage Docker build and docker-compose deployment support. Includes comprehensive deployment guide with production-ready configuration examples.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-pink-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">�</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">WAL Mode Hardening</h3>
              <p class="text-slate-400 leading-relaxed">Fixed WAL invariant gaps across all language clients (Python sync/async, Go, Rust, Node.js). All database connections now properly set WAL journal mode and busy timeout for reliable concurrent writes.</p>
            </div>
          </div>
        </div>

        <div class="feature-card rounded-xl p-6">
          <div class="flex items-start gap-4">
            <div class="w-12 h-12 rounded-lg bg-cyan-500/10 flex items-center justify-center flex-shrink-0">
              <span class="text-2xl">📚</span>
            </div>
            <div>
              <h3 class="text-xl font-semibold text-white mb-2">Comprehensive Documentation</h3>
              <p class="text-slate-400 leading-relaxed">Added 20+ new documentation files covering v1.3 features, security hardening, troubleshooting, deployment, and integration guides. Reorganized docs/ directory with clear ownership rules.</p>
            </div>
          </div>
        </div>