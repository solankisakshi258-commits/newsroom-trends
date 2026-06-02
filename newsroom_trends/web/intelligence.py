"""Newsroom AI Intelligence dashboard (separate page from the classic dashboard).

A read-only, agent-enriched view of the same `latest.json`. It reuses the classic
dashboard's helper renderers (sparkline, component bars, relative time, category colors)
and theme palette, and adds the advanced features: Traffic Opportunity Score, Discover
Potential, Forecasting, Competitor Analysis, Story Angles, grouped by Topic.

This module does NOT modify the classic dashboard; it only imports shared helpers.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone

from ..intelligence import analyze_report
from .dashboard import (
    _category_color,
    _history_sparkline,
    _load_latest,
    _metric_graph,
    _rel_time,
    _rep_signal,
)

# Render caps (topic grouping is computed over all stories; we display the top ones).
MAX_STORIES = 80
MAX_PER_TOPIC = 12

_DISCOVER_COLORS = {"High": "#22c55e", "Medium": "#fbbf24", "Low": "#7f8aa0"}
_FORECAST = {
    "up": ("▲", "#22c55e", "Rising"),
    "down": ("▼", "#ef6b6b", "Cooling"),
    "flat": ("▶", "#94a0b3", "Steady"),
    "new": ("◌", "#6b7588", "New"),
}


def render_intelligence_html(data: dict | None, refresh_seconds: int = 60) -> str:
    now = datetime.now(timezone.utc)
    if data is None or not data.get("clusters"):
        body = ("<div class='empty'>No report yet. The scheduler will populate this "
                "shortly, or run <code>python -m newsroom_trends.cli run</code>.</div>")
        return _PAGE.format(refresh=refresh_seconds, updated="", kpis="", topics=body)

    intel = analyze_report(data)
    clusters = intel["data"]["clusters"]
    summary = intel["summary"]

    # Show only the top stories (by opportunity) to keep the page light; topic grouping
    # is computed over everything, but we render the highest-value members.
    ranked = sorted(range(len(clusters)), key=lambda i: -clusters[i].get("opportunity", 0.0))
    show = set(ranked[:MAX_STORIES])
    shown_note = (f"showing top {min(MAX_STORIES, len(clusters))} of {len(clusters)} stories"
                  if len(clusters) > MAX_STORIES else f"{len(clusters)} stories")
    updated = f"updated {_rel_time(data.get('generated_at'), now)} · {shown_note}"

    kpis = "".join(
        f"<div class='kpi'><div class='kpi-v'>{v}</div><div class='kpi-l'>{html.escape(l)}</div></div>"
        for l, v in [
            ("Stories", summary["stories"]),
            ("Topic groups", summary["topics"]),
            ("Cross-platform", summary["cross_platform"]),
            ("High Discover", summary["high_discover"]),
            ("Rising now", summary["rising"]),
            ("Top category", summary["top_category"]),
            ("Avg opportunity", summary["avg_opportunity"]),
        ]
    )

    topics_html = "\n".join(
        _render_topic(t, clusters, now, show) for t in intel["topics"]
        if any(m in show for m in t["indices"])
    )
    return _PAGE.format(refresh=refresh_seconds, updated=html.escape(updated),
                        kpis=kpis, topics=topics_html)


def _render_topic(topic: dict, clusters: list[dict], now: datetime, show: set[int]) -> str:
    cat = topic["category"]
    color = _category_color(cat)
    members = [m for m in sorted(topic["indices"],
                                 key=lambda m: -clusters[m].get("opportunity", 0.0))
               if m in show][:MAX_PER_TOPIC]
    cards = "\n".join(_intel_card(clusters[m], now) for m in members)
    kw = " · ".join(html.escape(k) for k in topic.get("keywords", [])[:3])
    kw_html = f"<span class='topic-kw'>{kw}</span>" if kw else ""
    return f"""
    <section class="topic">
      <div class="topic-head">
        <span class="cat" style="--cat:{color}">{html.escape(cat)}</span>
        <h2>{html.escape(topic['name'])}</h2>
        <span class="topic-count">{topic['size']} related</span>
        {kw_html}
      </div>
      <div class="cards">{cards}</div>
    </section>"""


def _intel_card(c: dict, now: datetime) -> str:
    opp = float(c.get("opportunity", 0.0))
    opp_pct = max(2, min(100, int(round(opp * 100))))
    opp_hue = int(120 * opp)
    label = html.escape(c.get("label", ""))
    cat = c.get("category", "General")

    rep = _rep_signal(c)
    extra = rep.get("extra", {}) or {}
    explore_url = extra.get("explore_url") or rep.get("url")
    article_url = rep.get("url")
    traffic = extra.get("approx_traffic")
    when = _rel_time(rep.get("published_at"), now)

    title_target = explore_url or article_url
    label_html = (f"<a href='{html.escape(title_target)}' target='_blank' rel='noopener'>{label}</a>"
                  if title_target else label)

    badges = []
    if traffic:
        badges.append(f"<span class='vol'>🔍 {html.escape(str(traffic))}</span>")
    if when:
        badges.append(f"<span class='when'>🕒 {html.escape(when)}</span>")
    srcs = sorted({s.get("source_type", "") for s in c.get("signals", [])})
    src_tags = "".join(f"<span class='tag tag-{html.escape(s)}'>{html.escape(s)}</span>" for s in srcs)

    # Discover potential
    disc = c.get("_discover", {})
    dcolor = _DISCOVER_COLORS.get(disc.get("tier", "Low"), "#7f8aa0")
    dscore = disc.get("score", 0)
    dreasons = ", ".join(html.escape(r) for r in disc.get("reasons", []))

    # Forecast
    fc = c.get("_forecast", {})
    arrow, fcolor, _flabel = _FORECAST.get(fc.get("direction", "new"), _FORECAST["new"])
    proj = fc.get("projected", 0.0)
    fc_txt = (f"{fc.get('label','New')} → {proj:.2f}" if fc.get("points", 0) >= 2
              else "Building history")

    # Competitor analysis
    comp = c.get("_competitor", {})
    if comp.get("first_mover"):
        comp_html = "<span class='firstmover'>★ First-mover — no competitor yet</span>"
    else:
        covered = "".join(f"<span class='cc-has'>{html.escape(x)}</span>"
                          for x in comp.get("covered", [])[:6])
        missing = "".join(f"<span class='cc-gap'>{html.escape(x)}</span>"
                          for x in comp.get("missing", [])[:6])
        comp_html = (f"<div class='cc'><span class='cc-lbl'>has:</span>{covered or '—'}</div>"
                     f"<div class='cc'><span class='cc-lbl'>gap:</span>{missing or '—'}</div>")

    angles = c.get("_angles", c.get("angles", []))
    angles_html = ("<ul class='angles'>"
                   + "".join(f"<li>{html.escape(a)}</li>" for a in angles[:4])
                   + "</ul>") if angles else ""

    return f"""
      <article class="card">
        <div class="card-top">
          <span class="cat" style="--cat:{_category_color(cat)}">{html.escape(cat)}</span>
          <span class="srcs">{src_tags}</span>
        </div>
        <div class="title">{label_html}</div>
        <div class="badges">{''.join(badges)}</div>
        <div class="links">{f"<a class='article' href='{html.escape(article_url)}' target='_blank' rel='noopener'>📰 open source</a>" if article_url else ""}</div>

        <div class="metric">
          <div class="m-row"><span>Traffic Opportunity</span><b>{opp:.3f}</b></div>
          <div class="bar"><div class="fill" style="width:{opp_pct}%;background:hsl({opp_hue},72%,48%)"></div></div>
        </div>
        <div class="metric">
          <div class="m-row"><span>Discover Potential</span>
            <b style="color:{dcolor}">{disc.get('tier','Low')} · {dscore}</b></div>
          <div class="bar"><div class="fill" style="width:{max(2,dscore)}%;background:{dcolor}"></div></div>
          <div class="reasons">{dreasons}</div>
        </div>
        <div class="metric forecast">
          <div class="m-row"><span>Forecast</span>
            <b style="color:{fcolor}">{arrow} {html.escape(fc_txt)}</b></div>
          <div class="spark">{_history_sparkline(c)}</div>
        </div>

        <div class="competitors">
          <div class="sec-lbl">Competitor analysis</div>
          {comp_html}
        </div>

        <div class="angle-sec">
          <div class="sec-lbl">Story angles</div>
          {angles_html or "<div class='muted'>—</div>"}
        </div>

        <div class="components">{_metric_graph(c)}</div>
      </article>"""


_PAGE = """<!doctype html>
<html lang="hi"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="{refresh}">
<title>Newsroom AI Intelligence</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, "Segoe UI", Roboto, sans-serif; margin:0;
          background:#0b0d12; color:#e8eaed; }}
  a {{ color:inherit; }}
  header {{ padding:18px 28px; background:linear-gradient(135deg,#171326,#0f1320);
            border-bottom:1px solid #262b3a; position:sticky; top:0; z-index:5; }}
  .nav {{ display:flex; align-items:center; gap:14px; flex-wrap:wrap; }}
  .nav h1 {{ margin:0; font-size:21px; letter-spacing:.2px; }}
  .nav .pill {{ font-size:11px; background:#7c3aed22; color:#c4b5fd; border:1px solid #7c3aed55;
                padding:3px 10px; border-radius:999px; }}
  .navlink {{ font-size:13px; text-decoration:none; color:#9ec1ff;
              border:1px solid #2c3650; padding:5px 12px; border-radius:8px; background:#141a26; }}
  .navlink:hover {{ background:#1b2333; }}
  .updated {{ color:#5b6678; font-size:11.5px; margin-top:8px; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:18px 24px 70px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px;
           margin-bottom:22px; }}
  .kpi {{ background:#12161f; border:1px solid #222a38; border-radius:12px; padding:14px 16px; }}
  .kpi-v {{ font-size:24px; font-weight:750; }}
  .kpi-l {{ color:#94a0b3; font-size:11.5px; text-transform:uppercase; letter-spacing:.6px; margin-top:3px; }}
  .topic {{ margin:26px 0; }}
  .topic-head {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:12px;
                 padding-bottom:8px; border-bottom:1px solid #1d2433; }}
  .topic-head h2 {{ margin:0; font-size:17px; }}
  .topic-count {{ font-size:11px; color:#7f8aa0; background:#161b27; border:1px solid #262b3a;
                  padding:2px 9px; border-radius:999px; }}
  .topic-kw {{ font-size:11.5px; color:#6b7588; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); gap:16px; }}
  .card {{ background:#12161f; border:1px solid #222a38; border-radius:14px; padding:16px;
           display:flex; flex-direction:column; gap:9px; transition:border-color .15s,transform .15s; }}
  .card:hover {{ border-color:#3a4860; transform:translateY(-2px); }}
  .card-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }}
  .cat {{ display:inline-block; font-size:10px; font-weight:700; letter-spacing:.4px;
          text-transform:uppercase; color:var(--cat); border:1px solid var(--cat);
          background:color-mix(in srgb, var(--cat) 14%, transparent); padding:1px 8px; border-radius:5px; }}
  .srcs {{ display:flex; gap:5px; flex-wrap:wrap; justify-content:flex-end; }}
  .tag {{ font-size:10px; padding:2px 8px; border-radius:999px; white-space:nowrap;
          background:#222838; color:#9ec1ff; border:1px solid #2c3650; }}
  .tag-google_trends {{ background:#2a1e3a; color:#c79bff; border-color:#43306a; }}
  .tag-rss {{ background:#23291c; color:#bcd98a; border-color:#3c4a28; }}
  .tag-youtube {{ background:#3a1d1d; color:#ff9b9b; border-color:#5e2f2f; }}
  .tag-reddit {{ background:#3a2a1d; color:#ffba7a; border-color:#5e442f; }}
  .tag-twitter {{ background:#1d2f3a; color:#8fd1ff; border-color:#2f4d5e; }}
  .title {{ font-size:15.5px; font-weight:650; line-height:1.35; }}
  .title a {{ color:#eef1f6; text-decoration:none; }}
  .title a:hover {{ color:#9ec1ff; text-decoration:underline; }}
  .badges {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .vol {{ background:#15351f; color:#5fd58a; font-size:11px; padding:1px 8px; border-radius:6px;
          border:1px solid #1f5c33; }}
  .when {{ color:#7f8aa0; font-size:11px; }}
  .article {{ color:#79a9ff; font-size:12px; text-decoration:none; }}
  .article:hover {{ text-decoration:underline; }}
  .metric {{ margin-top:2px; }}
  .m-row {{ display:flex; justify-content:space-between; font-size:12px; color:#aeb8c8; margin-bottom:4px; }}
  .m-row b {{ color:#eef1f6; font-variant-numeric:tabular-nums; }}
  .bar {{ height:7px; background:#0b0d12; border:1px solid #222a38; border-radius:6px; overflow:hidden; }}
  .bar .fill {{ height:100%; }}
  .reasons {{ font-size:10.5px; color:#6b7588; margin-top:3px; }}
  .forecast .spark {{ background:#0e1119; border:1px solid #1d2433; border-radius:6px; padding:2px; margin-top:5px; }}
  .sec-lbl {{ font-size:10px; text-transform:uppercase; letter-spacing:.6px; color:#5b6678; margin:6px 0 4px; }}
  .cc {{ display:flex; gap:5px; flex-wrap:wrap; align-items:center; margin-bottom:3px; }}
  .cc-lbl {{ font-size:10.5px; color:#7f8aa0; }}
  .cc-has {{ font-size:10.5px; background:#15351f; color:#5fd58a; border:1px solid #1f5c33;
             padding:1px 7px; border-radius:5px; }}
  .cc-gap {{ font-size:10.5px; background:#1b2230; color:#8090a8; border:1px solid #2c3650;
             padding:1px 7px; border-radius:5px; }}
  .firstmover {{ font-size:11.5px; color:#ffd479; background:#3a2f17; border:1px solid #5e4a22;
                 padding:3px 9px; border-radius:6px; display:inline-block; }}
  .angles {{ margin:2px 0 0; padding-left:16px; color:#c4cee0; font-size:12px; line-height:1.5; }}
  .components {{ margin-top:6px; }}
  .components svg {{ display:block; }}
  .muted {{ color:#5b6678; font-size:12px; }}
  .empty {{ color:#94a0b3; padding:60px; text-align:center; }}
  code {{ background:#1b2230; padding:2px 6px; border-radius:4px; }}
  @media (max-width:560px) {{ .cards {{ grid-template-columns:1fr; }} }}
</style></head>
<body>
<header>
  <div class="nav">
    <a class="navlink" href="index.html">← Live Dashboard</a>
    <h1>🧠 Newsroom AI Intelligence</h1>
    <span class="pill">AI · agent-based · auto-refresh {refresh}s</span>
  </div>
  <div class="updated">{updated}</div>
</header>
<div class="wrap">
  <div class="kpis">{kpis}</div>
  {topics}
</div>
</body></html>"""
