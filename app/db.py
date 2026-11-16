"""SQLite storage: chat history, things already notified (no duplicate alerts), pending actions."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DATA_DIR

DB_PATH = DATA_DIR / "jarvis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,              -- 'user' | 'assistant'
    content TEXT NOT NULL,
    action_id INTEGER,               -- set when the message carries a confirmable action
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen (
    kind TEXT NOT NULL,              -- 'announcement' | 'job' | ...
    key TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (kind, key)
);
CREATE TABLE IF NOT EXISTS emails (
    account TEXT NOT NULL,
    msg_id TEXT NOT NULL,            -- the email's Message-ID header
    sender TEXT NOT NULL,
    subject TEXT NOT NULL,
    sent_at TEXT NOT NULL,           -- ISO date from the email
    summary TEXT NOT NULL,           -- one-line AI summary, made once and reused
    stored_at TEXT NOT NULL,
    PRIMARY KEY (account, msg_id)
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,              -- 'create_event'
    payload TEXT NOT NULL,           -- JSON
    status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | rejected | failed
    created_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init():
    with conn() as c:
        c.executescript(SCHEMA)


def add_message(role: str, content: str, action_id: int | None = None) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO messages (role, content, action_id, created_at) VALUES (?,?,?,?)",
            (role, content, action_id, now()),
        )
        return cur.lastrowid


def recent_messages(limit: int = 50) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            """SELECT m.*, a.status AS action_status, a.payload AS action_payload
               FROM messages m LEFT JOIN actions a ON a.id = m.action_id
               ORDER BY m.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in reversed(rows)]


def mark_seen(kind: str, key: str) -> bool:
    """Returns True if this item is new (and records it), False if already seen."""
    with conn() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO seen (kind, key, created_at) VALUES (?,?,?)", (kind, key, now())
        )
        return cur.rowcount == 1


def known_email_ids(account: str, msg_ids: list[str]) -> set[str]:
    if not msg_ids:
        return set()
    with conn() as c:
        rows = c.execute(
            f"SELECT msg_id FROM emails WHERE account = ? AND msg_id IN ({','.join('?' * len(msg_ids))})",
            (account, *msg_ids),
        ).fetchall()
    return {r["msg_id"] for r in rows}


def save_email(account: str, e: dict):
    with conn() as c:
        c.execute(
            """INSERT OR REPLACE INTO emails (account, msg_id, sender, subject, sent_at, summary, stored_at)
               VALUES (?,?,?,?,?,?,?)""",
            (account, e["msg_id"], e["sender"], e["subject"], e["sent_at"], e["summary"], now()),
        )


def latest_emails(account: str, limit: int = 5) -> list[dict]:
    with conn() as c:
        rows = c.execute(
            "SELECT sender, subject, sent_at, summary FROM emails WHERE account = ? "
            "ORDER BY sent_at DESC LIMIT ?",
            (account, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def kv_get(key: str) -> str | None:
    with conn() as c:
        r = c.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else None


def kv_set(key: str, value: str):
    with conn() as c:
        c.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?,?)", (key, value))


def create_action(type_: str, payload: dict) -> int:
    with conn() as c:
        cur = c.execute(
            "INSERT INTO actions (type, payload, created_at) VALUES (?,?,?)",
            (type_, json.dumps(payload), now()),
        )
        return cur.lastrowid


def get_action(action_id: int) -> dict | None:
    with conn() as c:
        r = c.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["payload"] = json.loads(d["payload"])
    return d


def set_action_status(action_id: int, status: str):
    with conn() as c:
        c.execute("UPDATE actions SET status = ? WHERE id = ?", (status, action_id))
