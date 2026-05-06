"""Affiliates Recon — daily email report (Reports→Invoice + Invoice→Cash)."""

import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config


# ── Formatters ────────────────────────────────────────────────────────────────
def _f0(val):
    if val is None: return "—"
    return f"${val:,.0f}"

def _pct(val):
    if val is None: return "—"
    return f"{'+'if val>0 else ''}{val:.1f}%"

def _clr(val):
    if val is None: return "#5c626e"
    if val > 0:  return "#0f4625"
    if val < 0:  return "#b91c1c"
    return "#5c626e"

def _pc(p):
    return {"moneylion":"#3b82f6","amone":"#8b5cf6","kashkick":"#0d9488",
            "freecash":"#17c95f","brigit":"#f97316","supermoney":"#e11d48"}.get(p,"#5c626e")

def _dot(p):
    return (f'<span style="display:inline-block;width:9px;height:9px;border-radius:50%;'
            f'background:{_pc(p)};margin-right:6px;vertical-align:middle"></span>')

def _badge(status):
    m = {"GREEN":("#dcfce7","#0f4625"),"LOW":("#dcfce7","#0f4625"),
         "AMBER":("#fef3c7","#92400e"),"MEDIUM":("#fef3c7","#92400e"),
         "RED":("#fef2f2","#b91c1c"),"HIGH":("#fef2f2","#b91c1c"),
         "PENDING":("#f1f5f9","#5c626e"),"GREY":("#f1f5f9","#5c626e")}
    bg,fg = m.get((status or "").upper(),("#f1f5f9","#5c626e"))
    return (f'<span style="background:{bg};color:{fg};padding:3px 10px;border-radius:20px;'
            f'font-size:9.5px;font-weight:700;white-space:nowrap">{status or "—"}</span>')

def _variance_badge(monthly_status, status):
    """Variance status badge: color from status (GREEN/AMBER/RED), label from monthly_status (Low/Medium/High)."""
    m = {"GREEN":("#dcfce7","#0f4625"),"AMBER":("#fef3c7","#92400e"),
         "RED":("#fef2f2","#b91c1c")}
    bg,fg = m.get((status or "").upper(),("#f1f5f9","#5c626e"))
    label = monthly_status or "Pending"
    return (f'<span style="background:{bg};color:{fg};padding:3px 10px;border-radius:20px;'
            f'font-size:9.5px;font-weight:700;white-space:nowrap">{label}</span>')

# ── Cell style constants ──────────────────────────────────────────────────────
_F  = "font-family:'Figtree','Segoe UI',Arial,sans-serif"
TH  = f'padding:9px 13px;font-size:9px;text-transform:uppercase;letter-spacing:1px;font-weight:700;border-bottom:2px solid #d1e8d8;white-space:nowrap;background:#f4f9f5;color:#5c626e;{_F}'
THB = f'padding:9px 13px;font-size:9px;text-transform:uppercase;letter-spacing:1px;font-weight:700;border-bottom:2px solid #bfdbfe;white-space:nowrap;background:#eff6ff;color:#1d4ed8;{_F}'
TD  = f'padding:9px 13px;border-bottom:1px solid #f0f7f2;font-size:11px;color:#1a2e1e;{_F}'
TDB = f'padding:9px 13px;border-bottom:1px solid #eff6ff;font-size:11px;color:#1e3a8a;{_F}'
TDR = f'{TD};text-align:right;font-family:"Courier New",monospace'
TDBR= f'{TDB};text-align:right;font-family:"Courier New",monospace'
TDC = f'{TD};text-align:center'
TDBC= f'{TDB};text-align:center'


# ── Change detection ──────────────────────────────────────────────────────────
def compute_changes(prev_l3, curr_l3):
    """Compare l3 snapshots → new_invoices and new_cash (kept for compatibility)."""
    empty = {"new_invoices": [], "new_cash": []}
    if not prev_l3 or not curr_l3:
        return empty

    def key(r):
        return (r.get("partner"), r.get("payout_month"), r.get("cycle",""), r.get("billed"))

    prev_map = {key(r): r for r in prev_l3.get("yet_to_receive",[]) + prev_l3.get("collected",[])}
    curr_all = curr_l3.get("yet_to_receive",[]) + curr_l3.get("collected",[])

    new_invoices, new_cash = [], []
    for r in curr_all:
        k = key(r); prev = prev_map.get(k)
        if prev is None:
            (new_cash if (r.get("received") or 0) > 0 else new_invoices).append(r)
        else:
            if (r.get("received") or 0) > 0 and (prev.get("received") or 0) != (r.get("received") or 0):
                new_cash.append(r)
    return {"new_invoices": new_invoices, "new_cash": new_cash}


