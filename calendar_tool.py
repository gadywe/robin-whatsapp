import httpx
import json
from datetime import datetime, timedelta
import os
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

CALENDAR_API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

def get_access_token() -> str:
    resp = httpx.post(TOKEN_URL, data={
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": GOOGLE_REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]

def get_upcoming_events(days: int = 7) -> list:
    token = get_access_token()
    now = datetime.utcnow()
    time_min = now.isoformat() + "Z"
    time_max = (now + timedelta(days=days)).isoformat() + "Z"
    resp = httpx.get(
        f"{CALENDAR_API}/calendars/primary/events",
        headers={"Authorization": f"Bearer {token}"},
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 20,
        },
        timeout=15,
    )
    resp.raise_for_status()
    events = []
    for e in resp.json().get("items", []):
        start = e.get("start", {})
        events.append({
            "id": e.get("id"),
            "summary": e.get("summary", "ללא כותרת"),
            "start": start.get("dateTime", start.get("date", "")),
            "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
            "description": e.get("description", ""),
            "location": e.get("location", ""),
        })
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
