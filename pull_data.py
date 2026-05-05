"""Metabase data pull + file validation."""

import os
import json
import csv
from datetime import datetime

import requests

import config


def authenticate():
    url = f"{config.METABASE_HOST}/api/session"
    resp = requests.post(url, json={
        "username": config.METABASE_USERNAME,
        "password": config.METABASE_PASSWORD,
    }, timeout=120)
    resp.raise_for_status()
    token = resp.json()["id"]
    print(f"[pull_data] Authenticated with Metabase (token: {token[:8]}…)")
    return token


def pull_native_query(token, query_config):
    sql_file = query_config["sql_file"]
    outfile = query_config["file"]
    with open(sql_file) as f:
        sql = f.read()

    url = f"{config.METABASE_HOST}/api/dataset"
    headers = {"X-Metabase-Session": token, "Content-Type": "application/json"}
    payload = {
        "database": config.METABASE_DATABASE_ID,
        "type": "native",
        "native": {"query": sql},
    }
    print(f"[pull_data] Running {os.path.basename(sql_file)} → {os.path.basename(outfile)} …")
    resp = requests.post(url, headers=headers, json=payload, timeout=300)
    resp.raise_for_status()

    result = resp.json()
    if result.get("error"):
        raise RuntimeError(f"Metabase query error: {result['error']}")

    data = result.get("data", {})
    cols = [c["name"] for c in data.get("cols", [])]
    rows = data.get("rows", [])

    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    with open(outfile, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        writer.writerows(rows)

    print(f"[pull_data]   ✓ {len(rows)} rows written")
    return len(rows)


def validate_file(filepath, expected_cols):
    result = {
        "file": os.path.basename(filepath),
        "exists": False,
        "row_count": 0,
        "columns_found": [],
        "columns_missing": [],
        "status": "FAIL",
    }
    if not os.path.exists(filepath):
        result["error"] = "File not found"
        return result
    result["exists"] = True
    with open(filepath, "r") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            result["error"] = "Empty file"
            return result
        result["columns_found"] = header
        result["columns_missing"] = [c for c in expected_cols if c not in header]
        rows = sum(1 for row in reader if any(cell.strip() for cell in row))
        result["row_count"] = rows
    result["status"] = "PASS" if not result["columns_missing"] and rows > 0 else "FAIL"
    return result


def main(skip_pull=False):
    os.makedirs(config.COMPUTED_DIR, exist_ok=True)
    pull_log = {"pull_timestamp": config.now_ist().strftime("%Y-%m-%d %H:%M IST"), "files": {}}

    if skip_pull:
        print("[pull_data] --skip-pull: using cached CSVs")
    else:
        token = authenticate()
        for name, qcfg in config.QUERIES.items():
            try:
                rc = pull_native_query(token, qcfg)
                pull_log["files"][name] = {"status": "pulled", "rows": rc}
            except Exception as e:
                print(f"[pull_data] ERROR pulling {name}: {e}")
                pull_log["files"][name] = {"status": "error", "error": str(e)}

    # Validate all files
    for name, qcfg in config.QUERIES.items():
        vr = validate_file(qcfg["file"], qcfg["expected_columns"])
        pull_log["files"].setdefault(name, {})
        pull_log["files"][name].update(vr)
        status_icon = "✓" if vr["status"] == "PASS" else "✗"
        print(f"[pull_data] {status_icon} {vr['file']}: {vr['row_count']} rows, {vr['status']}")
        if vr["columns_missing"]:
            print(f"           Missing columns: {vr['columns_missing']}")

    log_path = os.path.join(config.COMPUTED_DIR, "pull_log.json")
    with open(log_path, "w") as f:
        json.dump(pull_log, f, indent=2)
    print(f"[pull_data] Pull log written → {os.path.basename(log_path)}")
    return pull_log


if __name__ == "__main__":
    main()
