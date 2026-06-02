"""Newsroom AI Intelligence dashboard (separate page from the classic dashboard).

A read-only, agent-enriched view of the same `latest.json`. Reuses the classic
dashboard's helper renderers + theme and adds the advanced features: Traffic Opportunity
Score, Discover Potential, Forecasting, Competitor Analysis, Story Angles, grouped by
Topic Clustering — plus clickable source/category filters (client-side, works on static
GitHub Pages) and actionable headline metrics.

This module does NOT modify the classic dashboard; it only imports shared helpers.
"""

from __future__ import annotations

import html
from collections import Counter
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
# source type -> display label for the filter buttons
_SOURCE_LABELS = {
    "google_trends": "Google Trends",
    "twitter": "X Trends",
    "rss": "RSS",
    "youtube": "YouTube",
    "reddit": "Reddit",
}


def render_intelligence_html(data: dict | None, refresh_seconds: int = 60) -> str:
    now = datetime.now(timezone.utc)
    if data is None or not data.get("clusters"):
        body = ("<div class='empty'>No report yet. The scheduler will populate this "
                "shortly, or run <code>python -m newsroom_trends.cli run</code>.</div>")
        return _PAGE.format(refresh=refresh_seconds, updated="", kpis="", filters="",
                            body=body, script=_JS)

    intel = analyze_report(data)
    clusters = intel["data"]["clusters"]
    summary = intel["summary"]

    ranked = sorted(range(len(clusters)), key=lambda i: -clusters[i].get("opportunity", 0.0))
    show = set(ranked[:MAX_STORIES])
    shown = [i for i in ranked if i in show]

    updated = f"updated {_rel_time(data.get('generated_at'), now)}"

    # --- actionable headline metrics (clickable view filters) ----------------------
    kpis = _kpi_cards(summary, len(shown))

    # --- filter buttons ------------------------------------------------------------
    sources_present = [s for s in _SOURCE_LABELS
                       if any(s in {sig.get("source_type") for sig in clusters[i].get("signals", [])}
                              for i in shown)]
    cat_counts = Counter(clusters[i].get("category", "General") for i in shown)
    filters = _filter_bar(sources_present, cat_counts)

    # --- body: multi-story topics as sections, the rest in one flat grid -----------
    multi_topics = [t for t in intel["topics"]
                    if len([m for m in t["indices"] if m in show]) >= 2]
    grouped: set[int] = set()
    sections = []
    for t in multi_topics:
        members = [m for m in t["indices"] if m in show]
        grouped.update(members)
        sections.append(_render_topic(t, members, clusters, now))
    singles = [i for i in shown if i not in grouped]
    body = "".join(sections)
    if singles:
        cards = "".join(_intel_card(clusters[i], now) for i in singles)
        head = ("<div class='topic-head'><h2>More trending stories</h2>"
                f"<span class='topic-count'>{len(singles)}</span></div>"
                if sections else "")
        body += f"<section class='topic'>{head}<div class='cards'>{cards}</div></section>"

    return _PAGE.format(refresh=refresh_seconds, updated=html.escape(updated),
                        kpis=kpis, filters=filters, body=body, script=_JS)


def _kpi_cards(summary: dict, shown_count: int) -> str:
    cards = [
        ("all", "📊", "All stories", shown_count, "#9ec1ff"),
        ("emerging", "🚀", "Emerging trends", summary.get("rising", 0), "#22c55e"),
        ("discover", "🔥", "High Discover potential", summary.get("high_discover", 0), "#fbbf24"),
        ("firstmover", "🎯", "First-mover gaps", summary.get("first_mover", 0), "#ffd479"),
        ("cross", "🌐", "Cross-platform breakouts", summary.get("cross_platform", 0), "#c79bff"),
    ]
    out = []
    for view, icon, label, value, color in cards:
        active = " active" if view == "all" else ""
        out.append(
            f"<button class='kpi{active}' data-dim='view' data-val='{view}' "
            f"style='--accent:{color}'>"
            f"<div class='kpi-v'>{icon} {value}</div>"
            f"<div class='kpi-l'>{html.escape(label)}</div></button>"
        )
    return "".join(out)


def _filter_bar(sources_present: list[str], cat_counts: Counter) -> str:
    src_btns = ["<button class='fbtn active' data-dim='source' data-val='all'>All sources</button>"]
    for s in sources_present:
        src_btns.append(
            f"<button class='fbtn' data-dim='source' data-val='{html.escape(s)}'>"
            f"{html.escape(_SOURCE_LABELS.get(s, s))}</button>"
        )
    cat_btns = ["<button class='fbtn active' data-dim='category' data-val='all'>All categories</button>"]
    for cat, n in cat_counts.most_common():
        cat_btns.append(
            f"<button class='fbtn' data-dim='category' data-val='{html.escape(cat)}'>"
            f"{html.escape(cat)} <span class='fn'>{n}</span></button>"
        )
    return (
        "<div class='filters'>"
        f"<div class='frow'><span class='fl'>Source</span>{''.join(src_btns)}</div>"
        f"<div class='frow'><span class='fl'>Category</span>{''.join(cat_btns)}</div>"
        "<div class='frow'><span class='fl'>Showing</span>"
        "<span id='count' class='count'></span></div>"
        "</div>"
    )


