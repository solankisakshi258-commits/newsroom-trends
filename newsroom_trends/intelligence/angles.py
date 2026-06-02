"""Story Angles agent.

Starts from the pipeline's editorial angles and augments them with intelligence-derived
hints from the competitor, Discover, and forecast agents. Runs LAST so those annotations
are available.
"""

from __future__ import annotations

from .base import IntelligenceAgent, IntelligenceContext


class StoryAnglesAgent(IntelligenceAgent):
    name = "angles"

    def run(self, ctx: IntelligenceContext) -> None:
        for c in ctx.clusters:
            angles = list(c.get("angles", []))
            comp = c.get("_competitor", {})
            disc = c.get("_discover", {})
            fc = c.get("_forecast", {})

            if comp.get("first_mover"):
                angles.append("No competitor has this yet — first-mover window, publish fast.")
            elif comp.get("missing"):
                angles.append(
                    f"{len(comp['missing'])} competitor(s) haven't covered it — gap remains."
                )
            if disc.get("tier") == "High":
                angles.append("Strong Google Discover candidate — optimize headline + lead image.")
            if fc.get("direction") == "up":
                angles.append("Momentum rising — publish now to ride the curve.")
            elif fc.get("direction") == "down":
                angles.append("Cooling off — only worth a quick explainer or recap.")

            seen: set[str] = set()
            deduped: list[str] = []
            for a in angles:
                if a not in seen:
                    seen.add(a)
                    deduped.append(a)
            c["_angles"] = deduped
