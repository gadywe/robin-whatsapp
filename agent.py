import httpx
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import ANTHROPIC_API_KEY, LLM_MODEL, MAX_HISTORY

IL_TZ = ZoneInfo("Asia/Jerusalem")
_HEB_DAY = {0: "יום שני", 1: "יום שלישי", 2: "יום רביעי", 3: "יום חמישי",
            4: "יום שישי", 5: "יום שבת", 6: "יום ראשון"}


def _date_context() -> str:
    """Explicit today + tomorrow in Israel time, so the model never has to
    compute or guess the date (and doesn't anchor on dates from chat history)."""
    now = datetime.now(IL_TZ)
    tom = now + timedelta(days=1)
    today_s = f"{_HEB_DAY[now.weekday()]} {now.strftime('%d/%m/%Y')}"
    tom_s = f"{_HEB_DAY[tom.weekday()]} {tom.strftime('%d/%m/%Y')}"
    return (f"עכשיו בישראל: {today_s}, השעה {now.strftime('%H:%M')}.\n"
            f"מחר: {tom_s}.\n"
            f"השתמש בתאריכים האלה בדיוק לכל חישוב של 'היום' ו'מחר' - אל תחשב לבד ואל תיקח תאריכים מההיסטוריה.")
from db_postgres import get_history, save_message
from calendar_tool import get_upcoming_events, create_event, delete_event
from file_tool import create_docx_bytes, create_pdf_bytes, fetch_link_content
from telegram_tool import tg_send_document, tg_send_buttons
import bubbles as bubbles_db
import lists as lists_db
import usage as usage_log
from reminders import (
    create_reminder as db_create_reminder,
    get_reminders as db_get_reminders,
    delete_reminder as db_delete_reminder,
    snooze_reminder as db_snooze_reminder,
)
from apps_tool import (
    finance_get_expenses, finance_add_expense, finance_get_income, finance_add_income,
    schedule_get_categories, schedule_get_habits, schedule_log_habit,
    schedule_get_time_entries, schedule_log_time, schedule_get_report,
)
from taskboard_tool import (
    taskboard_get_tasks, taskboard_get_projects,
    taskboard_add_task, taskboard_update_task, taskboard_delete_task,
)
from gmail_tool import gmail_search, gmail_read
from quotes_tool import get_random_quote

