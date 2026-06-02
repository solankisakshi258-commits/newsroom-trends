"""Zero-dependency live dashboard.

A stdlib HTTP server that reads `latest.json` on every request (so it always reflects
the most recent scheduler run) and renders an auto-refreshing HTML page. Also exposes
the raw report at /api/latest for any other consumer.

Layout is a column grid:  rank | trend | source | graph | score
  * trend  : title (links to Google Trends explore), related article link, realtime
             search volume, English keyword chips, and editorial angle hints
  * source : the source type(s), in their own column
  * graph  : an inline SVG mini bar-chart of the four score components per trend
  * score  : the blended opportunity score + bar

Routes:
    GET /            -> HTML dashboard (meta-refresh every `refresh_seconds`)
    GET /api/latest  -> the latest report JSON
    GET /healthz     -> "ok"
"""

from __future__ import annotations

import html
import json
import logging
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger("newsroom_trends.web")

# Fixed palette for the 4 score components (keeps the per-trend graphs comparable).
_METRICS = [
    ("Vel", "velocity", "#4f9dff"),
    ("Eng", "engagement", "#8b5cf6"),
    ("Frsh", "freshness", "#22c55e"),
    ("Brd", "source_breadth", "#f59e0b"),
]

# Per-category accent colors for the category pill.
_CATEGORY_COLORS = {
    "Politics": "#ff7a7a",
    "Cricket & Sports": "#4ade80",
    "Entertainment": "#e879f9",
    "Business & Economy": "#fbbf24",
    "Crime & Law": "#f87171",
    "Technology": "#60a5fa",
    "Auto": "#22d3ee",
    "Weather & Disaster": "#38bdf8",
    "Health": "#34d399",
    "Education": "#a78bfa",
    "World": "#fb923c",
    "Religion & Festival": "#f0abfc",
    "General": "#94a0b3",
}


def _category_color(cat: str) -> str:
    return _CATEGORY_COLORS.get(cat, "#94a0b3")


def _load_latest(reports_dir: Path) -> dict | None:
    latest = reports_dir / "latest.json"
    if not latest.exists():
        return None
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None


def _rel_time(iso: str | None, now: datetime) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    secs = (now - dt).total_seconds()
    if secs < 0:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    return f"{int(secs // 86400)}d ago"


def _rep_signal(cluster: dict) -> dict:
    """The representative signal = highest engagement (matches the cluster label)."""
    sigs = cluster.get("signals", [])
    if not sigs:
        return {}
    return max(sigs, key=lambda s: s.get("engagement", 0.0))


def _history_sparkline(cluster: dict) -> str:
    """Inline SVG line of opportunity-over-time across runs (interest-over-time).

    Opportunity is already 0..1, so the y-axis is fixed to that range and lines are
    comparable across trends. With <2 points there's nothing to draw yet."""
    pts = [float(p.get("opportunity", 0.0)) for p in cluster.get("history", [])]
    w, h, pad = 128, 30, 3
    if len(pts) < 2:
        return (
            f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}'>"
            f"<text x='{w/2:.0f}' y='{h/2+3:.0f}' font-size='9' fill='#5b6678' "
            f"text-anchor='middle'>● new — building history…</text></svg>"
        )
    n = len(pts)
    step = (w - 2 * pad) / (n - 1)
    span = h - 2 * pad
    coords = [(pad + i * step, (h - pad) - v * span) for i, v in enumerate(pts)]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
    area = f"{pad},{h-pad} " + poly + f" {coords[-1][0]:.1f},{h-pad}"
    lx, ly = coords[-1]
    rising = pts[-1] >= pts[0]
    color = "#22c55e" if rising else "#ef6b6b"
    return (
        f"<svg width='{w}' height='{h}' viewBox='0 0 {w} {h}' role='img' "
        f"aria-label='opportunity over time'>"
        f"<polygon points='{area}' fill='{color}22'/>"
        f"<polyline points='{poly}' fill='none' stroke='{color}' stroke-width='1.6' "
        f"stroke-linejoin='round'/>"
        f"<circle cx='{lx:.1f}' cy='{ly:.1f}' r='2.4' fill='{color}'/>"
        f"<title>opportunity over last {n} runs</title></svg>"
    )


