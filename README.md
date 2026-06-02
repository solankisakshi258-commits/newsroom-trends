# Newsroom Trends — Hindi Editorial Intelligence Pipeline

Multi-source trend detection and editorial intelligence for a Hindi digital newsroom.
It ingests signals from Google Trends, YouTube, Reddit, Twitter/X, and competitor
Hindi news RSS feeds (Patrika, ABP Live, Aaj Tak, TV9 Hindi, NDTV, Jagran, Amar Ujala),
normalizes them into a common schema, clusters them into stories, scores each story for
virality / velocity / editorial opportunity, and emits a ranked trend report.

## Why this exists

A Hindi newsroom competes for Google Discover and search traffic on a clock measured in
minutes. This pipeline answers three editorial questions automatically:

1. **What is rising right now?** (velocity across sources)
2. **Who already has it?** (competitor coverage gap)
3. **What should we publish, and how should we frame it for Discover?** (opportunity score + angle hints)

## Architecture

```
            ┌──────────── connectors/ ────────────┐
 Google Trends  YouTube  Reddit  Twitter/X  RSS(competitors)
            └──────────────┬───────────────────────┘
                           │  RawSignal[]
                           ▼
                     normalize.py            → Signal[]   (common schema)
                           ▼
                     storage/ (SQLite)       → persisted, deduped
                           ▼
                     clustering.py           → StoryCluster[]  (group signals into stories)
                           ▼
                     scoring.py              → scored & ranked
                           ▼
                     pipeline.py / cli.py    → TrendReport (JSON + console)
```

Everything is gated behind a `Connector` interface, so adding a source = one new file.
Storage is abstracted so the SQLite backend can be swapped for Postgres later without
touching the pipeline.

## Quick start

```powershell
cd newsroom-trends
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt        # feedparser + requests are enough for the RSS MVP

# Run the pipeline using only the no-API-key sources (RSS competitor feeds):
python -m newsroom_trends.cli run --only rss

# Run everything that has credentials configured:
python -m newsroom_trends.cli run

# Show the latest report:
python -m newsroom_trends.cli report --top 20
```

The RSS path needs **no API keys** and works out of the box — that is the MVP.
Google Trends needs `pytrends` (in requirements). YouTube / Reddit / Twitter need keys
set in `.env` (see `.env.example`); without keys they are skipped, not failed.

## Configuration

- `config.yaml` — source list, competitor feed URLs, scoring weights, clustering threshold.
- `.env` — secrets (API keys). Copy from `.env.example`.

## Layout

```
newsroom_trends/
  config.py        load + validate config.yaml and .env
  models.py        RawSignal, Signal, StoryCluster, TrendReport dataclasses
  normalize.py     RawSignal -> Signal, Hindi-aware text cleanup
  clustering.py    pure-Python TF-IDF cosine clustering (no heavy deps)
  scoring.py       velocity / virality / opportunity scoring
  pipeline.py      orchestration (ingest -> normalize -> store -> cluster -> score)
  cli.py           command-line entrypoint
  storage/
    db.py          SQLite schema + repository
  connectors/
    base.py        Connector ABC
    rss.py         competitor Hindi news feeds  (no key)
    google_trends.py  pytrends                  (no key)
    youtube.py     YouTube Data API             (key)
    reddit.py      Reddit API                   (key)
    twitter.py     Twitter/X API                (key)
```

## Status of each connector

| Source        | Auth        | Status in scaffold |
|---------------|-------------|--------------------|
| RSS competitors | none      | ✅ implemented, runs |
| Google Trends | none (pytrends) | ✅ implemented (needs `pytrends`) |
| YouTube       | API key     | 🔌 implemented, gated on key |
| Reddit        | OAuth app   | 🔌 implemented, gated on key |
| Twitter/X     | Bearer token | 🔌 implemented, gated on key |

See `docs/` notes inside each connector for the exact env vars.
