"""
המעיין (The Spring) — memory bubbles layer.
Any idea/quote/thought/insight Gadi wants to keep becomes a "bubble".
Phase 1: plain text storage + ILIKE free-text search.
Phase 2 adds pgvector embeddings + semantic_search (see embeddings.py).
"""
from db_postgres import get_connection


def create_bubble(chat_id: str, text: str, tags: list[str] = None,
                  category: str = None, source: str = "text") -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO bubbles (chat_id, text, tags, category, source)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, chat_id, text, tags, category, source, created_at
            """, (chat_id, text, tags or [], category, source))
            return _row_to_dict(cur.fetchone())


def get_bubbles(chat_id: str, query: str = None, limit: int = 20) -> list[dict]:
    """Return recent bubbles, optionally filtered by free-text ILIKE on text/tags."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if query:
                like = f"%{query}%"
                cur.execute("""
                    SELECT id, chat_id, text, tags, category, source, created_at
                    FROM bubbles
                    WHERE chat_id = %s
                      AND (text ILIKE %s OR category ILIKE %s
                           OR EXISTS (SELECT 1 FROM unnest(tags) t WHERE t ILIKE %s))
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (chat_id, like, like, like, limit))
            else:
                cur.execute("""
                    SELECT id, chat_id, text, tags, category, source, created_at
                    FROM bubbles
                    WHERE chat_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (chat_id, limit))
            return [_row_to_dict(r) for r in cur.fetchall()]


def update_bubble(bubble_id: int, text: str = None, tags: list[str] = None,
                  category: str = None) -> dict:
    sets, params = [], []
    if text is not None:
        sets.append("text = %s"); params.append(text)
    if tags is not None:
        sets.append("tags = %s"); params.append(tags)
    if category is not None:
        sets.append("category = %s"); params.append(category)
    if not sets:
        return {}
    params.append(bubble_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE bubbles SET {", ".join(sets)}
                WHERE id = %s
                RETURNING id, chat_id, text, tags, category, source, created_at
            """, params)
            row = cur.fetchone()
            return _row_to_dict(row) if row else {}


def get_unfiled_learning(limit: int = 100) -> list[dict]:
    """Learning bubbles (source='learning') not yet filed into the local
    learning material. Used by the /admin/learning sync."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chat_id, text, tags, category, source, created_at
                FROM bubbles
                WHERE source = 'learning' AND filed_at IS NULL
                ORDER BY created_at
                LIMIT %s
            """, (limit,))
            return [_row_to_dict(r) for r in cur.fetchall()]


def mark_filed(ids: list[int]) -> int:
    """Mark the given learning bubbles as filed (so they aren't re-synced)."""
    if not ids:
        return 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE bubbles SET filed_at = NOW() WHERE id = ANY(%s)", (list(ids),))
            return cur.rowcount


def delete_bubble(bubble_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM bubbles WHERE id = %s", (bubble_id,))
            return cur.rowcount > 0


def _row_to_dict(row) -> dict:
    if not row:
        return {}
    return {
        "id": row[0],
        "chat_id": row[1],
        "text": row[2],
        "tags": list(row[3]) if row[3] else [],
        "category": row[4],
        "source": row[5],
        "created_at": row[6].isoformat() if hasattr(row[6], "isoformat") else str(row[6]),
    }
