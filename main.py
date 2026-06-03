import asyncio
import uvicorn
from fastapi import FastAPI, Request, Response
from contextlib import asynccontextmanager
from zoneinfo import ZoneInfo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from config import (
    TELEGRAM_SECRET_TOKEN, CRON_SECRET, GADI_TELEGRAM_CHAT_ID,
    REMINDERS_ENABLED, BRIEFING_ENABLED, COST_REPORT_ENABLED,
)
from db_postgres import init_db, is_message_processed, mark_message_processed
from agent import get_response
from transcribe import transcribe_audio_bytes
from file_tool import process_file_by_mime
from reminders import get_due_reminders, mark_reminder_sent, advance_recurring_reminder, delete_reminder
from weather_tool import get_jerusalem_weather, get_clothing_advice
from quotes_tool import get_random_quote
from gmail_tool import gmail_search, gmail_read
from reading_plan_tool import get_today_reading
from telegram_tool import (
    tg_send_message, tg_send_buttons, tg_answer_callback, tg_edit_buttons,
    tg_download_file, tg_set_webhook, parse_update,
)
import lists as lists_db
import bubbles as bubbles_db


ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
scheduler = AsyncIOScheduler(timezone=ISRAEL_TZ)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # In-process scheduler. Reminder firing no longer depends on an external
    # cron (cron-job.org) that auto-disables itself after a burst of failures.
    # Whenever the service is awake these jobs run, so the bot self-heals after
    # any outage instead of staying dead until a manual re-enable. A free
    # keep-alive pinger (UptimeRobot on /health) just prevents the free-tier
    # spin-down; it never disables itself.
    if REMINDERS_ENABLED:
        scheduler.add_job(
            _scheduled_reminder_check, IntervalTrigger(minutes=1),
            id="reminders", max_instances=1, coalesce=True,
        )
    if COST_REPORT_ENABLED:
        scheduler.add_job(
            _scheduled_daily_cost, CronTrigger(hour=20, minute=0),
            id="daily_cost", max_instances=1, coalesce=True,
        )
    scheduler.start()
    print(f"Scheduler started: jobs={[j.id for j in scheduler.get_jobs()]}")
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


async def _scheduled_reminder_check():
    try:
        sent = await asyncio.to_thread(_do_check_reminders)
        if sent:
            print(f"[scheduler] reminders sent: {sent}")
    except Exception as e:
        print(f"[scheduler] reminder check error: {e}")


async def _scheduled_daily_cost():
    try:
        await asyncio.to_thread(_do_daily_cost)
    except Exception as e:
        print(f"[scheduler] daily cost error: {e}")


app = FastAPI(lifespan=lifespan)


