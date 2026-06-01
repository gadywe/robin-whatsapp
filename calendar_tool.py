import httpx
import json
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
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

# כל היומנים שרובין קורא מהם. כל ערך: (calendar_id, label, emoji, interpret_fn).
# primary = היומן האישי הראשי. interpret_fn מקבל (summary, start_str) ומחזיר
# סיכום מפוענח (משמש למשימות הבית); אחרת מוצמד אימוג'י לפי המקור.
CALENDAR_SOURCES = [
    ("primary",               "אישי",          "",   None),
    (HOUSEHOLD_CALENDAR_ID,   "משרד האוצר",    "",   _interpret_household),
    ("9a9e5ead7a92907c9b4df52dafe6e72115a5a783bc62522ba640026ec4bd0031@group.calendar.google.com", "משרד הבריאות", "💪", None),
    ("j4iml6tbn34s77bido1vii373s@group.calendar.google.com",                                         "היומן הזוגי",  "❤️", None),
    ("family13706754214643911480@group.calendar.google.com",                                         "Family",       "👨‍👩‍👧‍👧", None),
    ("zoommysteries@gmail.com",                                                                       "התא האפור",    "🕵️", None),
    ("200b896290df51b03ac7c8d874833dc25a2afe43f2a7c9ae4ba43f12a7aab8b8@group.calendar.google.com",   "עבודה פרילאנס", "💼", None),
    ("7cmfe3gsa9skvhecqdbqbf14kk@group.calendar.google.com",                                         "עבודה תמ\"י",   "🏢", None),
    ("7f546a79afe3fc1ec6dc0ebf4a7fb6dc814a75b8e28530fe0ea3f7d7077568cb@group.calendar.google.com",   "מוח אש",        "🔥", None),
    ("a762f11304c7c585d236d778093ea12bd6b4780504687f684449167c7b367553@group.calendar.google.com",   "משרד החינוך",   "🎓", None),
]

def _map_event(e: dict, emoji: str, label: str, interpret) -> dict:
    start = e.get("start", {})
    start_str = start.get("dateTime", start.get("date", ""))
    raw = e.get("summary", "ללא כותרת")
    if interpret:
        summary = interpret(raw, start_str)
    elif emoji:
        summary = f"{emoji} {raw}"
    else:
        summary = raw
    return {
        "id": e.get("id"),
        "summary": summary,
        "start": start_str,
        "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
        "description": e.get("description", ""),
        "location": e.get("location", ""),
        "calendar": label,
    }

def _fetch_source(token: str, source: tuple, time_min: str, time_max: str) -> list:
    cal_id, label, emoji, interpret = source
    try:
        items = _fetch_calendar_items(token, cal_id, time_min, time_max)
        return [_map_event(e, emoji, label, interpret) for e in items]
    except Exception as ex:
        # יומן בודד שנכשל לא מפיל את כל השאר
        print(f"[calendar] fetch failed for {label}: {type(ex).__name__}: {ex}")
        return []

def get_upcoming_events(days: int = 7) -> list:
    token = get_access_token()
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"

    events = []
    # שליפה מקבילה מכל היומנים כדי לא להאט את התגובה
    with ThreadPoolExecutor(max_workers=len(CALENDAR_SOURCES)) as pool:
        futures = [pool.submit(_fetch_source, token, src, time_min, time_max) for src in CALENDAR_SOURCES]
        for f in futures:
            events.extend(f.result())

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
