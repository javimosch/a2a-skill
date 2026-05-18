# a2a v1.4 Architecture & Planning

**Status**: Design Phase  
**Target Date**: Q2 2026  
**Version**: 1.4.0

## Executive Summary

v1.4 adds **high-performance network APIs and observability** to a2a, enabling:
- **gRPC API** for inter-service and cross-instance communication (100x faster than HTTP)
- **WebSocket API** for real-time push notifications
- **Distributed tracing** with Jaeger integration for observability
- **Prometheus metrics** for monitoring and alerting

This enables a2a to move beyond SQLite-local messaging to networked, observable multi-instance deployments.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         a2a v1.4 Stack                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Client Layers                                                   │
│  ├─ Python Client (a2a_client.py)                              │
│  ├─ Python Async Client (a2a_client_async.py)                  │
│  ├─ Go Client (a2a_client.go)         [NEW: gRPC support]      │
│  ├─ Node.js Client (a2a_client.js)    [NEW: WebSocket support] │
│  └─ Rust Client (src/lib.rs)          [NEW: gRPC support]      │
│                                                                   │
│  Transport Layer                                                 │
│  ├─ SQLite (local, v1.3)                                        │
│  ├─ gRPC Streaming (v1.4)         [NEW]                         │
│  ├─ WebSocket (v1.4)              [NEW]                         │
│  └─ HTTP/REST (v1.3)                                            │
│                                                                   │
│  Core Services                                                   │
│  ├─ Messaging Service (gRPC)                                    │
│  ├─ Routing Service (gRPC)                                      │
│  ├─ Priority Service (gRPC)                                     │
│  ├─ Encryption Service (gRPC)                                   │
│  └─ Audit Service (gRPC)                                        │
│                                                                   │
│  Observability Layer                                             │
│  ├─ Jaeger Tracing (distributed tracing)                        │
│  ├─ Prometheus Metrics (monitoring)                             │
│  ├─ Structured Logging (JSON/OpenTelemetry)                     │
│  └─ Health Check API (gRPC health)                              │
│                                                                   │
│  Storage Layer                                                   │
│  ├─ SQLite (local node, v1.3)                                   │
│  ├─ Replication Log (async sync, v1.5)                          │
│  └─ Multi-Instance Consensus (v2.0)                             │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Feature Details

### 1. gRPC API

**Purpose**: High-performance inter-service communication (10-100x faster than REST).

**Services**:

#### MessageService
```protobuf
service MessageService {
  // Send a message with priority, encryption, routing
  rpc Send(SendRequest) returns (SendResponse);
  
  // Receive messages with streaming and backpressure
  rpc Recv(RecvRequest) returns (stream Message);
  
  // Bidirectional streaming for real-time collaboration
  rpc Chat(stream Message) returns (stream Message);
  
  // Search messages with full-text query
  rpc Search(SearchRequest) returns (SearchResponse);
  
  // Get message thread
  rpc GetThread(ThreadRequest) returns (ThreadResponse);
  
  // Mark message as read
  rpc MarkRead(MarkReadRequest) returns (MarkReadResponse);
}
```

#### RoutingService
```protobuf
service RoutingService {
  // Add routing rule
  rpc AddRule(AddRuleRequest) returns (AddRuleResponse);
  
  // Get routing rules
  rpc GetRules(GetRulesRequest) returns (GetRulesResponse);
  
  // Enable/disable rule
  rpc UpdateRule(UpdateRuleRequest) returns (UpdateRuleResponse);
  
  // Delete rule
  rpc DeleteRule(DeleteRuleRequest) returns (DeleteRuleResponse);
  
  // Get routing stats
  rpc GetStats(GetStatsRequest) returns (StatsResponse);
}
```

#### PriorityService
```protobuf
service PriorityService {
  // Get messages by priority
  rpc GetByPriority(PriorityRequest) returns (stream Message);
  
  // Get critical messages
  rpc GetCritical(GetCriticalRequest) returns (stream Message);
  
  // Get priority stats
  rpc GetStats(GetStatsRequest) returns (PriorityStats);
}
```

#### EncryptionService
```protobuf
service EncryptionService {
  // Generate keypair
  rpc GenerateKeypair(GenerateKeypairRequest) returns (KeyPair);
  
  // Encrypt message
  rpc Encrypt(EncryptRequest) returns (EncryptedMessage);
  
  // Decrypt message
  rpc Decrypt(DecryptRequest) returns (DecryptedMessage);
  
  // Exchange public keys
  rpc ExchangeKey(KeyExchangeRequest) returns (KeyExchangeResponse);
}
```

**Performance Target**: 
- Latency: < 5ms p99 (vs 50-100ms for HTTP)
- Throughput: 10,000+ msg/sec per connection
- Memory: < 50MB per service instance

