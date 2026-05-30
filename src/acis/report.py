"""HTML dashboard generator — produces output/report.html after every run.

Called from run.py after write_summary(). Self-contained single HTML file:
no external assets required beyond Chart.js loaded from jsDelivr CDN.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from acis.models import RunSummary


def generate_html_report(summary: RunSummary, output_path: Path) -> None:
    """Write a full HTML dashboard to output_path (e.g. output/report.html)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_build_html(summary), encoding="utf-8")


# ---------------------------------------------------------------------------
# Data extraction helpers
# ---------------------------------------------------------------------------

def _top_topics(summary: RunSummary, n: int = 12) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for r in summary.results:
        g = r.semantic_graph
        for t in g.technical_tools + g.architectures + g.use_cases + g.business_models:
            counter[t] += 1
    return counter.most_common(n)


def _hook_distribution(summary: RunSummary) -> dict[str, int]:
    counter: Counter = Counter()
    for r in summary.results:
        if r.hook_profile:
            counter[r.hook_profile.primary_taxonomy] += 1
    return dict(counter.most_common())


def _hype_stats(summary: RunSummary) -> dict[str, float]:
    scores = [r.hook_profile.hype_score for r in summary.results if r.hook_profile]
    if not scores:
        return {"mean": 0.0, "max": 0.0, "min": 0.0}
    return {
        "mean": round(sum(scores) / len(scores), 2),
        "max": round(max(scores), 2),
        "min": round(min(scores), 2),
    }


def _channel_velocity_data(summary: RunSummary) -> dict[str, object]:
    labels, medians = [], []
    for ch_id, matrix in summary.performance_matrices.items():
        labels.append(ch_id)
        medians.append(round(matrix.channel_median_velocity, 0))
    return {"labels": labels, "medians": medians}


def _significant_correlations(summary: RunSummary) -> list[dict]:
    rows = []
    for matrix in summary.performance_matrices.values():
        for corr in matrix.correlations:
            if corr.significant:
                rows.append({
                    "channel": matrix.channel_id,
                    "attribute": corr.attribute,
                    "multiplier": round(corr.mean_multiplier, 2),
                    "p_value": round(corr.p_value, 3),
                })
    rows.sort(key=lambda r: -r["multiplier"])
    return rows


