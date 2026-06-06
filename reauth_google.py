"""
re-auth של Google Calendar/Gmail לרובין (כשמופיע invalid_grant).
מריצים פעם אחת, מתחברים בדפדפן עם החשבון של גדי, והסקריפט:
  1. שואב GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET מ-.env לבד
  2. מבצע OAuth (פותח דפדפן)
  3. מדפיס את ה-refresh token החדש ומעדכן אותו ב-.env מקומית
  4. מזכיר לעדכן גם ב-Render (הבוט בפרודקשן קורא משם)

הרצה:  python reauth_google.py
"""
import json, os, re, urllib.parse, urllib.request, webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

ENV = Path(__file__).parent / ".env"
env_text = ENV.read_text(encoding="utf-8")
def env_get(k):
    m = re.search(rf"^{k}=(.*)$", env_text, re.M)
    return m.group(1).strip() if m else None

CLIENT_ID = env_get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = env_get("GOOGLE_CLIENT_SECRET")
if not CLIENT_ID or not CLIENT_SECRET:
    print("ERROR: חסר GOOGLE_CLIENT_ID/SECRET ב-.env"); raise SystemExit(1)

REDIRECT_URI = "http://localhost:8080"
SCOPES = "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly"
auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
    "client_id": CLIENT_ID, "redirect_uri": REDIRECT_URI, "response_type": "code",
    "scope": SCOPES, "access_type": "offline", "prompt": "consent",
})
print("\nפותח דפדפן — התחבר עם החשבון של גדי ואשר את הגישה...")
webbrowser.open(auth_url)

code_holder = {}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code_holder["code"] = q.get("code", [""])[0]
        self.send_response(200); self.end_headers()
        self.wfile.write("<h1>קיבלתי! אפשר לסגור את הטאב ולחזור לטרמינל.</h1>".encode("utf-8"))
    def log_message(self, *a): pass

print("ממתין לאישור בדפדפן (localhost:8080)...")
HTTPServer(("localhost", 8080), Handler).handle_request()
code = code_holder.get("code", "")
if not code:
    print("ERROR: לא התקבל code"); raise SystemExit(1)

resp = json.loads(urllib.request.urlopen(urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=urllib.parse.urlencode({
        "code": code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code",
    }).encode(),
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)).read())

rt = resp.get("refresh_token", "")
if not rt:
    print("ERROR:", resp); raise SystemExit(1)

# update .env locally
if re.search(r"^GOOGLE_REFRESH_TOKEN=.*$", env_text, re.M):
    env_text = re.sub(r"^GOOGLE_REFRESH_TOKEN=.*$", "GOOGLE_REFRESH_TOKEN=" + rt, env_text, flags=re.M)
else:
    env_text += f"\nGOOGLE_REFRESH_TOKEN={rt}\n"
ENV.write_text(env_text, encoding="utf-8")

print("\n✅ הצליח! .env המקומי עודכן.")
print("\n🔑 REFRESH TOKEN החדש:\n" + rt)
print("\n‼️ עכשיו עדכן גם ב-Render (הבוט בפרודקשן קורא משם):")
print("   Render → robin-whatsapp → Environment → GOOGLE_REFRESH_TOKEN → הדבק את הטוקן → Save")
print("   (השמירה מפעילה deploy אוטומטי). אחרי ~3 דק' בדוק:")
print("   https://robin-whatsapp.onrender.com/admin/calendar/check?token=cron_secret_9931")
