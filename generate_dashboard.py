"""Jinja2-based HTML dashboard renderer — v2 visual upgrade."""

import os
import json
from datetime import datetime

import yaml
from jinja2 import Template

from datetime import timedelta

import config

IST_OFFSET = timedelta(hours=5, minutes=30)

def _to_ist(ts_str):
    """Convert ISO timestamp string to IST string. Naive = assumed UTC, aware = already has offset."""
    if not ts_str or not isinstance(ts_str, str):
        return ts_str
    try:
        dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt + IST_OFFSET
        else:
            utc_dt = dt - dt.utcoffset()
            dt = utc_dt + IST_OFFSET
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ts_str

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Affiliates Reconciliation Dashboard — {{ close_month }}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #f0f2f5; --card: #ffffff; --border: #e2e8f0;
  --text: #1a1a2e; --muted: #718096; --subtle: #a0aec0;
  --green: #48bb78; --green-bg: #c6f6d5; --green-text: #22543d;
  --amber: #d97706; --amber-bg: #fef3c7; --amber-text: #92400e;
  --red: #f56565; --red-bg: #fed7d7; --red-text: #9b2c2c;
  --blue: #3b82f6; --blue-bg: #dbeafe; --blue-text: #1e40af;
  --purple: #8b5cf6; --purple-bg: #ede9fe; --purple-text: #6d28d9;
  --teal: #0d9488; --teal-bg: #ccfbf1; --teal-text: #0f766e;
  --rose: #e11d48; --rose-bg: #ffe4e6; --rose-text: #9f1239;
  --grey-bg: #f1f5f9; --grey-text: #64748b;
  --p-moneylion: #3b82f6; --p-amone: #8b5cf6; --p-kashkick: #0d9488;
  --p-freecash: #22c55e; --p-brigit: #f97316; --p-supermoney: #e11d48;
}
html.dark {
  --bg: #0f172a; --card: #1e293b; --border: #334155;
  --text: #e2e8f0; --muted: #94a3b8; --subtle: #64748b;
  --green: #4ade80; --green-bg: #14532d; --green-text: #86efac;
  --amber: #fbbf24; --amber-bg: #451a03; --amber-text: #fde68a;
  --red: #f87171; --red-bg: #450a0a; --red-text: #fca5a5;
  --blue: #60a5fa; --blue-bg: #1e3a5f; --blue-text: #93c5fd;
  --purple: #a78bfa; --purple-bg: #2e1065; --purple-text: #c4b5fd;
  --teal: #2dd4bf; --teal-bg: #042f2e; --teal-text: #5eead4;
  --rose: #fb7185; --rose-bg: #4c0519; --rose-text: #fda4af;
  --grey-bg: #1e293b; --grey-text: #94a3b8;
  --p-moneylion: #60a5fa; --p-amone: #a78bfa; --p-kashkick: #2dd4bf;
  --p-freecash: #4ade80; --p-brigit: #fb923c; --p-supermoney: #fb7185;
}
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:'Inter',system-ui,-apple-system,sans-serif; background:var(--bg); color:var(--text); font-size:13px; line-height:1.5; transition:background .3s,color .3s; }

/* ── Container ── */
.container { max-width:1440px; margin:0 auto; }

