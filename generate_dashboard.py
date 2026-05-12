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
<title>Affiliates Analytics — {{ close_month }}</title>
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
.refresh-btn { cursor:pointer; background:rgba(255,255,255,.08); border:1px solid rgba(255,255,255,.15); color:#94a3b8; border-radius:8px; padding:6px 14px; font-size:11px; font-weight:600; transition:.2s; font-family:inherit; display:inline-flex; align-items:center; gap:6px; }
.refresh-btn:hover:not(:disabled) { background:rgba(255,255,255,.15); color:#e2e8f0; }
.refresh-btn:disabled { opacity:.55; cursor:default; }
.refresh-btn.running { color:#38bdf8; border-color:rgba(56,189,248,.35); }
.refresh-btn.success { color:#4ade80; border-color:rgba(74,222,128,.35); }
.refresh-btn.error   { color:#f87171; border-color:rgba(248,113,113,.35); }
@keyframes spin { to { transform:rotate(360deg); } }
.spin { display:inline-block; animation:spin .8s linear infinite; }
.header-meta { display:flex; gap:24px; margin-top:20px; flex-wrap:wrap; align-items:flex-start; }
.header-meta .item { }
.header-meta .label { font-size:10px; text-transform:uppercase; letter-spacing:1.2px; color:#475569; font-weight:600; }
.header-meta .value { font-size:14px; font-weight:700; margin-top:1px; }

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
.tab-panel.p3 { padding:0; }

/* ── Experiments sub-nav ── */
#exp-tab1:checked ~ .sub-nav-bar label[for="exp-tab1"] { color:var(--blue); border-bottom-color:var(--blue); }
#exp-tab1:checked ~ .sub-panel.ep1 { display:block; }

/* ── C1B iframe ── */
.c1b-toolbar { display:flex; align-items:center; gap:10px; padding:10px 20px; border-bottom:1px solid var(--border); background:var(--card); }
.c1b-toolbar-title { font-size:11px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:1px; }
.c1b-toolbar-spacer { flex:1; }
.c1b-status-text { font-size:11px; color:var(--muted); }
.c1b-refresh-btn { cursor:pointer; background:var(--bg); border:1.5px solid var(--border); color:var(--text); border-radius:8px; padding:6px 14px; font-size:11px; font-weight:700; font-family:inherit; display:inline-flex; align-items:center; gap:6px; transition:.15s; }
.c1b-refresh-btn:hover:not(:disabled) { background:var(--border); }
.c1b-refresh-btn:disabled { opacity:.5; cursor:default; }
.c1b-refresh-btn.running { color:#0077cc; border-color:rgba(0,119,204,.4); }
.c1b-refresh-btn.success { color:var(--green); border-color:rgba(22,163,74,.4); }
.c1b-refresh-btn.error   { color:var(--red);   border-color:rgba(220,38,38,.4); }
@keyframes c1b-spin { to { transform:rotate(360deg); } }
.c1b-spin { display:inline-block; animation:c1b-spin 1s linear infinite; }
.c1b-iframe { display:block; width:100%; height:calc(100vh - 178px); border:none; }
/* Monitor partner filter bar */
#mon-filter-bar { margin-bottom:20px; }
.mon-cb-wrap { display:flex; flex-wrap:wrap; gap:8px; align-items:center; }
.mon-cb-label { display:inline-flex; align-items:center; gap:4px; font-size:12px; font-weight:500; color:var(--text); padding:4px 10px; border:1px solid var(--border); border-radius:6px; cursor:pointer; background:var(--card); transition:.15s; }
.mon-cb-label:hover { background:var(--bg); }
.mon-cb-label input[type="checkbox"] { width:13px; height:13px; cursor:pointer; }

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
.chart-grid { display:flex; flex-direction:column; gap:16px; }
.chart-row { display:grid; grid-template-columns:1fr 1fr 1fr; gap:16px; }
.chart-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:12px; min-width:0; }
html.dark .chart-card { background:var(--card); border-color:var(--border); }
/* About tab */
.sql-block { background:var(--bg); border:1px solid var(--border); border-radius:8px; padding:14px 18px; font-family:'SF Mono','Cascadia Code','Consolas',monospace; font-size:11.5px; white-space:pre; overflow-x:auto; color:var(--text); margin-top:10px; line-height:1.7; }
html.dark .sql-block { background:#0a0f1e; }
.about-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:8px; }
@media (max-width:900px) { .about-grid { grid-template-columns:1fr; } }
.about-card { background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:16px 20px; }
.about-card .ac-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.8px; color:var(--muted); margin-bottom:8px; }
.about-card .ac-val { font-size:13px; font-weight:600; color:var(--text); }
.about-card .ac-sub { font-size:11px; color:var(--muted); margin-top:3px; }
.tag { display:inline-block; padding:2px 9px; border-radius:10px; font-size:10px; font-weight:700; margin:2px; }
.tag-blue { background:var(--blue-bg); color:var(--blue-text); }
.tag-green { background:var(--green-bg); color:var(--green-text); }
.tag-purple { background:var(--purple-bg); color:var(--purple-text); }
.tag-teal { background:var(--teal-bg); color:var(--teal-text); }
.tag-amber { background:var(--amber-bg); color:var(--amber-text); }
.rule-row { display:flex; align-items:center; gap:10px; padding:7px 0; border-bottom:1px solid var(--border); font-size:12px; }
.rule-row:last-child { border-bottom:none; }
.rule-condition { flex:1; color:var(--muted); font-family:'SF Mono','Cascadia Code','Consolas',monospace; font-size:11px; }
.rule-result { font-weight:700; min-width:80px; }
/* Sub-tabs (Recon) */
.sub-tab-wrapper input[type="radio"] { display:none; }
.sub-panel { display:none; }
#recon-tab1:checked ~ .sub-nav-bar label[for="recon-tab1"],
#recon-tab2:checked ~ .sub-nav-bar label[for="recon-tab2"],
#recon-tab3:checked ~ .sub-nav-bar label[for="recon-tab3"] { color:var(--blue); border-bottom-color:var(--blue); }
#recon-tab1:checked ~ .sub-panel.rp1,
#recon-tab2:checked ~ .sub-panel.rp2,
#recon-tab3:checked ~ .sub-panel.rp3 { display:block; }
#mon-tab1:checked ~ .sub-nav-bar label[for="mon-tab1"],
#mon-tab2:checked ~ .sub-nav-bar label[for="mon-tab2"] { color:var(--blue); border-bottom-color:var(--blue); }
#mon-tab1:checked ~ .sub-panel.mp1,
#mon-tab2:checked ~ .sub-panel.mp2 { display:block; }
.sub-nav-bar { display:flex; padding:0 36px; gap:0; background:var(--card); border-bottom:2px solid var(--border); }
.sub-nav-bar label { cursor:pointer; padding:10px 22px; font-size:12px; font-weight:600; color:var(--muted); border-bottom:2px solid transparent; margin-bottom:-2px; transition:.15s; }
.sub-nav-bar label:hover { color:var(--text); }
html.dark .sub-nav-bar { background:var(--card); border-bottom-color:var(--border); }
/* KPI cards */
.kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:24px; }
.kpi-card { background:var(--card); border:1px solid var(--border); border-radius:12px; padding:20px 24px; }
.kpi-card .kpi-label { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.8px; color:var(--muted); }
.kpi-card .kpi-value { font-size:26px; font-weight:800; margin:6px 0 4px; color:var(--text); }
.kpi-card .kpi-sub { font-size:12px; font-weight:600; }
.kpi-up { color:var(--green-text); } .kpi-down { color:var(--red-text); }
html.dark .kpi-card { background:var(--card); border-color:var(--border); }
</style>
</head>
<body>

<div class="container">

<!-- ══ HEADER ══ -->
<div class="header">
  <div class="header-top">
    <div>
      <h1>Affiliates Analytics</h1>
    </div>
    <div class="header-actions">
      <button class="dark-toggle" onclick="toggleDark()">Dark Mode</button>
    </div>
  </div>
  <div class="header-meta">
    <div class="item"><div class="label">Close Month</div><div class="value">{{ close_month }}</div></div>
    <div class="item"><div class="label">Generated</div><div class="value">{{ generated_at }} IST</div></div>
  </div>
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
    <label for="tab0" class="nav-tab"><span class="tab-dot dot-grey"></span>About</label>
    <label for="tab1" class="nav-tab"><span class="tab-dot {% if l1 or l3 %}{% if (l1 and l1.overall_status == 'RED') or (l3 and l3.overall_status == 'RED') %}dot-red{% elif (l1 and l1.overall_status == 'AMBER') or (l3 and l3.overall_status == 'AMBER') %}dot-amber{% else %}dot-green{% endif %}{% else %}dot-grey{% endif %}"></span>Recon</label>
    <label for="tab2" class="nav-tab"><span class="tab-dot dot-grey"></span>Monitor</label>
    <label for="tab3" class="nav-tab"><span class="tab-dot dot-blue"></span>Experiments</label>
  </div>

  <!-- ══ TAB 0 — About ══ -->
  <div class="tab-panel p0">

    <!-- 1: Tab Reference -->
    <div class="section"><h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> Tab Reference</h2>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Tab</th><th>Sub-tab</th><th>What it shows</th><th>Primary source</th><th>Refresh</th></tr></thead>
        <tbody>
          <tr><td><strong>Recon</strong></td><td>Reports vs Invoice</td><td>Monthly partner payout amounts vs invoice amounts, delta $ and %, variance status and trend charts</td><td><span class="tag tag-blue">Metabase SQL</span> <code style="font-size:10px">reports_by_payout_cycle.sql</code></td><td>Daily 9 AM IST</td></tr>
          <tr><td><strong>Recon</strong></td><td>Cash Collections</td><td>Invoice amounts vs actual cash received from partners, yet-to-receive tracking, collection timeline</td><td><span class="tag tag-green">Google Sheet</span> <code style="font-size:10px">New R : finance</code></td><td>Daily 9 AM IST</td></tr>
          <tr><td><strong>Monitor</strong></td><td>—</td><td>Day-on-Day and Week-on-Week payout trends by sub-partner, heatmap, Month-on-Month bar chart and breakdown table</td><td><span class="tag tag-blue">Metabase SQL</span> <code style="font-size:10px">daily / weekly / monthly_by_partner.sql</code></td><td>Daily 9 AM IST</td></tr>
          <tr><td><strong>Recon</strong></td><td>Health</td><td>Pipeline run history, step-level status, email log, cron schedule</td><td><span class="tag tag-teal">Local logs</span> <code style="font-size:10px">logs/health_log.json</code></td><td>Written each run</td></tr>
        </tbody>
      </table></div>
    </div>

    <!-- 2: Data Sources -->
    <div class="section"><h2><span class="section-icon" style="background:var(--green-bg);color:var(--green-text);">2</span> Data Sources</h2>
      <div class="about-grid">
        <div class="about-card">
          <div class="ac-title">Metabase (Athena / Iceberg)</div>
          <div class="ac-val">cosmos-metabase.brightmoney.co</div>
          <div class="ac-sub">Database ID: 2 &nbsp;|&nbsp; User: n8n-bot@brightmoney.co</div>
          <div style="margin-top:8px;font-size:11px;color:var(--muted)">Table: <code>iceberg_db.affiliate__affiliate_revenue__entity</code></div>
          <div style="margin-top:6px;font-size:11px;color:var(--muted)">Key fields: <code>payout_date</code>, <code>partner</code>, <code>payout</code>, <code>conversion_type</code>, <code>l1_conversion</code>, <code>l2_conversion</code>, <code>account</code></div>
        </div>
        <div class="about-card">
          <div class="ac-title">Google Sheet — Cash Collections</div>
          <div class="ac-val">New R : finance</div>
          <div class="ac-sub">Sheet ID: <code style="font-size:10px">1EJPJubKrClHduO-_EgK-6Sh53dTB7Mmf0o5NHgxVsnQ</code></div>
          <div style="margin-top:6px;font-size:11px;color:var(--muted)">GID: 1688298716 &nbsp;|&nbsp; Header row: 10 &nbsp;|&nbsp; Data starts row: 11</div>
          <div style="margin-top:6px;font-size:11px;color:var(--muted)">Auth: Service account key (<code>google_sa_key.json</code>)</div>
        </div>
        <div class="about-card">
          <div class="ac-title">Manual Inputs</div>
          <div class="ac-val">manual_inputs.yaml</div>
          <div class="ac-sub">Optional overrides checked each run</div>
          <div style="margin-top:6px;font-size:11px;color:var(--muted)">Fields: <code>close_month</code> (default: current month − 1), <code>signoffs</code> (partner × cycle sign-off flags)</div>
        </div>
        <div class="about-card">
          <div class="ac-title">Pipeline Schedule</div>
          <div class="ac-val">Daily 9:00 AM IST</div>
          <div class="ac-sub">Cron: 03:30 UTC — run_recon.py</div>
          <div style="margin-top:6px;font-size:11px;color:var(--muted)">Email report: 03:50 UTC — run_email_report.py</div>
          <div style="margin-top:4px;font-size:11px;color:var(--muted)">Slack alert on FAILED or PARTIAL runs</div>
        </div>
      </div>
    </div>

    <!-- 3: SQL Queries -->
    <div class="section"><h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">3</span> SQL Queries</h2>
      <p style="font-size:12px;color:var(--muted);margin-bottom:14px">All queries run via Metabase <code>/api/dataset</code> endpoint against Athena (database_id=2). SQL files live in <code>queries/</code> — edit there to change what's pulled.</p>

      <details open><summary style="font-weight:700;font-size:13px;cursor:pointer;padding:6px 0">reports_by_payout_cycle.sql <span style="font-size:11px;font-weight:400;color:var(--muted)"> — Recon &gt; Reports vs Invoice &nbsp;|&nbsp; all history</span></summary>
        <pre class="sql-block">{{ sql_reports | e }}</pre>
      </details>

      <details style="margin-top:12px"><summary style="font-weight:700;font-size:13px;cursor:pointer;padding:6px 0">daily_by_partner.sql <span style="font-size:11px;font-weight:400;color:var(--muted)"> — Monitor: day-on-day &amp; heatmap &nbsp;|&nbsp; last 60 days &nbsp;|&nbsp; MoneyLion sub-partners kept split</span></summary>
        <pre class="sql-block">{{ sql_daily | e }}</pre>
      </details>

      <details style="margin-top:12px"><summary style="font-weight:700;font-size:13px;cursor:pointer;padding:6px 0">weekly_by_partner.sql <span style="font-size:11px;font-weight:400;color:var(--muted)"> — Monitor: week-on-week &nbsp;|&nbsp; last 16 weeks</span></summary>
        <pre class="sql-block">{{ sql_weekly | e }}</pre>
      </details>

      <details style="margin-top:12px"><summary style="font-weight:700;font-size:13px;cursor:pointer;padding:6px 0">monthly_by_partner.sql <span style="font-size:11px;font-weight:400;color:var(--muted)"> — Monitor: month-on-month &nbsp;|&nbsp; last 13 months</span></summary>
        <pre class="sql-block">{{ sql_monthly | e }}</pre>
      </details>
    </div>

    <!-- 4: Partner Name Mapping -->
    <div class="section"><h2><span class="section-icon" style="background:var(--teal-bg);color:var(--teal-text);">4</span> Partner Name Mapping</h2>
      <p style="font-size:12px;color:var(--muted);margin-bottom:12px">Raw DB partner names are normalised differently in each context. The Recon tab collapses all MoneyLion sub-partners; Monitor keeps them split.</p>
      <div class="tbl-wrap"><table>
        <thead><tr><th>DB Partner Name(s)</th><th>Recon (canonical)</th><th>Monitor display</th><th>GSheet name</th></tr></thead>
        <tbody>
          <tr><td><code style="font-size:10px">EngineAPI, EngineCC, EngineSDK, EngineStatic</code></td><td><span class="partner-dot moneylion"></span>MoneyLion</td><td><em>kept split</em> (EngineAPI, EngineCC…)</td><td>Engine</td></tr>
          <tr><td><code style="font-size:10px">AmoneAPI</code></td><td><span class="partner-dot amone"></span>AmONE</td><td>AmONE</td><td>AmOne</td></tr>
          <tr><td><code style="font-size:10px">PBrigit</code></td><td><span class="partner-dot brigit"></span>Brigit</td><td>Brigit</td><td>Brigit</td></tr>
          <tr><td><code style="font-size:10px">Pkashkick</code></td><td><span class="partner-dot kashkick"></span>Kashkick</td><td>Kashkick</td><td>Kashkick</td></tr>
          <tr><td><code style="font-size:10px">PFreecash</code></td><td><span class="partner-dot freecash"></span>Freecash</td><td>Freecash</td><td>Freecash</td></tr>
          <tr><td><code style="font-size:10px">PSupermoney</code></td><td><span class="partner-dot supermoney"></span>Supermoney</td><td>SuperMoney</td><td>Supermoney</td></tr>
        </tbody>
      </table></div>
    </div>

    <!-- 5: Partner Configuration -->
    <div class="section"><h2><span class="section-icon" style="background:var(--amber-bg);color:var(--amber-text);">5</span> Partner Configuration</h2>
      <div class="tbl-wrap"><table>
        <thead><tr><th>Partner</th><th>Payout Cycles</th><th>Payment Term</th><th>Accel. Charge</th><th>GSheet Name</th></tr></thead>
        <tbody>{% for p, cfg in partner_config.items() %}<tr>
          <td><span class="partner-dot {{ p }}"></span><strong>{{ partner_display[p] }}</strong></td>
          <td>{{ cfg.cycles }}</td>
          <td>{{ cfg.payment_term }} days</td>
          <td>{{ cfg.accel_charge }}</td>
          <td><code style="font-size:11px">{{ cfg.gsheet_name }}</code></td>
        </tr>{% endfor %}</tbody>
      </table></div>
      <p style="font-size:11px;color:var(--muted);margin-top:10px"><strong>Cycle logic (MoneyLion):</strong> payout_date day &le; 15 → C1 &nbsp;|&nbsp; day &gt; 15 → C2. All other partners: single cycle C1.</p>
    </div>

    <!-- 6: Status Logic & Variance Thresholds -->
    <div class="section"><h2><span class="section-icon" style="background:var(--rose-bg);color:var(--rose-text);">6</span> Status Logic &amp; Variance Thresholds</h2>

      <h3 style="margin-bottom:10px">Reports vs Invoice — Monthly Reconciliation</h3>
      <div class="about-grid" style="margin-bottom:16px">
        <div>
          <p style="font-size:12px;font-weight:600;margin-bottom:6px">Status Badge — Label (Variance Status)</p>
          <div class="rule-row"><span class="rule-condition">|delta%| within GREEN threshold</span><span class="rule-result"><span class="badge GREEN">Low</span></span></div>
          <div class="rule-row"><span class="rule-condition">|delta%| within AMBER threshold</span><span class="rule-result"><span class="badge AMBER">Medium</span></span></div>
          <div class="rule-row"><span class="rule-condition">|delta%| exceeds AMBER threshold</span><span class="rule-result"><span class="badge RED">High</span></span></div>
          <div class="rule-row"><span class="rule-condition">No invoice or future month</span><span class="rule-result"><span class="badge PENDING">Pending</span></span></div>
        </div>
        <div>
          <p style="font-size:12px;font-weight:600;margin-bottom:6px">Status Badge — Color (Variance Thresholds)</p>
          <div class="rule-row"><span class="rule-condition">MoneyLion &amp; AmONE &nbsp;|delta%| &lt; 5%</span><span class="rule-result" style="color:var(--green-text)">GREEN (Low)</span></div>
          <div class="rule-row"><span class="rule-condition">MoneyLion &amp; AmONE &nbsp;5% &le; |delta%| &lt; 10%</span><span class="rule-result" style="color:var(--amber-text)">AMBER (Medium)</span></div>
          <div class="rule-row"><span class="rule-condition">MoneyLion &amp; AmONE &nbsp;|delta%| &ge; 10%</span><span class="rule-result" style="color:var(--red-text)">RED (High)</span></div>
          <div class="rule-row"><span class="rule-condition">All others &nbsp;|delta%| &lt; 2%</span><span class="rule-result" style="color:var(--green-text)">GREEN (Low)</span></div>
          <div class="rule-row"><span class="rule-condition">All others &nbsp;2% &le; |delta%| &lt; 5%</span><span class="rule-result" style="color:var(--amber-text)">AMBER (Medium)</span></div>
          <div class="rule-row"><span class="rule-condition">All others &nbsp;|delta%| &ge; 5%</span><span class="rule-result" style="color:var(--red-text)">RED (High)</span></div>
        </div>
      </div>
      <p style="font-size:11px;color:var(--muted);margin-bottom:16px">The badge label shows Variance Status (Low / Medium / High / Pending) and the badge color reflects GREEN / AMBER / RED based on the thresholds above.</p>

      <h3 style="margin-bottom:10px">Cash Collections (Invoice vs Cash Received)</h3>
      <div class="rule-row"><span class="rule-condition">Received $ &ge; Invoiced $</span><span class="rule-result" style="color:var(--green-text)">GREEN &nbsp;(positive delta)</span></div>
      <div class="rule-row"><span class="rule-condition">Received $ &lt; Invoiced $</span><span class="rule-result" style="color:var(--red-text)">RED &nbsp;(shortfall)</span></div>
      <div class="rule-row"><span class="rule-condition">|net delta%| &lt; 2%</span><span class="rule-result" style="color:var(--green-text)">Low variance</span></div>
      <div class="rule-row"><span class="rule-condition">2% &le; |net delta%| &lt; 5%</span><span class="rule-result" style="color:var(--amber-text)">Medium variance</span></div>
      <div class="rule-row" style="margin-bottom:16px"><span class="rule-condition">|net delta%| &ge; 5%</span><span class="rule-result" style="color:var(--red-text)">High variance</span></div>
      <p style="font-size:11px;color:var(--muted)">Delta = Received − Invoiced. Net delta accounts for acceleration charge deductions where applicable. Rows marked "Signed Off" have product sign-off (product_signoff = Yes in the sheet).</p>
    </div>

    <!-- 7: System Configuration -->
    <div class="section"><h2><span class="section-icon" style="background:var(--grey-bg);color:var(--grey-text);">7</span> System Configuration</h2>
      <div class="tbl-wrap"><table class="cfg-tbl">
        <thead><tr><th>Setting</th><th>Value</th><th>Notes</th></tr></thead>
        <tbody>
          <tr><td>Close month</td><td><code>current_month − 1</code> (dynamic)</td><td>Auto-derived each run; override via <code>--month YYYY-MM</code> flag on run_recon.py for backfills</td></tr>
          <tr><td>Daily data window</td><td>Last 60 days</td><td>daily_by_partner.sql — used for day-on-day chart &amp; heatmap</td></tr>
          <tr><td>Weekly data window</td><td>Last 16 weeks</td><td>weekly_by_partner.sql — WoW chart</td></tr>
          <tr><td>Monthly data window</td><td>Last 13 months</td><td>monthly_by_partner.sql — MoM chart</td></tr>
          <tr><td>Heatmap window</td><td>Last 14 days</td><td>Shown in Monitor &gt; Day-on-Day section</td></tr>
          <tr><td>Health log retention</td><td>90 entries</td><td>health_log.json — older entries are pruned</td></tr>
          <tr><td>Email log retention</td><td>90 entries</td><td>email_log.json</td></tr>
          <tr><td>Metabase DB ID</td><td>2 (Athena / Iceberg)</td><td>METABASE_DATABASE_ID in config.py</td></tr>
          <tr><td>Google Sheet header</td><td>Row 10</td><td>Data starts row 11, GID 1688298716</td></tr>
          <tr><td>Acceleration charge</td><td>3% (MoneyLion only)</td><td>Applied when payment term &lt; 30 days</td></tr>
          <tr><td>Slack alerts</td><td>On FAILED or PARTIAL runs</td><td>Webhook URL via SLACK_WEBHOOK_URL env var</td></tr>
        </tbody>
      </table></div>
    </div>

  </div><!-- /p0 About -->

  <!-- ══ TAB 1 — Recon (sub-tabs) ══ -->
  <div class="tab-panel p1">
  <input type="radio" id="recon-tab1" name="recon-tabs" checked>
  <input type="radio" id="recon-tab2" name="recon-tabs">
  <input type="radio" id="recon-tab3" name="recon-tabs">
  <div class="sub-nav-bar" style="justify-content:space-between;align-items:center;">
    <div style="display:flex;">
      <label for="recon-tab1"><span class="tab-dot {% if l1 %}{% if l1.overall_status == 'GREEN' %}dot-green{% elif l1.overall_status == 'AMBER' %}dot-amber{% else %}dot-red{% endif %}{% else %}dot-grey{% endif %}"></span>Reports vs Invoice</label>
      <label for="recon-tab2"><span class="tab-dot {% if l3 %}{% if l3.overall_status == 'GREEN' %}dot-green{% elif l3.overall_status == 'AMBER' %}dot-amber{% else %}dot-red{% endif %}{% else %}dot-grey{% endif %}"></span>Cash Collections</label>
      <label for="recon-tab3"><span class="tab-dot {% if health_log %}{% if health_log[-1].status == 'SUCCESS' %}dot-green{% elif health_log[-1].status == 'PARTIAL' %}dot-amber{% else %}dot-red{% endif %}{% else %}dot-grey{% endif %}"></span>Health</label>
    </div>
    <div style="padding-right:16px;">
      <button class="refresh-btn" id="refreshBtn" onclick="triggerRefresh()">&#x21bb; Refresh</button>
    </div>
  </div>
  <div class="sub-panel rp1">
  {% if l1 %}
    <div class="section"><h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> Monthly Reconciliation</h2>
      <div class="filter-bar"><label>Partner:</label>
        <select id="f1m-partner" multiple size="1" onchange="applyFilter('t1m')"><option value="ALL" selected>All</option>{% for p in l1.cumulative %}<option value="{{ p.partner }}">{{ p.display_name }}</option>{% endfor %}</select>
        <label>Month:</label>
        <select id="f1m-month-from" onchange="applyFilter('t1m')"><option value="">From</option>{% for m in l1_months %}<option>{{ m }}</option>{% endfor %}</select>
        <select id="f1m-month-to" onchange="applyFilter('t1m')"><option value="">To</option>{% for m in l1_months|reverse %}<option>{{ m }}</option>{% endfor %}</select>
        <div class="status-checks">
          <label><input type="checkbox" value="Low" checked onchange="applyFilter('t1m')">Low</label>
          <label><input type="checkbox" value="Medium" checked onchange="applyFilter('t1m')">Medium</label>
          <label><input type="checkbox" value="High" checked onchange="applyFilter('t1m')">High</label>
          <label><input type="checkbox" value="Pending" checked onchange="applyFilter('t1m')">Pending</label>
        </div><button onclick="resetFilter('t1m')">Reset</button></div>
      <div class="tbl-wrap"><table id="t1m">
        <thead><tr><th onclick="sortTable('t1m',0)">Month <span class="sort-ind"></span></th><th onclick="sortTable('t1m',1)">Partner</th><th onclick="sortTable('t1m',2)">Cycle</th><th class="num" onclick="sortTable('t1m',3)">Invoice $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1m',4)">Reports $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1m',5)">Delta $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1m',6)">Delta % <span class="sort-ind"></span></th><th onclick="sortTable('t1m',7)">Status</th><th>Comments</th></tr></thead>
        <tbody>{% for r in l1.monthly_detail %}<tr data-partner="{{ r.partner }}" data-month="{{ r.payout_month }}" data-status="{{ r.monthly_status }}"><td>{{ r.payout_month }}</td><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td>{{ r.cycle }}</td><td class="num">${{ "{:,.2f}".format(r.invoice_amount if r.invoice_amount is defined else r.reports_amount) }}</td><td class="num">${{ "{:,.2f}".format(r.reports_amount) }}</td><td class="num {{ 'var-pos' if r.delta >= 0 else 'var-neg' }}">${{ "{:,.2f}".format(r.delta) }}</td><td class="num {{ 'var-pos' if r.delta_pct is not none and r.delta_pct >= 0 else 'var-neg' }}">{{ "{:.2f}%".format(r.delta_pct) if r.delta_pct is not none else '—' }}</td><td><span class="badge {{ r.status }}">{{ r.monthly_status }}</span></td><td><input class="comment-input" type="text" placeholder="Add note..."></td></tr>{% endfor %}</tbody>
      </table></div></div>
    <div class="section"><h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">2</span> Cumulative To-Date</h2>
      <div class="tbl-wrap"><table id="t1c">
        <thead><tr><th onclick="sortTable('t1c',0)">Partner <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',1)">Total Invoice $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',2)">Total Payout $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',3)">Delta $ <span class="sort-ind"></span></th><th class="num" onclick="sortTable('t1c',4)">Delta % <span class="sort-ind"></span></th><th onclick="sortTable('t1c',5)">Status</th><th class="num" onclick="sortTable('t1c',6)"># Months</th><th>Comments</th></tr></thead>
        <tbody>{% for r in l1.cumulative %}<tr data-partner="{{ r.partner }}" data-status="{{ r.status }}"><td><span class="partner-dot {{ r.partner }}"></span>{{ r.display_name }}</td><td class="num">${{ "{:,.2f}".format(r.total_invoice) }}</td><td class="num">${{ "{:,.2f}".format(r.total_reports) }}</td><td class="num {{ 'var-pos' if r.total_delta >= 0 else 'var-neg' }}">${{ "{:,.2f}".format(r.total_delta) }}</td><td class="num">{{ "{:.2f}%".format(r.delta_pct) if r.delta_pct is not none else '—' }}</td><td><span class="badge {{ r.status }}">{{ r.status }}</span></td><td class="num">{{ r.month_count }}</td><td><input class="comment-input" type="text" placeholder="Add note..."></td></tr>{% endfor %}
        {% if l1.grand_total %}<tr class="grand-total"><td><strong>{{ l1.grand_total.display_name }}</strong></td><td class="num">${{ "{:,.2f}".format(l1.grand_total.total_invoice) }}</td><td class="num">${{ "{:,.2f}".format(l1.grand_total.total_reports) }}</td><td class="num">${{ "{:,.2f}".format(l1.grand_total.total_delta) }}</td><td class="num">{{ "{:.2f}%".format(l1.grand_total.delta_pct) if l1.grand_total.delta_pct is not none else '—' }}</td><td></td><td class="num">{{ l1.grand_total.month_count }}</td><td></td></tr>{% endif %}</tbody>
      </table></div></div>
    <div class="section"><h2><span class="section-icon" style="background:var(--teal-bg);color:var(--teal-text);">3</span> Month-on-Month Trends</h2>
      <p style="font-size:12px;color:var(--muted);margin-bottom:16px">One chart per partner &times; cycle &mdash; Invoice $, Reports $, and Delta $ over time. Hover to inspect, drag to pan, scroll to zoom.</p>
      <div class="chart-grid" id="trend-chart-grid"></div>
    </div>
  {% else %}<div class="section"><p style="color:var(--muted)">Reports vs Invoice data not available.</p></div>{% endif %}
  </div><!-- /rp1 -->

  <!-- Invoice vs Cash sub-tab -->
  <div class="sub-panel rp2">
  {% if l3 %}
    <div class="note-box"><strong>Source:</strong> <a href="https://docs.google.com/spreadsheets/d/1EJPJubKrClHduO-_EgK-6Sh53dTB7Mmf0o5NHgxVsnQ/edit?gid=1688298716#gid=1688298716" target="_blank" style="color:var(--green-text);font-weight:600">Google Sheet — New R : finance</a>. Pulled: {{ l3.generated_at_ist }} IST. &nbsp;|&nbsp; Delta = Received − Invoiced. &nbsp;|&nbsp; <span style="color:var(--green-text)">GREEN</span> = Received &ge; Invoiced &nbsp;|&nbsp; <span style="color:var(--red-text)">RED</span> = shortfall. &nbsp;|&nbsp; Variance: <strong>Low</strong> &lt;2% &nbsp; <strong>Medium</strong> 2–5% &nbsp; <strong>High</strong> &ge;5%.</div>

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
  </div><!-- /rp2 -->

  <!-- Health sub-tab -->
  <div class="sub-panel rp3">
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
        <thead><tr><th>Timestamp (IST)</th><th>Close Month</th><th>Status</th><th>Data Pull</th><th>Validation</th><th>Reports vs Invoice</th><th>Invoice vs Cash</th><th>Dashboard</th><th class="num">Duration</th><th>Errors</th></tr></thead>
        <tbody>{% for h in health_log|reverse %}<tr{% if h.status == 'FAILED' %} style="background:var(--red-bg)"{% endif %}>
          <td>{{ h.timestamp_ist }} IST</td>
          <td>{{ h.close_month }}</td>
          <td><span class="badge {{ h.status }}">{{ h.status }}</span></td>
          <td>{{ h.steps.data_pull if h.steps.data_pull is defined else '—' }}</td>
          <td>{{ h.steps.validation if h.steps.validation is defined else '—' }}</td>
          <td>{{ h.steps.reports_vs_invoice if h.steps.reports_vs_invoice is defined else '—' }}</td>
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
  </div><!-- /rp3 Health -->

  </div><!-- /p1 Recon -->

  <!-- ══ TAB 2 — Monitor ══ -->
  <div class="tab-panel p2">
  <input type="radio" id="mon-tab1" name="mon-tabs" checked>
  <input type="radio" id="mon-tab2" name="mon-tabs">
  <div class="sub-nav-bar">
    <label for="mon-tab1"><span class="tab-dot dot-grey"></span>Payouts</label>
    <label for="mon-tab2"><span class="tab-dot dot-blue"></span>Enrolls</label>
  </div>
  <div class="sub-panel mp1">
    <!-- Partner filter -->
    <div class="filter-bar" id="mon-filter-bar">
      <label>Partner:</label>
      <div class="mon-cb-wrap" id="mon-partner-checks"></div>
      <button id="mon-btn-all" style="padding:5px 14px;font-size:11px;font-weight:600;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-family:inherit">All</button>
      <button id="mon-btn-none" style="padding:5px 14px;font-size:11px;font-weight:600;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);cursor:pointer;font-family:inherit">None</button>
    </div>

    <!-- KPI -->
    <div class="section">
      <h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> KPI Summary</h2>
      <div class="kpi-grid" id="mon-kpi-grid"></div>
    </div>

    <!-- Day-on-Day -->
    <div class="section">
      <h2><span class="section-icon" style="background:var(--green-bg);color:var(--green-text);">2</span> Day-on-Day Payouts <span style="font-size:12px;font-weight:400;color:var(--muted)">(last 30 days)</span></h2>
      <div class="chart-card" id="mon-daily-chart" style="padding:16px"></div>
      <div class="tbl-wrap" style="margin-top:16px"><table id="mon-heatmap-tbl"></table></div>
    </div>

    <!-- Week-on-Week -->
    <div class="section">
      <h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">3</span> Week-on-Week Payouts <span style="font-size:12px;font-weight:400;color:var(--muted)">(last 13 weeks)</span></h2>
      <div class="chart-card" id="mon-weekly-chart" style="padding:16px"></div>
    </div>

    <!-- Month-on-Month -->
    <div class="section">
      <h2><span class="section-icon" style="background:var(--teal-bg);color:var(--teal-text);">4</span> Month on Month Payouts <span style="font-size:12px;font-weight:400;color:var(--muted)">(last 13 months)</span></h2>
      <div class="chart-card" id="mon-mom-chart" style="padding:16px"></div>
      <div class="tbl-wrap" style="margin-top:16px"><table id="mon-mom-tbl"></table></div>
    </div>

  </div><!-- /mp1 Payouts -->

  <div class="sub-panel mp2" style="padding:28px 36px">
    <div class="section">
      <h2><span class="section-icon" style="background:var(--blue-bg);color:var(--blue-text);">1</span> Monthly Enrollments by Partner <span style="font-size:12px;font-weight:400;color:var(--muted)">(last 13 months)</span></h2>
      <div class="chart-card" id="enr-chart-monthly" style="padding:16px"></div>
    </div>
    <div class="section">
      <h2><span class="section-icon" style="background:var(--purple-bg);color:var(--purple-text);">2</span> Payout by Enroll Month &amp; Cohort Bucket <span style="font-size:12px;font-weight:400;color:var(--muted)">(last 13 months)</span></h2>
      <div class="chart-card" id="enr-chart-cohort" style="padding:16px"></div>
      <div class="tbl-wrap" style="margin-top:16px"><table id="enr-tbl-cohort"></table></div>
    </div>
    <div class="section">
      <h2><span class="section-icon" style="background:var(--teal-bg);color:var(--teal-text);">3</span> Enrollments by Imp Source <span style="font-size:12px;font-weight:400;color:var(--muted)">(last 13 months · top 8)</span></h2>
      <div class="chart-card" id="enr-chart-imp" style="padding:16px"></div>
      <div class="tbl-wrap" style="margin-top:16px"><table id="enr-tbl-imp"></table></div>
    </div>
    <div class="section">
      <h2><span class="section-icon" style="background:var(--grey-bg);color:var(--grey-text);">4</span> Enrolls Rollup <span style="font-size:12px;font-weight:400;color:var(--muted);margin-left:8px">last 30 days · enroll date × partner × imp_source × payout cohort</span></h2>
      <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;align-items:center">
        <div style="display:flex;align-items:center;gap:6px"><label style="font-size:11px;font-weight:600;color:var(--muted)">Partner:</label><select id="enr-filter-partner" style="font-size:11px;padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-family:inherit"><option value="">All</option></select></div>
        <div style="display:flex;align-items:center;gap:6px"><label style="font-size:11px;font-weight:600;color:var(--muted)">Cohort:</label><select id="enr-filter-cohort" style="font-size:11px;padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-family:inherit"><option value="">All</option></select></div>
        <div style="display:flex;align-items:center;gap:6px"><label style="font-size:11px;font-weight:600;color:var(--muted)">Imp Source:</label><select id="enr-filter-imp" style="font-size:11px;padding:4px 8px;border:1px solid var(--border);border-radius:6px;background:var(--card);color:var(--text);font-family:inherit"><option value="">All</option></select></div>
        <span id="enr-row-count" style="font-size:11px;color:var(--muted);margin-left:auto"></span>
      </div>
      <div class="tbl-wrap"><table id="enr-table">
        <thead><tr>
          <th data-col="enroll_date" style="cursor:pointer">Enroll Date ↕</th>
          <th data-col="partner" style="cursor:pointer">Partner ↕</th>
          <th data-col="imp_source" style="cursor:pointer">Imp Source ↕</th>
          <th data-col="payout_cohort_bucket" style="cursor:pointer">Cohort ↕</th>
          <th data-col="enrolled_users" style="cursor:pointer;text-align:right">Enrolled Users ↕</th>
          <th data-col="total_leads" style="cursor:pointer;text-align:right">Leads ↕</th>
          <th data-col="total_payout" style="cursor:pointer;text-align:right">Total Payout ↕</th>
          <th data-col="avg_payout" style="cursor:pointer;text-align:right">Avg Payout ↕</th>
        </tr></thead>
        <tbody id="enr-tbody"></tbody>
      </table></div>
    </div>
  </div><!-- /mp2 Enrolls -->

  </div><!-- /p2 Monitor -->

  <!-- ══ TAB 3 — Experiments ══ -->
  <div class="tab-panel p3">
    <input type="radio" id="exp-tab1" name="exp-tabs" checked>
    <div class="sub-nav-bar">
      <label for="exp-tab1"><span class="tab-dot dot-blue"></span>C1B</label>
      <div style="flex:1"></div>
      <div class="c1b-toolbar" style="border:none;padding:8px 20px 8px 0;background:transparent;">
        <span class="c1b-status-text" id="c1bStatusText"></span>
        <button class="c1b-refresh-btn" id="c1bRefreshBtn" onclick="triggerC1BRefresh()">&#x21bb; Refresh C1B</button>
      </div>
    </div>
    <div class="sub-panel ep1">
      <iframe class="c1b-iframe" id="c1bFrame" src="c1b_dashboard.html" title="C1B Experiment Dashboard"></iframe>
    </div>
  </div><!-- /p3 Experiments -->

</div><!-- /tab-wrapper -->
</div><!-- /body-wrap -->

<div class="footer">Dashboard generated: {{ generated_at }} IST &nbsp;&bull;&nbsp; Affiliates Analytics</div>

</div><!-- /container -->

<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
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

/* ── Trend charts (Plotly) ── */
(function() {
  var TREND_DATA = {{ chart_data_json }};
  var PARTNER_COLORS = {
    moneylion:'#3b82f6', amone:'#8b5cf6', kashkick:'#0d9488',
    freecash:'#22c55e', brigit:'#f97316', supermoney:'#e11d48'
  };
  function buildCharts() {
    var grid = document.getElementById('trend-chart-grid');
    if (!grid || !window.Plotly) return;
    grid.innerHTML = '';
    var isDark = document.documentElement.classList.contains('dark');
    var fontColor = isDark ? '#e2e8f0' : '#1a1a2e';
    var gridColor = isDark ? '#334155' : '#e2e8f0';
    var paperBg   = isDark ? '#1e293b' : '#ffffff';
    var cfg = { responsive:true, displayModeBar:false, scrollZoom:false };
    var groups = {};
    TREND_DATA.forEach(function(r) {
      var key = r.partner + '|' + r.cycle;
      if (!groups[key]) groups[key] = { partner:r.partner, display_name:r.display_name, cycle:r.cycle, rows:[] };
      groups[key].rows.push(r);
    });
    Object.values(groups).forEach(function(g) {
      g.rows.sort(function(a,b){ return a.payout_month.localeCompare(b.payout_month); });
      var _cutoff = new Date(); _cutoff.setMonth(_cutoff.getMonth() - 12);
      var _cutoffStr = _cutoff.getFullYear() + '-' + ('0' + (_cutoff.getMonth() + 1)).slice(-2);
      g.rows = g.rows.filter(function(r){ return r.payout_month >= _cutoffStr; });
    });
    var SKIP = { 'moneylion|C3':1, 'supermoney|C1':1 };
    var sorted = Object.values(groups).filter(function(g){
      return !SKIP[g.partner + '|' + g.cycle];
    }).sort(function(a,b){
      return a.partner.localeCompare(b.partner) || a.cycle.localeCompare(b.cycle);
    });
    sorted.forEach(function(g) {
      var months    = g.rows.map(function(r){ return r.payout_month; });
      var invoices  = g.rows.map(function(r){ return r.invoice_amount; });
      var reports   = g.rows.map(function(r){ return r.reports_amount; });
      var deltas    = g.rows.map(function(r){ return r.delta; });
      var deltaPcts = g.rows.map(function(r){ return r.delta_pct; });
      var baseColor = PARTNER_COLORS[g.partner] || '#64748b';
      var label = g.display_name + ' — ' + g.cycle;
      var baseLayout = {
        dragmode: false,
        height: 280,
        margin: { t:44, b:64, l:72, r:20 },
        legend: { orientation:'h', y:-0.3, font:{ size:11, color:fontColor } },
        xaxis: { tickangle:-45, tickfont:{ size:10, color:fontColor }, gridcolor:gridColor, automargin:true },
        plot_bgcolor: 'transparent', paper_bgcolor: paperBg,
        font: { family:'Inter,system-ui,sans-serif', color:fontColor }
      };

      /* row wrapper — both charts side by side */
      var row = document.createElement('div');
      row.className = 'chart-row';
      grid.appendChild(row);

      /* Chart 1: Invoice vs Reports */
      var c1 = document.createElement('div');
      c1.className = 'chart-card';
      c1.id = 'tchart-ir-' + g.partner + '-' + g.cycle;
      row.appendChild(c1);
      Plotly.newPlot(c1, [
        { x:months, y:invoices, name:'Invoice $', type:'bar',
          marker:{ color:baseColor, opacity:0.9 } },
        { x:months, y:reports,  name:'Reports $', type:'bar',
          marker:{ color:baseColor, opacity:0.4, line:{ color:baseColor, width:1 } } }
      ], Object.assign({}, baseLayout, {
        title:{ text: label + ' | Invoice vs Reports',
                font:{ size:12, color:fontColor, family:'Inter,system-ui,sans-serif' }, x:0.04 },
        barmode:'group',
        yaxis: Object.assign({}, { tickformat:'$,.0f', tickfont:{ size:10, color:fontColor },
               gridcolor:gridColor, title:{ text:'$', font:{ size:11, color:fontColor } } })
      }), cfg);

      /* Chart 2: Delta $ */
      var c2 = document.createElement('div');
      c2.className = 'chart-card';
      c2.id = 'tchart-d-' + g.partner + '-' + g.cycle;
      row.appendChild(c2);
      Plotly.newPlot(c2, [
        { x:months, y:deltas, name:'Delta $', type:'scatter', mode:'lines+markers',
          line:{ color:'#f97316', width:2 }, marker:{ size:6, color:'#f97316' } }
      ], Object.assign({}, baseLayout, {
        title:{ text: label + ' | Delta $',
                font:{ size:12, color:fontColor, family:'Inter,system-ui,sans-serif' }, x:0.04 },
        yaxis: { tickformat:'$,.0f', tickfont:{ size:10, color:fontColor },
                 gridcolor:gridColor, zeroline:true, zerolinecolor:'#94a3b8', zerolinewidth:1,
                 title:{ text:'Delta $', font:{ size:11, color:'#f97316' } } }
      }), cfg);

      /* Chart 3: Delta % */
      var c3 = document.createElement('div');
      c3.className = 'chart-card';
      c3.id = 'tchart-dp-' + g.partner + '-' + g.cycle;
      row.appendChild(c3);
      Plotly.newPlot(c3, [
        { x:months, y:deltaPcts, name:'Delta %', type:'scatter', mode:'lines+markers',
          line:{ color:'#a78bfa', width:2 }, marker:{ size:6, color:'#a78bfa' } }
      ], Object.assign({}, baseLayout, {
        title:{ text: label + ' | Delta %',
                font:{ size:12, color:fontColor, family:'Inter,system-ui,sans-serif' }, x:0.04 },
        yaxis: { tickformat:'.2f', ticksuffix:'%', tickfont:{ size:10, color:fontColor },
                 gridcolor:gridColor, zeroline:true, zerolinecolor:'#94a3b8', zerolinewidth:1,
                 title:{ text:'Delta %', font:{ size:11, color:'#a78bfa' } } }
      }), cfg);
    });
  }
  function resizeCharts() {
    document.querySelectorAll('[id^="tchart-"]').forEach(function(el) {
      if (window.Plotly) Plotly.Plots.resize(el);
    });
  }
  document.addEventListener('DOMContentLoaded', function() {
    buildCharts();
    var tab1Radio = document.getElementById('tab1');
    if (tab1Radio) tab1Radio.addEventListener('change', function() {
      if (this.checked) setTimeout(resizeCharts, 50);
    });
    document.querySelector('.dark-toggle') && document.querySelector('.dark-toggle').addEventListener('click', function() {
      setTimeout(buildCharts, 50);
    });
  });
})();

/* ── Monitor tab ── */
(function() {
  var MON = {{ monitor_data_json }};
  var PALETTE = [
    '#3b82f6','#1d4ed8','#60a5fa','#93c5fd','#bfdbfe',
    '#8b5cf6','#0d9488','#22c55e','#f97316','#e11d48',
    '#ec4899','#f59e0b','#10b981','#6366f1','#84cc16','#06b6d4'
  ];
  /* Stable partner → palette index mapping so colors stay consistent after filter */
  var PARTNER_IDX = {};
  (function() {
    var all = [];
    var seen = {};
    [(MON.daily||[]),(MON.weekly||[]),(MON.monthly||[])].forEach(function(arr) {
      arr.forEach(function(r) { if (!seen[r.partner]) { seen[r.partner]=1; all.push(r.partner); } });
    });
    all.sort().forEach(function(p, i) { PARTNER_IDX[p] = i; });
  })();

  function fmtDollar(v) { return v == null ? '—' : '$' + Math.round(v).toLocaleString('en-US'); }
  function fmtK(v) {
    if (v == null || v === 0) return '—';
    return v >= 1000 ? '$' + (v / 1000).toFixed(1) + 'k' : '$' + Math.round(v);
  }
  function plotColors(isDark) {
    return {
      fc: isDark ? '#e2e8f0' : '#1a1a2e',
      gc: isDark ? '#334155' : '#e2e8f0',
      pb: isDark ? '#1e293b' : '#ffffff'
    };
  }

  /* ── Partner filter ── */
  function getAllPartners() {
    var all = []; var seen = {};
    [(MON.daily||[]),(MON.weekly||[]),(MON.monthly||[])].forEach(function(arr) {
      arr.forEach(function(r) { if (!seen[r.partner]) { seen[r.partner]=1; all.push(r.partner); } });
    });
    return all.sort();
  }
  function buildPartnerFilter() {
    var wrap = document.getElementById('mon-partner-checks'); if (!wrap) return;
    var partners = getAllPartners();
    var html = '';
    partners.forEach(function(p) {
      var color = PALETTE[PARTNER_IDX[p] % PALETTE.length];
      html += '<label class="mon-cb-label" style="border-left:3px solid ' + color + '">'
            + '<input type="checkbox" class="mon-pcb" value="' + p + '" checked> ' + p + '</label>';
    });
    wrap.innerHTML = html;
    wrap.querySelectorAll('.mon-pcb').forEach(function(cb) {
      cb.addEventListener('change', applyFilter);
    });
    document.getElementById('mon-btn-all') && document.getElementById('mon-btn-all').addEventListener('click', function() {
      wrap.querySelectorAll('.mon-pcb').forEach(function(cb) { cb.checked = true; });
      applyFilter();
    });
    document.getElementById('mon-btn-none') && document.getElementById('mon-btn-none').addEventListener('click', function() {
      wrap.querySelectorAll('.mon-pcb').forEach(function(cb) { cb.checked = false; });
      applyFilter();
    });
  }
  function getSelectedPartners() {
    var cbs = document.querySelectorAll('.mon-pcb');
    var sel = [];
    cbs.forEach(function(cb) { if (cb.checked) sel.push(cb.value); });
    return sel.length ? sel : getAllPartners();
  }
  function applyFilter() {
    var isDark = document.documentElement.classList.contains('dark');
    var sel = getSelectedPartners();
    buildKPIs();
    renderChart('mon-daily-chart',  MON.daily,  'date',       isDark, sel);
    renderChart('mon-weekly-chart', MON.weekly, 'week_start', isDark, sel);
    renderHeatmap(sel);
    renderMoMChart(isDark, sel);
    renderMoMTable(sel);
  }

  /* ── KPI cards (no partner filter — always aggregate) ── */
  function buildKPIs() {
    var grid = document.getElementById('mon-kpi-grid'); if (!grid || !MON.kpis) return;
    var k = MON.kpis; var wtd = k.wtd || {}; var mtd = k.mtd || {};
    var wowHtml = '';
    if (wtd.wow_pct != null) {
      var cls = wtd.wow_pct >= 0 ? 'kpi-up' : 'kpi-down';
      wowHtml = '<div class="kpi-sub ' + cls + '">' + (wtd.wow_pct >= 0 ? '▲' : '▼') + ' '
              + Math.abs(wtd.wow_pct).toFixed(1) + '% vs same days last wk</div>';
    }
    var lwHtml = '';
    if (wtd.lfw_total != null) {
      var lwPct = wtd.lw_vs_llw_pct;
      var lwCls = (lwPct != null && lwPct >= 0) ? 'kpi-up' : 'kpi-down';
      var lwPctStr = lwPct != null ? ' (' + (lwPct >= 0 ? '▲' : '▼') + ' ' + Math.abs(lwPct).toFixed(1) + '% vs wk before)' : '';
      lwHtml = '<div style="font-size:11px;color:var(--muted);margin-top:6px">Last wk: <span class="' + lwCls + '" style="font-weight:600">'
             + fmtDollar(wtd.lfw_total) + '</span>' + lwPctStr + '</div>';
    }
    grid.style.gridTemplateColumns = 'repeat(2,minmax(0,360px))';
    grid.innerHTML =
      '<div class="kpi-card"><div class="kpi-label">WTD</div>'
      + '<div class="kpi-value">' + fmtDollar(wtd.total) + '</div>'
      + wowHtml + lwHtml
      + '<div style="font-size:11px;color:var(--subtle);margin-top:4px">Wk of ' + (wtd.week_start||'—') + '</div></div>'
      + '<div class="kpi-card"><div class="kpi-label">MTD</div>'
      + '<div class="kpi-value">' + fmtDollar(mtd.total) + '</div>'
      + '<div style="font-size:11px;color:var(--muted);margin-top:6px">Since ' + (mtd.month_start||'—') + '</div></div>';
  }

  /* ── Stacked bar chart with totals on top ── */
  function renderChart(elId, records, xField, isDark, selPartners) {
    var el = document.getElementById(elId); if (!el || !records || !records.length) return;
    var c = plotColors(isDark);
    var allX = []; var xs = {};
    records.forEach(function(r) { if (!xs[r[xField]]) { xs[r[xField]]=1; allX.push(r[xField]); } });
    allX.sort();
    var keep = allX.slice(xField === 'date' ? -30 : -13);
    /* build lookup */
    var lookup = {};
    records.forEach(function(r) {
      if (!lookup[r.partner]) lookup[r.partner] = {};
      lookup[r.partner][r[xField]] = r.payout;
    });
    var filtered = selPartners.filter(function(p) { return lookup[p]; });
    var traces = filtered.map(function(p) {
      var color = PALETTE[PARTNER_IDX[p] % PALETTE.length];
      return {
        x: keep,
        y: keep.map(function(x) { return (lookup[p] && lookup[p][x]) || 0; }),
        name: p, type: 'bar',
        marker: { color: color },
        hovertemplate: (xField === 'date' ? '%{x}' : 'Wk %{x}') + '<br>' + p + ': $%{y:,.0f}<extra></extra>'
      };
    });
    /* totals trace — text on top of each stacked bar */
    var totals = keep.map(function(x) {
      var t = 0;
      filtered.forEach(function(p) { t += (lookup[p] && lookup[p][x]) || 0; });
      return t;
    });
    traces.push({
      x: keep, y: totals,
      text: totals.map(function(v) { return v > 0 ? fmtK(v) : ''; }),
      mode: 'text', type: 'scatter',
      textposition: 'top center',
      textfont: { size: 9, color: c.fc },
      showlegend: false, hoverinfo: 'skip'
    });
    Plotly.newPlot(el, traces, {
      barmode: 'stack', dragmode: false, height: 380,
      margin: { t:30, b:90, l:80, r:20 },
      legend: { orientation:'h', y:-0.4, font:{ size:11, color:c.fc } },
      xaxis: { tickangle:-45, tickfont:{ size:10, color:c.fc }, gridcolor:c.gc, automargin:true },
      yaxis: { tickformat:'$,.0f', tickfont:{ size:10, color:c.fc }, gridcolor:c.gc,
               title:{ text:'Payout $', font:{ size:11, color:c.fc } } },
      plot_bgcolor:'transparent', paper_bgcolor:c.pb,
      font: { family:'Inter,system-ui,sans-serif', color:c.fc }
    }, { responsive:true, displayModeBar:false, scrollZoom:false });
  }

  /* ── Heatmap table (day × partner, last 14 days) ── */
  function renderHeatmap(selPartners) {
    var tbl = document.getElementById('mon-heatmap-tbl');
    if (!tbl || !MON.daily || !MON.daily.length) return;
    var allDates = []; var ds = {};
    MON.daily.forEach(function(r) { if (!ds[r.date]) { ds[r.date]=1; allDates.push(r.date); } });
    allDates.sort();
    var dates = allDates.slice(-14);
    var data = {};
    MON.daily.forEach(function(r) {
      if (!data[r.partner]) data[r.partner] = {};
      data[r.partner][r.date] = r.payout;
    });
    var filtered = selPartners.filter(function(p) { return data[p]; });
    var allVals = MON.daily.filter(function(r) { return selPartners.indexOf(r.partner) >= 0; }).map(function(r) { return r.payout; });
    var maxVal = allVals.length ? Math.max.apply(null, allVals) : 1;
    var html = '<thead><tr><th style="white-space:nowrap">Partner</th>';
    dates.forEach(function(d) { html += '<th class="num" style="font-size:10px">' + d.slice(5) + '</th>'; });
    html += '<th class="num" style="font-size:10px">Total</th></tr></thead><tbody>';
    filtered.forEach(function(p) {
      var rowTot = 0;
      html += '<tr><td style="white-space:nowrap;font-weight:600;font-size:11px">' + p + '</td>';
      dates.forEach(function(d) {
        var v = (data[p] && data[p][d]) || 0; rowTot += v;
        var alpha = v > 0 ? (0.1 + 0.7 * v / maxVal).toFixed(2) : '0';
        html += '<td class="num" style="background:rgba(59,130,246,' + alpha + ');font-size:11px">' + fmtK(v) + '</td>';
      });
      html += '<td class="num" style="font-weight:700;font-size:11px">' + fmtK(rowTot) + '</td></tr>';
    });
    html += '<tr class="grand-total"><td><strong>Total</strong></td>';
    var gt = 0;
    dates.forEach(function(d) {
      var col = 0;
      filtered.forEach(function(p) { col += (data[p] && data[p][d]) || 0; });
      gt += col;
      html += '<td class="num" style="font-size:11px"><strong>' + fmtK(col) + '</strong></td>';
    });
    html += '<td class="num" style="font-weight:800;font-size:11px"><strong>' + fmtK(gt) + '</strong></td></tr></tbody>';
    tbl.innerHTML = html;
  }

  /* ── Month-on-Month chart ── */
  function renderMoMChart(isDark, selPartners) {
    var el = document.getElementById('mon-mom-chart');
    if (!el || !MON.monthly || !MON.monthly.length) return;
    var c = plotColors(isDark);
    var allMonths = []; var ms = {};
    MON.monthly.forEach(function(r) { if (!ms[r.month]) { ms[r.month]=1; allMonths.push(r.month); } });
    allMonths.sort();
    var lookup = {};
    MON.monthly.forEach(function(r) {
      if (!lookup[r.partner]) lookup[r.partner] = {};
      lookup[r.partner][r.month] = r.payout;
    });
    var filtered = selPartners.filter(function(p) { return lookup[p]; });
    var traces = filtered.map(function(p) {
      var color = PALETTE[PARTNER_IDX[p] % PALETTE.length];
      return {
        x: allMonths,
        y: allMonths.map(function(m) { return (lookup[p] && lookup[p][m]) || 0; }),
        name: p, type: 'bar',
        marker: { color: color },
        hovertemplate: '%{x}<br>' + p + ': $%{y:,.0f}<extra></extra>'
      };
    });
    /* totals on top */
    var totals = allMonths.map(function(m) {
      var t = 0; filtered.forEach(function(p) { t += (lookup[p] && lookup[p][m]) || 0; }); return t;
    });
    traces.push({
      x: allMonths, y: totals,
      text: totals.map(function(v) { return v > 0 ? fmtK(v) : ''; }),
      mode: 'text', type: 'scatter',
      textposition: 'top center',
      textfont: { size: 10, color: c.fc },
      showlegend: false, hoverinfo: 'skip'
    });
    Plotly.newPlot(el, traces, {
      barmode: 'stack', dragmode: false, height: 420,
      margin: { t:30, b:80, l:90, r:20 },
      legend: { orientation:'h', y:-0.25, font:{ size:11, color:c.fc } },
      xaxis: { tickangle:-30, tickfont:{ size:11, color:c.fc }, gridcolor:c.gc },
      yaxis: { tickformat:'$,.0f', tickfont:{ size:10, color:c.fc }, gridcolor:c.gc,
               title:{ text:'Payout $', font:{ size:11, color:c.fc } } },
      plot_bgcolor:'transparent', paper_bgcolor:c.pb,
      font: { family:'Inter,system-ui,sans-serif', color:c.fc }
    }, { responsive:true, displayModeBar:false, scrollZoom:false });
  }

  /* ── Month-on-Month table ── */
  function renderMoMTable(selPartners) {
    var tbl = document.getElementById('mon-mom-tbl');
    if (!tbl || !MON.monthly || !MON.monthly.length) return;
    var allMonths = []; var ms = {};
    MON.monthly.forEach(function(r) { if (!ms[r.month]) { ms[r.month]=1; allMonths.push(r.month); } });
    allMonths.sort();
    var data = {};
    MON.monthly.forEach(function(r) {
      if (!data[r.partner]) data[r.partner] = {};
      data[r.partner][r.month] = r.payout;
    });
    var filtered = selPartners.filter(function(p) { return data[p]; });
    var allVals = MON.monthly.filter(function(r) { return selPartners.indexOf(r.partner) >= 0; }).map(function(r) { return r.payout; });
    var maxVal = allVals.length ? Math.max.apply(null, allVals) : 1;
    var html = '<thead><tr><th>Partner</th>';
    allMonths.forEach(function(m) { html += '<th class="num" style="font-size:10px">' + m + '</th>'; });
    html += '<th class="num">Total</th></tr></thead><tbody>';
    filtered.forEach(function(p) {
      var rowTotal = 0;
      html += '<tr><td style="font-weight:600;white-space:nowrap;font-size:11px">' + p + '</td>';
      allMonths.forEach(function(m) {
        var v = (data[p] && data[p][m]) || 0; rowTotal += v;
        var alpha = v > 0 ? (0.08 + 0.55 * v / maxVal).toFixed(2) : '0';
        html += '<td class="num" style="background:rgba(59,130,246,' + alpha + ');font-size:11px">' + (v > 0 ? fmtK(v) : '—') + '</td>';
      });
      html += '<td class="num" style="font-weight:700;font-size:11px">' + fmtK(rowTotal) + '</td></tr>';
    });
    html += '<tr class="grand-total"><td><strong>Total</strong></td>';
    var grandTotal = 0;
    allMonths.forEach(function(m) {
      var col = 0; filtered.forEach(function(p) { col += (data[p] && data[p][m]) || 0; }); grandTotal += col;
      html += '<td class="num" style="font-size:11px"><strong>' + fmtK(col) + '</strong></td>';
    });
    html += '<td class="num" style="font-weight:800;font-size:11px"><strong>' + fmtK(grandTotal) + '</strong></td></tr></tbody>';
    tbl.innerHTML = html;
  }

  function buildMonitor() {
    if (!window.Plotly || !MON) return;
    buildPartnerFilter();
    applyFilter();
  }

  document.addEventListener('DOMContentLoaded', function() {
    buildMonitor();
    var tab2Radio = document.getElementById('tab2');
    if (tab2Radio) tab2Radio.addEventListener('change', function() {
      if (!this.checked) return;
      var sel = getSelectedPartners(); var isDark = document.documentElement.classList.contains('dark');
      setTimeout(function() {
        try { ['mon-daily-chart','mon-weekly-chart','mon-mom-chart'].forEach(function(id) {
          var el = document.getElementById(id); if (window.Plotly && el && el._fullLayout) Plotly.Plots.resize(el);
        }); } catch(e) {}
      }, 50);
    });
    document.querySelector('.dark-toggle') && document.querySelector('.dark-toggle').addEventListener('click', function() {
      setTimeout(applyFilter, 50);
    });
  });
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

/* ── Enrolls tab ── */
(function() {
  var _enr = {{ enroll_data_json }};
  var ENR         = _enr.raw     || [];
  var ENR_MONTHLY = _enr.monthly || [];
  var ENR_COHORT  = _enr.cohort  || [];
  var ENR_IMP     = _enr.imp     || [];
  var PAL = ['#3b82f6','#8b5cf6','#0d9488','#f97316','#e11d48','#22c55e','#f59e0b','#6366f1','#ec4899','#84cc16','#06b6d4','#a78bfa'];

  var enrSort    = {col:'enroll_date', asc:false};
  var enrFilters = {partner:'', cohort:'', imp:''};

  function uniq(data, key) {
    var seen = {}, out = [];
    data.forEach(function(r){ if(r[key] && !seen[r[key]]){ seen[r[key]]=1; out.push(r[key]); } });
    return out.sort();
  }

  function last13(data, key) {
    var months = uniq(data, key);
    var cutoff = months.length > 13 ? months[months.length - 13] : (months[0] || '');
    return data.filter(function(r){ return r[key] >= cutoff; });
  }

  function fmt$(n){ return n==null?'':'$'+n.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}); }
  function fmtN(n){ return n==null?'':n.toLocaleString('en-US'); }

  /* ── Raw table ── */
  function populateFilter(id, key) {
    var sel = document.getElementById(id); if (!sel) return;
    var seen = {}, vals = [];
    ENR.forEach(function(r){ if(r[key] && !seen[r[key]]){ seen[r[key]]=1; vals.push(r[key]); } });
    vals.sort().forEach(function(v){ var o=document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); });
    sel.addEventListener('change', function() {
      enrFilters[key==='partner'?'partner':key==='payout_cohort_bucket'?'cohort':'imp'] = this.value;
      renderEnrTable();
    });
  }

  function renderEnrTable() {
    var rows = ENR.filter(function(r){
      return (!enrFilters.partner||r.partner===enrFilters.partner)
          && (!enrFilters.cohort||r.payout_cohort_bucket===enrFilters.cohort)
          && (!enrFilters.imp||r.imp_source===enrFilters.imp);
    });
    rows.sort(function(a,b){
      var av=a[enrSort.col]||'', bv=b[enrSort.col]||'';
      return enrSort.asc?(av>bv?1:av<bv?-1:0):(av<bv?1:av>bv?-1:0);
    });
    var tbody = document.getElementById('enr-tbody'); if (!tbody) return;
    tbody.innerHTML = rows.map(function(r){
      return '<tr><td>'+(r.enroll_date||'')+'</td><td>'+(r.partner||'')+'</td><td>'+(r.imp_source||'')+'</td><td>'+(r.payout_cohort_bucket||'')+'</td>'
        +'<td style="text-align:right">'+fmtN(r.enrolled_users)+'</td><td style="text-align:right">'+fmtN(r.total_leads)+'</td>'
        +'<td style="text-align:right">'+fmt$(r.total_payout)+'</td><td style="text-align:right">'+fmt$(r.avg_payout)+'</td></tr>';
    }).join('');
    var rc=document.getElementById('enr-row-count'); if(rc) rc.textContent=rows.length+' rows';
  }

  /* ── Charts + pivot tables ── */
  function baseLayout(dark) {
    var bg=dark?'#1e1e2e':'#ffffff', fc=dark?'#e2e8f0':'#1a1a2e', gc=dark?'rgba(255,255,255,.07)':'rgba(0,0,0,.06)';
    return {paper_bgcolor:bg,plot_bgcolor:bg,height:320,font:{family:'Inter,system-ui,sans-serif',size:11,color:fc},
      margin:{t:36,r:16,b:52,l:64},legend:{orientation:'h',y:-0.2,font:{size:10}},
      xaxis:{gridcolor:gc,tickfont:{size:10,color:fc}},yaxis:{gridcolor:gc,tickfont:{size:10,color:fc},zeroline:false}};
  }
  function titleFont(dark){ return {size:13,color:dark?'#e2e8f0':'#1a1a2e',family:'Inter,system-ui,sans-serif'}; }
  function isDark(){ return document.documentElement.classList.contains('dark'); }

  function buildEnrCharts() {
    if (!window.Plotly) return;
    var dark = isDark();

    /* Chart 1 */
    var d1=last13(ENR_MONTHLY,'enroll_month'), m1=uniq(d1,'enroll_month'), p1=uniq(d1,'partner');
    Plotly.newPlot('enr-chart-monthly', p1.map(function(p,i){
      var bm={}; d1.filter(function(r){return r.partner===p;}).forEach(function(r){bm[r.enroll_month]=r.enrolled_users;});
      return {x:m1,y:m1.map(function(m){return bm[m]||0;}),name:p,type:'scatter',mode:'lines+markers',
        line:{color:PAL[i%PAL.length],width:2},marker:{size:5,color:PAL[i%PAL.length]}};
    }), Object.assign({},baseLayout(dark),{title:{text:'Monthly Enrollments by Partner',font:titleFont(dark),x:0.02},
      yaxis:Object.assign({},baseLayout(dark).yaxis,{title:'Enrolled Users'})}),{responsive:true,displayModeBar:false});

    /* Chart 2 + Table */
    var d2=last13(ENR_COHORT,'enroll_month'), m2=uniq(d2,'enroll_month'), b2=uniq(d2,'payout_cohort_bucket');
    Plotly.newPlot('enr-chart-cohort', b2.map(function(b,i){
      var bm={}; d2.filter(function(r){return r.payout_cohort_bucket===b;}).forEach(function(r){bm[r.enroll_month]=r.total_payout;});
      return {x:m2,y:m2.map(function(m){return bm[m]||0;}),name:b,type:'bar',marker:{color:PAL[i%PAL.length]}};
    }), Object.assign({},baseLayout(dark),{barmode:'stack',title:{text:'Payout by Enroll Cohort',font:titleFont(dark),x:0.02},
      yaxis:Object.assign({},baseLayout(dark).yaxis,{title:'Total Payout ($)',tickformat:'$,.0f'})}),{responsive:true,displayModeBar:false});
    (function(){
      var tbl=document.getElementById('enr-tbl-cohort'); if(!tbl) return;
      var lk={}, cT={}, gT=0;
      d2.forEach(function(r){lk[r.enroll_month+'/'+r.payout_cohort_bucket]=r.total_payout||0;});
      b2.forEach(function(b){cT[b]=0;});
      var rows=m2.map(function(m){
        var rT=0, cells=b2.map(function(b){var v=lk[m+'/'+b]||0;rT+=v;cT[b]+=v;gT+=v;return v;});
        return {month:m,cells:cells,rT:rT};
      });
      tbl.innerHTML='<thead><tr><th>Enroll Month</th>'+b2.map(function(b){return '<th style="text-align:right">'+b+'</th>';}).join('')+'<th style="text-align:right;font-weight:700">Total</th></tr></thead>'
        +'<tbody>'+rows.map(function(r){return '<tr><td>'+r.month+'</td>'+r.cells.map(function(v){return '<td style="text-align:right">'+(v?fmt$(v):'—')+'</td>';}).join('')+'<td style="text-align:right;font-weight:700">'+fmt$(r.rT)+'</td></tr>';}).join('')
        +'<tr style="font-weight:700;border-top:2px solid var(--border)"><td>Total</td>'+b2.map(function(b){return '<td style="text-align:right">'+fmt$(cT[b])+'</td>';}).join('')+'<td style="text-align:right">'+fmt$(gT)+'</td></tr></tbody>';
    })();

    /* Chart 3 + Table */
    var d3=last13(ENR_IMP,'enroll_month');
    var totals={}; d3.forEach(function(r){totals[r.imp_source]=(totals[r.imp_source]||0)+r.enrolled_users;});
    var top8=Object.keys(totals).sort(function(a,b){return totals[b]-totals[a];}).slice(0,8);
    var m3=uniq(d3,'enroll_month');
    Plotly.newPlot('enr-chart-imp', top8.map(function(src,i){
      var bm={}; d3.filter(function(r){return r.imp_source===src;}).forEach(function(r){bm[r.enroll_month]=r.enrolled_users;});
      return {x:m3,y:m3.map(function(m){return bm[m]||0;}),name:src,type:'bar',marker:{color:PAL[i%PAL.length]}};
    }), Object.assign({},baseLayout(dark),{barmode:'stack',title:{text:'Enrollments by Imp Source (top 8)',font:titleFont(dark),x:0.02},
      yaxis:Object.assign({},baseLayout(dark).yaxis,{title:'Enrolled Users'})}),{responsive:true,displayModeBar:false});
    (function(){
      var tbl=document.getElementById('enr-tbl-imp'); if(!tbl) return;
      var lk={}, cT={}, gT=0;
      d3.forEach(function(r){lk[r.enroll_month+'/'+r.imp_source]=r.enrolled_users||0;});
      top8.forEach(function(s){cT[s]=0;});
      var rows=m3.map(function(m){
        var rT=0, cells=top8.map(function(s){var v=lk[m+'/'+s]||0;rT+=v;cT[s]+=v;gT+=v;return v;});
        return {month:m,cells:cells,rT:rT};
      });
      tbl.innerHTML='<thead><tr><th>Enroll Month</th>'+top8.map(function(s){return '<th style="text-align:right">'+s+'</th>';}).join('')+'<th style="text-align:right;font-weight:700">Total</th></tr></thead>'
        +'<tbody>'+rows.map(function(r){return '<tr><td>'+r.month+'</td>'+r.cells.map(function(v){return '<td style="text-align:right">'+(v||'—')+'</td>';}).join('')+'<td style="text-align:right;font-weight:700">'+fmtN(r.rT)+'</td></tr>';}).join('')
        +'<tr style="font-weight:700;border-top:2px solid var(--border)"><td>Total</td>'+top8.map(function(s){return '<td style="text-align:right">'+fmtN(cT[s])+'</td>';}).join('')+'<td style="text-align:right">'+fmtN(gT)+'</td></tr></tbody>';
    })();
  }

  document.addEventListener('DOMContentLoaded', function(){
    populateFilter('enr-filter-partner','partner');
    populateFilter('enr-filter-cohort','payout_cohort_bucket');
    populateFilter('enr-filter-imp','imp_source');
    document.querySelectorAll('#enr-table th[data-col]').forEach(function(th){
      th.addEventListener('click', function(){
        var col=this.getAttribute('data-col');
        if(enrSort.col===col){enrSort.asc=!enrSort.asc;}else{enrSort.col=col;enrSort.asc=col==='enroll_date'?false:true;}
        renderEnrTable();
      });
    });
    renderEnrTable();
    buildEnrCharts();
  });
  var dmBtn=document.querySelector('.dark-toggle');
  if(dmBtn) dmBtn.addEventListener('click',function(){setTimeout(buildEnrCharts,50);});
})();

// ── Refresh button ────────────────────────────────────────────────────────────
(function() {
  var API = window.location.protocol + '//' + window.location.hostname + ':8765';
  var pollTimer = null;

  function btn() { return document.getElementById('refreshBtn'); }

  function setState(state, label) {
    var b = btn();
    b.className = 'refresh-btn' + (state ? ' ' + state : '');
    b.disabled = (state === 'running');
    b.innerHTML = label;
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(poll, 4000);
  }

  function poll() {
    fetch(API + '/api/refresh-status')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'running') return;
        clearInterval(pollTimer);
        if (d.status === 'success') {
          setState('success', '&#x2713; Done — reloading');
          setTimeout(function() { window.location.reload(); }, 1200);
        } else {
          setState('error', '&#x2715; Failed');
        }
      })
      .catch(function() { /* keep polling */ });
  }

  window.triggerRefresh = function() {
    setState('running', '<span class="spin">&#x21bb;</span> Refreshing…');
    fetch(API + '/api/refresh', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'started' || d.status === 'already_running') startPolling();
      })
      .catch(function() {
        setState('error', '&#x2715; Server unreachable');
      });
  };

  // On load: resume spinner if a refresh is already in progress
  window.addEventListener('load', function() {
    fetch(API + '/api/refresh-status')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'running') {
          setState('running', '<span class="spin">&#x21bb;</span> Refreshing…');
          startPolling();
        }
      })
      .catch(function() {}); // refresh_server not running — button stays idle
  });
})();

