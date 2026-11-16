import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _list(name: str, default: str = "") -> list[str]:
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


APP_TOKEN = os.getenv("APP_TOKEN", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

NTFY_URL = os.getenv("NTFY_URL", "http://localhost:8080").rstrip("/")
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "http://localhost:8000")

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")


def _imap_accounts() -> list[dict]:
    """IMAP_ACCOUNTS=me@gmail.com:apppass,other@gmail.com:apppass[,user@x.com:pass@imap.x.com]"""
    accounts = []
    for entry in _list("IMAP_ACCOUNTS"):
        user, _, rest = entry.partition(":")
        password, _, host = rest.partition("@")
        if user and password:
            # Google shows app passwords with spaces; strip them.
            accounts.append({"user": user, "password": password.replace(" ", ""),
                             "host": host or IMAP_HOST})
    # Backward compatible with the single-account settings.
    if not accounts and os.getenv("IMAP_USER") and os.getenv("IMAP_PASSWORD"):
        accounts.append({"user": os.getenv("IMAP_USER"),
                         "password": os.getenv("IMAP_PASSWORD").replace(" ", ""), "host": IMAP_HOST})
    return accounts


IMAP_ACCOUNTS = _imap_accounts()
PRIORITY_COURSES = _list("PRIORITY_COURSES", "CMSC424,MATH401,CMSC335")

JOBS_FEED_URL = os.getenv("JOBS_FEED_URL", "")
JOB_KEYWORDS = [k.lower() for k in _list("JOB_KEYWORDS", "software,engineer,developer")]

GOOGLE_CLIENT_FILE = os.getenv("GOOGLE_CLIENT_FILE", str(DATA_DIR / "google_client.json"))
GOOGLE_TOKEN_FILE = os.getenv("GOOGLE_TOKEN_FILE", str(DATA_DIR / "google_token.json"))

TIMEZONE = "America/New_York"
