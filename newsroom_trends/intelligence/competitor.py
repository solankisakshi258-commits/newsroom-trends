"""Competitor Analysis agent.

For each story, work out which competitor outlets already cover it (from the RSS signals)
and which don't — the coverage gap. A story no competitor has yet is a first-mover
opportunity; a fully-saturated one is a weaker bet.
"""

from __future__ import annotations

from .base import IntelligenceAgent, IntelligenceContext


class CompetitorAnalysisAgent(IntelligenceAgent):
    name = "competitor"

    def run(self, ctx: IntelligenceContext) -> None:
        universe = set(ctx.competitor_universe)
        n = len(universe) or 1
        for c in ctx.clusters:
            covered = sorted(
                {
                    s.get("source_name")
                    for s in c.get("signals", [])
                    if s.get("source_type") == "rss" and s.get("source_name")
                }
            )
            missing = sorted(universe - set(covered))
            c["_competitor"] = {
                "covered": covered,
                "missing": missing,
                "count": len(covered),
                "universe": len(universe),
                "saturation": round(len(covered) / n, 3),
                "first_mover": len(covered) == 0,
            }
