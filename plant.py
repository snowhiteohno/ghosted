"""Plant a status change in a manual portal for the rehearsal, then hit "Check now".
Usage: uv run plant.py <portal> "<company>" "<title>" "<new raw status>"   (run again with the old text to reset)"""
import json
import sys

import store

if len(sys.argv) != 5:
    sys.exit(__doc__)
portal, company, title, status = sys.argv[1:5]
path = store.ROOT / "manual" / f"{portal}.json"
rows = json.loads(path.read_text())
row = next((r for r in rows if store.key(r) == store.key({"company": company, "title": title})), None)
if row is None:
    sys.exit(f"no row {company!r} / {title!r} in {path.name}. Rows: "
             + "; ".join(f"{r['company']} / {r['title']}" for r in rows))
print(f"{portal}: {company} · {title}: {row['status_raw']!r} → {status!r}   (now hit Check now)")
row["status_raw"] = status
path.write_text(json.dumps(rows, indent=1, ensure_ascii=False))
