"""Ghosted? board: FastAPI, one HTML page, server-sent events.
A full check runs on demand (POST /api/check) and every CHECK_INTERVAL_HOURS."""
import asyncio
import json
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse

load_dotenv()
import check  # noqa: E402
import logos  # noqa: E402
import engines  # noqa: E402
import store  # noqa: E402

ROOT = Path(__file__).parent
PORTALS = json.loads((ROOT / "portals.json").read_text())
URLS = {p["id"]: p.get("url") for p in PORTALS}
state = {p["id"]: store.latest(p["id"], ok_only=False)
         or {"portal": p["id"], "engine": p["engine"], "status": "never", "applications": []} for p in PORTALS}
events = [json.loads(l) for l in store.EVENTS.read_text().splitlines()] if store.EVENTS.exists() else []
listeners = set()
domains = logos.load()
checking = False
_task = None
COOLDOWN = float(os.getenv("CHECK_COOLDOWN_MIN", "10")) * 60  # bounds spend when the board is public
last_check = 0.0
# Demo control: the raw status a manual row moves to when a judge presses "Simulate a change".
NEXT_RAW = {"Applied": "Shortlisted", "Unknown": "Shortlisted", "Under review": "Interview scheduled",
            "Assessment": "Interview scheduled", "Interview": "Offer extended"}


def payload():
    portals = {k: {**v, "url": URLS.get(k)} for k, v in state.items()}  # snapshots do not carry the portal address
    return json.dumps({"portals": portals, "events": events[-50:], "checking": checking, "domains": domains,
                       "cooldown": max(0, int(last_check + COOLDOWN - time.time())), "bot": os.getenv("TELEGRAM_BOT_NAME")})


def broadcast():
    for q in listeners:
        q.put_nowait(payload())


async def check_one(portal):
    pid = portal["id"]
    loop = asyncio.get_running_loop()

    def live(url):  # called from the worker thread, so hop back to the loop before touching queues
        state[pid]["live"] = url
        loop.call_soon_threadsafe(broadcast)

    state[pid] = {**state[pid], "status": "checking"}
    broadcast()
    try:
        snap, evs = await asyncio.to_thread(check.check_portal, portal, live)
    except Exception as e:
        snap, evs = {**state[pid], "status": "failed", "notes": str(e), "checked_at": check.now_iso(), "live": None}, []
    state[pid] = snap
    events.extend(evs)
    broadcast()
    await enrich()
    for e in evs:
        try:
            await asyncio.to_thread(check.telegram, check.format_event(e))
        except Exception as err:
            print("telegram failed:", err)


async def enrich():
    """Fetch logo domains for companies the board has not seen before. Cosmetic, so failures are only logged."""
    names = {a["company"] for p in state.values() for a in p.get("applications", [])} - set(domains)
    if not names:
        return
    try:
        domains.update(await asyncio.to_thread(logos.resolve, names))
        broadcast()
    except Exception as e:
        print("logo lookup failed:", e)


async def check_all():
    global checking
    if checking:
        return
    checking = True
    broadcast()
    try:
        await asyncio.gather(*(check_one(p) for p in PORTALS))
    finally:
        checking = False
        broadcast()


async def scheduler():
    hours = float(os.getenv("CHECK_INTERVAL_HOURS", "12"))
    while True:
        await asyncio.sleep(hours * 3600)
        await check_all()


@asynccontextmanager
async def lifespan(app):
    for p in PORTALS:  # manual portals are free and instant: read them once so the board is never empty
        if p["engine"] == "manual" and state[p["id"]]["status"] == "never":
            await check_one(p)
    task = asyncio.create_task(scheduler())
    asyncio.create_task(enrich())
    yield
    task.cancel()


app = FastAPI(title="Ghosted?", lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
def board():
    return (ROOT / "board.html").read_text()


@app.get("/api/state")
def api_state():
    return Response(payload(), media_type="application/json")


@app.post("/api/check", status_code=202)
async def api_check():
    global _task, last_check
    if checking:
        raise HTTPException(409, "a check is already running")
    wait = last_check + COOLDOWN - time.time()
    if wait > 0:
        raise HTTPException(429, f"next check in {int(wait)}s")
    last_check = time.time()
    _task = asyncio.create_task(check_all())
    return {"started": True}


@app.post("/api/simulate", status_code=202)
async def api_simulate():
    """Demo control, labeled as such on the board: advance one manual row and re-check only that portal (free, instant)."""
    global _task
    for p in PORTALS:
        if p["engine"] != "manual":
            continue
        path = store.ROOT / "manual" / f"{p['id']}.json"
        rows = json.loads(path.read_text())
        row = next((r for r in rows if engines.normalize(r["status_raw"]) in NEXT_RAW), None)
        if row is None:
            continue
        before, row["status_raw"] = row["status_raw"], NEXT_RAW[engines.normalize(row["status_raw"])]
        path.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
        _task = asyncio.create_task(check_one(p))
        return {"portal": p["id"], "company": row["company"], "title": row["title"], "from": before, "to": row["status_raw"]}
    raise HTTPException(409, "every manual row is already at Offer or Rejected; reset manual/*.json")


@app.get("/api/stream")
async def stream():
    q = asyncio.Queue()
    listeners.add(q)

    async def gen():
        try:
            yield f"data: {payload()}\n\n"
            while True:
                yield f"data: {await q.get()}\n\n"
        finally:
            listeners.discard(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/shot/{portal}/{name}")
def shot(portal: str, name: str):
    if portal not in state or not re.fullmatch(r"\w+\.jpg", name) or not (store.SNAP / portal / name).exists():
        raise HTTPException(404)
    return FileResponse(store.SNAP / portal / name, media_type="image/jpeg")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
