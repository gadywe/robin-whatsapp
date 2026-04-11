import httpx
import json
from datetime import datetime
from config import ANTHROPIC_API_KEY, LLM_MODEL, MAX_HISTORY
from database import get_history, save_message
from calendar_tool import get_upcoming_events, create_event, delete_event
from file_tool import create_docx_bytes, create_pdf_bytes, send_document_whatsapp, fetch_link_content

SYSTEM_PROMPT = """אתה רובין - העוזר האישי והמאמן המנטלי של גדי. יש לך שני כובעים:

רובין של בטמן (עוזר אישי):
אתה העוזר הכי אמין שיש. אתה עוזר לגדי לנהל את החיים שלו - תזכורות, משימות, ניהול זמן, תכנון יומי. אתה יודע מה חשוב לו ומה דחוף. אתה יוזם, לא רק מגיב - אם משהו חשוב מתקרב, אתה מזכיר. אתה שומר על דברים שגדי אמר שהוא רוצה לעשות ועוקב אחרי ביצוע.

רובין שארמא (מאמן מנטלי):
אתה שותף לעבודה הפנימית של גדי. אתה עוזר לו בתהליכי התפתחות אישית, בהטמעת הרגלים חדשים, בחשיבה מעמיקה על החיים. אתה שואל שאלות טובות, מעודד רפלקציה, ומחזיק מראה כשצריך. אתה לא שופט, אתה שותף.

איך אתה מדבר:
- עברית תמיד
- כשמדובר במשימות יומיומיות - אתה חבר'מן, קליל, עם הומור
- כשמדובר בעבודה פנימית - אתה רציני יותר, עמוק, אמפתי
- אתה מכיר את גדי ולומד עליו כל הזמן. אתה זוכר מה הוא סיפר לך ומשתמש בזה
- הודעות קצרות וממוקדות, כמו בוואטסאפ אמיתי. לא מאמרים ארוכים

כלים שיש לך:
- גישה ליומן Google של גדי - אתה יכול לראות אירועים ולהוסיף חדשים
- כשגדי שואל על לוח הזמנים שלו, תשתמש בכלי היומן
- כשגדי מבקש להוסיף פגישה/אירוע, תוסיף ליומן

כללים:
- אתה תמיד בצד של גדי
- אתה לא מחכה שיבקשו ממך - אתה יוזם כשצריך
- אתה זוכר הקשרים משיחות קודמות
- אם גדי שיתף משהו אישי, אתה מתייחס לזה ברגישות
- התאריך והשעה הנוכחיים: {current_datetime}"""

TOOLS = [
    {
        "name": "get_upcoming_events",
        "description": "מחזיר את האירועים הקרובים ביומן Google של גדי. השתמש בכלי זה כשגדי שואל על לוח הזמנים, פגישות, מה יש לו היום/השבוע.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "כמה ימים קדימה לבדוק (ברירת מחדל: 7)",
                    "default": 7
                }
            },
            "required": []
        }
    },
    {
        "name": "create_calendar_event",
        "description": "מוסיף אירוע חדש ליומן Google של גדי. השתמש בכלי זה כשגדי מבקש להוסיף פגישה, תזכורת, אירוע.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "כותרת האירוע"
                },
                "start_datetime": {
                    "type": "string",
                    "description": "תאריך ושעת התחלה בפורמט ISO 8601 עם timezone ישראל, למשל: 2026-04-15T14:00:00+03:00"
                },
                "end_datetime": {
                    "type": "string",
                    "description": "תאריך ושעת סיום בפורמט ISO 8601 עם timezone ישראל, למשל: 2026-04-15T15:00:00+03:00"
                },
                "description": {
                    "type": "string",
                    "description": "תיאור האירוע (אופציונלי)"
                },
                "location": {
                    "type": "string",
                    "description": "מיקום האירוע (אופציונלי)"
                }
            },
            "required": ["summary", "start_datetime", "end_datetime"]
        }
    },
    {
        "name": "delete_calendar_event",
        "description": "מוחק אירוע מהיומן לפי ID. השתמש בכלי זה רק לאחר שקיבלת את ה-ID מ-get_upcoming_events.",
        "input_schema": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "ה-ID של האירוע למחיקה"
                }
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "fetch_url",
        "description": "פותח לינק ומחזיר את תוכן הדף. השתמש כשגדי שולח לינק או כשנמצא לינק בקובץ שנשלח.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "ה-URL לפתוח"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "create_document",
        "description": "יוצר קובץ Word או PDF ושולח אותו לגדי בוואטסאפ. השתמש כשגדי מבקש ליצור מסמך, דוח, סיכום, רשימה וכו'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "כותרת המסמך"},
                "content": {"type": "string", "description": "תוכן המסמך (טקסט, שורות חדשות מפרידות בין פסקאות)"},
                "format": {"type": "string", "enum": ["docx", "pdf"], "description": "פורמט הקובץ: docx לWord, pdf ל-PDF"},
                "to": {"type": "string", "description": "מספר הטלפון לשליחה (בפורמט בינלאומי, למשל 972501234567)"}
            },
            "required": ["title", "content", "format", "to"]
        }
    }
]

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