**Implementation**:
- Protocol: gRPC (HTTP/2 multiplexed streams)
- Serialization: Protobuf v3
- Async runtime: tokio (Rust) or asyncio (Python)
- Load balancing: gRPC load balancer or Envoy proxy

---

### 2. WebSocket API

**Purpose**: Real-time push notifications and bidirectional communication from browsers/clients.

**Endpoints**:

```javascript
// Connect to a2a WebSocket
const ws = new WebSocket('wss://a2a.example.com/ws/agent-123');

// Events
ws.onopen = () => {
  // Authenticate and subscribe
  ws.send(JSON.stringify({
    type: 'auth',
    agent_id: 'agent-123',
    token: '<jwt-token>'
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  
  switch(message.type) {
    case 'message':
      console.log('New message:', message.payload);
      break;
    case 'notification':
      console.log('Notification:', message.payload);
      break;
    case 'status':
      console.log('Status update:', message.payload);
      break;
  }
};

ws.onclose = () => {
  console.log('Disconnected, attempting reconnect...');
};
```

**Message Types**:
- `auth` — Authenticate and subscribe to channels
- `subscribe` — Subscribe to message stream, thread, or notifications
- `unsubscribe` — Unsubscribe from channel
- `send` — Send a message through WebSocket
- `ping` — Heartbeat/keepalive
- `message` — Incoming message (server → client)
- `notification` — Priority notification (server → client)
- `status` — Agent/bus status update (server → client)

