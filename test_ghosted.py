"""Self-check for the non-trivial logic. Run: uv run test_ghosted.py
With LLM_API_KEY in .env it also makes one small Gemini call to check the email classifier."""
import base64
import json
import os
import shutil

from dotenv import load_dotenv

load_dotenv(".env")
import check  # noqa: E402
import engines  # noqa: E402
import store  # noqa: E402
import tinyfish  # noqa: E402

n = engines.normalize
assert n("Not Selected") == "Rejected"           # must not fall into Offer via "selected"
assert n("Selected") == "Offer"
assert n("Shortlisted") == "Under review"
assert n("Interview scheduled") == "Interview"
assert n("Application sent") == "Applied" and n("New") == "Applied"
assert n("") == "Unknown" and n(None) == "Unknown"

old = {store.key(a): a for a in [
    {"company": "Acme", "title": "SWE Intern", "status": "Applied", "status_raw": "Applied"},
    {"company": "Beta", "title": "Data Intern", "status": "Unknown", "status_raw": "Stage 2"},
]}
new = [
    {"company": "ACME ", "title": "swe intern", "status": "Interview", "status_raw": "Interview"},   # changed, key is case/space insensitive
    {"company": "Beta", "title": "Data Intern", "status": "Unknown", "status_raw": "Stage 3"},     # Unknown with new raw text counts
    {"company": "Gamma", "title": "ML Intern", "status": "Applied", "status_raw": "Applied"},      # new application
]
d = store.diff(old, new)
assert [(c["company"], c["from"]) for c in d] == [("ACME ", "Applied"), ("Beta", "Unknown"), ("Gamma", None)]
assert store.diff(old, [dict(old[store.key({"company": "Acme", "title": "SWE Intern"})])]) == []
# renames the email classifier produces between reads must still match
assert store.key({"company": "Tower Research Capital LLC", "title": "Campus Positions"}) == \
       store.key({"company": "Tower Research Capital", "title": "Campus Position"})
assert store.key({"company": "National Laboratory of the Rockies (NLR)", "title": "Intern - AI"}) == \
       store.key({"company": "National Laboratory of the Rockies", "title": "Intern, AI"})
assert store.key({"company": "Acme", "title": "Data Intern"}) != store.key({"company": "Acme", "title": "ML Intern"})
assert store.key({"company": "A", "title": "Dev Internship Internship"}) == store.key({"company": "A", "title": "Dev Internship"})

assert tinyfish.referee([{"action": "Click the 'My Applications' tab"}, {"action": "Scroll down"}]) is None
assert tinyfish.referee([{"action": "Click 'Withdraw application'"}]) == "Click 'Withdraw application'"
assert tinyfish.referee([{"action": "Click the 'Applied' filter"}]) is None   # 'applied' is not 'apply'
assert tinyfish.referee([{"action": "Confirm login status"}, {"action": "Verify the applications list"}]) is None  # narration, no click
assert tinyfish.referee([{"action": "Click the 'Confirm' button"}]) == "Click the 'Confirm' button"
assert tinyfish.referee([{"action": "Enter a message and submit the form"}]) is not None
assert tinyfish.last_shot([{"id": "a", "screenshot": "data:x"}, {"id": "b", "screenshot": None}]) == "data:x"
assert tinyfish.last_shot([]) is None

assert check.iso_date("1 Nov' 26") == "2026-11-01"
assert check.iso_date("November 1, 2026 4:18am") == "2026-11-01"
assert check.iso_date("2026-11-01 4:18am") == "2026-11-01" and check.iso_date("2026-09-15") == "2026-09-15"
assert check.iso_date("last week") == "last week" and check.iso_date(None) is None

# manual engine through _read: normalization, default url, and rule 1 on an empty file
manual = store.ROOT / "manual" / "_test.json"
manual.parent.mkdir(exist_ok=True)
try:
    manual.write_text(json.dumps([{"title": "SWE Intern", "company": "Acme", "status_raw": "Shortlisted"}]))
    snap = check._read({"id": "_test", "engine": "manual", "url": "https://x.test"})
    assert snap["status"] == "ok" and snap["applications"][0]["status"] == "Under review"
    assert snap["applications"][0]["url"] == "https://x.test"
    manual.write_text("[]")
    assert check._read({"id": "_test", "engine": "manual"})["status"] == "failed"
finally:
    manual.unlink()

snap = store.save("_test", {"status": "ok", "shot": "data:image/jpeg;base64," + base64.b64encode(b"jpg").decode(),
                            "applications": [{"company": "A", "title": "B"}]})
saved = json.loads(snap.read_text())
assert saved["shot"].endswith(".jpg") and saved["applications"][0]["shot"] == saved["shot"]
assert (store.SNAP / saved["shot"]).read_bytes() == b"jpg"
shutil.rmtree(store.SNAP / "_test")

assert check.telegram("x") is False or os.getenv("TELEGRAM_BOT_TOKEN")  # no-op without a token

if os.getenv("LLM_API_KEY"):
    import gmail_engine
    mails = [
        {"from": "no-reply@us.greenhouse-mail.io", "subject": "Your application to Acme", "date": "Mon, 20 Oct 2026 10:00:00 +0000",
         "body": "Hi, thank you for applying to the Software Engineering Intern role at Acme. After careful consideration "
                 "we have decided not to move forward with your application at this time."},
        {"from": "no-reply@hire.lever.co", "subject": "Interview with Beta Labs", "date": "Tue, 21 Oct 2026 10:00:00 +0000",
         "body": "We'd like to invite you to a 45 minute technical interview for the Data Intern position at Beta Labs. "
                 "Please pick a slot that works for you."},
        {"from": "jobs@greenhouse.io", "subject": "12 new internships this week", "date": "Wed, 22 Oct 2026 10:00:00 +0000",
         "body": "Weekly digest: new openings at companies you follow. Unsubscribe."},
    ]
    apps = gmail_engine.classify(mails)
    states = {a["i"]: a["state"] for a in apps}
    assert states.get(0) == "Rejected" and states.get(1) == "Interview" and 2 not in states, apps
    print("classifier ok:", [(a["company"], a["state"], a["status_raw"]) for a in apps])
print("ok")