def compute_l1_changes(prev_l1, curr_l1):
    """Compare l1 snapshots → new or updated invoice entries."""
    empty = {"new_invoices": [], "updated_invoices": []}
    if not curr_l1 or not prev_l1:
        return empty

    def key(r):
        return (r.get("partner"), r.get("payout_month"), r.get("cycle"))

    prev_map = {key(r): r for r in prev_l1.get("monthly_detail", [])}
    new_inv, upd_inv = [], []
    for r in curr_l1.get("monthly_detail", []):
        curr_inv = r.get("invoice_amount") or 0
        if curr_inv <= 0:
            continue
        prev = prev_map.get(key(r))
        if prev is None:
            new_inv.append(r)
        else:
            prev_inv = prev.get("invoice_amount") or 0
            if prev_inv != curr_inv:
                upd_inv.append({**r, "prev_invoice_amount": prev_inv})
    return {"new_invoices": new_inv, "updated_invoices": upd_inv}


# ── Section 1 builders (Reports → Invoice, blue) ─────────────────────────────
def _s1_kpis(monthly_detail, close_month):
    """KPIs scoped to the close month only (current month − 1)."""
    rows = [r for r in monthly_detail if r.get("payout_month") == close_month]
    rep  = sum(r.get("reports_amount") or 0 for r in rows)
    inv  = sum(r.get("invoice_amount") or 0 for r in rows)
    dlt  = inv - rep
    pct  = (dlt / rep * 100) if rep else None
    d_pos = dlt >= 0
    d_bg  = "#eff6ff" if d_pos else "#fef2f2"
    d_bd  = "#bfdbfe" if d_pos else "#fecaca"
    d_cl  = "#1d4ed8" if d_pos else "#b91c1c"
    d_lbl = f"{'+'if d_pos else ''}{_f0(dlt)}"
    d_sub = "Invoice &gt; Reports" if d_pos else "Invoice &lt; Reports"
    return f"""
<table width="100%" cellpadding="0" cellspacing="6">
<tr>
  <td width="33%" style="padding-right:4px">
    <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:#3b82f6;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Reports Total</div>
      <div style="font-size:22px;font-weight:900;color:#1e3a8a;letter-spacing:-0.5px;line-height:1">{_f0(rep)}</div>
      <div style="font-size:9px;color:#3b82f6;margin-top:4px">Metabase</div>
    </div>
  </td>
  <td width="33%" style="padding:0 2px">
    <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:#0369a1;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Invoice Total</div>
      <div style="font-size:22px;font-weight:900;color:#0c4a6e;letter-spacing:-0.5px;line-height:1">{_f0(inv)}</div>
      <div style="font-size:9px;color:#0369a1;margin-top:4px">Google Sheet</div>
    </div>
  </td>
  <td width="33%" style="padding-left:4px">
    <div style="background:{d_bg};border:1px solid {d_bd};border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:{d_cl};text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Delta</div>
      <div style="font-size:22px;font-weight:900;color:{d_cl};letter-spacing:-0.5px;line-height:1">{d_lbl}</div>
      <div style="font-size:9px;color:{d_cl};margin-top:4px;font-weight:600">{d_sub} &middot; {_pct(pct)}</div>
    </div>
  </td>
</tr>
</table>"""


