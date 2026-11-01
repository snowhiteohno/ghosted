"""Engine task specs (one per engine, not per company), the output schema, and the six-state normalizer."""
import re

NAV = {
    "workday": 'Open "Candidate Home" from the account menu (top right), then its "My Applications" section.',
    "internshala": 'Open "My Applications" from the student menu.',
    "unstop": 'Open "My Applications" from the profile menu.',
    "wellfound": 'This page is the list of jobs you applied to. Check the "Ongoing" tab, then "Archived" if Ongoing is empty.',
}

GOAL = """TASK: ghosted_check_{engine}

You are already logged in via a saved browser profile. {nav}
If you are logged out or land on a login / sign-in page, set status to "logged_out" and stop.

For every application listed, record: job title, company, date applied, the exact status text shown,
and the application URL if a link is visible in the list. Read everything from the list page itself: do not
open individual applications, and leave the URL null rather than clicking to find it. Paginate only if the
list says there are more. The list is often below banners and promotions: scroll down until you see application
rows or an explicit empty-state message before deciding. Finish as soon as the list is recorded.

Do not click Withdraw, Accept, Decline, or any button that changes an application.
Do not upload, edit, or submit anything. Read only.

If the page shows zero applications, set status to "failed" and say why in notes. Do not report an
empty list as success; I know I have applications here."""

SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "logged_out", "failed"]},
        "notes": {"type": "string", "nullable": True},
        "applications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "applied_on": {"type": "string", "nullable": True},
                    "status_raw": {"type": "string"},
                    "url": {"type": "string", "nullable": True},
                },
                "required": ["title", "company", "status_raw"],
            },
        },
    },
    "required": ["status", "applications"],
}

STATES = ["Applied", "Under review", "Assessment", "Interview", "Offer", "Rejected"]

# Order matters: "not selected" must land on Rejected before "selected" lands on Offer.
RULES = [
    ("Rejected", r"reject|not selected|unsuccessful|declin|not shortlisted|no longer|not moving forward|regret|closed"),
    ("Offer", r"offer|selected|hired"),
    ("Interview", r"interview"),
    ("Assessment", r"assessment|test|challenge|assignment|coding round|online round"),
    ("Under review", r"review|shortlist|in process|in progress|screening|under consideration|viewed|seen"),
    ("Applied", r"applied|submitted|received|sent|pending|active|\bnew\b"),
]


def goal_for(engine):
    return GOAL.format(engine=engine, nav=NAV.get(engine, "Open the page that lists my job applications."))


def normalize(raw):
    """Map raw portal status text to one of the six states, or Unknown. The raw text is always kept alongside."""
    text = (raw or "").lower()
    for state, pattern in RULES:
        if re.search(pattern, text):
            return state
    return "Unknown"