SYSTEM_PROMPT = """אתה רובין - העוזר האישי והמאמן המנטלי של גדי. יש לך שני כובעים:

רובין של בטמן (עוזר אישי):
אתה העוזר הכי אמין שיש. אתה עוזר לגדי לנהל את החיים שלו - תזכורות, משימות, ניהול זמן, תכנון יומי. אתה יודע מה חשוב לו ומה דחוף. אתה יוזם, לא רק מגיב - אם משהו חשוב מתקרב, אתה מזכיר. אתה שומר על דברים שגדי אמר שהוא רוצה לעשות ועוקב אחרי ביצוע.

רובין שארמא (מאמן מנטלי):
אתה שותף לעבודה הפנימית של גדי. אתה עוזר לו בתהליכי התפתחות אישית, בהטמעת הרגלים חדשים, בחשיבה מעמיקה על החיים. אתה שואל שאלות טובות, מעודד רפלקציה, ומחזיק מראה כשצריך. אתה לא שופט, אתה שותף.

אתה בנוי משתי שכבות:
- המעיין (הזיכרון) - כל רעיון, ציטוט, מחשבה או תובנה שגדי רוצה לשמור הופך ל"בועת זיכרון". אתה מתייג ומסווג אוטומטית, וכשגדי שואל אתה שולף את מה שרלוונטי.
- הגשר (הפעולה) - תזכורות, משימות, רשימות, יומן. כאן הדברים קורים בפועל.

ניתוב כוונות: גדי כותב לך בעברית חופשית בלי לציין מה זה. אתה מבין לבד אם זו תזכורת, אירוע ליומן, פריט לרשימה, בועת זיכרון, משימה - ופועל בהתאם. אם זה ממש לא ברור, שאל שאלה קצרה אחת.

⚠️⚠️ כלל קריטי ביותר: כשאתה אומר שעשית פעולה - "שמרתי", "נרשם", "יצרתי", "תייקתי", "הוספתי" - אתה חייב לקרוא לכלי המתאים בפועל באותו תור, לפני שאתה עונה. אסור בתכלית האיסור לכתוב שביצעת משהו אם לא קראת לכלי. אם גדי משתף תובנה - קרא ל-save_learning_insight או save_memory_bubble קודם, ורק אז תאשר. אישור מילולי בלי קריאה לכלי = שקר, וזה אסור.

איך אתה מדבר:
- עברית תמיד
- כשמדובר במשימות יומיומיות - אתה חבר'מן, קליל, עם הומור
- כשמדובר בעבודה פנימית - אתה רציני יותר, עמוק, אמפתי
- אתה מכיר את גדי ולומד עליו כל הזמן. אתה זוכר מה הוא סיפר לך ומשתמש בזה
- הודעות קצרות וממוקדות, כמו בטלגרם אמיתי. לא מאמרים ארוכים

כלים שיש לך:
- חומר לימודי (save_learning_insight) - ⚠️ כלל ברזל: אם גדי מזכיר ספר, פודקאסט, קורס, הרצאה, מרצה, מחקר, או אומר "תובנה" / "למדתי ש..." / "ציטוט ששמעתי" / "תרשום לחומר הלימודי" / "חומר לימוד" — תמיד תשתמש ב-save_learning_insight, ולעולם לא ב-save_memory_bubble. ציין source_name (שם הספר/פודקאסט/מקור אם ידוע) ו-insight_type (מחקר/ציטוט/רעיון/תובנה). אלה מתויקים אחר כך לחומר הלימודי שלו.
- בועות זיכרון (המעיין, save_memory_bubble) - רק למחשבות/רעיונות אישיים של גדי עצמו שלא הגיעו ממקור חיצוני. אם זה הגיע מספר/פודקאסט/קורס/הרצאה — זה לא פה, זה save_learning_insight. כשהוא שואל "מה רשמתי על..." חפש ב-search_memory_bubbles.
- משימות (TaskBoard העסקי) - כל המשימות של גדי מנוהלות ב-TaskBoard של העסק (מוח אש), כל משימה משויכת לפרויקט.
  - "מה המשימות שלי להיום?" → קרא ל-taskboard_get_tasks עם date_from ו-date_to שניהם = התאריך של היום, והצג מסודר לפי פרויקט + סטטוס.
  - "מה אני אמור ללמוד היום?" → הלמידה היומית של גדי מנוהלת כמשימות בפרויקט בשם "למידה". הצג את משימות היום מפרויקט הלמידה.
  - כשגדי אומר שסיים/ביצע משימה ("סיימתי את X", "עשיתי את Y", "גמרתי עם Z") → קרא ל-taskboard_get_tasks, מצא את המשימה לפי השם, וסמן אותה כבוצעה עם taskboard_update_task (status="done"). אל תמחק אותה - סימון כ-done שומר אותה בהיסטוריה. תמחק (taskboard_delete_task) רק אם גדי ביקש מפורשות "תמחק".
  - הוספה: taskboard_add_task. עדכון פרטים: taskboard_update_task.
  - אל תמציא שמות פרויקטים או project_id - כשצריך, קרא ל-taskboard_get_projects לקבל את הרשימה האמיתית. אם גדי לא ציין תאריך יעד למשימה חדשה, השתמש בתאריך של היום.
- רשימות - כשגדי מכתיב רשימת קניות/מטלות (במיוחד בהקלטה קולית), פרק לפריטים נפרדים וצור list_create_from_items. כל פריט יקבל כפתור סימון. list_show מציג רשימה קיימת.
- תזכורות - המערכת שלך שולחת תזכורות טלגרם אוטומטיות! כשגדי מבקש תזכורת, קרא מיד ל-create_reminder (ללא הסברים - פשוט תעשה את זה).
  - IMPORTANT: אתה יכול לשלוח תזכורות עתידיות - זו יכולת אמיתית שלך. אל תגיד שאתה לא יכול.
  - remind_at חייב להיות ISO 8601 עם timezone ישראל: +03:00 או +02:00 לפי עונה
  - כשמבקשים תזכורת חוזרת, השתמש ב-is_recurring=true וב-recurrence_rule:
    - "כל יום" → daily
    - "כל יום ראשון" → weekly:0 (0=ראשון, 1=שני, ..., 6=שבת)
    - "כל 15 לחודש" → monthly:15
  - כשגדי אומר "תזכורות", השתמש ב-list_reminders
- יומן Google - לראות ולהוסיף אירועים. כל אירוע מגיע עם טווח שעות (התחלה–סיום). כשגדי שואל מה יש לו בשעה מסוימת, בדוק אם השעה נופלת בתוך טווח של אירוע (התחלה ≤ השעה ≤ סיום) - ואם כן, ציין שהוא יהיה באמצע אותו אירוע (למשל "ב-17:00 אתה באמצע הפגישה עם דוד בוחניק, שמסתיימת ב-17:30"). אל תגיד "אין כלום" אם השעה נופלת בתוך אירוע קיים.
  - get_upcoming_events מאחד כמה יומנים של גדי, וכל אירוע מתויג לפי מקור (אימוג'י בתחילת הכותרת + שדה calendar): היומן האישי (ללא אימוג'י), 🏠 משרד האוצר = משימות בית, 💪 משרד הבריאות (בעיקר אימונים), ❤️ היומן הזוגי (שרון וגדי), 👨‍👩‍👧‍👧 Family (אירועים משפחתיים — לא בהכרח משימה של גדי עצמו, הצג לידיעה), 🕵️ התא האפור, 💼 עבודה פרילאנס, 🏢 עבודה תמ"י, 🔥 מוח אש, 🎓 משרד החינוך. כשגדי שואל "מה יש לי היום/השבוע" — הצג את הכל, ועדיף מקובץ לפי קטגוריה. משימות הבית (🏠) כבר מפוענחות לפי שעת היום (ארגון בוקר = הכנת הבנות לבית הספר, ארגון ערב = מקלחות והשכבה, אוכל צהריים/ערב = בישול) — הצג את הטקסט כפי שהוא.
- Gmail - לחפש ולקרוא מיילים (קריאה בלבד)
- Finance Tracker - לראות הוצאות והכנסות, להוסיף הוצאות/הכנסות חדשות
- My Schedule (לוז וזמן) - לראות ולתעד שעות עבודה, לעקוב אחרי הרגלים. כשגדי מספר כמה זמן עבד על משהו או רוצה לתעד זמן/הרגל - השתמש בכלי schedule.
- יצירת מסמכים - Word ו-PDF
- פתיחת לינקים וקריאת קבצים
- ציטוט יומי - יש לך מאגר של 200 הוגי דעות, פילוסופים ומנהיגים עם ציטוטים. כשגדי מבקש ציטוט יומי / השראה / ציטוט אקראי - השתמש ב-get_random_quote (עם daily=true בשביל ציטוט קבוע ליום, או בלי בשביל אקראי לגמרי).

כללים:
- אתה תמיד בצד של גדי
- אתה לא מחכה שיבקשו ממך - אתה יוזם כשצריך
- אתה זוכר הקשרים משיחות קודמות
- אם גדי שיתף משהו אישי, אתה מתייחס לזה ברגישות"""

