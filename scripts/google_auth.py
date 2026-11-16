"""One-time Google Calendar sign-in. Run on your Mac (it opens a browser), then copy
data/google_token.json to the server's data/ folder.

    python scripts/google_auth.py
"""
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "data" / "google_client.json"
TOKEN = ROOT / "data" / "google_token.json"
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
]

if not CLIENT.exists():
    sys.exit(f"Missing {CLIENT}. Download your OAuth 'Desktop app' client JSON there first (see README).")

creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES).run_local_server(port=0)
TOKEN.write_text(creds.to_json())
print(f"Saved {TOKEN}")
