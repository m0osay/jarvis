# Jarvis (MVP)

Personal assistant that lives on your Linux box and talks to you through a private phone app.

- **Chat app**: installable web app (PWA) served by FastAPI. Reachable only on your Tailscale network.
- **Alerts**: ntfy pushes to your phone; tapping one opens the chat.
- **Scheduled jobs** (America/New_York):
  | Time | Job |
  |---|---|
  | 8:00 AM daily | Morning brief: today's calendar + what's due this week in CMSC424/MATH401/CMSC335 |
  | Every 2h, 7am–11pm | New Canvas announcement in a priority class → alert |
  | 6:00 PM daily | New full-time openings from your job feed → "go apply" |
  | 9:00 PM Mon–Fri | Lay out tomorrow's fit, based on tomorrow's first event |
- **Calendar**: Jarvis can *propose* events; nothing is written until you tap **Confirm**.

```
app/
  main.py          FastAPI server + API
  jobs.py          the scheduled jobs
  llm.py           Claude chat + live context
  prompt.md        Jarvis's instructions (edit freely)
  notify.py        ntfy push
  db.py            SQLite (chat, seen items, pending actions)
  integrations/    gcal.py, canvas.py, jobs.py
  static/          the phone app
scripts/           google_auth.py, make_icons.py
data/              db + secrets, never committed
```

## 1. Run it on your Mac

```bash
cp .env.example .env          # fill in APP_TOKEN and ANTHROPIC_API_KEY at minimum
docker compose up --build
```

Open http://localhost:8000, paste your APP_TOKEN, and chat. Each piece below is optional and the
app works without it; add them one at a time.

Fire any job by hand to test it:

```bash
curl -X POST localhost:8000/api/run/night_fit_reminder -H "Authorization: Bearer $APP_TOKEN"
# also: morning_brief, check_announcements, job_digest
```

## 2. Connect things

**Google Calendar**
1. console.cloud.google.com → new project → enable *Google Calendar API*.
2. OAuth consent screen → External → add yourself as a test user.
3. Credentials → Create OAuth client ID → *Desktop app* → download JSON to `data/google_client.json`.
4. On your Mac: `pip install google-auth-oauthlib && python scripts/google_auth.py`.
   This writes `data/google_token.json`.
5. Heads-up: while the Google app is in "Testing" mode, the token expires after ~7 days.
   Rerun step 4 when that happens, or publish the app (still just for you) to stop it.

**ELMS (no API token needed)**
- *Deadlines*: subscribe Google Calendar to your ELMS calendar feed (ELMS → Calendar → Calendar
  Feed → paste into Google Calendar "From URL"). Jarvis reads every calendar you have, and picks
  out events mentioning CMSC424 / MATH401 / CMSC335. Google refreshes subscribed calendars every
  several hours, so very last-minute changes can lag.
- *Announcements*: set ELMS → Account → Notifications → Announcement to "Notify immediately".
  Create an app password at myaccount.google.com/apppasswords (needs 2-Step Verification) for the
  each inbox you want checked, and list them in `IMAP_ACCOUNTS` (comma-separated `email:password`). Jarvis opens the inbox
  read-only, so nothing gets marked as read.

**Job feed**: in the new-grad repo you follow, find the JSON the README is generated from
(often `.github/scripts/listings.json`), click **Raw**, and paste that URL into `JOBS_FEED_URL`.
The first run only records existing listings, so you're alerted to genuinely new ones after that.

**ntfy**: install the ntfy app on your phone, add your server (`NTFY_PUBLIC_URL`) and subscribe to
your `NTFY_TOPIC`.

## 3. Move it to the Linux box

```bash
# on the server (Ubuntu)
curl -fsSL https://get.docker.com | sh && sudo usermod -aG docker $USER   # then log out/in
curl -fsSL https://tailscale.com/install.sh | sh && sudo tailscale up
git clone <your repo> jarvis && cd jarvis
scp/copy your .env and data/google_*.json onto the server
docker compose up -d --build
```

Install Tailscale on your phone, sign into the same account, then open
`http://<server-name>:8000` in Safari → Share → **Add to Home Screen**.

Updating later: `git pull && docker compose up -d --build`.

## Security notes
- Keep ports 8000/8080 off the public internet; Tailscale only.
- `.env` and `data/` hold your keys and tokens and are git-ignored. Keep it that way.
- Canvas access is read-only; calendar writes always need your tap.

## Next up (after MVP)
- Gmail: application-status tracking from ATS emails
- Chat-driven job tracking ("mark Datadog applied")
- Web push in the app itself instead of ntfy
- Finance via SimpleFIN
