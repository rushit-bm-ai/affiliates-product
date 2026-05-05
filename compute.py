"""All reconciliation computation logic."""

import os
import json
from datetime import datetime

import pandas as pd
import numpy as np

import config


def _save_json(filename, data):
    path = os.path.join(config.COMPUTED_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"[compute] Written → {filename}")


def _load_google_sheet():
    """Pull live data from Google Sheets using service account."""
    import gspread
    from google.oauth2.service_account import Credentials

    creds = Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_KEY,
        scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"],
    )
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(config.GOOGLE_SHEET_ID)
    ws = sh.get_worksheet_by_id(config.GOOGLE_SHEET_GID)
    rows = ws.get_all_values()

    data_rows = rows[config.GOOGLE_SHEET_DATA_START:]

    records = []
    for r in data_rows:
        affiliate = r[1].strip()
        if not affiliate:
            continue
        def parse_dollar(val):
            val = val.strip()
            if not val or val.upper() in ("NA", "N/A", "TBD", "PENDING"):
                return None
            cleaned = val.replace("$", "").replace(",", "").strip()
            if cleaned in ("-", "—", ""):
                return None
            return float(cleaned)

        cycle_val = r[13].strip().upper() if len(r) > 13 and r[13].strip() else "C1"
        records.append({
            "Affiliate": affiliate,
            "$ Billed": parse_dollar(r[2]),
            "$ Received": parse_dollar(r[3]),
            "Payout time period": r[7].strip() if r[7].strip() else None,
            "Collection time period": r[9].strip() if r[9].strip() else None,
            "Expected collection": r[10].strip() if r[10].strip() else None,
            "Product sign off": r[11].strip() if len(r) > 11 and r[11].strip() else None,
            "Comments": r[12].strip() if len(r) > 12 and r[12].strip() else None,
            "Cycle": cycle_val,
        })

    df = pd.DataFrame(records)
    df["partner_canonical"] = df["Affiliate"].map(config.GSHEET_PARTNER_MAP).fillna(df["Affiliate"].str.lower())
    df["$ Billed"] = pd.to_numeric(df["$ Billed"], errors="coerce")
    df["$ Received"] = pd.to_numeric(df["$ Received"], errors="coerce")
    df["month"] = pd.to_datetime(df["Payout time period"], errors="coerce").dt.strftime("%Y-%m")
    return df


def _get_status_p2(partner, variance_pct, invoice_amount, reports_amount):
    """Determine GREEN/AMBER/RED status based on variance thresholds."""
    if invoice_amount == 0 and reports_amount == 0:
        return "GREY"
    if (invoice_amount == 0) != (reports_amount == 0):
        return "RED"
    if variance_pct is None or pd.isna(variance_pct):
        return "RED"
    th = config.VARIANCE_THRESHOLDS.get(partner, config.VARIANCE_THRESHOLDS["DEFAULT"])
    apct = abs(variance_pct)
    if apct < th["green"]:
        return "GREEN"
    elif apct < th["amber"]:
        return "AMBER"
    else:
        return "RED"


def _load_q4122():
    """Load Q4122 reports by payout month and cycle."""
    df = pd.read_csv(config.QUERIES["reports_by_payout_cycle"]["file"])
    df["partner"] = df["partner"].str.lower()
    df["cycle"] = df["cycle"].str.upper()
    df["reports_revenue"] = pd.to_numeric(df["reports_revenue"], errors="coerce").fillna(0)
    df = df.rename(columns={"invoice_month": "payout_month"})
    return df


