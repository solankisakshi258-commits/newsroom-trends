"""Command-line entrypoint.

    python -m newsroom_trends.cli run [--only rss,google_trends] [--window 24]
    python -m newsroom_trends.cli report [--top 20]
    python -m newsroom_trends.cli sources
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import load_config
from .connectors import REGISTRY, build_connectors
from .pipeline import run_pipeline, save_report


def force_utf8_stdout() -> None:
    """Windows consoles default to cp1252, which can't encode Devanagari. Reconfigure
    stdout/stderr to UTF-8 (replacing anything truly unencodable) so reports print."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    report = run_pipeline(config, only=only, window_hours=args.window)
    path = save_report(report, config.reports_dir)
    if args.alert:
        from .notify import run_alerts

        alerted = run_alerts(config, report.clusters)
        print(f"Alerts: {len(alerted)} pushed/eligible.")
    _print_report(report, top=args.top)
    print(f"\nSaved report -> {path}")
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    from .scheduler import run_forever

    config = load_config(args.config)
    print("Scheduler running. Press Ctrl-C to stop.")
    try:
        run_forever(config)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    """Render the latest report to a static site folder (for GitHub Pages)."""
    import shutil

    from .web import render_html

    config = load_config(args.config)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    latest = config.reports_dir / "latest.json"
    data = json.loads(latest.read_text(encoding="utf-8")) if latest.exists() else None
    refresh = int(config.dashboard.get("refresh_seconds", 300))

    (out / "index.html").write_text(render_html(data, refresh), encoding="utf-8")
    if latest.exists():
        shutil.copyfile(latest, out / "latest.json")
    # Tell GitHub Pages not to run Jekyll over our files.
    (out / ".nojekyll").write_text("", encoding="utf-8")

    n = len(data.get("clusters", [])) if data else 0
    print(f"Exported static site -> {out}\\index.html  ({n} clusters)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .web import make_server

    config = load_config(args.config)
    dash = config.dashboard
    host = args.host or dash.get("host", "127.0.0.1")
    port = args.port or int(dash.get("port", 8787))
    refresh = int(dash.get("refresh_seconds", 30))
    server = make_server(config.reports_dir, host, port, refresh)
    print(f"Dashboard: http://{host}:{port}  (reading {config.reports_dir / 'latest.json'})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    """Run the dashboard (background thread) AND the scheduler loop (foreground)."""
    import threading

    from .scheduler import run_forever
    from .web import make_server

    config = load_config(args.config)
    dash = config.dashboard
    host = args.host or dash.get("host", "127.0.0.1")
    port = args.port or int(dash.get("port", 8787))
    refresh = int(dash.get("refresh_seconds", 30))

    server = make_server(config.reports_dir, host, port, refresh)
    threading.Thread(target=server.serve_forever, daemon=True, name="dashboard").start()
    print(f"Dashboard live: http://{host}:{port}")
    print("Scheduler running. Press Ctrl-C to stop.\n")
    try:
        run_forever(config)
    except KeyboardInterrupt:
        print("\nStopping…")
    finally:
        server.shutdown()
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    latest = config.reports_dir / "latest.json"
    if not latest.exists():
        print("No report yet. Run:  python -m newsroom_trends.cli run --only rss")
        return 1
    data = json.loads(latest.read_text(encoding="utf-8"))
    _print_report_dict(data, top=args.top)
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    print("Configured sources (✓ = available now):\n")
    for name, cls in REGISTRY.items():
        conn = cls(config)
        mark = "✓" if conn.is_available() else "·"
        enabled = "enabled" if config.source_enabled(name) else "disabled"
        print(f"  {mark} {name:<16} [{cls.source_type.value}]  ({enabled})")
    available = build_connectors(config)
    print(f"\n{len(available)} connector(s) will run.")
    return 0


# --- rendering ---------------------------------------------------------------------

def _print_report(report, top: int) -> None:
    _print_report_dict(report.to_dict(), top=top)


def _print_report_dict(data: dict, top: int) -> None:
    print("=" * 72)
    print(f"TREND REPORT  ·  {data['generated_at']}  ·  window {data['window_hours']}h")
    print(f"signals: {data['signal_count']}   breakdown: {data['source_breakdown']}")
    print("=" * 72)
    clusters = data.get("clusters", [])[:top]
    if not clusters:
        print("(no clusters)")
        return
    for i, c in enumerate(clusters, 1):
        opp = c["opportunity"]
        bar = "█" * int(round(opp * 20))
        print(f"\n{i:>2}. [{opp:.3f}] {bar}")
        print(f"    {c['label'][:90]}")
        print(
            f"    velocity={c['velocity']:.2f}  breadth={c['source_breadth']:.2f}  "
            f"engage={c['engagement']:.2f}  fresh={c['freshness']:.2f}  "
            f"compSat={c['competitor_saturation']:.2f}  signals={len(c['signals'])}"
        )
        if c.get("keywords"):
            print(f"    keywords: {', '.join(c['keywords'])}")
        srcs = sorted({s["source_type"] for s in c["signals"]})
        print(f"    sources:  {', '.join(srcs)}")
        for angle in c.get("angles", []):
            print(f"    → {angle}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="newsroom-trends", description=__doc__)
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("-v", "--verbose", action="store_true", help="info-level logs")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the full pipeline and print + save a report")
    r.add_argument("--only", default=None, help="comma-separated source names (e.g. rss)")
    r.add_argument("--window", type=int, default=24, help="lookback window in hours")
    r.add_argument("--top", type=int, default=15, help="how many clusters to print")
    r.add_argument("--alert", action="store_true", help="also push alerts for this run")
    r.set_defaults(func=cmd_run)

    sch = sub.add_parser("schedule", help="run the pipeline forever on the configured interval")
    sch.set_defaults(func=cmd_schedule)

    exp = sub.add_parser("export", help="render latest report to a static site (GitHub Pages)")
    exp.add_argument("--out", default="docs", help="output folder (default: docs)")
    exp.set_defaults(func=cmd_export)

    srv = sub.add_parser("serve", help="serve the live web dashboard")
    srv.add_argument("--host", default=None, help="override dashboard host")
    srv.add_argument("--port", type=int, default=None, help="override dashboard port")
    srv.set_defaults(func=cmd_serve)

    lv = sub.add_parser("live", help="run scheduler + dashboard together (for deploy)")
    lv.add_argument("--host", default=None, help="override dashboard host")
    lv.add_argument("--port", type=int, default=None, help="override dashboard port")
    lv.set_defaults(func=cmd_live)

    rep = sub.add_parser("report", help="print the latest saved report")
    rep.add_argument("--top", type=int, default=20)
    rep.set_defaults(func=cmd_report)

    s = sub.add_parser("sources", help="list configured sources and availability")
    s.set_defaults(func=cmd_sources)
    return p


def main(argv: list[str] | None = None) -> int:
    force_utf8_stdout()
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
