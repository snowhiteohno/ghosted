"""Snapshot store: snapshots/{portal}/{timestamp}.json (+ .jpg evidence), an events log, and the diff."""
import base64
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).parent
SNAP = ROOT / "snapshots"
EVENTS = ROOT / "events.jsonl"


def save(portal_id, data):
    """Write the snapshot. A data-URI screenshot in data["shot"] becomes a sibling .jpg, referenced by relative path."""
    d = SNAP / portal_id
    d.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%Y%m%dT%H%M%S")
    if (data.get("shot") or "").startswith("data:image/jpeg;base64,"):
        (d / f"{stem}.jpg").write_bytes(base64.b64decode(data["shot"].split(",", 1)[1]))
        data["shot"] = f"{portal_id}/{stem}.jpg"
        if data.get("status") == "ok":
            for a in data["applications"]:
                a["shot"] = data["shot"]
    p = d / f"{stem}.json"
    p.write_text(json.dumps(data, indent=1))
    return p


def latest(portal_id, ok_only=True):
    """Newest snapshot for a portal; by default only a successful one (failed checks never become the baseline)."""
    d = SNAP / portal_id
    for p in sorted(d.glob("*.json"), reverse=True) if d.exists() else []:
        data = json.loads(p.read_text())
        if not ok_only or data.get("status") == "ok":
            return data
    return None


SUFFIX = re.compile(r"\b(llc|inc|ltd|pvt|private|limited|corp|corporation|co|gmbh|plc)\b")


def _norm(text, company=False):
    """Lowercase, drop (parentheticals) and punctuation, company suffixes, and plural s, so small renames still match."""
    t = re.sub(r"\([^)]*\)", " ", text.lower())
    t = re.sub(r"[^a-z0-9]+", " ", t)
    if company:
        t = SUFFIX.sub(" ", t)
    words = [w[:-1] if len(w) > 3 and w.endswith("s") else w for w in t.split()]
    return " ".join(w for i, w in enumerate(words) if i == 0 or w != words[i - 1])  # "Internship Internship" happens


def key(app):
    return (_norm(app["company"], company=True), _norm(app["title"]))


def diff(old, new_apps):
    """Applications in new_apps whose state differs from old (a dict keyed by key()). Each carries 'from'."""
    out = []
    for a in new_apps:
        o = old.get(key(a))
        changed = o is None or o["status"] != a["status"] or (a["status"] == "Unknown" and o["status_raw"] != a["status_raw"])
        if changed:
            out.append({**a, "from": o["status"] if o else None})
    return out