**Implementation**:
- Protocol: WebSocket (ws:// or wss://)
- Serialization: JSON
- Auth: JWT tokens with agent_id claim
- Server: FastAPI + WebSockets (Python) or actix-web (Rust)
- Backpressure: Sliding window + backoff

---

### 3. Distributed Tracing (Jaeger Integration)

**Purpose**: Understand request flows across multiple services and instances.

**Tracing Points**:
- Client send → routing decision → encryption → storage
- Message receive → decryption → audit → notification
- Search query → FTS evaluation → result assembly
- Cross-instance replication and sync

**Implementation**:
- Library: OpenTelemetry (language-agnostic)
- Exporter: Jaeger UDP/HTTP
- Sampling: Adaptive (higher for errors, lower for success)
- Baggage: agent_id, project, request_id propagated across services

**Example Trace**:
```
Send Message (123.4ms)
├─ Validate (0.2ms)
├─ Encrypt (15.3ms)
│  ├─ Generate nonce (0.1ms)
│  └─ AES-128 encrypt (15.2ms)
├─ Route (1.2ms)
│  ├─ Evaluate rules (0.8ms)
│  └─ Forward decision (0.4ms)
├─ Store (3.1ms)
│  ├─ Insert message (2.8ms)
│  └─ Index FTS (0.3ms)
├─ Notify recipients (102.4ms)
│  ├─ Push via gRPC (50.2ms)
│  └─ Push via WebSocket (52.2ms)
└─ Audit (1.2ms)
```

---

### 4. Prometheus Metrics

**Purpose**: Monitor system health, performance, and load.

**Metrics**:

**Message Metrics**:
```
a2a_messages_sent_total{agent_id, priority, routing_rule} counter
a2a_messages_received_total{agent_id, priority} counter
a2a_messages_encrypted{encryption_type} counter
a2a_message_size_bytes{quantile} histogram
a2a_message_latency_ms{quantile} histogram
```

**Routing Metrics**:
```
a2a_routing_rules_total{agent_id, action} gauge
a2a_routing_matches_total{agent_id, rule_name} counter
a2a_routing_forward_latency_ms{quantile} histogram
```

**Priority Metrics**:
```
a2a_priority_queue_depth{agent_id, priority} gauge
a2a_priority_message_wait_ms{priority, quantile} histogram
```

**System Metrics**:
```
a2a_database_connections{state} gauge
a2a_database_query_ms{operation, quantile} histogram
a2a_grpc_requests_total{service, method, status} counter
a2a_grpc_latency_ms{service, method, quantile} histogram
a2a_websocket_connections_total gauge
a2a_websocket_messages_total counter
```

---

## Deployment Architecture (v1.4+)

### Single-Instance (v1.4)
```
┌──────────────────────────────────────────┐
│         Docker Container                 │
├──────────────────────────────────────────┤
│                                          │
│  ┌──────────────────────────────────┐   │
│  │   gRPC Server (:5000)            │   │
│  │   WebSocket Server (:8000)       │   │
│  │   HTTP/REST Server (:8080)       │   │
│  │   Metrics Endpoint (:9090)       │   │
│  └──────────────────────────────────┘   │
│           │                              │
│           └─→ SQLite DB                  │
│                                          │
└──────────────────────────────────────────┘
     │
     ├─→ Jaeger Agent (:6831)
     └─→ Prometheus Scraper (:9090)
```

### Multi-Instance (v2.0 — vision)
```
┌─────────────────────────────────────────────────────┐
│                  Load Balancer                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────┐  ┌──────────────┐               │
│  │  Instance 1  │  │  Instance 2  │               │
│  │  gRPC :5000  │  │  gRPC :5000  │               │
│  │  WS   :8000  │  │  WS   :8000  │               │
│  └──────────────┘  └──────────────┘               │
│       │                  │                         │
│       │  Replication     │                         │
│       └──────────────────┘                         │
│              │                                     │
│              └─→ Consensus Layer (Raft/Paxos)     │
│                  Shared SQLite (network FS)       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## Implementation Plan

### Phase 1: gRPC Foundation (Week 1-2)
1. Define `.proto` service definitions
2. Generate client/server stubs
3. Implement core MessageService
4. Add Python gRPC server with async/await
5. Update Python client to support gRPC transport
6. Integration tests for gRPC send/recv

**Deliverable**: Functional gRPC messaging (backwards compatible with SQLite)

### Phase 2: WebSocket & Real-Time (Week 3)
1. Implement WebSocket server with JSON protocol
2. Add authentication (JWT + agent_id)
3. Implement subscription model (channels)
4. Push notifications for high-priority messages
5. Web client example (Vue.js or React)
6. Connection pooling and backpressure

**Deliverable**: Real-time browser client + push notifications

### Phase 3: Observability (Week 4)
1. Add OpenTelemetry instrumentation
2. Export to Jaeger
3. Add Prometheus metrics and exporter
4. Create Grafana dashboard
5. Document tracing architecture
6. Performance dashboard

**Deliverable**: Full observability stack (tracing + metrics + visualization)

### Phase 4: Operations & Hardening (Week 5)
1. Docker/Kubernetes manifests
2. Load testing (10K msg/sec)
3. Failover and reconnection logic
4. Circuit breaker patterns
5. Operational runbooks
6. Documentation

**Deliverable**: Production-ready deployment guides

---

## Testing Strategy

### Unit Tests
- gRPC message serialization/deserialization
- Protobuf compatibility
- WebSocket frame parsing
- Metrics collection

### Integration Tests
- gRPC send/recv with encryption
- WebSocket subscription and push
- Cross-transport (SQLite + gRPC)
- Tracing propagation

### Performance Tests
- 10,000 msg/sec throughput
- Latency percentiles (p50, p95, p99)
- Memory under load
- Connection scalability

### Chaos Tests
- Network partition simulation
- Service restart recovery
- Message loss and reordering
- Clock skew handling

---

## Backwards Compatibility

✅ **Fully compatible with v1.3**:
- Existing SQLite clients continue to work
- HTTP/REST API unchanged
- Python/Go/Node/Rust clients updated to support new transports
- Default behavior unchanged (SQLite if no gRPC configured)

**Migration path**:
1. Deploy v1.4 with gRPC disabled (SQLite default)
2. Enable gRPC in staging, validate
3. Optional: Migrate clients to gRPC for better perf
4. No breaking changes — old clients always work

---

## Success Metrics

| Metric | Target | v1.3 | v1.4 Target |
|--------|--------|------|-------------|
| Message Latency (p99) | < 5ms | 15-20ms | < 5ms |
| Throughput | 10K msg/sec | 1K msg/sec | 10K+ msg/sec |
| Max Connections | 1K | 100 | 10K |
| Memory per Service | < 100MB | 50MB | < 100MB |
| Observability | Local logs | Full tracing + metrics |
| Multi-instance | No | Yes (v1.4+) |

---

## Known Design Decisions

1. **gRPC over REST**: HTTP/2 multiplexing + protobuf serialization = 10x faster
2. **WebSocket for browser**: Real-time push impossible with polling; JWT auth for security
3. **Jaeger over custom tracing**: OpenTelemetry standard, vendor-neutral, mature ecosystem
4. **Prometheus for metrics**: Industry standard, integrates with existing monitoring stacks
5. **Async runtime**: tokio/asyncio for non-blocking I/O under high concurrency

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| gRPC complexity | Implementation time | Start with MessageService only, add others later |
| Connection leaks | Memory exhaustion | Implement connection pooling, health checks |
| Backward compat breaks | Production issues | Maintain SQLite + gRPC dual support; gradual rollout |
| Tracing overhead | Performance impact | Adaptive sampling; trace only errors and slow requests |
| WebSocket state management | Reconnection issues | Auto-reconnect with exponential backoff + state replay |

---

## References

- [gRPC Best Practices](https://grpc.io/docs/guides/performance-best-practices/)
- [OpenTelemetry Specification](https://opentelemetry.io/docs/reference/specification/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [Prometheus Client Libraries](https://prometheus.io/docs/instrumenting/clientlibs/)
- [WebSocket Protocol (RFC 6455)](https://tools.ietf.org/html/rfc6455)

---

**Next Step**: Finalize `.proto` definitions and prototype gRPC MessageService.
