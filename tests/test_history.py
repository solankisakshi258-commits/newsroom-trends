from datetime import datetime, timedelta, timezone
from pathlib import Path

from newsroom_trends.config import Config
from newsroom_trends.history import history_path, record_and_attach
from newsroom_trends.models import StoryCluster


def _cfg(tmp_path: Path, **hist) -> Config:
    base = {"file": "history.json", "max_points": 3, "prune_hours": 72}
    base.update(hist)
    return Config(raw={"history": base}, project_root=tmp_path)


def _cluster(label, opp) -> StoryCluster:
    c = StoryCluster(id="x", label=label, keywords=[], signals=[])
    c.opportunity = opp
    return c


def test_appends_and_attaches_points(tmp_path):
    cfg = _cfg(tmp_path)
    now = datetime.now(timezone.utc)
    c = _cluster("story one", 0.4)
    record_and_attach(cfg, [c], now=now)
    record_and_attach(cfg, [_cluster("story one", 0.6)], now=now + timedelta(minutes=30))
    c2 = _cluster("story one", 0.8)
    record_and_attach(cfg, [c2], now=now + timedelta(minutes=60))
    # 3 runs -> 3 points, attached to the cluster, in order.
    assert [round(p["opportunity"], 1) for p in c2.history] == [0.4, 0.6, 0.8]


def test_max_points_trims_oldest(tmp_path):
    cfg = _cfg(tmp_path, max_points=2)
    now = datetime.now(timezone.utc)
    for i, opp in enumerate([0.1, 0.2, 0.3]):
        record_and_attach(cfg, [_cluster("s", opp)], now=now + timedelta(minutes=30 * i))
    final = _cluster("s", 0.4)
    record_and_attach(cfg, [final], now=now + timedelta(minutes=120))
    assert len(final.history) == 2
    assert round(final.history[-1]["opportunity"], 1) == 0.4


def test_prunes_stale_stories(tmp_path):
    cfg = _cfg(tmp_path, prune_hours=12)
    now = datetime.now(timezone.utc)
    record_and_attach(cfg, [_cluster("old", 0.5)], now=now - timedelta(hours=20))
    # A later run that doesn't include "old" should prune it.
    record_and_attach(cfg, [_cluster("new", 0.5)], now=now)
    import json

    data = json.loads(history_path(cfg).read_text(encoding="utf-8"))
    labels = {v["label"] for v in data.values()}
    assert "new" in labels and "old" not in labels
