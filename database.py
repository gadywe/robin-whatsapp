import sqlite3
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "robin.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp REAL NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, timestamp);

        CREATE TABLE IF NOT EXISTS processed_messages (
            message_id TEXT PRIMARY KEY,
            timestamp REAL NOT NULL
        );
    """)
    conn.close()


def is_message_processed(message_id: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM processed_messages WHERE message_id = ?", (message_id,)
    ).fetchone()
    conn.close()
    return row is not None


def mark_message_processed(message_id: str):
    conn = get_connection()
    conn.execute(
        "INSERT OR IGNORE INTO processed_messages (message_id, timestamp) VALUES (?, ?)",
        (message_id, time.time()),
    )
    conn.commit()
    conn.close()


def save_message(chat_id: str, role: str, content: str):
    conn = get_connection()
    conn.execute(
        "INSERT INTO messages (chat_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
        (chat_id, role, content, time.time()),
    )
    conn.commit()
    conn.close()


def get_history(chat_id: str, limit: int = 20) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp DESC LIMIT ?",
        (chat_id, limit),
    ).fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def cleanup_old_processed(days: int = 7):
    cutoff = time.time() - (days * 86400)
    conn = get_connection()
    conn.execute("DELETE FROM processed_messages WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()
