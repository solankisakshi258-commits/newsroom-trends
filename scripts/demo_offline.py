"""Offline end-to-end demo — exercises the whole pipeline with synthetic Hindi signals,
no network and no API keys. Useful as a smoke test and a feel for the report output.

    python scripts/demo_offline.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from newsroom_trends.clustering import cluster_signals  # noqa: E402
from newsroom_trends.models import RawSignal, SourceType, TrendReport  # noqa: E402
from newsroom_trends.normalize import normalize_all  # noqa: E402
from newsroom_trends.scoring import score_clusters  # noqa: E402
from newsroom_trends.cli import _print_report, force_utf8_stdout  # noqa: E402
from collections import Counter  # noqa: E402

force_utf8_stdout()


def _r(title, st, name, eng=0.0, age=1.0, summary=""):
    return RawSignal(
        source_type=st,
        source_name=name,
        title=title,
        url=f"https://example.com/{abs(hash(title)) % 100000}",
        summary=summary,
        published_at=datetime.now(timezone.utc) - timedelta(hours=age),
        engagement=eng,
        lang="hi",
    )


# A few overlapping "stories" spread across sources, plus noise.
RAWS = [
    # Story 1: cross-platform breakout, fresh, low competitor coverage
    _r("भारत ने क्रिकेट विश्व कप का फाइनल जीता", SourceType.GOOGLE_TRENDS, "Google Trends IN", 95, 0.3),
    _r("क्रिकेट विश्व कप फाइनल में भारत की ऐतिहासिक जीत", SourceType.YOUTUBE, "YouTube IN", 1_200_000, 0.4),
    _r("विश्व कप फाइनल भारत जीत पर सोशल मीडिया पर जश्न", SourceType.TWITTER, "Twitter/X", 45_000, 0.2),
    _r("भारत बना विश्व कप चैंपियन फाइनल में शानदार जीत", SourceType.RSS, "Aaj Tak", 0, 0.5),
    # Story 2: heavily covered by competitors (saturated), older
    _r("बजट 2026 में टैक्स स्लैब में बदलाव की घोषणा", SourceType.RSS, "Patrika", 0, 8),
    _r("बजट 2026 टैक्स स्लैब बदलाव बड़ी राहत", SourceType.RSS, "Jagran", 0, 8.5),
    _r("बजट 2026 में टैक्स स्लैब को लेकर बड़ा ऐलान", SourceType.RSS, "ABP Live", 0, 9),
    _r("बजट 2026 टैक्स स्लैब में संशोधन की पूरी जानकारी", SourceType.RSS, "Amar Ujala", 0, 9.5),
    # Story 3: emerging search interest, no competitor coverage yet (first-mover)
    _r("नई इलेक्ट्रिक कार लॉन्च कीमत और फीचर्स", SourceType.GOOGLE_TRENDS, "Google Trends IN", 70, 0.6),
    _r("इलेक्ट्रिक कार लॉन्च कीमत फीचर्स रिव्यू", SourceType.REDDIT, "r/india", 900, 0.7),
    # Noise: single, old, low-interest items
    _r("स्थानीय नगर निगम की मासिक बैठक संपन्न", SourceType.RSS, "NDTV Hindi", 0, 20),
    _r("मौसम विभाग ने हल्की बारिश की संभावना जताई", SourceType.RSS, "TV9 Hindi", 0, 15),
]


def main() -> int:
    signals = normalize_all(RAWS)
    clusters = cluster_signals(signals, similarity_threshold=0.18, min_cluster_size=1)
    scoring_cfg = {
        "weights": {"velocity": 0.40, "source_breadth": 0.25, "engagement": 0.20, "freshness": 0.15},
        "competitor_penalty": 0.30,
        "freshness_half_life_hours": 6,
    }
    clusters = score_clusters(clusters, scoring_cfg, window_hours=24)

    report = TrendReport(
        generated_at=datetime.now(timezone.utc),
        window_hours=24,
        signal_count=len(signals),
        source_breakdown=dict(Counter(s.source_type.value for s in signals)),
        clusters=clusters,
    )
    _print_report(report, top=10)
    print("\n[offline demo OK]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