def compute_reports_vs_invoice(close_month):
    """Reports (Q4122) vs Invoice (Google Sheet) — full outer join on (payout_month, partner, cycle)."""
    print(f"[compute] Reports vs Invoice (close_month={close_month})")

    # Load reports data from Q4122
    q4122 = _load_q4122()

    # Load invoice data from Google Sheet
    try:
        gdf = _load_google_sheet()
    except Exception as e:
        print(f"[compute] WARNING: Google Sheet failed for Reports vs Invoice: {e}")
        gdf = pd.DataFrame()

    # Build reports lookup: (payout_month, partner, cycle) -> reports_revenue
    reports_lookup = {}
    for _, row in q4122.iterrows():
        key = (row["payout_month"], row["partner"], row["cycle"])
        reports_lookup[key] = reports_lookup.get(key, 0) + float(row["reports_revenue"])

    # Build invoice lookup: (payout_month, partner, cycle) -> $ Billed
    invoice_lookup = {}
    if len(gdf) > 0:
        for _, row in gdf.iterrows():
            month = row["month"]
            partner = row["partner_canonical"]
            billed = row["$ Billed"]
            cycle = row.get("Cycle", "C1")
            if pd.isna(month) or pd.isna(billed) or month in ("", "NaT"):
                continue
            if pd.isna(cycle) or not cycle:
                cycle = "C1"
            key = (month, partner, cycle)
            invoice_lookup[key] = invoice_lookup.get(key, 0) + float(billed)

    # Full outer join on (payout_month, partner, cycle)
    all_keys = set(list(reports_lookup.keys()) + list(invoice_lookup.keys()))

    monthly_detail = []
    for key in sorted(all_keys):
        payout_month, partner, cycle = key
        reports_amt = round(reports_lookup.get(key, 0), 2)
        invoice_amt = round(invoice_lookup.get(key, 0), 2)
        delta = round(invoice_amt - reports_amt, 2)
        delta_pct = round(delta / invoice_amt * 100, 2) if invoice_amt != 0 else (0.0 if reports_amt == 0 else None)
        status = _get_status_p2(partner, delta_pct, invoice_amt, reports_amt)
        display_name = config.PARTNER_DISPLAY_NAMES.get(partner, partner.title())

        monthly_detail.append({
            "payout_month": payout_month,
            "partner": partner,
            "display_name": display_name,
            "cycle": cycle,
            "reports_amount": reports_amt,
            "invoice_amount": invoice_amt,
            "delta": delta,
            "delta_pct": delta_pct,
            "status": status,
        })

    # Sort: month desc, partner asc, cycle asc
    monthly_detail.sort(key=lambda r: (r["partner"], r["cycle"]))
    monthly_detail.sort(key=lambda r: r["payout_month"], reverse=True)

    # Cumulative by partner
    cumulative = []
    for partner in sorted(set(r["partner"] for r in monthly_detail)):
        prows = [r for r in monthly_detail if r["partner"] == partner]
        total_reports = round(sum(r["reports_amount"] for r in prows), 2)
        total_invoice = round(sum(r["invoice_amount"] for r in prows), 2)
        total_delta = round(total_invoice - total_reports, 2)
        delta_pct = round(total_delta / total_invoice * 100, 2) if total_invoice != 0 else None
        status = _get_status_p2(partner, delta_pct, total_invoice, total_reports)
        display_name = config.PARTNER_DISPLAY_NAMES.get(partner, partner.title())
        cumulative.append({
            "partner": partner, "display_name": display_name,
            "total_reports": total_reports, "total_invoice": total_invoice,
            "total_delta": total_delta, "delta_pct": delta_pct, "status": status,
            "month_count": len(set(r["payout_month"] for r in prows)),
        })

    # Grand total
    gt_rep = sum(r["total_reports"] for r in cumulative)
    gt_inv = sum(r["total_invoice"] for r in cumulative)
    gt_delta = round(gt_inv - gt_rep, 2)
    gt_pct = round(gt_delta / gt_inv * 100, 2) if gt_inv != 0 else None
    grand_total = {
        "partner": "_TOTAL", "display_name": "Grand Total",
        "total_reports": round(gt_rep, 2), "total_invoice": round(gt_inv, 2),
        "total_delta": gt_delta, "delta_pct": gt_pct, "status": "",
        "month_count": len(set(r["payout_month"] for r in monthly_detail)),
    }

    # Overall status
    statuses = [r["status"] for r in cumulative if r["status"]]
    overall = "GREEN"
    if "RED" in statuses:
        overall = "RED"
    elif "AMBER" in statuses:
        overall = "AMBER"

    result = {
        "close_month": close_month, "generated_at": datetime.now().isoformat(),
        "monthly_detail": monthly_detail, "cumulative": cumulative,
        "grand_total": grand_total, "overall_status": overall,
    }
    _save_json("l1_results.json", result)
    print(f"[compute] Reports vs Invoice complete — {len(monthly_detail)} rows, overall: {overall}")
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════════════

