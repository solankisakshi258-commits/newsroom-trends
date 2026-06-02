from newsroom_trends.clustering import cluster_signals
from newsroom_trends.models import SourceType
from newsroom_trends.normalize import normalize_all
from newsroom_trends.scoring import normalize_engagement, score_clusters

from .factories import raw

SCORING_CFG = {
    "weights": {"velocity": 0.4, "source_breadth": 0.25, "engagement": 0.2, "freshness": 0.15},
    "competitor_penalty": 0.3,
    "freshness_half_life_hours": 6,
}


def test_engagement_normalized_within_source_type():
    signals = normalize_all([
        raw("a", source_type=SourceType.YOUTUBE, engagement=10),
        raw("b", source_type=SourceType.YOUTUBE, engagement=1000),
    ])
    normalize_engagement(signals)
    norms = sorted(s.engagement_norm for s in signals)
    assert norms[0] < norms[1]
    assert 0.0 <= norms[0] <= norms[1] <= 1.0


def test_cross_platform_story_beats_single_source():
    cross = normalize_all([
        raw("चुनाव परिणाम घोषित आज", source_type=SourceType.RSS, age_hours=0.5),
        raw("चुनाव परिणाम आज घोषित हुए", source_type=SourceType.YOUTUBE, engagement=5000, age_hours=0.5),
        raw("चुनाव परिणाम पर चर्चा", source_type=SourceType.TWITTER, engagement=800, age_hours=0.5),
    ])
    single = normalize_all([
        raw("स्थानीय नगर निगम की बैठक", source_type=SourceType.RSS, age_hours=20),
    ])
    clusters = cluster_signals(cross + single, similarity_threshold=0.15)
    scored = score_clusters(clusters, SCORING_CFG, window_hours=24)
    top = scored[0]
    assert top.source_breadth >= 0.4  # at least 3 of 5 source types
    assert top.opportunity == max(c.opportunity for c in scored)


def test_competitor_saturation_penalizes_opportunity():
    # Same story, but one cluster is heavily competitor-covered.
    saturated = normalize_all([
        raw("बड़ी खबर एक", source_type=SourceType.RSS, source_name="A", age_hours=0.2),
        raw("बड़ी खबर एक दोबारा", source_type=SourceType.RSS, source_name="B", age_hours=0.2),
        raw("बड़ी खबर एक फिर", source_type=SourceType.RSS, source_name="C", age_hours=0.2),
    ])
    fresh = normalize_all([
        raw("अलग ताज़ा खबर", source_type=SourceType.GOOGLE_TRENDS, engagement=90, age_hours=0.2),
    ])
    clusters = cluster_signals(saturated + fresh, similarity_threshold=0.15)
    scored = score_clusters(clusters, SCORING_CFG, window_hours=24)
    sat = next(c for c in scored if c.competitor_count == 3)
    assert sat.competitor_saturation == 1.0
    assert any("Saturated" in a or "differentiate" in a.lower() for a in sat.angles)
