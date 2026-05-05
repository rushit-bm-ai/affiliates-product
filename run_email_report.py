"""Entry point for the daily Invoice vs Cash email report."""

import json
import os
import traceback
from datetime import datetime, timezone, timedelta

import requests

import config
from send_email import generate_email_html, send_email, append_email_log, compute_changes

SNAPSHOT_FILE  = os.path.join(config.COMPUTED_DIR, "l3_prev_snapshot.json")
L3_FILE        = os.path.join(config.COMPUTED_DIR, "l3_live_results.json")
STALE_HOURS    = 26   # flag as stale if data is older than this


def load_json(name):
    p = os.path.join(config.COMPUTED_DIR, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return None


def is_stale(l3):
    """Return (is_stale, age_str) — stale if generated_at is older than STALE_HOURS."""
    generated_at = l3.get("generated_at")
    if not generated_at:
        return True, "unknown age"
    try:
        dt = datetime.fromisoformat(generated_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = datetime.now(timezone.utc) - dt.astimezone(timezone.utc)
        hours = age.total_seconds() / 3600
        age_str = f"{int(hours)}h {int((age.total_seconds() % 3600) / 60)}m ago"
        return hours > STALE_HOURS, age_str
    except Exception:
        return True, "unknown age"


def main():
    print(f"═══ Daily Data Refresh — Email Report ═══")
    start = datetime.now()

    log_entry = {
        "timestamp": config.now_ist().isoformat(),
        "status": "SUCCESS",
        "recipients": config.EMAIL_TO,
        "error": None,
        "data_stale": False,
    }

    try:
        l3 = load_json("l3_live_results.json")
        if not l3:
            raise RuntimeError("No computed data found — run run_recon.py first.")

        # Stale data detection
        stale, age_str = is_stale(l3)
        log_entry["data_stale"] = stale
        if stale:
            print(f"[email] WARNING: data is stale ({age_str}) — sending on existing data")
        else:
            print(f"[email] Data freshness OK ({age_str})")

        # Load previous snapshot for change detection
        prev_l3 = load_json("l3_prev_snapshot.json") if os.path.exists(SNAPSHOT_FILE) else None
        changes = compute_changes(prev_l3, l3)

        new_inv  = len(changes.get("new_invoices", []))
        new_cash = len(changes.get("new_cash", []))
        print(f"[email] Changes — new invoices: {new_inv}, new cash: {new_cash}")

        # Generate and send — pass stale flag so template can surface it
        html = generate_email_html(l3, changes, stale=stale, data_age=age_str)
        print(f"[email] HTML generated ({len(html):,} bytes)")
        send_email(html)
        log_entry["status"] = "SUCCESS"

    except Exception as e:
        log_entry["status"] = "FAILED"
        log_entry["error"]  = traceback.format_exc()
        print(f"[email] FAILED: {e}")
        try:
            requests.post(config.SLACK_WEBHOOK_URL, json={
                "text": (f":red_circle: *Daily Data Refresh — Email Failed*\n"
                         f"*Error:* `{e}`\n"
                         f"*Time:* {config.now_ist().strftime('%Y-%m-%d %H:%M IST')}"),
            }, timeout=10)
        except Exception:
            pass

    log_entry["duration_seconds"] = round((datetime.now() - start).total_seconds(), 1)
    append_email_log(log_entry)
    print(f"═══ Done ({log_entry['status']}) — {log_entry['duration_seconds']}s ═══")


if __name__ == "__main__":
    main()
