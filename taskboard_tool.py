import httpx
from config import TASKBOARD_SUPABASE_URL, TASKBOARD_SUPABASE_KEY

HEADERS = {
    "apikey": TASKBOARD_SUPABASE_KEY,
    "Authorization": f"Bearer {TASKBOARD_SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BASE = f"{TASKBOARD_SUPABASE_URL}/rest/v1"


def _get(path: str, params: dict = None) -> list:
    resp = httpx.get(f"{BASE}/{path}", headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, data: dict) -> dict:
    resp = httpx.post(f"{BASE}/{path}", headers=HEADERS, json=data, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    return result[0] if isinstance(result, list) else result


def _patch(path: str, params: dict, data: dict) -> dict:
    resp = httpx.patch(f"{BASE}/{path}", headers=HEADERS, params=params, json=data, timeout=15)
    resp.raise_for_status()
    result = resp.json()
    return result[0] if isinstance(result, list) else result


def _delete(path: str, params: dict) -> bool:
    resp = httpx.delete(f"{BASE}/{path}", headers=HEADERS, params=params, timeout=15)
    resp.raise_for_status()
    return True


def taskboard_get_tasks(date_from: str = None, date_to: str = None, status: str = None) -> list:
    """Get tasks, optionally filtered by date range and/or status."""
    params = {"select": "id,name,description,due_date,due_time,status,position,project:projects(id,name,domain:domains(id,name))", "order": "due_date.asc,position.asc"}
    if date_from:
        params["due_date"] = f"gte.{date_from}"
    if date_to:
        params["due_date"] = f"lte.{date_to}" if not date_from else params.get("due_date", "") + f"&due_date=lte.{date_to}"
    if status:
        params["status"] = f"eq.{status}"
    return _get("tasks", params)


def taskboard_get_projects() -> list:
    """Get all projects with their domains."""
    return _get("projects", {"select": "id,name,domain:domains(id,name)", "order": "position.asc"})


def taskboard_add_task(name: str, project_id: int, due_date: str,
                       due_time: str = None, description: str = None,
                       status: str = "new") -> dict:
    """Create a new task."""
    data = {
        "name": name,
        "project_id": project_id,
        "due_date": due_date,
        "status": status,
    }
    if due_time:
        data["due_time"] = due_time
    if description:
        data["description"] = description
    return _post("tasks", data)


def taskboard_update_task(task_id: int, name: str = None, status: str = None,
                          due_date: str = None, due_time: str = None,
                          description: str = None, project_id: int = None) -> dict:
    """Update an existing task."""
    data = {}
    if name is not None:
        data["name"] = name
    if status is not None:
        data["status"] = status
    if due_date is not None:
        data["due_date"] = due_date
    if due_time is not None:
        data["due_time"] = due_time
    if description is not None:
        data["description"] = description
    if project_id is not None:
        data["project_id"] = project_id
    return _patch("tasks", {"id": f"eq.{task_id}"}, data)


def taskboard_delete_task(task_id: int) -> bool:
    """Delete a task by ID."""
    return _delete("tasks", {"id": f"eq.{task_id}"})
