"""Story clustering: group signals that are about the same story.

Pure-Python TF-IDF + cosine similarity with greedy agglomerative merging — no heavy
dependencies, so the pipeline runs anywhere. If scikit-learn is installed it is used
for the vectorization (faster, better tokenization), but results are equivalent in shape.

Greedy single-pass clustering is O(n²) in similarity comparisons, which is fine for the
hundreds-of-signals scale a newsroom run produces. Threshold comes from config
(`clustering.similarity_threshold`).
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

from .models import Signal, SourceType, StoryCluster

# Minimal Hindi + English stopword list — enough to stop function words dominating TF-IDF.
_STOPWORDS = {
    # Hindi
    "और", "का", "के", "की", "को", "में", "है", "हैं", "से", "पर", "ने", "कि", "यह",
    "वह", "एक", "हो", "था", "थे", "थी", "गया", "गई", "लिए", "कर", "भी", "तो", "जो",
    "कुछ", "इस", "उस", "अब", "क्या", "नहीं", "हुआ", "हुई", "साथ", "बाद", "रहा", "रही",
    # English
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was",
    "were", "with", "at", "by", "from", "as", "be", "this", "that", "it", "its", "new",
}

_TOKEN_RE = re.compile(r"[ऀ-ॿa-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    return [
        t for t in (_TOKEN_RE.findall(text.lower()))
        if len(t) > 1 and t not in _STOPWORDS
    ]


def _tfidf_vectors(docs: list[list[str]]) -> list[dict[str, float]]:
    """Compute L2-normalized TF-IDF vectors (as sparse dicts) for tokenized docs."""
    n = len(docs)
    df: Counter[str] = Counter()
    for tokens in docs:
        for term in set(tokens):
            df[term] += 1

    vectors: list[dict[str, float]] = []
    for tokens in docs:
        tf = Counter(tokens)
        vec: dict[str, float] = {}
        for term, count in tf.items():
            idf = math.log((1 + n) / (1 + df[term])) + 1.0
            vec[term] = count * idf
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vectors.append({t: w / norm for t, w in vec.items()})
    return vectors


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    # Both are L2-normalized, so cosine == dot product. Iterate the smaller dict.
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def cluster_signals(
    signals: list[Signal],
    similarity_threshold: float = 0.22,
    min_cluster_size: int = 1,
) -> list[StoryCluster]:
    """Group signals into stories. Returns clusters meeting `min_cluster_size`."""
    if not signals:
        return []

    docs = [tokenize(s.text) for s in signals]
    vectors = _tfidf_vectors(docs)

    # Greedy: each signal joins the existing cluster whose centroid it is most similar
    # to (above threshold); otherwise it seeds a new cluster.
    cluster_members: list[list[int]] = []
    cluster_centroids: list[dict[str, float]] = []

    for i, vec in enumerate(vectors):
        best_idx, best_sim = -1, similarity_threshold
        for ci, centroid in enumerate(cluster_centroids):
            sim = _cosine(vec, centroid)
            if sim >= best_sim:
                best_idx, best_sim = ci, sim
        if best_idx == -1:
            cluster_members.append([i])
            cluster_centroids.append(dict(vec))
        else:
            cluster_members[best_idx].append(i)
            _merge_centroid(cluster_centroids[best_idx], vec, len(cluster_members[best_idx]))

    clusters: list[StoryCluster] = []
    for ci, members in enumerate(cluster_members):
        if len(members) < min_cluster_size:
            continue
        member_signals = [signals[i] for i in members]
        clusters.append(_build_cluster(ci, member_signals, [docs[i] for i in members]))
    return clusters


def _merge_centroid(centroid: dict[str, float], vec: dict[str, float], size: int) -> None:
    """Running average of cluster member vectors (kept roughly normalized)."""
    for term, w in vec.items():
        centroid[term] = (centroid.get(term, 0.0) * (size - 1) + w) / size
    norm = math.sqrt(sum(w * w for w in centroid.values())) or 1.0
    for term in list(centroid.keys()):
        centroid[term] /= norm


def _build_cluster(
    idx: int, signals: list[Signal], docs: list[list[str]]
) -> StoryCluster:
    # Label = title of the highest-engagement signal (ties -> newest).
    rep = max(signals, key=lambda s: (s.engagement, s.published_at))
    keywords = _top_keywords(docs, k=6)
    cid = f"story-{idx:04d}-{rep.id[:8]}"
    return StoryCluster(
        id=cid,
        label=rep.title,
        keywords=keywords,
        signals=signals,
    )


_ENGLISH_RE = re.compile(r"^[a-z0-9]+$")


def _top_keywords(docs: list[list[str]], k: int) -> list[str]:
    """Most frequent terms across the cluster, ENGLISH/Latin only.

    Clustering itself uses Devanagari + Latin tokens (so Hindi stories group correctly),
    but the displayed keyword chips are restricted to English/Latin per product choice.
    """
    freq: Counter[str] = Counter()
    for tokens in docs:
        # set() so one doc doesn't dominate by repetition; English/Latin tokens only.
        freq.update({t for t in tokens if _ENGLISH_RE.match(t)})
    return [term for term, _ in freq.most_common(k)]
