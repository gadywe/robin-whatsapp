import httpx
import json
from datetime import datetime, timedelta
import os
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

CALENDAR_API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# יומן "משרד האוצר" — משימות הבית של גדי (יומן נפרד מהיומן הראשי).
# ניתן לעקוף דרך משתנה סביבה אם ה-ID משתנה.
HOUSEHOLD_CALENDAR_ID = os.getenv(
    "HOUSEHOLD_CALENDAR_ID",
    "d7b24aaf668d861ecd3c6ea824c8d128b75ec0bd4ff944cb1a6aa932399330cd@group.calendar.google.com",
)

def get_access_token() -> str:
    resp = httpx.post(TOKEN_URL, data={
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]

def _fetch_calendar_items(token: str, calendar_id: str, time_min: str, time_max: str, max_results: int = 20) -> list:
    resp = httpx.get(
        f"{CALENDAR_API}/calendars/{calendar_id}/events",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": max_results,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("items", [])

def _interpret_household(summary: str, start_str: str) -> str:
    """משימת בית מיומן 'משרד האוצר' — המשמעות נגזרת משעת היום.
    ארגון בבוקר = הכנת הבנות לבית הספר; ארגון בערב = מקלחות והשכבה.
    אוכל בצהריים = בישול ארוחת צהריים; אוכל בערב = בישול ארוחת ערב."""
    hour = None
    if "T" in start_str and len(start_str) >= 13:
        try:
            hour = int(start_str[11:13])
        except ValueError:
            hour = None
    s = (summary or "").strip()
    if "ארגון" in s:
        if hour is not None and hour >= 14:
            return "🏠 ארגון (ערב) — מקלחות והשכבה של הבנות"
        return "🏠 ארגון (בוקר) — הכנת הבנות לבית הספר"
    if "אוכל" in s:
        if hour is not None and hour >= 16:
            return "🏠 אוכל (ערב) — בישול ארוחת ערב"
        return "🏠 אוכל (צהריים) — בישול ארוחת צהריים"
    # משימת בית אחרת מהיומן — סמן כללית כדי שגדי יזהה שזו משימת בית
    return f"🏠 {s}" if s else "🏠 משימת בית"

def get_upcoming_events(days: int = 7) -> list:
    token = get_access_token()
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"

    events = []

    # היומן הראשי
    for e in _fetch_calendar_items(token, "primary", time_min, time_max):
        start = e.get("start", {})
        events.append({
            "id": e.get("id"),
            "summary": e.get("summary", "ללא כותרת"),
            "start": start.get("dateTime", start.get("date", "")),
            "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
            "description": e.get("description", ""),
            "location": e.get("location", ""),
            "household": False,
        })

    # יומן "משרד האוצר" (משימות בית) — לא מפיל את הראשי אם נכשל
    try:
        for e in _fetch_calendar_items(token, HOUSEHOLD_CALENDAR_ID, time_min, time_max):
            start = e.get("start", {})
            start_str = start.get("dateTime", start.get("date", ""))
            events.append({
                "id": e.get("id"),
                "summary": _interpret_household(e.get("summary", ""), start_str),
                "start": start_str,
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                "description": e.get("description", ""),
                "location": e.get("location", ""),
                "household": True,
            })
    except Exception as ex:
        print(f"[calendar] household fetch failed: {type(ex).__name__}: {ex}")

    # מיון לפי זמן התחלה
    events.sort(key=lambda x: x.get("start") or "")
    return events

def create_event(summary: str, start_datetime: str, end_datetime: str, description: str = "", location: str = "") -> dict:
    """
    start_datetime and end_datetime format: "2026-04-15T14:00:00+03:00"
    """
    token = get_access_token()
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start_datetime, "timeZone": "Asia/Jerusalem"},
        "end": {"dateTime": end_datetime, "timeZone": "Asia/Jerusalem"},
    }
    resp = httpx.post(
        f"{CALENDAR_API}/calendars/primary/events",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()

def delete_event(event_id: str) -> bool:
    token = get_access_token()
    resp = httpx.delete(
        f"{CALENDAR_API}/calendars/primary/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    return resp.status_code == 204