def run_tool(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "get_upcoming_events":
            days = tool_input.get("days", 7)
            events = get_upcoming_events(days=days)
            if not events:
                return "אין אירועים קרובים"
            lines = []
            for e in events:
                start = e["start"].replace("T", " ")[:16] if "T" in e["start"] else e["start"]
                line = f"• {e['summary']} — {start}"
                if e.get("location"):
                    line += f" @ {e['location']}"
                lines.append(line)
            return "\n".join(lines)

        elif tool_name == "create_calendar_event":
            result = create_event(
                summary=tool_input["summary"],
                start_datetime=tool_input["start_datetime"],
                end_datetime=tool_input["end_datetime"],
                description=tool_input.get("description", ""),
                location=tool_input.get("location", ""),
            )
            return f"נוצר: {result.get('summary')} ב-{result.get('start', {}).get('dateTime', '')}"

        elif tool_name == "delete_calendar_event":
            success = delete_event(tool_input["event_id"])
            return "נמחק בהצלחה" if success else "שגיאה במחיקה"

        elif tool_name == "fetch_url":
            return fetch_link_content(tool_input["url"])

        elif tool_name == "create_document":
            fmt = tool_input.get("format", "docx")
            title = tool_input.get("title", "מסמך")
            content = tool_input.get("content", "")
            to = tool_input.get("to", "")
            if fmt == "docx":
                file_bytes = create_docx_bytes(content, title=title)
                mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                filename = f"{title}.docx"
            else:
                file_bytes = create_pdf_bytes(content, title=title)
                mime = "application/pdf"
                filename = f"{title}.pdf"
            send_document_whatsapp(to, file_bytes, mime, filename, caption=title)
            return f"קובץ '{filename}' נשלח בהצלחה"

        else:
            return f"כלי לא מוכר: {tool_name}"

    except Exception as e:
        print(f"ERROR tool {tool_name}: {e}")
        return f"שגיאה בביצוע הכלי: {e}"


def get_response(chat_id: str, user_message: str) -> str:
    save_message(chat_id, "user", user_message)

    history = get_history(chat_id, limit=MAX_HISTORY)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    current_datetime = datetime.now().strftime("%A %d/%m/%Y %H:%M")
    system = SYSTEM_PROMPT.format(current_datetime=current_datetime)

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    # Agentic loop - allow multiple tool calls
    for _ in range(5):
        payload = {
            "model": LLM_MODEL,
            "max_tokens": 1024,
            "system": system,
            "tools": TOOLS,
            "messages": messages,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        stop_reason = data.get("stop_reason")
        content = data.get("content", [])

        if stop_reason == "end_turn":
            # Extract text response
            for block in content:
                if block.get("type") == "text":
                    assistant_message = block["text"]
                    save_message(chat_id, "assistant", assistant_message)
                    return assistant_message
            return "..."

        elif stop_reason == "tool_use":
            # Add assistant message with tool calls
            messages.append({"role": "assistant", "content": content})

            # Run all tools and collect results
            tool_results = []
            for block in content:
                if block.get("type") == "tool_use":
                    tool_result = run_tool(block["name"], block.get("input", {}))
                    print(f"TOOL {block['name']}: {tool_result[:100]}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": tool_result,
                    })

            messages.append({"role": "user", "content": tool_results})

        else:
            break

    return "משהו השתבש, נסה שוב"
