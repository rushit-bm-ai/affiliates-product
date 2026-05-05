"""Invoice vs Cash — daily email report + SMTP sender."""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from collections import defaultdict

import config


# ── Formatters ───────────────────────────────────────────────────────────────
def _f(val, prefix="$"):
    if val is None: return "—"
    return f"{prefix}{val:,.2f}"

def _f0(val, prefix="$"):
    if val is None: return "—"
    return f"{prefix}{val:,.0f}"

def _pct(val):
    if val is None: return "—"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.1f}%"

def _clr(val):
    if val is None: return "#5c626e"
    return "#0f4625" if val >= 0 else "#b91c1c"

def _pc(p):
    return {
        "moneylion":  "#3b82f6",
        "amone":      "#8b5cf6",
        "kashkick":   "#0d9488",
        "freecash":   "#17c95f",
        "brigit":     "#f97316",
        "supermoney": "#e11d48",
    }.get(p, "#5c626e")

def _dot(p):
    return (f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background:{_pc(p)};margin-right:7px;vertical-align:middle"></span>')

def _badge(status, text=None):
    label = text or status
    m = {
        "Low":     ("#dcfce7", "#0f4625"),
        "GREEN":   ("#dcfce7", "#0f4625"),
        "Medium":  ("#fef3c7", "#92400e"),
        "AMBER":   ("#fef3c7", "#92400e"),
        "High":    ("#fef2f2", "#b91c1c"),
        "RED":     ("#fef2f2", "#b91c1c"),
        "PENDING": ("#f1f5f9", "#5c626e"),
        "GREY":    ("#f1f5f9", "#5c626e"),
    }
    bg, fg = m.get(status, ("#f1f5f9", "#5c626e"))
    return (f'<span style="background:{bg};color:{fg};padding:3px 11px;border-radius:20px;'
            f'font-size:10px;font-weight:700;white-space:nowrap;letter-spacing:0.2px">{label}</span>')

# Base cell styles
TH  = ('padding:11px 14px;font-size:9px;text-transform:uppercase;letter-spacing:1px;'
       'color:#5c626e;font-weight:700;border-bottom:2px solid #e3f1e7;white-space:nowrap;'
       'background:#f4f9f5')
TD  = ('padding:10px 14px;border-bottom:1px solid #f0f7f2;font-size:11.5px;color:#1a2e1e;'
       "font-family:'Figtree','Segoe UI',system-ui,sans-serif")
TDR = f'{TD};text-align:right;font-family:"Courier New",monospace'
TDC = f'{TD};text-align:center'


# ── Change detection ─────────────────────────────────────────────────────────
def compute_changes(prev_l3, curr_l3):
    """Compare prev snapshot vs current l3 → new invoices and new cash received."""
    empty = {"new_invoices": [], "new_cash": []}
    if not prev_l3 or not curr_l3:
        return empty

    def key(r):
        return (r.get("partner"), r.get("payout_month"), r.get("cycle", ""), r.get("billed"))

    prev_map = {key(r): r for r in (prev_l3.get("yet_to_receive", []) + prev_l3.get("collected", []))}
    curr_all = curr_l3.get("yet_to_receive", []) + curr_l3.get("collected", [])

    new_invoices, new_cash = [], []
    for r in curr_all:
        k    = key(r)
        prev = prev_map.get(k)
        if prev is None:
            if r.get("received") is not None and (r.get("received") or 0) > 0:
                new_cash.append(r)
            else:
                new_invoices.append(r)
        else:
            prev_recv = prev.get("received") or 0
            curr_recv = r.get("received") or 0
            if curr_recv > 0 and prev_recv != curr_recv:
                new_cash.append(r)

    return {"new_invoices": new_invoices, "new_cash": new_cash}


# ── HTML builder ─────────────────────────────────────────────────────────────
def generate_email_html(l3, changes=None, stale=False, data_age=""):
    if changes is None:
        changes = {"new_invoices": [], "new_cash": []}

    now_ist     = config.now_ist().strftime("%d %b %Y, %I:%M %p IST")
    close_month = l3.get("close_month", "—")
    gt          = l3.get("grand_total", {})
    collected   = l3.get("collected", [])
    ytr_list    = l3.get("yet_to_receive", [])
    cum_list    = l3.get("cumulative", [])

    total_billed   = gt.get("total_billed",   0) or 0
    total_received = gt.get("total_received", 0) or 0
    yet_to_receive = gt.get("yet_to_receive", 0) or 0
    net_delta      = gt.get("net_delta",      0) or 0
    coll_pct       = gt.get("collection_pct", 0) or 0

    delta_pos    = net_delta >= 0
    delta_bg     = "#e8f8ef" if delta_pos else "#fef2f2"
    delta_border = "#a7f3c8" if delta_pos else "#fecaca"
    delta_clr    = "#0f4625" if delta_pos else "#b91c1c"
    delta_label  = (f"+{_f0(net_delta)}" if delta_pos else _f0(net_delta))
    delta_sub    = "Cash &gt; Invoice" if delta_pos else "Cash &lt; Invoice"

    new_inv  = changes.get("new_invoices", [])
    new_cash = changes.get("new_cash",     [])

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    kpis = f"""
<table width="100%" cellpadding="0" cellspacing="0">
  <tr>
    <td width="50%" style="padding-right:8px;padding-bottom:8px">
      <div style="background:#f4f9f5;border:1px solid #d1e8d8;border-radius:16px;padding:24px 20px 20px;text-align:center">
        <div style="font-size:11px;color:#5c626e;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:10px">Net Billed</div>
        <div style="font-size:30px;font-weight:900;color:#0e1e14;letter-spacing:-1px;line-height:1">{_f0(total_billed)}</div>
        <div style="font-size:10px;color:#5c626e;margin-top:6px">Total invoiced to partners</div>
      </div>
    </td>
    <td width="50%" style="padding-left:0;padding-bottom:8px">
      <div style="background:#e8f8ef;border:1px solid #a7f3c8;border-radius:16px;padding:24px 20px 20px;text-align:center">
        <div style="font-size:11px;color:#0f4625;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:10px">Net Received</div>
        <div style="font-size:30px;font-weight:900;color:#0f4625;letter-spacing:-1px;line-height:1">{_f0(total_received)}</div>
        <div style="font-size:10px;color:#17c95f;margin-top:6px;font-weight:700">{coll_pct:.1f}% collected so far</div>
      </div>
    </td>
  </tr>
  <tr>
    <td width="50%" style="padding-right:8px;padding-top:0">
      <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:16px;padding:24px 20px 20px;text-align:center">
        <div style="font-size:11px;color:#92400e;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:10px">Yet to Receive</div>
        <div style="font-size:30px;font-weight:900;color:#92400e;letter-spacing:-1px;line-height:1">{_f0(yet_to_receive)}</div>
        <div style="font-size:10px;color:#b45309;margin-top:6px;font-weight:600">{len(ytr_list)} invoice(s) pending collection</div>
      </div>
    </td>
    <td width="50%" style="padding-left:0;padding-top:0">
      <div style="background:{delta_bg};border:1px solid {delta_border};border-radius:16px;padding:24px 20px 20px;text-align:center">
        <div style="font-size:11px;color:{delta_clr};text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:10px">Overall Delta</div>
        <div style="font-size:30px;font-weight:900;color:{delta_clr};letter-spacing:-1px;line-height:1">{delta_label}</div>
        <div style="font-size:10px;color:{delta_clr};margin-top:6px;font-weight:700">{delta_sub}</div>
      </div>
    </td>
  </tr>
</table>"""

    # ── What's New Since Last Refresh ─────────────────────────────────────────
    def new_section(title, rows, border_clr, hdr_bg, hdr_fg, is_cash=False):
        if not rows:
            return ""
        body = ""
        for i, r in enumerate(rows):
            bg = f' style="background:#fafcfa"' if i % 2 else ""
            body += (
                f'<tr{bg}>'
                f'<td style="{TD}">{_dot(r["partner"])}<strong>{r["display_name"]}</strong></td>'
                f'<td style="{TD};color:#5c626e">{r.get("payout_month","—")}</td>'
                f'<td style="{TDR}">{_f0(r.get("billed",0))}</td>'
                + (f'<td style="{TDR};color:#0f4625;font-weight:700">+{_f0(r.get("received",0))}</td>' if is_cash else '')
                + f'<td style="{TDC}">{_badge("PENDING" if not is_cash else "Low")}</td>'
                f'</tr>'
            )
        cash_col = f'<th style="{TH};color:{hdr_fg};text-align:right">Cash Received</th>' if is_cash else ""
        return f"""
<div style="margin-bottom:18px">
  <div style="font-size:11px;font-weight:700;color:{hdr_fg};margin-bottom:10px;display:flex;align-items:center">
    {title}
    <span style="background:{hdr_bg};color:{hdr_fg};padding:2px 10px;border-radius:20px;font-size:10px;font-weight:700;margin-left:8px;border:1px solid {border_clr}">{len(rows)} new</span>
  </div>
  <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid {border_clr};border-radius:12px;overflow:hidden">
    <tr style="background:{hdr_bg}">
      <th style="{TH};color:{hdr_fg};text-align:left">Partner</th>
      <th style="{TH};color:{hdr_fg};text-align:left">Payout Month</th>
      <th style="{TH};color:{hdr_fg};text-align:right">Billed</th>
      {cash_col}
      <th style="{TH};color:{hdr_fg};text-align:center">Status</th>
    </tr>
    {body}
  </table>
</div>"""

    if new_inv or new_cash:
        changes_html = (
            new_section("New Invoices Raised",   new_inv,  "#bfdbfe", "#eff6ff", "#1d4ed8", is_cash=False) +
            new_section("New Cash Received",      new_cash, "#a7f3c8", "#e8f8ef", "#0f4625", is_cash=True)
        )
    else:
        changes_html = ('<div style="color:#5c626e;font-size:12px;font-style:italic;padding:10px 0">'
                        'No new invoices or payments since last refresh.</div>')

    # ── Table 1: Cumulative by Partner ────────────────────────────────────────
    cum_rows = ""
    for i, r in enumerate(cum_list):
        bg = f' style="background:#fafcfa"' if i % 2 else ""
        nd = r.get("net_delta", 0) or 0
        cum_rows += (
            f'<tr{bg}>'
            f'<td style="{TD}">{_dot(r["partner"])}<strong>{r["display_name"]}</strong></td>'
            f'<td style="{TDR}">{_f0(r.get("total_billed",   0))}</td>'
            f'<td style="{TDR};color:#0f4625;font-weight:700">{_f0(r.get("total_received", 0))}</td>'
            f'<td style="{TDR};color:#92400e">{_f0(r.get("yet_to_receive",  0))}</td>'
            f'<td style="{TDR};color:{_clr(nd)};font-weight:800">{_f0(nd)}</td>'
            f'<td style="{TDC}">{r.get("payment_term","—")}d</td>'
            f'</tr>'
        )
    # Grand total
    cum_rows += (
        f'<tr style="background:#e3f1e7">'
        f'<td style="{TD};border-top:2px solid #17c95f"><strong>Grand Total</strong></td>'
        f'<td style="{TDR};border-top:2px solid #17c95f;font-weight:700">{_f0(total_billed)}</td>'
        f'<td style="{TDR};color:#0f4625;font-weight:800;border-top:2px solid #17c95f">{_f0(total_received)}</td>'
        f'<td style="{TDR};color:#92400e;font-weight:700;border-top:2px solid #17c95f">{_f0(yet_to_receive)}</td>'
        f'<td style="{TDR};color:{delta_clr};font-weight:900;border-top:2px solid #17c95f">{delta_label}</td>'
        f'<td style="{TDC};border-top:2px solid #17c95f">—</td>'
        f'</tr>'
    )

    table1_footnote = f"""
<div style="margin-top:10px;padding:10px 16px;background:#f4f9f5;border-radius:10px;border-left:3px solid #17c95f;font-size:10.5px;color:#5c626e;line-height:1.6">
  <strong style="color:#0f4625">&#43; Net Delta</strong> = Cash received &gt; Invoice
  &nbsp;<span style="color:#17c95f;font-weight:700">&#10003; Good for Bright</span>
  &nbsp;&nbsp;&nbsp;
  <strong style="color:#b91c1c">&minus; Net Delta</strong> = Cash received &lt; Invoice
  &nbsp;<span style="color:#b91c1c;font-weight:700">&#9888; Needs deep dive</span>
</div>"""

    table1 = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1e8d8;border-radius:14px;overflow:hidden">
  <tr>
    <th style="{TH};text-align:left">Partner</th>
    <th style="{TH};text-align:right">Billed</th>
    <th style="{TH};text-align:right">Received</th>
    <th style="{TH};text-align:right">Yet to Receive</th>
    <th style="{TH};text-align:right">Net Delta</th>
    <th style="{TH};text-align:center">Term</th>
  </tr>
  {cum_rows}
</table>
{table1_footnote}"""

    # ── Table 3: Yet to Receive (shown FIRST before table 2) ─────────────────
    ytr_total = sum(r.get("billed", 0) or 0 for r in ytr_list)
    ytr_rows  = ""
    for i, r in enumerate(ytr_list):
        bg = f' style="background:#fffdf5"' if i % 2 else ""
        ytr_rows += (
            f'<tr{bg}>'
            f'<td style="{TD}">{_dot(r["partner"])}<strong>{r["display_name"]}</strong></td>'
            f'<td style="{TD};color:#5c626e">{r.get("payout_month","—")}</td>'
            f'<td style="{TDR};font-weight:700;color:#92400e">{_f0(r.get("billed",0))}</td>'
            f'<td style="{TD};color:#5c626e">{r.get("expected_collection") or "—"}</td>'
            f'<td style="{TDC}">{_badge("PENDING")}</td>'
            f'</tr>'
        )
    ytr_rows += (
        f'<tr style="background:#fef3c7">'
        f'<td style="{TD};border-top:2px solid #fbbf24;font-weight:800" colspan="2">Total Pending</td>'
        f'<td style="{TDR};border-top:2px solid #fbbf24;font-weight:900;color:#92400e">{_f0(ytr_total)}</td>'
        f'<td style="{TD};border-top:2px solid #fbbf24" colspan="2"></td>'
        f'</tr>'
    )

    table3 = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #fde68a;border-radius:14px;overflow:hidden">
  <tr style="background:#fffbeb">
    <th style="{TH};color:#92400e;text-align:left">Partner</th>
    <th style="{TH};color:#92400e;text-align:left">Payout Month</th>
    <th style="{TH};color:#92400e;text-align:right">Invoice Amount</th>
    <th style="{TH};color:#92400e;text-align:left">Expected Collection</th>
    <th style="{TH};color:#92400e;text-align:center">Status</th>
  </tr>
  {ytr_rows}
</table>"""

    # ── Table 2: Last 3 months per partner ───────────────────────────────────
    by_partner = defaultdict(list)
    for r in sorted(collected, key=lambda r: (r["partner"], r.get("payout_month", ""))):
        by_partner[r["partner"]].append(r)

    coll_rows     = ""
    total_shown   = 0
    for partner, rows in by_partner.items():
        # Last 3 months per partner (most recent first, then display ascending)
        trimmed = sorted(rows, key=lambda r: r.get("payout_month", ""), reverse=True)[:3]
        trimmed = sorted(trimmed, key=lambda r: r.get("payout_month", ""))
        total_shown += len(trimmed)

        p_billed   = sum(r.get("billed",    0) or 0 for r in trimmed)
        p_received = sum(r.get("received",  0) or 0 for r in trimmed)
        p_delta    = sum(r.get("net_delta", 0) or 0 for r in trimmed)

        # Partner header
        coll_rows += (
            f'<tr style="background:#e3f1e7">'
            f'<td style="{TD};font-weight:700;font-size:11px;color:#0f4625;letter-spacing:0.3px" colspan="2">'
            f'{_dot(partner)}{rows[0]["display_name"]}'
            f'<span style="font-size:9px;color:#5c626e;font-weight:400;margin-left:6px">(last 3 months)</span>'
            f'</td>'
            f'<td style="{TDR};font-weight:700;font-size:11px">{_f0(p_billed)}</td>'
            f'<td style="{TDR};color:#0f4625;font-weight:700;font-size:11px">{_f0(p_received)}</td>'
            f'<td style="{TDR};color:{_clr(p_delta)};font-weight:700;font-size:11px">{_f0(p_delta)}</td>'
            f'<td style="{TDC}"></td>'
            f'</tr>'
        )
        for i, r in enumerate(trimmed):
            bg = ' style="background:#fafcfa"' if i % 2 else ""
            coll_rows += (
                f'<tr{bg}>'
                f'<td style="{TD};padding-left:28px;color:#5c626e;font-size:10.5px">{r.get("payout_month","—")}</td>'
                f'<td style="{TD};color:#5c626e;font-size:10.5px">{r.get("collection_month","—")}</td>'
                f'<td style="{TD};font-size:10.5px;font-weight:700;color:#0f4625">{r.get("cycle","—")}</td>'
                f'<td style="{TDR};font-size:10.5px">{_f0(r.get("billed",0))}</td>'
                f'<td style="{TDR};color:#0f4625;font-size:10.5px">{_f0(r.get("received",0))}</td>'
                f'<td style="{TDR};color:{_clr(r.get("net_delta"))};font-size:10.5px">{_f0(r.get("net_delta",0))}</td>'
                f'<td style="{TDC}">{_badge(r.get("net_status","—"))}</td>'
                f'</tr>'
            )

    table2 = f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1e8d8;border-radius:14px;overflow:hidden">
  <tr>
    <th style="{TH};text-align:left">Payout Month</th>
    <th style="{TH};text-align:left">Collection Month</th>
    <th style="{TH};text-align:left">Cycle</th>
    <th style="{TH};text-align:right">Billed</th>
    <th style="{TH};text-align:right">Received</th>
    <th style="{TH};text-align:right">Net Delta</th>
    <th style="{TH};text-align:center">Status</th>
  </tr>
  {coll_rows}
</table>
<div style="font-size:10px;color:#5c626e;margin-top:8px;text-align:right">
  Showing last 3 months per partner ({total_shown} of {len(collected)} rows) &nbsp;·&nbsp;
  <a href="http://10.0.204.191/affiliates-recon-dashboard" style="color:#17c95f;text-decoration:none;font-weight:600">View all on dashboard &rarr;</a>
</div>"""

    # ── Section wrapper ───────────────────────────────────────────────────────
    def section(title, subtitle, content, badge=None):
        badge_html = (
            f' <span style="background:#e3f1e7;color:#0f4625;padding:2px 10px;'
            f'border-radius:20px;font-size:10px;font-weight:700;border:1px solid #a7f3c8">{badge}</span>'
        ) if badge else ""
        return f"""
<tr><td style="padding:32px 36px 0">
  <div style="border-left:4px solid #17c95f;padding-left:14px;margin-bottom:18px">
    <div style="font-size:15px;font-weight:800;color:#0e1e14;letter-spacing:-0.3px">{title}{badge_html}</div>
    <div style="font-size:11px;color:#5c626e;margin-top:3px">{subtitle}</div>
  </div>
  {content}
</td></tr>"""

    # ── Full HTML ─────────────────────────────────────────────────────────────
    stale_banner = (
        f'<tr><td style="padding:12px 40px 0">\n'
        f'  <div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:12px;padding:14px 20px">'
        f'    <div style="font-size:13px;font-weight:800;color:#92400e">&#9888;&nbsp; Using Existing Data &mdash; Dashboard Refresh May Have Failed</div>'
        f'    <div style="font-size:11px;color:#b45309;margin-top:4px">Data was last refreshed <strong>{data_age}</strong>. '
        f'The daily refresh job may not have run successfully. Tables below show the most recently available data.</div>'
        f'  </div>\n'
        f'</td></tr>'
    ) if stale else ""
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Daily Data Refresh — Invoice vs Cash</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#eef2ee;font-family:'Figtree','Segoe UI',system-ui,-apple-system,sans-serif;color:#0e1e14">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2ee;padding:32px 0">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0"
       style="background:#ffffff;border-radius:24px;overflow:hidden;
              box-shadow:0 20px 60px rgba(14,30,20,0.12),0 4px 16px rgba(14,30,20,0.06)">

  <!-- ═══ HEADER ════════════════════════════════════════════════════════════ -->
  <tr><td style="background:linear-gradient(160deg,#0e1e14 0%,#0f4625 55%,#0a3520 100%);padding:40px 40px 32px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle">
        <div style="font-size:10px;color:#17c95f;text-transform:uppercase;letter-spacing:2.5px;font-weight:700;margin-bottom:8px">
          Bright Money &nbsp;·&nbsp; Affiliates
        </div>
        <div style="font-size:28px;font-weight:900;color:#ffffff;letter-spacing:-1px;line-height:1.1">
          Daily Data Refresh
        </div>
        <div style="font-size:13px;color:#6bde9b;margin-top:8px;font-weight:500">
          Invoice vs Cash &nbsp;·&nbsp; Close Month:
          <strong style="color:#ffffff">{close_month}</strong>
        </div>
      </td>
      <td align="right" style="vertical-align:middle;padding-left:20px">
        <div style="background:rgba(23,201,95,0.12);border:1px solid rgba(23,201,95,0.3);
                    border-radius:14px;padding:16px 22px;text-align:center;white-space:nowrap">
          <div style="font-size:9px;color:#6bde9b;text-transform:uppercase;letter-spacing:1.5px;font-weight:700">Last Refreshed</div>
          <div style="font-size:13px;font-weight:700;color:#ffffff;margin-top:5px">{now_ist}</div>
        </div>
      </td>
    </tr></table>
    <div style="margin-top:22px;padding-top:16px;border-top:1px solid rgba(23,201,95,0.2);
                font-size:10.5px;color:#6bde9b;line-height:1.5">
      <span style="opacity:0.75">This report is</span>
      <strong style="color:#17c95f">auto-generated and sent daily</strong>
      <span style="opacity:0.75">after each data refresh. Data sourced live from Google Sheets.</span>
    </div>
  </td></tr>

  {stale_banner}

  <!-- ═══ KPI CARDS ═════════════════════════════════════════════════════════ -->
  <tr><td style="padding:32px 40px 0">{kpis}</td></tr>

  <!-- ═══ WHAT'S NEW ════════════════════════════════════════════════════════ -->
  <tr><td style="padding:24px 40px 0">
    <div style="background:#f4f9f5;border:1px solid #d1e8d8;border-radius:16px;padding:22px 24px">
      <div style="font-size:13px;font-weight:800;color:#0e1e14;margin-bottom:16px;letter-spacing:-0.3px">
        <span style="color:#17c95f">&#9889;</span>&nbsp; What's New Since Last Refresh
      </div>
      {changes_html}
    </div>
  </td></tr>

  <!-- ═══ TABLE 1: CUMULATIVE ════════════════════════════════════════════════ -->
  {section(
      "Table 1 &mdash; Cumulative by Partner",
      "Lifetime billing vs cash received, net delta per partner",
      table1,
      badge=f"{len(cum_list)} partners"
  )}

  <!-- ═══ TABLE 3: PENDING (shown before detail) ════════════════════════════ -->
  {section(
      "Table 3 &mdash; Pending Collections",
      "Invoices raised &mdash; cash not yet received",
      table3,
      badge=f"{len(ytr_list)} pending"
  )}

  <!-- ═══ TABLE 2: MONTHLY DETAIL ═══════════════════════════════════════════ -->
  {section(
      "Table 2 &mdash; Monthly Collections Detail",
      "Last 3 payout months per partner &mdash; grouped and sorted",
      table2,
      badge=f"{total_shown} rows shown"
  )}

  <!-- ═══ CTA ═══════════════════════════════════════════════════════════════ -->
  <tr><td style="padding:36px 40px 40px;text-align:center">
    <div style="background:#f4f9f5;border:1px solid #d1e8d8;border-radius:18px;padding:28px 24px">
      <div style="font-size:12px;color:#5c626e;margin-bottom:16px;line-height:1.6">
        For full historical data, filters, and interactive views, visit the dashboard.
      </div>
      <a href="http://10.0.204.191/affiliates-recon-dashboard"
         style="display:inline-block;background:linear-gradient(135deg,#0e1e14 0%,#0f4625 100%);
                color:#ffffff;text-decoration:none;padding:14px 40px;border-radius:100px;
                font-size:13px;font-weight:700;letter-spacing:0.4px;
                box-shadow:0 4px 20px rgba(15,70,37,0.35)">
        View Full Dashboard &rarr;
      </a>
    </div>
  </td></tr>

  <!-- ═══ FOOTER ════════════════════════════════════════════════════════════ -->
  <tr><td style="background:#0e1e14;padding:22px 40px;border-radius:0 0 24px 24px;text-align:center">
    <div style="font-size:10.5px;color:#6bde9b;line-height:2;letter-spacing:0.2px">
      <strong style="color:#ffffff">Bright Money</strong> &nbsp;·&nbsp; Affiliates Reconciliation<br>
      <span style="color:#4a7a5a">Auto-generated by</span>
      <strong style="color:#17c95f">automation_ops@brightmoney.co</strong><br>
      <span style="color:#4a7a5a">Refreshed:</span>
      <span style="color:#6bde9b">{now_ist}</span>
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""
    return html


# ── Email sender ──────────────────────────────────────────────────────────────
def send_email(html, subject=None):
    if subject is None:
        subject = f"Affiliates Recon Invoice to Cash · {config.now_ist().strftime('%d %b %Y')}"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.SMTP_SENDER
    msg["To"]      = ", ".join(config.EMAIL_TO)
    msg.attach(MIMEText(html, "html"))
    print(f"[email] Connecting to {config.SMTP_HOST}:{config.SMTP_PORT} …")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as srv:
        srv.starttls()
        srv.login(config.SMTP_SENDER, config.SMTP_PASSWORD)
        srv.sendmail(config.SMTP_SENDER, config.EMAIL_TO, msg.as_string())
    print(f"[email] Sent → {', '.join(config.EMAIL_TO)}")


def append_email_log(entry):
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    log = []
    if os.path.exists(config.EMAIL_LOG_FILE):
        try:
            with open(config.EMAIL_LOG_FILE) as f:
                log = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            log = []
    log.append(entry)
    log = log[-config.EMAIL_LOG_MAX_ENTRIES:]
    with open(config.EMAIL_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2, default=str)
