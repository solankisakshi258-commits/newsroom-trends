from datetime import datetime, timedelta, timezone

from newsroom_trends.config import Config
from newsroom_trends.models import StoryCluster
from newsroom_trends.notify import AlertState, build_payload, select_alertable, _story_key


def _cfg(**alerts) -> Config:
    base = {"enabled": True, "min_opportunity": 0.5, "max_per_run": 5, "resuppress_hours": 12}
    base.update(alerts)
    return Config(raw={"alerts": base}, project_root=__import__("pathlib").Path("."))


def _cluster(label, opp) -> StoryCluster:
    c = StoryCluster(id="x", label=label, keywords=[], signals=[])
    c.opportunity = opp
    return c


def test_threshold_filters_low_opportunity(tmp_path):
    state = AlertState(tmp_path / "s.json")
    clusters = [_cluster("big", 0.8), _cluster("small", 0.2)]
    picked = select_alertable(clusters, _cfg(), state)
    assert [c.label for c in picked] == ["big"]


def test_max_per_run_caps(tmp_path):
    state = AlertState(tmp_path / "s.json")
    clusters = [_cluster(f"s{i}", 0.9) for i in range(10)]
    picked = select_alertable(clusters, _cfg(max_per_run=3), state)
    assert len(picked) == 3


def test_dedup_suppresses_recent(tmp_path):
    now = datetime.now(timezone.utc)
    state = AlertState(tmp_path / "s.json")
    state.mark(_story_key("repeat story"), now - timedelta(hours=1))
    clusters = [_cluster("repeat story", 0.9), _cluster("fresh story", 0.9)]
    picked = select_alertable(clusters, _cfg(resuppress_hours=12), state, now=now)
    assert [c.label for c in picked] == ["fresh story"]


def test_dedup_expires_after_window(tmp_path):
    now = datetime.now(timezone.utc)
    state = AlertState(tmp_path / "s.json")
    state.mark(_story_key("old alert"), now - timedelta(hours=20))
    picked = select_alertable([_cluster("old alert", 0.9)], _cfg(resuppress_hours=12),
                              state, now=now)
    assert len(picked) == 1


def test_state_round_trips(tmp_path):
    now = datetime.now(timezone.utc)
    p = tmp_path / "s.json"
    s1 = AlertState(p)
    s1.mark("abc", now)
    s1.save()
    s2 = AlertState(p)
    assert s2.is_suppressed("abc", 12, now)


def test_payload_has_text_and_alerts():
    now = datetime.now(timezone.utc)
    payload = build_payload([_cluster("बड़ी खबर", 0.7)], now)
    assert "बड़ी खबर" in payload["text"]
    assert payload["alerts"][0]["opportunity"] == 0.7
    assert "generated_at" in payload
