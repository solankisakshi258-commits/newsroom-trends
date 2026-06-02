"""Core data models shared across the pipeline.

The pipeline has three layers of representation:

  RawSignal   -- whatever a connector pulled, lightly typed. Source-specific quirks live here.
  Signal      -- normalized, deduped, common schema. The unit of clustering and storage.
  StoryCluster-- a group of Signals judged to be about the same story, plus scores.

TrendReport is the final, ranked, serializable artifact handed to the newsroom.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SourceType(str, Enum):
    """The kind of source a signal came from. Used for source-breadth scoring."""

    GOOGLE_TRENDS = "google_trends"
    YOUTUBE = "youtube"
    REDDIT = "reddit"
    TWITTER = "twitter"
    RSS = "rss"  # competitor news feeds


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class RawSignal:
    """Raw output of a connector before normalization.

    Connectors should fill what they can; missing numeric engagement is fine (0.0).
    `extra` carries source-specific fields (e.g. video_id, subreddit) for debugging
    and downstream enrichment without polluting the common schema.
    """

    source_type: SourceType
    source_name: str  # e.g. "Aaj Tak", "r/india", "Google Trends IN"
    title: str
    url: Optional[str] = None
    summary: str = ""
    published_at: Optional[datetime] = None
    engagement: float = 0.0  # raw, source-native (views, upvotes, search interest…)
    lang: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Signal:
    """Normalized signal — the unit stored, deduped, and clustered."""

    id: str  # stable hash, used for dedup
    source_type: SourceType
    source_name: str
    title: str
    text: str  # cleaned title + summary, used for clustering
    url: Optional[str]
    published_at: datetime
    ingested_at: datetime
    engagement: float
    engagement_norm: float = 0.0  # 0..1 within its source type, filled by scoring
    lang: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def make_id(source_type: SourceType, url: Optional[str], title: str) -> str:
        """Stable dedup id: prefer URL, fall back to source+title."""
        basis = (url or f"{source_type.value}:{title}").strip().lower()
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


@dataclass(slots=True)
class StoryCluster:
    """A group of signals about the same story, with computed scores."""

    id: str
    label: str  # representative title (the highest-engagement signal's title)
    keywords: list[str]
    signals: list[Signal]
    # Scores (all 0..1 unless noted), filled by scoring.py:
    velocity: float = 0.0
    source_breadth: float = 0.0
    engagement: float = 0.0
    freshness: float = 0.0
    competitor_saturation: float = 0.0  # fraction of competitor coverage
    opportunity: float = 0.0  # final blended, penalty-adjusted score
    angles: list[str] = field(default_factory=list)  # Discover framing hints
    history: list[dict[str, Any]] = field(default_factory=list)  # interest-over-time points
    category: str = "General"  # editorial category (Politics, Sports, …)

    @property
    def source_types(self) -> set[SourceType]:
        return {s.source_type for s in self.signals}

    @property
    def competitor_count(self) -> int:
        return sum(1 for s in self.signals if s.source_type == SourceType.RSS)


@dataclass(slots=True)
class TrendReport:
    """Final ranked artifact for the newsroom."""

    generated_at: datetime
    window_hours: int
    signal_count: int
    source_breakdown: dict[str, int]
    clusters: list[StoryCluster]

    def to_dict(self) -> dict[str, Any]:
        def _ser(obj: Any) -> Any:
            if isinstance(obj, datetime):
                return obj.isoformat()
            if isinstance(obj, SourceType):
                return obj.value
            if isinstance(obj, Enum):
                return obj.value
            raise TypeError(f"not serializable: {type(obj)}")

        import json

        # asdict handles nested dataclasses; round-trip through json for enum/datetime.
        return json.loads(json.dumps(asdict(self), default=_ser))
