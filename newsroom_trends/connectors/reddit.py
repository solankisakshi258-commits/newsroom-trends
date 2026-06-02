"""Reddit connector — hot posts from configured subreddits via the OAuth API.

Requires REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT in .env.
Uses the application-only (client_credentials) OAuth flow — no user login needed.
Engagement = upvote score. Self-skips if credentials are absent.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from ..models import RawSignal, SourceType
from .base import Connector

log = logging.getLogger("newsroom_trends.connectors.reddit")

_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_API_BASE = "https://oauth.reddit.com"


class RedditConnector(Connector):
    name = "reddit"
    source_type = SourceType.REDDIT

    def is_available(self) -> bool:
        return super().is_available() and bool(
            self.config.secret("REDDIT_CLIENT_ID")
            and self.config.secret("REDDIT_CLIENT_SECRET")
        )

    def fetch(self) -> list[RawSignal]:
        import requests

        token = self._get_token(requests)
        if not token:
            return []

        ua = self.config.secret("REDDIT_USER_AGENT") or "newsroom-trends/0.1"
        headers = {"Authorization": f"bearer {token}", "User-Agent": ua}
        limit = int(self.settings.get("limit", 50))
        signals: list[RawSignal] = []

        for sub in self.settings.get("subreddits", []):
            try:
                resp = requests.get(
                    f"{_API_BASE}/r/{sub}/hot",
                    headers=headers,
                    params={"limit": limit},
                    timeout=20,
                )
                resp.raise_for_status()
                children = resp.json().get("data", {}).get("children", [])
            except Exception as exc:
                log.warning("Reddit fetch failed for r/%s: %s", sub, exc)
                continue

            for child in children:
                d = child.get("data", {})
                if d.get("stickied"):
                    continue
                signals.append(
                    RawSignal(
                        source_type=self.source_type,
                        source_name=f"r/{sub}",
                        title=(d.get("title") or "").strip(),
                        url="https://www.reddit.com" + d.get("permalink", ""),
                        summary=(d.get("selftext") or "")[:500],
                        published_at=datetime.fromtimestamp(
                            d.get("created_utc", 0), tz=timezone.utc
                        ),
                        engagement=float(d.get("score", 0) or 0),
                        lang=None,
                        extra={
                            "subreddit": sub,
                            "num_comments": d.get("num_comments"),
                            "external_url": d.get("url"),
                        },
                    )
                )
            log.info("Reddit r/%s: %d posts", sub, len(children))
        return signals

    def _get_token(self, requests) -> str | None:
        cid = self.config.secret("REDDIT_CLIENT_ID")
        secret = self.config.secret("REDDIT_CLIENT_SECRET")
        ua = self.config.secret("REDDIT_USER_AGENT") or "newsroom-trends/0.1"
        try:
            resp = requests.post(
                _TOKEN_URL,
                auth=(cid, secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": ua},
                timeout=20,
            )
            resp.raise_for_status()
            return resp.json().get("access_token")
        except Exception as exc:
            log.warning("Reddit auth failed: %s", exc)
            return None
