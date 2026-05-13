"""Recon email report entrypoint — generates and sends the daily recon email."""

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

import config
from recon.email import (generate_email_html, send_email, append_email_log,
                         compute_changes, compute_l1_changes)

L3_FILE           = os.path.join(config.COMPUTED_DIR, "l3_live_results.json")
L3_SNAPSHOT_FILE  = os.path.join(config.COMPUTED_DIR, "l3_prev_snapshot.json")
L1_FILE           = os.path.join(config.COMPUTED_DIR, "l1_results.json")
L1_SNAPSHOT_FILE  = os.path.join(config.COMPUTED_DIR, "l1_prev_snapshot.json")
STALE_HOURS       = 26


def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def is_stale(l3):
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
    parser = argparse.ArgumentParser(description="Send daily affiliates recon email")
    parser.add_argument("--to", nargs="+", help="Override recipient(s) for test sends")
    args = parser.parse_args()

    print("═══ Daily Affiliates Recon — Email Report ═══")
    start = datetime.now()

    log_entry = {
        "timestamp": config.now_ist().isoformat(),
        "status": "SUCCESS",
        "recipients": args.to or config.EMAIL_TO,
        "error": None,
        "data_stale": False,
    }

    try:
        l3 = load_json(L3_FILE)
        if not l3:
            raise RuntimeError("No l3 data found — run recon/run.py first.")

        stale, age_str = is_stale(l3)
        log_entry["data_stale"] = stale
        if stale:
            print(f"[email] WARNING: data is stale ({age_str})")
        else:
            print(f"[email] Data freshness OK ({age_str})")

        prev_l3 = load_json(L3_SNAPSHOT_FILE)
        changes = compute_changes(prev_l3, l3)
        print(f"[email] l3 changes — new_cash: {len(changes['new_cash'])}")

        l1      = load_json(L1_FILE)
        prev_l1 = load_json(L1_SNAPSHOT_FILE)
        l1_changes = compute_l1_changes(prev_l1, l1)
        print(f"[email] l1 changes — new invoices: {len(l1_changes['new_invoices'])}, "
              f"updated: {len(l1_changes['updated_invoices'])}")

        html = generate_email_html(l3, l1=l1, changes=changes, l1_changes=l1_changes,
                                   stale=stale, data_age=age_str)
        print(f"[email] HTML generated ({len(html):,} bytes)")

        preview_path = os.path.join(config.BASE_DIR, "email_preview.html")
        with open(preview_path, "w") as f:
            f.write(html)
        print(f"[email] Preview saved → email_preview.html")

        send_email(html, to=args.to if args.to else None)
        log_entry["status"] = "SUCCESS"

    except Exception as e:
        log_entry["status"] = "FAILED"
        log_entry["error"]  = traceback.format_exc()
        print(f"[email] FAILED: {e}")
        try:
            requests.post(config.SLACK_WEBHOOK_URL, json={
                "text": (f":red_circle: *Affiliates Recon Email Failed*\n"
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
