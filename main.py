import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from config import META_ACCESS_TOKEN, META_PHONE_NUMBER_ID, META_WEBHOOK_VERIFY_TOKEN
from database import init_db, is_message_processed, mark_message_processed
from agent import get_response
from transcribe import transcribe_audio_bytes

META_API_URL = "https://graph.facebook.com/v19.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


def send_whatsapp_message(to: str, text: str):
    url = f"{META_API_URL}/{META_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {META_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()


def download_meta_media(media_id: str) -> bytes:
    headers = {"Authorization": f"Bearer {META_ACCESS_TOKEN}"}
    # Step 1: get the media URL
    resp = httpx.get(f"{META_API_URL}/{media_id}", headers=headers, timeout=30)
    resp.raise_for_status()
    media_url = resp.json().get("url", "")
    # Step 2: download the file
    resp2 = httpx.get(media_url, headers=headers, timeout=60)
    resp2.raise_for_status()
    return resp2.content


@app.get("/webhook/meta")
async def webhook_verify(request: Request):
    """Meta webhook verification handshake"""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    if mode == "subscribe" and token == META_WEBHOOK_VERIFY_TOKEN:
        return Response(content=challenge, media_type="text/plain")
    return Response(content="Forbidden", status_code=403)


@app.post("/webhook/meta")
async def webhook(request: Request):
    data = await request.json()

    if data.get("object") != "whatsapp_business_account":
        return {"status": "ignored"}

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            for message in value.get("messages", []):
                message_id = message.get("id", "")
                if is_message_processed(message_id):
                    continue
                mark_message_processed(message_id)

                from_number = message.get("from", "")
                msg_type = message.get("type", "")

                if msg_type == "text":
                    text = message.get("text", {}).get("body", "")
                elif msg_type == "audio":
                    audio_id = message.get("audio", {}).get("id", "")
                    try:
                        audio_bytes = download_meta_media(audio_id)
                        text = transcribe_audio_bytes(audio_bytes)
                        if not text:
                            send_whatsapp_message(from_number, "לא הצלחתי לתמלל את ההודעה הקולית 🎤")
                            continue
                        text = f"[הודעה קולית שתומללה]: {text}"
                    except Exception as e:
                        print(f"ERROR voice transcription: {e}")
                        send_whatsapp_message(from_number, "אירעה שגיאה בתמלול ההודעה הקולית 😕")
                        continue
                else:
                    continue

                if not text.strip():
                    continue

                response_text = get_response(from_number, text)
                send_whatsapp_message(from_number, response_text)

    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "robin"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
