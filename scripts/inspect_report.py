"""Quick look at multi-outlet clusters in the latest report (proves cross-competitor dedup)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from newsroom_trends.cli import force_utf8_stdout

force_utf8_stdout()

d = json.load(open("data/reports/latest.json", encoding="utf-8"))
cl = d["clusters"]
multi = [c for c in cl if len(c["signals"]) > 1]
print(f"Total clusters: {len(cl)}  |  multi-outlet stories: {len(multi)}\n")
for c in sorted(multi, key=lambda x: -len(x["signals"]))[:8]:
    outlets = ", ".join(sorted({s["source_name"] for s in c["signals"]}))
    print(f"[opp {c['opportunity']:.3f}] compSat={c['competitor_saturation']:.2f} "
          f"x{len(c['signals'])} ({outlets})")
    print(f"   {c['label'][:78]}")
