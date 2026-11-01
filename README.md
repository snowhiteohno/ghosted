# Ghosted? v1

Reads your real application status from inside each portal with TinyFish, shows one board, and logs every change as an event. Telegram alerts are optional. Spec: `GHOSTED.md`.

## Setup

1. `.env` holds `TINYFISH_API_KEY` and the Gemini key. Fill in `GMAIL_USER` / `GMAIL_APP_PASSWORD` for the email engine. The app password needs 2-Step Verification on the Google account: myaccount.google.com → Security → 2-Step Verification → App passwords → create one named Ghosted. Telegram alerts are optional: set `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` to turn them on; without them sending is skipped.
2. Log in once per portal: open https://agent.tinyfish.ai → Browser Context Profiles → set up the profile → sign in to internshala.com and wellfound.com in that browser → save. Save after each site; the timer discards unsaved logins. `uv run probe.py --profiles` lists profile ids.
3. Edit `portals.json`: one row per portal with `engine` (`workday` | `internshala` | `unstop` | `email` | `manual`), the applications-page `url`, and the `profile_id` that holds that login. Unstop, Workday, SmartRecruiters, iCIMS, Taleo, Greenhouse, Lever and Ashby are all covered by the `email` engine, so no extra portal logins or signups are needed.
4. `manual` portals are hand-tracked rows for sites with no engine yet. One ships, `naukri`, with sample companies in `manual/naukri.json`; it exists so the simulate button and `plant.py` have something to flip. Replace its rows with real hand-tracked applications, or delete the row from `portals.json` if you would rather show only live data.

## Run

```
uv sync
uv run test_ghosted.py        # logic self-check (+ one small Gemini call for the email classifier)
uv run probe.py               # step 1: probe every non-email portal, print structured results
uv run probe.py --telegram    # test ping
uv run app.py                 # board at http://127.0.0.1:8000, checks every CHECK_INTERVAL_HOURS
```

## Demo rehearsal (90 seconds)

Before: profile signed in, `uv run probe.py` returned `ok` with rows for at least one real portal, `uv run test_ghosted.py` prints `ok`.

1. `uv run app.py`, open the board. The header reads "N applications · 4 portals · last check HH:MM". Opening line: "This is my actual pipeline."
2. In a second terminal plant the change: `uv run plant.py naukri "Initech" "Data Analyst Intern" "Interview scheduled"`.
3. Click **Check now**. Real portals show "checking…" with a *watch live* link and a live browser frame; manual portals finish at once.
4. The Initech row flips Under review → Interview, jumps to the top highlighted, and the event appears on the right with the raw status text.
5. Click a real portal row's *screenshot*: the page the status was read from.
6. Reset: `uv run plant.py naukri "Initech" "Data Analyst Intern" "Shortlisted"`, then **Check now** (this fires one more event, so do it after the demo, or delete `events.jsonl` and `snapshots/naukri/` to start clean).

Cost: a check is roughly 8–15 steps at $0.016 per real portal, and a detected change triggers one confirming re-read of that portal. Manual portals are free.

## Judge mode: let anyone test it without an account

Judges will not sign up for Internshala, and they do not need to. They test *your* pipeline from a public URL:

```
uv run app.py
cloudflared tunnel --url http://127.0.0.1:8000     # prints a public https://….trycloudflare.com URL, no account needed
```

At that URL a judge can: press **Check now** and watch the live browser read your real portals; press **Simulate a change** (clearly labeled, moves one hand-tracked row to its next status) and see the row flip and the event appear; click any row's screenshot.

Reset after judges have pressed Simulate: `cp manual/naukri.orig.json manual/naukri.json && rm -rf snapshots/naukri && : > events.jsonl`, then restart the app.

Spend is bounded: **Check now** runs at most once per `CHECK_COOLDOWN_MIN` (default 10) across all visitors, and the button shows the countdown. Simulate is free.

## Files

| File | Does |
|---|---|
| `engines.py` | Engine goal templates, output schema, six-state normalizer |
| `tinyfish.py` | Agent API client (async run + poll with live URL, run fetch, profiles) and the read-only referee |
| `check.py` | One portal check enforcing the five reliability rules; manual engine; Telegram |
| `store.py` | `snapshots/{portal}/{timestamp}.json` plus the `.jpg` it was read from, `events.jsonl`, diff |
| `gmail_engine.py` | Greenhouse/Lever/Ashby emails via Gmail IMAP (read-only) + one Gemini call |
| `logos.py` | Company name to website domain, one Gemini call per batch of new names, cached; the board shows the logo or a monogram |
| `app.py`, `board.html` | FastAPI board, SSE, live browser frames, local screenshot route, cooldown, simulate, 12 h scheduler |
| `plant.py` | Plant a status change in a manual portal for the rehearsal |
| `probe.py` | Probes, profile list, Telegram test ping |

## Where v1 differs from the spec

- **Scheduling is in-app**, not TinyMonitor. TinyFish Monitors only do page-fetch or topic-search runs; they cannot run an agent with a Browser Context Profile.
- **Referee reads the step log**, not the screenshot: a run whose step actions contain withdraw / accept / decline / submit / upload / apply / confirm / delete / edit / save is rejected.
- **Rule 4 (two reads)** re-reads a portal immediately when a change is seen, so the demo works in one "Check now"; only confirmed changes become events, and the first ever read is a silent baseline.
- **Screenshots are saved locally** at check time (`snapshots/{portal}/{timestamp}.jpg`, the last step that had one). TinyFish's per-step screenshot endpoint returned 404 for stored steps, so runs are fetched with `screenshots=base64` instead.
- **Telegram** is one HTTP call, no bot library, sent to the configured chat plus anyone who messaged the bot. **Gmail** is IMAP with an app password, no OAuth.

## Still unverified

Telegram delivery has not been tested; it is off until a bot token is set.
