"""Topic Clustering agent.

A second level of grouping on top of story clusters: stories whose keyword/label token
sets overlap enough (Jaccard ≥ threshold) are grouped into a single "topic", so related
trends sit together. Reuses the pipeline tokenizer so Hindi and English both group.
"""

from __future__ import annotations

from collections import Counter

from ..clustering import tokenize
from .base import IntelligenceAgent, IntelligenceContext


class TopicClusteringAgent(IntelligenceAgent):
    name = "topics"
    THRESHOLD = 0.20

    def run(self, ctx: IntelligenceContext) -> None:
        token_sets = [
            set(tokenize(c.get("label", ""))) | {k.lower() for k in c.get("keywords", [])}
            for c in ctx.clusters
        ]

        groups: list[dict] = []  # {indices: [...], tokens: set}
        for i, ts in enumerate(token_sets):
            best_idx, best_sim = -1, self.THRESHOLD
            for gi, g in enumerate(groups):
                sim = self._jaccard(ts, g["tokens"])
                if sim >= best_sim:
                    best_idx, best_sim = gi, sim
            if best_idx == -1:
                groups.append({"indices": [i], "tokens": set(ts)})
            else:
                groups[best_idx]["indices"].append(i)
                groups[best_idx]["tokens"] |= ts

        topics: list[dict] = []
        for gi, g in enumerate(groups):
            members = g["indices"]
            cats = [ctx.clusters[m].get("category", "General") for m in members]
            dom_cat = Counter(cats).most_common(1)[0][0]
            rep = max(members, key=lambda m: ctx.clusters[m].get("opportunity", 0.0))
            kw_count: Counter = Counter()
            for m in members:
                kw_count.update(ctx.clusters[m].get("keywords", []))
            top_kw = [k for k, _ in kw_count.most_common(3)]
            name = top_kw[0].title() if top_kw else (ctx.clusters[rep].get("label", "Topic")[:46])
            best_opp = max(ctx.clusters[m].get("opportunity", 0.0) for m in members)
            topics.append(
                {
                    "id": f"topic-{gi}",
                    "name": name,
                    "category": dom_cat,
                    "indices": members,
                    "size": len(members),
                    "keywords": top_kw,
                    "best_opportunity": round(best_opp, 3),
                }
            )
            for m in members:
                ctx.clusters[m]["_topic"] = gi

        topics.sort(key=lambda t: -t["best_opportunity"])
        # Re-id after sort so the display order is stable and 0-based.
        for new_i, t in enumerate(topics):
            t["id"] = f"topic-{new_i}"
        ctx.topics = topics

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        if not a or not b:
            return 0.0
        return len(a & b) / len(a | b)
