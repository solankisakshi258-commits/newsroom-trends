# How Newsroom Trends works — a beginner's guide

This explains the whole system in plain language: where the data comes from, what every
step does, which free tools are used and why, and how the live website updates itself.
No prior knowledge assumed.

---

## 1. The big picture (in one paragraph)

Every ~30 minutes, a robot (a "scheduled job" on GitHub's servers) wakes up, visits a few
public websites, collects what people in India are searching for and reading right now,
groups similar stories together, scores each story for "how good a story is this to
publish," and rebuilds two web pages showing the results. You just open a link in your
browser and see the latest trends. Nobody has to press a button — it refreshes on its own.

Think of it like a **news scout** that never sleeps: it checks the same sources on a timer,
takes notes, ranks what's hot, and pins the notes to a public board (the website).

---

## 2. Where the data comes from (the "sources")

The system pulls from **three live sources**. All three are **free** and need **no login
or paid key**:

| Source | What we get | How we get it | Free? |
|---|---|---|---|
| **Competitor news (RSS)** | Latest articles from Hindi news sites (ABP Live, TV9 Hindi, NDTV Hindi, Amar Ujala) | Each site publishes an "RSS feed" — a machine-readable list of its latest stories. We just read it. | ✅ Free, public |
| **Google Trends** | India's real-time trending searches + how many people are searching + a related news link | Google publishes a public "trending now" RSS feed. We read it. | ✅ Free, public, no API key |
| **X / Twitter trends** | The trending topics on X in India | X shut off its free data access, so we read a free public website (`trends24.in`) that lists X's India trends. | ✅ Free, but "best-effort" (see §7) |

**What is an "RSS feed"?** It's a standard text format websites use to publish "here are my
latest items." Originally made for news readers. We use it because it's free, stable, and
designed to be read by programs — no scraping tricks needed.

> Three more sources (YouTube, Reddit, official X API) are **built but switched off**, because
> they need paid or registered API keys. The moment you add a key, they turn on automatically.

---

## 3. Why free tools? (and which ones)

The whole project deliberately avoids anything that costs money or locks you in:

| Need | Free tool used | Why this one |
|---|---|---|
| Programming language | **Python** | Free, huge ecosystem, great for data + web. |
| Read RSS feeds | **feedparser** | Free library that understands every RSS variant. |
| Fetch web pages | **requests** | Free, the standard way to download a URL in Python. |
| Store data | **SQLite** | A database that's a single file — built into Python, zero setup, free. |
| Group similar stories | **pure-Python TF-IDF** (hand-written) | Avoids heavy paid/complex AI libraries; runs anywhere. |
| The dashboard web server | **Python's built-in `http.server`** | No web framework needed, nothing to install. |
| Hosting the website | **GitHub Pages** | Free hosting for public projects. |
| The auto-update robot | **GitHub Actions** | Free scheduled jobs for public projects. |

**The bottom line:** running this costs **₹0**. The only thing that would cost money is the
official X/Twitter API (~$100/month) — which is why we use the free trends24 page instead.

---

## 4. The pipeline — what happens on every run, step by step

When the system runs (locally or on GitHub), it does these steps in order. Picture an
assembly line:

1. **Ingest (collect).** Visit each source and download the raw items. A competitor article,
   a Google trend, an X trend — each becomes one "signal" (a single raw data point).

2. **Normalize (clean up).** Strip HTML tags, clean the text, and put every signal into the
   same shape so they're comparable. Hindi text is preserved carefully.

3. **Language filter.** Keep only **English + Hindi** topics. Other scripts (Tamil, Telugu,
   Bengali, etc.) that Google Trends India returns are dropped — your choice.

4. **Store.** Save signals into the SQLite database file (`data/trends.db`). Duplicates are
   ignored, so the same article isn't counted twice.

5. **Cluster (group similar stories).** Many sources may report the *same* event with
   different wording. We measure how similar two signals' words are and group matches into
   one "story." (Example: "India wins final" + "भारत फाइनल जीता" → one story.)

6. **Score.** Give each story numbers (explained in §6) — most importantly an **Opportunity
   score**: "how worth publishing is this right now?"

7. **Categorise.** Tag each story with a topic like *Politics, Cricket & Sports,
   Entertainment, Crime,* etc., using a Hindi+English keyword dictionary.

8. **Record history.** Append today's scores to `data/history.json` so we can later draw
   "how this story's score changed over time" graphs.

9. **Report.** Save everything to `data/reports/latest.json` and rebuild the two web pages.

---

## 5. The two dashboards

- **Classic dashboard** (`/`) — a clean ranked list of trends with scores, source tags, a
  "score over time" line, and the four score bars.
- **Newsroom AI Intelligence** (`/newsroom-intelligence.html`) — an advanced view with
  clickable filters (by source and category), actionable headline numbers (Emerging trends,
  High Discover potential, First-mover gaps, Cross-platform breakouts), competitor analysis,
  forecasting, Discover-potential scores, and topic grouping.

Both read the **same** `latest.json`. The Intelligence page adds an "agent" layer — small
independent analyzers (one for competitors, one for forecasting, one for Discover potential,
one for topic grouping, one for story angles) that each add their own insight.

---

## 6. What the numbers mean (no math degree needed)

Each story gets four ingredient-scores, each from 0 to 1:

- **Vel (Velocity)** — *How fast is it rising?* More recent pickups = higher.
- **Eng (Engagement)** — *How much interest?* Search volume / tweet volume, scaled 0–1.
- **Frsh (Freshness)** — *How new?* 1.0 = just now, fades over hours.
- **Brd (Breadth)** — *On how many platforms?* One source = low, several = high.

These blend into the **Opportunity score** (the headline number):
`40% Velocity + 25% Breadth + 20% Engagement + 15% Freshness`, then reduced if competitors
already covered it.

Extra signals on the Intelligence page:
- **Discover Potential** — chance of doing well on Google Discover (favours fresh, fast,
  visual, high-interest stories). Shown as High / Medium / Low + a 0–100 score.
- **Forecast** — looks at the story's recent score history and says *Rising / Steady /
  Cooling*, with a projected next value.
- **Competitor Analysis** — which competitor outlets already have it ("has") and which don't
  ("gap"); a story nobody has yet is a **first-mover** opportunity.
- **Topic clustering** — groups related stories so you see themes, not just a flat list.

**About "0m ago":** it means the newest signal in that story arrived within the last minute.
For competitor articles it's the real publish time; for Google/X trends it's the moment we
fetched them (those sources don't give a per-trend timestamp).

---

## 7. Honest limitations (what to watch)

- **X / Twitter trends are "best-effort."** Because X has no free data API, we read a free
  public site. If that site changes its layout or blocks automated visits, X trends may
  temporarily disappear from a run. Everything else keeps working. For rock-solid X data
  you'd add a paid X API key (the code already supports it).
- **Three competitor feeds are dead** (Patrika, Aaj Tak, Jagran) — their old feed URLs no
  longer work. The four working ones still provide plenty; fixing the URLs would re-enable them.
- **Keywords are shown in English only** (your choice); the story titles stay in their
  original language.

---

## 8. Does it update automatically? Yes — here's exactly how

**The auto-updater is a GitHub Actions "workflow"** (`.github/workflows/publish.yml`). Think
of it as a free robot living on GitHub's servers with an alarm clock.

**Schedule:** it's set to run on the cron `5,35 * * * *`, which means **twice every hour — at
:05 and :35 past the hour. So roughly every 30 minutes.**

**On each run it:**
1. Starts a fresh free Linux machine on GitHub.
2. Installs the project.
3. Runs the whole pipeline (§4) against the live sources.
4. Rebuilds the two web pages and saves the new history.
5. Commits the updated files back to the repository.
6. GitHub Pages then re-publishes the website with the new content.

**So the update time is ~30 minutes.** Two caveats, in plain terms:
- GitHub's free scheduler is **"best-effort"** — it usually runs on time but can be a few
  minutes late when GitHub is busy. It's not a to-the-second guarantee.
- After the robot finishes, **GitHub Pages takes another 1–2 minutes** to publish the new
  files to the public URL.

It **also** updates instantly whenever you push a change, and you can trigger a run by hand
from the repo's **Actions** tab → "Run workflow".

**You do nothing.** Just open the link whenever you want; what you see is at most ~30 minutes
old. (The web page also auto-refreshes itself in your browser so you don't even need to hit
reload.)

> Note: while your laptop runs the `live` command, it updates locally every 30 minutes too
> (set by `schedule.interval_minutes` in `config.yaml`). But the **public website** updates
> via the GitHub robot, independent of your computer — even when your laptop is off.

---

## 9. The live links

- Classic: **https://solankisakshi258-commits.github.io/newsroom-trends/**
- AI Intelligence: **https://solankisakshi258-commits.github.io/newsroom-trends/newsroom-intelligence.html**

(Project sites live under the `/newsroom-trends/` path — the repository name.)

---

## 10. Where each piece lives (file map)

```
newsroom_trends/
  connectors/        the "collectors" — one file per source (rss, google_trends, twitter, …)
  normalize.py       cleans text + the English/Hindi language filter
  storage/db.py      the SQLite database
  clustering.py      groups similar stories (pure-Python TF-IDF)
  scoring.py         the Vel/Eng/Frsh/Brd + Opportunity math
  categorize.py      tags each story with a category
  history.py         records score-over-time for the graphs
  pipeline.py        runs all the steps in order
  scheduler.py       the every-30-min loop (for local running)
  web/
    dashboard.py     the classic dashboard page + web server
    intelligence.py  the AI Intelligence page
  intelligence/      the "agents": competitor, forecast, discover, topics, angles + engine
  cli.py             commands: run / report / serve / live / export / schedule / sources
.github/workflows/
  publish.yml        the auto-update robot (every ~30 min)
config.yaml          all settings (sources, schedule, filters, scoring weights)
docs/                the published website (index.html + newsroom-intelligence.html)
```

---

## 11. Run it yourself (optional)

```powershell
cd newsroom-trends
pip install -r requirements.txt
$env:PYTHONUTF8 = "1"
python -m newsroom_trends.cli -v live      # runs scheduler + dashboards locally
# then open http://127.0.0.1:8787
```

That's the whole system: **free sources → clean → group → score → publish → auto-repeat
every 30 minutes.**
