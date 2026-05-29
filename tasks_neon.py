"""
הגשר (The Bridge) — Robin's native task board (Neon Postgres).
Tasks + subtasks + statuses + priorities. Distinct from the external
Supabase TaskBoard (taskboard_tool.py), which stays as an outside integration.

status:   new | working | done
priority: low | med | high
"""
from db_postgres import get_connection

STATUSES = {"new", "working", "done"}
PRIORITIES = {"low", "med", "high"}


def create_task(chat_id: str, title: str, description: str = None,
                priority: str = "med", due_date: str = None,
                parent_task_id: int = None) -> dict:
    if priority not in PRIORITIES:
        priority = "med"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO tasks (chat_id, title, description, priority, due_date, parent_task_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, chat_id, title, description, status, priority,
                          parent_task_id, due_date, created_at, completed_at
            """, (chat_id, title, description, priority, due_date, parent_task_id))
            return _row_to_dict(cur.fetchone())


def create_subtask(chat_id: str, parent_task_id: int, title: str,
                   description: str = None, priority: str = "med") -> dict:
    return create_task(chat_id, title, description, priority,
                       parent_task_id=parent_task_id)


def get_tasks(chat_id: str, status: str = None, priority: str = None,
              include_subtasks: bool = True) -> list[dict]:
    clauses = ["chat_id = %s"]
    params = [chat_id]
    if status:
        clauses.append("status = %s"); params.append(status)
    if priority:
        clauses.append("priority = %s"); params.append(priority)
    if not include_subtasks:
        clauses.append("parent_task_id IS NULL")
    where = " AND ".join(clauses)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT id, chat_id, title, description, status, priority,
                       parent_task_id, due_date, created_at, completed_at
                FROM tasks
                WHERE {where}
                ORDER BY parent_task_id NULLS FIRST,
                         CASE priority WHEN 'high' THEN 0 WHEN 'med' THEN 1 ELSE 2 END,
                         due_date NULLS LAST, created_at
            """, params)
            return [_row_to_dict(r) for r in cur.fetchall()]


def update_task(task_id: int, title: str = None, description: str = None,
                status: str = None, priority: str = None, due_date: str = None) -> dict:
    sets, params = [], []
    if title is not None:
        sets.append("title = %s"); params.append(title)
    if description is not None:
        sets.append("description = %s"); params.append(description)
    if status is not None and status in STATUSES:
        sets.append("status = %s"); params.append(status)
        sets.append("completed_at = " + ("NOW()" if status == "done" else "NULL"))
    if priority is not None and priority in PRIORITIES:
        sets.append("priority = %s"); params.append(priority)
    if due_date is not None:
        sets.append("due_date = %s"); params.append(due_date)
    if not sets:
        return {}
    params.append(task_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                UPDATE tasks SET {", ".join(sets)}
                WHERE id = %s
                RETURNING id, chat_id, title, description, status, priority,
                          parent_task_id, due_date, created_at, completed_at
            """, params)
            row = cur.fetchone()
            return _row_to_dict(row) if row else {}


def complete_task(task_id: int) -> dict:
    return update_task(task_id, status="done")


def delete_task(task_id: int) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
            return cur.rowcount > 0


def _row_to_dict(row) -> dict:
    if not row:
        return {}
    return {
        "id": row[0],
        "chat_id": row[1],
        "title": row[2],
        "description": row[3],
        "status": row[4],
        "priority": row[5],
        "parent_task_id": row[6],
        "due_date": row[7].isoformat() if hasattr(row[7], "isoformat") else row[7],
        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8]),
        "completed_at": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
    }
