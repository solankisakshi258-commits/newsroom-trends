"""Connector contract. Add a source = subclass Connector and register it."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

from ..config import Config
from ..models import RawSignal, SourceType

log = logging.getLogger("newsroom_trends.connectors")


class Connector(ABC):
    """A source of raw signals.

    Subclasses declare a `name` (matching the key in config.yaml `sources:`) and a
    `source_type`. `is_available()` lets a connector self-skip when its config or
    credentials are missing, so the pipeline degrades gracefully instead of failing.
    """

    name: str
    source_type: SourceType

    def __init__(self, config: Config):
        self.config = config
        self.settings = config.source(self.name)

    def is_available(self) -> bool:
        """Whether this connector can run. Default: enabled flag in config.
        Connectors needing credentials should override and also check those."""
        return self.config.source_enabled(self.name)

    @abstractmethod
    def fetch(self) -> list[RawSignal]:
        """Pull raw signals. Should catch its own network errors and return what it got,
        logging failures rather than raising — one bad source must not sink the run."""
        raise NotImplementedError