def validate_inputs(close_month):
    print(f"[compute] Validation (close_month={close_month})")
    cleaning_log = []

    def log_step(action, detail, status="PASS"):
        cleaning_log.append({"timestamp": datetime.now().isoformat(), "action": action, "detail": detail, "status": status})

    q4122 = _load_q4122()
    log_step("Load Q4122", f"{len(q4122)} rows loaded from reports_by_payout_cycle.csv")

    # Try loading Google Sheet for validation
    gsheet_rows = 0
    try:
        gdf = _load_google_sheet()
        gsheet_rows = len(gdf)
        log_step("Load Google Sheet", f"{gsheet_rows} rows loaded from live sheet")
    except Exception as e:
        log_step("Load Google Sheet", f"Failed: {e}", "FAIL")

    files_analysis = []
    # Q4122 analysis
    cols_info = []
    for c in q4122.columns:
        info = {
            "name": c, "dtype": str(q4122[c].dtype),
            "nulls": int(q4122[c].isna().sum()),
            "null_pct": round(q4122[c].isna().mean() * 100, 2),
            "sample_values": [str(v) for v in q4122[c].dropna().unique()[:3]],
        }
        if pd.api.types.is_numeric_dtype(q4122[c]):
            info["min"] = float(q4122[c].min()) if not q4122[c].isna().all() else None
            info["max"] = float(q4122[c].max()) if not q4122[c].isna().all() else None
        elif q4122[c].dtype == "object":
            info["min"] = str(q4122[c].dropna().min()) if not q4122[c].isna().all() else None
            info["max"] = str(q4122[c].dropna().max()) if not q4122[c].isna().all() else None
        cols_info.append(info)
        if info["null_pct"] > 20:
            log_step(f"Column: Q4122.{c}", f"null% = {info['null_pct']}%", "FAIL")
        elif info["null_pct"] > 5:
            log_step(f"Column: Q4122.{c}", f"null% = {info['null_pct']}%", "WARN")

    month_min = str(q4122["payout_month"].dropna().min()) if "payout_month" in q4122.columns else None
    month_max = str(q4122["payout_month"].dropna().max()) if "payout_month" in q4122.columns else None
    files_analysis.append({
        "label": "Q4122", "file": "reports_by_payout_cycle.csv", "pull_method": "Metabase Q4122",
        "row_count": len(q4122), "columns": cols_info,
        "month_range": {"min": month_min, "max": month_max}, "status": "PASS",
    })
    files_analysis.append({
        "label": "Google Sheet", "file": "Live (New R : finance)", "pull_method": "Google Sheets API",
        "row_count": gsheet_rows, "columns": [],
        "month_range": {"min": "—", "max": "—"}, "status": "PASS" if gsheet_rows > 0 else "FAIL",
    })

    # Partner coverage
    q4122_partners = set(q4122["partner"].unique())
    partner_coverage = []
    for p in config.EXPECTED_PARTNERS:
        display = config.PARTNER_DISPLAY_NAMES.get(p, p)
        in_q = p in q4122_partners
        q_rows = int(q4122[q4122["partner"] == p].shape[0]) if in_q else 0
        status = "PASS" if in_q else "WARN"
        if not in_q:
            log_step(f"Partner: {display}", "Not found in Q4122", "WARN")
        partner_coverage.append({
            "partner": p, "display_name": display, "in_q4122": in_q,
            "q4122_rows": q_rows, "status": status,
        })

    overall = "PASS"
    if any(e["status"] == "FAIL" for e in cleaning_log):
        overall = "FAIL"
    elif any(e["status"] == "WARN" for e in cleaning_log):
        overall = "WARN"

    report = {
        "close_month": close_month, "generated_at": datetime.now().isoformat(),
        "files": files_analysis, "partner_coverage": partner_coverage,
        "cleaning_log": cleaning_log, "overall_status": overall,
    }
    _save_json("validation_report.json", report)
    print(f"[compute] Validation complete — overall: {overall}")
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# Invoice vs Cash (Live Google Sheet)
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_accel_charge(partner):
    """Parse acceleration charge rate from PARTNER_CONFIG. '3%' -> 0.03, '—' -> 0."""
    cfg = config.PARTNER_CONFIG.get(partner, {})
    charge_str = cfg.get("accel_charge", "—")
    if charge_str in ("—", "", None):
        return 0.0
    try:
        return float(charge_str.replace("%", "")) / 100.0
    except (ValueError, AttributeError):
        return 0.0


