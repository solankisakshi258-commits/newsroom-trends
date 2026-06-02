"""Scheduler: run the pipeline on a fixed interval, save reports, fire alerts.

`run_once` is one full cycle (ingest -> report -> alert). `run_forever` loops it every
`interval_minutes`, catching per-cycle errors so a single bad run doesn't stop the loop.
The loop is the long-running foreground process for both local `schedule`/`live` and the
Docker container.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from .config import Config
from .models import TrendReport
from .notify import run_alerts
from .pipeline import run_pipeline, save_report

log = logging.getLogger("newsroom_trends.scheduler")


def run_once(
    config: Config,
    sources: list[str] | None = None,
    window_hours: int = 24,
    do_alerts: bool = True,
) -> TrendReport:
    """One full cycle: ingest -> normalize -> store -> cluster -> score -> save -> alert."""
    report = run_pipeline(config, only=sources, window_hours=window_hours)
    path = save_report(report, config.reports_dir)
    log.info("Report saved: %s (%d clusters)", path, len(report.clusters))
    if do_alerts:
        alerted = run_alerts(config, report.clusters)
        if alerted:
            log.info("Alerted %d stor%s.", len(alerted), "y" if len(alerted) == 1 else "ies")
    return report


def run_forever(
    config: Config,
    stop_event: threading.Event | None = None,
) -> None:
    """Loop `run_once` on the configured interval until interrupted/stopped."""
    sch = config.schedule
    interval_min = float(sch.get("interval_minutes", 30))
    sources = sch.get("sources") or None
    window_hours = int(sch.get("window_hours", 24))
    interval_s = max(60.0, interval_min * 60.0)
    stop = stop_event or threading.Event()

    log.info(
        "Scheduler started: every %.0f min, sources=%s, window=%dh",
        interval_min, sources or "all-available", window_hours,
    )
    while not stop.is_set():
        cycle_start = time.monotonic()
        started = datetime.now(timezone.utc)
        try:
            run_once(config, sources=sources, window_hours=window_hours, do_alerts=True)
        except Exception as exc:  # never let one cycle kill the loop
            log.exception("Scheduler cycle failed: %s", exc)

        elapsed = time.monotonic() - cycle_start
        sleep_for = max(1.0, interval_s - elapsed)
        log.info("Cycle done in %.1fs (started %s). Next run in %.0f min.",
                 elapsed, started.isoformat(timespec="seconds"), sleep_for / 60.0)
        # Interruptible sleep so Ctrl-C / stop_event responds promptly.
        if stop.wait(sleep_for):
            break
    log.info("Scheduler stopped.")
