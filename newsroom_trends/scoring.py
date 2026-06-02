"""Scoring: turn clusters of signals into ranked editorial opportunities.

Each cluster gets four 0..1 sub-scores, blended by config weights into an
`opportunity` score, then docked by a competitor-saturation penalty:

  velocity        rising-ness — recent signals vs. older signals in the window
  source_breadth  how many distinct source TYPES carry the story (cross-platform = strong)
  engagement      normalized engagement (views/upvotes/likes/search interest)
  freshness       recency of the newest signal, exponential half-life decay

  opportunity = (Σ wᵢ·scoreᵢ) · (1 − penalty·competitor_saturation)

`angles` are lightweight Discover framing hints derived from which sources carry the
story and how saturated competitors are — not AI-generated prose, just signposts.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from .models import Signal, SourceType, StoryCluster

_DEFAULT_WEIGHTS = {
    "velocity": 0.40,
    "source_breadth": 0.25,
    "engagement": 0.20,
    "freshness": 0.15,
}
_ALL_SOURCE_TYPES = len(SourceType)


def normalize_engagement(signals: list[Signal]) -> None:
    """Fill `engagement_norm` (0..1) per source type, in place.

    Engagement scales are wildly different across sources (YouTube views vs Reddit
    upvotes), so we normalize within each source type using a log transform to tame
    heavy tails, scaled to the max within that type.
    """
    by_type: dict[SourceType, list[Signal]] = defaultdict(list)
    for s in signals:
        by_type[s.source_type].append(s)

    for group in by_type.values():
        logs = [math.log1p(max(0.0, s.engagement)) for s in group]
        hi = max(logs) if logs else 0.0
        for s, lv in zip(group, logs):
            s.engagement_norm = (lv / hi) if hi > 0 else 0.0


def score_clusters(
    clusters: list[StoryCluster],
    scoring_cfg: dict[str, Any] | None,
    window_hours: int,
    now: datetime | None = None,
) -> list[StoryCluster]:
    """Compute all sub-scores + opportunity for each cluster, return sorted desc."""
    cfg = scoring_cfg or {}
    weights = _normalized_weights(cfg.get("weights"))
    penalty = float(cfg.get("competitor_penalty", 0.30))
    half_life = float(cfg.get("freshness_half_life_hours", 6))
    now = now or datetime.now(timezone.utc)

    # Normalize engagement across the full signal pool so cross-cluster comparison is fair.
    all_signals = [s for c in clusters for s in c.signals]
    normalize_engagement(all_signals)

    max_competitors = max((c.competitor_count for c in clusters), default=0)

    for c in clusters:
        c.velocity = _velocity(c, window_hours, now)
        c.source_breadth = len(c.source_types) / _ALL_SOURCE_TYPES
        c.engagement = _avg_engagement(c)
        c.freshness = _freshness(c, half_life, now)
        c.competitor_saturation = (
            c.competitor_count / max_competitors if max_competitors else 0.0
        )

        base = (
            weights["velocity"] * c.velocity
            + weights["source_breadth"] * c.source_breadth
            + weights["engagement"] * c.engagement
            + weights["freshness"] * c.freshness
        )
        c.opportunity = base * (1.0 - penalty * c.competitor_saturation)
        c.angles = _angles(c)

    clusters.sort(key=lambda c: c.opportunity, reverse=True)
    return clusters


# --- sub-scores --------------------------------------------------------------------

def _velocity(c: StoryCluster, window_hours: int, now: datetime) -> float:
    """Rising-ness: fraction of the cluster's signals published in the recent half of
    the window, scaled so a story that's all-recent approaches 1.0 and one that's all-old
    approaches 0. Also rewards raw signal volume slightly (more pickups = hotter)."""
    if not c.signals:
        return 0.0
    half = window_hours / 2.0
    recent = sum(
        1 for s in c.signals if (now - s.published_at).total_seconds() / 3600.0 <= half
    )
    recency_ratio = recent / len(c.signals)
    # Volume bonus saturates: 1 signal -> 0, many -> ~1, via log.
    volume = math.log1p(len(c.signals)) / math.log1p(10)
    return min(1.0, 0.7 * recency_ratio + 0.3 * min(1.0, volume))


def _avg_engagement(c: StoryCluster) -> float:
    vals = [s.engagement_norm for s in c.signals]
    return sum(vals) / len(vals) if vals else 0.0


def _freshness(c: StoryCluster, half_life_hours: float, now: datetime) -> float:
    """Exponential decay on the age of the newest signal in the cluster."""
    if not c.signals:
        return 0.0
    newest = max(s.published_at for s in c.signals)
    age_h = max(0.0, (now - newest).total_seconds() / 3600.0)
    return math.pow(0.5, age_h / half_life_hours) if half_life_hours > 0 else 0.0


def _normalized_weights(raw: dict[str, Any] | None) -> dict[str, float]:
    w = dict(_DEFAULT_WEIGHTS)
    if raw:
        for k in w:
            if k in raw:
                w[k] = float(raw[k])
    total = sum(w.values()) or 1.0
    return {k: v / total for k, v in w.items()}


# --- editorial angle hints ---------------------------------------------------------

def _angles(c: StoryCluster) -> list[str]:
    """Cheap, deterministic Discover framing hints from signal composition."""
    angles: list[str] = []
    types = c.source_types

    if SourceType.GOOGLE_TRENDS in types:
        angles.append("High search intent — lead with the exact query in the H1 for Discover/SEO.")
    if SourceType.YOUTUBE in types:
        angles.append("Video demand present — pair the article with an embedded/short video.")
    if {SourceType.TWITTER, SourceType.REDDIT} & types:
        angles.append("Social conversation live — add a reactions/what-people-are-saying section.")
    if c.competitor_count == 0:
        angles.append("No competitor coverage yet — first-mover window, publish fast.")
    elif c.competitor_saturation >= 0.7:
        angles.append("Saturated by competitors — differentiate with an explainer or local angle.")
    if len(types) >= 3:
        angles.append("Cross-platform breakout — strong candidate for a top-of-homepage push.")
    return angles
