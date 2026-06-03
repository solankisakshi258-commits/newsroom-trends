"""Diagnose the 'X ago' time display: compare report generated_at vs each top cluster's
representative-signal published_at, and show the source + IST conversion."""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from newsroom_trends.cli import force_utf8_stdout
force_utf8_stdout()

IST = timezone(timedelta(hours=5, minutes=30))
d = json.load(open("data/reports/latest.json", encoding="utf-8"))
gen = datetime.fromisoformat(d["generated_at"])
now = datetime.now(timezone.utc)
print(f"report generated_at : {gen.astimezone(IST):%Y-%m-%d %H:%M IST}")
print(f"real now            : {now.astimezone(IST):%Y-%m-%d %H:%M IST}")
print(f"page age (now-gen)  : {(now-gen).total_seconds()/3600:.1f} h  <- static page is this stale\n")

def rep(c):
    return max(c["signals"], key=lambda s: s.get("engagement", 0))

for c in d["clusters"][:6]:
    r = rep(c)
    pub = datetime.fromisoformat(r["published_at"])
    age_at_gen = (gen - pub).total_seconds()/3600
    age_now = (now - pub).total_seconds()/3600
    print(f"- {c['label'][:50]}")
    print(f"    rep source={r['source_type']}  pub={pub.astimezone(IST):%m-%d %H:%M IST}")
    print(f"    age shown on page={age_at_gen:.1f}h   real age now={age_now:.1f}h")
