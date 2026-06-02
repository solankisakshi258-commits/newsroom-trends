"""Pipeline orchestration: ingest -> normalize -> store -> cluster -> score -> report."""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .categorize import categorize_clusters
from .clustering import cluster_signals
from .config import Config
from .connectors import build_connectors
from .history import record_and_attach
from .models import RawSignal, Signal, TrendReport
from .normalize import has_disallowed_script, normalize_all
from .scoring import score_clusters
from .storage import SignalRepository

log = logging.getLogger("newsroom_trends.pipeline")


def run_pipeline(
    config: Config,
    only: list[str] | None = None,
    window_hours: int = 24,
) -> TrendReport:
    """Execute one full pipeline pass and return a ranked TrendReport.

    `only` restricts to named sources (e.g. ["rss"]). `window_hours` is the lookback
    used both for the clustering input set and for velocity/freshness scoring.
    """
    # 1. Ingest -------------------------------------------------------------------
    connectors = build_connectors(config, only=only)
    if not connectors:
        log.warning("No available connectors (check config + .env credentials).")
    raws: list[RawSignal] = []
    for conn in connectors:
        try:
            pulled = conn.fetch()
            log.info("%s -> %d raw signals", conn.name, len(pulled))
            raws.extend(pulled)
        except Exception as exc:  # defensive: a connector bug must not kill the run
            log.exception("connector %s crashed: %s", conn.name, exc)

    # 2. Normalize + dedup (drop non English/Hindi topics if configured) ----------
    restrict = bool(config.raw.get("filtering", {}).get("english_hindi_only", True))
    signals = normalize_all(raws, restrict_languages=restrict)
    log.info("Normalized to %d unique signals (english_hindi_only=%s)", len(signals), restrict)

    # 3. Store (dedup persists across runs, enabling cross-run history) ------------
    repo = SignalRepository.open(config.db_path)
    try:
        inserted = repo.upsert_many(signals)
        log.info("Stored %d new signals (db: %s)", inserted, config.db_path)
        # Use the full recent window from storage so prior runs contribute to clustering.
        windowed = repo.recent(window_hours)
    finally:
        repo.close()

    if not windowed:
        windowed = signals  # first run / empty db fallback

    # The stored window can contain signals from older runs (e.g. before a filter was
    # added), so re-apply the language restriction here too.
    if restrict:
        windowed = [s for s in windowed if not has_disallowed_script(s.title)]

    # 4. Cluster ------------------------------------------------------------------
    cl_cfg = config.clustering
    clusters = cluster_signals(
        windowed,
        similarity_threshold=float(cl_cfg.get("similarity_threshold", 0.22)),
        min_cluster_size=int(cl_cfg.get("min_cluster_size", 1)),
    )
    log.info("Formed %d story clusters", len(clusters))

    # 5. Score + categorise -------------------------------------------------------
    clusters = score_clusters(clusters, config.scoring, window_hours=window_hours)
    categorize_clusters(clusters)

    # 5b. Record interest-over-time history + attach the series to each cluster.
    try:
        record_and_attach(config, clusters)
    except Exception as exc:  # history is best-effort; never fail the run over it
        log.warning("history recording failed: %s", exc)

    # 6. Assemble report ----------------------------------------------------------
    breakdown = Counter(s.source_type.value for s in windowed)
    report = TrendReport(
        generated_at=datetime.now(timezone.utc),
        window_hours=window_hours,
        signal_count=len(windowed),
        source_breakdown=dict(breakdown),
        clusters=clusters,
    )
    return report


def save_report(report: TrendReport, reports_dir: Path) -> Path:
    """Persist the report as timestamped JSON; also update `latest.json`. Returns path."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    path = reports_dir / f"trends-{stamp}.json"
    payload = report.to_dict()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (reports_dir / "latest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path
