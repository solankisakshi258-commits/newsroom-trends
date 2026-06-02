"""Google Trends connector — realtime "trending now" searches for a region.

Source: the public realtime trending feed
    https://trends.google.com/trending/rss?geo=IN

This is Google's realtime trending-searches feed (no API key, no pytrends — pytrends'
endpoint now 404s). Each item carries:
  * the search term + approximate search volume (`ht:approx_traffic`)  -> engagement
  * a publish time                                                     -> freshness/velocity
  * one or more related news items (title, url, source)                -> the "relevant URL"

We parse with ElementTree (not feedparser) so we can pull ALL nested `ht:news_item`
elements, not just the last. On any network/parse failure we log and return [].
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET

from ..models import RawSignal, SourceType
from .base import Connector

log = logging.getLogger("newsroom_trends.connectors.google_trends")

_RSS_URL = "https://trends.google.com/trending/rss?geo={geo}"
_HT_NS = "https://trends.google.com/trending/rss"
_NUM_RE = re.compile(r"[\d,]+")


class GoogleTrendsConnector(Connector):
    name = "google_trends"
    source_type = SourceType.GOOGLE_TRENDS

    def fetch(self) -> list[RawSignal]:
        try:
            import requests
        except ImportError:
            log.error("requests not installed; `pip install requests`. Skipping Google Trends.")
            return []

        geo = self.settings.get("geo", "IN")
        url = _RSS_URL.format(geo=geo)
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "newsroom-trends/0.1"})
            resp.raise_for_status()
            root = ET.fromstring(resp.content)
        except Exception as exc:
            log.warning("Google Trends realtime fetch failed: %s", exc)
            return []

        signals: list[RawSignal] = []
        for item in root.iter("item"):
            term = (item.findtext("title") or "").strip()
            if not term:
                continue
            traffic_raw = (item.findtext(f"{{{_HT_NS}}}approx_traffic") or "").strip()
            news = self._news_items(item)
            # The "relevant URL" = first related news article; fall back to Trends explore.
            explore_url = f"https://trends.google.com/trends/explore?geo={geo}&q={quote_plus(term)}"
            relevant_url = news[0]["url"] if news else explore_url

            signals.append(
                RawSignal(
                    source_type=self.source_type,
                    source_name=f"Google Trends {geo}",
                    title=term,
                    url=relevant_url,
                    summary=" | ".join(n["title"] for n in news[:3]),
                    published_at=self._pub_date(item),
                    engagement=self._traffic_to_float(traffic_raw),
                    lang="hi",
                    extra={
                        "geo": geo,
                        "approx_traffic": traffic_raw,            # e.g. "50,000+"
                        "explore_url": explore_url,
                        "news_items": news,                       # full related-article list
                        "realtime": True,
                    },
                )
            )
        log.info("Google Trends %s: %d realtime trending searches", geo, len(signals))
        return signals

    # --- parsing helpers ---------------------------------------------------------------

    def _news_items(self, item: ET.Element) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        for ni in item.findall(f"{{{_HT_NS}}}news_item"):
            out.append(
                {
                    "title": (ni.findtext(f"{{{_HT_NS}}}news_item_title") or "").strip(),
                    "url": (ni.findtext(f"{{{_HT_NS}}}news_item_url") or "").strip(),
                    "source": (ni.findtext(f"{{{_HT_NS}}}news_item_source") or "").strip(),
                }
            )
        return [n for n in out if n["url"]]

    @staticmethod
    def _traffic_to_float(raw: str) -> float:
        """'50,000+' -> 50000.0"""
        m = _NUM_RE.search(raw or "")
        if not m:
            return 0.0
        try:
            return float(m.group(0).replace(",", ""))
        except ValueError:
            return 0.0

    @staticmethod
    def _pub_date(item: ET.Element) -> datetime:
        raw = item.findtext("pubDate")
        if raw:
            try:
                dt = parsedate_to_datetime(raw)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
        return datetime.now(timezone.utc)
