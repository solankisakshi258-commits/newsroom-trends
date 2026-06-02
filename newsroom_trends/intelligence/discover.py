"""Google Discover Potential agent.

Discover rewards content that is fresh, timely, high-interest, and visual/social. We blend
the story's freshness, velocity, engagement, and the presence of search-intent (Google
Trends), social buzz (X), and video (YouTube) signals into a 0–100 Discover score + tier.
"""

from __future__ import annotations

from .base import IntelligenceAgent, IntelligenceContext


class DiscoverPotentialAgent(IntelligenceAgent):
    name = "discover"

    def run(self, ctx: IntelligenceContext) -> None:
        for c in ctx.clusters:
            c["_discover"] = self._score(c)

    @staticmethod
    def _score(c: dict) -> dict:
        fresh = float(c.get("freshness", 0.0))
        vel = float(c.get("velocity", 0.0))
        eng = float(c.get("engagement", 0.0))
        breadth = float(c.get("source_breadth", 0.0))
        srcs = {s.get("source_type") for s in c.get("signals", [])}
        search_intent = 1.0 if "google_trends" in srcs else 0.0
        social = 1.0 if "twitter" in srcs else 0.0
        video = 1.0 if "youtube" in srcs else 0.0

        raw = (
            0.30 * fresh
            + 0.25 * vel
            + 0.18 * eng
            + 0.12 * search_intent
            + 0.10 * social
            + 0.05 * video
        )
        score = int(round(raw * 100))
        tier = "High" if score >= 60 else "Medium" if score >= 35 else "Low"

        reasons: list[str] = []
        if fresh > 0.6:
            reasons.append("Fresh")
        if vel > 0.6:
            reasons.append("Rising fast")
        if search_intent:
            reasons.append("High search intent")
        if social:
            reasons.append("Social buzz")
        if video:
            reasons.append("Video available")
        if breadth >= 0.4:
            reasons.append("Cross-platform")
        if not reasons:
            reasons.append("Limited signals")
        return {"score": score, "tier": tier, "reasons": reasons}
