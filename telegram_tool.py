"""
Telegram Bot API channel layer for Robin.
Replaces the WhatsApp/Meta send/receive functions in main.py + file_tool.py.

Public API:
  tg_send_message(chat_id, text)
  tg_send_buttons(chat_id, text, buttons)      buttons = [{"text":..,"data":..}, ...] or list-of-rows
  tg_send_document(chat_id, file_bytes, filename, caption="")
  tg_download_file(file_id) -> bytes
  tg_answer_callback(callback_query_id, text="")
  tg_set_webhook(url) -> dict
  parse_update(update) -> dict   # normalizes a Telegram update
"""
import httpx
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_SECRET_TOKEN

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
FILE_BASE = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

# Telegram caps a single text message at 4096 chars.
MAX_TG_TEXT = 4096
# getFile download cap is ~20MB.
MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024


def _post(method: str, **kwargs):
    url = f"{API_BASE}/{method}"
    resp = httpx.post(url, timeout=60, **kwargs)
    if not resp.is_success:
        print(f"ERROR telegram {method} {resp.status_code}: {resp.text}")
    resp.raise_for_status()
    return resp.json()


def tg_send_message(chat_id, text: str):
    """Send a plain text message. Long text is split into <=4096-char chunks."""
    text = text or "…"
    chunks = [text[i:i + MAX_TG_TEXT] for i in range(0, len(text), MAX_TG_TEXT)] or ["…"]
    last = None
    for chunk in chunks:
        last = _post("sendMessage", json={
            "chat_id": chat_id,
            "text": chunk,
            "disable_web_page_preview": True,
        })
    return last


def _normalize_keyboard(buttons: list) -> list:
    """Accepts a flat list of {"text","data"} (one button per row) or a list of
    rows (each row a list of {"text","data"}). Returns Telegram inline_keyboard."""
    if buttons and isinstance(buttons[0], dict):
        rows = [[b] for b in buttons]  # one button per row
    else:
        rows = buttons
    return [
        [{"text": b["text"], "callback_data": b["data"]} for b in row]
        for row in rows
    ]


def tg_send_buttons(chat_id, text: str, buttons: list):
    """Send a message with an inline keyboard.
    buttons: [{"text": "מחק", "data": "reminder_delete_42"}, ...]"""
    return _post("sendMessage", json={
        "chat_id": chat_id,
        "text": text or "…",
        "reply_markup": {"inline_keyboard": _normalize_keyboard(buttons)},
        "disable_web_page_preview": True,
    })


def tg_send_document(chat_id, file_bytes: bytes, filename: str, caption: str = ""):
    """Upload and send a document."""
    files = {"document": (filename, file_bytes)}
    data = {"chat_id": str(chat_id)}
    if caption:
        data["caption"] = caption[:1024]
    return _post("sendDocument", data=data, files=files)


def tg_download_file(file_id: str) -> bytes:
    """Resolve a file_id to its bytes via getFile + file download."""
    info = _post("getFile", json={"file_id": file_id})
    file_path = info["result"]["file_path"]
    size = info["result"].get("file_size", 0)
    if size and size > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"file too large: {size} bytes (max {MAX_DOWNLOAD_BYTES})")
    resp = httpx.get(f"{FILE_BASE}/{file_path}", timeout=120)
    resp.raise_for_status()
    return resp.content


def tg_edit_buttons(chat_id, message_id, text: str, buttons: list):
    """Edit an existing message's text + inline keyboard in place (used to
    re-render a list after toggling an item, instead of spamming new messages)."""
    return _post("editMessageText", json={
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text or "…",
        "reply_markup": {"inline_keyboard": _normalize_keyboard(buttons)},
        "disable_web_page_preview": True,
    })


def tg_answer_callback(callback_query_id: str, text: str = ""):
    """Stop the loading spinner on an inline button press."""
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        return _post("answerCallbackQuery", json=payload)
    except Exception as e:
        print(f"WARN answerCallbackQuery: {e}")
        return None


def tg_set_webhook(url: str) -> dict:
    """One-time webhook registration. Binds our secret token so we can verify
    incoming updates via the X-Telegram-Bot-Api-Secret-Token header."""
    return _post("setWebhook", json={
        "url": url,
        "secret_token": TELEGRAM_SECRET_TOKEN,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    })


def parse_update(update: dict) -> dict:
    """Normalize a Telegram update into a flat dict the webhook can dispatch on.

    Returns: {
        kind: text|voice|photo|document|callback|ignore,
        update_id, chat_id, text, caption,
        file_id, mime, filename,
        callback_data, callback_id,
    }
    """
    out = {
        "kind": "ignore",
        "update_id": update.get("update_id"),
        "chat_id": None,
        "text": "",
        "caption": "",
        "file_id": None,
        "mime": "",
        "filename": "",
        "callback_data": None,
        "callback_id": None,
        "message_id": None,
    }

    # Inline button press
    cq = update.get("callback_query")
    if cq:
        out["kind"] = "callback"
        out["callback_data"] = cq.get("data", "")
        out["callback_id"] = cq.get("id", "")
        msg = cq.get("message", {}) or {}
        out["chat_id"] = str((msg.get("chat", {}) or {}).get("id", ""))
        out["message_id"] = msg.get("message_id")
        return out

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return out

    out["chat_id"] = str((msg.get("chat", {}) or {}).get("id", ""))
    out["caption"] = msg.get("caption", "") or ""

    if "text" in msg:
        out["kind"] = "text"
        out["text"] = msg["text"]
    elif "voice" in msg:
        out["kind"] = "voice"
        out["file_id"] = msg["voice"].get("file_id")
        out["mime"] = msg["voice"].get("mime_type", "audio/ogg")
    elif "audio" in msg:
        out["kind"] = "voice"
        out["file_id"] = msg["audio"].get("file_id")
        out["mime"] = msg["audio"].get("mime_type", "audio/mpeg")
    elif "photo" in msg:
        # photo is an array of sizes; take the largest (last)
        out["kind"] = "photo"
        out["file_id"] = msg["photo"][-1].get("file_id")
        out["mime"] = "image/jpeg"
    elif "document" in msg:
        out["kind"] = "document"
        doc = msg["document"]
        out["file_id"] = doc.get("file_id")
        out["mime"] = doc.get("mime_type", "")
        out["filename"] = doc.get("file_name", "file")

    return out
