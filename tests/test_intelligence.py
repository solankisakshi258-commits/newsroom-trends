from datetime import datetime, timezone

from newsroom_trends.intelligence import analyze_report
from newsroom_trends.web import render_intelligence_html


def _now():
    return datetime.now(timezone.utc).isoformat()


def _report():
    now = _now()
    return {
        "generated_at": now,
        "window_hours": 24,
        "signal_count": 6,
        "source_breakdown": {"google_trends": 2, "rss": 3, "twitter": 1},
        "clusters": [
            {
                "label": "भारत ने क्रिकेट विश्व कप जीता",
                "category": "Cricket & Sports",
                "opportunity": 0.70, "velocity": 0.8, "engagement": 0.6,
                "freshness": 0.9, "source_breadth": 0.4, "competitor_saturation": 0.5,
                "keywords": ["cricket", "world", "cup"],
                "angles": ["High search intent"],
                "history": [
                    {"ts": now, "opportunity": 0.5},
                    {"ts": now, "opportunity": 0.6},
                    {"ts": now, "opportunity": 0.7},
                ],
                "signals": [
                    {"source_type": "rss", "source_name": "ABP Live",
                     "url": "https://abp/a", "published_at": now, "engagement": 0, "extra": {}},
                    {"source_type": "google_trends", "source_name": "Google Trends IN",
                     "url": "https://t/x", "published_at": now, "engagement": 50000,
                     "extra": {"approx_traffic": "50K+", "explore_url": "https://t/explore"}},
                ],
            },
            {
                "label": "Cricket world cup final India win",
                "category": "Cricket & Sports",
                "opportunity": 0.60, "velocity": 0.7, "engagement": 0.5,
                "freshness": 0.8, "source_breadth": 0.2, "competitor_saturation": 0.0,
                "keywords": ["cricket", "world", "cup", "final"],
                "angles": [],
                "history": [{"ts": now, "opportunity": 0.6}],
                "signals": [
                    {"source_type": "google_trends", "source_name": "Google Trends IN",
                     "url": "https://t/y", "published_at": now, "engagement": 30000, "extra": {}},
                ],
            },
            {
                "label": "बजट 2026 टैक्स स्लैब",
                "category": "Business & Economy",
                "opportunity": 0.40, "velocity": 0.3, "engagement": 0.0,
                "freshness": 0.3, "source_breadth": 0.2, "competitor_saturation": 1.0,
                "keywords": ["budget", "tax"],
                "angles": [],
                "history": [{"ts": now, "opportunity": 0.45}, {"ts": now, "opportunity": 0.40}],
                "signals": [
                    {"source_type": "rss", "source_name": "ABP Live",
                     "url": "https://abp/b", "published_at": now, "engagement": 0, "extra": {}},
                    {"source_type": "rss", "source_name": "Jagran",
                     "url": "https://jag/b", "published_at": now, "engagement": 0, "extra": {}},
                ],
            },
        ],
    }


def test_competitor_analysis_gap_and_first_mover():
    intel = analyze_report(_report())
    cl = intel["data"]["clusters"]
    assert cl[0]["_competitor"]["covered"] == ["ABP Live"]
    assert cl[0]["_competitor"]["missing"] == ["Jagran"]
    assert cl[1]["_competitor"]["first_mover"] is True          # google_trends only
    assert cl[2]["_competitor"]["saturation"] == 1.0            # both outlets cover it


def test_discover_potential_scored():
    intel = analyze_report(_report())
    d0 = intel["data"]["clusters"][0]["_discover"]
    assert 0 <= d0["score"] <= 100
    assert d0["tier"] in {"High", "Medium", "Low"}
    assert "High search intent" in d0["reasons"]


def test_forecast_direction():
    intel = analyze_report(_report())
    cl = intel["data"]["clusters"]
    assert cl[0]["_forecast"]["direction"] == "up"     # 0.5->0.6->0.7 rising
    assert cl[2]["_forecast"]["direction"] == "down"   # 0.45->0.40 cooling
    assert cl[1]["_forecast"]["direction"] == "new"    # single point


def test_topic_clustering_groups_related():
    intel = analyze_report(_report())
    cl = intel["data"]["clusters"]
    # The two cricket stories share keywords -> same topic; budget is separate.
    assert cl[0]["_topic"] == cl[1]["_topic"]
    assert cl[2]["_topic"] != cl[0]["_topic"]
    assert intel["summary"]["topics"] >= 2


def test_angles_augmented_with_intelligence():
    intel = analyze_report(_report())
    cl = intel["data"]["clusters"]
    assert any("first-mover" in a.lower() for a in cl[1]["_angles"])  # first mover note


def test_summary_metrics():
    intel = analyze_report(_report())
    s = intel["summary"]
    assert s["stories"] == 3
    assert s["cross_platform"] == 1          # only cluster 0 has 2 source types
    assert s["top_category"] == "Cricket & Sports"


def test_render_intelligence_html_has_all_features():
    out = render_intelligence_html(_report())
    for needle in [
        "Newsroom AI Intelligence", "Traffic Opportunity", "Discover Potential",
        "Forecast", "Competitor analysis", "Story angles",
        "index.html",          # back-nav to classic dashboard
        "Cricket & Sports",
    ]:
        assert needle in out, f"missing: {needle}"


def test_render_intelligence_empty():
    assert "No report yet" in render_intelligence_html(None)
