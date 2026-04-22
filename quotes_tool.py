"""Random quote tool — pulls from quotes_data.json (Daily Quote project)."""
import json
import os
import random
from datetime import date
from typing import Optional

_DATA_PATH = os.path.join(os.path.dirname(__file__), "quotes_data.json")
_PEOPLE: Optional[list] = None


def _load() -> list:
    global _PEOPLE
    if _PEOPLE is None:
        with open(_DATA_PATH, "r", encoding="utf-8") as f:
            _PEOPLE = json.load(f)
    return _PEOPLE


def get_random_quote(person_name: Optional[str] = None, daily: bool = False) -> dict:
    people = _load()

    if person_name:
        matches = [p for p in people if person_name.lower() in p["name"].lower()]
        if not matches:
            return {"error": f"לא נמצא אדם בשם '{person_name}'"}
        pool = matches
    else:
        pool = people

    if daily:
        seed = date.today().toordinal()
        rng = random.Random(seed)
        person = rng.choice(pool)
        quote = rng.choice(person["quotes"])
    else:
        person = random.choice(pool)
        quote = random.choice(person["quotes"])

    return {
        "quote": quote,
        "name": person["name"],
        "field": person.get("field", ""),
        "dates": person.get("dates", ""),
    }