def _s1_invoice_changes(l1_changes):
    new_inv = l1_changes.get("new_invoices", [])
    upd_inv = l1_changes.get("updated_invoices", [])
    all_rows = sorted(new_inv + upd_inv, key=lambda r: (r.get("partner",""), r.get("payout_month","")))
    if not all_rows:
        return '<div style="color:#5c626e;font-size:11.5px;font-style:italic">No invoice changes since last refresh.</div>'

    rows_html = ""
    for i, r in enumerate(all_rows):
        bg = ' style="background:#f8faff"' if i % 2 else ""
        is_upd  = "prev_invoice_amount" in r
        prev_i  = r.get("prev_invoice_amount", 0) or 0
        curr_i  = r.get("invoice_amount", 0) or 0
        rep_a   = r.get("reports_amount", 0) or 0
        delta   = curr_i - rep_a
        tag_bg  = "#fef3c7;color:#92400e" if is_upd else "#dbeafe;color:#1d4ed8"
        tag_lbl = "UPDATED" if is_upd else "NEW"
        inv_cell = (f'<td style="{TDBR}">{_f0(prev_i)}&nbsp;→&nbsp;<strong>{_f0(curr_i)}</strong></td>'
                    if is_upd else f'<td style="{TDBR}"><strong>{_f0(curr_i)}</strong></td>')
        rows_html += (
            f'<tr{bg}>'
            f'<td style="{TDB}">{_dot(r.get("partner",""))}<strong>{r.get("display_name","—")}</strong></td>'
            f'<td style="{TDB}">{r.get("payout_month","—")}</td>'
            f'<td style="{TDBC}"><span style="font-size:9.5px;font-weight:700;background:#e0f2fe;color:#0369a1;padding:2px 7px;border-radius:8px">{r.get("cycle","—")}</span></td>'
            f'<td style="{TDBR}">{_f0(rep_a)}</td>'
            f'{inv_cell}'
            f'<td style="{TDBR};color:{"#1d4ed8"if delta>=0 else "#b91c1c"};font-weight:700">{"+"if delta>0 else ""}{_f0(delta)}</td>'
            f'<td style="{TDBC}">{_variance_badge(r.get("monthly_status"), r.get("status"))}</td>'
            f'<td style="{TDBC}"><span style="padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700;background:{tag_bg}">{tag_lbl}</span></td>'
            f'</tr>'
        )
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #bfdbfe;border-radius:12px;overflow:hidden">
  <tr>
    <th style="{THB};text-align:left">Partner</th>
    <th style="{THB};text-align:left">Month</th>
    <th style="{THB};text-align:center">Cycle</th>
    <th style="{THB};text-align:right">Reports Amt</th>
    <th style="{THB};text-align:right">Invoice Amt</th>
    <th style="{THB};text-align:right">Delta</th>
    <th style="{THB};text-align:center">Status</th>
    <th style="{THB};text-align:center">Change</th>
  </tr>
  {rows_html}
</table>"""


def _s1_close_month_table(monthly_detail, close_month):
    rows = [r for r in monthly_detail
            if r.get("payout_month") == close_month
            and ((r.get("invoice_amount") or 0) > 0 or (r.get("reports_amount") or 0) > 0)]
    rows = sorted(rows, key=lambda r: (r.get("partner",""), r.get("cycle","")))

    if not rows:
        return f'<div style="color:#5c626e;font-size:11.5px;font-style:italic">No invoice data for {close_month} yet.</div>'

    rows_html = ""
    for i, r in enumerate(rows):
        bg   = ' style="background:#f8faff"' if i % 2 else ""
        inv  = r.get("invoice_amount") or 0
        rep  = r.get("reports_amount") or 0
        dlt  = inv - rep
        rows_html += (
            f'<tr{bg}>'
            f'<td style="{TDB}">{_dot(r.get("partner",""))}<strong>{r.get("display_name","—")}</strong></td>'
            f'<td style="{TDBC}"><span style="font-size:9.5px;font-weight:700;background:#e0f2fe;color:#0369a1;padding:2px 7px;border-radius:8px">{r.get("cycle","—")}</span></td>'
            f'<td style="{TDBR}">{_f0(rep)}</td>'
            f'<td style="{TDBR}">{_f0(inv) if inv>0 else "—"}</td>'
            f'<td style="{TDBR};color:{"#1d4ed8"if dlt>=0 else "#b91c1c"};font-weight:700">{"+"if dlt>0 else ""}{_f0(dlt) if inv>0 else "—"}</td>'
            f'<td style="{TDBC}">{_variance_badge(r.get("monthly_status"), r.get("status"))}</td>'
            f'</tr>'
        )
    t_rep = sum(r.get("reports_amount") or 0 for r in rows)
    t_inv = sum(r.get("invoice_amount") or 0 for r in rows)
    t_dlt = t_inv - t_rep
    rows_html += (
        f'<tr style="background:#dbeafe">'
        f'<td style="{TDB};border-top:2px solid #93c5fd;font-weight:800" colspan="2">Total ({close_month})</td>'
        f'<td style="{TDBR};border-top:2px solid #93c5fd;font-weight:700">{_f0(t_rep)}</td>'
        f'<td style="{TDBR};border-top:2px solid #93c5fd;font-weight:700">{_f0(t_inv)}</td>'
        f'<td style="{TDBR};border-top:2px solid #93c5fd;font-weight:900;color:{"#1d4ed8"if t_dlt>=0 else "#b91c1c"}">{"+"if t_dlt>0 else ""}{_f0(t_dlt)}</td>'
        f'<td style="{TDBC};border-top:2px solid #93c5fd"></td>'
        f'</tr>'
    )
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #bfdbfe;border-radius:14px;overflow:hidden">
  <tr>
    <th style="{THB};text-align:left">Partner</th>
    <th style="{THB};text-align:center">Cycle</th>
    <th style="{THB};text-align:right">Reports Amount</th>
    <th style="{THB};text-align:right">Invoice Amount</th>
    <th style="{THB};text-align:right">Delta</th>
    <th style="{THB};text-align:center">Status</th>
  </tr>
  {rows_html}
</table>
<div style="margin-top:8px;padding:8px 12px;background:#eff6ff;border-radius:8px;border-left:3px solid #3b82f6;font-size:9.5px;color:#1d4ed8;line-height:1.6">
  <strong>+ Delta</strong> = Invoice &gt; Reports &nbsp;&nbsp;
  <strong style="color:#b91c1c">− Delta</strong> = Invoice &lt; Reports (potential under-billing)
</div>"""


