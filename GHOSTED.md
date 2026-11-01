# Ghosted?

**Every internship you applied to. Real status, pulled from inside each portal. One dashboard. One ping the moment anything moves.**

Swim with TinyFish · Scaler School of Technology · Round 1

---

## What it is

You applied to 40 internships on 40 different career portals. Each one has a status page behind its own login. Nobody checks all 40, so the first you hear is a rejection email three weeks late, or nothing at all.

Ghosted? logs into every portal you applied through, reads the real application status from inside, shows them on one board, and sends you a Telegram ping the minute any status changes. Read-only. Your accounts, your data, nothing submitted.

## Why this is not ordinary agent work

Application trackers (Simplify, Huntr, spreadsheets) track what *you* typed. The actual status lives behind a login on the company's portal and changes without telling you. Reading it means forty authenticated, multi-step sessions, repeated on a schedule. A single agent with one browser tab can check one. A fleet of persistent profiles can check all forty, every morning.

The same insight that powered our tender research applies here: **the long tail of career portals runs on a handful of engines.**

| Engine | Behind portals like | Status visible where |
|---|---|---|
| Workday | Amazon, Adobe, Salesforce, Flipkart, Walmart | Candidate Home → My Applications |
| SmartRecruiters | Visa, Ubisoft, Bosch | Candidate profile → Applications |
| iCIMS / Taleo (Oracle) | Many large enterprises | Candidate dashboard |
| Internshala | Thousands of Indian startups | My Applications |
| Unstop | Campus hiring, hackathons | My Applications |
| Naukri | Most Indian mid-market | Applied jobs |
| **Email engine** (Greenhouse, Lever, Ashby) | Most startups | No portal at all. Status arrives only by email → parsed from Gmail |

One task spec per engine covers hundreds of companies. Onboarding a new engine is an afternoon.

## Feasibility status

**Not yet probed.** Every portal requires the applicant's own login, so probes need your credentials inside a Browser Context Profile. Before committing, run three probes:

1. **Workday** — one company you have actually applied to. Goal: open Candidate Home, read every application's title, company, date applied, and status text.
2. **Internshala** — My Applications. Same fields.
3. **Unstop** — My Applications. Same fields.

Each probe answers: does the profile hold the session across runs, is the status text machine-readable, and how many steps does one check cost. If two of three pass, the project is sound.

**Deliberately excluded:** LinkedIn. Its terms treat any automation on your account as a violation, and it actively detects it. Not worth the risk at a hackathon.

## Scope

**In (v1, 36 hours)**
- Four engines: Workday, Internshala, Unstop, Email (Gmail parse for Greenhouse/Lever/Ashby)
- Onboarding: the user pastes portal URLs and logs in once per profile
- One status check across all portals, on demand and on a schedule (morning + evening)
- Status normalization into six states: Applied · Under review · Assessment · Interview · Offer · Rejected · (Unknown, shown raw)
- Diffing against the previous check; every change is an event
- Telegram alert per change, with the portal link
- Board: one row per application, status, last checked, last changed, source screenshot
- Read-only, always

**Out**
- Applying to jobs, filling forms, uploading resumes
- LinkedIn, Glassdoor, Indeed
- Any action inside a portal beyond reading
- Predicting outcomes

## How TinyFish is used

| TinyFish feature | Where it does the work |
|---|---|
| **Browser Context Profiles** | One per portal. Login once. The session persists across every scheduled check. This is the whole product; without persistent sessions there are 40 OTP prompts every morning. |
| **TinyAgent** | One run per portal per check. Goal: open the applications page, read every row into a structured schema. Engine-level task spec, not per-company. |
| **TinyMonitor** | Drives the cadence. Each portal is a monitor on a 12-hour schedule; its run triggers the agent check and the diff. |
| **Run observability** | Every status on the board links to the screenshot it was read from. Disputes resolve by looking. |
| **TinyVault** | Repairs a stale session without the user re-entering a password, when a portal logs the profile out. |

## Architecture

```
onboarding ─ portal URL + login once per profile
      │
      ▼
scheduler (TinyMonitor, 12 h) ──► TinyAgent run per portal (profile_id)
                                          │
                                          ▼
                                 applications[] per portal
                                          │
                        ┌─────────────────┴──────────────────┐
                        ▼                                    ▼
                normalizer (6 states)              Gmail parser (email engine)
                        └─────────────────┬──────────────────┘
                                          ▼
                             diff vs last snapshot ─► events
                                          │
                              ┌───────────┴───────────┐
                              ▼                       ▼
                           board                 Telegram ping
```

