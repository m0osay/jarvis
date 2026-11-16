"""FastAPI server: serves the phone app and its small JSON API."""
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db, jobs, llm
from .config import APP_TOKEN, TIMEZONE
from .integrations import gcal, mail

TZ = ZoneInfo(TIMEZONE)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init()
    scheduler = jobs.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="Jarvis", lifespan=lifespan)


def auth(authorization: str = Header(default="")):
    token = authorization.removeprefix("Bearer ").strip()
    if not APP_TOKEN or not secrets.compare_digest(token, APP_TOKEN):
        raise HTTPException(401, "bad token")


class ChatIn(BaseModel):
    text: str


@app.get("/api/messages", dependencies=[Depends(auth)])
def messages():
    return db.recent_messages(100)


@app.post("/api/chat", dependencies=[Depends(auth)])
def chat(body: ChatIn):
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "empty message")
    db.add_message("user", text)
    reply = llm.chat(text)
    db.add_message("assistant", reply["text"], reply["action_id"])
    return {"ok": True}


@app.post("/api/actions/{action_id}/{decision}", dependencies=[Depends(auth)])
def decide(action_id: int, decision: str):
    action = db.get_action(action_id)
    if not action or action["status"] != "pending":
        raise HTTPException(404, "no pending action")
    if decision == "reject":
        db.set_action_status(action_id, "rejected")
        db.add_message("assistant", "Skipped — nothing added.")
        return {"ok": True}
    if decision != "confirm":
        raise HTTPException(400, "decision must be confirm or reject")
    p = action["payload"]
    try:
        link = gcal.create_event(p["summary"], p["start"], p["end"], p.get("description", ""))
    except Exception as e:
        db.set_action_status(action_id, "failed")
        db.add_message("assistant", f"Couldn't add it: {e}")
        return {"ok": False}
    db.set_action_status(action_id, "done")
    db.add_message("assistant", f"✅ Added **{p['summary']}** to your calendar." + (f"\n{link}" if link else ""))
    return {"ok": True}


_cal_cache: dict = {"at": None, "day": None, "events": []}


def _tomorrow_events(force: bool = False) -> tuple[datetime, list[dict]]:
    """Tomorrow's events, cached 10 minutes (no AI involved, just avoids slow Google calls)."""
    now = datetime.now(TZ)
    tomorrow = now + timedelta(days=1)
    c = _cal_cache
    fresh = c["at"] and (now - c["at"]).total_seconds() < 600 and c["day"] == tomorrow.date()
    if force or not fresh:
        c.update(at=now, day=tomorrow.date(), events=gcal.events_for_day(tomorrow))
    return tomorrow, c["events"]


@app.get("/api/dashboard", dependencies=[Depends(auth)])
def dashboard():
    """Home screen: stored email summaries + tomorrow's calendar. Never calls the AI."""
    tomorrow, events = _tomorrow_events()
    return {
        **mail.overview(),
        "tomorrow": {"date": tomorrow.strftime("%A %-m/%-d"), "events": events},
    }


@app.post("/api/refresh", dependencies=[Depends(auth)])
def refresh():
    """Refresh button: check inboxes (AI only for new emails) and re-read the calendar."""
    result = mail.refresh()
    _tomorrow_events(force=True)
    return result


@app.post("/api/run/{job}", dependencies=[Depends(auth)])
def run_job(job: str):
    """Trigger a scheduled job by hand — handy while testing."""
    fn = jobs.JOBS.get(job)
    if not fn:
        raise HTTPException(404, f"unknown job; try one of {list(jobs.JOBS)}")
    fn()
    return {"ok": True}


@app.get("/health")
def health():
    return {"ok": True}


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC / "sw.js", media_type="application/javascript")
