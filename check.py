"""One status check for one portal, enforcing the reliability rules in GHOSTED.md."""
import json
import os
import re
import time
from datetime import datetime

import httpx

import engines
import store
import tinyfish


def now_iso():
    """Local time with its UTC offset, so a viewer in another timezone still sees correct "5 min ago" values."""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _snap(portal):
    return {"portal": portal["id"], "engine": portal["engine"], "checked_at": now_iso(), "run_id": None,
            "shot": None, "steps": 0, "status": "failed", "applications": [], "notes": None}


DATE_FORMATS = ["%Y-%m-%d", "%d %b' %y", "%d %b %Y", "%B %d, %Y %I:%M%p", "%B %d, %Y", "%Y-%m-%d %I:%M%p", "%b %d, %Y"]


def iso_date(text):
    """Portals print dates every which way ("1 Nov' 26", "November 1, 2026 4:18am"); store YYYY-MM-DD, else keep the raw text."""
    text = (text or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    m = re.match(r"\d{4}-\d{2}-\d{2}", text)
    return m.group(0) if m else (text or None)


def _accept(snap, portal, apps):
    """Rule 1: zero rows is a failed check, never "no applications". Normalizes each row and fills the url."""
    apps = [a for a in apps if a.get("title") and a.get("company")]
    if not apps:
        snap["notes"] = snap["notes"] or "zero applications read"
        return snap
    for a in apps:
        a["status"] = engines.normalize(a.get("status_raw"))
        a["url"] = a.get("url") or portal.get("url")
        a["applied_on"] = iso_date(a.get("applied_on"))
    snap.update(status="ok", applications=apps)
    return snap


def _read(portal, use_vault=False, on_live=None):
    """One read of a portal. Rule 5 (referee) lives here for agent engines."""
    if portal["engine"] == "email":
        import gmail_engine
        return gmail_engine.check(portal)
    snap = _snap(portal)
    if portal["engine"] == "manual":  # rows kept by hand in manual/{portal}.json, for portals with no engine yet
        rows = json.loads((store.ROOT / "manual" / f"{portal['id']}.json").read_text())
        return _accept(snap, portal, rows)
    run = tinyfish.run(portal["url"], engines.goal_for(portal["engine"]), engines.SCHEMA,
                       portal.get("profile_id"), use_vault, on_live=on_live)
    snap["run_id"] = run.get("run_id")
    steps = tinyfish.get_run(snap["run_id"])["steps"] if snap["run_id"] else []
    snap.update(steps=len(steps), shot=tinyfish.last_shot(steps))
    if run.get("status") != "COMPLETED":
        snap["notes"] = (run.get("error") or {}).get("message") or f"run {str(run.get('status', 'failed')).lower()}"
        return snap
    bad = tinyfish.referee(steps)
    if bad:
        snap["notes"] = f"referee rejected run, write action seen: {bad}"
        return snap
    result = run.get("result") or {}
    snap["notes"] = result.get("notes")
    if result.get("status") == "logged_out":
        snap["status"] = "logged_out"
        return snap
    rows = result.get("applications") or [] if result.get("status") == "ok" else []
    return _accept(snap, portal, rows)


def check_portal(portal, on_live=None):
    """Returns (snapshot, events). Rule 2: logged out -> vault repair -> re-login badge. Rule 4: a change needs two reads."""
    snap = _read(portal, on_live=on_live)
    if snap["status"] == "failed" and portal["engine"] not in ("manual", "email"):
        snap = _read(portal, on_live=on_live)  # one retry: an agent that stops before scrolling to the list is the usual cause
    if snap["status"] == "logged_out":
        try:
            snap = _read(portal, use_vault=True, on_live=on_live)
        except Exception as e:
            snap["notes"] = f"vault repair failed: {e}"
        if snap["status"] == "logged_out":
            snap["status"] = "relogin"
    prev = store.latest(portal["id"])
    old = {store.key(a): a for a in prev["applications"]} if prev else {}
    events = []
    if snap["status"] == "ok":
        changes = store.diff(old, snap["applications"])
        if changes and prev:  # rule 4: confirm with a second read; a flip that flips back is noise
            second = _read(portal, on_live=on_live)
            if second["status"] != "ok":
                snap = {**second, "status": "failed", "notes": "change seen but the confirming read failed"}
            else:
                first = {(store.key(c), c["status"]) for c in changes}
                snap = second
                changes = [c for c in store.diff(old, snap["applications"]) if (store.key(c), c["status"]) in first]
    if snap["status"] == "ok":
        if not prev:
            changes = []  # the first successful read is the baseline, not a pile of alerts
        for a in snap["applications"]:
            o = old.get(store.key(a))
            a["changed_at"] = o["changed_at"] if o and o["status"] == a["status"] else snap["checked_at"]
        events = [{"ts": snap["checked_at"], "portal": portal["id"], "company": c["company"], "title": c["title"],
                   "from": c["from"], "to": c["status"], "raw": c["status_raw"], "url": c["url"]} for c in changes]
    elif prev:
        snap["applications"] = prev["applications"]  # keep the last known rows on the board behind a "check failed" badge
    store.save(portal["id"], snap)
    with store.EVENTS.open("a") as f:
        f.writelines(json.dumps(e) + "\n" for e in events)
    return snap, events


def format_event(e):
    move = f"{e['from']} → {e['to']}" if e["from"] else f"new application: {e['to']}"
    return f"Ghosted? · {e['portal']}\n{e['company']} · {e['title']}\n{move}\nraw: \"{e['raw']}\"\n{e['url']}"


def chat_ids(token):
    """The configured chat plus everyone who messaged the bot recently: a judge subscribes by sending it /start."""
    ids = {os.getenv("TELEGRAM_CHAT_ID")} - {None, ""}
    try:
        updates = httpx.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=15).json().get("result", [])
        ids |= {str(u["message"]["chat"]["id"]) for u in updates if "message" in u}
    except Exception:
        pass
    return ids


def telegram(text):
    """Send one Telegram message to every subscribed chat. No-op (returns False) until TELEGRAM_BOT_TOKEN is set."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        return False
    sent = False
    for chat in chat_ids(token):
        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=30).raise_for_status()
        sent = True
    return sent
