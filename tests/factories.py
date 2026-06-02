"""Synthetic signal builders so tests need no network."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from newsroom_trends.models import RawSignal, SourceType


def raw(
    title: str,
    source_type: SourceType = SourceType.RSS,
    source_name: str = "Test",
    summary: str = "",
    engagement: float = 0.0,
    age_hours: float = 1.0,
    url: str | None = None,
) -> RawSignal:
    published = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return RawSignal(
        source_type=source_type,
        source_name=source_name,
        title=title,
        url=url or f"https://example.com/{abs(hash(title)) % 10_000}",
        summary=summary,
        published_at=published,
        engagement=engagement,
        lang="hi",
    )
