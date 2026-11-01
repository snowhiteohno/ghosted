"""Company name -> website domain, so the board can show real logos. One LLM call per batch of new names, cached."""
import json
import re

import store

CACHE = store.SNAP / "domains.json"
DOMAIN = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$")


def load():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def resolve(names):
    """Look up domains for names not in the cache; unknowns are cached as None so they are not asked again."""
    import gmail_engine
    cache = load()
    missing = sorted(set(names) - set(cache))
    if missing:
        prompt = ("For each company or organisation below, give the domain of its main public website (for example "
                  'stripe.com). Use null when you are not sure it is a real organisation. Answer with JSON: '
                  '{"domains": {"<name exactly as given>": "<domain or null>"}}\n\n' + "\n".join(missing))
        got = gmail_engine.llm_json(prompt).get("domains", {})
        for n in missing:
            d = (got.get(n) or "").strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
            cache[n] = d if DOMAIN.match(d) else None
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1, sort_keys=True))
    return {n: cache.get(n) for n in names}
