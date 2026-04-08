import httpx
import uvicorn
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from config import GREEN_API_URL, GREEN_API_INSTANCE, GREEN_API_TOKEN
from database import init_db, is_message_processed, mark_message_processed
from agent import get_response


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


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