# ── Section 2 builders (Invoice → Cash, green) ───────────────────────────────
def _s2_kpis(gt, ytr_list):
    billed   = gt.get("total_billed",   0) or 0
    received = gt.get("total_received", 0) or 0
    ytr      = gt.get("yet_to_receive", 0) or 0
    delta    = gt.get("net_delta",      0) or 0
    pct      = gt.get("collection_pct", 0) or 0
    d_pos    = delta >= 0
    d_bg  = "#e8f8ef" if d_pos else "#fef2f2"
    d_bd  = "#a7f3c8" if d_pos else "#fecaca"
    d_cl  = "#0f4625" if d_pos else "#b91c1c"
    d_lbl = f"{'+'if d_pos else ''}{_f0(delta)}"
    d_sub = "Cash &gt; Invoice" if d_pos else "Cash &lt; Invoice"
    return f"""
<table width="100%" cellpadding="0" cellspacing="6">
<tr>
  <td width="50%" style="padding-right:4px">
    <div style="background:#f4f9f5;border:1px solid #d1e8d8;border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:#5c626e;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Net Billed</div>
      <div style="font-size:24px;font-weight:900;color:#0e1e14;letter-spacing:-0.5px;line-height:1">{_f0(billed)}</div>
      <div style="font-size:9px;color:#5c626e;margin-top:4px">Total invoiced to partners</div>
    </div>
  </td>
  <td width="50%" style="padding-left:4px">
    <div style="background:#e8f8ef;border:1px solid #a7f3c8;border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:#0f4625;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Net Received</div>
      <div style="font-size:24px;font-weight:900;color:#0f4625;letter-spacing:-0.5px;line-height:1">{_f0(received)}</div>
      <div style="font-size:9px;color:#17c95f;margin-top:4px;font-weight:700">{pct:.1f}% collected so far</div>
    </div>
  </td>
</tr>
<tr>
  <td width="50%" style="padding-right:4px;padding-top:6px">
    <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:#92400e;text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Yet to Receive</div>
      <div style="font-size:24px;font-weight:900;color:#92400e;letter-spacing:-0.5px;line-height:1">{_f0(ytr)}</div>
      <div style="font-size:9px;color:#b45309;margin-top:4px;font-weight:600">{len(ytr_list)} invoice(s) pending</div>
    </div>
  </td>
  <td width="50%" style="padding-left:4px;padding-top:6px">
    <div style="background:{d_bg};border:1px solid {d_bd};border-radius:14px;padding:18px 14px;text-align:center">
      <div style="font-size:9.5px;color:{d_cl};text-transform:uppercase;letter-spacing:1px;font-weight:700;margin-bottom:6px">Overall Delta</div>
      <div style="font-size:24px;font-weight:900;color:{d_cl};letter-spacing:-0.5px;line-height:1">{d_lbl}</div>
      <div style="font-size:9px;color:{d_cl};margin-top:4px;font-weight:700">{d_sub}</div>
    </div>
  </td>
</tr>
</table>"""