# ── Telegram webhook ───────────────────────────────────────────────────────────

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    # Verify the secret token Telegram echoes back on every update.
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != TELEGRAM_SECRET_TOKEN:
        return Response(content="Forbidden", status_code=403)

    update = await request.json()
    u = parse_update(update)

    # Idempotency on update_id (Telegram resends until it gets a 200).
    update_id = u.get("update_id")
    if update_id is not None:
        uid = f"tg_{update_id}"
        if is_message_processed(uid):
            return {"status": "duplicate"}
        mark_message_processed(uid)

    chat_id = u.get("chat_id")
    if not chat_id:
        return {"status": "ignored"}

    try:
        handle_update(u, chat_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR handle_update: {e}")

    return {"status": "ok"}


def handle_update(u: dict, chat_id: str):
    kind = u["kind"]

    if kind == "callback":
        handle_callback(u, chat_id)
        return

    text = ""

    if kind == "text":
        text = u["text"]
        # Deep-link / start handling reserved for Phase 3 (sharing).
        if text.startswith("/start"):
            tg_send_message(chat_id, "היי, אני רובין 🤖 כתוב לי כל דבר - תזכורת, משימה, רעיון לזכור, או מה ביומן.")
            return

    elif kind == "voice":
        try:
            audio_bytes = tg_download_file(u["file_id"])
            transcript = transcribe_audio_bytes(audio_bytes, mime_type=u.get("mime", "audio/ogg"))
            if not transcript:
                tg_send_message(chat_id, "לא הצלחתי לתמלל את ההודעה הקולית 🎤")
                return
            text = f"[הודעה קולית שתומללה]: {transcript}"
        except Exception as e:
            print(f"ERROR voice: {e}")
            tg_send_message(chat_id, "אירעה שגיאה בתמלול ההודעה הקולית 😕")
            return

    elif kind == "photo":
        try:
            image_bytes = tg_download_file(u["file_id"])
            response_text = get_response(
                chat_id, u.get("caption") or "[המשתמש שלח תמונה]",
                image_bytes=image_bytes, image_mime="image/jpeg",
            )
            tg_send_message(chat_id, response_text)
        except Exception as e:
            print(f"ERROR image: {e}")
            tg_send_message(chat_id, "לא הצלחתי לראות את התמונה 😕")
        return

    elif kind == "document":
        try:
            file_bytes = tg_download_file(u["file_id"])
            file_content = process_file_by_mime(file_bytes, u.get("mime", ""), u.get("filename", ""))
            caption = u.get("caption", "")
            text = f"[קובץ שנשלח: {u.get('filename','')}]\n{file_content}"
            if caption:
                text = f"{caption}\n{text}"
        except Exception as e:
            print(f"ERROR document: {e}")
            tg_send_message(chat_id, f"לא הצלחתי לקרוא את הקובץ (שגיאה: {type(e).__name__}) 😕")
            return

    else:
        return

    if not text.strip():
        return

    response_text = get_response(chat_id, text)
    tg_send_message(chat_id, response_text)


def handle_callback(u: dict, chat_id: str):
    """Inline button presses. callback_data convention: action_param_id."""
    data = u.get("callback_data", "") or ""
    tg_answer_callback(u.get("callback_id", ""))
    parts = data.split("_")

    # reminder_delete_<id> / reminder_snooze_<id>
    if parts[0] == "reminder" and len(parts) >= 3:
        action, rid = parts[1], int(parts[2])
        if action == "delete":
            delete_reminder(rid)
            tg_send_message(chat_id, "התזכורת נמחקה ✓")
        elif action == "snooze":
            text = f"[המשתמש לחץ על 'הזכר שוב' לתזכורת מספר {rid}]. שאל אותו בעוד כמה זמן להזכיר."
            tg_send_message(chat_id, get_response(chat_id, text))
        return

    # list_check_<itemId> / list_uncheck_<itemId>  → toggle + re-render in place
    if parts[0] == "list" and len(parts) >= 3:
        action, item_id = parts[1], int(parts[2])
        list_id = lists_db.check_item(item_id) if action == "check" else lists_db.uncheck_item(item_id)
        if list_id:
            lst = lists_db.get_list(list_id)
            text, buttons = lists_db.render_list(lst)
            if u.get("message_id"):
                try:
                    tg_edit_buttons(chat_id, u["message_id"], text, buttons)
                    return
                except Exception:
                    pass
            tg_send_buttons(chat_id, text, buttons)
        return


@app.api_route("/admin/set-webhook", methods=["GET", "POST"])
async def set_webhook(token: str = "", url: str = ""):
    """One-time webhook registration. Call with ?token=<CRON_SECRET>&url=<public_url>/webhook/telegram"""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    if not url:
        return {"error": "missing url param"}
    return tg_set_webhook(url)


@app.get("/admin/bubbles/recent")
async def bubbles_recent(token: str = "", limit: int = 15):
    """Diagnostic: most recent bubbles across all sources."""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    return {"items": bubbles_db.get_recent(limit)}


@app.get("/admin/calendar/check")
async def calendar_check(token: str = ""):
    """Diagnostic: does Robin's Google Calendar connection actually work?"""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    try:
        from calendar_tool import get_upcoming_events
        events = get_upcoming_events(days=10)
        return {"ok": True, "count": len(events), "v": "with-end",
                "events": [{"start": e["start"], "end": e.get("end"), "summary": e["summary"]} for e in events[:25]]}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}"}


@app.get("/admin/learning/pending")
async def learning_pending(token: str = ""):
    """Return learning insights captured via Telegram that aren't yet filed into
    the local learning material. Used by the local sync (Claude Code)."""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    items = bubbles_db.get_unfiled_learning()
    return {"count": len(items), "items": items}


@app.get("/admin/learning/mark")
async def learning_mark(token: str = "", ids: str = ""):
    """Mark learning insights as filed. ids = comma-separated bubble ids."""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    id_list = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    n = bubbles_db.mark_filed(id_list)
    return {"marked": n, "ids": id_list}


# ── Cron: reminders ──────────────────────────────────────────────────────────

def _do_check_reminders() -> int:
    """Send all due reminders; return how many were sent.

    Safe to call concurrently (scheduler + external pinger): get_due_reminders
    atomically claims rows (status active -> sending) so no reminder double-sends.
    """
    due = get_due_reminders()
    sent_count = 0
    for reminder in due:
        try:
            body = f"⏰ תזכורת:\n{reminder['text']}"
            buttons = [
                {"text": "מחק", "data": f"reminder_delete_{reminder['id']}"},
                {"text": "הזכר שוב", "data": f"reminder_snooze_{reminder['id']}"},
            ]
            tg_send_buttons(reminder['chat_id'], body, buttons)

            if reminder['is_recurring']:
                advance_recurring_reminder(reminder['id'])
            else:
                mark_reminder_sent(reminder['id'])
            sent_count += 1
        except Exception as e:
            print(f"ERROR sending reminder {reminder['id']}: {e}")
            mark_reminder_sent(reminder['id'])
    return sent_count