def _metric_graph(cluster: dict) -> str:
    """Inline SVG vertical bar-chart of the 4 score components for one trend."""
    bars, labels = [], []
    n = len(_METRICS)
    col_w, gap, chart_h, base_y = 22, 8, 50, 54
    for i, (short, key, color) in enumerate(_METRICS):
        val = max(0.0, min(1.0, float(cluster.get(key, 0.0))))
        h = round(val * chart_h, 1)
        x = i * (col_w + gap) + 4
        y = base_y - h
        bars.append(
            f"<rect x='{x}' y='{y}' width='{col_w}' height='{h}' rx='3' fill='{color}'>"
            f"<title>{short} {val:.2f}</title></rect>"
        )
        labels.append(
            f"<text x='{x + col_w/2:.0f}' y='66' font-size='9' fill='#7f8aa0' "
            f"text-anchor='middle'>{short}</text>"
        )
    width = n * (col_w + gap)
    return (
        f"<svg width='{width}' height='70' viewBox='0 0 {width} 70' "
        f"role='img' aria-label='score components'>"
        f"<line x1='0' y1='54' x2='{width}' y2='54' stroke='#2a3140' stroke-width='1'/>"
        + "".join(bars) + "".join(labels) + "</svg>"
    )


def render_html(data: dict | None, refresh_seconds: int = 30) -> str:
    now = datetime.now(timezone.utc)
    if data is None:
        body = (
            "<div class='empty'>No report yet. The scheduler will populate this "
            "shortly, or run <code>python -m newsroom_trends.cli run</code>.</div>"
        )
        return _PAGE.format(refresh=refresh_seconds, meta="", rows=body, count=0,
                            updated="", cats="")

    sb = data.get("source_breakdown", {})
    sb_str = " · ".join(f"{k}:{v}" for k, v in sb.items())
    meta = (
        f"window {data.get('window_hours','?')}h &nbsp;•&nbsp; "
        f"{data.get('signal_count',0)} signals &nbsp;•&nbsp; {html.escape(sb_str)}"
    )
    updated = f"updated {_rel_time(data.get('generated_at'), now)}"
    all_clusters = data.get("clusters", [])
    # Category counts across the whole report, most common first.
    cat_counts: dict[str, int] = {}
    for c in all_clusters:
        cat = c.get("category", "General")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    cat_chips = "".join(
        f"<span class='catchip' style='--cat:{_category_color(k)}'>{html.escape(k)} {v}</span>"
        for k, v in sorted(cat_counts.items(), key=lambda kv: -kv[1])
    )
    clusters = all_clusters[:40]
    rows = "\n".join(_render_row(i, c, now) for i, c in enumerate(clusters, 1))
    rows = rows or "<div class='empty'>No clusters in latest report.</div>"
    return _PAGE.format(refresh=refresh_seconds, meta=meta, rows=rows,
                        count=len(clusters), updated=html.escape(updated), cats=cat_chips)


def _render_row(rank: int, c: dict, now: datetime) -> str:
    opp = float(c.get("opportunity", 0.0))
    pct = max(2, min(100, int(round(opp * 100))))
    hue = int(120 * opp)  # red -> green
    label = html.escape(c.get("label", ""))

    rep = _rep_signal(c)
    extra = rep.get("extra", {}) or {}
    explore_url = extra.get("explore_url") or rep.get("url")
    article_url = rep.get("url")
    traffic = extra.get("approx_traffic")
    when = _rel_time(rep.get("published_at"), now)

    # Title links to the trend (explore page if present, else the article).
    title_target = explore_url or article_url
    label_html = (
        f"<a href='{html.escape(title_target)}' target='_blank' rel='noopener'>{label}</a>"
        if title_target else label
    )

    # Realtime search-volume badge + freshness.
    badges = []
    if traffic:
        badges.append(f"<span class='vol'>🔍 {html.escape(str(traffic))} searches</span>")
    if when:
        badges.append(f"<span class='when'>🕒 {html.escape(when)}</span>")
    badges_html = f"<div class='badges'>{''.join(badges)}</div>" if badges else ""

    # Relevant article link (req 6).
    link_html = ""
    if article_url:
        src_name = html.escape(extra.get("news_items", [{}])[0].get("source", "")
                               if extra.get("news_items") else rep.get("source_name", ""))
        link_label = f"📰 {src_name}" if src_name else "📰 related article"
        link_html = (f"<a class='article' href='{html.escape(article_url)}' "
                     f"target='_blank' rel='noopener'>{link_label}</a>")

    kw = c.get("keywords", [])[:6]
    kw_html = ("<div class='kw'>"
               + "".join(f"<span class='chip'>{html.escape(k)}</span>" for k in kw)
               + "</div>") if kw else ""

    angles = c.get("angles", [])
    angles_html = ("<ul class='angles'>"
                   + "".join(f"<li>{html.escape(a)}</li>" for a in angles)
                   + "</ul>") if angles else ""

    # Source column.
    srcs = sorted({s.get("source_type", "") for s in c.get("signals", [])})
    src_html = "".join(f"<span class='tag tag-{html.escape(s)}'>{html.escape(s)}</span>"
                       for s in srcs)
    sat = float(c.get("competitor_saturation", 0.0))
    if sat > 0:
        src_html += f"<div class='sat' title='competitor saturation'>comp {sat:.0%}</div>"

    return f"""
    <div class="row">
      <div class="c-rank">{rank}</div>
      <div class="c-trend">
        <div class="cat" style="--cat:{_category_color(c.get('category','General'))}">{html.escape(c.get('category','General'))}</div>
        <div class="label">{label_html}</div>
        {badges_html}
        <div class="links">{link_html}</div>
        {kw_html}
        {angles_html}
      </div>
      <div class="c-source">{src_html}</div>
      <div class="c-graph">
        <div class="spark">{_history_sparkline(c)}</div>
        <div class="bars">{_metric_graph(c)}</div>
      </div>
      <div class="c-score">
        <div class="opp">{opp:.3f}</div>
        <div class="scorebar"><div class="fill" style="width:{pct}%;background:hsl({hue},72%,48%)"></div></div>
      </div>
    </div>"""


