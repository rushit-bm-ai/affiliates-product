"""Monitor computation — payout trends, enrolls, and app completion."""

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import requests

import config


def _save_json(filename, data):
    path = os.path.join(config.COMPUTED_DIR, filename)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    print(f"[monitor.compute] Written → {filename}")


def compute_monitor():
    """Load daily/weekly/monthly payout CSVs and compute KPIs for the Monitor tab."""
    print("[monitor.compute] Monitor data")

    daily_file   = config.QUERIES["daily_by_partner"]["file"]
    weekly_file  = config.QUERIES["weekly_by_partner"]["file"]
    monthly_file = config.QUERIES["monthly_by_partner"]["file"]

    daily   = pd.read_csv(daily_file)   if os.path.exists(daily_file)   else pd.DataFrame(columns=["date","partner","payout"])
    weekly  = pd.read_csv(weekly_file)  if os.path.exists(weekly_file)  else pd.DataFrame(columns=["week_start","partner","payout"])
    monthly = pd.read_csv(monthly_file) if os.path.exists(monthly_file) else pd.DataFrame(columns=["month","partner","payout"])

    daily["payout"]   = pd.to_numeric(daily["payout"],   errors="coerce").fillna(0)
    weekly["payout"]  = pd.to_numeric(weekly["payout"],  errors="coerce").fillna(0)
    monthly["payout"] = pd.to_numeric(monthly["payout"], errors="coerce").fillna(0)

    today      = datetime.now().date()
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    wtd_total = round(float(daily[daily["date"] >= str(week_start)]["payout"].sum()), 2)
    mtd_total = round(float(daily[daily["date"] >= str(month_start)]["payout"].sum()), 2)

    days_so_far     = (today - week_start).days + 1
    lw_start        = week_start - timedelta(weeks=1)
    lw_same_end     = lw_start + timedelta(days=days_so_far - 1)
    lw_same_total   = round(float(
        daily[(daily["date"] >= str(lw_start)) & (daily["date"] <= str(lw_same_end))]["payout"].sum()
    ), 2)
    wow_pct = round((wtd_total - lw_same_total) / lw_same_total * 100, 1) if lw_same_total else None

    lfw_end         = week_start - timedelta(days=1)
    lfw_start       = lfw_end - timedelta(days=6)
    lfw_total       = round(float(
        daily[(daily["date"] >= str(lfw_start)) & (daily["date"] <= str(lfw_end))]["payout"].sum()
    ), 2)
    lltw_end        = lfw_start - timedelta(days=1)
    lltw_start      = lltw_end - timedelta(days=6)
    lltw_total      = round(float(
        daily[(daily["date"] >= str(lltw_start)) & (daily["date"] <= str(lltw_end))]["payout"].sum()
    ), 2)
    lw_vs_llw_pct   = round((lfw_total - lltw_total) / lltw_total * 100, 1) if lltw_total else None

    result = {
        "kpis": {
            "wtd":  {
                "total": wtd_total, "week_start": str(week_start),
                "wow_pct": wow_pct, "lw_same_total": lw_same_total,
                "lfw_total": lfw_total, "lfw_start": str(lfw_start), "lfw_end": str(lfw_end),
                "lltw_total": lltw_total, "lw_vs_llw_pct": lw_vs_llw_pct,
            },
            "mtd":  {"total": mtd_total, "month_start": str(month_start)},
        },
        "daily":   daily.to_dict(orient="records"),
        "weekly":  weekly.to_dict(orient="records"),
        "monthly": monthly.to_dict(orient="records"),
    }
    _save_json("monitor_data.json", result)
    print(f"[monitor.compute] Monitor data complete — {len(daily)} daily rows, {len(weekly)} weekly rows, {len(monthly)} monthly rows")
    return result


SQL_1F_APP_COMPLETION = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           date_trunc('week', uc.first_enrolled_on) AS enroll_week
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') = 'treatment7'
      AND DATE(uc.first_enrolled_on) >= DATE '2026-04-09'
    GROUP BY uc.bright_uid, date_trunc('week', uc.first_enrolled_on)
),
clicked_users AS (
    SELECT DISTINCT imp.bright_uid
    FROM iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateimpressions AS imp
    LEFT JOIN iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateproduct AS ap
        ON ap.id = imp.affiliate_product_id
    WHERE imp.is_clicked = true
      AND imp.source = 'FUNNEL'
      AND ap.product_name = 'pre_qual_cc'
),
last_api_per_user AS (
    SELECT
        ou.bright_uid,
        sess.status,
        ROW_NUMBER() OVER (
            PARTITION BY ou.bright_uid
            ORDER BY sess.created_date DESC
        ) AS rn
    FROM iceberg_db_views.brightmoney_offers__public__offers_platform_offersessiondetails AS sess
    LEFT JOIN iceberg_db_views.brightmoney_offers__public__offers_platform_user AS ou
        ON ou.id = sess.user_id
    WHERE sess.partner_id = 4
)
SELECT
    CAST(ut.enroll_week AS VARCHAR) AS enroll_week,
    COUNT(DISTINCT cu.bright_uid) AS users_clicked,
    COUNT(DISTINCT CASE WHEN las.status IS NOT NULL THEN cu.bright_uid END) AS users_with_api_status,
    COUNT(DISTINCT CASE WHEN las.status = 'APPLICATION_SUBMITTED' THEN cu.bright_uid END) AS users_app_submitted
