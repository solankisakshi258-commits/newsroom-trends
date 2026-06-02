from newsroom_trends.clustering import cluster_signals, tokenize
from newsroom_trends.models import SourceType
from newsroom_trends.normalize import normalize_all

from .factories import raw


def test_tokenize_drops_stopwords():
    toks = tokenize("भारत और पाकिस्तान का मैच")
    assert "और" not in toks and "का" not in toks
    assert "भारत" in toks and "पाकिस्तान" in toks


def test_similar_titles_cluster_together():
    signals = normalize_all([
        raw("भारत ने क्रिकेट मैच जीता बड़े अंतर से"),
        raw("क्रिकेट मैच में भारत की शानदार जीत"),
        raw("मौसम विभाग ने दिल्ली में बारिश की चेतावनी दी"),
    ])
    clusters = cluster_signals(signals, similarity_threshold=0.15)
    # The two cricket items should merge; weather stands alone -> 2 clusters.
    sizes = sorted(len(c.signals) for c in clusters)
    assert sizes == [1, 2]


def test_unrelated_titles_stay_separate():
    signals = normalize_all([
        raw("शेयर बाजार में तेजी"),
        raw("बॉलीवुड फिल्म की कमाई"),
    ])
    clusters = cluster_signals(signals, similarity_threshold=0.3)
    assert len(clusters) == 2


def test_empty_input():
    assert cluster_signals([]) == []