## Agent task spec (one per engine)

```
TASK: ghosted_check_{engine}

You are logged in via this profile. Open the page that lists my job applications
(Workday: "Candidate Home" → "My Applications"; Internshala: "My Applications";
Unstop: "My Applications"). If you are logged out, report LOGGED_OUT and stop.

For every application listed, record: job title, company, date applied, the exact
status text shown, and the application URL if there is one. Paginate if needed.

Do not click Withdraw, Accept, Decline, or any button that changes an application.
Do not upload, edit, or submit anything. Read only.

If the page shows zero applications, report FAILED with a screenshot. Do not report
an empty list as success; I know I have applications here.
```

`output_schema`: `applications[] {title, company, applied_on, status_raw, url}`, `status: ok|logged_out|failed`, `notes`.

## Reliability rules

1. **Zero is a failure.** An empty applications list is reported as FAILED and the board shows "check failed", never "no applications".
2. **Logged out is its own state.** Triggers a Vault repair, then one retry, then a "re-login needed" badge. Never silent.
3. **Raw status is kept.** Normalization maps to six states but the raw text is always shown on hover and in the alert.
4. **A change needs two reads.** A status that flips and flips back within one check is noise, not an event.
5. **Read-only is enforced twice.** In the goal text, and by the referee rejecting any run whose screenshot shows a confirmation dialog.

## Demo (90 seconds)

1. The board: 23 applications, 8 portals, statuses, last-checked times. "This is my actual pipeline."
2. Hit "Check now". Eight runs fan out. Screenshots stream in.
3. One row flips: Under review → Interview. A Telegram ping lands on the phone on stage.
4. Click the row: the Workday screenshot it was read from.
5. Close: "Every student here has a spreadsheet lying to them. This is the truth, from inside the portals, every morning."

## Build plan (36 hours)

| Hours | Deliverable |
|---|---|
| 0–4 | Three profiles logged in. Three probe runs. Decide engines based on results. |
| 4–10 | Engine task specs. Structured output. Normalizer. |
| 10–16 | Snapshot store, diff, events. Gmail parser for the email engine. |
| 16–24 | Board. Telegram bot (free, BotFather token). |
| 24–30 | TinyMonitor schedule. Logged-out handling and Vault repair. |
| 30–36 | Seed with real applications. Deck. Rehearse with one planted status change. |

## Cost

A status check is a short run: roughly 8–15 steps at $0.016, so about $0.15–0.25 per portal. Twenty portals twice a day is about $6–10 a day during the hackathon. Monitor runs are $0.005 each. Fine for the event; a real product would check less often and batch by engine.

## Risks and the answer to each

| Risk | Answer |
|---|---|
| Portals log the profile out between checks | Logged-out state + Vault repair + re-login badge |
| Status text is inconsistent across companies on the same engine | Six-state normalizer keeps raw text; Unknown is a valid state |
| A portal blocks automation | It shows up in the probe; drop it, don't fight it |
| Email-only engines have no status at all | Gmail parse is a first-class engine, not a fallback |
| Privacy: this holds the user's logins | Profiles and Vault, never plaintext; read-only; nothing leaves the user's account |

---

## Builder prompt

Paste this into Claude Code to start the build:

> Build Ghosted? v1 per GHOSTED.md in this folder. Stack: Python 3.12, FastAPI, one HTML page with vanilla JS and server-sent events. TinyFish via the connected MCP tools (run_web_automation with use_profile and profile_id; create_monitor for the schedule; get_run for polling). Profiles exist, one per portal, listed in `portals.json` with engine type and profile id. Step 1: the engine task specs from the doc as templates; run the Workday, Internshala and Unstop probes and print structured results. Step 2: snapshot store as `snapshots/{portal}/{timestamp}.json`, diff, normalizer. Step 3: the board and a Telegram bot via python-telegram-bot with the token in `.env`. Step 4: Gmail engine using the connected Gmail tools, matching Greenhouse/Lever/Ashby sender domains. Enforce every reliability rule in the doc, especially rule 1 (zero is FAILED) and rule 5 (read-only, twice).
