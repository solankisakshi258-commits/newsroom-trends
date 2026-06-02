"""Forecasting agent.

Fits a least-squares trend line to a story's recent opportunity-over-time history and
projects the next value, classifying momentum as Rising / Steady / Cooling. With fewer
than two history points it reports "New" (not enough data yet).
"""

from __future__ import annotations

from .base import IntelligenceAgent, IntelligenceContext


class ForecastAgent(IntelligenceAgent):
    name = "forecast"
    LOOKBACK = 6          # consider at most the last N history points
    THRESHOLD = 0.02      # slope magnitude that counts as a real move

    def run(self, ctx: IntelligenceContext) -> None:
        for c in ctx.clusters:
            pts = [float(p.get("opportunity", 0.0)) for p in c.get("history", [])]
            c["_forecast"] = self._forecast(pts[-self.LOOKBACK:])

    @classmethod
    def _forecast(cls, pts: list[float]) -> dict:
        if len(pts) < 2:
            return {
                "label": "New", "direction": "new", "slope": 0.0,
                "projected": round(pts[-1], 3) if pts else 0.0, "points": len(pts),
            }
        n = len(pts)
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(pts) / n
        denom = sum((x - mx) ** 2 for x in xs) or 1e-9
        slope = sum((xs[i] - mx) * (pts[i] - my) for i in range(n)) / denom
        projected = max(0.0, min(1.0, pts[-1] + slope))
        if slope > cls.THRESHOLD:
            direction, label = "up", "Rising"
        elif slope < -cls.THRESHOLD:
            direction, label = "down", "Cooling"
        else:
            direction, label = "flat", "Steady"
        return {
            "label": label, "direction": direction, "slope": round(slope, 4),
            "projected": round(projected, 3), "points": n,
        }
