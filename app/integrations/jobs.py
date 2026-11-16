"""New-grad job openings from a GitHub listings feed (the JSON behind the README tables).

Most new-grad repos keep a machine-readable file next to the README, often at
`.github/scripts/listings.json`. Open the repo, find that file, click "Raw", and put that URL in
JOBS_FEED_URL. The parser below is tolerant of the usual field names.
"""
import logging

import httpx

from ..config import JOB_KEYWORDS, JOBS_FEED_URL

log = logging.getLogger(__name__)


def _field(d: dict, *names, default=""):
    for n in names:
        if d.get(n):
            return d[n]
    return default


def fetch_openings() -> list[dict]:
    if not JOBS_FEED_URL:
        return []
    try:
        r = httpx.get(JOBS_FEED_URL, timeout=30, follow_redirects=True)
        r.raise_for_status()
        raw = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.error("job feed failed: %s", e)
        return []
    if isinstance(raw, dict):  # some feeds wrap the list
        raw = raw.get("listings") or raw.get("jobs") or []

    out = []
    for j in raw:
        if not isinstance(j, dict):
            continue
        if j.get("active") is False or j.get("is_visible") is False:
            continue
        title = _field(j, "title", "role", "position")
        if JOB_KEYWORDS and not any(k in title.lower() for k in JOB_KEYWORDS):
            continue
        url = _field(j, "url", "link", "apply_url")
        company = _field(j, "company_name", "company")
        out.append({
            "key": str(_field(j, "id", default=f"{company}|{title}|{url}")),
            "company": company,
            "title": title,
            "url": url,
            "locations": ", ".join(j.get("locations", []) or [])[:80],
            "posted": _field(j, "date_posted", "date_updated", default=0),
        })
    return out