def _s2_cash_changes(new_cash):
    if not new_cash:
        return '<div style="color:#5c626e;font-size:11.5px;font-style:italic">No new cash received since last refresh.</div>'
    rows_html = ""
    for i, r in enumerate(new_cash):
        bg = f' style="background:#fafcfa"' if i % 2 else ""
        rows_html += (
            f'<tr{bg}>'
            f'<td style="{TD}">{_dot(r.get("partner",""))}<strong>{r.get("display_name","—")}</strong></td>'
            f'<td style="{TD}">{r.get("payout_month","—")}</td>'
            f'<td style="{TDR}">{_f0(r.get("billed",0))}</td>'
            f'<td style="{TDR};color:#0f4625;font-weight:700">+{_f0(r.get("received",0))}</td>'
            f'<td style="padding:9px 13px;text-align:center">{_badge("LOW")}</td>'
            f'</tr>'
        )
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #a7f3c8;border-radius:12px;overflow:hidden">
  <tr>
    <th style="{TH};color:#0f4625;text-align:left">Partner</th>
    <th style="{TH};color:#0f4625;text-align:left">Month</th>
    <th style="{TH};color:#0f4625;text-align:right">Invoice Amt</th>
    <th style="{TH};color:#0f4625;text-align:right">Cash Received</th>
    <th style="{TH};color:#0f4625;text-align:center">Status</th>
  </tr>
  {rows_html}
</table>"""


def _s2_table1(cum_list, gt):
    billed   = gt.get("total_billed",   0) or 0
    received = gt.get("total_received", 0) or 0
    ytr      = gt.get("yet_to_receive", 0) or 0
    delta    = gt.get("net_delta",      0) or 0
    d_cl = _clr(delta)
    d_lbl = f"{'+'if delta>0 else ''}{_f0(delta)}"
    rows_html = ""
    for i, r in enumerate(cum_list):
        bg = f' style="background:#fafcfa"' if i % 2 else ""
        nd = r.get("net_delta", 0) or 0
        rows_html += (
            f'<tr{bg}>'
            f'<td style="{TD}">{_dot(r.get("partner",""))}<strong>{r.get("display_name","—")}</strong></td>'
            f'<td style="{TDR}">{_f0(r.get("total_billed",0))}</td>'
            f'<td style="{TDR};color:#0f4625;font-weight:700">{_f0(r.get("total_received",0))}</td>'
            f'<td style="{TDR};color:#92400e">{_f0(r.get("yet_to_receive",0))}</td>'
            f'<td style="{TDR};color:{_clr(nd)};font-weight:800">{"+"if nd>0 else ""}{_f0(nd)}</td>'
            f'<td style="{TDC}">{r.get("payment_term","—")}d</td>'
            f'</tr>'
        )
    rows_html += (
        f'<tr style="background:#e3f1e7">'
        f'<td style="{TD};border-top:2px solid #17c95f"><strong>Grand Total</strong></td>'
        f'<td style="{TDR};border-top:2px solid #17c95f;font-weight:700">{_f0(billed)}</td>'
        f'<td style="{TDR};border-top:2px solid #17c95f;color:#0f4625;font-weight:800">{_f0(received)}</td>'
        f'<td style="{TDR};border-top:2px solid #17c95f;color:#92400e;font-weight:700">{_f0(ytr)}</td>'
        f'<td style="{TDR};border-top:2px solid #17c95f;color:{d_cl};font-weight:900">{d_lbl}</td>'
        f'<td style="{TDC};border-top:2px solid #17c95f">—</td>'
        f'</tr>'
    )
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #d1e8d8;border-radius:14px;overflow:hidden">
  <tr>
    <th style="{TH};text-align:left">Partner</th>
    <th style="{TH};text-align:right">Billed</th>
    <th style="{TH};text-align:right">Received</th>
    <th style="{TH};text-align:right">Yet to Receive</th>
    <th style="{TH};text-align:right">Net Delta</th>
    <th style="{TH};text-align:center">Term</th>
  </tr>
  {rows_html}
</table>
<div style="margin-top:8px;padding:8px 12px;background:#f4f9f5;border-radius:8px;border-left:3px solid #17c95f;font-size:9.5px;color:#5c626e;line-height:1.6">
  <strong style="color:#0f4625">+ Delta</strong> = Cash &gt; Invoice ✓ Good &nbsp;&nbsp;
  <strong style="color:#b91c1c">− Delta</strong> = Cash &lt; Invoice ⚠ Needs review
</div>"""