def _render_topic(topic: dict, members: list[int], clusters: list[dict], now: datetime) -> str:
    members = sorted(members, key=lambda m: -clusters[m].get("opportunity", 0.0))[:MAX_PER_TOPIC]
    cards = "".join(_intel_card(clusters[m], now) for m in members)
    cat = topic["category"]
    return (
        "<section class='topic'>"
        "<div class='topic-head'>"
        f"<span class='cat' style='--cat:{_category_color(cat)}'>{html.escape(cat)}</span>"
        f"<h2>{html.escape(topic['name'])}</h2>"
        f"<span class='topic-count'>{len(members)} related</span>"
        "</div>"
        f"<div class='cards'>{cards}</div></section>"
    )


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

    srcs = sorted({s.get("source_type", "") for s in c.get("signals", [])})
    src_tags = "".join(f"<span class='tag tag-{html.escape(s)}'>{html.escape(s)}</span>" for s in srcs)

    # badges (only render if present — no blank rows)
    badges = []
    if traffic:
        badges.append(f"<span class='vol'>🔍 {html.escape(str(traffic))}</span>")
    if when:
        badges.append(f"<span class='when'>🕒 {html.escape(when)}</span>")
    badges_html = f"<div class='badges'>{''.join(badges)}</div>" if badges else ""

    disc = c.get("_discover", {})
    dcolor = _DISCOVER_COLORS.get(disc.get("tier", "Low"), "#7f8aa0")
    dscore = disc.get("score", 0)
    dreasons = ", ".join(html.escape(r) for r in disc.get("reasons", []))
    reasons_html = f"<div class='reasons'>{dreasons}</div>" if dreasons else ""

    fc = c.get("_forecast", {})
    arrow, fcolor, _ = _FORECAST.get(fc.get("direction", "new"), _FORECAST["new"])
    proj = fc.get("projected", 0.0)
    fc_txt = (f"{fc.get('label','New')} → {proj:.2f}" if fc.get("points", 0) >= 2
              else "Building history")

    comp = c.get("_competitor", {})
    comp_html = ""
    if comp.get("universe", 0) > 0:
        if comp.get("first_mover"):
            inner = "<span class='firstmover'>★ First-mover — no competitor yet</span>"
        else:
            has = "".join(f"<span class='cc-has'>{html.escape(x)}</span>"
                          for x in comp.get("covered", [])[:6])
            gap = "".join(f"<span class='cc-gap'>{html.escape(x)}</span>"
                          for x in comp.get("missing", [])[:6])
            rows = []
            if has:
                rows.append(f"<div class='cc'><span class='cc-lbl'>has</span>{has}</div>")
            if gap:
                rows.append(f"<div class='cc'><span class='cc-lbl'>gap</span>{gap}</div>")
            inner = "".join(rows)
        if inner:
            comp_html = (f"<div class='block'><div class='sec-lbl'>Competitor analysis</div>{inner}</div>")

    angles = c.get("_angles", c.get("angles", []))
    angles_html = ""
    if angles:
        items = "".join(f"<li>{html.escape(a)}</li>" for a in angles[:4])
        angles_html = f"<div class='block'><div class='sec-lbl'>Story angles</div><ul class='angles'>{items}</ul></div>"

    # data-* attributes drive the client-side filters
    attrs = (
        f"data-sources=\"{html.escape(' '.join(srcs))}\" "
        f"data-category=\"{html.escape(cat)}\" "
        f"data-emerging=\"{1 if fc.get('direction') == 'up' else 0}\" "
        f"data-discover=\"{html.escape(disc.get('tier', 'Low'))}\" "
        f"data-firstmover=\"{1 if comp.get('first_mover') else 0}\" "
        f"data-cross=\"{1 if len(srcs) > 1 else 0}\""
    )
    return f"""
      <article class="card" {attrs}>
        <div class="card-top">
          <span class="cat" style="--cat:{_category_color(cat)}">{html.escape(cat)}</span>
          <span class="srcs">{src_tags}</span>
        </div>
        <div class="title">{label_html}</div>
        {badges_html}
        {f'<div class="links"><a class="article" href="{html.escape(article_url)}" target="_blank" rel="noopener">📰 open source</a></div>' if article_url else ''}
        <div class="metric">
          <div class="m-row"><span>Traffic Opportunity</span><b>{opp:.3f}</b></div>
          <div class="bar"><div class="fill" style="width:{opp_pct}%;background:hsl({opp_hue},72%,48%)"></div></div>
        </div>
        <div class="metric">
          <div class="m-row"><span>Discover Potential</span><b style="color:{dcolor}">{disc.get('tier','Low')} · {dscore}</b></div>
          <div class="bar"><div class="fill" style="width:{max(2,dscore)}%;background:{dcolor}"></div></div>
          {reasons_html}
        </div>
        <div class="metric">
          <div class="m-row"><span>Forecast</span><b style="color:{fcolor}">{arrow} {html.escape(fc_txt)}</b></div>
          <div class="spark">{_history_sparkline(c)}</div>
        </div>
        {comp_html}
        {angles_html}
        <div class="components">{_metric_graph(c)}</div>
      </article>"""


