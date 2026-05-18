#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compliance & Archival Agent

Demonstrates v1.3 audit and search features:
- Full-text search for message discovery
- Audit log querying for compliance
- Message archival with retention policies
- Export functionality for external audit
"""

import json
import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

from a2a_fts import FTSClient
from a2a_audit import AuditClient
from a2a_client import A2AClient


class ComplianceArchivalAgent:
    """Agent managing compliance, archival, and retention for messages."""

    def __init__(self, project: str, agent_id: str):
        """Initialize compliance agent.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        self.project = project
        self.agent_id = agent_id

        # Initialize components
        self.a2a = A2AClient(project, agent_id)
        self.fts = FTSClient(project, agent_id)
        self.audit = AuditClient(project)

    def initialize(self):
        """Initialize agent infrastructure."""
        print(f"[{self.agent_id}] Initializing compliance agent...")

        self.fts.init_fts_table()
        self.audit.init_audit_table()

        print(f"[{self.agent_id}] ✓ FTS search ready")
        print(f"[{self.agent_id}] ✓ Audit logging ready")

    def search_messages(self, query: str, limit: int = 100) -> list:
        """Search messages using full-text search.

        Args:
            query: Search query (supports boolean operators, phrases)
            limit: Max results to return

        Returns:
            List of matching messages
        """
        print(f"[{self.agent_id}] Searching for: {query}")

        try:
            results = self.fts.search_fts(query, limit=limit)

            print(f"[{self.agent_id}] Found {len(results)} messages")
            for result in results[:5]:  # Show first 5
                print(f"  - {result['id']}: {result['sender']} → {result['body'][:50]}...")

            return results

        except Exception as e:
            print(f"[{self.agent_id}] Search error: {e}")
            return []

    def search_by_sender(self, sender: str, limit: int = 100) -> list:
        """Find all messages from a specific sender.

        Args:
            sender: Sender agent ID
            limit: Max results

        Returns:
            List of messages from sender
        """
        query = f"sender:{sender}"
        print(f"[{self.agent_id}] Searching messages from {sender}...")

        return self.search_messages(query, limit=limit)

    def search_by_date_range(self, start_date: datetime, end_date: datetime) -> list:
        """Find messages within a date range.

        Args:
            start_date: Start of range
            end_date: End of range

        Returns:
            List of messages in range
        """
        print(f"[{self.agent_id}] Searching for messages from {start_date} to {end_date}...")

        # Query database directly for date range (FTS doesn't support dates well)
        db_path = Path.home() / ".a2a" / self.project / "database.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        try:
            start_ts = start_date.timestamp()
            end_ts = end_date.timestamp()

            cursor = conn.execute(
                """
                SELECT id, sender, recipient, body, created_at
                FROM messages
                WHERE created_at >= ? AND created_at <= ?
                ORDER BY created_at DESC
            """,
                (start_ts, end_ts),
            )

            results = [dict(row) for row in cursor.fetchall()]
            print(f"[{self.agent_id}] Found {len(results)} messages in date range")

            return results

        finally:
            conn.close()

    def get_audit_trail(self, agent_id: str, days: int = 30) -> dict:
        """Get audit trail for specific agent.

        Args:
            agent_id: Agent to audit
            days: Number of days to include

        Returns:
            Audit trail data
        """
        print(f"[{self.agent_id}] Generating audit trail for {agent_id} (last {days} days)...")

        trail = self.audit.get_agent_audit_trail(agent_id, days=days)

        print(f"[{self.agent_id}] Audit trail retrieved:")
        print(f"  Operations: {len(trail.get('operations', []))}")
        if trail.get('operations'):
            print(f"  Date range: {trail['operations'][0]['timestamp']} to "
                  f"{trail['operations'][-1]['timestamp']}")

        return trail

    def get_audit_statistics(self, days: int = 30) -> dict:
        """Get audit statistics for compliance reporting.

        Args:
            days: Number of days to analyze

        Returns:
            Statistics dict
        """
        print(f"[{self.agent_id}] Analyzing audit statistics (last {days} days)...")

        stats = self.audit.get_audit_stats(days=days)

        print(f"[{self.agent_id}] Audit statistics:")
        print(f"  Total operations: {stats.get('total_operations', 0)}")
        print(f"  Successful: {stats.get('successful_operations', 0)}")
        print(f"  Failed: {stats.get('failed_operations', 0)}")

        if "by_operation" in stats:
            print(f"  By operation type:")
            for op_type, count in stats["by_operation"].items():
                print(f"    - {op_type}: {count}")

        if "by_agent" in stats:
            print(f"  By agent (top 5):")
            sorted_agents = sorted(
                stats["by_agent"].items(), key=lambda x: x[1], reverse=True
            )
            for agent, count in sorted_agents[:5]:
                print(f"    - {agent}: {count}")

        return stats

    def archive_messages(self, days_old: int = 90, dry_run: bool = True) -> int:
        """Archive messages older than specified days.

        Args:
            days_old: Archive messages older than this many days
            dry_run: If True, don't actually delete, just report

        Returns:
            Number of messages archived
        """
        cutoff_time = time.time() - (days_old * 86400)

        print(f"[{self.agent_id}] Archiving messages older than {days_old} days...")
        print(f"[{self.agent_id}] Cutoff time: {datetime.fromtimestamp(cutoff_time)}")

        db_path = Path.home() / ".a2a" / self.project / "database.db"
        conn = sqlite3.connect(str(db_path))

        try:
            # Count messages to archive
            cursor = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE created_at < ?", (cutoff_time,)
            )
            count = cursor.fetchone()[0]

            print(f"[{self.agent_id}] Found {count} messages to archive")

            if not dry_run and count > 0:
                # Export to JSON before deleting
                cursor = conn.execute(
                    "SELECT * FROM messages WHERE created_at < ?", (cutoff_time,)
                )
                messages = [
                    dict(zip([col[0] for col in cursor.description], row))
                    for row in cursor.fetchall()
                ]

                # Save archive
                archive_file = f"archive_{int(time.time())}.json.gz"
                print(f"[{self.agent_id}] Saving to {archive_file}...")

                import gzip
                with gzip.open(archive_file, "wt") as f:
                    json.dump(messages, f, indent=2, default=str)

                # Delete from database
                cursor = conn.execute("DELETE FROM messages WHERE created_at < ?", (cutoff_time,))
                conn.commit()
                print(f"[{self.agent_id}] Archived and deleted {cursor.rowcount} messages")

                return cursor.rowcount

            return count

        finally:
            conn.close()

    def export_audit_log(self, filename: str = None) -> str:
        """Export audit log for external auditors.

        Args:
            filename: Output filename

        Returns:
            Path to exported file
        """
        if not filename:
            filename = f"audit_export_{int(time.time())}.json"

        print(f"[{self.agent_id}] Exporting audit log to {filename}...")

        # Export last 90 days
        self.audit.export_audit_log(filename, days=90)

        # Get file size
        file_size = Path(filename).stat().st_size
        print(f"[{self.agent_id}] Exported {file_size} bytes to {filename}")

        return filename

    def generate_compliance_report(self, output_file: str = None) -> str:
        """Generate comprehensive compliance report.

        Args:
            output_file: Where to save report

        Returns:
            Path to report file
        """
        if not output_file:
            output_file = f"compliance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        print(f"[{self.agent_id}] Generating compliance report...")

        report = {
            "generated_at": datetime.now().isoformat(),
            "report_period_days": 90,
            "audit_stats": self.get_audit_statistics(days=90),
            "message_counts": self._get_message_counts(),
            "archival_status": {
                "total_archived": self._count_archived_messages(),
            },
        }

        # Save report
        with open(output_file, "w") as f:
            json.dump(report, f, indent=2, default=str)

        print(f"[{self.agent_id}] Compliance report saved to {output_file}")
        return output_file

    def verify_message_integrity(self) -> dict:
        """Verify message database integrity.

        Returns:
            Integrity check results
        """
        print(f"[{self.agent_id}] Verifying message database integrity...")

        db_path = Path.home() / ".a2a" / self.project / "database.db"
        conn = sqlite3.connect(str(db_path))

        try:
            # Run integrity check
            cursor = conn.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]

            if result == "ok":
                print(f"[{self.agent_id}] ✅ Database integrity check passed")
            else:
                print(f"[{self.agent_id}] ❌ Database integrity check failed: {result}")

            # Count tables
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
            tables = [row[0] for row in cursor.fetchall()]

            # Count rows in each table
            counts = {}
            for table in tables:
                cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                counts[table] = cursor.fetchone()[0]

            print(f"[{self.agent_id}] Table row counts: {counts}")

            return {
                "status": "ok" if result == "ok" else "failed",
                "integrity_check": result,
                "table_counts": counts,
            }

        finally:
            conn.close()

    def _get_message_counts(self) -> dict:
        """Get message statistics."""
        db_path = Path.home() / ".a2a" / self.project / "database.db"
        conn = sqlite3.connect(str(db_path))

        try:
            cursor = conn.execute("SELECT COUNT(*) FROM messages")
            total = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(DISTINCT sender) FROM messages")
            senders = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(DISTINCT recipient) FROM messages")
            recipients = cursor.fetchone()[0]

            return {
                "total_messages": total,
                "unique_senders": senders,
                "unique_recipients": recipients,
            }

        finally:
            conn.close()

    def _count_archived_messages(self) -> int:
        """Count archived messages (for report)."""
        db_path = Path.home() / ".a2a" / self.project / "database.db"
        conn = sqlite3.connect(str(db_path))

        try:
            # Count messages older than 90 days
            cutoff = time.time() - (90 * 86400)
            cursor = conn.execute("SELECT COUNT(*) FROM messages WHERE created_at < ?", (cutoff,))
            return cursor.fetchone()[0]

        finally:
            conn.close()

    def run_compliance_loop(self, iterations: int = 1):
        """Run compliance and archival loop.

        Args:
            iterations: Number of loop iterations
        """
        print(f"[{self.agent_id}] Starting compliance loop...\n")

        for i in range(iterations):
            print(f"=== Iteration {i + 1} ===\n")

            # Search examples
            self.search_messages("error OR warning", limit=10)
            print()

            # Audit statistics
            self.get_audit_statistics(days=30)
            print()

            # Verify integrity
            self.verify_message_integrity()
            print()

            # Dry run archival
            self.archive_messages(days_old=90, dry_run=True)
            print()

        # Generate final report
        self.generate_compliance_report()
        print(f"\n[{self.agent_id}] Compliance loop complete")


if __name__ == "__main__":
    # Example usage
    agent = ComplianceArchivalAgent("compliance-team", "compliance-agent")

    try:
        agent.initialize()
        agent.run_compliance_loop(iterations=1)

        print("\n✅ Compliance agent completed successfully")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        raise