def _get_delta_status(variance_pct):
    if variance_pct is None:
        return "PENDING"
    apct = abs(variance_pct)
    if apct < 2:
        return "Low"
    elif apct < 5:
        return "Medium"
    else:
        return "High"


def _delta_color(received, billed):
    if received is None or billed is None:
        return "grey"
    return "green" if received >= billed else "red"


def compute_invoice_vs_cash_live(close_month):
    print(f"[compute] Invoice vs Cash — Live Google Sheet")
    df = _load_google_sheet()
    print(f"[compute]   Pulled {len(df)} rows from Google Sheet")

    df["collection_month"] = pd.to_datetime(df["Collection time period"], errors="coerce").dt.strftime("%Y-%m")

    yet_to_receive = []
    collected = []

    for _, row in df.iterrows():
        billed = row["$ Billed"]
        received = row["$ Received"]
        if pd.isna(billed):
            continue
        billed = round(float(billed), 2)
        has_received = not pd.isna(received)
        received_val = round(float(received), 2) if has_received else None
        delta = round(received_val - billed, 2) if has_received else None
        delta_pct = round(delta / billed * 100, 2) if (delta is not None and billed != 0) else None
        status = _get_delta_status(delta_pct)
        color = _delta_color(received_val, billed)
        coll_month = row["collection_month"]
        is_collected = isinstance(coll_month, str) and coll_month not in ("", "NaT")

        rec = {
            "partner": row["partner_canonical"],
            "display_name": config.PARTNER_DISPLAY_NAMES.get(row["partner_canonical"], row["partner_canonical"]),
            "payout_month": row["month"],
            "collection_month": coll_month if is_collected else None,
            "billed": billed, "received": received_val,
            "delta": delta, "delta_pct": delta_pct,
            "status": status, "color": color,
            "expected_collection": (str(row["Expected collection"]).strip() or None) if pd.notna(row["Expected collection"]) and str(row["Expected collection"]).strip() else (coll_month if is_collected and not has_received else None),
            "product_signoff": str(row.get("Product sign off", "")).strip() if pd.notna(row.get("Product sign off")) else None,
            "comments": str(row.get("Comments", "")).strip() if pd.notna(row.get("Comments")) else None,
            "cycle": str(row.get("Cycle", "C1")).strip().upper() or "C1",
        }

        # Compute net delta post acceleration charges
        accel_rate = _parse_accel_charge(row["partner_canonical"])
        if has_received and delta is not None:
            net_delta_val = round(delta + (accel_rate * billed), 2)
            net_delta_pct_val = round(net_delta_val / billed * 100, 2) if billed != 0 else None
            net_status = _get_delta_status(net_delta_pct_val)
            net_color = "green" if net_delta_val >= 0 else "red"
        else:
            net_delta_val = None
            net_delta_pct_val = None
            net_status = status
            net_color = color

        rec["accel_rate"] = accel_rate
        rec["net_delta"] = net_delta_val
        rec["net_delta_pct"] = net_delta_pct_val
        rec["net_status"] = net_status
        rec["net_color"] = net_color

        if not has_received:
            yet_to_receive.append(rec)
        else:
            collected.append(rec)

    yet_to_receive.sort(key=lambda r: (r["payout_month"] or "", r["partner"]), reverse=False)
    yet_to_receive.sort(key=lambda r: r["payout_month"] or "", reverse=True)
    collected.sort(key=lambda r: (r["collection_month"] or "", r["partner"], r["payout_month"] or ""))
    collected.sort(key=lambda r: r["collection_month"] or "", reverse=True)

    cumulative = []
    partners = sorted(df["partner_canonical"].unique())
    for partner in partners:
        pdf = df[df["partner_canonical"] == partner]
        total_billed = round(float(pdf["$ Billed"].sum()), 2)
        total_received = round(float(pdf["$ Received"].dropna().sum()), 2)
        partner_ytr = [r for r in yet_to_receive if r["partner"] == partner]
        ytr_total = round(sum(r["billed"] for r in partner_ytr), 2)
        ytr_details = [{"payout_month": r["payout_month"], "amount": r["billed"], "expected_collection": r["expected_collection"]} for r in partner_ytr]
        # Net delta = sum of net_delta (post accel) from collected rows for this partner
        partner_collected = [r for r in collected if r["partner"] == partner]
        net_delta = round(sum(r["net_delta"] for r in partner_collected if r["net_delta"] is not None), 2)
        collection_pct = round(total_received / total_billed * 100, 2) if total_billed != 0 else None
        term = config.PARTNER_CONFIG.get(partner, {}).get("payment_term", "—")
        cumulative.append({
            "partner": partner, "display_name": config.PARTNER_DISPLAY_NAMES.get(partner, partner),
            "total_billed": total_billed, "total_received": total_received,
            "yet_to_receive": ytr_total, "yet_to_receive_details": ytr_details,
            "net_delta": net_delta, "collection_pct": collection_pct, "payment_term": term,
        })

    gt_billed = sum(r["total_billed"] for r in cumulative)
    gt_received = sum(r["total_received"] for r in cumulative)
    gt_ytr = sum(r["yet_to_receive"] for r in cumulative)
    gt_net_delta = round(sum(r["net_delta"] for r in cumulative), 2)
    gt_cpct = round(gt_received / gt_billed * 100, 2) if gt_billed != 0 else None
    grand_total = {
        "partner": "_TOTAL", "display_name": "Grand Total",
        "total_billed": round(gt_billed, 2), "total_received": round(gt_received, 2),
        "yet_to_receive": round(gt_ytr, 2), "yet_to_receive_details": [],
        "net_delta": gt_net_delta, "collection_pct": gt_cpct, "payment_term": "—",
    }

    overall = "GREEN"
    if "High" in [r["net_status"] for r in collected]:
        overall = "RED"
    elif "Medium" in [r["net_status"] for r in collected]:
        overall = "AMBER"

    result = {
        "close_month": close_month, "generated_at": datetime.now().isoformat(),
        "source": "Google Sheet (live)", "sheet_id": config.GOOGLE_SHEET_ID,
        "yet_to_receive": yet_to_receive, "collected": collected,
        "cumulative": cumulative, "grand_total": grand_total, "overall_status": overall,
    }
    _save_json("l3_live_results.json", result)
    print(f"[compute] Invoice vs Cash complete — {len(yet_to_receive)} yet-to-receive, {len(collected)} collected")
    return result