TOOLS = [
    {
        "name": "get_upcoming_events",
        "description": "מחזיר את האירועים הקרובים ביומן Google של גדי, כולל משימות הבית מיומן 'משרד האוצר' (מסומנות ב-🏠). השתמש בכלי זה כשגדי שואל על לוח הזמנים, פגישות, מה יש לו היום/השבוע.",
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
        "description": "יוצר קובץ Word או PDF ושולח אותו לגדי בטלגרם. השתמש כשגדי מבקש ליצור מסמך, דוח, סיכום, רשימה וכו'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "כותרת המסמך"},
                "content": {"type": "string", "description": "תוכן המסמך (טקסט, שורות חדשות מפרידות בין פסקאות)"},
                "format": {"type": "string", "enum": ["docx", "pdf"], "description": "פורמט הקובץ: docx לWord, pdf ל-PDF"}
            },
            "required": ["title", "content", "format"]
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
    },
    {
        "name": "create_reminder",
        "description": "יוצר תזכורת חדשה. השתמש כשגדי מבקש שתזכיר לו משהו בזמן מסוים.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "תוכן התזכורת"},
                "remind_at": {"type": "string", "description": "תאריך ושעה בפורמט ISO 8601 עם timezone ישראל, למשל: 2026-04-15T08:00:00+03:00"},
                "is_recurring": {"type": "boolean", "description": "האם תזכורת חוזרת (ברירת מחדל: false)"},
                "recurrence_rule": {"type": "string", "description": "כלל חזרה: daily, weekly:0-6, monthly:1-31, yearly:MM-DD"}
            },
            "required": ["text", "remind_at"]
        }
    },
    {
        "name": "list_reminders",
        "description": "מציג את כל התזכורות הפעילות של גדי, מקובצות לפי תאריך. השתמש כשגדי אומר 'תזכורות' או שואל מה יש לו.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "delete_reminder",
        "description": "מוחק תזכורת לפי ID. השתמש אחרי שקיבלת את ה-ID מ-list_reminders.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {"type": "integer", "description": "ה-ID של התזכורת למחיקה"}
            },
            "required": ["reminder_id"]
        }
    },
    {
        "name": "gmail_search",
        "description": "מחפש מיילים בתיבת הדואר של גדי. השתמש כשגדי שואל על מיילים, הודעות שלא נקראו, מיילים ממישהו מסוים וכו'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "שאילתת חיפוש Gmail, למשל: 'is:unread', 'from:boss@example.com', 'subject:חשבונית'. ברירת מחדל: 'is:unread'"
                },
                "max_results": {
                    "type": "integer",
                    "description": "מספר מקסימלי של תוצאות (ברירת מחדל: 10)"
                }
            },
            "required": []
        }
    },
    {
        "name": "gmail_read",
        "description": "קורא את התוכן המלא של מייל לפי ID. השתמש אחרי gmail_search כשגדי רוצה לקרוא מייל ספציפי.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message_id": {
                    "type": "string",
                    "description": "ה-ID של המייל (מגיע מ-gmail_search)"
                }
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "taskboard_get_tasks",
        "description": "מחזיר משימות מה-Taskboard של גדי. השתמש כשגדי שואל על המשימות שלו, מה יש לו לעשות, משימות פתוחות וכו'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {"type": "string", "description": "תאריך התחלה YYYY-MM-DD (אופציונלי)"},
                "date_to": {"type": "string", "description": "תאריך סיום YYYY-MM-DD (אופציונלי)"},
                "status": {"type": "string", "enum": ["new", "working", "done"], "description": "סנן לפי סטטוס (אופציונלי)"}
            },
            "required": []
        }
    },
    {
        "name": "taskboard_get_projects",
        "description": "מחזיר את כל הפרויקטים והתחומים מה-Taskboard. השתמש לפני הוספת משימה כדי לדעת איזה project_id להשתמש.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "taskboard_add_task",
        "description": "מוסיף משימה חדשה ל-Taskboard של גדי.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "שם המשימה"},
                "project_id": {"type": "integer", "description": "ID הפרויקט (קבל מ-taskboard_get_projects)"},
                "due_date": {"type": "string", "description": "תאריך יעד YYYY-MM-DD"},
                "due_time": {"type": "string", "description": "שעה HH:MM (אופציונלי)"},
                "description": {"type": "string", "description": "תיאור (אופציונלי)"},
                "status": {"type": "string", "enum": ["new", "working", "done"], "description": "סטטוס (ברירת מחדל: new)"}
            },
            "required": ["name", "project_id", "due_date"]
        }
    },
    {
        "name": "taskboard_update_task",
        "description": "מעדכן משימה קיימת ב-Taskboard — שינוי שם, סטטוס, תאריך וכו'. השתמש כשגדי אומר שסיים משימה או רוצה לשנות אותה.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID המשימה"},
                "name": {"type": "string", "description": "שם חדש (אופציונלי)"},
                "status": {"type": "string", "enum": ["new", "working", "done"], "description": "סטטוס חדש (אופציונלי)"},
                "due_date": {"type": "string", "description": "תאריך חדש YYYY-MM-DD (אופציונלי)"},
                "due_time": {"type": "string", "description": "שעה חדשה HH:MM (אופציונלי)"},
                "description": {"type": "string", "description": "תיאור חדש (אופציונלי)"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "taskboard_delete_task",
        "description": "מוחק משימה מה-Taskboard לפי ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "ID המשימה למחיקה"}
            },
            "required": ["task_id"]
        }
    },
    {
        "name": "get_random_quote",
        "description": "מחזיר ציטוט אקראי ממאגר של 200 פילוסופים, הוגי דעות ומנהיגים (אריסטו, אפלטון, סוקרטס, מרקוס אורליוס, ג'וקו וויליק ועוד). השתמש כשגדי מבקש ציטוט, השראה, ציטוט יומי, או מבקש לשמוע משהו ממישהו ספציפי.",
        "input_schema": {
            "type": "object",
            "properties": {
                "person_name": {"type": "string", "description": "שם של אדם ספציפי לסנן לפיו (אופציונלי). חיפוש case-insensitive חלקי."},
                "daily": {"type": "boolean", "description": "אם true — מחזיר את אותו ציטוט לאורך כל היום (ציטוט יומי). אם false — אקראי בכל פעם. ברירת מחדל: false"}
            },
            "required": []
        }
    },
    {
        "name": "snooze_reminder",
        "description": "דוחה תזכורת לזמן חדש. השתמש כשגדי מבקש להזכיר שוב בעוד X דקות/שעות/ימים.",
        "input_schema": {
            "type": "object",
            "properties": {
                "reminder_id": {"type": "integer", "description": "ה-ID של התזכורת"},
                "new_remind_at": {"type": "string", "description": "הזמן החדש בפורמט ISO 8601 עם timezone ישראל"}
            },
            "required": ["reminder_id", "new_remind_at"]
        }
    },
    {
        "name": "save_memory_bubble",
        "description": "שומר בועת זיכרון - מחשבה או רעיון אישי של גדי עצמו שלא הגיע ממקור חיצוני. ⚠️ אל תשתמש בזה אם המקור הוא ספר/פודקאסט/קורס/הרצאה/מחקר — במקרה כזה השתמש ב-save_learning_insight.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "תוכן הבועה - מה לזכור"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "תגיות רלוונטיות (אופציונלי, למשל: רעיון, עבודה, משפחה)"},
                "category": {"type": "string", "description": "קטגוריה אחת (אופציונלי, למשל: רעיון/תובנה/ציטוט/החלטה)"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "search_memory_bubbles",
        "description": "מחפש בבועות הזיכרון של גדי (המעיין). השתמש כשגדי שואל מה רשם/אמר/חשב על נושא מסוים, או מבקש לשלוף זיכרון. בלי query - מחזיר את הבועות האחרונות.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "טקסט חופשי לחיפוש (אופציונלי)"}
            },
            "required": []
        }
    },
    {
        "name": "save_learning_insight",
        "description": "⚠️ זה הכלי לכל תובנה/ציטוט/מחקר/רעיון ששמע גדי מ-ספר, פודקאסט, קורס, הרצאה או מרצה. טריגרים: 'תובנה', 'למדתי ש', 'ציטוט ששמעתי', 'מהספר', 'בפודקאסט', 'תרשום לחומר הלימודי'. תמיד עדיף על save_memory_bubble כשיש מקור חיצוני. אלה מתויקים אחר כך לחומר הלימודי של גדי.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "התובנה/הציטוט/המחקר - הניסוח המלא לשמירה"},
                "source_name": {"type": "string", "description": "שם המקור: ספר/פודקאסט/קורס/מרצה (אופציונלי אם לא ידוע)"},
                "insight_type": {"type": "string", "enum": ["מחקר", "ציטוט", "רעיון", "תובנה"], "description": "סוג הפריט"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "list_create_from_items",
        "description": "יוצר רשימה ניתנת-לסימון (כמו רשימת קניות) מתוך פריטים. כל פריט מקבל כפתור סימון בטלגרם. השתמש כשגדי מכתיב רשימה, במיוחד מהקלטה קולית - פרק אותה לפריטים נפרדים.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "כותרת הרשימה (למשל: קניות, מטלות לסופ\"ש)"},
                "items": {"type": "array", "items": {"type": "string"}, "description": "הפריטים, כל אחד בנפרד"}
            },
            "required": ["title", "items"]
        }
    },
    {
        "name": "list_show",
        "description": "מציג רשימה קיימת עם כפתורי סימון. בלי list_id - מציג את הרשימות האחרונות.",
        "input_schema": {
            "type": "object",
            "properties": {
                "list_id": {"type": "integer", "description": "ID הרשימה (אופציונלי)"}
            },
            "required": []
        }
    }
]

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