def _md_to_html(text: str) -> str:
    """Minimal Markdown → HTML: bold, bullets, line breaks."""
    import re
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    lines, out, in_ul = text.split("\n"), [], False
    for line in lines:
        s = line.strip()
        if s.startswith("- ") or s.startswith("* "):
            if not in_ul:
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{s[2:]}</li>")
        else:
            if in_ul:
                out.append("</ul>")
                in_ul = False
            if s:
                out.append(f"<p>{s}</p>")
    if in_ul:
        out.append("</ul>")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def _build_html(summary: RunSummary) -> str:  # noqa: PLR0914
    run_date = summary.started_at.strftime("%d %b %Y, %H:%M UTC")
    duration_s = int((summary.completed_at - summary.started_at).total_seconds())
    duration_str = f"{duration_s // 60}m {duration_s % 60}s" if duration_s >= 60 else f"{duration_s}s"

    top_topics = _top_topics(summary)
    hook_dist  = _hook_distribution(summary)
    hype       = _hype_stats(summary)
    vel_data   = _channel_velocity_data(summary)
    sig_corr   = _significant_correlations(summary)
    brief      = summary.strategic_brief
    opp        = summary.opportunity_vector

    n_gaps = len(opp.opportunities) if opp else 0
    n_sig  = len(sig_corr)

    hook_palette = ["#4f46e5","#7c3aed","#db2777","#ea580c",
                    "#ca8a04","#16a34a","#0891b2","#475569"]

    topic_labels_js = json.dumps([t for t, _ in top_topics])
    topic_counts_js = json.dumps([c for _, c in top_topics])
    hook_labels_js  = json.dumps(list(hook_dist.keys()))
    hook_counts_js  = json.dumps(list(hook_dist.values()))
    hook_colors_js  = json.dumps(hook_palette[:len(hook_dist)])
    vel_labels_js   = json.dumps(vel_data["labels"])
    vel_medians_js  = json.dumps(vel_data["medians"])
    hype_scores_js  = json.dumps([
        round(r.hook_profile.hype_score, 2)
        for r in summary.results if r.hook_profile
    ])

    # ── Gap opportunity cards ──────────────────────────────────────
    gap_cards_html = ""
    if opp and opp.opportunities:
        for item in opp.opportunities:
            conf_pct = int(item.confidence * 100)
            sat_pct  = int(item.saturation_score * 100)
            conf_color = "#059669" if conf_pct >= 70 else "#d97706" if conf_pct >= 50 else "#dc2626"
            adj_tags = "".join(
                f'<span class="tag">{t}</span>' for t in item.adjacent_rising_topics[:4]
            )
            ev_items = "".join(f"<li>{e}</li>" for e in item.evidence)
            gap_cards_html += f"""
<div class="gap-card">
  <div class="gap-header">
    <span class="gap-topic">{item.topic}</span>
    <span class="gap-conf" style="color:{conf_color}">Confidence {conf_pct}%</span>
  </div>
  <div class="bar-row">
    <span class="bar-label">Saturation</span>
    <div class="bar-track"><div class="bar-fill sat-fill" style="width:{sat_pct}%"></div></div>
    <span class="bar-val">{item.saturation_score:.2f}</span>
  </div>
  <div class="bar-row">
    <span class="bar-label">Confidence</span>
    <div class="bar-track"><div class="bar-fill conf-fill" style="width:{conf_pct}%"></div></div>
    <span class="bar-val">{item.confidence:.2f}</span>
  </div>
  <div class="gap-adj">Adjacent rising: {adj_tags if adj_tags else "<em>none</em>"}</div>
  <ul class="gap-evidence">{ev_items}</ul>
</div>"""
    else:
        gap_cards_html = '<p class="empty">No gap opportunities detected in this run.</p>'

    # ── Correlations table ─────────────────────────────────────────
    corr_rows_html = ""
    for row in sig_corr:
        mult = row["multiplier"]
        bc = "badge-green" if mult >= 1.5 else "badge-blue"
        corr_rows_html += f"""
<tr>
  <td>{row['channel']}</td>
  <td><code>{row['attribute']}</code></td>
  <td><span class="badge {bc}">{mult}×</span></td>
  <td>p = {row['p_value']}</td>
</tr>"""
    if not corr_rows_html:
        corr_rows_html = '<tr><td colspan="4" class="empty-cell">No significant correlations (p&lt;0.05) detected.</td></tr>'

    # ── Brief sections ─────────────────────────────────────────────
    def brief_sec(title: str, content: str, icon: str) -> str:
        return (f'<div class="brief-sec">'
                f'<div class="brief-sec-title">{icon} {title}</div>'
                f'<div class="brief-body">{_md_to_html(content)}</div>'
                f'</div>')

    brief_html = ""
    if brief:
        brief_html = (
            brief_sec("Situation", brief.situation, "📊") +
            brief_sec("Complication", brief.complication, "⚠️") +
            brief_sec("Resolution", brief.resolution, "🎯") +
            brief_sec("Recommendations", brief.recommendations, "✅") +
            brief_sec("Risks & Falsification", brief.risks_and_falsification, "🔍") +
            brief_sec("Belief Updates", brief.belief_graph_deltas, "🧠")
        )
    else:
        brief_html = '<p class="empty">Strategic brief not available (run with --full).</p>'

    hype_color = "#dc2626" if hype["mean"] > 0.6 else "#d97706" if hype["mean"] > 0.35 else "#059669"
    hype_label = "High" if hype["mean"] > 0.6 else "Moderate" if hype["mean"] > 0.35 else "Low"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>ACIS Report — {run_date}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#f0f4f8;--surface:#fff;--border:#e2e8f0;--accent:#4f46e5;
  --accent-light:#ede9fe;--text:#0f172a;--muted:#64748b;
  --green:#059669;--amber:#d97706;--red:#dc2626}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6}}
