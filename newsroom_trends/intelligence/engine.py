"""Intelligence engine — composes the agents over a trend report.

Pure read-layer: takes the report dict (from latest.json), runs each agent in order,
and returns an enriched structure (clusters annotated in place + topics + summary).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .angles import StoryAnglesAgent
from .base import IntelligenceAgent, IntelligenceContext
from .competitor import CompetitorAnalysisAgent
from .discover import DiscoverPotentialAgent
from .forecast import ForecastAgent
from .topics import TopicClusteringAgent

# Order matters: angles depends on competitor/discover/forecast annotations.
DEFAULT_AGENTS: list[IntelligenceAgent] = [
    CompetitorAnalysisAgent(),
    DiscoverPotentialAgent(),
    ForecastAgent(),
    TopicClusteringAgent(),
    StoryAnglesAgent(),
]


def analyze_report(
    data: dict[str, Any], agents: list[IntelligenceAgent] | None = None
) -> dict[str, Any]:
    """Run the agent pipeline over a report dict and return the enriched intelligence."""
    clusters = data.get("clusters", []) or []
    universe = sorted(
        {
            s.get("source_name")
            for c in clusters
            for s in c.get("signals", [])
            if s.get("source_type") == "rss" and s.get("source_name")
        }
    )
    ctx = IntelligenceContext(
        clusters=clusters,
        competitor_universe=universe,
        source_breakdown=data.get("source_breakdown", {}) or {},
    )
    for agent in (agents or DEFAULT_AGENTS):
        agent.run(ctx)

    n = len(clusters)
    cats = Counter(c.get("category", "General") for c in clusters)
    ctx.summary = {
        "stories": n,
        "topics": len(ctx.topics),
        "cross_platform": sum(
            1 for c in clusters if len({s.get("source_type") for s in c.get("signals", [])}) > 1
        ),
        "high_discover": sum(1 for c in clusters if c.get("_discover", {}).get("tier") == "High"),
        "rising": sum(1 for c in clusters if c.get("_forecast", {}).get("direction") == "up"),
        "top_category": cats.most_common(1)[0][0] if cats else "—",
        "avg_opportunity": round(sum(c.get("opportunity", 0.0) for c in clusters) / n, 3) if n else 0.0,
    }
    return {
        "data": data,
        "topics": ctx.topics,
        "summary": ctx.summary,
        "competitor_universe": universe,
    }
