"""Interest-over-time: persist a score snapshot for each story on every run.

Each run appends one point per story (keyed by a normalized-label hash, the same key
the alerter uses) to a small JSON file. Over many scheduler/CI runs this builds a
time series we can draw as a sparkline. Old stories not seen for `prune_hours` are
dropped so the file stays small.

The file is plain JSON (text-diffable) precisely so it can be committed by GitHub
Actions and accumulate history across cloud runs — that is what makes interest-over-time
work on a static GitHub Pages site.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .models import StoryCluster
from .notify import _story_key

log = logging.getLogger("newsroom_trends.history")


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def _save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def history_path(config: Config) -> Path:
    hist_cfg = config.raw.get("history", {}) or {}
    return config._resolve(hist_cfg.get("file", "data/history.json"))


def record_and_attach(
    config: Config,
    clusters: list[StoryCluster],
    now: datetime | None = None,
) -> dict:
    """Append this run's snapshot per story, prune stale stories, attach series to clusters."""
    hist_cfg = config.raw.get("history", {}) or {}
    max_points = int(hist_cfg.get("max_points", 48))
    prune_hours = float(hist_cfg.get("prune_hours", 72))
    now = now or datetime.now(timezone.utc)
    ts = now.isoformat()
    path = history_path(config)
    data = _load(path)

    for c in clusters:
        key = _story_key(c.label)
        rec = data.setdefault(key, {"label": c.label, "points": []})
        rec["label"] = c.label  # keep latest spelling
        rec["points"].append(
            {
                "ts": ts,
                "opportunity": round(c.opportunity, 4),
                "engagement": round(c.engagement, 4),
                "velocity": round(c.velocity, 4),
                "signals": len(c.signals),
            }
        )
        rec["points"] = rec["points"][-max_points:]

    # Prune stories whose most recent point is older than the retention window.
    cutoff = now - timedelta(hours=prune_hours)
    for key in list(data.keys()):
        points = data[key].get("points") or []
        if not points:
            data.pop(key)
            continue
        try:
            last = datetime.fromisoformat(points[-1]["ts"])
        except (ValueError, KeyError):
            data.pop(key)
            continue
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last < cutoff:
            data.pop(key)

    _save(path, data)

    # Attach the (now-updated) series to each cluster for the report/dashboard.
    for c in clusters:
        c.history = data.get(_story_key(c.label), {}).get("points", [])

    log.info("History: %d stories tracked (file: %s)", len(data), path)
    return data