.header{{background:linear-gradient(135deg,#1e1b4b 0%,#312e81 55%,#4338ca 100%);
  padding:32px 40px;color:#fff}}
.header-inner{{max-width:1200px;margin:0 auto;display:flex;justify-content:space-between;
  align-items:flex-end;flex-wrap:wrap;gap:16px}}
.header h1{{font-size:24px;font-weight:800;letter-spacing:-.02em}}
.header h1 span{{color:#a5b4fc}}
.header-meta{{font-size:13px;color:#c7d2fe;display:flex;gap:24px;flex-wrap:wrap}}
.header-meta b{{color:#fff;display:block;margin-bottom:2px}}
.run-id{{background:rgba(255,255,255,.12);color:#e0e7ff;padding:2px 7px;
  border-radius:4px;font-size:11px;font-family:monospace}}
.wrapper{{max-width:1200px;margin:0 auto;padding:28px 20px 64px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
  gap:14px;margin-bottom:24px}}
.card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:18px 22px;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
.card-label{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);margin-bottom:6px}}
.card-value{{font-size:30px;font-weight:800;line-height:1}}
.card-sub{{font-size:12px;color:var(--muted);margin-top:4px}}
.c-accent{{border-top:3px solid var(--accent)}}
.c-green{{border-top:3px solid var(--green)}}
.c-amber{{border-top:3px solid var(--amber)}}
.charts-grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}}
@media(max-width:760px){{.charts-grid{{grid-template-columns:1fr}}}}
.chart-card{{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:22px 24px;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
.chart-title{{font-size:13px;font-weight:700;margin-bottom:14px}}
.chart-container{{position:relative;height:240px}}
.section{{background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:24px 28px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
.section-title{{font-size:15px;font-weight:700;margin-bottom:18px;
  display:flex;align-items:center;gap:8px}}
.section-title::before{{content:'';display:block;width:3px;height:16px;
  background:var(--accent);border-radius:2px}}
.gaps-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}}
.gap-card{{border:1px solid var(--border);border-radius:10px;padding:18px;
  transition:box-shadow .15s}}
.gap-card:hover{{box-shadow:0 4px 16px rgba(79,70,229,.1)}}
.gap-header{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}}
.gap-topic{{font-size:16px;font-weight:700}}
.gap-conf{{font-size:12px;font-weight:700}}
.bar-row{{display:flex;align-items:center;gap:8px;margin-bottom:7px}}
.bar-label{{font-size:11px;color:var(--muted);width:74px;flex-shrink:0}}
.bar-track{{flex:1;height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden}}
.bar-fill{{height:100%;border-radius:3px}}
.sat-fill{{background:#dc2626}}
.conf-fill{{background:var(--green)}}
.bar-val{{font-size:11px;font-weight:600;width:28px;text-align:right}}
.gap-adj{{font-size:11px;color:var(--muted);margin:10px 0 6px}}
.tag{{display:inline-block;background:var(--accent-light);color:var(--accent);
  font-size:11px;font-weight:600;padding:1px 7px;border-radius:9px;margin:1px}}
.gap-evidence{{padding-left:14px;font-size:11px;color:var(--muted)}}
.gap-evidence li{{margin-bottom:2px}}
.table-wrap{{overflow-x:auto;border-radius:9px;border:1px solid var(--border)}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
thead tr{{background:#f8fafc}}
th{{text-align:left;padding:9px 13px;font-size:11px;font-weight:700;
  text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
  border-bottom:1px solid var(--border)}}
td{{padding:10px 13px;border-bottom:1px solid var(--border);vertical-align:top}}
tbody tr:last-child td{{border-bottom:none}}
tbody tr:hover{{background:#fafbff}}
.empty-cell{{color:var(--muted);font-style:italic;padding:16px 13px}}
code{{background:#f3f4f6;color:#be185d;padding:1px 5px;border-radius:3px;font-size:11px}}
.badge{{display:inline-block;padding:2px 8px;border-radius:10px;font-size:12px;font-weight:700}}
.badge-green{{background:#d1fae5;color:#065f46}}
.badge-blue{{background:#dbeafe;color:#1d4ed8}}
.brief-sec{{border-bottom:1px solid var(--border);padding:18px 0}}
.brief-sec:last-child{{border-bottom:none;padding-bottom:0}}
.brief-sec-title{{font-size:12px;font-weight:700;color:var(--accent);
  text-transform:uppercase;letter-spacing:.07em;margin-bottom:10px}}
.brief-body p{{font-size:14px;color:#374151;margin-bottom:7px}}
.brief-body ul{{padding-left:18px;margin-bottom:7px}}
.brief-body li{{font-size:14px;color:#374151;margin-bottom:3px}}
.brief-body strong{{color:var(--text)}}
.empty{{color:var(--muted);font-style:italic;font-size:14px}}
</style>
</head>
<body>

<div class="header">
  <div class="header-inner">
    <div>
      <h1>ACIS <span>Strategic Report</span></h1>
      <div style="font-size:12px;color:#c7d2fe;margin-top:5px">Autonomous Creator Intelligence System</div>
    </div>
    <div class="header-meta">
      <div><b>Run date</b>{run_date}</div>
      <div><b>Duration</b>{duration_str}</div>
      <div><b>Run ID</b><span class="run-id">{summary.run_id[:8]}…</span></div>
    </div>
  </div>
</div>

<div class="wrapper">

<div class="cards">
  <div class="card c-accent">
    <div class="card-label">Videos Processed</div>
    <div class="card-value">{summary.videos_processed}</div>
    <div class="card-sub">{summary.videos_skipped} deduplicated/skipped</div>
  </div>
  <div class="card c-accent">
    <div class="card-label">Channels</div>
    <div class="card-value">{summary.channels_processed}</div>
    <div class="card-sub">analysed this run</div>
  </div>
  <div class="card c-green">
    <div class="card-label">Gap Opportunities</div>
    <div class="card-value">{n_gaps}</div>
    <div class="card-sub">white-space topics</div>
  </div>
  <div class="card c-amber">
    <div class="card-label">Sig. Correlations</div>
    <div class="card-value">{n_sig}</div>
    <div class="card-sub">p &lt; 0.05 format signals</div>
  </div>
  <div class="card" style="border-top:3px solid {hype_color}">
    <div class="card-label">Avg Hype Score</div>
    <div class="card-value" style="color:{hype_color}">{hype['mean']}</div>
    <div class="card-sub">{hype_label} · max {hype['max']}</div>
  </div>
</div>

<div class="charts-grid">
  <div class="chart-card">
    <div class="chart-title">Top Topics — Video Frequency</div>
    <div class="chart-container"><canvas id="topicsChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Hook Taxonomy Distribution</div>
    <div class="chart-container"><canvas id="hookChart"></canvas></div>
  </div>
</div>
<div class="charts-grid">
  <div class="chart-card">
    <div class="chart-title">Channel Median Velocity (views/day)</div>
    <div class="chart-container"><canvas id="velocityChart"></canvas></div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Hype Score Distribution</div>
    <div class="chart-container"><canvas id="hypeChart"></canvas></div>
  </div>
</div>

<div class="section">
  <div class="section-title">Gap Opportunities</div>
  <div class="gaps-grid">{gap_cards_html}</div>
</div>

<div class="section">
  <div class="section-title">Significant Performance Correlations</div>
  <div class="table-wrap"><table>
    <thead><tr><th>Channel</th><th>Attribute</th><th>Multiplier</th><th>p-value</th></tr></thead>
    <tbody>{corr_rows_html}</tbody>
  </table></div>
</div>

<div class="section">
  <div class="section-title">Strategic Brief</div>
  {brief_html}
</div>

</div>

<script>
Chart.defaults.font.family="system-ui,sans-serif";
Chart.defaults.color="#64748b";

new Chart(document.getElementById("topicsChart"),{{
  type:"bar",
  data:{{labels:{topic_labels_js},datasets:[{{label:"Videos",data:{topic_counts_js},
    backgroundColor:"rgba(79,70,229,0.72)",borderRadius:5}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{maxRotation:38,font:{{size:11}}}}}},
      y:{{grid:{{color:"#f1f5f9"}},ticks:{{stepSize:1}}}}}}}}
}});

new Chart(document.getElementById("hookChart"),{{
  type:"doughnut",
  data:{{labels:{hook_labels_js},datasets:[{{data:{hook_counts_js},
    backgroundColor:{hook_colors_js},borderWidth:2,borderColor:"#fff"}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{position:"right",labels:{{boxWidth:11,font:{{size:11}}}}}}}}}}
}});

new Chart(document.getElementById("velocityChart"),{{
  type:"bar",
  data:{{labels:{vel_labels_js},datasets:[{{label:"Median views/day",data:{vel_medians_js},
    backgroundColor:"rgba(5,150,105,0.72)",borderRadius:5}}]}},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{grid:{{display:false}}}},y:{{grid:{{color:"#f1f5f9"}}}}}}}}
}});

const hs={hype_scores_js};
const bins=[0,.1,.2,.3,.4,.5,.6,.7,.8,.9,1.0];
new Chart(document.getElementById("hypeChart"),{{
  type:"bar",
  data:{{
    labels:bins.slice(0,-1).map((b,i)=>b.toFixed(1)+"–"+bins[i+1].toFixed(1)),
    datasets:[{{label:"Videos",
      data:bins.slice(0,-1).map((b,i)=>hs.filter(s=>s>=b&&s<bins[i+1]).length),
      backgroundColor:bins.slice(0,-1).map(b=>b<0.35?"rgba(5,150,105,.72)":b<0.6?"rgba(217,119,6,.72)":"rgba(220,38,38,.72)"),
      borderRadius:4}}]
  }},
  options:{{responsive:true,maintainAspectRatio:false,
    plugins:{{legend:{{display:false}}}},
    scales:{{x:{{grid:{{display:false}},ticks:{{font:{{size:10}}}}}},
      y:{{grid:{{color:"#f1f5f9"}},ticks:{{stepSize:1}}}}}}}}
}});
</script>
</body>
</html>"""
