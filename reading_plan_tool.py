import re
from datetime import date
from pathlib import Path

PLAN_FILE = Path(__file__).parent / "plans" / "current_week.md"


def get_today_reading() -> str:
    """Return today's reading assignment from the current week plan, or empty string."""
    if not PLAN_FILE.exists():
        return ""

    content = PLAN_FILE.read_text(encoding="utf-8")
    today = date.today()
    day_pattern = f"{today.day}.{today.month}"

    sections = re.split(r"(?=### )", content)
    for section in sections:
        if day_pattern in section:
            match = re.search(r"\*\*קריאה היום\*\*:(.+)", section)
            if match:
                reading = match.group(1).strip()
                if reading == "אין — יום עמוס." or reading.startswith("אין"):
                    return ""
                return reading
    return ""
