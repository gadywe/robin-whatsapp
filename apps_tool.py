"""
Integration tools for finance-tracker and my-schedule apps.
"""
import httpx
from datetime import date as _date

FINANCE_BASE = "https://finance-tracker-gadywe.vercel.app"
SCHEDULE_BASE = "https://my-schedule-omega.vercel.app"


# ── FINANCE TRACKER ───────────────────────────────────────────────────────────

def finance_get_expenses(year: int = None, month: int = None) -> list:
    """Get expenses. year defaults to current year, month optional."""
    params = {}
    if year:
        params["year"] = year
    if month is not None:
        params["month"] = month
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{FINANCE_BASE}/api/expenses", params=params)
        resp.raise_for_status()
        return resp.json()


def finance_add_expense(date: str, category: str, description: str,
                        amount: float, payment_method: str = "אשראי",
                        group: str = "") -> dict:
    """Add a new expense. date format: YYYY-MM-DD."""
    body = {
        "date": date,
        "category": category,
        "group": group,
        "description": description,
        "amount": amount,
        "paymentMethod": payment_method,
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{FINANCE_BASE}/api/expenses", json=body)
        resp.raise_for_status()
        return resp.json()


def finance_get_income() -> list:
    """Get all income jobs."""
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{FINANCE_BASE}/api/income")
        resp.raise_for_status()
        return resp.json()


def finance_add_income(project: str, income_type: str, amount: float,
                       end_date: str, pay_date: str, status: str = "expected",
                       owner: str = "גדי", note: str = "") -> dict:
    """Add a new income job. dates format: YYYY-MM-DD. status: paid/expected."""
    body = {
        "project": project,
        "type": income_type,
        "amount": amount,
        "endDate": end_date,
        "payDate": pay_date,
        "status": status,
        "owner": owner,
        "note": note,
    }
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{FINANCE_BASE}/api/income", json=body)
        resp.raise_for_status()
        return resp.json()


# ── MY SCHEDULE ───────────────────────────────────────────────────────────────

def schedule_get_categories() -> list:
    """Get all categories with their activities (includes activity IDs needed for logging time)."""
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{SCHEDULE_BASE}/api/categories")
        resp.raise_for_status()
        return resp.json()


def schedule_get_habits(date: str = None) -> dict:
    """Get all habits and their completion status for a given date (default: today)."""
    if not date:
        date = _date.today().strftime("%Y-%m-%d")
    with httpx.Client(timeout=20) as client:
        habits_resp = client.get(f"{SCHEDULE_BASE}/api/habits")
        habits_resp.raise_for_status()
        entries_resp = client.get(f"{SCHEDULE_BASE}/api/habit-entries", params={"date": date})
        entries_resp.raise_for_status()
    habits = habits_resp.json()
    entries = {e["habitId"]: e["value"] for e in entries_resp.json()}
    result = []
    for h in habits:
        result.append({
            "id": h["id"],
            "name": h["name"],
            "emoji": h.get("emoji", ""),
            "done": h["id"] in entries,
            "value": entries.get(h["id"]),
            "targetType": h.get("targetType", "boolean"),
        })
    return {"date": date, "habits": result}


def schedule_log_habit(habit_id: int, date: str = None, value: int = 1) -> dict:
    """Mark a habit as done. date format: YYYY-MM-DD (default: today)."""
    if not date:
        date = _date.today().strftime("%Y-%m-%d")
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{SCHEDULE_BASE}/api/habit-entries",
                           json={"habitId": habit_id, "date": date, "value": value})
        resp.raise_for_status()
        return resp.json()


def schedule_get_time_entries(date: str = None) -> list:
    """Get time entries logged for a specific date (default: today)."""
    if not date:
        date = _date.today().strftime("%Y-%m-%d")
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{SCHEDULE_BASE}/api/time-entries", params={"date": date})
        resp.raise_for_status()
        return resp.json()


def schedule_log_time(activity_id: int, date: str, start_time: str,
                      end_time: str = None, notes: str = None) -> dict:
    """Log a time entry. date: YYYY-MM-DD, times: HH:MM format."""
    body = {"activityId": activity_id, "date": date, "startTime": start_time}
    if end_time:
        body["endTime"] = end_time
    if notes:
        body["notes"] = notes
    with httpx.Client(timeout=20) as client:
        resp = client.post(f"{SCHEDULE_BASE}/api/time-entries", json=body)
        resp.raise_for_status()
        return resp.json()


def schedule_get_report(year: int = None, quarter: int = None) -> dict:
    """Get quarterly time report (hours per category). Defaults to current quarter."""
    params = {}
    if year:
        params["year"] = year
    if quarter:
        params["quarter"] = quarter
    with httpx.Client(timeout=20) as client:
        resp = client.get(f"{SCHEDULE_BASE}/api/reports", params=params)
        resp.raise_for_status()
        return resp.json()
