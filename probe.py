"""Step 1: run the engine probes and print structured results.
Usage:  uv run probe.py                 # every non-email portal in portals.json
        uv run probe.py internshala     # one or more portal ids
        uv run probe.py --profiles      # list Browser Context Profiles
        uv run probe.py --telegram      # send a test ping"""
import json
import sys

from dotenv import load_dotenv

load_dotenv()
import check  # noqa: E402
import tinyfish  # noqa: E402

if "--profiles" in sys.argv:
    print(json.dumps(tinyfish.list_profiles(), indent=1))
    sys.exit()
if "--telegram" in sys.argv:
    print("sent" if check.telegram("Ghosted? test ping") else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in .env")
    sys.exit()

portals = json.load(open("portals.json"))
want = sys.argv[1:] or [p["id"] for p in portals if p["engine"] != "email"]
for p in portals:
    if p["id"] not in want:
        continue
    print(f"\n=== {p['id']} ({p['engine']}) {p.get('url', '')}", flush=True)
    snap, events = check.check_portal(p, on_live=lambda u: print("live:", u, flush=True))
    print(json.dumps(snap, indent=1))
    print(f"status: {snap['status']}   steps: {snap['steps']} (≈ ${snap['steps'] * 0.016:.2f})   events: {len(events)}")