// ── C1B Refresh ───────────────────────────────────────────────────────────────
(function() {
  var API = window.location.protocol + '//' + window.location.hostname + ':8765';
  var pollTimer = null;

  function btn()    { return document.getElementById('c1bRefreshBtn'); }
  function status() { return document.getElementById('c1bStatusText'); }

  function setState(state, label, msg) {
    var b = btn(); if (!b) return;
    b.className = 'c1b-refresh-btn' + (state ? ' ' + state : '');
    b.disabled  = (state === 'running');
    b.innerHTML = label;
    if (status()) status().textContent = msg || '';
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(poll, 4000);
  }

  function poll() {
    fetch(API + '/api/c1b-refresh-status')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'running') return;
        clearInterval(pollTimer);
        if (d.status === 'success') {
          setState('success', '&#x2713; Done', 'Updated ' + (d.finished_at || ''));
          var f = document.getElementById('c1bFrame');
          if (f) f.src = 'c1b_dashboard.html?t=' + Date.now();
        } else {
          setState('error', '&#x2715; Failed', d.error || '');
        }
      })
      .catch(function() {});
  }

  window.triggerC1BRefresh = function() {
    setState('running', '<span class="c1b-spin">&#x21bb;</span> Refreshing…', 'Running queries…');
    fetch(API + '/api/refresh-c1b', { method: 'POST' })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'started' || d.status === 'already_running') startPolling();
      })
      .catch(function() { setState('error', '&#x2715; Server unreachable', ''); });
  };

  window.addEventListener('load', function() {
    fetch(API + '/api/c1b-refresh-status')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.status === 'running') {
          setState('running', '<span class="c1b-spin">&#x21bb;</span> Refreshing…', 'Running queries…');
          startPolling();
        } else if (d.finished_at) {
          if (status()) status().textContent = 'Last: ' + d.finished_at;
        }
      })
      .catch(function() {});
  });
})();
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
        close_month = config.default_close_month()

    signoffs = manual_inputs.get("signoffs", {})

    def load_json(name):
        p = os.path.join(config.COMPUTED_DIR, name)
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
        return None

    def read_sql(filename):
        p = os.path.join(config.QUERIES_DIR, filename)
        if os.path.exists(p):
            with open(p) as f:
                return f.read().strip()
        return f"-- {filename} not found"

    l1 = load_json("l1_results.json")
    l3 = load_json("l3_live_results.json")
    monitor = load_json("monitor_data.json")
    enroll = load_json("enroll_data.json") or {"raw": [], "monthly": [], "cohort": [], "imp": []}

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

    l1_months = sorted(set(r.get("payout_month") or r.get("month", "") for r in l1["monthly_detail"] if not r.get("is_total_row")), reverse=True) if l1 else []
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
        "l1": to_dot(l1) if l1 else None,
        "l3": to_dot(l3) if l3 else None,
        "l1_months": l1_months,
        "l3_coll_months": l3_coll_months,
        "signoffs": to_dot(signoffs),
        "partner_config": {k: DotDict(v) for k, v in config.PARTNER_CONFIG.items()},
        "partner_display": config.PARTNER_DISPLAY_NAMES,
        "health_log": to_dot(health_log),
        "email_log": to_dot(email_log),
        "chart_data_json": json.dumps(l1["monthly_detail"] if l1 else []),
        "monitor_data_json": json.dumps(monitor if monitor else {"kpis": {}, "daily": [], "weekly": [], "monthly": []}),
        "enroll_data_json":  json.dumps(enroll),
        "sql_reports": read_sql("reports_by_payout_cycle.sql"),
        "sql_daily":   read_sql("daily_by_partner.sql"),
        "sql_weekly":  read_sql("weekly_by_partner.sql"),
        "sql_monthly": read_sql("monthly_by_partner.sql"),
    }

    tmpl = Template(TEMPLATE)
    html = tmpl.render(**ctx)

    with open(config.OUTPUT_HTML, "w") as f:
        f.write(html)
    print(f"[dashboard] Written → index.html ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
