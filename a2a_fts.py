#!/usr/bin/env python3
"""
a2a Full-Text Search (FTS5) — Advanced message discovery and filtering.

Enables fast full-text search across message bodies, supporting
phrase queries, boolean operators, and ranking.
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional
from pathlib import Path


class FTSClient:
    """Full-text search client for a2a messages."""

    def __init__(self, project: str, agent_id: str):
        """Initialize FTS client.

        Args:
            project: Project name
            agent_id: This agent's ID
        """
        self.project = project
        self.agent_id = agent_id
        self.db_path = Path.home() / ".a2a" / project / "database.db"

    def _connect(self) -> sqlite3.Connection:
        """Connect to database."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def init_fts_table(self) -> bool:
        """Initialize FTS5 virtual table for full-text search.

        Returns:
            True if table created/already exists, False on error
        """
        conn = self._connect()
        try:
            # Create FTS5 virtual table
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    id,
                    sender,
                    recipient,
                    body,
                    thread_id,
                    created_at,
                    content=messages,
                    content_rowid=id
                )
            """
            )

            # Create triggers to keep FTS index in sync
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS messages_fts_insert
                AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, id, sender, recipient, body, thread_id, created_at)
                    VALUES (new.rowid, new.id, new.sender, new.recipient, new.body, new.thread_id, new.created_at);
                END
            """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS messages_fts_delete
                AFTER DELETE ON messages BEGIN
                    DELETE FROM messages_fts WHERE rowid = old.rowid;
                END
            """
            )

            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS messages_fts_update
                AFTER UPDATE ON messages BEGIN
                    DELETE FROM messages_fts WHERE rowid = old.rowid;
                    INSERT INTO messages_fts(rowid, id, sender, recipient, body, thread_id, created_at)
                    VALUES (new.rowid, new.id, new.sender, new.recipient, new.body, new.thread_id, new.created_at);
                END
            """
            )

            conn.commit()
            return True
        except Exception as e:
            print(f"Error initializing FTS: {e}")
            return False
        finally:
            conn.close()

    def search_fts(
        self, query: str, limit: int = 100, rank_by_relevance: bool = True
    ) -> List[Dict[str, Any]]:
        """Full-text search messages using FTS5.

        Supports:
        - Simple queries: "login"
        - Phrase queries: "\"user login\""
        - Boolean: "login AND password" "error OR warning"
        - Prefix: "auth*"
        - Negation: "login -failed"

        Args:
            query: FTS5 query string
            limit: Max results
            rank_by_relevance: Sort by relevance score

        Returns:
            List of matching message dicts
        """
        conn = self._connect()
        try:
            if rank_by_relevance:
                sql = """
                    SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.created_at,
                           rank as relevance_score
                    FROM messages_fts
                    JOIN messages m ON messages_fts.rowid = m.rowid
                    WHERE messages_fts MATCH ?
                    ORDER BY rank
                    LIMIT ?
                """
            else:
                sql = """
                    SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.created_at
                    FROM messages_fts
                    JOIN messages m ON messages_fts.rowid = m.rowid
                    WHERE messages_fts MATCH ?
                    LIMIT ?
                """

            cursor = conn.execute(sql, (query, limit))
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Search error: {e}")
            return []
        finally:
            conn.close()

    def search_advanced(
        self,
        query: str,
        sender: Optional[str] = None,
        recipient: Optional[str] = None,
        thread_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Advanced search with filters.

        Args:
            query: FTS5 query string
            sender: Filter by sender
            recipient: Filter by recipient
            thread_id: Filter by thread
            limit: Max results

        Returns:
            List of matching message dicts
        """
        conn = self._connect()
        try:
            sql = """
                SELECT m.id, m.sender, m.recipient, m.body, m.thread_id, m.created_at,
                       rank as relevance_score
                FROM messages_fts
                JOIN messages m ON messages_fts.rowid = m.rowid
                WHERE messages_fts MATCH ?
            """
            params = [query]

            if sender:
                sql += " AND m.sender = ?"
                params.append(sender)

            if recipient:
                sql += " AND m.recipient = ?"
                params.append(recipient)

            if thread_id:
                sql += " AND m.thread_id = ?"
                params.append(thread_id)

            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            print(f"Advanced search error: {e}")
            return []
        finally:
            conn.close()

    def get_search_suggestions(self, partial_query: str) -> List[str]:
        """Get search suggestions for autocomplete.

        Args:
            partial_query: Partial search term

        Returns:
            List of suggested full terms
        """
        conn = self._connect()
        try:
            # Get unique words in messages that start with partial
            sql = """
                SELECT DISTINCT word
                FROM messages_fts(messages_fts)
                WHERE word LIKE ?
                LIMIT 10
            """
            cursor = conn.execute(sql, (f"{partial_query}%",))
            return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            # Fallback: simple substring search if FTS word list unavailable
            return []
        finally:
            conn.close()

    def rebuild_fts_index(self) -> bool:
        """Rebuild FTS5 index (useful after large data changes).

        Returns:
            True on success, False on error
        """
        conn = self._connect()
        try:
            conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
            conn.commit()
            return True
        except Exception as e:
            print(f"Rebuild error: {e}")
            return False
        finally:
            conn.close()

    def get_search_stats(self) -> Dict[str, Any]:
        """Get FTS index statistics.

        Returns:
            Dict with index stats
        """
        conn = self._connect()
        try:
            # Count indexed messages
            cursor = conn.execute("SELECT COUNT(*) FROM messages_fts")
            indexed_count = cursor.fetchone()[0]

            # Get index size estimate
            cursor = conn.execute("SELECT page_count * page_size FROM pragma_page_count(), pragma_page_size()")
            total_size = cursor.fetchone()[0]

            return {
                "indexed_messages": indexed_count,
                "total_messages": self._get_total_messages(),
                "index_status": "healthy" if indexed_count > 0 else "needs_rebuild",
                "estimated_size_bytes": total_size,
            }
        except Exception as e:
            return {"error": str(e)}
        finally:
            conn.close()

    def _get_total_messages(self) -> int:
        """Get total message count."""
        conn = self._connect()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM messages")
            return cursor.fetchone()[0]
        finally:
            conn.close()


class SearchQueryBuilder:
    """Builder for FTS5 queries."""

    def __init__(self):
        """Initialize query builder."""
        self.terms = []
        self.phrases = []
        self.must_have = []
        self.must_not_have = []

    def add_term(self, term: str) -> "SearchQueryBuilder":
        """Add a search term.

        Args:
            term: Search term

        Returns:
            Self for chaining
        """
        self.terms.append(term)
        return self

    def add_phrase(self, phrase: str) -> "SearchQueryBuilder":
        """Add a phrase (quoted).

        Args:
            phrase: Exact phrase to search

        Returns:
            Self for chaining
        """
        self.phrases.append(f'"{phrase}"')
        return self

    def must_contain(self, term: str) -> "SearchQueryBuilder":
        """Add required term (AND).

        Args:
            term: Required term

        Returns:
            Self for chaining
        """
        self.must_have.append(term)
        return self

    def must_not_contain(self, term: str) -> "SearchQueryBuilder":
        """Add excluded term (NOT).

        Args:
            term: Excluded term

        Returns:
            Self for chaining
        """
        self.must_not_have.append(f"-{term}")
        return self

    def build(self) -> str:
        """Build FTS5 query string.

        Returns:
            FTS5 query string
        """
        parts = self.terms + self.phrases + self.must_have + self.must_not_have
        return " ".join(parts) if parts else "*"

    def __str__(self) -> str:
        """String representation of query."""
        return self.build()
