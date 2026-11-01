"""Email engine. Any ATS whose status reaches you by email, from Greenhouse and Lever to Workday and SmartRecruiters.
Reads Gmail over IMAP (read-only), then one LLM call turns the emails into application rows."""
import email
import imaplib
import json
import os
import re
import time
from email.header import decode_header
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

import engines
import store

# Every ATS that only talks by email. Workday, SmartRecruiters, iCIMS and Taleo live here too, so no portal login is needed.
DOMAINS = ["greenhouse.io", "greenhouse-mail.io", "lever.co", "ashbyhq.com", "myworkday.com", "myworkdayjobs.com",
           "smartrecruiters.com", "icims.com", "taleo.net", "oraclecloud.com", "workable.com", "jobvite.com",
           "recruitee.com", "bamboohr.com", "successfactors.com", "eightfold.ai", "phenompeople.com",
           "unstop.com"]  # Unstop keeps its login where profile capture cannot reach, so its emails are the source


def _decode(h):
    return "".join(s.decode(c or "utf-8", "ignore") if isinstance(s, bytes) else s for s, c in decode_header(h or ""))


def _text(msg):
    parts = {p.get_content_type(): p for p in msg.walk() if p.get_content_type() in ("text/plain", "text/html")}
    p = parts.get("text/plain") or parts.get("text/html")
    if not p:
        return ""
    body = p.get_payload(decode=True).decode(p.get_content_charset() or "utf-8", "ignore")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)) if p.get_content_type() == "text/html" else body


def fetch(days=90):
    m = imaplib.IMAP4_SSL("imap.gmail.com")
    m.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
    m.select("INBOX", readonly=True)  # rule 5: nothing is ever marked, moved or sent
    since = time.strftime("%d-%b-%Y", time.gmtime(time.time() - days * 86400))
    mails = []
    for dom in DOMAINS:
        _, data = m.search(None, "FROM", f'"{dom}"', "SINCE", since)
        for num in data[0].split():
            _, raw = m.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            mails.append({"id": (msg["Message-ID"] or "").strip("<>"), "from": _decode(msg["From"]),
                          "subject": _decode(msg["Subject"]), "date": msg["Date"], "body": _text(msg)[:1500]})
    m.logout()
    return mails


def classify(mails, known=()):
    prompt = ("Each email below came from a job application system. For every email about one specific application, "
              'output an item: {"i": <email index>, "company": "...", "title": "<role>", '
              '"state": one of Applied | Under review | Assessment | Interview | Offer | Rejected | Unknown, '
              '"status_raw": "<short phrase quoted from the email that states the status>"}. '
              'Skip job alerts, newsletters and marketing. Answer with JSON: {"applications": [...]}\n\n')
    if known:  # keeps names stable between checks, so a re-read is never mistaken for a new application
        prompt += ("Applications already tracked (company | title | state). When an email is about one of these, copy its "
                   "company and title exactly as written here, and keep the same state unless the email itself says the "
                   "status moved:\n" + "\n".join(f"- {c} | {t} | {st}" for c, t, st in known) + "\n\n")
    for i, m in enumerate(mails):
        prompt += f"--- email {i}\nFrom: {m['from']}\nSubject: {m['subject']}\nDate: {m['date']}\n{m['body']}\n\n"
    r = httpx.post(f"{os.environ['LLM_BASE_URL']}/chat/completions",
                   headers={"Authorization": f"Bearer {os.environ['LLM_API_KEY']}"},
                   json={"model": os.environ["LLM_MODEL"], "messages": [{"role": "user", "content": prompt}],
                         "response_format": {"type": "json_object"}, "temperature": 0}, timeout=120)
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"].strip()
    return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", content))["applications"]


def check(portal):
    snap = {"portal": portal["id"], "engine": "email", "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"), "run_id": None,
            "shot": None, "steps": 0, "status": "failed", "applications": [], "notes": None}
    try:
        mails = fetch()
    except Exception as e:
        snap["notes"] = f"gmail: {e}"
        return snap
    if not mails:  # rule 1
        snap["notes"] = "zero application emails found"
        return snap
    newest = {}
    prev = store.latest(portal["id"])
    known = [(a["company"], a["title"], a["status"]) for a in prev["applications"]] if prev else []
    for a in classify(mails, known):
        m = mails[a["i"]]
        try:
            when = parsedate_to_datetime(m["date"])
        except Exception:
            when = None
        app = {"title": a["title"], "company": a["company"], "applied_on": when.strftime("%Y-%m-%d") if when else m["date"],
               "status_raw": a["status_raw"],
               "status": a["state"] if a["state"] in engines.STATES else "Unknown",
               "url": f"https://mail.google.com/mail/u/0/#search/{quote('rfc822msgid:' + m['id'])}", "when": when}
        k = (app["company"].lower(), app["title"].lower())
        if k not in newest or (when and newest[k]["when"] and when > newest[k]["when"]):
            newest[k] = app
    apps = [{k: v for k, v in a.items() if k != "when"} for a in newest.values()]
    if not apps:
        snap["notes"] = "emails found but none described a specific application"
        return snap
    snap.update(status="ok", applications=apps)
    return snap
