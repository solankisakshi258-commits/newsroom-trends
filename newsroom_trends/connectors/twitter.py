"""Twitter/X connector — recent search via API v2.

Requires TWITTER_BEARER_TOKEN in .env. Self-skips if absent.
Engagement = like + retweet + reply counts. Each configured query is a separate search.

Note: recent-search access depends on your X API tier. On failure (auth/rate limit)
this connector logs and returns what it has rather than raising.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..models import RawSignal, SourceType
from .base import Connector

log = logging.getLogger("newsroom_trends.connectors.twitter")

_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


class TwitterConnector(Connector):
    name = "twitter"
    source_type = SourceType.TWITTER

    def is_available(self) -> bool:
        return super().is_available() and bool(self.config.secret("TWITTER_BEARER_TOKEN"))

    def fetch(self) -> list[RawSignal]:
        import requests

        token = self.config.secret("TWITTER_BEARER_TOKEN")
        if not token:
            return []

        headers = {"Authorization": f"Bearer {token}"}
        max_results = int(self.settings.get("max_results", 50))
        signals: list[RawSignal] = []

        for query in self.settings.get("queries", []):
            params = {
                "query": query,
                "max_results": min(max(max_results, 10), 100),
                "tweet.fields": "created_at,public_metrics,lang",
            }
            try:
                resp = requests.get(_SEARCH_URL, headers=headers, params=params, timeout=20)
                resp.raise_for_status()
                tweets = resp.json().get("data", [])
            except Exception as exc:
                log.warning("Twitter fetch failed for query %r: %s", query, exc)
                continue

            for tw in tweets:
                m = tw.get("public_metrics", {})
                engagement = float(
                    m.get("like_count", 0)
                    + m.get("retweet_count", 0)
                    + m.get("reply_count", 0)
                )
                signals.append(
                    RawSignal(
                        source_type=self.source_type,
                        source_name="Twitter/X",
                        title=(tw.get("text") or "").strip().replace("\n", " ")[:200],
                        url=f"https://twitter.com/i/web/status/{tw.get('id')}",
                        summary=tw.get("text", ""),
                        published_at=self._parse_iso(tw.get("created_at")),
                        engagement=engagement,
                        lang=tw.get("lang"),
                        extra={"query": query, "metrics": m},
                    )
                )
            log.info("Twitter query %r: %d tweets", query, len(tweets))
        return signals

    @staticmethod
    def _parse_iso(s: str | None) -> datetime:
        if not s:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
