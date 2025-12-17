"""
Conversation database management for Orac.
Handles SQLite storage of conversation history.
"""

import os
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager
from loguru import logger
import uuid


class ConversationDB:
    """Manages conversation storage using SQLite."""

    def __init__(self, db_path: Optional[str] = None):
        """Initialize the conversation database.

        Args:
            db_path: Path to SQLite database file. If None, uses default location.
        """
        if db_path is None:
            # Default to ~/.orac/conversations.db
            orac_dir = Path.home() / ".orac"
            orac_dir.mkdir(exist_ok=True)
            db_path = str(orac_dir / "conversations.db")
        else:
            # Ensure parent directory exists for provided path
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        self.db_path = db_path
        self._init_database()
        logger.debug(f"Initialized conversation database at: {db_path}")

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_database(self):
        """Create tables if they don't exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    prompt_name TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id)
                )
            """)

            # Create indices for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, timestamp)
            """)

    def create_conversation(self, conversation_id: Optional[str] = None,
                          prompt_name: str = "unknown",
                          metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new conversation.

        Args:
            conversation_id: Unique ID for the conversation. Auto-generated if None.
            prompt_name: Name of the prompt being used.
            metadata: Optional metadata to store with the conversation.

        Returns:
            The conversation ID.
        """
        if conversation_id is None:
            conversation_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO conversations (id, prompt_name, metadata, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (conversation_id, prompt_name, json.dumps(metadata or {})))

        logger.debug(f"Created conversation: {conversation_id}")
        return conversation_id

    def add_message(self, conversation_id: str, role: str, content: str):
        """Add a message to a conversation.

        Args:
            conversation_id: The conversation to add to.
            role: Message role ('user' or 'assistant').
            content: Message content.
        """
        with self._get_connection() as conn:
            conn.execute("""
                INSERT INTO messages (conversation_id, role, content)
                VALUES (?, ?, ?)
            """, (conversation_id, role, content))

            conn.execute("""
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (conversation_id,))

        logger.debug(f"Added {role} message to conversation {conversation_id}")

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get messages for a conversation.

        Args:
            conversation_id: The conversation to retrieve.
            limit: Maximum number of recent messages to return.

        Returns:
            List of messages with role and content.
        """
        with self._get_connection() as conn:
            query = """
                SELECT role, content, timestamp
                FROM messages
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """

            if limit:
                # Get the most recent messages
                query = f"""
                    SELECT role, content, timestamp FROM (
                        SELECT role, content, timestamp
                        FROM messages
                        WHERE conversation_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    ) ORDER BY timestamp ASC
                """
                cursor = conn.execute(query, (conversation_id, limit))
            else:
                cursor = conn.execute(query, (conversation_id,))

            messages = []
            for row in cursor:
                messages.append({
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"]
                })

            return messages

    def delete_conversation(self, conversation_id: str):
        """Delete a conversation and all its messages.

        Args:
            conversation_id: The conversation to delete.
        """
        with self._get_connection() as conn:
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conversation_id,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))

        logger.debug(f"Deleted conversation: {conversation_id}")

    def list_conversations(self) -> List[Dict[str, Any]]:
        """List all conversations.

        Returns:
            List of conversation metadata.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT c.id, c.prompt_name, c.created_at, c.updated_at,
                       COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                GROUP BY c.id
                ORDER BY c.updated_at DESC
            """)

            conversations = []
            for row in cursor:
                conversations.append({
                    "id": row["id"],
                    "prompt_name": row["prompt_name"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "message_count": row["message_count"]
                })

            return conversations

    def conversation_exists(self, conversation_id: str) -> bool:
        """Check if a conversation exists.

        Args:
            conversation_id: The conversation ID to check.

        Returns:
            True if the conversation exists.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT 1 FROM conversations WHERE id = ? LIMIT 1",
                (conversation_id,)
            )
            return cursor.fetchone() is not None

    def get_conversation(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific conversation by ID.

        Args:
            conversation_id: The conversation ID to retrieve.

        Returns:
            Conversation metadata dict, or None if not found.
        """
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT c.id, c.prompt_name, c.created_at, c.updated_at,
                       COUNT(m.id) as message_count
                FROM conversations c
                LEFT JOIN messages m ON c.id = m.conversation_id
                WHERE c.id = ?
                GROUP BY c.id
            """, (conversation_id,))

            row = cursor.fetchone()
            if row:
                return {
                    "id": row["id"],
                    "prompt_name": row["prompt_name"],
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"],
                    "message_count": row["message_count"]
                }
            return None