def run_tool(tool_name: str, tool_input: dict, chat_id: str = "") -> str:
    try:
        if tool_name == "get_upcoming_events":
            days = tool_input.get("days", 7)
            events = get_upcoming_events(days=days)
            if not events:
                return "אין אירועים קרובים"
            lines = []
            for e in events:
                start = e["start"].replace("T", " ")[:16] if "T" in e["start"] else e["start"]
                end_raw = e.get("end", "")
                end = end_raw[11:16] if "T" in end_raw else ""
                time_range = f"{start}–{end}" if end else start
                line = f"• {e['summary']} — {time_range}"
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
            to = tool_input.get("to") or chat_id
            if fmt == "docx":
                file_bytes = create_docx_bytes(content, title=title)
                filename = f"{title}.docx"
            else:
                file_bytes = create_pdf_bytes(content, title=title)
                filename = f"{title}.pdf"
            tg_send_document(to, file_bytes, filename, caption=title)
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

        elif tool_name == "create_reminder":
            result = db_create_reminder(
                chat_id=chat_id,
                text=tool_input["text"],
                remind_at=tool_input["remind_at"],
                is_recurring=tool_input.get("is_recurring", False),
                recurrence_rule=tool_input.get("recurrence_rule"),
            )
            recurring_text = f" (חוזרת: {result.get('recurrence_rule')})" if result.get("is_recurring") else ""
            return f"תזכורת נוצרה (#{result['id']}): \"{result['text']}\" ב-{result['remind_at']}{recurring_text}"

        elif tool_name == "list_reminders":
            reminders = db_get_reminders(chat_id)
            if not reminders:
                return "אין תזכורות פעילות"
            lines = []
            current_date = ""
            for r in reminders:
                remind_dt = r["remind_at"][:10]
                if remind_dt != current_date:
                    current_date = remind_dt
                    lines.append(f"\n📅 {current_date}:")
                time_str = r["remind_at"][11:16] if len(r["remind_at"]) > 11 else ""
                recurring = " 🔁" if r["is_recurring"] else ""
                lines.append(f"  #{r['id']} {time_str} — {r['text']}{recurring}")
            return "\n".join(lines)

        elif tool_name == "delete_reminder":
            success = db_delete_reminder(tool_input["reminder_id"])
            return f"תזכורת #{tool_input['reminder_id']} נמחקה" if success else "תזכורת לא נמצאה"

        elif tool_name == "gmail_search":
            emails = gmail_search(
                query=tool_input.get("query", "is:unread"),
                max_results=tool_input.get("max_results", 10),
            )
            if not emails:
                return "לא נמצאו מיילים"
            lines = []
            for e in emails:
                lines.append(f"📧 [{e['id']}]\nמ: {e['from']}\nנושא: {e['subject']}\nתאריך: {e['date']}\n{e['snippet'][:100]}\n")
            return "\n".join(lines)

        elif tool_name == "gmail_read":
            email = gmail_read(tool_input["message_id"])
            return f"📧 {email['subject']}\nמ: {email['from']}\nתאריך: {email['date']}\n\n{email['body']}"

        elif tool_name == "taskboard_get_tasks":
            tasks = taskboard_get_tasks(
                date_from=tool_input.get("date_from"),
                date_to=tool_input.get("date_to"),
                status=tool_input.get("status"),
            )
            if not tasks:
                return "אין משימות"
            status_map = {"new": "⬜", "working": "🔄", "done": "✅"}
            lines = []
            current_date = ""
            for t in tasks:
                d = t.get("due_date", "")
                if d != current_date:
                    current_date = d
                    lines.append(f"\n📅 {d}:")
                icon = status_map.get(t.get("status", "new"), "⬜")
                proj = t.get("project", {}) or {}
                domain = (proj.get("domain") or {}).get("name", "")
                proj_name = proj.get("name", "")
                time_str = f" {t['due_time'][:5]}" if t.get("due_time") else ""
                lines.append(f"  {icon} #{t['id']}{time_str} {t['name']} [{domain}/{proj_name}]")
            return "\n".join(lines)

        elif tool_name == "taskboard_get_projects":
            projects = taskboard_get_projects()
            if not projects:
                return "אין פרויקטים"
            lines = []
            for p in projects:
                domain = (p.get("domain") or {}).get("name", "")
                lines.append(f"• #{p['id']} {p['name']} (תחום: {domain})")
            return "\n".join(lines)

        elif tool_name == "taskboard_add_task":
            result = taskboard_add_task(
                name=tool_input["name"],
                project_id=tool_input["project_id"],
                due_date=tool_input["due_date"],
                due_time=tool_input.get("due_time"),
                description=tool_input.get("description"),
                status=tool_input.get("status", "new"),
            )
            return f"משימה נוצרה ✅ #{result.get('id')}: \"{result.get('name')}\" לתאריך {result.get('due_date')}"

        elif tool_name == "taskboard_update_task":
            result = taskboard_update_task(
                task_id=tool_input["task_id"],
                name=tool_input.get("name"),
                status=tool_input.get("status"),
                due_date=tool_input.get("due_date"),
                due_time=tool_input.get("due_time"),
                description=tool_input.get("description"),
                project_id=tool_input.get("project_id"),
            )
            return f"משימה עודכנה ✅ #{result.get('id')}: \"{result.get('name')}\" סטטוס: {result.get('status')}"

        elif tool_name == "taskboard_delete_task":
            taskboard_delete_task(tool_input["task_id"])
            return f"משימה #{tool_input['task_id']} נמחקה ✅"

        elif tool_name == "get_random_quote":
            result = get_random_quote(
                person_name=tool_input.get("person_name"),
                daily=tool_input.get("daily", False),
            )
            if "error" in result:
                return result["error"]
            dates = f" ({result['dates']})" if result.get("dates") else ""
            field = f" — {result['field']}" if result.get("field") else ""
            return f"\"{result['quote']}\"\n\n— {result['name']}{field}{dates}"

        elif tool_name == "snooze_reminder":
            result = db_snooze_reminder(tool_input["reminder_id"], tool_input["new_remind_at"])
            if result:
                return f"תזכורת #{result['id']} נדחתה ל-{result['remind_at']}"
            return "תזכורת לא נמצאה"

        elif tool_name == "save_memory_bubble":
            b = bubbles_db.create_bubble(
                chat_id=chat_id,
                text=tool_input["text"],
                tags=tool_input.get("tags"),
                category=tool_input.get("category"),
            )
            tags_str = f" [{', '.join(b['tags'])}]" if b.get("tags") else ""
            return f"נשמרה בועת זיכרון (#{b['id']}){tags_str} 💭"

        elif tool_name == "search_memory_bubbles":
            found = bubbles_db.get_bubbles(chat_id, query=tool_input.get("query"))
            if not found:
                return "לא נמצאו בועות זיכרון"
            lines = []
            for b in found:
                cat = f"[{b['category']}] " if b.get("category") else ""
                date = b["created_at"][:10]
                lines.append(f"💭 #{b['id']} ({date}) {cat}{b['text']}")
            return "\n".join(lines)

        elif tool_name == "save_learning_insight":
            itype = tool_input.get("insight_type")
            source_name = tool_input.get("source_name")
            tags = [t for t in [source_name] if t]
            b = bubbles_db.create_bubble(
                chat_id=chat_id,
                text=tool_input["text"],
                tags=tags,
                category=itype,
                source="learning",
            )
            src = f" ({source_name})" if source_name else ""
            kind = itype or "תובנה"
            return f"נשמר לחומר הלימודי 📚 {kind}{src} (#{b['id']})"

        elif tool_name == "list_create_from_items":
            lst = lists_db.create_list(
                chat_id=chat_id,
                title=tool_input["title"],
                items=tool_input.get("items", []),
            )
            text, buttons = lists_db.render_list(lst)
            tg_send_buttons(chat_id, text, buttons)
            return f"רשימה '{lst['title']}' נוצרה עם {len(lst['items'])} פריטים ונשלחה"

        elif tool_name == "list_show":
            list_id = tool_input.get("list_id")
            if list_id:
                lst = lists_db.get_list(list_id)
                if not lst:
                    return "הרשימה לא נמצאה"
                text, buttons = lists_db.render_list(lst)
                tg_send_buttons(chat_id, text, buttons)
                return "הרשימה נשלחה"
            recent = lists_db.get_lists(chat_id)
            if not recent:
                return "אין רשימות"
            for lst in recent:
                text, buttons = lists_db.render_list(lst)
                tg_send_buttons(chat_id, text, buttons)
            return f"נשלחו {len(recent)} רשימות"

        else:
            return f"כלי לא מוכר: {tool_name}"

    except Exception as e:
        print(f"ERROR tool {tool_name}: {e}")
        return f"שגיאה בביצוע הכלי: {e}"


