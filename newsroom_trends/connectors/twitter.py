"""X / Twitter trends connector.

Two modes, picked automatically:

  1. Official API (reliable) — if TWITTER_BEARER_TOKEN is set, use X API v2 recent search
     over the configured queries. ToS-compliant; needs a paid X API tier.

  2. Best-effort scrape (free, FRAGILE) — otherwise scrape a public trends aggregator
     (trends24.in) for the current India X trends. ⚠️ This is unofficial: the site's HTML
     can change without notice, it may rate-limit or block datacenter IPs (e.g. GitHub
     Actions runners), and it is not guaranteed. On any failure it logs and returns []
     so the rest of the pipeline keeps working — X trends just won't appear that run.

Engagement = tweet volume when the aggregator exposes it (e.g. "12K Tweets"), else 0.
"""

from __future__ import annotations

import html as _html
import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote_plus

from ..models import RawSignal, SourceType
from .base import Connector

log = logging.getLogger("newsroom_trends.connectors.twitter")

_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"

# Best-effort scrape target. Each trend on trends24 is an <a> whose href is an X search
# link; an optional adjacent element carries the tweet volume.
_TRENDS24_URL = "https://trends24.in/{region}/"
_ITEM_RE = re.compile(
    r'<a\b[^>]*\bhref="[^"]*(?:search\?q=|twitter\.com/search|x\.com/search)[^"]*"[^>]*>'
    r'([^<]+)</a>'
    r'(?:(?:(?!<a\b).){0,160}?>\s*([\d.,]+\s*[KMB]?)\s*(?:tweet|Tweet))?',
    re.I | re.S,
)
_VOL_RE = re.compile(r"([\d.,]+)\s*([KMB])?", re.I)


class TwitterConnector(Connector):
    name = "twitter"
    source_type = SourceType.TWITTER

    def is_available(self) -> bool:
        # Available whenever enabled: the scraper needs no credentials. (With a token we
        # use the official API instead, but either way the source can run.)
        return self.config.source_enabled(self.name)

    def fetch(self) -> list[RawSignal]:
        if self.config.secret("TWITTER_BEARER_TOKEN"):
            return self._fetch_api()
        return self._fetch_scrape()

    # --- mode 2: best-effort public scrape --------------------------------------------

    def _fetch_scrape(self) -> list[RawSignal]:
        import requests

        region = self.settings.get("region_path", "india")
        url = _TRENDS24_URL.format(region=region)
        max_results = int(self.settings.get("max_results", 30))
        headers = {
            # A browser-like UA improves the odds the aggregator serves us.
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "en-IN,en;q=0.9,hi;q=0.8",
        }
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
            html_text = resp.text
        except Exception as exc:
            log.warning("X trends scrape failed (best-effort source): %s", exc)
            return []

        now = datetime.now(timezone.utc)
        seen: set[str] = set()
        signals: list[RawSignal] = []
        for match in _ITEM_RE.finditer(html_text):
            term = _html.unescape(match.group(1)).strip()
            if not term or term.lower() in seen:
                continue
            seen.add(term.lower())
            signals.append(
                RawSignal(
                    source_type=self.source_type,
                    source_name="X Trends IN",
                    title=term,
                    url=f"https://x.com/search?q={quote_plus(term)}",
                    summary="",
                    published_at=now,  # aggregator shows "now"; no per-trend timestamp
                    engagement=self._parse_volume(match.group(2)),
                    lang=None,
                    extra={"region": region, "source": "trends24.in", "best_effort": True},
                )
            )
            if len(signals) >= max_results:
                break
        if signals:
            log.info("X Trends %s: %d trends (best-effort scrape)", region, len(signals))
        else:
            log.warning("X trends scrape returned 0 (HTML layout may have changed / blocked).")
        return signals

    @staticmethod
    def _parse_volume(raw: str | None) -> float:
        if not raw:
            return 0.0
        m = _VOL_RE.search(raw)
        if not m:
            return 0.0
        try:
            num = float(m.group(1).replace(",", ""))
        except ValueError:
            return 0.0
        mult = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}.get(
            (m.group(2) or "").lower(), 1
        )
        return num * mult

    # --- mode 1: official X API v2 recent search --------------------------------------

    def _fetch_api(self) -> list[RawSignal]:
        import requests

        token = self.config.secret("TWITTER_BEARER_TOKEN")
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
                log.warning("Twitter API fetch failed for query %r: %s", query, exc)
                continue
            for tw in tweets:
                m = tw.get("public_metrics", {})
                engagement = float(
                    m.get("like_count", 0) + m.get("retweet_count", 0) + m.get("reply_count", 0)
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
            log.info("Twitter API query %r: %d tweets", query, len(tweets))
        return signals

    @staticmethod
    def _parse_iso(s: str | None) -> datetime:
        if not s:
            return datetime.now(timezone.utc)
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
