"""Chat with Claude. Live context (calendar, deadlines, announcements) is injected each turn."""
import logging
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import anthropic

from . import db
from .config import ANTHROPIC_API_KEY, CLAUDE_MODEL, TIMEZONE
from .integrations import canvas, gcal

log = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)
SYSTEM_PROMPT = (Path(__file__).parent / "prompt.md").read_text()

TOOLS = [{
    "name": "propose_calendar_event",
    "description": "Propose adding an event to Sam's Google Calendar. Sam must confirm in the app "
                   "before it is created.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "Event title"},
            "start": {"type": "string", "description": "ISO 8601 local start, e.g. 2026-11-10T19:00:00"},
            "end": {"type": "string", "description": "ISO 8601 local end"},
            "description": {"type": "string"},
        },
        "required": ["summary", "start", "end"],
    },
}]

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None


def build_context() -> str:
    now = datetime.now(TZ)
    parts = [f"Current time: {now.strftime('%A %B %-d, %Y %-I:%M %p')} (America/New_York)"]
    parts.append("Today's calendar:\n" + gcal.format_events(gcal.events_for_day(now)))
    parts.append("Tomorrow's calendar:\n" + gcal.format_events(gcal.events_for_day(now + timedelta(days=1))))
    if canvas.enabled():
        due = canvas.upcoming_assignments(7)
        parts.append("Priority-course assignments due in the next 7 days:\n" + (
            "\n".join(f"- [{a['course']}] {a['name']} — due {a['due'].astimezone(TZ):%a %-m/%-d %-I:%M %p}"
                      for a in due) or "None found."))
        ann = canvas.recent_announcements(5)
        parts.append("Recent priority-course announcements:\n" + (
            "\n".join(f"- [{a['course']}] {a['title']}: {a['preview']}" for a in ann) or "None."))
    # Stored email summaries (already in the DB, so no extra AI or inbox calls).
    from .integrations import mail
    inbox_lines = []
    for box in mail.overview()["inboxes"]:
        for e in box["items"]:
            inbox_lines.append(f"- [{box['account']}] {e['sender']}: {e['subject']} — {e['summary']}")
    parts.append("Latest emails (summaries):\n" + ("\n".join(inbox_lines) or "None stored yet."))
    return "\n\n".join(parts)


def chat(user_text: str) -> dict:
    """Returns {"text": ..., "action_id": int|None}."""
    if _client is None:
        return {"text": "ANTHROPIC_API_KEY isn't set yet, so I can't think. Add it to .env.",
                "action_id": None}

    history = [m for m in db.recent_messages(20) if m["role"] in ("user", "assistant")]
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    # The API needs alternating roles starting with user; merge consecutive same-role turns.
    merged: list[dict] = []
    for m in messages:
        if merged and merged[-1]["role"] == m["role"]:
            merged[-1]["content"] += "\n\n" + m["content"]
        else:
            merged.append(dict(m))
    while merged and merged[0]["role"] != "user":
        merged.pop(0)
    if not merged or merged[-1]["role"] != "user":
        merged.append({"role": "user", "content": user_text})

    system = SYSTEM_PROMPT + "\n\n## Live context\n" + build_context()
    try:
        resp = _client.messages.create(model=CLAUDE_MODEL, max_tokens=4096, system=system,
                                       tools=TOOLS, messages=merged)
    except anthropic.APIError as e:
        log.error("claude call failed: %s", e)
        return {"text": f"I couldn't reach Claude just now ({e.__class__.__name__}).", "action_id": None}

    text_parts, action_id = [], None
    for block in resp.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use" and block.name == "propose_calendar_event":
            action_id = db.create_action("create_event", block.input)
            ev = block.input
            text_parts.append(f"📅 Add **{ev['summary']}** — {ev['start'].replace('T', ' ')[:16]} "
                              f"to {ev['end'][11:16]}?")
    if resp.stop_reason == "max_tokens":
        text_parts.append("…(cut off — ask me to continue)")
    return {"text": "\n\n".join(t for t in text_parts if t).strip() or "OK.", "action_id": action_id}
