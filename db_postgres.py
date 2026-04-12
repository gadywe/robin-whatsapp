"""
PostgreSQL (Neon) database layer for robin messages.
Replaces SQLite database.py
"""
import os
import time
import psycopg
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required")


@contextmanager
def get_connection():
    """Get a PostgreSQL connection."""
    conn = psycopg.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Initialize database schema."""
    sql = """
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        chat_id TEXT NOT NULL,
        role TEXT NOT NULL,
        content TEXT NOT NULL,
        timestamp DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_messages_chat_timestamp ON messages(chat_id, timestamp);

    CREATE TABLE IF NOT EXISTS processed_messages (
        message_id TEXT PRIMARY KEY,
        timestamp DOUBLE PRECISION NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE INDEX IF NOT EXISTS idx_processed_timestamp ON processed_messages(timestamp);

    CREATE TABLE IF NOT EXISTS reminders (
        id SERIAL PRIMARY KEY,
        chat_id TEXT NOT NULL,
        text TEXT NOT NULL,
        remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
        is_recurring BOOLEAN DEFAULT FALSE,
        recurrence_rule TEXT,
        status TEXT DEFAULT 'active',
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        sent_at TIMESTAMP WITH TIME ZONE
    );

    CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(remind_at) WHERE status = 'active';
    CREATE INDEX IF NOT EXISTS idx_reminders_chat ON reminders(chat_id, status);
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)


def is_message_processed(message_id: str) -> bool:
    """Check if a message has been processed."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = %s LIMIT 1",
                (message_id,)
            )
            return cur.fetchone() is not None


def mark_message_processed(message_id: str):
    """Mark a message as processed."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO processed_messages (message_id, timestamp) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (message_id, time.time())
            )


def save_message(chat_id: str, role: str, content: str):
    """Save a message to the database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (%s, %s, %s, %s)",
                (chat_id, role, content, time.time())
            )


def get_history(chat_id: str, limit: int = 10) -> list[dict]:
    """Get message history for a chat."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content FROM messages WHERE chat_id = %s ORDER BY timestamp DESC LIMIT %s",
                (chat_id, limit)
            )
            rows = cur.fetchall()

    # Return in chronological order
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def cleanup_old_processed(days: int = 7):
    """Clean up old processed message records."""
    cutoff = time.time() - (days * 86400)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM processed_messages WHERE timestamp < %s",
                (cutoff,)
            )


def get_all_messages() -> list[tuple]:
    """Get all messages (for export)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT chat_id, role, content, timestamp FROM messages ORDER BY timestamp ASC"
            )
            return cur.fetchall()
