#!/usr/bin/env python3
"""
Secure Team Collaboration Agent

Demonstrates v1.3 security and privacy features:
- Asymmetric encryption for team member communication
- Audit logging for compliance
- Message routing for role-based delivery
- Priority-based urgent escalation
"""

import json
import time
from datetime import datetime
from pathlib import Path

from a2a_client import A2AClient
from a2a_crypto import CryptoClient
from a2a_audit import AuditClient, AuditContextManager
from a2a_routing import RoutingClient, RoutingRule, RoutingAction
from a2a_priority import PriorityClient, Priority


class SecureTeamAgent:
    """Agent managing secure team communication with encryption and audit trails."""

    def __init__(self, project: str, agent_id: str, team_members: list):
        """Initialize secure team agent.

        Args:
            project: Project name
            agent_id: This agent's ID
            team_members: List of team member IDs
        """
        self.project = project
        self.agent_id = agent_id
        self.team_members = team_members

        # Initialize components
        self.a2a = A2AClient(project, agent_id)
        self.crypto = CryptoClient(project, agent_id)
        self.audit = AuditClient(project)
        self.routing = RoutingClient(project, agent_id)
        self.priority = PriorityClient(project, agent_id)

    def initialize(self):
        """Initialize agent infrastructure."""
        print(f"[{self.agent_id}] Initializing secure team agent...")

        # Initialize tables
        self.crypto.generate_keypair()  # Generate keypair if not exists
        self.audit.init_audit_table()
        self.routing.init_routing_table()
        self.priority.init_priority_table()

        print(f"[{self.agent_id}] ✓ Encryption ready")
        print(f"[{self.agent_id}] ✓ Audit logging ready")
        print(f"[{self.agent_id}] ✓ Routing ready")
        print(f"[{self.agent_id}] ✓ Priority queue ready")

    def setup_routing_rules(self):
        """Configure routing rules for team roles."""
        print(f"[{self.agent_id}] Setting up routing rules...")

        # Route security alerts to security lead
        self.routing.add_rule(
            RoutingRule(
                name="security_escalate",
                action=RoutingAction.FORWARD,
                match_content="security",
                match_priority=Priority.CRITICAL,
                forward_to="security-lead",
            )
        )

        # Route urgent requests to on-call
        self.routing.add_rule(
            RoutingRule(
                name="oncall_urgent",
                action=RoutingAction.FORWARD,
                match_priority=Priority.CRITICAL,
                forward_to="oncall-engineer",
            )
        )

        # Archive low-priority messages
        self.routing.add_rule(
            RoutingRule(
                name="archive_low_priority",
                action=RoutingAction.QUEUE,
                match_priority=Priority.LOW,
            )
        )

        print(f"[{self.agent_id}] ✓ Routing rules configured")

    def distribute_public_keys(self):
        """Share public key with all team members."""
        print(f"[{self.agent_id}] Distributing public keys to team...")

        public_key = self.crypto.get_public_key()
        if not public_key:
            print(f"[{self.agent_id}] No public key found")
            return

        # Share public key with all team members
        for member in self.team_members:
            message = json.dumps(
                {
                    "type": "public_key_exchange",
                    "from": self.agent_id,
                    "public_key": public_key,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            self.a2a.send(member, message)
            print(f"[{self.agent_id}] Shared public key with {member}")

    def send_encrypted_message(self, recipient: str, content: str, priority: int = Priority.NORMAL):
        """Send encrypted message to team member.

        Args:
            recipient: Recipient agent ID
            content: Message content
            priority: Message priority level
        """
        with AuditContextManager(self.audit, self.agent_id, "send_encrypted") as ctx:
            try:
                # Get recipient's public key
                recipient_public_key = self._get_team_member_public_key(recipient)
                if not recipient_public_key:
                    ctx.details["result"] = "public_key_not_found"
                    raise Exception(f"Public key not found for {recipient}")

                # Wrap message with encryption
                encrypted_message = self.crypto.wrap_encrypted_message(content, recipient_public_key)

                # Send with priority
                msg_id = self.priority.send(
                    recipient, encrypted_message, priority=priority
                )

                ctx.details = {
                    "recipient": recipient,
                    "message_id": msg_id,
                    "priority": priority,
                    "encryption": "asymmetric",
                }

                print(f"[{self.agent_id}] Encrypted message sent to {recipient} (id: {msg_id})")
                return msg_id

            except Exception as e:
                ctx.details["error"] = str(e)
                print(f"[{self.agent_id}] Failed to send encrypted message: {e}")
                raise

    def receive_and_decrypt(self, wait: float = 30):
        """Receive messages and decrypt them.

        Args:
            wait: How long to wait for messages

        Returns:
            List of decrypted messages
        """
        with AuditContextManager(self.audit, self.agent_id, "receive_and_decrypt") as ctx:
            try:
                # Receive priority-ordered messages
                messages = self.priority.recv(wait=wait, priority_aware=True)

                decrypted = []
                for msg in messages:
                    try:
                        # Try to decrypt
                        decrypted_body = self.crypto.decrypt_message(msg["body"])
                        decrypted.append({
                            "id": msg["id"],
                            "sender": msg["sender"],
                            "body": decrypted_body,
                            "priority": msg["priority"],
                            "timestamp": msg["created_at"],
                            "encrypted": True,
                        })
                        print(f"[{self.agent_id}] Decrypted message from {msg['sender']}")
                    except Exception as decrypt_error:
                        # Message wasn't encrypted or decryption failed
                        decrypted.append({
                            "id": msg["id"],
                            "sender": msg["sender"],
                            "body": msg["body"],
                            "priority": msg["priority"],
                            "timestamp": msg["created_at"],
                            "encrypted": False,
                        })
                        print(f"[{self.agent_id}] Received plain message from {msg['sender']}")

                ctx.details = {
                    "messages_received": len(messages),
                    "messages_decrypted": sum(1 for m in decrypted if m["encrypted"]),
                }

                return decrypted

            except Exception as e:
                ctx.details["error"] = str(e)
                print(f"[{self.agent_id}] Error receiving messages: {e}")
                return []

    def handle_routed_messages(self):
        """Process routed messages according to rules."""
        print(f"[{self.agent_id}] Processing routed messages...")

        with AuditContextManager(self.audit, self.agent_id, "route_messages") as ctx:
            try:
                # Get all messages with routing
                routed = self.routing.recv_with_routing(wait=5)

                # Process by action
                for action_name, messages in routed.items():
                    if messages:
                        print(f"[{self.agent_id}] {len(messages)} messages: {action_name}")

                    for item in messages:
                        msg = item["message"]
                        rule = item.get("rule", "default")

                        if action_name == "forward":
                            # Forward to specified agent
                            forward_to = item.get("forward_to")
                            print(
                                f"[{self.agent_id}] Forwarding message to {forward_to} "
                                f"(rule: {rule})"
                            )

                        elif action_name == "deliver":
                            print(f"[{self.agent_id}] Delivering message to inbox (rule: {rule})")

                        elif action_name == "escalate":
                            print(f"[{self.agent_id}] Escalating message (rule: {rule})")

                        elif action_name == "queue":
                            print(f"[{self.agent_id}] Queueing message (rule: {rule})")

                        elif action_name == "discard":
                            print(f"[{self.agent_id}] Discarding message (rule: {rule})")

                # Apply routing decisions
                self.routing.apply_routing(routed)

                ctx.details = {
                    "messages_routed": sum(len(m) for m in routed.values()),
                    "by_action": {action: len(msgs) for action, msgs in routed.items()},
                }

            except Exception as e:
                ctx.details["error"] = str(e)
                print(f"[{self.agent_id}] Error handling routed messages: {e}")

    def export_audit_log(self, filename: str = None):
        """Export audit log for compliance.

        Args:
            filename: Where to save audit log
        """
        if not filename:
            filename = f"audit_export_{self.agent_id}_{int(time.time())}.json"

        print(f"[{self.agent_id}] Exporting audit log to {filename}...")

        # Export last 7 days
        self.audit.export_audit_log(filename, days=7)

        # Show stats
        stats = self.audit.get_audit_stats(days=7)
        print(f"[{self.agent_id}] Audit stats: {stats}")

        return filename

    def _get_team_member_public_key(self, member_id: str) -> str:
        """Get public key for team member.

        In a real implementation, this would be fetched from a key server
        or recovered from previous key exchange messages.

        Args:
            member_id: Team member's agent ID

        Returns:
            Public key or None if not found
        """
        # For now, load from file if it exists
        key_path = Path.home() / ".a2a" / self.project / "keys" / f"{member_id}_public.pem"
        if key_path.exists():
            return key_path.read_text()

        # Otherwise, we'd need to receive it from key exchange
        return None

    def run_team_loop(self, iterations: int = 3):
        """Run main team collaboration loop.

        Args:
            iterations: Number of loop iterations
        """
        print(f"[{self.agent_id}] Starting team collaboration loop...")

        for i in range(iterations):
            print(f"\n=== Iteration {i + 1} ===")

            # Check for messages
            messages = self.receive_and_decrypt(wait=5)
            if messages:
                print(f"[{self.agent_id}] Got {len(messages)} messages")

            # Handle routed messages
            self.handle_routed_messages()

            # Example: Send an update to team
            if i == 0:
                try:
                    self.send_encrypted_message(
                        self.team_members[0] if self.team_members else "team-all",
                        "Team status update: secure agent online",
                        priority=Priority.NORMAL,
                    )
                except Exception as e:
                    print(f"[{self.agent_id}] Could not send update: {e}")

            time.sleep(1)

        # Export audit log before finishing
        self.export_audit_log()
        print(f"\n[{self.agent_id}] Team collaboration loop complete")


if __name__ == "__main__":
    # Example usage
    agent = SecureTeamAgent("secure-team", "alice", ["bob", "charlie", "security-lead"])

    try:
        agent.initialize()
        agent.setup_routing_rules()
        agent.distribute_public_keys()
        agent.run_team_loop(iterations=2)

        print("\n✅ Secure team agent completed successfully")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