/* ── Header ── */
.header { background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%); color:#fff; padding:28px 36px 24px; }
.header-top { display:flex; justify-content:space-between; align-items:flex-start; }
.header h1 { font-size:20px; font-weight:800; letter-spacing:-.3px; }
.header .subtitle { color:#64748b; font-size:12px; margin-top:2px; }
.header-actions { display:flex; gap:8px; align-items:center; }
.dark-toggle { cursor:pointer; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.15); color:#94a3b8; border-radius:8px; padding:6px 14px; font-size:11px; font-weight:600; transition:.2s; font-family:inherit; }
.dark-toggle:hover { background:rgba(255,255,255,.15); color:#e2e8f0; }
.header-meta { display:flex; gap:24px; margin-top:20px; flex-wrap:wrap; align-items:flex-start; }
.header-meta .item { }
.header-meta .label { font-size:10px; text-transform:uppercase; letter-spacing:1.2px; color:#475569; font-weight:600; }
.header-meta .value { font-size:14px; font-weight:700; margin-top:1px; }
.stats-bar { display:flex; gap:8px; margin-top:20px; flex-wrap:wrap; }
.stat { padding:6px 16px; border-radius:8px; font-size:12px; font-weight:700; }
.stat-total { background:rgba(255,255,255,.06); color:#94a3b8; }
.stat-pass { background:rgba(72,187,120,.12); color:#86efac; }
.stat-fail { background:rgba(245,101,101,.12); color:#fca5a5; }
.stat-warn { background:rgba(251,191,36,.12); color:#fde68a; }
.stat-pending { background:rgba(148,163,184,.12); color:#94a3b8; }
.overall-badge { display:inline-block; padding:5px 18px; border-radius:20px; font-size:11px; font-weight:800; letter-spacing:.5px; margin-top:16px; }
.overall-green { background:rgba(72,187,120,.15); color:#86efac; }
.overall-red { background:rgba(245,101,101,.15); color:#fca5a5; }
.overall-amber { background:rgba(251,191,36,.15); color:#fde68a; }

/* ── Summary strip ── */
.summary-strip { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; padding:20px 36px; background:var(--card); border-bottom:1px solid var(--border); }
.sc { padding:18px 20px; border-radius:12px; border:1px solid var(--border); background:var(--bg); transition:transform .15s,box-shadow .15s; }
.sc:hover { transform:translateY(-2px); box-shadow:0 4px 12px rgba(0,0,0,.06); }
.sc .sc-val { font-size:24px; font-weight:800; letter-spacing:-.5px; font-variant-numeric:tabular-nums; }
.sc .sc-lbl { font-size:11px; color:var(--muted); margin-top:2px; font-weight:500; }
.sc.status-card { text-align:center; }

/* ── Body wrapper ── */
.body-wrap { background:var(--card); box-shadow:0 4px 24px rgba(0,0,0,.04); }

/* ── Navigation ── */
.nav-bar { display:flex; gap:6px; padding:14px 36px; border-bottom:1px solid var(--border); background:var(--card); position:sticky; top:0; z-index:10; flex-wrap:wrap; }
.tab-wrapper input[type="radio"] { display:none; }
.nav-tab { display:inline-flex; align-items:center; gap:6px; padding:8px 18px; border-radius:8px; font-size:12px; font-weight:600; cursor:pointer; border:1px solid var(--border); background:var(--card); color:var(--muted); transition:all .15s; font-family:inherit; }
.nav-tab:hover { background:var(--bg); color:var(--text); transform:translateY(-1px); }
.tab-dot { width:7px; height:7px; border-radius:50%; flex-shrink:0; }
.dot-green { background:var(--green); }
.dot-red { background:var(--red); animation:pulse 2s infinite; }
.dot-amber { background:var(--amber); }
.dot-grey { background:var(--subtle); }
@keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:.4;} }
#tab0:checked ~ .nav-bar label[for="tab0"],
#tab1:checked ~ .nav-bar label[for="tab1"],
#tab2:checked ~ .nav-bar label[for="tab2"],
#tab3:checked ~ .nav-bar label[for="tab3"] {
  background:#0f172a; color:#fff; border-color:#0f172a; box-shadow:0 2px 8px rgba(15,23,42,.2); }
html.dark #tab0:checked ~ .nav-bar label[for="tab0"],
html.dark #tab1:checked ~ .nav-bar label[for="tab1"],
html.dark #tab2:checked ~ .nav-bar label[for="tab2"],
html.dark #tab3:checked ~ .nav-bar label[for="tab3"] {
  background:#3b82f6; color:#fff; border-color:#3b82f6; }

/* ── Tab panels ── */
.tab-panel { display:none; padding:28px 36px; }
#tab0:checked ~ .tab-panel.p0,
#tab1:checked ~ .tab-panel.p1,
#tab2:checked ~ .tab-panel.p2,
#tab3:checked ~ .tab-panel.p3 { display:block; }

/* ── Sections ── */
.section { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:24px 28px; margin-bottom:20px; box-shadow:0 1px 3px rgba(0,0,0,.04); }
.section h2 { font-size:14px; font-weight:700; margin-bottom:14px; color:var(--text); display:flex; align-items:center; gap:8px; }
.section h2 .section-icon { width:28px; height:28px; border-radius:8px; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:800; flex-shrink:0; }
.section h3 { font-size:12px; font-weight:700; margin:16px 0 8px; color:var(--muted); text-transform:uppercase; letter-spacing:.5px; }

/* ── Tables ── */
.tbl-wrap { max-height:600px; overflow-y:auto; border:1px solid var(--border); border-radius:8px; }
table { width:100%; border-collapse:collapse; font-size:12px; }
thead { position:sticky; top:0; z-index:2; }
th { background:var(--bg); padding:10px 14px; text-align:left; font-weight:700; font-size:10px; text-transform:uppercase; letter-spacing:.5px; color:var(--muted); border-bottom:2px solid var(--border); cursor:pointer; user-select:none; white-space:nowrap; }
th.num, td.num { text-align:right; }
th .sort-ind { font-size:9px; margin-left:3px; color:var(--subtle); }
td { padding:10px 14px; border-bottom:1px solid var(--border); font-variant-numeric:tabular-nums; }
td.num { font-family:'SF Mono','Cascadia Code','Consolas',monospace; font-size:12px; }
tr:hover { background:var(--grey-bg); }
tr.grand-total { font-weight:700; background:var(--bg) !important; }
tr.grand-total td { border-top:2px solid var(--border); }
tr.pending-row { opacity:.65; }
.cfg-tbl { width:auto; }
.cfg-tbl th, .cfg-tbl td { padding:8px 16px; }

/* ── Badges ── */
.badge { display:inline-block; padding:3px 12px; border-radius:20px; font-size:10px; font-weight:800; letter-spacing:.3px; }
.badge.GREEN, .badge.PASS, .badge.SUCCESS { background:var(--green-bg); color:var(--green-text); }
.badge.AMBER, .badge.WARN, .badge.PARTIAL { background:var(--amber-bg); color:var(--amber-text); }
.badge.RED, .badge.FAIL, .badge.FAILED { background:var(--red-bg); color:var(--red-text); }
.badge.GREY, .badge.PENDING { background:var(--grey-bg); color:var(--grey-text); }
.var-pos { color:var(--green-text); font-weight:600; }
.var-neg { color:var(--red-text); font-weight:600; }

/* ── Note box ── */
.note-box { background:var(--blue-bg); border-left:4px solid var(--blue); padding:14px 18px; margin-bottom:18px; font-size:12px; border-radius:0 8px 8px 0; color:var(--blue-text); }

/* ── Filter bar ── */
.filter-bar { display:flex; gap:12px; align-items:center; flex-wrap:wrap; margin-bottom:14px; padding:12px 16px; background:var(--bg); border-radius:10px; border:1px solid var(--border); }
.filter-bar label { font-size:11px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.3px; }
.filter-bar select, .filter-bar input[type="checkbox"] { font-size:12px; font-family:inherit; }
.filter-bar select { padding:5px 10px; border:1px solid var(--border); border-radius:6px; background:var(--card); color:var(--text); }
.filter-bar button { padding:5px 14px; font-size:11px; font-weight:600; border:1px solid var(--border); border-radius:6px; background:var(--card); color:var(--text); cursor:pointer; font-family:inherit; transition:.15s; }
.filter-bar button:hover { background:var(--bg); transform:translateY(-1px); }
.filter-bar .status-checks { display:flex; gap:10px; align-items:center; }
.filter-bar .status-checks label { display:flex; align-items:center; gap:4px; font-weight:500; text-transform:none; letter-spacing:0; }

/* ── Details / Accordion ── */
details { margin-bottom:8px; }
summary { cursor:pointer; font-weight:600; padding:8px 0; color:var(--text); }

/* ── Comment inputs ── */
td input.comment-input { width:100%; border:1px solid transparent; background:transparent; font-size:12px; padding:4px 8px; border-radius:4px; font-family:inherit; color:var(--text); }
td input.comment-input:focus { border-color:var(--blue); outline:none; background:var(--card); box-shadow:0 0 0 3px rgba(59,130,246,.15); }

/* ── Health cards ── */
.health-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:12px; margin-bottom:20px; }
.health-card { padding:18px 20px; border-radius:12px; border:1px solid var(--border); text-align:center; background:var(--bg); transition:transform .15s; }
.health-card:hover { transform:translateY(-2px); }
.health-card .val { font-size:32px; font-weight:800; letter-spacing:-.5px; }
.health-card .lbl { font-size:10px; color:var(--muted); margin-top:4px; font-weight:600; text-transform:uppercase; letter-spacing:.5px; }

/* ── Partner dots ── */
.partner-dot { display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; vertical-align:middle; }
.partner-dot.moneylion { background:var(--p-moneylion); }
.partner-dot.amone { background:var(--p-amone); }
.partner-dot.kashkick { background:var(--p-kashkick); }
.partner-dot.freecash { background:var(--p-freecash); }
.partner-dot.brigit { background:var(--p-brigit); }
.partner-dot.supermoney { background:var(--p-supermoney); }

/* ── Partner row tinting ── */
tr[data-partner="moneylion"]:not(:hover) { background:rgba(59,130,246,.04); }
tr[data-partner="amone"]:not(:hover) { background:rgba(139,92,246,.04); }
tr[data-partner="kashkick"]:not(:hover) { background:rgba(13,148,136,.04); }
tr[data-partner="freecash"]:not(:hover) { background:rgba(34,197,94,.04); }
tr[data-partner="brigit"]:not(:hover) { background:rgba(249,115,22,.04); }
tr[data-partner="supermoney"]:not(:hover) { background:rgba(225,29,72,.04); }
html.dark tr[data-partner="moneylion"]:not(:hover) { background:rgba(96,165,250,.06); }
html.dark tr[data-partner="amone"]:not(:hover) { background:rgba(167,139,250,.06); }
html.dark tr[data-partner="kashkick"]:not(:hover) { background:rgba(45,212,191,.06); }
html.dark tr[data-partner="freecash"]:not(:hover) { background:rgba(74,222,128,.06); }
html.dark tr[data-partner="brigit"]:not(:hover) { background:rgba(251,146,60,.06); }
html.dark tr[data-partner="supermoney"]:not(:hover) { background:rgba(251,113,133,.06); }
tr.grand-total { background:var(--bg) !important; }
html.dark tr.grand-total { background:#0f172a !important; }
tr.partner-highlight { outline:2px solid var(--blue); outline-offset:-1px; border-radius:2px; }

/* ── Mismatch row tinting ── */
tr[data-status="RED"] td:last-child .badge { animation:pulse 2s infinite; }

/* ── Footer ── */
.footer { text-align:center; padding:18px 36px; font-size:11px; color:var(--subtle); background:var(--card); border-top:1px solid var(--border); }

/* ── Dark mode overrides ── */
html.dark th { background:#0f172a; border-bottom-color:#334155; }
html.dark tr:hover { background:rgba(255,255,255,.03); }
html.dark .filter-bar { background:#0f172a; border-color:#334155; }
html.dark .filter-bar select { background:#1e293b; color:var(--text); border-color:#334155; }
html.dark .filter-bar button { background:#1e293b; color:var(--text); border-color:#334155; }
html.dark .note-box { background:rgba(59,130,246,.1); border-left-color:var(--blue); color:var(--blue-text); }
html.dark td { border-bottom-color:#1e293b; }
html.dark input.comment-input { color:var(--text); }
html.dark input.comment-input:focus { background:#0f172a; border-color:var(--blue); }
html.dark details summary { color:var(--text); }
html.dark pre { background:var(--red-bg) !important; color:var(--red-text); }
html.dark .section { background:var(--card); border-color:var(--border); box-shadow:none; }
html.dark .sc { background:#0f172a; border-color:#334155; }
html.dark .sc:hover { box-shadow:0 4px 12px rgba(0,0,0,.3); }
html.dark .health-card { background:#0f172a; border-color:#334155; }
</style>
</head>
<body>

<div class="container">

<!-- ══ HEADER ══ -->
<div class="header">
  <div class="header-top">
    <div>
      <h1>Affiliates Reconciliation Dashboard</h1>
      <div class="subtitle">Bright Money — Partner Payout & Invoice Reconciliation</div>
    </div>
    <div class="header-actions">
      <button class="dark-toggle" onclick="toggleDark()">Dark Mode</button>
    </div>
  </div>
  <div class="header-meta">
    <div class="item"><div class="label">Close Month</div><div class="value">{{ close_month }}</div></div>
    <div class="item"><div class="label">Generated</div><div class="value">{{ generated_at }} IST</div></div>
    <div class="item"><div class="label">Data Pulled</div><div class="value">{{ pull_timestamp_ist or '—' }} IST</div></div>
    {% if l1 %}
    <div class="item"><div class="label">Overall Status</div><div class="value">
      {% set red_count = l1.monthly_detail|selectattr('status','equalto','RED')|list|length %}
      {% set amber_count = l1.monthly_detail|selectattr('status','equalto','AMBER')|list|length %}
      {% set green_count = l1.monthly_detail|selectattr('status','equalto','GREEN')|list|length %}
      {% if red_count > 0 %}<span class="overall-badge overall-red">{{ red_count }} VARIANCE ISSUES</span>
      {% elif amber_count > 0 %}<span class="overall-badge overall-amber">{{ amber_count }} WARNINGS</span>
      {% else %}<span class="overall-badge overall-green">ALL RECONCILED</span>{% endif %}
    </div></div>
    {% endif %}
  </div>
  {% if l1 %}
  <div class="stats-bar">
    <span class="stat stat-total">{{ l1.monthly_detail|length }} Total Rows</span>
    <span class="stat stat-pass">{{ l1.monthly_detail|selectattr('status','equalto','GREEN')|list|length }} Green</span>
    <span class="stat stat-warn">{{ l1.monthly_detail|selectattr('status','equalto','AMBER')|list|length }} Amber</span>
    <span class="stat stat-fail">{{ l1.monthly_detail|selectattr('status','equalto','RED')|list|length }} Red</span>
    <span class="stat stat-pending">{{ l1.monthly_detail|selectattr('status','equalto','GREY')|list|length }} Grey</span>
  </div>
  {% endif %}
</div>

<!-- ══ SUMMARY STRIP ══ -->
{% if l3 %}
<div class="summary-strip">
  <div class="sc">
    <div class="sc-val">${{ "{:,.0f}".format(l3.grand_total.total_billed) }}</div>
    <div class="sc-lbl">Total Billed</div>
  </div>
  <div class="sc">
    <div class="sc-val" style="color:var(--green)">${{ "{:,.0f}".format(l3.grand_total.total_received) }}</div>
    <div class="sc-lbl">Total Received</div>
  </div>
  <div class="sc">
    <div class="sc-val" style="color:var(--amber)">${{ "{:,.0f}".format(l3.grand_total.yet_to_receive) }}</div>
    <div class="sc-lbl">Yet to Receive</div>
  </div>
  <div class="sc status-card">
    {% set g = l3.collected|selectattr('net_status','equalto','Low')|list|length %}
    {% set a = l3.collected|selectattr('net_status','equalto','Medium')|list|length %}
    {% set r = l3.collected|selectattr('net_status','equalto','High')|list|length %}
    {% set p = l3.yet_to_receive|length %}
    <div class="sc-val">
      <span style="color:var(--green)">{{ g }}</span>
      <span style="color:var(--subtle);font-size:16px">/</span>
      <span style="color:var(--amber)">{{ a }}</span>
      <span style="color:var(--subtle);font-size:16px">/</span>
      <span style="color:var(--red)">{{ r }}</span>
      <span style="color:var(--subtle);font-size:16px">/</span>
      <span style="color:var(--subtle)">{{ p }}</span>
    </div>
    <div class="sc-lbl">Low / Medium / High / Pending</div>
  </div>
</div>
{% endif %}

<!-- ══ NAV + TABS ══ -->
<div class="body-wrap">
<div class="tab-wrapper">
  <input type="radio" id="tab0" name="tabs" checked>
  <input type="radio" id="tab1" name="tabs">
  <input type="radio" id="tab2" name="tabs">
  <input type="radio" id="tab3" name="tabs">
  <div class="nav-bar">
    <label for="tab0" class="nav-tab"><span class="tab-dot {% if validation and validation.overall_status == 'PASS' %}dot-green{% elif validation and validation.overall_status == 'WARN' %}dot-amber{% else %}dot-grey{% endif %}"></span>Inputs & Validation</label>
    <label for="tab1" class="nav-tab"><span class="tab-dot {% if l1 %}{% if l1.overall_status == 'GREEN' %}dot-green{% elif l1.overall_status == 'AMBER' %}dot-amber{% else %}dot-red{% endif %}{% else %}dot-grey{% endif %}"></span>Payout vs Invoice</label>
    <label for="tab2" class="nav-tab"><span class="tab-dot {% if l3 %}{% if l3.overall_status == 'GREEN' %}dot-green{% elif l3.overall_status == 'AMBER' %}dot-amber{% else %}dot-red{% endif %}{% else %}dot-grey{% endif %}"></span>Invoice vs Cash (Live)</label>
    <label for="tab3" class="nav-tab"><span class="tab-dot {% if health_log %}{% if health_log[-1].status == 'SUCCESS' %}dot-green{% elif health_log[-1].status == 'PARTIAL' %}dot-amber{% else %}dot-red{% endif %}{% else %}dot-grey{% endif %}"></span>Health</label>
  </div>

  <!-- ══ TAB 0 — Inputs & Validation ══ -->
  <div class="tab-panel p0">
    <div class="section"><h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> Data Source Inventory</h2>
      <div class="tbl-wrap"><table><thead><tr><th>Source</th><th>File</th><th>Pull Method</th><th class="num">Rows</th><th>Month Range</th><th>Status</th></tr></thead>
        <tbody>{% for f in validation.files %}<tr><td>{{ f.label }}</td><td><code style="font-size:11px;color:var(--muted)">{{ f.file }}</code></td><td>{{ f.pull_method }}</td><td class="num">{{ f.row_count }}</td><td>{{ f.month_range.min }} &rarr; {{ f.month_range.max }}</td><td><span class="badge {{ f.status }}">{{ f.status }}</span></td></tr>{% endfor %}</tbody></table></div>
    </div>
    {% if validation.files[0].columns %}
    <div class="section"><h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">2</span> Column-Level Validation</h2>
      {% for f in validation.files %}{% if f.columns %}
      <details><summary>{{ f.label }} — {{ f.file }} ({{ f.columns|length }} columns)</summary>
        <div class="tbl-wrap" style="margin-top:8px"><table><thead><tr><th>Column</th><th>Dtype</th><th class="num">Nulls</th><th class="num">Null %</th><th>Min</th><th>Max</th><th>Sample Values</th></tr></thead>
          <tbody>{% for c in f.columns %}<tr><td><code style="font-size:11px">{{ c.name }}</code></td><td>{{ c.dtype }}</td><td class="num">{{ c.nulls }}</td><td class="num">{{ c.null_pct }}%</td><td>{{ c.min if c.min is not none else '—' }}</td><td>{{ c.max if c.max is not none else '—' }}</td><td style="color:var(--muted);font-size:11px">{{ c.sample_values|join(', ') }}</td></tr>{% endfor %}</tbody></table></div>
      </details>{% endif %}{% endfor %}
    </div>
    {% endif %}
    <div class="section"><h2><span class="section-icon" style="background:var(--teal-bg);color:var(--teal-text);">3</span> Partner Coverage</h2>
      <div class="tbl-wrap"><table><thead><tr><th>Partner</th><th>In Q3870</th><th class="num">Q3870 Rows</th><th>Status</th></tr></thead>
        <tbody>{% for p in validation.partner_coverage %}<tr><td><span class="partner-dot {{ p.partner }}"></span>{{ p.display_name }}</td><td style="font-size:15px">{{ '&#10003;' if p.in_q3870 else '&#10007;' }}</td><td class="num">{{ p.q3870_rows }}</td><td><span class="badge {{ p.status }}">{{ p.status }}</span></td></tr>{% endfor %}</tbody></table></div>
    </div>
    <div class="section"><h2><span class="section-icon" style="background:var(--amber-bg);color:var(--amber-text);">4</span> Partner Configuration</h2>
      <table class="cfg-tbl"><thead><tr><th>Partner</th><th>Cycles</th><th>Payment Term</th><th>Accel. Charge</th><th>Q3870 Name</th><th>GSheet Name</th></tr></thead>
        <tbody>{% for p, cfg in partner_config.items() %}<tr><td><span class="partner-dot {{ p }}"></span>{{ partner_display[p] }}</td><td>{{ cfg.cycles }}</td><td>{{ cfg.payment_term }} days</td><td>{{ cfg.accel_charge }}</td><td><code style="font-size:11px">{{ cfg.q3870_name }}</code></td><td><code style="font-size:11px">{{ cfg.gsheet_name }}</code></td></tr>{% endfor %}</tbody></table>
    </div>
    <div class="section"><h2><span class="section-icon" style="background:var(--rose-bg);color:var(--rose-text);">5</span> Variance Thresholds</h2>
      <h3>Payout vs Invoice</h3>
      <table class="cfg-tbl"><thead><tr><th>Partners</th><th><span class="badge GREEN">GREEN</span></th><th><span class="badge AMBER">AMBER</span></th><th><span class="badge RED">RED</span></th></tr></thead>
        <tbody><tr><td>MoneyLion &amp; AmONE</td><td>abs &lt; 5%</td><td>5–10%</td><td>&gt; 10%</td></tr>
        <tr><td>Generic</td><td>abs &lt; 2%</td><td>2–5%</td><td>&ge; 5%</td></tr></tbody></table>
      <h3>Invoice vs Cash (Live)</h3>
      <table class="cfg-tbl"><thead><tr><th>Condition</th><th>Status</th></tr></thead>
        <tbody><tr><td>abs(delta %) &lt; 2%</td><td style="color:var(--green-text);font-weight:700">Low</td></tr>
        <tr><td>abs(delta %) 2–5%</td><td style="color:var(--amber-text);font-weight:700">Medium</td></tr>
        <tr><td>abs(delta %) &ge; 5%</td><td style="color:var(--red-text);font-weight:700">High</td></tr></tbody></table>
    </div>
    <div class="section"><h2><span class="section-icon" style="background:var(--grey-bg);color:var(--grey-text);">6</span> Cleaning Log</h2>
      <div class="tbl-wrap"><table><thead><tr><th>#</th><th>Action</th><th>Detail</th><th>Status</th></tr></thead>
        <tbody>{% for e in validation.cleaning_log %}<tr><td>{{ loop.index }}</td><td><strong>{{ e.action }}</strong></td><td style="color:var(--muted)">{{ e.detail }}</td><td><span class="badge {{ e.status }}">{{ e.status }}</span></td></tr>{% endfor %}</tbody></table></div>
    </div>
  </div>

  <!-- ══ TAB 1 — Payout vs Invoice ══ -->
  <div class="tab-panel p1">
  {% if l1 %}
    <div class="section"><h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> Monthly Reconciliation</h2>
      <div class="filter-bar"><label>Partner:</label>
        <select id="f1m-partner" multiple size="1" onchange="applyFilter('t1m')"><option value="ALL" selected>All</option>{% for p in l1.cumulative %}<option value="{{ p.partner }}">{{ p.display_name }}</option>{% endfor %}</select>
        <label>Month:</label>
        <select id="f1m-month-from" onchange="applyFilter('t1m')"><option value="">From</option>{% for m in l1_months %}<option>{{ m }}</option>{% endfor %}</select>
        <select id="f1m-month-to" onchange="applyFilter('t1m')"><option value="">To</option>{% for m in l1_months|reverse %}<option>{{ m }}</option>{% endfor %}</select>
        <div class="status-checks">
          <label><input type="checkbox" value="GREEN" checked onchange="applyFilter('t1m')">GREEN</label>
          <label><input type="checkbox" value="AMBER" checked onchange="applyFilter('t1m')">AMBER</label>
          <label><input type="checkbox" value="RED" checked onchange="applyFilter('t1m')">RED</label>
          <label><input type="checkbox" value="GREY" checked onchange="applyFilter('t1m')">GREY</label>
        </div><button onclick="resetFilter('t1m')">Reset</button></div>
      <div class="tbl-wrap"><table id="t1m">
        <thead><tr><th onclick="sortTable('t1m',0)">Month <span class="sort-ind"></span></th><th onclick="sortTable('t1m',1)">Partner</th><th onclick="sortTable('t1m',2)">Cycle</th><th class="num" onclick="sortTable('t1m',3)">Invoice $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1m',4)">Reports $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1m',5)">Delta $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1m',6)">Delta % <span class="sort-ind"></span></th><th onclick="sortTable('t1m',7)">Status</th><th>Comments</th></tr></thead>
        <tbody>{% for r in l1.monthly_detail %}<tr data-partner="{{ r.partner }}" data-month="{{ r.month }}" data-status="{{ r.status }}"><td>{{ r.month }}</td><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td>{{ r.cycle }}</td><td class="num">${{ "{:,.2f}".format(r.invoice_amount if r.invoice_amount is defined else r.reports_amount) }}</td><td class="num">${{ "{:,.2f}".format(r.reports_amount) }}</td><td class="num {{ 'var-pos' if r.delta >= 0 else 'var-neg' }}">${{ "{:,.2f}".format(r.delta) }}</td><td class="num {{ 'var-pos' if r.delta_pct is not none and r.delta_pct >= 0 else 'var-neg' }}">{{ "{:.2f}%".format(r.delta_pct) if r.delta_pct is not none else '—' }}</td><td><span class="badge {{ r.status }}">{{ r.status }}</span></td><td><input class="comment-input" type="text" placeholder="Add note..."></td></tr>{% endfor %}</tbody>
      </table></div></div>
    <div class="section"><h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">2</span> Cumulative To-Date</h2>
      <div class="tbl-wrap"><table id="t1c">
        <thead><tr><th onclick="sortTable('t1c',0)">Partner <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',1)">Total Invoice $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',2)">Total Payout $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',3)">Delta $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',4)">Delta % <span class="sort-ind"></span></th><th onclick="sortTable('t1c',5)">Status</th><th class="num" onclick="sortTable('t1c',6)"># Months</th><th>Comments</th></tr></thead>
        <tbody>{% for r in l1.cumulative %}<tr data-partner="{{ r.partner }}" data-status="{{ r.status }}"><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td class="num">${{ "{:,.2f}".format(r.total_invoice) }}</td><td class="num">${{ "{:,.2f}".format(r.total_reports) }}</td><td class="num {{ 'var-pos' if r.total_delta >= 0 else 'var-neg' }}">${{ "{:,.2f}".format(r.total_delta) }}</td><td class="num">{{ "{:.2f}%".format(r.delta_pct) if r.delta_pct is not none else '—' }}</td><td><span class="badge {{ r.status }}">{{ r.status }}</span></td><td class="num">{{ r.month_count }}</td><td><input class="comment-input" type="text" placeholder="Add note..."></td></tr>{% endfor %}
        {% if l1.grand_total %}<tr class="grand-total"><td><strong>{{ l1.grand_total.display_name }}</strong></td><td class="num">${{ "{:,.2f}".format(l1.grand_total.total_invoice) }}</td><td class="num">${{ "{:,.2f}".format(l1.grand_total.total_reports) }}</td><td class="num">${{ "{:,.2f}".format(l1.grand_total.total_delta) }}</td><td class="num">{{ "{:.2f}%".format(l1.grand_total.delta_pct) if l1.grand_total.delta_pct is not none else '—' }}</td><td></td><td class="num">{{ l1.grand_total.month_count }}</td><td></td></tr>{% endif %}</tbody>
      </table></div></div>
  {% else %}<div class="section"><p style="color:var(--muted)">Payout vs Invoice data not available.</p></div>{% endif %}
  </div>

  <!-- ══ TAB 2 — Invoice vs Cash (Live) ══ -->
  <div class="tab-panel p2">
  {% if l3 %}
    <div class="note-box"><strong>Live Data Source:</strong> <a href="https://docs.google.com/spreadsheets/d/1EJPJubKrClHduO-_EgK-6Sh53dTB7Mmf0o5NHgxVsnQ/edit?gid=1688298716#gid=1688298716" target="_blank" style="color:var(--green-text);font-weight:600">Google Sheet — New R : finance</a>. Pulled: {{ l3.generated_at_ist }} IST. &nbsp;|&nbsp; Delta = Received - Invoiced. &nbsp;|&nbsp; <span style="color:var(--green-text)">GREEN</span> = Received &ge; Invoiced, <span style="color:var(--red-text)">RED</span> = shortfall. &nbsp;|&nbsp; Status: <strong>Low</strong> &lt;2%, <strong>Medium</strong> 2–5%, <strong>High</strong> &ge;5%.</div>

    <div class="section"><h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> Cumulative Collection Summary</h2>
      <div class="tbl-wrap"><table id="t3cum">
        <thead><tr><th onclick="sortTable('t3cum',0)">Partner <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3cum',1)">Total Billed $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3cum',2)">Total Received $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3cum',3)">Yet to Receive $ <span class="sort-ind"></span></th><th>Expected Collection</th><th class="num" onclick="sortTable('t3cum',5)">Net Delta $ <span class="sort-ind"></span></th><th onclick="sortTable('t3cum',6)">Payment Term</th></tr></thead>
        <tbody>{% for r in l3.cumulative %}<tr data-partner="{{ r.partner }}"><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td class="num">${{ "{:,.2f}".format(r.total_billed) }}</td><td class="num">${{ "{:,.2f}".format(r.total_received) }}</td><td class="num">${{ "{:,.2f}".format(r.yet_to_receive) }}</td><td style="font-size:11px;color:var(--muted)">{% if r.yet_to_receive_details %}{% for d in r.yet_to_receive_details %}${{ "{:,.0f}".format(d.amount) }} ({{ d.payout_month }}) &rarr; {{ d.expected_collection or '—' }}{% if not loop.last %}<br>{% endif %}{% endfor %}{% else %}—{% endif %}</td><td class="num" style="font-weight:700; color:{{ 'var(--red-text)' if r.net_delta < 0 else 'var(--green-text)' }}">${{ "{:,.2f}".format(r.net_delta) }}</td><td>{{ r.payment_term }} days</td></tr>{% endfor %}
        {% if l3.grand_total %}<tr class="grand-total"><td><strong>{{ l3.grand_total.display_name }}</strong></td><td class="num">${{ "{:,.2f}".format(l3.grand_total.total_billed) }}</td><td class="num">${{ "{:,.2f}".format(l3.grand_total.total_received) }}</td><td class="num">${{ "{:,.2f}".format(l3.grand_total.yet_to_receive) }}</td><td></td><td class="num" style="font-weight:800; color:{{ 'var(--red-text)' if l3.grand_total.net_delta < 0 else 'var(--green-text)' }}">${{ "{:,.2f}".format(l3.grand_total.net_delta) }}</td><td></td></tr>{% endif %}</tbody>
      </table></div></div>

    <div class="section"><h2><span class="section-icon" style="background:var(--green-bg);color:var(--green-text);">2</span> Invoice to Cash Reconciliation</h2>
      <div class="filter-bar"><label>Partner:</label><select id="f3c2-partner" multiple size="1" onchange="applyFilter('t3c2')"><option value="ALL" selected>All</option>{% for p in l3.cumulative %}<option value="{{ p.partner }}">{{ p.display_name }}</option>{% endfor %}</select>
        <label>Collection Month:</label><select id="f3c2-month-from" onchange="applyFilter('t3c2')"><option value="">From</option>{% for m in l3_coll_months %}<option>{{ m }}</option>{% endfor %}</select><select id="f3c2-month-to" onchange="applyFilter('t3c2')"><option value="">To</option>{% for m in l3_coll_months|reverse %}<option>{{ m }}</option>{% endfor %}</select>
        <div class="status-checks"><label><input type="checkbox" value="Low" checked onchange="applyFilter('t3c2')">Low</label><label><input type="checkbox" value="Medium" checked onchange="applyFilter('t3c2')">Medium</label><label><input type="checkbox" value="High" checked onchange="applyFilter('t3c2')">High</label></div>
        <button onclick="resetFilter('t3c2')">Reset</button></div>
      <div class="tbl-wrap"><table id="t3c2">
        <thead><tr><th onclick="sortTable('t3c2',0)">Collection Month <span class="sort-ind"></span></th><th onclick="sortTable('t3c2',1)">Partner</th><th onclick="sortTable('t3c2',2)">Payout Month</th><th onclick="sortTable('t3c2',3)">Cycle</th><th class="num" onclick="sortTable('t3c2',4)">Invoice $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3c2',4)">Received $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3c2',5)">Delta $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3c2',6)">Net Delta $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3c2',7)">Net Delta % <span class="sort-ind"></span></th><th onclick="sortTable('t3c2',8)">Status</th><th>Comments</th></tr></thead>
        <tbody>{% for r in l3.collected %}<tr data-partner="{{ r.partner }}" data-month="{{ r.collection_month }}" data-status="{{ r.net_status }}"><td>{{ r.collection_month }}</td><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td>{{ r.payout_month }}</td><td style="font-weight:600">{{ r.cycle or "—" }}</td><td class="num">${{ "{:,.2f}".format(r.billed) }}</td><td class="num">${{ "{:,.2f}".format(r.received) }}</td><td class="num" style="color:{{ 'var(--green-text)' if r.color == 'green' else 'var(--red-text)' }};font-weight:600">${{ "{:,.2f}".format(r.delta) }}</td><td class="num" style="color:{{ 'var(--red-text)' if r.net_delta < 0 else 'var(--green-text)' }};font-weight:700">${{ "{:,.2f}".format(r.net_delta) }}</td><td class="num" style="color:{{ 'var(--red-text)' if r.net_delta < 0 else 'var(--green-text)' }};font-weight:600">{{ "{:.2f}%".format(r.net_delta_pct) if r.net_delta_pct is not none else '—' }}</td><td>{% if r.product_signoff and r.product_signoff|lower == 'yes' %}<span style="color:var(--green-text);font-weight:700">{{ r.net_status }}</span> <span class="badge SUCCESS" style="font-size:9px">Signed Off</span>{% else %}<span style="color:{{ 'var(--red-text)' if r.net_delta < 0 else 'var(--green-text)' }}; font-weight:700">{{ r.net_status }}</span>{% endif %}</td><td style="font-size:11px;color:var(--muted);max-width:200px">{{ r.comments or '' }}</td></tr>{% endfor %}</tbody>
      </table></div></div>

    <div class="section"><h2><span class="section-icon" style="background:var(--amber-bg);color:var(--amber-text);">3</span> Yet to Receive</h2>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px;">Invoices where cash has not yet been collected from partner.</p>
      {% if l3.yet_to_receive %}
      {% set ytr_total = l3.yet_to_receive|sum(attribute='billed') %}
      <div class="filter-bar"><label>Partner:</label><select id="f3y-partner" onchange="applyFilter('t3y')"><option value="ALL" selected>All</option>{% for p in l3.cumulative %}<option value="{{ p.partner }}">{{ p.display_name }}</option>{% endfor %}</select><button onclick="resetFilter('t3y')">Reset</button></div>
      <div class="tbl-wrap"><table id="t3y">
        <thead><tr><th onclick="sortTable('t3y',0)">Partner</th><th onclick="sortTable('t3y',1)">Payout Month <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t3y',2)">Invoice $</th><th>Status</th><th onclick="sortTable('t3y',4)">Expected Collection</th></tr></thead>
        <tbody>{% for r in l3.yet_to_receive %}<tr data-partner="{{ r.partner }}" class="pending-row"><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td>{{ r.payout_month or '—' }}</td><td class="num">${{ "{:,.2f}".format(r.billed) }}</td><td><span class="badge PENDING">PENDING</span></td><td>{{ r.expected_collection or '—' }}</td></tr>{% endfor %}
        <tr class="grand-total"><td><strong>Total</strong></td><td></td><td class="num"><strong>${{ "{:,.2f}".format(ytr_total) }}</strong></td><td></td><td></td></tr></tbody>
      </table></div>
      {% else %}<p style="color:var(--muted);">All invoices collected.</p>{% endif %}
    </div>

  {% else %}<div class="section"><p style="color:var(--muted);">Google Sheet data not available. Ensure google_sa_key.json is in place.</p></div>{% endif %}
  </div>

  <!-- ══ TAB 3 — Health ══ -->
  <div class="tab-panel p3">
    <div class="section"><h2><span class="section-icon" style="background:var(--teal-bg);color:var(--teal-text);">1</span> Pipeline Health</h2>
      {% if health_log %}
      {% set last = health_log[-1] %}
      {% set success_count = health_log|selectattr('status', 'equalto', 'SUCCESS')|list|length %}
      {% set fail_count = health_log|selectattr('status', 'equalto', 'FAILED')|list|length %}
      {% set partial_count = health_log|selectattr('status', 'equalto', 'PARTIAL')|list|length %}
      <div class="health-grid">
        <div class="health-card"><div class="val" style="color:var(--blue)">{{ health_log|length }}</div><div class="lbl">Total Runs</div></div>
        <div class="health-card"><div class="val" style="color:var(--green)">{{ success_count }}</div><div class="lbl">Successful</div></div>
        <div class="health-card"><div class="val" style="color:var(--red)">{{ fail_count }}</div><div class="lbl">Failed</div></div>
        <div class="health-card"><div class="val" style="color:var(--amber)">{{ partial_count }}</div><div class="lbl">Partial</div></div>
        <div class="health-card"><div class="val">{{ last.duration_seconds }}s</div><div class="lbl">Last Duration</div></div>
      </div>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px;">Last run: <strong>{{ last.timestamp_ist }} IST</strong> &mdash; <span class="badge {{ last.status }}">{{ last.status }}</span></p>
      {% else %}
      <p style="color:var(--muted);">No health data yet. Run the pipeline at least once.</p>
      {% endif %}
    </div>

    {% if health_log %}
    <div class="section"><h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">2</span> Run History (last {{ health_log|length }} runs)</h2>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Timestamp (IST)</th><th>Close Month</th><th>Status</th><th>Data Pull</th><th>Validation</th><th>Payout vs Invoice</th><th>Invoice vs Cash</th><th>Dashboard</th><th class="num">Duration</th><th>Errors</th></tr></thead>
        <tbody>{% for h in health_log|reverse %}<tr{% if h.status == 'FAILED' %} style="background:var(--red-bg)"{% endif %}>
          <td>{{ h.timestamp_ist }} IST</td>
          <td>{{ h.close_month }}</td>
          <td><span class="badge {{ h.status }}">{{ h.status }}</span></td>
          <td>{{ h.steps.data_pull if h.steps.data_pull is defined else '—' }}</td>
          <td>{{ h.steps.validation if h.steps.validation is defined else '—' }}</td>
          <td>{{ h.steps.payout_vs_invoice if h.steps.payout_vs_invoice is defined else '—' }}</td>
          <td>{{ h.steps.invoice_vs_cash_live if h.steps.invoice_vs_cash_live is defined else '—' }}</td>
          <td>{{ h.steps.dashboard_render if h.steps.dashboard_render is defined else '—' }}</td>
          <td class="num">{{ h.duration_seconds }}s</td>
          <td>{% if h.errors and h.errors|length > 0 %}<details><summary style="color:var(--red);cursor:pointer;font-size:12px">{{ h.errors|length }} error(s)</summary>{% for e in h.errors %}<pre style="background:var(--red-bg);color:var(--red-text);padding:10px;border-radius:6px;font-size:11px;overflow-x:auto;margin-top:6px;">{{ e[:500] }}</pre>{% endfor %}</details>{% else %}<span style="color:var(--green)">&#10003;</span>{% endif %}</td>
        </tr>{% endfor %}</tbody>
      </table></div>
    </div>
    {% endif %}

    <div class="section"><h2><span class="section-icon" style="background:var(--rose-bg);color:var(--rose-text);">3</span> Email Report History</h2>
      {% if email_log %}
      <div class="tbl-wrap"><table>
        <thead><tr><th>Timestamp (IST)</th><th>Status</th><th>Recipients</th><th class="num">Duration</th><th>Error</th></tr></thead>
        <tbody>{% for e in email_log|reverse %}<tr{% if e.status == 'FAILED' %} style="background:var(--red-bg)"{% endif %}>
          <td>{{ e.timestamp_ist }}</td>
          <td><span class="badge {{ e.status }}">{{ e.status }}</span></td>
          <td style="font-size:11px">{{ e.recipients|join(', ') if e.recipients else '—' }}</td>
          <td class="num">{{ e.duration_seconds }}s</td>
          <td>{% if e.error %}<details><summary style="color:var(--red);cursor:pointer;font-size:12px">View error</summary><pre style="background:var(--red-bg);color:var(--red-text);padding:8px;border-radius:6px;font-size:11px;overflow-x:auto;margin-top:6px;">{{ e.error[:500] }}</pre></details>{% else %}<span style="color:var(--green)">&#10003;</span>{% endif %}</td>
        </tr>{% endfor %}</tbody>
      </table></div>
      {% else %}<p style="color:var(--muted)">No email reports sent yet.</p>{% endif %}
    </div>

    <div class="section"><h2><span class="section-icon" style="background:var(--grey-bg);color:var(--grey-text);">4</span> Refresh Schedule</h2>
      <div class="note-box">Dashboard refreshes daily at <strong>9:00 AM IST</strong> (3:30 AM UTC) via cron job. Slack alerts are sent on failure.</div>
    </div>
  </div>

</div><!-- /tab-wrapper -->
</div><!-- /body-wrap -->

<div class="footer">Data pulled: {{ pull_timestamp_ist or '—' }} IST &nbsp;&bull;&nbsp; Dashboard generated: {{ generated_at }} IST &nbsp;&bull;&nbsp; Bright Money Affiliates Recon</div>

</div><!-- /container -->

<script>
function applyFilter(tableId) {
  var tbl = document.getElementById(tableId); if (!tbl) return;
  var rows = tbl.querySelectorAll('tbody tr:not(.grand-total)');
  var fb = tbl.closest('.section').querySelector('.filter-bar'); if (!fb) return;
  var pSel = fb.querySelector('select[id$="-partner"]');
  var pVals = [];
  if (pSel) { for (var o of pSel.selectedOptions) pVals.push(o.value); if (pVals.includes('ALL') || pVals.length === 0) pVals = ['ALL']; } else { pVals = ['ALL']; }
  var mFrom = fb.querySelector('select[id$="-month-from"]'), mTo = fb.querySelector('select[id$="-month-to"]');
  var monthFrom = mFrom ? mFrom.value : '', monthTo = mTo ? mTo.value : '';
  var checks = fb.querySelectorAll('.status-checks input[type="checkbox"]');
  var statuses = []; checks.forEach(function(c) { if (c.checked) statuses.push(c.value); });
  rows.forEach(function(r) {
    var show = true, rp = r.getAttribute('data-partner'), rm = r.getAttribute('data-month'), rs = r.getAttribute('data-status');
    if (!pVals.includes('ALL') && rp && !pVals.includes(rp)) show = false;
    if (monthFrom && rm && rm < monthFrom) show = false;
    if (monthTo && rm && rm > monthTo) show = false;
    if (statuses.length > 0 && rs && !statuses.includes(rs)) show = false;
    r.style.display = show ? '' : 'none';
  });
}
function resetFilter(tableId) {
  var tbl = document.getElementById(tableId); if (!tbl) return;
  var fb = tbl.closest('.section').querySelector('.filter-bar'); if (!fb) return;
  fb.querySelectorAll('select').forEach(function(s) { for (var o of s.options) o.selected = (o.value === 'ALL' || o.value === ''); });
  fb.querySelectorAll('input[type="checkbox"]').forEach(function(c) { c.checked = true; });
  applyFilter(tableId);
}
var sortState = {};
function sortTable(tableId, colIdx) {
  var tbl = document.getElementById(tableId); if (!tbl) return;
  var key = tableId + '-' + colIdx, dir = (sortState[key] === 'asc') ? 'desc' : 'asc'; sortState[key] = dir;
  tbl.querySelectorAll('th .sort-ind').forEach(function(s) { s.textContent = ''; });
  var th = tbl.querySelectorAll('thead th')[colIdx]; if (th) { var si = th.querySelector('.sort-ind'); if (si) si.textContent = dir === 'asc' ? '▲' : '▼'; }
  var tbody = tbl.querySelector('tbody'), rows = Array.from(tbody.querySelectorAll('tr:not(.grand-total)')), gt = tbody.querySelector('tr.grand-total');
  rows.sort(function(a, b) {
    var aV = a.children[colIdx] ? a.children[colIdx].textContent.trim() : '', bV = b.children[colIdx] ? b.children[colIdx].textContent.trim() : '';
    var aN = parseFloat(aV.replace(/[$,%]/g, '').replace(/,/g, '')), bN = parseFloat(bV.replace(/[$,%]/g, '').replace(/,/g, ''));
    if (!isNaN(aN) && !isNaN(bN)) return dir === 'asc' ? aN - bN : bN - aN;
    return dir === 'asc' ? aV.localeCompare(bV) : bV.localeCompare(aV);
  });
  rows.forEach(function(r) { tbody.appendChild(r); }); if (gt) tbody.appendChild(gt);
}

/* Dark mode */
function toggleDark() {
  document.documentElement.classList.toggle('dark');
  var isDark = document.documentElement.classList.contains('dark');
  localStorage.setItem('recon-dark', isDark ? '1' : '0');
  document.querySelector('.dark-toggle').textContent = isDark ? 'Light Mode' : 'Dark Mode';
}
(function() {
  if (localStorage.getItem('recon-dark') === '1') {
    document.documentElement.classList.add('dark');
    document.addEventListener('DOMContentLoaded', function() {
      var btn = document.querySelector('.dark-toggle');
      if (btn) btn.textContent = 'Light Mode';
    });
  }
})();

/* Hover highlight: all rows with same partner */
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('tr[data-partner]').forEach(function(row) {
    row.addEventListener('mouseenter', function() {
      var p = this.getAttribute('data-partner');
      var tbl = this.closest('table');
      if (!tbl) return;
      tbl.querySelectorAll('tr[data-partner="' + p + '"]').forEach(function(r) {
        r.classList.add('partner-highlight');
      });
    });
    row.addEventListener('mouseleave', function() {
      var p = this.getAttribute('data-partner');
      var tbl = this.closest('table');
      if (!tbl) return;
      tbl.querySelectorAll('tr[data-partner="' + p + '"]').forEach(function(r) {
        r.classList.remove('partner-highlight');
      });
    });
  });
});
</script>
</body></html>"""


def main(close_month=None):
    os.makedirs(config.COMPUTED_DIR, exist_ok=True)

    mi_path = os.path.join(config.BASE_DIR, "manual_inputs.yaml")
    manual_inputs = {}
    if os.path.exists(mi_path):
        with open(mi_path) as f:
            manual_inputs = yaml.safe_load(f) or {}
    if not close_month:
        close_month = manual_inputs.get("close_month", config.default_close_month())

    signoffs = manual_inputs.get("signoffs", {})

    def load_json(name):
        p = os.path.join(config.COMPUTED_DIR, name)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        return None

    validation = load_json("validation_report.json")
    l1 = load_json("l1_results.json")
    l3 = load_json("l3_live_results.json")
    pull_log = load_json("pull_log.json")

    # Health log
    health_log = []
    if os.path.exists(config.HEALTH_LOG_FILE):
        try:
            with open(config.HEALTH_LOG_FILE) as f:
                health_log = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            health_log = []

    # Email log
    email_log = []
    if os.path.exists(config.EMAIL_LOG_FILE):
        try:
            with open(config.EMAIL_LOG_FILE) as f:
                email_log = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            email_log = []

    # Add IST timestamps to health log and email log entries
    for entry in health_log:
        entry["timestamp_ist"] = _to_ist(entry.get("timestamp", ""))
    for entry in email_log:
        entry["timestamp_ist"] = _to_ist(entry.get("timestamp", ""))

    # Add IST to l3 generated_at
    if l3 and l3.get("generated_at"):
        l3["generated_at_ist"] = _to_ist(l3["generated_at"])

    pull_ts = pull_log.get("pull_timestamp") if pull_log else None
    pull_ts_ist = _to_ist(pull_ts) if pull_ts else None
    l1_months = sorted(set(r.get("payout_month") or r.get("month", "") for r in l1["monthly_detail"] if not r.get("is_total_row")), reverse=True) if l1 else []
    l3_months = sorted(set(r["payout_month"] for r in (l3.get("collected", []) + l3.get("yet_to_receive", [])) if isinstance(r.get("payout_month"), str) and r["payout_month"] not in ("", "NaT")), reverse=True) if l3 else []
    l3_coll_months = sorted(set(r["collection_month"] for r in l3.get("collected", []) if isinstance(r.get("collection_month"), str) and r["collection_month"] not in ("", "NaT")), reverse=True) if l3 else []

    class DotDict(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                raise AttributeError(key)

    def to_dot(d):
        if isinstance(d, dict):
            return DotDict({k: to_dot(v) for k, v in d.items()})
        if isinstance(d, list):
            return [to_dot(i) for i in d]
        return d

    ctx = {
        "close_month": close_month,
        "generated_at": (datetime.utcnow() + IST_OFFSET).strftime("%Y-%m-%d %H:%M"),
        "pull_timestamp_ist": pull_ts_ist,
        "validation": to_dot(validation) if validation else None,
        "l1": to_dot(l1) if l1 else None,
        "l3": to_dot(l3) if l3 else None,
        "l1_months": l1_months,
        "l3_months": l3_months,
        "l3_coll_months": l3_coll_months,
        "signoffs": to_dot(signoffs),
        "partner_config": {k: DotDict(v) for k, v in config.PARTNER_CONFIG.items()},
        "partner_display": config.PARTNER_DISPLAY_NAMES,
        "health_log": to_dot(health_log),
        "email_log": to_dot(email_log),
    }

    tmpl = Template(TEMPLATE)
    html = tmpl.render(**ctx)

    with open(config.OUTPUT_HTML, "w") as f:
        f.write(html)
    print(f"[dashboard] Written → index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
