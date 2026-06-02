"""Push alerts for high-opportunity stories.

Sends a JSON payload to a webhook (Make.com custom webhook or Slack incoming webhook).
The payload includes a Slack-friendly `text` field AND a structured `alerts` array so
Make.com scenarios can route on individual fields.

De-duplication: a story is identified by a hash of its normalized label. We keep a small
JSON state file of when each story was last alerted and re-suppress it for
`resuppress_hours`, so a 30-minute scheduler doesn't re-alert the same trend every cycle.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import Config
from .models import StoryCluster

log = logging.getLogger("newsroom_trends.notify")

_WS = re.compile(r"\s+")


def _story_key(label: str) -> str:
    norm = _WS.sub(" ", label.strip().lower())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


class AlertState:
    """Tracks when each story was last alerted, persisted to JSON."""

    def __init__(self, path: Path):
        self.path = path
        self._data: dict[str, str] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                self._data = {}

    def is_suppressed(self, key: str, resuppress_hours: float, now: datetime) -> bool:
        last = self._data.get(key)
        if not last:
            return False
        try:
            last_dt = datetime.fromisoformat(last)
        except ValueError:
            return False
        return (now - last_dt) < timedelta(hours=resuppress_hours)

    def mark(self, key: str, now: datetime) -> None:
        self._data[key] = now.isoformat()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def select_alertable(
    clusters: list[StoryCluster],
    config: Config,
    state: AlertState,
    now: datetime | None = None,
) -> list[StoryCluster]:
    """Filter clusters down to the ones worth alerting on this run (threshold + dedup)."""
    cfg = config.alerts
    now = now or datetime.now(timezone.utc)
    min_opp = float(cfg.get("min_opportunity", 0.50))
    max_per = int(cfg.get("max_per_run", 5))
    resuppress = float(cfg.get("resuppress_hours", 12))

    picked: list[StoryCluster] = []
    for c in clusters:
        if c.opportunity < min_opp:
            continue
        key = _story_key(c.label)
        if state.is_suppressed(key, resuppress, now):
            continue
        picked.append(c)
        if len(picked) >= max_per:
            break
    return picked


def build_payload(clusters: list[StoryCluster], now: datetime) -> dict:
    """Webhook payload: Slack-friendly `text` + structured `alerts` for Make.com."""
    lines = [f"🔥 {len(clusters)} trending stor{'y' if len(clusters)==1 else 'ies'} to consider:"]
    alerts = []
    for c in clusters:
        srcs = ", ".join(sorted(t.value for t in c.source_types))
        lines.append(f"• [{c.opportunity:.2f}] {c.label}  ({srcs})")
        rep_url = next((s.url for s in c.signals if s.url), None)
        alerts.append(
            {
                "label": c.label,
                "opportunity": round(c.opportunity, 3),
                "velocity": round(c.velocity, 3),
                "engagement": round(c.engagement, 3),
                "freshness": round(c.freshness, 3),
                "source_breadth": round(c.source_breadth, 3),
                "competitor_saturation": round(c.competitor_saturation, 3),
                "sources": sorted(t.value for t in c.source_types),
                "keywords": c.keywords,
                "angles": c.angles,
                "url": rep_url,
                "signal_count": len(c.signals),
            }
        )
    return {"text": "\n".join(lines), "generated_at": now.isoformat(), "alerts": alerts}


def push(config: Config, payload: dict) -> bool:
    """POST the payload to the configured webhook. Returns True on success.
    If no webhook URL is set, logs the payload and returns False (not an error)."""
    url = config.secret("ALERT_WEBHOOK_URL")
    if not url:
        log.info("No ALERT_WEBHOOK_URL set; computed %d alert(s) but not pushing.",
                 len(payload.get("alerts", [])))
        return False
    try:
        import requests

        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        log.info("Pushed %d alert(s) to webhook (HTTP %d).",
                 len(payload.get("alerts", [])), resp.status_code)
        return True
    except Exception as exc:
        log.warning("Alert webhook push failed: %s", exc)
        return False


def run_alerts(config: Config, clusters: list[StoryCluster]) -> list[StoryCluster]:
    """End-to-end: select, push, persist dedup state. Returns the alerted clusters."""
    if not config.alerts.get("enabled", False):
        return []
    now = datetime.now(timezone.utc)
    state_path = config.db_path.parent / "alert_state.json"
    state = AlertState(state_path)

    picked = select_alertable(clusters, config, state, now=now)
    if not picked:
        log.info("No new stories above alert threshold this run.")
        return []

    payload = build_payload(picked, now)
    push(config, payload)
    for c in picked:
        state.mark(_story_key(c.label), now)
    state.save()
    return picked