@app.get("/check-reminders")
async def check_reminders(token: str = ""):
    """External-cron fallback. The in-process scheduler is now the primary
    trigger; this endpoint stays so an external pinger can still drive it."""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    if not REMINDERS_ENABLED:
        return {"status": "disabled"}
    sent_count = await asyncio.to_thread(_do_check_reminders)
    return {"sent": sent_count}


# ── Cron: morning briefing ───────────────────────────────────────────────────

@app.get("/morning-briefing")
async def morning_briefing(token: str = ""):
    """Called by cron every morning. Sends a personalized morning message to Gadi."""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    if not BRIEFING_ENABLED:
        return {"status": "disabled"}

    try:
        # 1. Weather
        weather_text = ""
        try:
            weather = get_jerusalem_weather()
            clothing = get_clothing_advice(weather)
            weather_text = (
                f"מזג האוויר בירושלים היום:\n"
                f"{weather['description']}\n"
                f"טמפרטורה: {weather['temp_min']}°–{weather['temp_max']}° (עכשיו {weather['temp_now']}°, מורגש {weather['feels_like']}°)\n"
                f"{'גשם צפוי: ' + str(weather['rain_mm']) + ' מ\"מ 🌂' + chr(10) if weather['rain_mm'] > 0 else ''}"
                f"בגדים: {clothing}"
            )
        except Exception as e:
            print(f"Morning briefing: Weather error: {e}")
            weather_text = "(לא הצלחתי לטעון את מזג האוויר היום)"

        # 2. Quote
        quote_data = get_random_quote(daily=False)
        quote_text = f'"{quote_data["quote"]}"\n— {quote_data["name"]}'

        # 3. The Rundown AI email (search last 24h)
        rundown_text = ""
        try:
            emails = gmail_search(query='from:(therundown.ai) newer_than:1d', max_results=1)
            if emails:
                email = gmail_read(emails[0]["id"])
                body = email["body"][:2000] if email["body"] else ""
                rundown_text = body
        except Exception as e:
            print(f"Morning briefing: Gmail error: {e}")
            rundown_text = "(לא הצלחתי לטעון את המייל היום)"

        # 4. Today's reading
        reading_today = get_today_reading()

        # 5. Compose with Claude
        from agent import ANTHROPIC_API_KEY, LLM_MODEL
        import httpx as _httpx

        reading_section = f"""5. Today's reading/listening assignment (from Gadi's weekly learning plan):
{reading_today}
""" if reading_today else ""

        prompt = f"""You are Robin, Gadi's personal assistant. Write a morning message entirely in English that includes:

1. A warm and original morning greeting (different every day, not just "good morning")
2. Weather + clothing recommendation:
{weather_text}
3. Daily quote:
{quote_text}
4. Short summary (3-5 lines) of The Rundown AI newsletter:
{rundown_text if rundown_text else '(no email available today)'}
{reading_section}
Guidelines:
- Short and flowing, like a real Telegram message
- Casual — friendly, warm, energetic
- Order: greeting → weather → quote → AI summary{' → reading assignment' if reading_today else ''}
- Use emojis in moderation
- End with a short encouraging sentence for the day"""

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": LLM_MODEL,
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = _httpx.post("https://api.anthropic.com/v1/messages", headers=headers, json=payload, timeout=60)
        resp.raise_for_status()
        message = resp.json()["content"][0]["text"]

        print(f"Morning briefing message ({len(message)} chars): {message[:200]}")
        tg_send_message(GADI_TELEGRAM_CHAT_ID, message)
        print(f"Morning briefing sent to {GADI_TELEGRAM_CHAT_ID}")
        return {"status": "sent", "length": len(message)}

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR morning briefing: {e}")
        return {"status": "error", "error": str(e)}


def _do_daily_cost() -> dict:
    """Send Gadi today's Claude API cost."""
    import usage as usage_log
    t = usage_log.get_today_totals()
    usd = t["cost_usd"]
    ils = usd * 3.7
    total_in = t["input"] + t["cache_read"] + t["cache_creation"]
    msg = (
        f"💸 עלות ההתכתבות עם רובין היום:\n"
        f"${usd:.3f}  (~₪{ils:.2f})\n\n"
        f"📊 {t['calls']} קריאות ל-Claude\n"
        f"קלט: {total_in:,} טוקנים (מתוכם {t['cache_read']:,} ממטמון 💾)\n"
        f"פלט: {t['output']:,} טוקנים"
    )
    tg_send_message(GADI_TELEGRAM_CHAT_ID, msg)
    return {"status": "sent", "usd": round(usd, 4), "calls": t["calls"]}


@app.get("/daily-cost")
async def daily_cost(token: str = ""):
    """External-cron fallback for the 20:00 cost report (scheduler is primary)."""
    if token != CRON_SECRET:
        return Response(content="Forbidden", status_code=403)
    if not COST_REPORT_ENABLED:
        return {"status": "disabled"}
    try:
        return await asyncio.to_thread(_do_daily_cost)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}


@app.get("/health")
async def health():
    return {"status": "ok", "agent": "robin", "channel": "telegram", "version": "phase1"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
