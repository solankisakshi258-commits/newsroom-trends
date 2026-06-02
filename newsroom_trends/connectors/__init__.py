"""Connector registry. To add a source: implement a Connector subclass and add it here."""

from __future__ import annotations

from ..config import Config
from .base import Connector
from .google_trends import GoogleTrendsConnector
from .reddit import RedditConnector
from .rss import RSSConnector
from .twitter import TwitterConnector
from .youtube import YouTubeConnector

# name -> class. The `name` here matches the key in config.yaml `sources:`.
REGISTRY: dict[str, type[Connector]] = {
    RSSConnector.name: RSSConnector,
    GoogleTrendsConnector.name: GoogleTrendsConnector,
    YouTubeConnector.name: YouTubeConnector,
    RedditConnector.name: RedditConnector,
    TwitterConnector.name: TwitterConnector,
}


def build_connectors(config: Config, only: list[str] | None = None) -> list[Connector]:
    """Instantiate connectors that are available. `only` restricts to named sources."""
    names = only if only else list(REGISTRY.keys())
    built: list[Connector] = []
    for name in names:
        cls = REGISTRY.get(name)
        if cls is None:
            raise ValueError(f"unknown source: {name!r}. Known: {list(REGISTRY)}")
        conn = cls(config)
        if conn.is_available():
            built.append(conn)
    return built


__all__ = ["Connector", "REGISTRY", "build_connectors"]
