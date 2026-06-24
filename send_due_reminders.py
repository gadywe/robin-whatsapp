#!/usr/bin/env python3
"""
Independent reminder sender — runs in GitHub Actions every 5 minutes, completely
decoupled from the Render web service.

Why this exists: Render's free tier spins the bot down after ~15 min idle, and the
750h/month cap can suspend it for days. The in-process APScheduler only fires while
that process is awake, so reminders arrived hours late (or not at all). This sender
talks STRAIGHT to Neon + Telegram from a GitHub runner that never sleeps, so a due
reminder goes out even when Robin itself is asleep, recycling, or suspended.

It mirrors main._do_check_reminders exactly and reuses the same DB helpers, so the
delivery logic stays single-sourced. get_due_reminders atomically claims rows
(active -> sending), so running this alongside Robin's own in-process scheduler can
never double-send the same reminder.

Note: this path is intentionally NOT gated by REMINDERS_ENABLED — that flag controls
Robin's in-process scheduler; this external sender is the reliable floor and always
delivers what is due.
"""
from reminders import (
    get_due_reminders,
    mark_reminder_sent,
    advance_recurring_reminder,
    snooze_reminder,
)
from telegram_tool import tg_send_buttons


def main() -> int:
    due = get_due_reminders()
    sent = 0
    for r in due:
        try:
            body = f"⏰ תזכורת:\n{r['text']}"
            buttons = [
                {"text": "מחק", "data": f"reminder_delete_{r['id']}"},
                {"text": "הזכר שוב", "data": f"reminder_snooze_{r['id']}"},
            ]
            tg_send_buttons(r["chat_id"], body, buttons)

            if r["is_recurring"]:
                advance_recurring_reminder(r["id"])
            else:
                mark_reminder_sent(r["id"])
            sent += 1
        except Exception as e:
            print(f"ERROR sending reminder {r['id']}: {e}")
            # Re-arm (status -> active, same remind_at) instead of killing it, so a
            # transient failure retries next run and a recurring reminder only
            # advances after it truly sends. Matches main._do_check_reminders.
            try:
                snooze_reminder(r["id"], r["remind_at"])
            except Exception as e2:
                print(f"ERROR re-arming reminder {r['id']}: {e2}")
    print(f"due={len(due)} sent={sent}")
    return sent


if __name__ == "__main__":
    main()
