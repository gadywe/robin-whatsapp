#!/usr/bin/env python3
"""
Independent daily cost-report sender — runs in GitHub Actions, triggered once a day
at 20:00 Asia/Jerusalem by cron-job.org → workflow_dispatch.

Same rationale as send_due_reminders.py: Render's free tier sleeps/suspends, so the
in-process scheduler may not be awake at 20:00 to fire the report. This computes the
cost straight from Neon and sends it to Gadi's Telegram from a runner that never
sleeps. Mirrors main._do_daily_cost and reuses usage.py + telegram_tool.py.

The in-process daily_cost job was removed from main.py so this is the sole sender —
no duplicate message. get_today_totals() bounds "today" by Asia/Jerusalem in SQL,
so the day boundary is correct regardless of where this runs.
"""
from config import GADI_TELEGRAM_CHAT_ID
import usage as usage_log
from telegram_tool import tg_send_message


def main():
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
    print(f"cost report sent: usd={usd:.4f} calls={t['calls']}")


if __name__ == "__main__":
    main()
