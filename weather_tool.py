import httpx

# Jerusalem coordinates
LAT = 31.7683
LON = 35.2137

WMO_CODES = {
    0: "שמיים בהירים ☀️",
    1: "בעיקר בהיר 🌤️", 2: "מעונן חלקית ⛅", 3: "מעונן ☁️",
    45: "ערפל 🌫️", 48: "ערפל קפוא 🌫️",
    51: "טפטוף קל 🌦️", 53: "טפטוף 🌦️", 55: "טפטוף כבד 🌧️",
    61: "גשם קל 🌧️", 63: "גשם 🌧️", 65: "גשם כבד 🌧️",
    71: "שלג קל ❄️", 73: "שלג ❄️", 75: "שלג כבד ❄️",
    80: "מקלחות גשם 🌦️", 81: "מקלחות 🌧️", 82: "מקלחות כבדות ⛈️",
    95: "סופת רעמים ⛈️", 96: "סופת רעמים עם ברד ⛈️", 99: "סופת רעמים עם ברד כבד ⛈️",
}

def get_jerusalem_weather() -> dict:
    """Fetch current weather and today's forecast for Jerusalem."""
    resp = httpx.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": LAT,
            "longitude": LON,
            "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code",
            "timezone": "Asia/Jerusalem",
            "forecast_days": 1,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    current = data["current"]
    daily = data["daily"]

    weather_code = current.get("weather_code", 0)
    description = WMO_CODES.get(weather_code, "לא ידוע")

    return {
        "temp_now": round(current.get("temperature_2m", 0)),
        "feels_like": round(current.get("apparent_temperature", 0)),
        "humidity": current.get("relative_humidity_2m", 0),
        "wind_kmh": round(current.get("wind_speed_10m", 0)),
        "description": description,
        "temp_max": round(daily["temperature_2m_max"][0]),
        "temp_min": round(daily["temperature_2m_min"][0]),
        "rain_mm": daily["precipitation_sum"][0] or 0,
    }


def get_clothing_advice(weather: dict) -> str:
    """Generate clothing advice based on weather."""
    temp_max = weather["temp_max"]
    rain = weather["rain_mm"]
    wind = weather["wind_kmh"]

    advice = []

    if temp_max >= 28:
        advice.append("בגדים קלים וקצרים")
    elif temp_max >= 22:
        advice.append("בגדים קלים, אפשר שרוולים ארוכים בערב")
    elif temp_max >= 16:
        advice.append("שכבות — חולצה + סוודר/ג'קט קל")
    else:
        advice.append("מעיל חם")

    if rain > 0:
        advice.append("מטרייה בהחלט! 🌂")
    if wind > 30:
        advice.append("ג'קט עמיד לרוח")

    return ", ".join(advice)
