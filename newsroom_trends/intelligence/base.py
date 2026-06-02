"""Agent contract + shared analysis context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class IntelligenceContext:
    """Mutable analysis state shared across agents.

    `clusters` are the report's cluster dicts (annotated in place with `_`-prefixed keys
    by the agents). `topics` and `summary` are populated by the topic + engine steps.
    """

    clusters: list[dict[str, Any]]
    competitor_universe: list[str]
    source_breakdown: dict[str, int]
    topics: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


class IntelligenceAgent(ABC):
    """A single-responsibility analyzer. Agents are composed by the engine."""

    name: str = "agent"

    @abstractmethod
    def run(self, ctx: IntelligenceContext) -> None:
        """Read + annotate the context in place. Must not raise on missing fields."""
        raise NotImplementedError