_PAGE = """<!doctype html>
<html lang="hi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh}">
<title>Newsroom Trends</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, "Segoe UI", Roboto, sans-serif; margin:0;
          background:#0b0d12; color:#e8eaed; }}
  header {{ padding:20px 28px; background:linear-gradient(135deg,#161b27,#0f1320);
            border-bottom:1px solid #232a38; position:sticky; top:0; z-index:5; }}
  header .top {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap; }}
  header h1 {{ margin:0; font-size:22px; letter-spacing:.2px; }}
  header .pill {{ font-size:11px; background:#1f6feb22; color:#7fb0ff; border:1px solid #1f6feb55;
                  padding:3px 10px; border-radius:999px; }}
  header .navlink {{ font-size:12px; text-decoration:none; color:#c4b5fd; border:1px solid #7c3aed55;
                     background:#7c3aed1a; padding:4px 11px; border-radius:8px; }}
  header .navlink:hover {{ background:#7c3aed33; }}
  header .meta {{ color:#94a0b3; font-size:12.5px; margin-top:8px; }}
  header .updated {{ color:#5b6678; font-size:11.5px; margin-top:2px; }}
  .legend {{ color:#6b7588; font-size:11px; margin-top:10px; display:flex; gap:14px; flex-wrap:wrap; }}
  .legend b {{ color:#9aa6ba; font-weight:600; }}
  .wrap {{ max-width:1060px; margin:0 auto; padding:10px 24px 70px; }}
  .head-row, .row {{ display:grid;
      grid-template-columns: 40px minmax(0,1fr) 120px 150px 96px; gap:14px; align-items:center; }}
  .head-row {{ padding:10px 16px 4px; color:#5b6678; font-size:11px; text-transform:uppercase;
               letter-spacing:.8px; }}
  .row {{ background:#12161f; border:1px solid #222a38; border-radius:12px;
          padding:14px 16px; margin:10px 0; transition:border-color .15s, transform .15s; }}
  .row:hover {{ border-color:#33405a; transform:translateY(-1px); }}
  .c-rank {{ font-size:20px; font-weight:700; color:#48526a; text-align:center; }}
  .c-trend {{ min-width:0; }}
  .cat {{ display:inline-block; font-size:10px; font-weight:700; letter-spacing:.4px;
          text-transform:uppercase; color:var(--cat); border:1px solid var(--cat);
          background:color-mix(in srgb, var(--cat) 14%, transparent);
          padding:1px 8px; border-radius:5px; margin-bottom:5px; }}
  .cats {{ margin-top:10px; display:flex; gap:6px; flex-wrap:wrap; }}
  .catchip {{ font-size:11px; color:var(--cat); border:1px solid var(--cat);
              background:color-mix(in srgb, var(--cat) 12%, transparent);
              padding:2px 9px; border-radius:999px; }}
  .label {{ font-size:16px; font-weight:650; line-height:1.35; }}
  .label a {{ color:#eef1f6; text-decoration:none; }}
  .label a:hover {{ color:#9ec1ff; text-decoration:underline; }}
  .badges {{ margin:7px 0 4px; display:flex; gap:8px; flex-wrap:wrap; }}
  .vol {{ background:#15351f; color:#5fd58a; font-size:11px; padding:2px 9px; border-radius:6px;
          border:1px solid #1f5c33; font-variant-numeric:tabular-nums; }}
  .when {{ color:#7f8aa0; font-size:11px; padding:2px 0; }}
  .links {{ margin:2px 0; }}
  .article {{ color:#79a9ff; font-size:12px; text-decoration:none; }}
  .article:hover {{ text-decoration:underline; }}
  .kw {{ margin:8px 0 2px; display:flex; gap:6px; flex-wrap:wrap; }}
  .chip {{ background:#1b2230; color:#8da2c0; font-size:10.5px; padding:2px 8px; border-radius:5px; }}
  .angles {{ margin:8px 0 0; padding-left:18px; color:#c4cee0; font-size:12.5px; line-height:1.5; }}
  .c-source {{ display:flex; flex-direction:column; gap:6px; align-items:flex-start; }}
  .tag {{ font-size:10.5px; padding:3px 9px; border-radius:999px; white-space:nowrap;
          background:#222838; color:#9ec1ff; border:1px solid #2c3650; }}
  .tag-google_trends {{ background:#2a1e3a; color:#c79bff; border-color:#43306a; }}
  .tag-rss {{ background:#23291c; color:#bcd98a; border-color:#3c4a28; }}
  .tag-youtube {{ background:#3a1d1d; color:#ff9b9b; border-color:#5e2f2f; }}
  .tag-reddit {{ background:#3a2a1d; color:#ffba7a; border-color:#5e442f; }}
  .tag-twitter {{ background:#1d2f3a; color:#8fd1ff; border-color:#2f4d5e; }}
  .sat {{ font-size:10px; color:#e0863f; }}
  .c-graph svg {{ display:block; }}
  .c-graph .spark {{ background:#0e1119; border:1px solid #1d2433; border-radius:6px; padding:2px; margin-bottom:6px; }}
  .c-score {{ text-align:right; }}
  .opp {{ font-size:18px; font-weight:700; font-variant-numeric:tabular-nums; }}
  .scorebar {{ height:7px; background:#0b0d12; border:1px solid #222a38; border-radius:6px;
               overflow:hidden; margin-top:6px; }}
  .scorebar .fill {{ height:100%; }}
  .empty {{ color:#94a0b3; padding:50px; text-align:center; }}
  code {{ background:#1b2230; padding:2px 6px; border-radius:4px; }}
  @media (max-width:760px) {{
    .head-row {{ display:none; }}
    .row {{ grid-template-columns: 32px 1fr; }}
    .c-source, .c-graph, .c-score {{ grid-column:2; text-align:left; }}
    .c-score {{ text-align:left; }}
  }}
</style></head>
<body>
<header>
  <div class="top"><h1>📈 Newsroom Trends</h1>
    <span class="pill">LIVE · auto-refresh {refresh}s</span>
    <a class="navlink" href="newsroom-intelligence.html">🧠 AI Intelligence →</a></div>
  <div class="meta">{meta}</div>
  <div class="updated">{updated} · showing {count} stories</div>
  <div class="cats">{cats}</div>
  <div class="legend">
    <span><b>Line:</b> opportunity over time (green rising / red falling)</span>
    <span><b>Bars:</b> Vel · Eng · Frsh · Brd (each 0–1)</span>
    <span><b>Score:</b> blended opportunity</span>
  </div>
</header>
<div class="wrap">
  <div class="head-row"><div>#</div><div>Trend</div><div>Source</div><div>Graphs</div><div>Score</div></div>
  {rows}
</div>
</body></html>"""


def make_server(reports_dir: Path, host: str, port: int, refresh_seconds: int = 30):
    """Build (but do not start) a ThreadingHTTPServer serving the dashboard."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802
            if self.path in ("/", "/index.html"):
                data = _load_latest(reports_dir)
                self._send(200, render_html(data, refresh_seconds).encode("utf-8"),
                           "text/html; charset=utf-8")
            elif self.path.rstrip("/") in (
                "/newsroom-intelligence", "/newsroom-intelligence.html", "/intelligence"
            ):
                # Separate AI Intelligence dashboard (additive route; classic page untouched).
                from .intelligence import render_intelligence_html

                data = _load_latest(reports_dir)
                self._send(200, render_intelligence_html(data, refresh_seconds).encode("utf-8"),
                           "text/html; charset=utf-8")
            elif self.path.startswith("/api/latest"):
                data = _load_latest(reports_dir) or {}
                self._send(200, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            elif self.path.startswith("/healthz"):
                self._send(200, b"ok", "text/plain")
            else:
                self._send(404, b"not found", "text/plain")

    return ThreadingHTTPServer((host, port), Handler)
