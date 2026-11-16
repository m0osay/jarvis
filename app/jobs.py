"""Scheduled jobs: morning brief, class announcements, job openings, night fit reminder."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db, notify
from .config import TIMEZONE
import threading

from .integrations import canvas, gcal, jobs as jobfeed, mail

log = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)


def morning_brief():
    today = datetime.now(TZ)
    lines = ["**Today**", gcal.format_events(gcal.events_for_day(today))]
    if canvas.enabled():
        due = canvas.upcoming_assignments(7)
        lines.append("\n**Due this week (priority classes)**")
        lines.append("\n".join(
            f"- [{a['course']}] {a['name']} — {a['due'].astimezone(TZ):%a %-m/%-d %-I:%M %p}"
            for a in due) or "Nothing due. 🎉")
    notify.push(f"Good morning, Sam — {today:%A %-m/%-d}", "\n".join(lines), tags="sunny")


def check_announcements():
    new = [a for a in canvas.recent_announcements(3) if db.mark_seen("announcement", a["id"])]
    for a in new:
        notify.push(f"📣 {a['course']}: {a['title']}", f"{a['preview']}\n\n{a['url']}",
                    tags="loudspeaker", priority=4)


def job_digest(prime_only: bool = False):
    new = [j for j in jobfeed.fetch_openings() if db.mark_seen("job", j["key"])]
    if prime_only or not new:
        return  # first run just records what's already listed, so you don't get 500 "new" jobs
    shown = new[:10]
    body = "\n".join(f"- **{j['company']}** — {j['title']}"
                     + (f" ({j['locations']})" if j["locations"] else "")
                     + (f"\n  {j['url']}" if j["url"] else "") for j in shown)
    more = f"\n\n…and {len(new) - len(shown)} more in the feed." if len(new) > len(shown) else ""
    notify.push(f"💼 {len(new)} new opening{'s' if len(new) != 1 else ''} — go apply",
                body + more, tags="briefcase")


def night_fit_reminder():
    tomorrow = datetime.now(TZ) + timedelta(days=1)
    events = gcal.events_for_day(tomorrow)
    first = next((e for e in events if "T" in e["start"]), None)
    if first:
        t = datetime.fromisoformat(first["start"]).strftime("%-I:%M %p")
        hint = f"First thing tomorrow: **{first['summary']}** at {t}. Dress for that."
    else:
        hint = "Nothing scheduled early tomorrow — still worth laying it out tonight."
    notify.push("👔 Lay out tomorrow's fit", hint, tags="necktie")


def _safe(fn, *args, **kwargs):
    def run():
        try:
            fn(*args, **kwargs)
        except Exception:
            log.exception("job %s failed", fn.__name__)
    run.__name__ = fn.__name__
    return run


def start() -> BackgroundScheduler:
    s = BackgroundScheduler(timezone=TZ)
    s.add_job(_safe(morning_brief), CronTrigger(hour=8, minute=0))
    s.add_job(_safe(check_announcements), CronTrigger(minute=17, hour="7-23/2"))
    s.add_job(_safe(job_digest), CronTrigger(hour=18, minute=0))
    s.add_job(_safe(night_fit_reminder), CronTrigger(day_of_week="mon-fri", hour=21, minute=0))
    s.add_job(_safe(mail.refresh), CronTrigger(minute="5,35"))   # inbox summaries every 30 min
    s.start()
    # Fill the inbox section right away, in the background so the server starts instantly.
    threading.Thread(target=_safe(mail.refresh), daemon=True).start()
    # Prime "seen" lists so the first real alert only contains genuinely new items.
    _safe(job_digest, prime_only=True)()
    for a in canvas.recent_announcements(3):
        db.mark_seen("announcement", a["id"])
    return s


JOBS = {
    "morning_brief": morning_brief,
    "check_announcements": check_announcements,
    "job_digest": job_digest,
    "night_fit_reminder": night_fit_reminder,
    "inbox_refresh": mail.refresh,
}
