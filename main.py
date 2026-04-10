import httpx
import uvicorn
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from config import GREEN_API_URL, GREEN_API_INSTANCE, GREEN_API_TOKEN
from database import init_db, is_message_processed, mark_message_processed
from agent import get_response
from transcribe import transcribe_audio


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


def get_green_api_download_url(chat_id: str, message_id: str) -> str:
    """Ask Green API to give us the download URL for a media message."""
    url = f"{GREEN_API_URL}/waInstance{GREEN_API_INSTANCE}/downloadFile/{GREEN_API_TOKEN}"
    payload = {"chatId": chat_id, "idMessage": message_id}
    resp = httpx.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json().get("downloadUrl", "")


def send_whatsapp_message(chat_id: str, text: str):
    url = f"{GREEN_API_URL}/waInstance{GREEN_API_INSTANCE}/sendMessage/{GREEN_API_TOKEN}"
    payload = {"chatId": chat_id, "message": text}
    resp = httpx.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


@app.post("/webhook/green-api")
async def webhook(request: Request):
    data = await request.json()

    type_webhook = data.get("typeWebhook")
    if type_webhook != "incomingMessageReceived":
        return {"status": "ignored"}

    message_id = data.get("idMessage", "")
    if is_message_processed(message_id):
        return {"status": "duplicate"}

    mark_message_processed(message_id)

    sender_data = data.get("senderData", {})
    chat_id = sender_data.get("chatId", "")

    # Ignore group messages
    if "@g.us" in chat_id:
        return {"status": "group_ignored"}

    message_data = data.get("messageData", {})
    type_message = message_data.get("typeMessage", "")

    if type_message == "textMessage":
        text = message_data.get("textMessageData", {}).get("textMessage", "")
    elif type_message == "extendedTextMessage":
        text = message_data.get("extendedTextMessageData", {}).get("text", "")
    elif type_message in ("audioMessage", "pttMessage", "voiceMessage"):
        # Voice message - use Green API downloadFile endpoint to get the URL
        message_id = data.get("idMessage", "")
        try:
            audio_url = get_green_api_download_url(chat_id, message_id)
            if not audio_url:
                send_whatsapp_message(chat_id, "לא הצלחתי להוריד את ההודעה הקולית 🎤")
                return {"status": "no_audio_url"}
            transcribed = transcribe_audio(audio_url)
            if not transcribed:
                send_whatsapp_message(chat_id, "לא הצלחתי לתמלל את ההודעה הקולית 🎤")
                return {"status": "empty_transcription"}
            text = f"[הודעה קולית שתומללה]: {transcribed}"
        except Exception as e:
            print(f"ERROR voice transcription: {e}")
            send_whatsapp_message(chat_id, "אירעה שגיאה בתמלול ההודעה הקולית 😕")
            return {"status": "transcription_error", "error": str(e)}
    else:
        return {"status": "unsupported_type"}

    if not text.strip():
        return {"status": "empty"}

    response_text = get_response(chat_id, text)
    send_whatsapp_message(chat_id, response_text)

    return {"status": "ok", "response": response_text}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "robin"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
