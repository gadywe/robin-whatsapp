import httpx
import base64
import re
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REFRESH_TOKEN

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
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


def _headers():
    return {"Authorization": f"Bearer {get_access_token()}"}


def _decode_body(part: dict) -> str:
    """Decode base64url email body."""
    data = part.get("body", {}).get("data", "")
    if data:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    return ""


def _extract_text(payload: dict) -> str:
    """Extract plain text from email payload (handles multipart)."""
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        return _decode_body(payload)
    if mime == "text/html":
        html = _decode_body(payload)
        # strip tags
        return re.sub(r"<[^>]+>", "", html).strip()
    if "parts" in payload:
        # prefer text/plain
        for part in payload["parts"]:
            if part.get("mimeType") == "text/plain":
                text = _decode_body(part)
                if text.strip():
                    return text
        # fallback to any part
        for part in payload["parts"]:
            text = _extract_text(part)
            if text.strip():
                return text
    return ""


def gmail_search(query: str = "is:unread", max_results: int = 10) -> list:
    """Search emails. Returns list of {id, subject, from, date, snippet}."""
    resp = httpx.get(
        f"{GMAIL_API}/messages",
        headers=_headers(),
        params={"q": query, "maxResults": max_results},
        timeout=15,
    )
    resp.raise_for_status()
    messages = resp.json().get("messages", [])

    results = []
    for msg in messages:
        msg_id = msg["id"]
        detail = httpx.get(
            f"{GMAIL_API}/messages/{msg_id}",
            headers=_headers(),
            params={"format": "metadata", "metadataHeaders": ["Subject", "From", "Date"]},
            timeout=15,
        )
        detail.raise_for_status()
        data = detail.json()
        headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
        results.append({
            "id": msg_id,
            "subject": headers.get("Subject", "(ללא נושא)"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": data.get("snippet", ""),
        })
    return results


def gmail_read(message_id: str) -> dict:
    """Read full email content by ID. Returns {subject, from, date, body}."""
    resp = httpx.get(
        f"{GMAIL_API}/messages/{message_id}",
        headers=_headers(),
        params={"format": "full"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    headers = {h["name"]: h["value"] for h in data.get("payload", {}).get("headers", [])}
    body = _extract_text(data.get("payload", {}))
    # truncate long bodies
    if len(body) > 3000:
        body = body[:3000] + "\n...[המייל ארוך, קוצר ל-3000 תווים]"
    return {
        "id": message_id,
        "subject": headers.get("Subject", "(ללא נושא)"),
        "from": headers.get("From", ""),
        "date": headers.get("Date", ""),
        "body": body.strip(),
    }
