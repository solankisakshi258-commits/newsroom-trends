from datetime import datetime, timezone

from newsroom_trends.web import render_html


def test_render_empty():
    out = render_html(None, refresh_seconds=30)
    assert "No report yet" in out
    assert 'content="30"' in out  # meta refresh wired


def _sample():
    now = datetime.now(timezone.utc).isoformat()
    return {
        "generated_at": now,
        "window_hours": 24,
        "signal_count": 2,
        "source_breakdown": {"google_trends": 1, "rss": 1},
        "clusters": [
            {
                "label": "शशि थरूर <script>",
                "opportunity": 0.635,
                "velocity": 0.7, "source_breadth": 0.2, "engagement": 1.0,
                "freshness": 0.4, "competitor_saturation": 0.5,
                "keywords": ["protest", "exam"],
                "angles": ["High search intent"],
                "signals": [{
                    "source_type": "google_trends",
                    "source_name": "Google Trends IN",
                    "url": "https://news.example/article",
                    "published_at": now,
                    "engagement": 50000.0,
                    "extra": {
                        "approx_traffic": "50,000+",
                        "explore_url": "https://trends.google.com/trends/explore?q=x",
                        "news_items": [{"title": "T", "url": "https://news.example/article",
                                        "source": "Example News"}],
                    },
                }],
            }
        ],
    }


def test_render_escapes_label():
    out = render_html(_sample())
    assert "शशि थरूर" in out
    assert "<script>" not in out  # escaped, not injected


def test_render_shows_score_and_graph():
    out = render_html(_sample())
    assert "0.635" in out
    assert "<svg" in out                 # per-trend graph present (req 5)
    assert "score components" in out


def test_render_source_column_and_realtime_volume():
    out = render_html(_sample())
    assert "c-source" in out             # source has its own column (req 2)
    assert "tag-google_trends" in out
    assert "50,000+" in out              # realtime search volume (req 4)


def test_render_shows_relevant_url():
    out = render_html(_sample())
    assert "https://news.example/article" in out   # relevant trend URL (req 6)
    assert "Example News" in out                   # related-source label
    assert "https://trends.google.com/trends/explore?q=x" in out  # title -> explore


def test_history_sparkline_new_when_insufficient():
    # No/one history point -> "building history" placeholder, no polyline.
    out = render_html(_sample())
    assert "building history" in out
    assert "<polyline" not in out


def test_history_sparkline_draws_line_with_history():
    data = _sample()
    data["clusters"][0]["history"] = [
        {"ts": "2026-06-02T09:00:00+00:00", "opportunity": 0.3},
        {"ts": "2026-06-02T09:30:00+00:00", "opportunity": 0.5},
        {"ts": "2026-06-02T10:00:00+00:00", "opportunity": 0.635},
    ]
    out = render_html(data)
    assert "<polyline" in out                     # interest-over-time line drawn
    assert "opportunity over time" in out