def _s2_table3(ytr_list):
    total = sum(r.get("billed", 0) or 0 for r in ytr_list)
    rows_html = ""
    for i, r in enumerate(ytr_list):
        bg = f' style="background:#fffdf5"' if i % 2 else ""
        rows_html += (
            f'<tr{bg}>'
            f'<td style="{TD}">{_dot(r.get("partner",""))}<strong>{r.get("display_name","—")}</strong></td>'
            f'<td style="{TD}">{r.get("payout_month","—")}</td>'
            f'<td style="{TDR};color:#92400e;font-weight:700">{_f0(r.get("billed",0))}</td>'
            f'<td style="{TD}">{r.get("expected_collection") or "—"}</td>'
            f'<td style="{TDC}">{_badge("PENDING")}</td>'
            f'</tr>'
        )
    rows_html += (
        f'<tr style="background:#fef3c7">'
        f'<td style="{TD};border-top:2px solid #fbbf24;font-weight:800" colspan="2">Total Pending</td>'
        f'<td style="{TDR};border-top:2px solid #fbbf24;font-weight:900;color:#92400e">{_f0(total)}</td>'
        f'<td style="{TD};border-top:2px solid #fbbf24" colspan="2"></td>'
        f'</tr>'
    )
    return f"""
<table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #fde68a;border-radius:14px;overflow:hidden">
  <tr style="background:#fffbeb">
    <th style="{TH};color:#92400e;text-align:left">Partner</th>
    <th style="{TH};color:#92400e;text-align:left">Payout Month</th>
    <th style="{TH};color:#92400e;text-align:right">Invoice Amount</th>
    <th style="{TH};color:#92400e;text-align:left">Expected Collection</th>
    <th style="{TH};color:#92400e;text-align:center">Status</th>
  </tr>
  {rows_html}
</table>"""


# ── Section divider ───────────────────────────────────────────────────────────
def _divider(num, title, subtitle, accent):
    return f"""
<tr><td style="padding:28px 36px 0">
  <table width="100%" cellpadding="0" cellspacing="0" style="border-top:2px solid {accent}44">
  <tr><td style="padding-top:18px">
    <table cellpadding="0" cellspacing="0">
    <tr>
      <td width="36" style="vertical-align:middle;padding-right:12px">
        <div style="width:30px;height:30px;border-radius:50%;background:{accent};text-align:center;
                    font-size:15px;font-weight:900;color:#fff;line-height:30px;{_F}">{num}</div>
      </td>
      <td style="vertical-align:middle;border-left:3px solid {accent};padding-left:12px">
        <div style="font-size:14px;font-weight:800;color:#0e1e14;{_F}">{title}</div>
        <div style="font-size:10.5px;color:#5c626e;margin-top:2px;{_F}">{subtitle}</div>
      </td>
    </tr>
    </table>
  </td></tr>
  </table>
</td></tr>"""


# ── Subsection header ─────────────────────────────────────────────────────────
def _sub(title, subtitle, accent, badge=None):
    bdg = (f' <span style="background:{accent}22;color:{accent};padding:2px 9px;border-radius:20px;'
           f'font-size:9.5px;font-weight:700;border:1px solid {accent}55">{badge}</span>') if badge else ""
    return f"""
<tr><td style="padding:20px 36px 4px">
  <div style="border-left:3px solid {accent};padding-left:12px">
    <div style="font-size:13px;font-weight:800;color:#0e1e14;{_F}">{title}{bdg}</div>
    <div style="font-size:10.5px;color:#5c626e;margin-top:2px;{_F}">{subtitle}</div>
  </div>
</td></tr>"""


def _content(html):
    return f'<tr><td style="padding:12px 36px 0">{html}</td></tr>'


def _changes_box(title, accent, content, badge=None):
    bdg = (f' <span style="background:{accent}22;color:{accent};padding:2px 9px;border-radius:20px;'
           f'font-size:9.5px;font-weight:700;border:1px solid {accent}55;margin-left:8px">{badge}</span>') if badge else ""
    return f"""
<tr><td style="padding:20px 36px 0">
  <div style="background:{accent}0d;border:1px solid {accent}44;border-radius:14px;padding:18px 20px">
    <div style="font-size:12px;font-weight:800;color:#0e1e14;margin-bottom:12px;{_F}">
      &#9889;&nbsp;{title}{bdg}
    </div>
    {content}
  </div>
</td></tr>"""


