"""Canvas (UMD ELMS) without an API token.

- Deadlines: the ELMS calendar feed, which you've subscribed to in Google Calendar.
- Announcements: Canvas notification emails, read over IMAP with an app password.

Both are filtered to PRIORITY_COURSES. Same function names as before, so jobs.py and llm.py
don't care where the data comes from.
"""
import email
import imaplib
import logging
import re
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from zoneinfo import ZoneInfo

from ..config import IMAP_ACCOUNTS, PRIORITY_COURSES, TIMEZONE
from . import gcal

log = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)


def _norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def _course_of(text: str) -> str | None:
    """Return the priority course code mentioned in text (e.g. 'CMSC424'), or None."""
    hay = _norm(text)
    return next((c for c in PRIORITY_COURSES if _norm(c) in hay), None)


def enabled() -> bool:
    # Calendar-based deadlines work whenever Google Calendar is connected.
    return True


# ---------- deadlines (from the ELMS calendar subscribed in Google Calendar) ----------

def upcoming_assignments(days: int = 7) -> list[dict]:
    now = datetime.now(TZ)
    out = []
    for ev in gcal.events_between(now, now + timedelta(days=days)):
        course = _course_of(f"{ev['summary']} {ev.get('calendar', '')}")
        if not course:
            continue
        s = ev["start"]
        due = datetime.fromisoformat(s) if "T" in s else datetime.fromisoformat(s).replace(tzinfo=TZ)
        # ELMS titles often end with "[CMSC424-0101-Fall-2026]"; drop that clutter.
        name = re.sub(r"\s*\[[^\]]*\]\s*$", "", ev["summary"]).strip()
        out.append({"course": course, "name": name, "due": due, "url": ""})
    return sorted(out, key=lambda a: a["due"])


# ---------- announcements (from Canvas notification emails) ----------

def _decode(value: str | None) -> str:
    return str(make_header(decode_header(value or "")))


def _body_text(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    html = ""
    for p in parts:
        ctype = p.get_content_type()
        if ctype not in ("text/plain", "text/html") or p.get_filename():
            continue
        payload = p.get_payload(decode=True) or b""
        text = payload.decode(p.get_content_charset() or "utf-8", errors="replace")
        if ctype == "text/plain":
            return text
        html = html or text
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def recent_announcements(days: int = 3) -> list[dict]:
    out, seen_ids = [], set()
    for acct in IMAP_ACCOUNTS:
        for a in _announcements_from(acct, days):
            if a["id"] not in seen_ids:   # same email forwarded to two inboxes → alert once
                seen_ids.add(a["id"])
                out.append(a)
    return out


def _announcements_from(acct: dict, days: int) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%d-%b-%Y")
    out = []
    try:
        with imaplib.IMAP4_SSL(acct["host"]) as m:
            m.login(acct["user"], acct["password"])
            m.select("INBOX", readonly=True)   # read-only: never marks your mail as read
            _, data = m.search(None, f'(SINCE {since} FROM "instructure.com")')
            ids = data[0].split()[-50:]
            for num in ids:
                _, msg_data = m.fetch(num, "(BODY.PEEK[])")
                msg = email.message_from_bytes(msg_data[0][1])
                subject = _decode(msg.get("Subject"))
                body = _body_text(msg)
                course = _course_of(subject) or _course_of(body[:600])
                if not course:
                    continue
                link = re.search(r"https://\S*instructure\.com/courses/\S+", body)
                out.append({
                    "id": msg.get("Message-ID") or f"{subject}|{msg.get('Date')}",
                    "course": course,
                    "title": subject,
                    "preview": re.sub(r"\s+", " ", body).strip()[:280],
                    "url": link.group(0).rstrip(").,>\"'") if link else "",
                })
    except (imaplib.IMAP4.error, OSError) as e:
        log.error("email check failed for %s: %s", acct["user"], e)  # one bad inbox doesn't stop the others
    return out