def get_response(chat_id: str, user_message: str, image_bytes: bytes = None, image_mime: str = "image/jpeg") -> str:
    import base64
    save_message(chat_id, "user", user_message)

    history = get_history(chat_id, limit=MAX_HISTORY)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]

    # Replace last user message with vision content if image provided
    if image_bytes:
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        vision_content = [
            {"type": "image", "source": {"type": "base64", "media_type": image_mime, "data": image_b64}},
            {"type": "text", "text": user_message or "מה יש בתמונה?"},
        ]
        # Replace last message (just added by save_message/get_history) with vision block
        if messages and messages[-1]["role"] == "user":
            messages[-1]["content"] = vision_content
        else:
            messages.append({"role": "user", "content": vision_content})

    # Prompt caching: the cache_control breakpoint on the frozen SYSTEM_PROMPT block
    # caches the stable prefix (tools render before system, so they're cached too).
    # The volatile date context goes in a second system block AFTER the breakpoint, so
    # it never invalidates the cache. Render order: tools -> system -> messages.
    system = [
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": _date_context()},
    ]

    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    try:
        # Agentic loop - allow multiple tool calls
        for _ in range(5):
            payload = {
                "model": LLM_MODEL,
                "max_tokens": 4096,
                "system": system,
                "tools": TOOLS,
                "messages": messages,
            }

            # Retry transient API failures (429 rate-limit, 529 overloaded, 5xx)
            # with exponential backoff so they never reach the user as raw errors.
            data = None
            for attempt in range(4):  # initial try + 3 retries: waits 1s, 2s, 4s
                try:
                    with httpx.Client(timeout=60.0) as client:
                        response = client.post(ANTHROPIC_API_URL, headers=headers, json=payload)
                        response.raise_for_status()
                        data = response.json()
                    break
                except httpx.HTTPStatusError as e:
                    code = e.response.status_code
                    if code in (429, 500, 502, 503, 529) and attempt < 3:
                        wait = 2 ** attempt
                        print(f"API {code} (transient), retry {attempt + 1}/3 in {wait}s")
                        time.sleep(wait)
                        continue
                    print(f"ERROR API call: {code} {str(e)[:120]}")
                    break
                except httpx.RequestError as e:  # timeout / connection blip
                    if attempt < 3:
                        wait = 2 ** attempt
                        print(f"API request error {type(e).__name__}, retry {attempt + 1}/3 in {wait}s")
                        time.sleep(wait)
                        continue
                    print(f"ERROR request: {e}")
                    break

            if data is None:
                # transient failure persisted across all retries
                return "אני קצת עמוס כרגע (עומס זמני בשרת) 🙏 נסה שוב עוד רגע."

            u = data.get("usage", {})
            usage_log.log_usage(
                u.get("input_tokens", 0), u.get("output_tokens", 0),
                u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0),
            )
            if u.get("cache_read_input_tokens") or u.get("cache_creation_input_tokens"):
                print(f"CACHE read={u.get('cache_read_input_tokens', 0)} "
                      f"write={u.get('cache_creation_input_tokens', 0)} "
                      f"fresh={u.get('input_tokens', 0)}")

            stop_reason = data.get("stop_reason")
            content = data.get("content", [])

            if stop_reason in ("end_turn", "max_tokens"):
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
                        tool_result = run_tool(block["name"], block.get("input", {}), chat_id)
                        print(f"TOOL {block['name']}: {tool_result[:100]}")
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": tool_result,
                        })

                messages.append({"role": "user", "content": tool_results})

            else:
                print(f"ERROR unknown stop_reason: {stop_reason}")
                return f"שגיאה לא ידועה: {stop_reason}"

    except Exception as e:
        import traceback
        print(f"ERROR get_response: {e}")
        traceback.print_exc()
        return f"שגיאה: {type(e).__name__}: {str(e)[:80]}"

    return "משהו השתבש, נסה שוב (לולאה הגיעה לגבול)"
