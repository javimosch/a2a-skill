#!/usr/bin/env python3
"""
a2a Audit Logging — Message lifecycle tracking for compliance and debugging (v1.3).

Tracks all message operations: created, sent, received, read, encrypted, decrypted.
Supports querying audit logs by agent, time range, message type, operation.
"""

import sqlite3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path


class AuditClient:
    """Audit logging client for message operations."""

    def __init__(self, project: str):
        """Initialize audit client.

        Args:
            project: Project name
        """
        self.project = project
        self.db_path = Path.home() / ".a2a" / project / "database.db"

    def _connect(self) -> sqlite3.Connection:
        """Connect to database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def init_audit_table(self) -> bool:
        """Initialize audit log table.

        Returns:
            True if successful, False on error
        """
        conn = self._connect()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    agent_id TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    message_id INTEGER,
                    details TEXT,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create indexes for common queries
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_agent ON audit_log(agent_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_operation ON audit_log(operation)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_message ON audit_log(message_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_log(timestamp)"
            )

            conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing audit table: {e}")
            return False
        finally:
            conn.close()

    def log_operation(
        self,
        agent_id: str,
        operation: str,
        message_id: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        result: str = "success",
    ) -> bool:
        """Log a message operation.

        Args:
            agent_id: Agent performing operation
            operation: Operation name (send, recv, read, encrypt, decrypt, etc.)
            message_id: Associated message ID
            details: Additional details dict
            result: Result status (success, failure, etc.)

        Returns:
            True if logged successfully
        """
        conn = self._connect()
        try:
            details_json = json.dumps(details) if details else None
            conn.execute(
                """
                INSERT INTO audit_log (timestamp, agent_id, operation, message_id, details, result)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().timestamp(),
                    agent_id,
                    operation,
                    message_id,
                    details_json,
                    result,
                ),
            )
            conn.commit()
            return True
        except Exception as e:
            print(f"Error logging operation: {e}")
            return False
        finally:
            conn.close()

    def get_agent_audit_trail(
        self, agent_id: str, limit: int = 100, days: int = 7
    ) -> List[Dict[str, Any]]:
        """Get audit trail for specific agent.

        Args:
            agent_id: Agent to audit
            limit: Max results
            days: Look back N days

        Returns:
            List of audit log entries
        """
        conn = self._connect()
        try:
            cutoff_time = (
                datetime.now() - timedelta(days=days)
            ).timestamp()

            cursor = conn.execute(
                """
                SELECT id, timestamp, agent_id, operation, message_id, details, result
                FROM audit_log
                WHERE agent_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (agent_id, cutoff_time, limit),
            )

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_message_audit_trail(self, message_id: int) -> List[Dict[str, Any]]:
        """Get complete audit trail for specific message.

        Args:
            message_id: Message to audit

        Returns:
            List of audit log entries for message
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT id, timestamp, agent_id, operation, message_id, details, result
                FROM audit_log
                WHERE message_id = ?
                ORDER BY timestamp ASC
            """,
                (message_id,),
            )

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def search_audit_logs(
        self,
        operation: Optional[str] = None,
        agent_id: Optional[str] = None,
        result: Optional[str] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search audit logs with filters.

        Args:
            operation: Filter by operation type
            agent_id: Filter by agent
            result: Filter by result status
            start_time: Filter from timestamp
            end_time: Filter to timestamp
            limit: Max results

        Returns:
            List of matching audit log entries
        """
        conn = self._connect()
        try:
            query = "SELECT id, timestamp, agent_id, operation, message_id, details, result FROM audit_log WHERE 1=1"
            params = []

            if operation:
                query += " AND operation = ?"
                params.append(operation)

            if agent_id:
                query += " AND agent_id = ?"
                params.append(agent_id)

            if result:
                query += " AND result = ?"
                params.append(result)

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_audit_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get audit statistics.

        Args:
            days: Look back N days

        Returns:
            Dict with audit statistics
        """
        conn = self._connect()
        try:
            cutoff_time = (
                datetime.now() - timedelta(days=days)
            ).timestamp()

            # Total operations
            cursor = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE timestamp >= ?",
                (cutoff_time,),
            )
            total_ops = cursor.fetchone()[0]

            # Operations by type
            cursor = conn.execute(
                """
                SELECT operation, COUNT(*) as count
                FROM audit_log
                WHERE timestamp >= ?
                GROUP BY operation
                ORDER BY count DESC
            """,
                (cutoff_time,),
            )
            ops_by_type = {row[0]: row[1] for row in cursor.fetchall()}

            # Operations by agent
            cursor = conn.execute(
                """
                SELECT agent_id, COUNT(*) as count
                FROM audit_log
                WHERE timestamp >= ?
                GROUP BY agent_id
                ORDER BY count DESC
            """,
                (cutoff_time,),
            )
            ops_by_agent = {row[0]: row[1] for row in cursor.fetchall()}

            # Success/failure ratio
            cursor = conn.execute(
                """
                SELECT result, COUNT(*) as count
                FROM audit_log
                WHERE timestamp >= ?
                GROUP BY result
            """,
                (cutoff_time,),
            )
            results = {row[0]: row[1] for row in cursor.fetchall()}

            return {
                "period_days": days,
                "total_operations": total_ops,
                "operations_by_type": ops_by_type,
                "operations_by_agent": ops_by_agent,
                "result_summary": results,
            }
        finally:
            conn.close()

    def export_audit_log(
        self, filepath: str, start_time: Optional[float] = None, end_time: Optional[float] = None
    ) -> bool:
        """Export audit log to JSON file for external analysis.

        Args:
            filepath: Path to export to
            start_time: Filter from timestamp
            end_time: Filter to timestamp

        Returns:
            True if exported successfully
        """
        conn = self._connect()
        try:
            query = "SELECT id, timestamp, agent_id, operation, message_id, details, result FROM audit_log WHERE 1=1"
            params = []

            if start_time:
                query += " AND timestamp >= ?"
                params.append(start_time)

            if end_time:
                query += " AND timestamp <= ?"
                params.append(end_time)

            query += " ORDER BY timestamp ASC"

            cursor = conn.execute(query, params)
            logs = [dict(row) for row in cursor.fetchall()]

            with open(filepath, "w") as f:
                json.dump(logs, f, indent=2, default=str)

            return True
        except Exception as e:
            print(f"Error exporting audit log: {e}")
            return False
        finally:
            conn.close()

    def cleanup_old_logs(self, days: int = 90) -> int:
        """Delete audit logs older than N days.

        Args:
            days: Delete logs older than this many days

        Returns:
            Number of rows deleted
        """
        conn = self._connect()
        try:
            cutoff_time = (
                datetime.now() - timedelta(days=days)
            ).timestamp()

            cursor = conn.execute(
                "DELETE FROM audit_log WHERE timestamp < ?",
                (cutoff_time,),
            )
            conn.commit()

            return cursor.rowcount
        finally:
            conn.close()


class AuditContextManager:
    """Context manager for automatic audit logging of operations."""

    def __init__(self, audit_client: AuditClient, agent_id: str, operation: str):
        """Initialize audit context.

        Args:
            audit_client: AuditClient instance
            agent_id: Agent performing operation
            operation: Operation name
        """
        self.audit_client = audit_client
        self.agent_id = agent_id
        self.operation = operation
        self.message_id = None
        self.details = {}

    def __enter__(self):
        """Enter context."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and log operation."""
        result = "failure" if exc_type else "success"
        details = self.details.copy()

        if exc_type:
            details["error"] = str(exc_val)

        self.audit_client.log_operation(
            self.agent_id,
            self.operation,
            self.message_id,
            details,
            result,
        )

        return False  # Don't suppress exceptions