# ── Main HTML builder ─────────────────────────────────────────────────────────
def generate_email_html(l3, l1=None, changes=None, l1_changes=None, stale=False, data_age=""):
    if changes is None:
        changes = {"new_invoices": [], "new_cash": []}
    if l1_changes is None:
        l1_changes = {"new_invoices": [], "updated_invoices": []}

    now_ist     = config.now_ist().strftime("%d %b %Y, %I:%M %p IST")
    close_month = l3.get("close_month", "—")
    l3_gt       = l3.get("grand_total", {})
    ytr_list    = l3.get("yet_to_receive", [])
    cum_list    = l3.get("cumulative", [])
    new_cash    = changes.get("new_cash", [])
    l1_gt       = (l1 or {}).get("grand_total", {})
    l1_detail   = (l1 or {}).get("monthly_detail", [])

    l1_chg = len(l1_changes.get("new_invoices",[])) + len(l1_changes.get("updated_invoices",[]))
    l3_chg = len(new_cash)

    stale_row = ""
    if stale:
        stale_row = (
            f'<tr><td style="padding:12px 36px 0">'
            f'<div style="background:#fef3c7;border:1px solid #fbbf24;border-radius:12px;padding:14px 18px">'
            f'<div style="font-size:12px;font-weight:800;color:#92400e">&#9888; Using Existing Data</div>'
            f'<div style="font-size:10.5px;color:#b45309;margin-top:3px">Last refreshed <strong>{data_age}</strong>. The daily job may not have run successfully.</div>'
            f'</div></td></tr>'
        )

    # Header change pills (inline-block for email compat)
    pills = ""
    if l1_chg:
        pills += (f'<span style="display:inline-block;background:rgba(59,130,246,0.2);border:1px solid rgba(59,130,246,0.4);'
                  f'border-radius:20px;padding:3px 11px;font-size:9.5px;color:#93c5fd;font-weight:700;margin-left:6px">'
                  f'{l1_chg} invoice update{"s"if l1_chg!=1 else ""}</span>')
    if l3_chg:
        pills += (f'<span style="display:inline-block;background:rgba(23,201,95,0.2);border:1px solid rgba(23,201,95,0.4);'
                  f'border-radius:20px;padding:3px 11px;font-size:9.5px;color:#6bde9b;font-weight:700;margin-left:6px">'
                  f'{l3_chg} cash update{"s"if l3_chg!=1 else ""}</span>')

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <title>Affiliates Recon Report — {close_month}</title>
  <link href="https://fonts.googleapis.com/css2?family=Figtree:wght@400;600;700;800;900&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#eef2ee;{_F}">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#eef2ee;padding:28px 0">
