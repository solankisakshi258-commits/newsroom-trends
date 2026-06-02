"""YouTube Data API v3 connector — most-popular videos for a region (IN, hi).

Requires YOUTUBE_API_KEY in .env. Self-skips if the key is absent.
Engagement = viewCount; published_at = video publish time.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..models import RawSignal, SourceType
from .base import Connector

log = logging.getLogger("newsroom_trends.connectors.youtube")

_API = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeConnector(Connector):
    name = "youtube"
    source_type = SourceType.YOUTUBE

    def is_available(self) -> bool:
        return super().is_available() and bool(self.config.secret("YOUTUBE_API_KEY"))

    def fetch(self) -> list[RawSignal]:
        import requests

        key = self.config.secret("YOUTUBE_API_KEY")
        if not key:
            return []

        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": self.settings.get("region_code", "IN"),
            "maxResults": int(self.settings.get("max_results", 50)),
            "key": key,
        }
        try:
            resp = requests.get(_API, params=params, timeout=20)
            resp.raise_for_status()
            items = resp.json().get("items", [])
        except Exception as exc:
            log.warning("YouTube fetch failed: %s", exc)
            return []

        signals: list[RawSignal] = []
        for it in items:
            snippet = it.get("snippet", {})
            stats = it.get("statistics", {})
            vid = it.get("id", "")
            signals.append(
                RawSignal(
                    source_type=self.source_type,
                    source_name="YouTube IN",
                    title=snippet.get("title", "").strip(),
                    url=f"https://www.youtube.com/watch?v={vid}",
                    summary=snippet.get("description", "")[:500],
                    published_at=self._parse_iso(snippet.get("publishedAt")),
                    engagement=float(stats.get("viewCount", 0) or 0),
                    lang=snippet.get("defaultAudioLanguage") or "hi",
                    extra={
                        "video_id": vid,
                        "channel": snippet.get("channelTitle"),
                        "likes": stats.get("likeCount"),
                    },
                )
            )
        log.info("YouTube: %d videos", len(signals))
        return signals

    @staticmethod
    def _parse_iso(s: str | None) -> datetime:
        if not s:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