_JS = """
(function(){
  var state = {source:'all', category:'all', view:'all'};
  try { Object.assign(state, JSON.parse(sessionStorage.getItem('niFilters')||'{}')); } catch(e){}

  function apply(){
    var cards = document.querySelectorAll('.card'), n = 0;
    cards.forEach(function(c){
      var okS = state.source==='all' || (c.dataset.sources||'').split(' ').indexOf(state.source) >= 0;
      var okC = state.category==='all' || c.dataset.category===state.category;
      var okV = true;
      if (state.view==='emerging')        okV = c.dataset.emerging==='1';
      else if (state.view==='discover')   okV = c.dataset.discover==='High';
      else if (state.view==='firstmover') okV = c.dataset.firstmover==='1';
      else if (state.view==='cross')      okV = c.dataset.cross==='1';
      var vis = okS && okC && okV;
      c.style.display = vis ? '' : 'none';
      if (vis) n++;
    });
    document.querySelectorAll('.topic').forEach(function(sec){
      var any = false;
      sec.querySelectorAll('.card').forEach(function(c){ if (c.style.display !== 'none') any = true; });
      sec.style.display = any ? '' : 'none';
    });
    var cnt = document.getElementById('count'); if (cnt) cnt.textContent = n + ' stories';
    document.querySelectorAll('[data-dim]').forEach(function(b){
      b.classList.toggle('active', state[b.dataset.dim] === b.dataset.val);
    });
  }
  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('[data-dim]').forEach(function(b){
      b.addEventListener('click', function(){
        state[b.dataset.dim] = b.dataset.val;
        try { sessionStorage.setItem('niFilters', JSON.stringify(state)); } catch(e){}
        apply();
      });
    });
    apply();
  });
})();
"""


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
  header {{ padding:16px 24px; background:linear-gradient(135deg,#171326,#0f1320);
            border-bottom:1px solid #262b3a; position:sticky; top:0; z-index:5; }}
  .nav {{ display:flex; align-items:center; gap:12px; flex-wrap:wrap; }}
  .nav h1 {{ margin:0; font-size:20px; }}
  .nav .pill {{ font-size:11px; background:#7c3aed22; color:#c4b5fd; border:1px solid #7c3aed55;
                padding:3px 10px; border-radius:999px; }}
  .navlink {{ font-size:13px; text-decoration:none; color:#9ec1ff; border:1px solid #2c3650;
              padding:5px 12px; border-radius:8px; background:#141a26; }}
  .navlink:hover {{ background:#1b2333; }}
  .updated {{ color:#5b6678; font-size:11.5px; margin-top:6px; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:16px 24px 60px; }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin-bottom:16px; }}
  .kpi {{ text-align:left; cursor:pointer; font:inherit; color:inherit;
          background:#12161f; border:1px solid #222a38; border-radius:12px; padding:13px 15px;
          transition:border-color .12s, transform .12s; }}
  .kpi:hover {{ transform:translateY(-1px); border-color:#3a4860; }}
  .kpi.active {{ border-color:var(--accent); box-shadow:0 0 0 1px var(--accent) inset; }}
  .kpi-v {{ font-size:22px; font-weight:750; color:var(--accent); }}
  .kpi-l {{ color:#94a0b3; font-size:11px; text-transform:uppercase; letter-spacing:.5px; margin-top:3px; }}
  .filters {{ background:#10141d; border:1px solid #1d2433; border-radius:12px; padding:10px 12px;
              margin-bottom:18px; display:flex; flex-direction:column; gap:8px; }}
  .frow {{ display:flex; align-items:center; gap:7px; flex-wrap:wrap; }}
  .fl {{ font-size:10.5px; text-transform:uppercase; letter-spacing:.6px; color:#5b6678; min-width:64px; }}
  .fbtn {{ cursor:pointer; font:inherit; font-size:12px; color:#aeb8c8; background:#161b27;
           border:1px solid #2a3142; padding:4px 11px; border-radius:999px; transition:all .12s; }}
  .fbtn:hover {{ border-color:#3a4860; color:#e8eaed; }}
  .fbtn.active {{ background:#1f6feb22; border-color:#1f6feb; color:#cfe0ff; }}
  .fbtn .fn {{ color:#6b7588; font-size:10.5px; }}
  .count {{ font-size:12px; color:#7fb0ff; font-weight:600; }}
  .topic {{ margin:18px 0; }}
  .topic-head {{ display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:10px;
                 padding-bottom:7px; border-bottom:1px solid #1d2433; }}
  .topic-head h2 {{ margin:0; font-size:16px; }}
  .topic-count {{ font-size:11px; color:#7f8aa0; background:#161b27; border:1px solid #262b3a;
                  padding:2px 9px; border-radius:999px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(310px,1fr)); gap:14px; }}
  .card {{ background:#12161f; border:1px solid #222a38; border-radius:14px; padding:14px;
           display:flex; flex-direction:column; gap:8px; transition:border-color .15s, transform .15s; }}
  .card:hover {{ border-color:#3a4860; transform:translateY(-2px); }}
  .card-top {{ display:flex; justify-content:space-between; align-items:flex-start; gap:8px; }}
  .cat {{ display:inline-block; font-size:10px; font-weight:700; letter-spacing:.4px; text-transform:uppercase;
          color:var(--cat); border:1px solid var(--cat);
          background:color-mix(in srgb, var(--cat) 14%, transparent); padding:1px 8px; border-radius:5px; }}
  .srcs {{ display:flex; gap:5px; flex-wrap:wrap; justify-content:flex-end; }}
  .tag {{ font-size:10px; padding:2px 8px; border-radius:999px; white-space:nowrap;
          background:#222838; color:#9ec1ff; border:1px solid #2c3650; }}
  .tag-google_trends {{ background:#2a1e3a; color:#c79bff; border-color:#43306a; }}
  .tag-rss {{ background:#23291c; color:#bcd98a; border-color:#3c4a28; }}
  .tag-youtube {{ background:#3a1d1d; color:#ff9b9b; border-color:#5e2f2f; }}
  .tag-reddit {{ background:#3a2a1d; color:#ffba7a; border-color:#5e442f; }}
  .tag-twitter {{ background:#1d2f3a; color:#8fd1ff; border-color:#2f4d5e; }}
  .title {{ font-size:15px; font-weight:650; line-height:1.35; }}
  .title a {{ color:#eef1f6; text-decoration:none; }}
  .title a:hover {{ color:#9ec1ff; text-decoration:underline; }}
  .badges {{ display:flex; gap:8px; flex-wrap:wrap; }}
  .vol {{ background:#15351f; color:#5fd58a; font-size:11px; padding:1px 8px; border-radius:6px; border:1px solid #1f5c33; }}
  .when {{ color:#7f8aa0; font-size:11px; }}
  .article {{ color:#79a9ff; font-size:12px; text-decoration:none; }}
  .article:hover {{ text-decoration:underline; }}
  .metric {{ }}
  .m-row {{ display:flex; justify-content:space-between; font-size:12px; color:#aeb8c8; margin-bottom:4px; }}
  .m-row b {{ color:#eef1f6; font-variant-numeric:tabular-nums; }}
  .bar {{ height:7px; background:#0b0d12; border:1px solid #222a38; border-radius:6px; overflow:hidden; }}
  .bar .fill {{ height:100%; }}
  .reasons {{ font-size:10.5px; color:#6b7588; margin-top:3px; }}
  .spark {{ background:#0e1119; border:1px solid #1d2433; border-radius:6px; padding:2px; margin-top:5px; }}
  .block {{ }}
  .sec-lbl {{ font-size:10px; text-transform:uppercase; letter-spacing:.6px; color:#5b6678; margin:2px 0 4px; }}
  .cc {{ display:flex; gap:5px; flex-wrap:wrap; align-items:center; margin-bottom:3px; }}
  .cc-lbl {{ font-size:10.5px; color:#7f8aa0; }}
  .cc-has {{ font-size:10.5px; background:#15351f; color:#5fd58a; border:1px solid #1f5c33; padding:1px 7px; border-radius:5px; }}
  .cc-gap {{ font-size:10.5px; background:#1b2230; color:#8090a8; border:1px solid #2c3650; padding:1px 7px; border-radius:5px; }}
  .firstmover {{ font-size:11.5px; color:#ffd479; background:#3a2f17; border:1px solid #5e4a22; padding:3px 9px; border-radius:6px; display:inline-block; }}
  .angles {{ margin:0; padding-left:16px; color:#c4cee0; font-size:12px; line-height:1.5; }}
  .components svg {{ display:block; }}
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
  {filters}
  {body}
</div>
<script>{script}</script>
</body></html>"""
