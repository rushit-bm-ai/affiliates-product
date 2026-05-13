"""Recon pipeline entrypoint — pull → compute → render → log health → alert."""

import argparse
import json
import os
import shutil
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import requests

import config
from recon import pull as pull_module
from recon import compute as recon_compute
from monitor import compute as monitor_compute
from dashboard import render as dashboard_render

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
    os.makedirs(config.LOGS_DIR, exist_ok=True)
    log = []
    if os.path.exists(config.HEALTH_LOG_FILE):
        try:
            with open(config.HEALTH_LOG_FILE) as f:
                log = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            log = []
    log.append(entry)
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

    save_snapshot()

    try:
        print("─── Step 1: Data Pull ───")
        pull_module.main(skip_pull=args.skip_pull)
        health["steps"]["data_pull"] = "OK"
        print()

        print("─── Step 2: Compute ───")
        vr = recon_compute.validate_inputs(close_month)
        health["steps"]["validation"] = vr.get("overall_status", "UNKNOWN")

        l1 = recon_compute.compute_reports_vs_invoice(close_month)
        health["steps"]["reports_vs_invoice"] = f"{len(l1['monthly_detail'])} rows, {l1['overall_status']}"

        try:
            l3 = recon_compute.compute_invoice_vs_cash_live(close_month)
            health["steps"]["invoice_vs_cash_live"] = f"{len(l3['collected'])} collected, {len(l3['yet_to_receive'])} pending"
        except Exception as e:
            err = f"Google Sheet pull failed: {e}"
            print(f"[recon] WARNING: {err}")
            health["steps"]["invoice_vs_cash_live"] = "FAILED"
            health["errors"].append(err)

        try:
            mon = monitor_compute.compute_monitor()
            health["steps"]["monitor"] = f"{len(mon['daily'])} daily rows"
        except Exception as e:
            err = f"Monitor compute failed: {e}"
            print(f"[recon] WARNING: {err}")
            health["steps"]["monitor"] = "FAILED"
            health["errors"].append(err)

        try:
            enr = monitor_compute.compute_enrolls()
            health["steps"]["enrolls"] = f"{len(enr['raw'])} raw rows"
        except Exception as e:
            err = f"Enrolls compute failed: {e}"
            print(f"[recon] WARNING: {err}")
            health["steps"]["enrolls"] = "FAILED"
            health["errors"].append(err)

        try:
            apc = monitor_compute.compute_app_completion()
            health["steps"]["app_completion"] = f"{len(apc['rows'])} enroll-week rows"
        except Exception as e:
            err = f"App Completion compute failed: {e}"
            print(f"[recon] WARNING: {err}")
            health["steps"]["app_completion"] = "FAILED"
            health["errors"].append(err)
        print()

        print("─── Step 3: Generate Dashboard ───")
        dashboard_render.main(close_month)
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