FROM user_treatments ut
INNER JOIN clicked_users cu ON cu.bright_uid = ut.bright_uid
LEFT JOIN (SELECT * FROM last_api_per_user WHERE rn = 1) las ON las.bright_uid = cu.bright_uid
GROUP BY 1
ORDER BY enroll_week DESC
"""


def compute_app_completion():
    """Fetch click→Application Submitted conversion data from Metabase."""
    resp = requests.post(
        f"{config.METABASE_HOST}/api/session",
        json={"username": config.METABASE_USERNAME, "password": config.METABASE_PASSWORD},
        timeout=60,
    )
    resp.raise_for_status()
    token = resp.json()["id"]

    def run_q(sql):
        r = requests.post(
            f"{config.METABASE_HOST}/api/dataset",
            headers={"X-Metabase-Session": token, "Content-Type": "application/json"},
            json={"database": config.METABASE_DATABASE_ID, "type": "native", "native": {"query": sql}},
            timeout=300,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        cols = [c["name"] for c in data["data"]["cols"]]
        result = []
        for row in data["data"]["rows"]:
            obj = {}
            for c, v in zip(cols, row):
                if isinstance(v, str) and v.endswith("T00:00:00Z"):
                    v = v[:10]
                obj[c] = v
            result.append(obj)
        return result

    print("[monitor.compute] App Completion data")
    rows = run_q(SQL_1F_APP_COMPLETION)
    for row in rows:
        clicked = row.get("users_clicked") or 0
        submitted = row.get("users_app_submitted") or 0
        row["conversion_pct"] = round(submitted / clicked * 100, 1) if clicked else 0.0

    result = {"rows": rows, "generated_at": datetime.now().isoformat()}
    _save_json("app_completion_data.json", result)
    print(f"[monitor.compute] App Completion complete — {len(rows)} enroll-week rows")
    return result


def compute_enrolls():
    """Fetch enrolls rollup data from Metabase."""
    resp = requests.post(
        f"{config.METABASE_HOST}/api/session",
        json={"username": config.METABASE_USERNAME, "password": config.METABASE_PASSWORD},
        timeout=60,
    )
    resp.raise_for_status()
    token = resp.json()["id"]

    def run_q(sql):
        r = requests.post(
            f"{config.METABASE_HOST}/api/dataset",
            headers={"X-Metabase-Session": token, "Content-Type": "application/json"},
            json={"database": config.METABASE_DATABASE_ID, "type": "native", "native": {"query": sql}},
            timeout=300,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("error"):
            raise RuntimeError(data["error"])
        cols = [c["name"] for c in data["data"]["cols"]]
        result = []
        for row in data["data"]["rows"]:
            obj = {}
            for c, v in zip(cols, row):
                if isinstance(v, str) and v.endswith("T00:00:00Z"):
                    v = v[:10]
                obj[c] = v
            result.append(obj)
        return result

    PC = ("case when partner='AmoneAPI' then 'AmONE' when partner='PBrigit' then 'Brigit' "
          "when partner='Pkashkick' then 'Kashkick' when partner='PSupermoney' then 'SuperMoney' "
          "when partner='PFreecash' then 'Freecash' else partner end")
    BASE   = "iceberg_db.affiliate__revenue_uid_enriched_v0"
    FILTER = "first_enrolled_on is not null and enrol_status='Enrol'"

    print("[monitor.compute] Enrolls data")
    raw = run_q(
        f"select date(first_enrolled_on) as enroll_date, {PC} as partner, "
        f"coalesce(imp_source,'(none)') as imp_source, payout_cohort_bucket, "
        f"count(distinct bright_uid) as enrolled_users, count(distinct api_lead_id) as total_leads, "
        f"round(sum(payout),2) as total_payout, round(avg(payout),2) as avg_payout "
        f"from {BASE} where {FILTER} and first_enrolled_on >= current_date - interval '30' day "
        f"group by 1,2,3,4 order by 1 desc,2,3,4"
    )
    monthly = run_q(
        f"select date_format(date_trunc('month',cast(first_enrolled_on as timestamp)),'%Y-%m') as enroll_month, "
        f"{PC} as partner, count(distinct bright_uid) as enrolled_users "
        f"from {BASE} where {FILTER} group by 1,2 order by 1,2"
    )
    cohort = run_q(
        f"select date_format(date_trunc('month',cast(first_enrolled_on as timestamp)),'%Y-%m') as enroll_month, "
        f"payout_cohort_bucket, count(distinct bright_uid) as enrolled_users, "
        f"round(sum(coalesce(payout,0)),2) as total_payout "
        f"from {BASE} where {FILTER} group by 1,2 order by 1,2"
    )
    imp = run_q(
        f"select date_format(date_trunc('month',cast(first_enrolled_on as timestamp)),'%Y-%m') as enroll_month, "
        f"coalesce(imp_source,'(none)') as imp_source, count(distinct bright_uid) as enrolled_users "
        f"from {BASE} where {FILTER} group by 1,2 order by 1,2"
    )

    result = {"raw": raw, "monthly": monthly, "cohort": cohort, "imp": imp}
    _save_json("enroll_data.json", result)
    print(f"[monitor.compute] Enrolls complete — {len(raw)} raw, {len(monthly)} monthly, "
          f"{len(cohort)} cohort, {len(imp)} imp rows")
    return result
