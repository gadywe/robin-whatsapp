"""
Lists with checkable items (e.g. a shopping list dictated as a voice message).
Items are toggled individually via Telegram inline buttons.
"""
from db_postgres import get_connection


def create_list(chat_id: str, title: str, items: list[str] = None) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO lists (chat_id, title) VALUES (%s, %s)
                RETURNING id, chat_id, title, created_at
            """, (chat_id, title))
            row = cur.fetchone()
            list_id = row[0]
            if items:
                for pos, item in enumerate(items):
                    cur.execute("""
                        INSERT INTO list_items (list_id, text, position)
                        VALUES (%s, %s, %s)
                    """, (list_id, item, pos))
    return get_list(list_id)


def add_items(list_id: int, items: list[str]) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(position), -1) FROM list_items WHERE list_id = %s",
                        (list_id,))
            start = (cur.fetchone()[0] or -1) + 1
            for offset, item in enumerate(items):
                cur.execute("""
                    INSERT INTO list_items (list_id, text, position)
                    VALUES (%s, %s, %s)
                """, (list_id, item, start + offset))
    return get_list(list_id)


def get_list(list_id: int) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, chat_id, title, created_at FROM lists WHERE id = %s",
                        (list_id,))
            head = cur.fetchone()
            if not head:
                return {}
            cur.execute("""
                SELECT id, text, is_checked, position
                FROM list_items WHERE list_id = %s
                ORDER BY position, id
            """, (list_id,))
            items = [{"id": r[0], "text": r[1], "is_checked": r[2], "position": r[3]}
                     for r in cur.fetchall()]
    return {
        "id": head[0], "chat_id": head[1], "title": head[2],
        "created_at": head[3].isoformat() if hasattr(head[3], "isoformat") else str(head[3]),
        "items": items,
    }


def get_lists(chat_id: str, limit: int = 10) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM lists WHERE chat_id = %s
                ORDER BY created_at DESC LIMIT %s
            """, (chat_id, limit))
            ids = [r[0] for r in cur.fetchall()]
    return [get_list(i) for i in ids]


def set_item_checked(item_id: int, checked: bool) -> int:
    """Toggle one item; returns the parent list_id (for re-rendering)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE list_items SET is_checked = %s WHERE id = %s
                RETURNING list_id
            """, (checked, item_id))
            row = cur.fetchone()
            return row[0] if row else None


def check_item(item_id: int) -> int:
    return set_item_checked(item_id, True)


def uncheck_item(item_id: int) -> int:
    return set_item_checked(item_id, False)


def render_list(list_dict: dict) -> tuple[str, list[dict]]:
    """Build (text, inline_buttons) for a list. Each item is a toggle button;
    callback_data = 'list_check_<id>' / 'list_uncheck_<id>'."""
    if not list_dict:
        return ("הרשימה לא נמצאה", [])
    lines = [f"📝 {list_dict['title']}"]
    buttons = []
    for it in list_dict["items"]:
        mark = "✅" if it["is_checked"] else "⬜"
        lines.append(f"{mark} {it['text']}")
        if it["is_checked"]:
            buttons.append({"text": f"↩️ {it['text']}", "data": f"list_uncheck_{it['id']}"})
        else:
            buttons.append({"text": f"✔️ {it['text']}", "data": f"list_check_{it['id']}"})
    return ("\n".join(lines), buttons)
