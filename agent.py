import httpx
import json
from datetime import datetime
from config import ANTHROPIC_API_KEY, LLM_MODEL, MAX_HISTORY
from db_postgres import get_history, save_message
from calendar_tool import get_upcoming_events, create_event, delete_event
from file_tool import create_docx_bytes, create_pdf_bytes, send_document_whatsapp, fetch_link_content
from apps_tool import (
    finance_get_expenses, finance_add_expense, finance_get_income, finance_add_income,
    schedule_get_categories, schedule_get_habits, schedule_log_habit,
    schedule_get_time_entries, schedule_log_time, schedule_get_report,
)

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
- יומן Google - לראות ולהוסיף אירועים
- Finance Tracker - לראות הוצאות והכנסות, להוסיף הוצאות/הכנסות חדשות
- My Schedule - לראות ולתעד שעות עבודה, לעקוב אחרי הרגלים
- יצירת מסמכים - Word ו-PDF
- פתיחת לינקים וקריאת קבצים

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
    },
    {
        "name": "finance_get_expenses",
        "description": "מחזיר הוצאות מה-Finance Tracker של גדי. השתמש כשגדי שואל על הוצאות, כמה הוציא החודש, סיכום פיננסי וכו'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "שנה (ברירת מחדל: השנה הנוכחית)"},
                "month": {"type": "integer", "description": "חודש 1-12 (אופציונלי, בלי זה מחזיר את כל השנה)"}
            },
            "required": []
        }
    },
    {
        "name": "finance_add_expense",
        "description": "מוסיף הוצאה חדשה ל-Finance Tracker. השתמש כשגדי מספר שהוציא כסף על משהו.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "תאריך בפורמט YYYY-MM-DD"},
                "category": {"type": "string", "description": "קטגוריה (למשל: מזון, תחבורה, בילויים)"},
                "description": {"type": "string", "description": "תיאור ההוצאה"},
                "amount": {"type": "number", "description": "סכום בשקלים"},
                "payment_method": {"type": "string", "description": "אמצעי תשלום: אשראי / מזומן / ביט (ברירת מחדל: אשראי)"},
                "group": {"type": "string", "description": "קבוצה/סוג הוצאה (אופציונלי)"}
            },
            "required": ["date", "category", "description", "amount"]
        }
    },
    {
        "name": "finance_get_income",
        "description": "מחזיר את כל הכנסות גדי מה-Finance Tracker. השתמש כשגדי שואל על הכנסות, פרויקטים, תשלומים צפויים.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "finance_add_income",
        "description": "מוסיף הכנסה חדשה ל-Finance Tracker. השתמש כשגדי מספר על פרויקט חדש או תשלום שקיבל/צפוי.",
        "input_schema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "שם הפרויקט"},
                "income_type": {"type": "string", "description": "סוג ההכנסה (למשל: משחק, כתיבת מחזות, הוראה)"},
                "amount": {"type": "number", "description": "סכום בשקלים"},
                "end_date": {"type": "string", "description": "תאריך סיום הפרויקט YYYY-MM-DD"},
                "pay_date": {"type": "string", "description": "תאריך תשלום צפוי YYYY-MM-DD"},
                "status": {"type": "string", "enum": ["paid", "expected"], "description": "שולם / צפוי"},
                "owner": {"type": "string", "description": "גדי / שרון / כללי"},
                "note": {"type": "string", "description": "הערה (אופציונלי)"}
            },
            "required": ["project", "income_type", "amount", "end_date", "pay_date"]
        }
    },
    {
        "name": "schedule_get_categories",
        "description": "מחזיר את כל הקטגוריות והפעילויות מה-Schedule של גדי, כולל ה-IDs שלהם. השתמש לפני שאתה מתעד זמן כדי לדעת איזה activity_id להשתמש.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "schedule_get_habits",
        "description": "מחזיר את רשימת ההרגלים של גדי ואת הסטטוס שלהם להיום (או לתאריך ספציפי). השתמש כשגדי שואל על ההרגלים שלו.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "תאריך YYYY-MM-DD (ברירת מחדל: היום)"}
            },
            "required": []
        }
    },
    {
        "name": "schedule_log_habit",
        "description": "מסמן הרגל כבוצע. השתמש כשגדי אומר שעשה משהו מרשימת ההרגלים שלו.",
        "input_schema": {
            "type": "object",
            "properties": {
                "habit_id": {"type": "integer", "description": "ה-ID של ההרגל (קבל מ-schedule_get_habits)"},
                "date": {"type": "string", "description": "תאריך YYYY-MM-DD (ברירת מחדל: היום)"},
                "value": {"type": "integer", "description": "ערך (ברירת מחדל: 1)"}
            },
            "required": ["habit_id"]
        }
    },
    {
        "name": "schedule_get_time_entries",
        "description": "מחזיר את רשומות הזמן של גדי לתאריך מסוים. השתמש כשגדי שואל מה עשה היום / כמה שעות עבד.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "תאריך YYYY-MM-DD (ברירת מחדל: היום)"}
            },
            "required": []
        }
    },
    {
        "name": "schedule_log_time",
        "description": "מתעד שעות עבודה/פעילות ב-Schedule. השתמש כשגדי אומר שעבד על משהו או רוצה לתעד זמן. קבל קודם את ה-activity_id מ-schedule_get_categories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "activity_id": {"type": "integer", "description": "ה-ID של הפעילות"},
                "date": {"type": "string", "description": "תאריך YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "שעת התחלה HH:MM"},
                "end_time": {"type": "string", "description": "שעת סיום HH:MM (אופציונלי)"},
                "notes": {"type": "string", "description": "הערות (אופציונלי)"}
            },
            "required": ["activity_id", "date", "start_time"]
        }
    },
    {
        "name": "schedule_get_report",
        "description": "מחזיר דוח רבעוני של שעות עבודה לפי קטגוריה מה-Schedule. השתמש כשגדי רוצה לראות סיכום כמה שעות השקיע בכל תחום.",
        "input_schema": {
            "type": "object",
            "properties": {
                "year": {"type": "integer", "description": "שנה (ברירת מחדל: השנה הנוכחית)"},
                "quarter": {"type": "integer", "description": "רבעון 1-4 (ברירת מחדל: הרבעון הנוכחי)"}
            },
            "required": []
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

        elif tool_name == "finance_get_expenses":
            expenses = finance_get_expenses(
                year=tool_input.get("year"),
                month=tool_input.get("month"),
            )
            if not expenses:
                return "לא נמצאו הוצאות"
            total = sum(e.get("amount", 0) for e in expenses)
            lines = [f"סה\"כ {len(expenses)} הוצאות, סכום כולל: ₪{total:,.0f}\n"]
            for e in expenses[:30]:
                lines.append(f"• {e.get('date','')} | {e.get('category','')} | {e.get('description','')} | ₪{e.get('amount',0):,.0f} | {e.get('paymentMethod','')}")
            if len(expenses) > 30:
                lines.append(f"... ועוד {len(expenses)-30} הוצאות")
            return "\n".join(lines)

        elif tool_name == "finance_add_expense":
            result = finance_add_expense(
                date=tool_input["date"],
                category=tool_input["category"],
                description=tool_input["description"],
                amount=tool_input["amount"],
                payment_method=tool_input.get("payment_method", "אשראי"),
                group=tool_input.get("group", ""),
            )
            return f"נוספה הוצאה: {result.get('description')} ₪{result.get('amount')} בתאריך {result.get('date')}"

        elif tool_name == "finance_get_income":
            jobs = finance_get_income()
            if not jobs:
                return "לא נמצאו הכנסות"
            lines = []
            for j in jobs:
                status = "שולם ✓" if j.get("status") == "paid" else "צפוי"
                lines.append(f"• {j.get('project')} | {j.get('type')} | ₪{j.get('amount',0):,.0f} | {status} | תשלום: {j.get('payDate','')}")
            return "\n".join(lines)

        elif tool_name == "finance_add_income":
            result = finance_add_income(
                project=tool_input["project"],
                income_type=tool_input["income_type"],
                amount=tool_input["amount"],
                end_date=tool_input["end_date"],
                pay_date=tool_input["pay_date"],
                status=tool_input.get("status", "expected"),
                owner=tool_input.get("owner", "גדי"),
                note=tool_input.get("note", ""),
            )
            return f"נוספה הכנסה: {result.get('project')} ₪{result.get('amount'):,.0f}"

        elif tool_name == "schedule_get_categories":
            cats = schedule_get_categories()
            lines = []
            for c in cats:
                lines.append(f"📁 {c['name']} (id:{c['id']})")
                for a in c.get("activities", []):
                    lines.append(f"   • {a['name']} (id:{a['id']})")
            return "\n".join(lines) if lines else "לא נמצאו קטגוריות"

        elif tool_name == "schedule_get_habits":
            data = schedule_get_habits(date=tool_input.get("date"))
            habits = data["habits"]
            if not habits:
                return "לא נמצאו הרגלים"
            lines = [f"הרגלים לתאריך {data['date']}:"]
            for h in habits:
                status = "✅" if h["done"] else "⬜"
                lines.append(f"{status} {h['emoji']} {h['name']} (id:{h['id']})")
            return "\n".join(lines)

        elif tool_name == "schedule_log_habit":
            result = schedule_log_habit(
                habit_id=tool_input["habit_id"],
                date=tool_input.get("date"),
                value=tool_input.get("value", 1),
            )
            return f"הרגל סומן כבוצע ✅ (id:{result.get('habitId')}, תאריך:{result.get('date')})"

        elif tool_name == "schedule_get_time_entries":
            entries = schedule_get_time_entries(date=tool_input.get("date"))
            if not entries:
                return "אין רשומות זמן לתאריך זה"
            total_min = sum(e.get("durationMinutes") or 0 for e in entries)
            lines = [f"רשומות זמן — סה\"כ {total_min//60}:{total_min%60:02d} שעות:"]
            for e in entries:
                dur = e.get("durationMinutes") or 0
                lines.append(f"• {e.get('categoryName')} / {e.get('activityName')} | {e.get('startTime','')}-{e.get('endTime','?')} ({dur} דק')")
            return "\n".join(lines)

        elif tool_name == "schedule_log_time":
            result = schedule_log_time(
                activity_id=tool_input["activity_id"],
                date=tool_input["date"],
                start_time=tool_input["start_time"],
                end_time=tool_input.get("end_time"),
                notes=tool_input.get("notes"),
            )
            return f"זמן נרשם ✅ (activity:{result.get('activityId')}, {result.get('startTime')}-{result.get('endTime','פתוח')})"

        elif tool_name == "schedule_get_report":
            data = schedule_get_report(
                year=tool_input.get("year"),
                quarter=tool_input.get("quarter"),
            )
            q = data.get("quarter", {})
            report = data.get("report", [])
            lines = [f"דוח רבעון {q.get('quarter')}/{q.get('year')}:"]
            for cat in report:
                lines.append(f"• {cat['categoryName']}: ממוצע {cat['weeklyAverage']} שעות/שבוע")
            return "\n".join(lines)

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
