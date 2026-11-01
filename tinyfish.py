"""Thin TinyFish Agent API client. Reference: https://docs.tinyfish.ai/agent-api/reference"""
import os
import re
import time

import httpx

BASE = "https://agent.tinyfish.ai/v1"
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}
# Rule 5, second enforcement: a step that clicks/types on a write control rejects the run. The verb is required
# because the agent also narrates checks like "Confirm login status", which touch nothing.
WRITE_ACTION = re.compile(r"\b(click|press|tap|select|choose|type|enter|fill|upload)\b.*"
                          r"\b(withdraw|accept|decline|submit|apply|confirm|delete|edit|save|upload)\b", re.I)


def _headers():
    return {"X-API-Key": os.environ["TINYFISH_API_KEY"]}


def run(url, goal, output_schema, profile_id=None, use_vault=False, max_seconds=300, on_live=None):
    """Start an async run and poll it to a terminal state. on_live(url) fires once when the live browser stream exists.
    Returns the run object: run_id, status (COMPLETED|FAILED|CANCELLED), result, error."""
    body = {"url": url, "goal": goal, "output_schema": output_schema,
            "agent_config": {"max_duration_seconds": max_seconds}}
    if profile_id:
        body.update(use_profile=True, profile_id=profile_id)
    if use_vault:
        body["use_vault"] = True
    r = httpx.post(f"{BASE}/automation/run-async", headers=_headers(), json=body, timeout=60)
    r.raise_for_status()
    data = r.json()
    run_id = data.get("run_id")
    if not run_id:
        raise RuntimeError(f"run not created: {data.get('error')}")
    deadline = time.time() + max_seconds + 120
    live_sent = False
    while time.time() < deadline:
        try:
            run = get_run(run_id, screenshots="none")
        except httpx.HTTPError:
            time.sleep(3)
            continue
        if run["status"] in TERMINAL:
            return run
        if on_live and run.get("streaming_url") and not live_sent:
            on_live(run["streaming_url"])
            live_sent = True
        time.sleep(3)
    httpx.post(f"{BASE}/runs/{run_id}/cancel", headers=_headers(), timeout=30)
    return {"run_id": run_id, "status": "FAILED", "error": {"message": "timed out, run cancelled"}}


def get_run(run_id, screenshots="base64"):
    """Run object with steps. Poll with screenshots="none"; fetch once with base64 for the evidence image.
    shortcut: screenshots=base64 is flagged temporary by TinyFish, but url mode lists steps whose image is missing
    from storage and the per-step endpoint 404s on them; switch to the step endpoint once that is fixed."""
    r = httpx.get(f"{BASE}/runs/{run_id}", headers=_headers(), params={"screenshots": screenshots}, timeout=120)
    r.raise_for_status()
    return r.json()


def last_shot(steps):
    """Data URI of the last step that has a screenshot; the final "Task completed" step never does."""
    return next((s["screenshot"] for s in reversed(steps) if s.get("screenshot")), None)


def list_profiles():
    r = httpx.get(f"{BASE}/profiles", headers=_headers(), timeout=30)
    r.raise_for_status()
    return r.json()["profiles"]


def referee(steps):
    """Return the first step action that looks like a write, or None if the run was read-only."""
    for s in steps:
        if WRITE_ACTION.search(s.get("action") or ""):
            return s["action"]
    return None
