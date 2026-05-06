"""Orchestrator entry point — pull → compute → render → log health → alert."""

import argparse
import json
import os
import shutil
import sys
import traceback
from datetime import datetime

import yaml
import requests

import config

L3_FILE           = os.path.join(config.COMPUTED_DIR, "l3_live_results.json")
L3_SNAPSHOT_FILE  = os.path.join(config.COMPUTED_DIR, "l3_prev_snapshot.json")
L1_FILE           = os.path.join(config.COMPUTED_DIR, "l1_results.json")
L1_SNAPSHOT_FILE  = os.path.join(config.COMPUTED_DIR, "l1_prev_snapshot.json")


def save_snapshot():
    """Copy current l3/l1 results → prev snapshots before new data overwrites them."""
    for src, dst, label in [
        (L3_FILE, L3_SNAPSHOT_FILE, "l3_prev_snapshot.json"),
        (L1_FILE, L1_SNAPSHOT_FILE, "l1_prev_snapshot.json"),
    ]:
        if os.path.exists(src):
            shutil.copy(src, dst)
            print(f"[recon] Snapshot saved → {label}")
        else:
            print(f"[recon] No existing {os.path.basename(src)} to snapshot — skipping")


def send_slack_alert(message):
    """Send failure alert to Slack."""
    try:
        payload = {
            "text": f":red_circle: *Daily data refresh — Pipeline Failed*\n{message}",
            "unfurl_links": False,
        }
        resp = requests.post(config.SLACK_WEBHOOK_URL, json=payload, timeout=10)
        if resp.status_code == 200:
            print(f"[slack] Alert sent successfully")
        else:
            print(f"[slack] Failed to send alert: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"[slack] Error sending alert: {e}")


def append_health_log(entry):
    """Append a run entry to the health log JSON."""
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    log = []
    if os.path.exists(config.HEALTH_LOG_FILE):
        try:
            with open(config.HEALTH_LOG_FILE) as f:
                log = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            log = []
    log.append(entry)
    # Keep only last N entries
    log = log[-config.HEALTH_MAX_ENTRIES:]
    with open(config.HEALTH_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="Daily data refresh")
    parser.add_argument("--skip-pull", action="store_true", help="Skip Metabase pull, use cached CSV")
    parser.add_argument("--month", type=str, default=None, help="Override close month (YYYY-MM)")
    args = parser.parse_args()

    os.makedirs(config.INPUT_DIR, exist_ok=True)
    os.makedirs(config.COMPUTED_DIR, exist_ok=True)
    os.makedirs(config.LOGS_DIR, exist_ok=True)

    mi_path = os.path.join(config.BASE_DIR, "manual_inputs.yaml")
    manual_inputs = {}
    if os.path.exists(mi_path):
        with open(mi_path) as f:
            manual_inputs = yaml.safe_load(f) or {}

    close_month = args.month or manual_inputs.get("close_month", config.default_close_month())
    start_time = config.now_ist()
    print(f"═══ Daily data refresh — close month: {close_month} ═══\n")

    health = {
        "timestamp": start_time.isoformat(),
        "close_month": close_month,
        "status": "SUCCESS",
        "steps": {},
        "errors": [],
        "duration_seconds": 0,
    }

    # Save snapshot of previous l3 before new data is pulled
    save_snapshot()

    try:
        # Step 1: Pull data
        print("─── Step 1: Data Pull ───")
        import pull_data
        pull_data.main(skip_pull=args.skip_pull)
        health["steps"]["data_pull"] = "OK"
        print()

        # Step 2: Compute
        print("─── Step 2: Compute ───")
        import compute

        vr = compute.validate_inputs(close_month)
        health["steps"]["validation"] = vr.get("overall_status", "UNKNOWN")

        l1 = compute.compute_reports_vs_invoice(close_month)
        health["steps"]["reports_vs_invoice"] = f"{len(l1['monthly_detail'])} rows, {l1['overall_status']}"

        try:
            l3 = compute.compute_invoice_vs_cash_live(close_month)
            health["steps"]["invoice_vs_cash_live"] = f"{len(l3['collected'])} collected, {len(l3['yet_to_receive'])} pending"
        except Exception as e:
            err = f"Google Sheet pull failed: {e}"
            print(f"[compute] WARNING: {err}")
            health["steps"]["invoice_vs_cash_live"] = "FAILED"
            health["errors"].append(err)

        try:
            mon = compute.compute_monitor()
            health["steps"]["monitor"] = f"{len(mon['daily'])} daily rows"
        except Exception as e:
            err = f"Monitor compute failed: {e}"
            print(f"[compute] WARNING: {err}")
            health["steps"]["monitor"] = "FAILED"
            health["errors"].append(err)
        print()

        # Step 3: Generate dashboard
        print("─── Step 3: Generate Dashboard ───")
        import generate_dashboard
        generate_dashboard.main(close_month)
        health["steps"]["dashboard_render"] = "OK"

    except Exception as e:
        health["status"] = "FAILED"
        health["errors"].append(traceback.format_exc())
        print(f"\n[ERROR] Pipeline failed: {e}")
        send_slack_alert(f"*Error:* `{e}`\n*Close month:* {close_month}\n*Time:* {start_time.strftime('%Y-%m-%d %H:%M IST')}")

    health["duration_seconds"] = round((config.now_ist() - start_time).total_seconds(), 1)
    append_health_log(health)

    if health["errors"] and health["status"] != "FAILED":
        health["status"] = "PARTIAL"
        send_slack_alert(
            f"*Partial failure:* {len(health['errors'])} error(s)\n"
            + "\n".join(f"• `{e[:200]}`" for e in health["errors"])
            + f"\n*Close month:* {close_month}"
        )

    print(f"\n═══ Done ({health['status']}) — {health['duration_seconds']}s ═══")
    print(f"    http://10.0.204.191/affiliates-recon-dashboard")


if __name__ == "__main__":
    main()
