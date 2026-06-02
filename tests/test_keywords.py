from newsroom_trends.clustering import cluster_signals
from newsroom_trends.normalize import normalize_all

from .factories import raw


def test_keywords_are_english_only():
    # Mixed Hindi + English headline; keyword chips must be English/Latin only.
    signals = normalize_all([
        raw("भारत में Cricket World Cup फाइनल जीत"),
        raw("Cricket World Cup फाइनल में भारत की जीत"),
    ])
    clusters = cluster_signals(signals, similarity_threshold=0.1)
    kws = clusters[0].keywords
    assert kws, "expected some English keywords"
    assert all(k.isascii() for k in kws), f"non-English keyword leaked: {kws}"
    assert "cricket" in kws or "world" in kws


def test_clustering_still_groups_hindi_without_english():
    # Pure-Hindi headlines (no English tokens) must still cluster together,
    # even though their keyword list ends up empty.
    signals = normalize_all([
        raw("मौसम विभाग ने भारी बारिश की चेतावनी दी"),
        raw("भारी बारिश की चेतावनी मौसम विभाग ने जारी की"),
    ])
    clusters = cluster_signals(signals, similarity_threshold=0.12)
    assert len(clusters) == 1
    assert clusters[0].keywords == []  # no English tokens -> empty chips, by design
