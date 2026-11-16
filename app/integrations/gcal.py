"""Google Calendar: read events, and create events only after you confirm in the app."""
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..config import GOOGLE_TOKEN_FILE, TIMEZONE

log = logging.getLogger(__name__)
SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",  # to see subscribed calendars (ELMS)
]
TZ = ZoneInfo(TIMEZONE)


def _service():
    if not os.path.exists(GOOGLE_TOKEN_FILE):
        return None
    creds = Credentials.from_authorized_user_file(GOOGLE_TOKEN_FILE, SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        with open(GOOGLE_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _calendars(svc) -> list[dict]:
    """Every calendar shown in your Google Calendar, including subscribed ones like ELMS."""
    try:
        items = svc.calendarList().list().execute().get("items", [])
        return [{"id": c["id"], "name": c.get("summary", "")} for c in items if c.get("selected", True)]
    except Exception as e:
        log.warning("couldn't list calendars, using primary only: %s", e)
        return [{"id": "primary", "name": "primary"}]


def events_between(start: datetime, end: datetime) -> list[dict]:
    svc = _service()
    if svc is None:
        return []
    out = []
    for cal in _calendars(svc):
        try:
            res = svc.events().list(
                calendarId=cal["id"],
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime",
            ).execute()
        except Exception as e:  # expired token, removed calendar, etc. — don't crash the scheduler
            log.error("calendar read failed for %s: %s", cal["name"], e)
            continue
        for ev in res.get("items", []):
            s = ev["start"].get("dateTime") or ev["start"].get("date")
            out.append({"summary": ev.get("summary", "(no title)"), "start": s,
                        "location": ev.get("location", ""), "calendar": cal["name"]})
    return sorted(out, key=lambda e: e["start"])


def events_for_day(day: datetime) -> list[dict]:
    start = day.astimezone(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    return events_between(start, start + timedelta(days=1))


def format_events(events: list[dict]) -> str:
    if not events:
        return "Nothing on the calendar."
    lines = []
    for ev in events:
        s = ev["start"]
        when = datetime.fromisoformat(s).strftime("%-I:%M %p") if "T" in s else "All day"
        loc = f" ({ev['location']})" if ev["location"] else ""
        lines.append(f"- {when}: {ev['summary']}{loc}")
    return "\n".join(lines)


def create_event(summary: str, start_iso: str, end_iso: str, description: str = "") -> str:
    svc = _service()
    if svc is None:
        raise RuntimeError("Google Calendar isn't connected yet (run scripts/google_auth.py).")
    ev = svc.events().insert(calendarId="primary", body={
        "summary": summary,
        "description": description,
        "start": {"dateTime": start_iso, "timeZone": TIMEZONE},
        "end": {"dateTime": end_iso, "timeZone": TIMEZONE},
    }).execute()
    return ev.get("htmlLink", "")
