"""
Reminders system for Robin.
CRUD operations and scheduling logic for WhatsApp reminders.
"""
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from db_postgres import get_connection


def create_reminder(chat_id: str, text: str, remind_at: str,
                    is_recurring: bool = False, recurrence_rule: str = None) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO reminders (chat_id, text, remind_at, is_recurring, recurrence_rule)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, chat_id, text, remind_at, is_recurring, recurrence_rule, status
            """, (chat_id, text, remind_at, is_recurring, recurrence_rule))
            row = cur.fetchone()
            conn.commit()
            return _row_to_dict(row)


def get_reminders(chat_id: str) -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, chat_id, text, remind_at, is_recurring, recurrence_rule, status
                FROM reminders
                WHERE chat_id = %s AND status = 'active'
                ORDER BY remind_at ASC
            """, (chat_id,))
            return [_row_to_dict(row) for row in cur.fetchall()]


def delete_reminder(reminder_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE reminders SET status = 'deleted'
                WHERE id = %s AND status = 'active'
            """, (reminder_id,))
            conn.commit()
            return cur.rowcount > 0


def snooze_reminder(reminder_id: int, new_remind_at: str) -> dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE reminders SET remind_at = %s, status = 'active'
                WHERE id = %s
                RETURNING id, chat_id, text, remind_at, is_recurring, recurrence_rule, status
            """, (new_remind_at, reminder_id))
            conn.commit()
            row = cur.fetchone()
            return _row_to_dict(row) if row else {}


def get_due_reminders() -> list[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE reminders
                SET status = 'sending'
                WHERE remind_at <= NOW() AND status = 'active'
                RETURNING id, chat_id, text, remind_at, is_recurring, recurrence_rule, status
            """)
            conn.commit()
            return [_row_to_dict(row) for row in cur.fetchall()]


def mark_reminder_sent(reminder_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE reminders SET status = 'sent', sent_at = NOW()
                WHERE id = %s
            """, (reminder_id,))
            conn.commit()


def advance_recurring_reminder(reminder_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, remind_at, recurrence_rule
                FROM reminders WHERE id = %s
            """, (reminder_id,))
            row = cur.fetchone()
            if not row:
                return

            current_time = row[1]
            rule = row[2] or ""
            next_time = _compute_next(current_time, rule)

            cur.execute("""
                UPDATE reminders
                SET remind_at = %s, status = 'active', sent_at = NOW()
                WHERE id = %s
            """, (next_time, reminder_id))
            conn.commit()


def _compute_next(current: datetime, rule: str) -> datetime:
    if rule == "daily":
        return current + timedelta(days=1)
    elif rule.startswith("weekly:"):
        return current + timedelta(weeks=1)
    elif rule.startswith("monthly:"):
        return current + relativedelta(months=1)
    elif rule.startswith("yearly:"):
        return current + relativedelta(years=1)
    else:
        return current + timedelta(days=1)


def _row_to_dict(row) -> dict:
    return {
        "id": row[0],
        "chat_id": row[1],
        "text": row[2],
        "remind_at": row[3].isoformat() if hasattr(row[3], 'isoformat') else str(row[3]),
        "is_recurring": row[4],
        "recurrence_rule": row[5],
        "status": row[6],
    }
