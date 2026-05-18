#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
v1.3 Integrated Agent Example

Demonstrates all v1.3 features working together:
- Message encryption (send/receive encrypted messages)
- Full-text search (find specific messages)
- Audit logging (track all operations)
- Message prioritization (queue by priority)
- Message routing (auto-distribute by rules)
"""

import asyncio
import time
import json
from datetime import datetime

from a2a_client_async import A2AClientAsync
from a2a_crypto import CryptoClient
from a2a_fts import FTSClient
from a2a_audit import AuditClient
from a2a_priority import PriorityClient, Priority
from a2a_routing import RoutingClient, RoutingRule, RoutingAction


async def setup_encryption(project: str, agent_id: str) -> CryptoClient:
    """Initialize encryption for this agent."""
    crypto = CryptoClient(project, agent_id)
    # Generate keypair if not exists
    if not crypto.public_key_path.exists():
        crypto.generate_keypair()
    return crypto


async def setup_audit(project: str) -> AuditClient:
    """Initialize audit logging."""
    audit = AuditClient(project)
    audit.init_audit_table()
    return audit


async def setup_fts(project: str, agent_id: str) -> FTSClient:
    """Initialize full-text search."""
    fts = FTSClient(project, agent_id)
    fts.init_fts_table()
    return fts


async def setup_priority(project: str, agent_id: str) -> PriorityClient:
    """Initialize message prioritization."""
    priority_client = PriorityClient(project, agent_id)
    priority_client.init_priority_table()
    return priority_client


async def setup_routing(project: str, agent_id: str) -> RoutingClient:
    """Initialize message routing."""
    routing_client = RoutingClient(project, agent_id)
    routing_client.init_routing_table()
    return routing_client


class V13IntegratedAgent:
    """Agent demonstrating all v1.3 features."""

    def __init__(self, project: str, agent_id: str):
        """Initialize integrated agent."""
        self.project = project
        self.agent_id = agent_id

    async def initialize(self):
        """Initialize all v1.3 components."""
        print(f"[{self.agent_id}] Initializing v1.3 components...")

        # Core messaging
        self.a2a = A2AClientAsync(self.project, self.agent_id)
        await self.a2a.__aenter__()

        # Features
        self.crypto = await setup_encryption(self.project, self.agent_id)
        self.audit = await setup_audit(self.project)
        self.fts = await setup_fts(self.project, self.agent_id)
        self.priority = await setup_priority(self.project, self.agent_id)
        self.routing = await setup_routing(self.project, self.agent_id)

        print(f"[{self.agent_id}] ✓ Encryption ready")
        print(f"[{self.agent_id}] ✓ Audit logging ready")
        print(f"[{self.agent_id}] ✓ Full-text search ready")
        print(f"[{self.agent_id}] ✓ Priority queue ready")
        print(f"[{self.agent_id}] ✓ Routing rules ready")

    async def setup_routing_rules(self):
        """Configure routing rules for this agent."""
        print(f"[{self.agent_id}] Setting up routing rules...")

        # Critical alerts to escalate
        self.routing.add_rule(
            RoutingRule(
                name="escalate_critical",
                action=RoutingAction.ESCALATE,
                match_priority=Priority.CRITICAL,
            )
        )

        # Database issues to queue
        self.routing.add_rule(
            RoutingRule(
                name="database_queue",
                action=RoutingAction.QUEUE,
                match_content="database|sql|connection",
            )
        )

        # Low priority to discard
        self.routing.add_rule(
            RoutingRule(
                name="discard_low",
                action=RoutingAction.DISCARD,
                match_priority=Priority.LOW,
            )
        )

        print(f"[{self.agent_id}] ✓ {len(self.routing.get_rules())} routing rules configured")

    async def send_secure_message(self, recipient: str, message: str, priority: int = Priority.NORMAL):
        """Send encrypted message with priority."""
        # Log operation
        with self.audit.log_operation(
            agent_id=self.agent_id,
            operation="encrypt",
            details={"recipient": recipient},
        ):
            pass

        # Get recipient's public key (in real scenario, would fetch from message)
        recipient_crypto = CryptoClient(self.project, recipient)
        recipient_public = recipient_crypto.get_public_key()

        # Encrypt message
        encrypted = self.crypto.wrap_encrypted_message(message, recipient_public)

        # Send with priority
        msg_id = self.priority.send(recipient, encrypted, priority=priority)

        # Log send
        self.audit.log_operation(
            agent_id=self.agent_id,
            operation="send",
            message_id=msg_id,
            details={"priority": priority, "encrypted": True},
        )

        print(f"[{self.agent_id}] → {recipient}: {message[:40]}... (priority={priority})")
        return msg_id

    async def receive_and_process(self):
        """Receive messages with routing and decryption."""
        print(f"[{self.agent_id}] Waiting for messages...")

        # Receive with routing (groups by action)
        routed = self.routing.recv_with_routing(wait=5, limit=10)

        print(f"[{self.agent_id}] Received: {sum(len(v) for v in routed.values())} messages")
        print(f"[{self.agent_id}]   - Deliver: {len(routed['deliver'])}")
        print(f"[{self.agent_id}]   - Forward: {len(routed['forward'])}")
        print(f"[{self.agent_id}]   - Queue: {len(routed['queue'])}")
        print(f"[{self.agent_id}]   - Escalate: {len(routed['escalate'])}")

        # Process delivered messages
        for item in routed["deliver"]:
            msg = item["message"]
            rule = item.get("rule", "no_rule")

            # Try to decrypt if encrypted
            body = msg["body"]
            is_encrypted = False
            try:
                decrypted = self.crypto.unwrap_encrypted_message(body, self.crypto)
                if decrypted:
                    body = decrypted
                    is_encrypted = True
                    self.audit.log_operation(
                        agent_id=self.agent_id,
                        operation="decrypt",
                        message_id=msg["id"],
                        result="success",
                    )
            except Exception:
                pass

            # Display message
            priority_name = Priority(msg.get("priority", Priority.NORMAL)).name
            encryption_tag = "[encrypted] " if is_encrypted else ""
            print(
                f"  • {msg['sender']}: {encryption_tag}{body[:50]}... "
                f"(priority={priority_name}, rule={rule})"
            )

            # Mark as read
            self.priority.mark_read(msg["id"])
            self.audit.log_operation(
                agent_id=self.agent_id,
                operation="read",
                message_id=msg["id"],
            )

        # Apply routing (forward, discard)
        self.routing.apply_routing(routed)

    async def search_messages(self, query: str):
        """Full-text search messages."""
        print(f"[{self.agent_id}] Searching for: {query}")

        results = self.fts.search_fts(query, limit=5)
        print(f"[{self.agent_id}] Found {len(results)} results")

        for result in results:
            relevance = result.get("relevance_score", "N/A")
            print(f"  • {result['sender']}: {result['body'][:40]}... (relevance={relevance})")

            # Log search operation
            self.audit.log_operation(
                agent_id=self.agent_id,
                operation="search",
                message_id=result["id"],
                details={"query": query},
            )

    async def print_statistics(self):
        """Print all collected statistics."""
        print(f"\n[{self.agent_id}] === STATISTICS ===")

        # Priority stats
        priority_stats = self.priority.get_priority_stats()
        print(f"Priority distribution: {priority_stats}")

        # Routing stats
        routing_stats = self.routing.get_routing_stats()
        print(f"Routing rules: {routing_stats['total_rules']} total, {routing_stats['enabled_rules']} enabled")

        # Audit stats
        audit_stats = self.audit.get_audit_stats(days=1)
        print(f"Audit operations: {audit_stats['total_operations']} total")
        print(f"  Operations by type: {audit_stats['operations_by_type']}")

        # FTS stats
        fts_stats = self.fts.get_search_stats()
        print(f"FTS index: {fts_stats['indexed_messages']} messages indexed")

    async def cleanup(self):
        """Cleanup resources."""
        if hasattr(self, "a2a"):
            await self.a2a.__aexit__(None, None, None)
        print(f"[{self.agent_id}] Cleanup complete")


async def demo_alice(project: str):
    """Alice: Sender with encryption and priorities."""
    alice = V13IntegratedAgent(project, "alice")
    await alice.initialize()
    await alice.setup_routing_rules()

    # Get Bob's public key (Bob generates it first)
    await asyncio.sleep(1)

    # Send messages with different priorities
    await alice.send_secure_message("bob", "System outage detected!", priority=Priority.CRITICAL)
    await asyncio.sleep(0.5)

    await alice.send_secure_message("bob", "High priority task", priority=Priority.HIGH)
    await asyncio.sleep(0.5)

    await alice.send_secure_message("bob", "Regular message", priority=Priority.NORMAL)
    await asyncio.sleep(0.5)

    await alice.send_secure_message("bob", "FYI: documentation updated", priority=Priority.LOW)

    # Search for messages
    await asyncio.sleep(1)
    await alice.search_messages("task")

    # Print stats
    await alice.print_statistics()

    await alice.cleanup()


async def demo_bob(project: str):
    """Bob: Receiver with routing and audit."""
    bob = V13IntegratedAgent(project, "bob")
    await bob.initialize()
    await bob.setup_routing_rules()

    # Receive and process messages
    await asyncio.sleep(2)
    await bob.receive_and_process()

    # Search for critical messages
    await bob.search_messages("outage")

    # Print stats
    await bob.print_statistics()

    await bob.cleanup()


async def main():
    """Run integrated demo."""
    project = "v13-demo"

    print("=" * 60)
    print("a2a v1.3 Integrated Agent Demo")
    print("=" * 60)
    print()

    # Run agents concurrently
    alice_task = asyncio.create_task(demo_alice(project))
    bob_task = asyncio.create_task(demo_bob(project))

    await asyncio.gather(alice_task, bob_task)

    print()
    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
