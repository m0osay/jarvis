"""Push a notification to your phone through ntfy. Also logs it into the chat so you can reply."""
import logging

import httpx

from . import db
from .config import APP_PUBLIC_URL, NTFY_TOPIC, NTFY_URL

log = logging.getLogger(__name__)


def push(title: str, body: str, tags: str = "", priority: int = 3, to_chat: bool = True):
    if to_chat:
        db.add_message("assistant", f"**{title}**\n\n{body}")
    if not NTFY_TOPIC:
        log.warning("NTFY_TOPIC not set; skipping push: %s", title)
        return
    try:
        httpx.post(
            f"{NTFY_URL}/{NTFY_TOPIC}",
            content=body.encode("utf-8"),
            headers={
                "Title": title.encode("utf-8"),
                "Tags": tags,
                "Priority": str(priority),
                "Click": APP_PUBLIC_URL,   # tapping the notification opens the chat app
                "Markdown": "yes",
            },
            timeout=10,
        )
    except httpx.HTTPError as e:
        log.error("ntfy push failed: %s", e)