<tr><td align="center">
<table width="660" cellpadding="0" cellspacing="0"
       style="background:#fff;border-radius:20px;overflow:hidden;
              box-shadow:0 16px 48px rgba(14,30,20,0.12),0 4px 12px rgba(14,30,20,0.06)">

  <!-- HEADER -->
  <tr><td style="background:linear-gradient(155deg,#0e1e14 0%,#0f4625 60%,#0a3520 100%);padding:32px 36px 24px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle">
        <div style="font-size:9.5px;color:#17c95f;text-transform:uppercase;letter-spacing:2.5px;font-weight:700;margin-bottom:6px">
          Bright Money &nbsp;·&nbsp; Affiliates
        </div>
        <div style="font-size:24px;font-weight:900;color:#fff;letter-spacing:-0.8px;line-height:1.1">
          Affiliates Recon Report
        </div>
        <div style="font-size:11px;color:#6bde9b;margin-top:6px">
          Reports &#8594; Invoice &nbsp;·&nbsp; Invoice &#8594; Cash &nbsp;·&nbsp;
          Close Month: <strong style="color:#fff">{close_month}</strong>
        </div>
        <div style="margin-top:10px">{pills}</div>
      </td>
      <td align="right" style="vertical-align:top;padding-left:12px;white-space:nowrap">
        <div style="background:rgba(23,201,95,0.12);border:1px solid rgba(23,201,95,0.3);
                    border-radius:12px;padding:12px 16px;text-align:center">
          <div style="font-size:8.5px;color:#6bde9b;text-transform:uppercase;letter-spacing:1.5px;font-weight:700">Generated</div>
          <div style="font-size:11px;font-weight:700;color:#fff;margin-top:3px">{now_ist}</div>
        </div>
      </td>
    </tr></table>
  </td></tr>

  {stale_row}

  <!-- ① REPORTS → INVOICE -->
  {_divider("1", "Reports &#8594; Invoice Recon",
            f"Reports (Metabase) vs Invoice (Google Sheet) · {close_month}", "#3b82f6")}

  {_content(_s1_kpis(l1_detail, close_month) if l1 else '<p style="color:#5c626e;font-size:11.5px">No Reports data available.</p>')}

  {_changes_box(
      "Invoice Updates Since Last Refresh",
      "#3b82f6",
      _s1_invoice_changes(l1_changes) if l1 else '<p style="color:#5c626e;font-size:11.5px;font-style:italic">No data.</p>',
      badge=f"{l1_chg} changes" if l1_chg else None
  )}

  {_sub("Close Month Invoice Summary", f"Reports vs Invoice per partner · {close_month} only", "#3b82f6")}
  {_content(_s1_close_month_table(l1_detail, close_month) if l1 else '<p style="color:#5c626e;font-size:11.5px;font-style:italic">No data.</p>')}

  <!-- ② INVOICE → CASH -->
  {_divider("2", "Invoice &#8594; Cash Recon",
            "Invoice (Google Sheet) vs Cash Received · all-time cumulative", "#17c95f")}

  {_content(_s2_kpis(l3_gt, ytr_list))}

  {_changes_box(
      "Cash Received Since Last Refresh",
      "#17c95f",
      _s2_cash_changes(new_cash),
      badge=f"{l3_chg} new" if l3_chg else None
  )}

  {_sub("Cumulative by Partner", "Lifetime billing vs cash received, net delta per partner", "#17c95f",
        badge=f"{len(cum_list)} partners")}
  {_content(_s2_table1(cum_list, l3_gt))}

  {_sub("Pending Collections", "Invoices raised — cash not yet received", "#f59e0b",
        badge=f"{len(ytr_list)} pending")}
  {_content(_s2_table3(ytr_list))}

  <!-- CTA -->
  <tr><td style="padding:28px 36px 32px;text-align:center">
    <div style="background:#f4f9f5;border:1px solid #d1e8d8;border-radius:14px;padding:22px">
      <div style="font-size:11px;color:#5c626e;margin-bottom:12px">Full interactive views, historical data and filters:</div>
      <a href="http://10.0.204.191/affiliates-recon-dashboard"
         style="display:inline-block;background:linear-gradient(135deg,#0e1e14,#0f4625);
                color:#fff;text-decoration:none;padding:11px 32px;border-radius:100px;
                font-size:12px;font-weight:700;letter-spacing:0.4px">
        View Full Dashboard &#8594;
      </a>
    </div>
  </td></tr>

  <!-- FOOTER -->
  <tr><td style="background:#0e1e14;padding:18px 36px;border-radius:0 0 20px 20px;text-align:center">
    <div style="font-size:9.5px;color:#6bde9b;line-height:2;letter-spacing:0.2px">
      <strong style="color:#fff">Bright Money</strong> &nbsp;·&nbsp; Affiliates Reconciliation<br>
      <span style="color:#4a7a5a">Auto-generated by</span>
      <strong style="color:#17c95f">automation_ops@brightmoney.co</strong> &nbsp;·&nbsp;
      <span style="color:#4a7a5a">{now_ist}</span>
    </div>
  </td></tr>

</table>
</td></tr>
</table>
</body></html>"""


# ── SMTP sender ───────────────────────────────────────────────────────────────
def send_email(html, subject=None, to=None):
    if subject is None:
        subject = f"Affiliates Recon Report — {config.now_ist().strftime('%d %b %Y')}"
    recipients = to if to else config.EMAIL_TO
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = config.SMTP_SENDER
    msg["To"]      = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))
    print(f"[email] Connecting to {config.SMTP_HOST}:{config.SMTP_PORT} …")
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as srv:
        srv.starttls()
        srv.login(config.SMTP_SENDER, config.SMTP_PASSWORD)
        srv.sendmail(config.SMTP_SENDER, recipients, msg.as_string())
    print(f"[email] Sent → {', '.join(recipients)}")


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
