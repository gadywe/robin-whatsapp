"""
One-time script to get Google Calendar OAuth refresh token.
Run this once, paste the refresh token into .env
"""
import json
import urllib.parse
import urllib.request
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

CLIENT_ID = input("Client ID: ").strip()
CLIENT_SECRET = input("Client secret: ").strip()
REDIRECT_URI = "http://localhost:8080"
SCOPES = "https://www.googleapis.com/auth/calendar https://www.googleapis.com/auth/gmail.readonly"

auth_url = (
    "https://accounts.google.com/o/oauth2/v2/auth?"
    + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
)

print(f"\nפותח דפדפן לאישור הגישה...")
webbrowser.open(auth_url)

code_holder = {}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        code_holder["code"] = params.get("code", [""])[0]
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"<h1>Got it! Close this tab and go back to the terminal.</h1>")

    def log_message(self, format, *args):
        pass

print("ממתין לאישור בדפדפן...")
server = HTTPServer(("localhost", 8080), Handler)
server.handle_request()

code = code_holder.get("code", "")
if not code:
    print("ERROR: no code received")
    exit(1)

data = urllib.parse.urlencode({
    "code": code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
}).encode()

req = urllib.request.Request(
    "https://oauth2.googleapis.com/token",
    data=data,
    headers={"Content-Type": "application/x-www-form-urlencoded"},
)
resp = json.loads(urllib.request.urlopen(req).read())

refresh_token = resp.get("refresh_token", "")
if refresh_token:
    print(f"\n✅ REFRESH TOKEN:\n{refresh_token}\n")
    print("הוסף לקובץ .env:\nGOOGLE_REFRESH_TOKEN=" + refresh_token)
else:
    print("ERROR:", resp)
