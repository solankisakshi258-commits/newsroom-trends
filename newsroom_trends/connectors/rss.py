"""Competitor Hindi news RSS connector. No API key required — this is the MVP source.

Reads every feed in config `competitors:` and emits one RawSignal per item. The
presence of a story in many competitor feeds is what drives the competitor-saturation
penalty in scoring (a story everyone already has is a weaker opportunity).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from time import mktime
from typing import Any

from ..models import RawSignal, SourceType
from .base import Connector

log = logging.getLogger("newsroom_trends.connectors.rss")


class RSSConnector(Connector):
    name = "rss"
    source_type = SourceType.RSS

    def fetch(self) -> list[RawSignal]:
        try:
            import feedparser
        except ImportError:
            log.error("feedparser not installed; `pip install feedparser`. Skipping RSS.")
            return []

        signals: list[RawSignal] = []
        for comp in self.config.competitors:
            name = comp.get("name", "competitor")
            url = comp.get("url")
            if not url:
                continue
            try:
                parsed = feedparser.parse(url)
            except Exception as exc:  # network / parse errors must not sink the run
                log.warning("RSS fetch failed for %s (%s): %s", name, url, exc)
                continue
            if getattr(parsed, "bozo", 0) and not parsed.entries:
                log.warning("RSS feed empty/malformed for %s (%s)", name, url)
                continue

            for entry in parsed.entries:
                signals.append(self._entry_to_signal(name, entry))
            log.info("RSS %s: %d items", name, len(parsed.entries))
        return signals

    def _entry_to_signal(self, source_name: str, entry: Any) -> RawSignal:
        published = self._parse_published(entry)
        summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        return RawSignal(
            source_type=self.source_type,
            source_name=source_name,
            title=getattr(entry, "title", "").strip(),
            url=getattr(entry, "link", None),
            summary=summary,
            published_at=published,
            engagement=0.0,  # RSS gives no engagement; presence is the signal
            lang="hi",
            extra={"competitor": source_name},
        )

    @staticmethod
    def _parse_published(entry: Any) -> datetime:
        for attr in ("published_parsed", "updated_parsed"):
            tm = getattr(entry, attr, None)
            if tm:
                return datetime.fromtimestamp(mktime(tm), tz=timezone.utc)
        return datetime.now(timezone.utc)
