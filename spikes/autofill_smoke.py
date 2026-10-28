"""Run the auto-fill analysis (no DB writes) on a sample and print what it found.

    docker compose exec worker python spikes/autofill_smoke.py /samples/<file>.pdf [--json]

Output contains document values: confidential, terminal only.
"""

import json
import sys
from pathlib import Path

from dbresearch.autofill.pipeline import analyse
from dbresearch.db import new_session

with new_session() as db:
    _, _, d = analyse(Path(sys.argv[1]), db)

if "--json" in sys.argv:
    print(json.dumps(d, ensure_ascii=False, indent=1, default=str))
    sys.exit()
print("sections:", [(s["template"], s["attachment_no"], s["pages"]) for s in d["sections"]])
for name, v in sorted(d["fields"].items()):
    print(
        f"  {name:15} p{v['page']} {v['source']:8} {v['confidence']:.2f} "
        f"-> {str(v['value'])[:70]}  alt={str(v['alternatives'])[:50]}"
    )
print("inferred:", d["inferred"])
print("people:", [(p["prefix_th"], p["name"][:25], p["role"], p["share_pct"]) for p in d["people"]])
print(
    "checks:", [(c["group_key"], c["category_name"], c["score"], c["suggest"]) for c in d["checks"]]
)
print("hints:", [(h["group_key"], h.get("category_name"), h.get("label")) for h in d["hints"]])
print("warnings:", d["warnings"])
