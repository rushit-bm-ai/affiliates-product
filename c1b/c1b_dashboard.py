"""
C1B Experiment Impact Dashboard
Metabase + Google Sheets → self-contained HTML dashboard.

Usage:
    python3 c1b_dashboard.py

Output:
    /Users/users/Documents/C1B Analytics/c1b_dashboard.html

Layers:
  1 – Operational Health  (1A funnel rates | 1B API health | 1C impression delivery | 1D assignment balance)
  2 – Revenue Impact      (2A RPU trend | 2B RPU decomposition | 2C cohort maturity)
  4 – Incremental Lift    (4A cannibalization)

RPU = Revenue / all enrolled users in that treatment group (per enroll_week).
"""

import json, os, subprocess, time, sys
from datetime import date, datetime, timedelta
from collections import defaultdict

from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

# ── Config ────────────────────────────────────────────────────────────────────
METABASE_URL  = "https://cosmos-metabase.brightmoney.co"
MB_USER       = "n8n-bot@brightmoney.co"
MB_PASS       = os.getenv("METABASE_PASSWORD", "zuJl3S7MmhpnJ9")
MB_DB_ID      = 2
SA_KEY_PATH   = os.getenv("GOOGLE_SA_KEY_PATH",
                    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "google_sa_key.json"))
PERF_SHEET_ID = "1cATByAMpa5WSQ6mHz0VASF3s_llx7gddp8Ob0HKTL6M"
SCOPES        = ["https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive"]
OUTPUT_PATH   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "c1b_dashboard.html")
EXP_START     = "2026-04-09"

# ═══════════════════════════════════════════════════════════════════════════════
#  SQL
# ═══════════════════════════════════════════════════════════════════════════════

# 1A — Eligibility funnel by signup_week (treatment7 only).
# Returns raw counts; rates computed in Python.
SQL_1A_FUNNEL = """
WITH
latest_debt AS (
    SELECT sa.user_id,
           json_extract_scalar(sa.survey_response, '$.CreditDebt') AS debt_band,
           ROW_NUMBER() OVER (PARTITION BY sa.user_id ORDER BY sa.created DESC) AS rn
    FROM iceberg_db_views.brightmoney_backend_master_2__public__bm_users_surveyanswers AS sa
    WHERE json_extract_scalar(sa.survey_response, '$.CreditDebt') IS NOT NULL
),
latest_cs AS (
    SELECT sa.user_id,
           json_extract_scalar(sa.survey_response, '$.CreditScore') AS cs_band,
           ROW_NUMBER() OVER (PARTITION BY sa.user_id ORDER BY sa.created DESC) AS rn
    FROM iceberg_db_views.brightmoney_backend_master_2__public__bm_users_surveyanswers AS sa
    WHERE json_extract_scalar(sa.survey_response, '$.CreditScore') IS NOT NULL
),
latest_interest AS (
    SELECT sa.user_id,
           json_extract_scalar(sa.survey_response, '$.UserFinancialProductInterest') AS interest_band,
           ROW_NUMBER() OVER (PARTITION BY sa.user_id ORDER BY sa.created DESC) AS rn
    FROM iceberg_db_views.brightmoney_backend_master_2__public__bm_users_surveyanswers AS sa
    WHERE json_extract_scalar(sa.survey_response, '$.UserFinancialProductInterest') IS NOT NULL
),
user_flags AS (
    SELECT
        uc.bright_uid,
        CASE WHEN json_extract_scalar(usm.split_session_data,
                      '$.growth_survey_experiment.treatment') = 'treatment7'
             THEN 1 ELSE 0 END AS meets_cond1,
        CASE WHEN json_extract_scalar(usm.split_session_data,
                      '$.growth_survey_experiment.treatment') = 'treatment7'
             AND d.debt_band NOT IN ('more-than-3000') THEN 1 ELSE 0 END AS meets_cond2,
        CASE WHEN json_extract_scalar(usm.split_session_data,
                      '$.growth_survey_experiment.treatment') = 'treatment7'
             AND d.debt_band NOT IN ('more-than-3000')
             AND c.cs_band NOT IN ('less-than-540') THEN 1 ELSE 0 END AS meets_cond3,
        CASE WHEN json_extract_scalar(usm.split_session_data,
                      '$.growth_survey_experiment.treatment') = 'treatment7'
             AND d.debt_band NOT IN ('more-than-3000')
             AND c.cs_band NOT IN ('less-than-540')
             AND up.is_kyc_verified = true THEN 1 ELSE 0 END AS meets_cond4,
        CASE WHEN json_extract_scalar(usm.split_session_data,
                      '$.growth_survey_experiment.treatment') = 'treatment7'
             AND d.debt_band NOT IN ('more-than-3000')
             AND c.cs_band NOT IN ('less-than-540')
             AND up.is_kyc_verified = true
             AND i.interest_band NOT IN ('only_loans') THEN 1 ELSE 0 END AS meets_cond5
    FROM iceberg_db.meta_cube__user_current_state AS uc
    LEFT JOIN (SELECT user_id, debt_band FROM latest_debt WHERE rn = 1) d ON d.user_id = uc.bm_user_id
    LEFT JOIN (SELECT user_id, cs_band   FROM latest_cs   WHERE rn = 1) c ON c.user_id = uc.bm_user_id
    LEFT JOIN (SELECT user_id, interest_band FROM latest_interest WHERE rn = 1) i ON i.user_id = uc.bm_user_id
    LEFT JOIN iceberg_db_views.brightmoney_backend_master_2__public__bm_users_userprofile AS up
        ON up.bright_user_id = uc.bm_user_id
    LEFT JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
)
SELECT
    DATE(uc.first_enrolled_on)                                                  AS signup_date,
    COUNT(DISTINCT uc.bright_uid)                                               AS enroll_count,
    COUNT(DISTINCT CASE WHEN uf.meets_cond1 = 1 THEN uc.bright_uid END)        AS cond1_treatment7,
    COUNT(DISTINCT CASE WHEN uf.meets_cond2 = 1 THEN uc.bright_uid END)        AS cond2_debt_ok,
    COUNT(DISTINCT CASE WHEN uf.meets_cond3 = 1 THEN uc.bright_uid END)        AS cond3_cs_ok,
    COUNT(DISTINCT CASE WHEN uf.meets_cond4 = 1 THEN uc.bright_uid END)        AS cond4_kyc_ok,
    COUNT(DISTINCT CASE WHEN uf.meets_cond5 = 1 THEN uc.bright_uid END)        AS cond5_eligible
FROM iceberg_db.meta_cube__user_current_state AS uc
LEFT JOIN user_flags uf ON uf.bright_uid = uc.bright_uid
WHERE DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
GROUP BY DATE(uc.first_enrolled_on)
ORDER BY signup_date DESC
""".replace("{exp_start}", EXP_START)

# 1B — API health: one best-status row per user, grouped by enroll_week × segment × status.
SQL_1B_API_HEALTH = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           date_trunc('week', uc.first_enrolled_on) AS enroll_week
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') = 'treatment7'
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid, date_trunc('week', uc.first_enrolled_on)
),
sessions_deduped AS (
    SELECT
        ou.bright_uid,
        sess.status,
        aou.segmentation_treatment,
        ROW_NUMBER() OVER (
            PARTITION BY ou.bright_uid
            ORDER BY
                CASE WHEN sess.status IN ('SUCCESS','API_SUCCESS','APPLICATION_SUBMITTED') THEN 0 ELSE 1 END,
                sess.created_date DESC
        ) AS rn
    FROM iceberg_db_views.brightmoney_offers__public__offers_platform_offersessiondetails AS sess
    LEFT JOIN iceberg_db_views.brightmoney_offers__public__offers_platform_user AS ou
        ON ou.id = sess.user_id
    LEFT JOIN iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateofferuser AS aou
        ON aou.bright_uid = ou.bright_uid
    WHERE sess.partner_id = 4
)
SELECT
    ut.enroll_week,
    COALESCE(sd.segmentation_treatment, 'unknown') AS user_segment,
    sd.status,
    COUNT(DISTINCT ut.bright_uid)                  AS user_count
FROM user_treatments ut
INNER JOIN (SELECT * FROM sessions_deduped WHERE rn = 1) sd ON sd.bright_uid = ut.bright_uid
GROUP BY 1, 2, 3
ORDER BY enroll_week DESC, user_segment, status
""".replace("{exp_start}", EXP_START)

# 1B (daily) — API health grouped by enroll date for day-view Report Card.
SQL_1B_API_HEALTH_DAILY = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           DATE(uc.first_enrolled_on) AS enroll_date
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') = 'treatment7'
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid, DATE(uc.first_enrolled_on)
),
sessions_deduped AS (
    SELECT
        ou.bright_uid,
        sess.status,
        ROW_NUMBER() OVER (
            PARTITION BY ou.bright_uid
            ORDER BY
                CASE WHEN sess.status IN ('SUCCESS','API_SUCCESS','APPLICATION_SUBMITTED') THEN 0 ELSE 1 END,
                sess.created_date DESC
        ) AS rn
    FROM iceberg_db_views.brightmoney_offers__public__offers_platform_offersessiondetails AS sess
    LEFT JOIN iceberg_db_views.brightmoney_offers__public__offers_platform_user AS ou
        ON ou.id = sess.user_id
    WHERE sess.partner_id = 4
)
SELECT
    ut.enroll_date,
    sd.status,
    COUNT(DISTINCT ut.bright_uid) AS user_count
FROM user_treatments ut
INNER JOIN (SELECT * FROM sessions_deduped WHERE rn = 1) sd ON sd.bright_uid = ut.bright_uid
GROUP BY 1, 2
ORDER BY enroll_date DESC, status
""".replace("{exp_start}", EXP_START)

# 1C — Impression delivery: per enroll_week, users with offers vs those who got impression vs clicked.
SQL_1C_IMPRESSION = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           date_trunc('week', uc.first_enrolled_on) AS enroll_week
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') = 'treatment7'
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid, date_trunc('week', uc.first_enrolled_on)
),
success_buids AS (
    SELECT DISTINCT ou.bright_uid
    FROM iceberg_db_views.brightmoney_offers__public__offers_platform_offersessiondetails AS sess
    LEFT JOIN iceberg_db_views.brightmoney_offers__public__offers_platform_user AS ou
        ON ou.id = sess.user_id
    WHERE sess.partner_id = 4
      AND sess.status IN ('SUCCESS','API_SUCCESS','APPLICATION_SUBMITTED')
),
funnel_imps AS (
    SELECT DISTINCT imp.bright_uid,
           MAX(CASE WHEN imp.is_clicked = true THEN 1 ELSE 0 END) AS clicked
    FROM iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateimpressions AS imp
    LEFT JOIN iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateproduct AS ap
        ON ap.id = imp.affiliate_product_id
    WHERE imp.source = 'FUNNEL'
      AND ap.product_name = 'pre_qual_cc'
    GROUP BY imp.bright_uid
)
SELECT
    ut.enroll_week,
    COUNT(DISTINCT ut.bright_uid)                                             AS t7_enrolls,
    COUNT(DISTINCT sb.bright_uid)                                             AS users_with_offers,
    COUNT(DISTINCT CASE WHEN sb.bright_uid IS NOT NULL THEN fi.bright_uid END) AS users_with_impression,
    COUNT(DISTINCT CASE WHEN sb.bright_uid IS NOT NULL AND fi.clicked = 1 THEN fi.bright_uid END) AS users_clicked
FROM user_treatments ut
LEFT JOIN success_buids sb ON sb.bright_uid = ut.bright_uid
LEFT JOIN funnel_imps   fi ON fi.bright_uid = ut.bright_uid
GROUP BY 1
ORDER BY enroll_week DESC
""".replace("{exp_start}", EXP_START)

# 1C (daily) — Impression delivery grouped by enroll date for day-view Report Card.
SQL_1C_IMPRESSION_DAILY = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           DATE(uc.first_enrolled_on) AS enroll_date
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') = 'treatment7'
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid, DATE(uc.first_enrolled_on)
),
success_buids AS (
    SELECT DISTINCT ou.bright_uid
    FROM iceberg_db_views.brightmoney_offers__public__offers_platform_offersessiondetails AS sess
    LEFT JOIN iceberg_db_views.brightmoney_offers__public__offers_platform_user AS ou
        ON ou.id = sess.user_id
    WHERE sess.partner_id = 4
      AND sess.status IN ('SUCCESS','API_SUCCESS','APPLICATION_SUBMITTED')
),
funnel_imps AS (
    SELECT DISTINCT imp.bright_uid,
           MAX(CASE WHEN imp.is_clicked = true THEN 1 ELSE 0 END) AS clicked
    FROM iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateimpressions AS imp
    LEFT JOIN iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateproduct AS ap
        ON ap.id = imp.affiliate_product_id
    WHERE imp.source = 'FUNNEL'
      AND ap.product_name = 'pre_qual_cc'
    GROUP BY imp.bright_uid
)
SELECT
    ut.enroll_date,
    COUNT(DISTINCT sb.bright_uid)                                               AS users_with_offers,
    COUNT(DISTINCT CASE WHEN sb.bright_uid IS NOT NULL THEN fi.bright_uid END)  AS users_with_impression,
    COUNT(DISTINCT CASE WHEN sb.bright_uid IS NOT NULL AND fi.clicked = 1 THEN fi.bright_uid END) AS users_clicked
FROM user_treatments ut
LEFT JOIN success_buids sb ON sb.bright_uid = ut.bright_uid
LEFT JOIN funnel_imps   fi ON fi.bright_uid = ut.bright_uid
GROUP BY 1
ORDER BY enroll_date DESC
""".replace("{exp_start}", EXP_START)

# 1D — Assignment balance: treatment3 vs treatment7 enrolls per week + debt/CS quality proxy.
SQL_1D_BALANCE = """
WITH
user_treatments AS (
    SELECT
        uc.bright_uid,
        uc.bm_user_id,
        MAX(json_extract_scalar(usm.split_session_data,
                '$.growth_survey_experiment.treatment')) AS treatment,
        date_trunc('week', uc.first_enrolled_on)         AS enroll_week
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') IN ('treatment3','treatment7')
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid, uc.bm_user_id, date_trunc('week', uc.first_enrolled_on)
),
latest_debt AS (
    SELECT sa.user_id,
           json_extract_scalar(sa.survey_response, '$.CreditDebt') AS debt_band,
           ROW_NUMBER() OVER (PARTITION BY sa.user_id ORDER BY sa.created DESC) AS rn
    FROM iceberg_db_views.brightmoney_backend_master_2__public__bm_users_surveyanswers AS sa
    WHERE json_extract_scalar(sa.survey_response, '$.CreditDebt') IS NOT NULL
),
latest_cs AS (
    SELECT sa.user_id,
           json_extract_scalar(sa.survey_response, '$.CreditScore') AS cs_band,
           ROW_NUMBER() OVER (PARTITION BY sa.user_id ORDER BY sa.created DESC) AS rn
    FROM iceberg_db_views.brightmoney_backend_master_2__public__bm_users_surveyanswers AS sa
    WHERE json_extract_scalar(sa.survey_response, '$.CreditScore') IS NOT NULL
)
SELECT
    ut.enroll_week,
    ut.treatment,
    COUNT(DISTINCT ut.bright_uid)                                                               AS enrolls,
    COUNT(DISTINCT CASE WHEN d.debt_band IS NOT NULL AND d.debt_band NOT IN ('more-than-3000')
                        THEN ut.bright_uid END)                                                 AS debt_pass,
    COUNT(DISTINCT CASE WHEN c.cs_band   IS NOT NULL AND c.cs_band   NOT IN ('less-than-540')
                        THEN ut.bright_uid END)                                                 AS cs_pass
FROM user_treatments ut
LEFT JOIN (SELECT user_id, debt_band FROM latest_debt WHERE rn = 1) d ON d.user_id = ut.bm_user_id
LEFT JOIN (SELECT user_id, cs_band   FROM latest_cs   WHERE rn = 1) c ON c.user_id = ut.bm_user_id
GROUP BY 1, 2
ORDER BY enroll_week DESC, treatment
""".replace("{exp_start}", EXP_START)

# 1E — User segment overlap: treatment3 vs treatment7 users by affiliate segmentation_treatment.
# Sanity check that both arms have balanced segment distributions.
SQL_1E_USER_OVERLAP = """
WITH
user_treatments AS (
    SELECT
        uc.bright_uid,
        MAX(json_extract_scalar(usm.split_session_data,
            '$.growth_survey_experiment.treatment')) AS treatment
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') IN ('treatment3', 'treatment7')
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid
),
user_segments AS (
    SELECT
        ut.bright_uid,
        ut.treatment,
        COALESCE(aou.segmentation_treatment, 'None') AS user_segment
    FROM user_treatments ut
    LEFT JOIN iceberg_db_views.brightmoney_affiliate__public__affiliate_affiliateofferuser AS aou
        ON aou.bright_uid = ut.bright_uid
    WHERE COALESCE(aou.segmentation_treatment, 'None') NOT IN (
        'None', 'engine_l1', 'both_l1', 'amone_l1',
        'engine_l2_NS2', 'treatment9', 'treatment1', 'treatment17'
    )
),
totals AS (
    SELECT treatment, COUNT(DISTINCT bright_uid) AS total
    FROM user_segments
    GROUP BY treatment
),
by_segment AS (
    SELECT
        user_segment,
        COUNT(DISTINCT CASE WHEN treatment = 'treatment3' THEN bright_uid END) AS control_count,
        COUNT(DISTINCT CASE WHEN treatment = 'treatment7' THEN bright_uid END) AS test_count
    FROM user_segments
    GROUP BY user_segment
)
SELECT
    bs.user_segment,
    bs.control_count,
    ROUND(bs.control_count * 100.0 / tc.total, 1) AS control_pct,
    bs.test_count,
    ROUND(bs.test_count * 100.0 / tt.total, 1) AS test_pct
FROM by_segment bs
CROSS JOIN (SELECT total FROM totals WHERE treatment = 'treatment3') tc
CROSS JOIN (SELECT total FROM totals WHERE treatment = 'treatment7') tt
ORDER BY (bs.control_count + bs.test_count) DESC
""".replace("{exp_start}", EXP_START)

# 2A / 2C / 4A — Base affiliate payout per enroll_week × treatment (no C1B bounty).
SQL_BASE_RPU = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           MAX(json_extract_scalar(usm.split_session_data,
               '$.growth_survey_experiment.treatment')) AS treatment
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') IN ('treatment3','treatment7')
      AND DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY uc.bright_uid
),
payouts AS (
    SELECT bright_uid, SUM(payout) AS total_payout
    FROM iceberg_db.affiliate__revenue_uid_enriched_v0
    GROUP BY bright_uid
)
SELECT
    date_trunc('week', uc.first_enrolled_on)    AS enroll_week,
    CASE ut.treatment
        WHEN 'treatment7' THEN 'Test (treatment7)'
        WHEN 'treatment3' THEN 'Control (treatment3)'
    END                                          AS grp,
    COUNT(DISTINCT uc.bright_uid)                AS enrolls,
    COALESCE(SUM(p.total_payout), 0)             AS affiliate_payout
FROM iceberg_db.meta_cube__user_current_state AS uc
INNER JOIN user_treatments ut ON ut.bright_uid = uc.bright_uid
LEFT JOIN  payouts p           ON p.bright_uid  = uc.bright_uid
WHERE DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
GROUP BY date_trunc('week', uc.first_enrolled_on), ut.treatment
ORDER BY enroll_week DESC, ut.treatment
""".replace("{exp_start}", EXP_START)

# 2B / 4A — Per-partner payout breakdown by enroll_week × treatment.
SQL_PARTNER_PAYOUTS = """
WITH
user_treatments AS (
    SELECT uc.bright_uid,
           MAX(json_extract_scalar(usm.split_session_data,
               '$.growth_survey_experiment.treatment')) AS treatment
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN iceberg_db.brightmoney_backend_master_2__public__bm_users_userstatemachinesessiondata__base AS usm
        ON usm.user_id = uc.bm_user_id
    WHERE json_extract_scalar(usm.split_session_data,
              '$.growth_survey_experiment.treatment') IN ('treatment3','treatment7')
    GROUP BY uc.bright_uid
),
enrolls AS (
    SELECT date_trunc('week', uc.first_enrolled_on) AS enroll_week,
           ut.treatment,
           COUNT(DISTINCT uc.bright_uid)             AS enrolls
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN user_treatments ut ON ut.bright_uid = uc.bright_uid
    WHERE DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
    GROUP BY 1, 2
),
partner_payouts AS (
    SELECT date_trunc('week', uc.first_enrolled_on) AS enroll_week,
           ut.treatment,
           ace.partner,
           SUM(ace.payout)                           AS payout
    FROM iceberg_db.meta_cube__user_current_state AS uc
    INNER JOIN user_treatments ut ON ut.bright_uid = uc.bright_uid
    INNER JOIN iceberg_db.affiliate__engagement_conversion_enriched AS ace
        ON ace.bright_uid = uc.bright_uid
    WHERE DATE(uc.first_enrolled_on) >= DATE '{exp_start}'
      AND ace.partner IS NOT NULL AND ace.partner != 'Unknown' AND ace.payout > 0
    GROUP BY 1, 2, 3
)
SELECT
    e.enroll_week,
    CASE e.treatment
        WHEN 'treatment7' THEN 'Test (treatment7)'
        WHEN 'treatment3' THEN 'Control (treatment3)'
    END                              AS grp,
    e.enrolls,
    COALESCE(pp.partner, 'no_payout') AS partner,
    COALESCE(pp.payout,  0.0)         AS payout
FROM enrolls e
LEFT JOIN partner_payouts pp
    ON pp.enroll_week = e.enroll_week AND pp.treatment = e.treatment
ORDER BY e.enroll_week DESC, e.treatment, COALESCE(pp.payout, 0.0) DESC
""".replace("{exp_start}", EXP_START)


# ═══════════════════════════════════════════════════════════════════════════════
#  Metabase helpers
# ═══════════════════════════════════════════════════════════════════════════════

def metabase_auth():
    payload = json.dumps({"username": MB_USER, "password": MB_PASS})
    r = subprocess.run(
        ["curl", "-s", "--max-time", "120", "-k", "-X", "POST",
         f"{METABASE_URL}/api/session",
         "-H", "Content-Type: application/json", "-d", payload],
        capture_output=True, text=True,
    )
    data = json.loads(r.stdout)
    token = data.get("id")
    if not token:
        raise RuntimeError(f"Metabase auth failed: {r.stdout}")
    return token


def run_query(session, sql):
    payload = json.dumps({"database": MB_DB_ID, "type": "native", "native": {"query": sql}})
    r = subprocess.run(
        ["curl", "-s", "--max-time", "300", "-k", "-X", "POST",
         f"{METABASE_URL}/api/dataset",
         "-H", "Content-Type: application/json",
         "-H", f"X-Metabase-Session: {session}",
         "-d", payload],
        capture_output=True, text=True, timeout=310,
    )
    data = json.loads(r.stdout)
    if data.get("status") != "completed":
        raise RuntimeError(f"Query failed: {data.get('error', r.stdout[:300])}")
    cols = [c["name"] for c in data["data"]["cols"]]
    rows = data["data"]["rows"]
    return cols, rows


def to_records(cols, rows):
    return [dict(zip(cols, r)) for r in rows]


def parse_week(s):
    return str(s).strip().split("T")[0]


# ═══════════════════════════════════════════════════════════════════════════════
#  Data fetching
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_c1b_pivot(sh):
    """Read P: Conversions Pivot from performance sheet → {week_str: total_payout}."""
    try:
        ws   = sh.worksheet("P: Conversions Pivot")
        rows = ws.get_all_values()
        col  = {h: i for i, h in enumerate(rows[0])}
        out  = {}
        for r in rows[1:]:
            wk = parse_week(r[col["enroll_week"]])
            try:    out[wk] = float(r[col["total_payout"]])
            except: out[wk] = 0.0
        return out
    except Exception as e:
        print(f"  WARNING: could not read P: Conversions Pivot — {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════════
#  Processing helpers
# ═══════════════════════════════════════════════════════════════════════════════

def pct(num, den, decimals=2):
    if not den: return 0.0
    return round(num / den * 100, decimals)


def fmt_pct(v):
    return f"{v:.2f}%"


def fmt_dollar(v):
    return f"${v:.2f}"


def fmt_num(v):
    """Plain number: up to 2 dp, no trailing zeros, no decimals if whole."""
    if v is None:
        return "—"
    rounded = round(float(v), 2)
    if rounded == int(rounded):
        return str(int(rounded))
    s = f"{rounded:.2f}"
    return s.rstrip("0")


def delta_class(v):
    if v is None: return "neutral-val"
    return "positive" if v > 0 else ("negative" if v < 0 else "neutral-val")


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1A — Funnel rates
# ═══════════════════════════════════════════════════════════════════════════════

def process_1a(cols, rows):
    records = to_records(cols, rows)
    out = []
    for r in records:
        wk  = parse_week(r["signup_date"])
        ec  = int(r["enroll_count"] or 0)
        c1  = int(r["cond1_treatment7"] or 0)
        c2  = int(r["cond2_debt_ok"]    or 0)
        c3  = int(r["cond3_cs_ok"]      or 0)
        c4  = int(r["cond4_kyc_ok"]     or 0)
        c5  = int(r["cond5_eligible"]   or 0)
        out.append({
            "week": wk,
            "enroll_count": ec,
            "t7_count": c1,
            "debt_count": c2,
            "cs_count": c3,
            "kyc_count": c4,
            "eligible_count": c5,
            "t7_rate":      pct(c1, ec),
            "debt_rate":    pct(c2, c1),
            "cs_rate":      pct(c3, c2),
            "kyc_rate":     pct(c4, c3),
            "interest_rate":      pct(c5, c4),
            "net_eligible_rate":  pct(c5, c1),
        })
    return out


def agg_1a(records, period):
    """Aggregate day-level 1A records. period: 'day' | 'week' | 'month'"""
    from datetime import datetime, timedelta
    buckets = defaultdict(lambda: defaultdict(int))
    for r in records:
        dt = datetime.strptime(r["week"][:10], "%Y-%m-%d")
        if period == "day":
            key = dt.strftime("%Y-%m-%d")
        elif period == "week":
            monday = dt - timedelta(days=dt.weekday())
            key = monday.strftime("%Y-%m-%d")
        else:
            key = dt.strftime("%Y-%m")
        for col in ("enroll_count", "t7_count", "debt_count", "cs_count", "kyc_count", "eligible_count"):
            buckets[key][col] += r[col]
    out = []
    for key in sorted(buckets.keys(), reverse=True):
        b = buckets[key]
        ec, c1, c2, c3, c4, c5 = (b["enroll_count"], b["t7_count"], b["debt_count"],
                                    b["cs_count"], b["kyc_count"], b["eligible_count"])
        out.append({
            "week": key,
            "enroll_count": ec,  "t7_count": c1,  "debt_count": c2,
            "cs_count": c3,      "kyc_count": c4, "eligible_count": c5,
            "t7_rate":           pct(c1, ec),
            "debt_rate":         pct(c2, c1),
            "cs_rate":           pct(c3, c2),
            "kyc_rate":          pct(c4, c3),
            "interest_rate":     pct(c5, c4),
            "net_eligible_rate": pct(c5, c1),
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1B — API health
# ═══════════════════════════════════════════════════════════════════════════════

def process_1b(cols, rows):
    records = to_records(cols, rows)

    # Aggregate by week
    by_week = defaultdict(lambda: defaultdict(int))
    for r in records:
        wk     = parse_week(r["enroll_week"])
        status = r["status"]
        seg    = r["user_segment"]
        cnt    = int(r["user_count"] or 0)
        by_week[wk]["total"] += cnt
        by_week[wk][status]  += cnt
        # flag l1/l2 (wrong segment — 0% success)
        if seg in ("l1", "l2"):
            by_week[wk]["l1l2_wasted"] += cnt

    out = []
    for wk in sorted(by_week.keys(), reverse=True):
        d     = by_week[wk]
        total = d["total"]
        succ  = d.get("SUCCESS", 0) + d.get("API_SUCCESS", 0) + d.get("APPLICATION_SUBMITTED", 0)
        fail  = total - succ
        out.append({
            "week": wk, "total": total,
            "success": succ, "success_rate": pct(succ, total),
            "failure": fail, "failure_rate": pct(fail, total),
        })
    return out


def process_1b_daily(cols, rows):
    """API health aggregated by enroll date for day-view Report Card."""
    records = to_records(cols, rows)
    by_day = defaultdict(lambda: defaultdict(int))
    for r in records:
        day    = parse_week(r["enroll_date"])
        status = r["status"]
        cnt    = int(r["user_count"] or 0)
        by_day[day]["total"] += cnt
        by_day[day][status]  += cnt
    out = []
    for day in sorted(by_day.keys(), reverse=True):
        d     = by_day[day]
        total = d["total"]
        succ  = d.get("SUCCESS", 0) + d.get("API_SUCCESS", 0) + d.get("APPLICATION_SUBMITTED", 0)
        out.append({"date": day, "total": total, "success": succ})
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1C — Impression delivery
# ═══════════════════════════════════════════════════════════════════════════════

def process_1c(cols, rows):
    records = to_records(cols, rows)
    out = []
    for r in records:
        wk      = parse_week(r["enroll_week"])
        enrolls = int(r["t7_enrolls"]            or 0)
        offered = int(r["users_with_offers"]      or 0)
        imped   = int(r["users_with_impression"]  or 0)
        clicked = int(r["users_clicked"]          or 0)
        out.append({
            "week": wk,
            "t7_enrolls": enrolls,
            "users_with_offers": offered,
            "users_with_impression": imped,
            "users_clicked": clicked,
            "delivery_rate": pct(imped,   offered),
            "ctr":           pct(clicked, imped),
            "impression_rate_of_enrolls": pct(imped, enrolls),
        })
    return out


def process_1c_daily(cols, rows):
    """Impression delivery aggregated by enroll date for day-view Report Card."""
    records = to_records(cols, rows)
    out = []
    for r in records:
        day     = parse_week(r["enroll_date"])
        imped   = int(r["users_with_impression"] or 0)
        clicked = int(r["users_clicked"]         or 0)
        out.append({"date": day, "users_with_impression": imped, "users_clicked": clicked})
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1D — Assignment balance
# ═══════════════════════════════════════════════════════════════════════════════

def process_1d(cols, rows):
    records = to_records(cols, rows)

    by_week = defaultdict(dict)
    for r in records:
        wk  = parse_week(r["enroll_week"])
        grp = "test" if r["treatment"] == "treatment7" else "ctrl"
        by_week[wk][grp] = {
            "enrolls":   int(r["enrolls"]    or 0),
            "debt_pass": int(r["debt_pass"]  or 0),
            "cs_pass":   int(r["cs_pass"]    or 0),
        }

    out = []
    for wk in sorted(by_week.keys(), reverse=True):
        d    = by_week[wk]
        test = d.get("test", {})
        ctrl = d.get("ctrl", {})
        te, ce = test.get("enrolls", 0), ctrl.get("enrolls", 0)
        total = te + ce
        out.append({
            "week": wk,
            "test_enrolls": te,
            "ctrl_enrolls": ce,
            "t7_share": pct(te, total),
            "test_debt_rate": pct(test.get("debt_pass", 0), te),
            "ctrl_debt_rate": pct(ctrl.get("debt_pass", 0), ce),
            "test_cs_rate":   pct(test.get("cs_pass", 0),   te),
            "ctrl_cs_rate":   pct(ctrl.get("cs_pass", 0),   ce),
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1E — User segment overlap
# ═══════════════════════════════════════════════════════════════════════════════

def process_1e(cols, rows):
    records = to_records(cols, rows)
    out = []
    for r in records:
        ctrl_n = int(r["control_count"] or 0)
        test_n = int(r["test_count"]    or 0)
        out.append({
            "segment":     r["user_segment"],
            "ctrl_count":  ctrl_n,
            "ctrl_pct":    float(r["control_pct"] or 0),
            "test_count":  test_n,
            "test_pct":    float(r["test_pct"]    or 0),
            "delta_pct":   round(float(r["test_pct"] or 0) - float(r["control_pct"] or 0), 2),
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 2A — RPU trend
# ═══════════════════════════════════════════════════════════════════════════════

def process_2a(base_cols, base_rows, c1b_map):
    records = to_records(base_cols, base_rows)
    pivot = {}  # week → {grp: {enrolls, affiliate_payout}}
    for r in records:
        wk  = parse_week(r["enroll_week"])
        grp = r["grp"]
        pivot.setdefault(wk, {})[grp] = {
            "enrolls": int(r["enrolls"] or 0),
            "affiliate_payout": float(r["affiliate_payout"] or 0),
        }

    today = date.today()
    out = []
    cumul = {"test_rev": 0, "ctrl_rev": 0, "test_n": 0, "ctrl_n": 0}

    for wk in sorted(pivot.keys()):
        d       = pivot[wk]
        test    = d.get("Test (treatment7)",    {})
        ctrl    = d.get("Control (treatment3)", {})
        t_enr   = test.get("enrolls", 0)
        c_enr   = ctrl.get("enrolls", 0)
        t_aff   = test.get("affiliate_payout", 0.0)
        c_aff   = ctrl.get("affiliate_payout", 0.0)
        c1b     = c1b_map.get(wk, 0.0)
        t_total = t_aff + c1b
        c_total = c_aff

        t_rpu = round(t_total / t_enr, 4) if t_enr else 0.0
        c_rpu = round(c_total / c_enr, 4) if c_enr else 0.0
        delta = round(t_rpu - c_rpu, 4)
        lift  = round(delta / c_rpu * 100, 1) if c_rpu else None

        cumul["test_rev"] += t_total
        cumul["ctrl_rev"] += c_total
        cumul["test_n"]   += t_enr
        cumul["ctrl_n"]   += c_enr
        cum_t_rpu = round(cumul["test_rev"] / cumul["test_n"], 4) if cumul["test_n"] else 0.0
        cum_c_rpu = round(cumul["ctrl_rev"] / cumul["ctrl_n"], 4) if cumul["ctrl_n"] else 0.0

        # weeks since enroll for cohort maturity
        try:
            wk_date = datetime.strptime(wk, "%Y-%m-%d").date()
            weeks_maturity = (today - wk_date).days // 7
        except:
            weeks_maturity = None

        out.append({
            "week": wk,
            "test_enrolls": t_enr, "ctrl_enrolls": c_enr,
            "test_aff_rpu":  round(t_aff / t_enr, 4) if t_enr else 0.0,
            "test_c1b_rpu":  round(c1b   / t_enr, 4) if t_enr else 0.0,
            "test_rpu":  t_rpu,
            "ctrl_rpu":  c_rpu,
            "delta_rpu": delta,
            "pct_lift":  lift,
            "cum_test_rpu": cum_t_rpu,
            "cum_ctrl_rpu": cum_c_rpu,
            "cum_delta":    round(cum_t_rpu - cum_c_rpu, 4),
            "t_total_rev": t_total,
            "c_total_rev": c_total,
            "c1b_rev":     c1b,
            "weeks_maturity": weeks_maturity,
        })

    out.reverse()  # newest first for display
    return out, cumul


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 2B — RPU decomposition (C1B vs loan affiliate)
# ═══════════════════════════════════════════════════════════════════════════════

def process_2b(partner_cols, partner_rows, c1b_map):
    records = to_records(partner_cols, partner_rows)

    # {(wk, grp): {enrolls, partners: {name: payout}}}
    data = {}
    for r in records:
        wk      = parse_week(r["enroll_week"])
        grp     = r["grp"]
        enrolls = int(r["enrolls"] or 0)
        partner = r["partner"]
        payout  = float(r["payout"] or 0)
        key = (wk, grp)
        if key not in data:
            data[key] = {"enrolls": enrolls, "loan_payout": 0.0}
        if partner not in ("no_payout",) and payout > 0:
            data[key]["loan_payout"] += payout

    # Inject C1B payout into Test rows
    for (wk, grp), d in data.items():
        if "treatment7" in grp:
            d["c1b_payout"] = c1b_map.get(wk, 0.0)
        else:
            d["c1b_payout"] = 0.0

    out = []
    for (wk, grp) in sorted(data.keys(), reverse=True):
        d      = data[(wk, grp)]
        enr    = d["enrolls"]
        loan   = d["loan_payout"]
        c1b    = d["c1b_payout"]
        total  = loan + c1b
        out.append({
            "week": wk, "grp": grp, "enrolls": enr,
            "loan_rpu":  round(loan  / enr, 4) if enr else 0.0,
            "c1b_rpu":   round(c1b   / enr, 4) if enr else 0.0,
            "total_rpu": round(total / enr, 4) if enr else 0.0,
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 4A — Cannibalization
# ═══════════════════════════════════════════════════════════════════════════════

def process_4a(rpu_rows):
    """
    Uses already-processed 2A rows (which have test_aff_rpu, ctrl_rpu, test_c1b_rpu).
    loan_rpu_delta = test_aff_rpu - ctrl_rpu  (negative → cannibalization)
    net_lift = test_c1b_rpu + loan_rpu_delta
    """
    out = []
    for r in rpu_rows:
        loan_delta = round(r["test_aff_rpu"] - r["ctrl_rpu"], 4)
        net_lift   = round(r["test_c1b_rpu"] + loan_delta, 4)
        out.append({
            "week": r["week"],
            "test_enrolls": r["test_enrolls"],
            "ctrl_enrolls": r["ctrl_enrolls"],
            "ctrl_loan_rpu":   r["ctrl_rpu"],
            "test_loan_rpu":   r["test_aff_rpu"],
            "loan_rpu_delta":  loan_delta,
            "test_c1b_rpu":    r["test_c1b_rpu"],
            "gross_lift_rpu":  r["delta_rpu"],
            "net_lift_rpu":    net_lift,
        })
    return out


# ═══════════════════════════════════════════════════════════════════════════════
#  HTML generation helpers
# ═══════════════════════════════════════════════════════════════════════════════

CHART_COLORS = {
    "test":    "#2563eb",
    "ctrl":    "#9ca3af",
    "c1b":     "#16a34a",
    "loan":    "#60a5fa",
    "delta":   "#f59e0b",
    "success": "#16a34a",
    "declined":"#dc2626",
    "failed":  "#f59e0b",
    "running": "#8b5cf6",
    "waste":   "#6b7280",
}

_chart_id = [0]
def next_chart_id():
    _chart_id[0] += 1
    return f"chart_{_chart_id[0]}"


def chart_js(canvas_id, cfg_dict):
    cfg_json = json.dumps(cfg_dict)
    return f"""
<script>
(function(){{
  var ctx = document.getElementById('{canvas_id}').getContext('2d');
  new Chart(ctx, {cfg_json});
}})();
</script>"""


def line_chart(canvas_id, labels, datasets, title=""):
    return chart_js(canvas_id, {
        "type": "line",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 12}},
                "legend": {"position": "top", "labels": {"boxWidth": 12, "font": {"size": 11}}},
            },
            "scales": {
                "x": {"ticks": {"font": {"size": 10}}},
                "y": {"ticks": {"font": {"size": 10}}},
            },
        },
    })


def bar_chart(canvas_id, labels, datasets, title="", stacked=False):
    return chart_js(canvas_id, {
        "type": "bar",
        "data": {"labels": labels, "datasets": datasets},
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {"display": bool(title), "text": title, "font": {"size": 12}},
                "legend": {"position": "top", "labels": {"boxWidth": 12, "font": {"size": 11}}},
            },
            "scales": {
                "x": {"stacked": stacked, "ticks": {"font": {"size": 10}}},
                "y": {"stacked": stacked, "ticks": {"font": {"size": 10}}},
            },
        },
    })


def table_html(headers, rows_data, col_classes=None):
    th_html = "".join(f"<th>{h}</th>" for h in headers)
    trs = []
    for row in rows_data:
        tds = []
        for i, cell in enumerate(row):
            cls = col_classes[i] if col_classes and i < len(col_classes) else ""
            cls_attr = f' class="{cls}"' if cls else ""
            tds.append(f"<td{cls_attr}>{cell}</td>")
        trs.append("<tr>" + "".join(tds) + "</tr>")
    return f'<div class="tbl-wrap"><table><thead><tr>{th_html}</tr></thead><tbody>{"".join(trs)}</tbody></table></div>'


def view_card(title, content, full_width=False):
    cls = ' class="card full"' if full_width else ' class="card"'
    return f'<div{cls}><h3>{title}</h3>{content}</div>'


def canvas(cid, height=280):
    return f'<div class="chart-wrap" style="height:{height}px"><canvas id="{cid}"></canvas></div>'


# ═══════════════════════════════════════════════════════════════════════════════
#  Section renderers
# ═══════════════════════════════════════════════════════════════════════════════

def render_1a(day_data):
    def _lbl(r, period):
        return r["week"] if period == "month" else r["week"][-5:]

    def _build(period):
        agg = agg_1a(day_data, period)
        labels = [_lbl(r, period) for r in agg]
        tbl = table_html(
            ["Period", "Enrolls", "T7", "T7%", "Debt OK", "Debt%", "CS OK", "CS%",
             "KYC OK", "KYC%", "Interest OK", "Interest(CC)%", "Net Eligible%"],
            [[r["week"], r["enroll_count"], r["t7_count"],
              fmt_pct(r["t7_rate"]), r["debt_count"], fmt_pct(r["debt_rate"]),
              r["cs_count"], fmt_pct(r["cs_rate"]),
              r["kyc_count"], fmt_pct(r["kyc_rate"]),
              r["eligible_count"], fmt_pct(r["interest_rate"]), fmt_pct(r["net_eligible_rate"])]
             for r in agg],
        )
        return {
            "labels":   labels,
            "rate_ds":  [
                [r["t7_rate"]       for r in agg],
                [r["debt_rate"]     for r in agg],
                [r["cs_rate"]       for r in agg],
                [r["kyc_rate"]      for r in agg],
                [r["interest_rate"] for r in agg],
            ],
            "count_ds": [
                [r["t7_count"]       for r in agg],
                [r["debt_count"]     for r in agg],
                [r["cs_count"]       for r in agg],
                [r["kyc_count"]      for r in agg],
                [r["eligible_count"] for r in agg],
            ],
            "tbl": tbl,
        }

    views = {p: _build(p) for p in ("day", "week", "month")}
    dw    = views["week"]  # default

    cid1 = next_chart_id()
    cid2 = next_chart_id()
    tid  = f"tbl1a_{cid1}"
    fn   = f"set1aView_{cid1}"

    rate_cfg = {
        "type": "line",
        "data": {"labels": dw["labels"], "datasets": [
            {"label": "Treatment7 %",    "data": dw["rate_ds"][0], "borderColor": CHART_COLORS["test"], "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Debt pass %",     "data": dw["rate_ds"][1], "borderColor": "#3b82f6", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "CS ≥540 pass %",  "data": dw["rate_ds"][2], "borderColor": "#f59e0b", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "KYC pass %",      "data": dw["rate_ds"][3], "borderColor": "#8b5cf6", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Interest (CC) %", "data": dw["rate_ds"][4], "borderColor": "#dc2626", "backgroundColor": "transparent", "tension": 0.3},
        ]},
        "options": {"responsive": True, "maintainAspectRatio": False,
            "plugins": {"title": {"display": True, "text": "Step-over-step pass rates (treatment7 users)", "font": {"size": 12}},
                        "legend": {"position": "top", "labels": {"boxWidth": 12, "font": {"size": 11}}}},
            "scales": {"x": {"ticks": {"font": {"size": 10}}}, "y": {"ticks": {"font": {"size": 10}}}}},
    }
    count_cfg = {
        "type": "bar",
        "data": {"labels": dw["labels"], "datasets": [
            {"label": "Treatment7", "data": dw["count_ds"][0], "backgroundColor": "#93c5fd"},
            {"label": "Debt pass",  "data": dw["count_ds"][1], "backgroundColor": "#60a5fa"},
            {"label": "CS pass",    "data": dw["count_ds"][2], "backgroundColor": "#3b82f6"},
            {"label": "KYC pass",   "data": dw["count_ds"][3], "backgroundColor": "#2563eb"},
            {"label": "Eligible",   "data": dw["count_ds"][4], "backgroundColor": "#1d4ed8"},
        ]},
        "options": {"responsive": True, "maintainAspectRatio": False,
            "plugins": {"title": {"display": True, "text": "Funnel count", "font": {"size": 12}},
                        "legend": {"position": "top", "labels": {"boxWidth": 12, "font": {"size": 11}}}},
            "scales": {"x": {"ticks": {"font": {"size": 10}}}, "y": {"ticks": {"font": {"size": 10}}}}},
    }

    # Strip tbl from JS payload (sent separately to avoid double-encoding)
    js_views = {p: {k: v for k, v in views[p].items() if k != "tbl"} for p in views}
    js_tbls  = {p: views[p]["tbl"] for p in views}

    rate_cfg_json  = json.dumps(rate_cfg)
    count_cfg_json = json.dumps(count_cfg)
    js_views_json  = json.dumps(js_views)
    js_tbls_json   = json.dumps(js_tbls)

    toggle = f"""<div style="display:flex;gap:6px;align-items:center;margin-bottom:16px;">
  <span style="font-size:11px;font-weight:600;color:#718096;margin-right:2px;">Granularity:</span>
  <button class="period-btn-1a" data-p="day"   onclick="{fn}('day',this)"  style="padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer;border-radius:20px;border:1.5px solid #d1e8d8;background:#fff;color:#5c7a62;font-family:inherit;transition:.15s;">Day on Day</button>
  <button class="period-btn-1a period-btn-1a-active" data-p="week" onclick="{fn}('week',this)" style="padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer;border-radius:20px;border:1.5px solid #0f4625;background:#0f4625;color:#fff;font-family:inherit;transition:.15s;">Week on Week</button>
  <button class="period-btn-1a" data-p="month" onclick="{fn}('month',this)" style="padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer;border-radius:20px;border:1.5px solid #d1e8d8;background:#fff;color:#5c7a62;font-family:inherit;transition:.15s;">Month on Month</button>
</div>"""

    script = f"""
<script>
(function(){{
  var ctx1 = document.getElementById('{cid1}').getContext('2d');
  var chart1 = new Chart(ctx1, {rate_cfg_json});
  var ctx2 = document.getElementById('{cid2}').getContext('2d');
  var chart2 = new Chart(ctx2, {count_cfg_json});
  var _views = {js_views_json};
  var _tbls  = {js_tbls_json};
  window['{fn}'] = function(period, el) {{
    document.querySelectorAll('.period-btn-1a').forEach(function(b) {{
      b.style.background = '#fff'; b.style.color = '#5c7a62'; b.style.borderColor = '#d1e8d8';
    }});
    el.style.background = '#0f4625'; el.style.color = '#fff'; el.style.borderColor = '#0f4625';
    var d = _views[period];
    chart1.data.labels = d.labels;
    d.rate_ds.forEach(function(vals, i) {{ chart1.data.datasets[i].data = vals; }});
    chart1.update();
    chart2.data.labels = d.labels;
    d.count_ds.forEach(function(vals, i) {{ chart2.data.datasets[i].data = vals; }});
    chart2.update();
    document.getElementById('{tid}').innerHTML = _tbls[period];
  }};
}})();
</script>"""

    return f"""{toggle}
<div class="view-grid">
{view_card("Step-over-Step Pass Rates", canvas(cid1))}
{view_card("Funnel Volume", canvas(cid2))}
</div>
{view_card("Funnel Detail Table", f'<div id="{tid}">{dw["tbl"]}</div>', full_width=True)}
{script}"""


def render_1b(data):
    weeks  = [r["week"] for r in data]
    labels = [w[-5:] for w in weeks]

    cid1 = next_chart_id()
    cid2 = next_chart_id()

    scripts = bar_chart(cid1, labels, [
        {"label": "Success", "data": [r["success"] for r in data], "backgroundColor": CHART_COLORS["success"]},
        {"label": "Failure", "data": [r["failure"] for r in data], "backgroundColor": CHART_COLORS["failed"]},
    ], "API calls: Success vs Failure per week", stacked=True)

    scripts += line_chart(cid2, labels, [
        {"label": "Success rate %", "data": [r["success_rate"] for r in data],
         "borderColor": CHART_COLORS["success"], "backgroundColor": "transparent", "tension": 0.3},
        {"label": "Failure rate %", "data": [r["failure_rate"] for r in data],
         "borderColor": CHART_COLORS["failed"],  "backgroundColor": "transparent", "tension": 0.3},
    ], "API success vs failure rate over time (%)")

    tbl = table_html(
        ["Week", "Total API Calls", "Success", "Succ%", "Failure", "Fail%"],
        [[r["week"], r["total"],
          r["success"], fmt_pct(r["success_rate"]),
          r["failure"], fmt_pct(r["failure_rate"])]
         for r in data],
        col_classes=["", "", "positive", "positive", "negative", "negative"],
    )

    return f"""
<div class="view-grid">
{view_card("API Status Stack by Week", canvas(cid1))}
{view_card("API Rates Over Time", canvas(cid2))}
</div>
{view_card("API Health Table", tbl, full_width=True)}
{scripts}"""


def render_1c(data):
    weeks  = [r["week"] for r in data]
    labels = [w[-5:] for w in weeks]

    cid1 = next_chart_id()
    cid2 = next_chart_id()

    scripts = line_chart(cid1, labels, [
        {"label": "Delivery rate % (imps/offers)",   "data": [r["delivery_rate"] for r in data],
         "borderColor": CHART_COLORS["test"], "backgroundColor": "transparent", "tension": 0.3},
        {"label": "CTR % (clicks/imps)",             "data": [r["ctr"]           for r in data],
         "borderColor": CHART_COLORS["c1b"],  "backgroundColor": "transparent", "tension": 0.3},
    ], "Delivery rate & CTR over time")

    scripts += bar_chart(cid2, labels, [
        {"label": "Users with offers",     "data": [r["users_with_offers"]      for r in data], "backgroundColor": "#93c5fd"},
        {"label": "Users with impression", "data": [r["users_with_impression"]  for r in data], "backgroundColor": "#2563eb"},
        {"label": "Users clicked",         "data": [r["users_clicked"]          for r in data], "backgroundColor": "#16a34a"},
    ], "Offer → Impression → Click funnel by week")

    tbl = table_html(
        ["Week", "T7 Enrolls", "Users with Offers", "Users with Impression", "Delivery Rate", "Users Clicked", "CTR"],
        [[r["week"], r["t7_enrolls"],
          r["users_with_offers"], r["users_with_impression"],
          fmt_pct(r["delivery_rate"]),
          r["users_clicked"], fmt_pct(r["ctr"])]
         for r in data],
    )

    return f"""
<div class="view-grid">
{view_card("Delivery Rate & CTR", canvas(cid1))}
{view_card("Offer → Impression → Click Volume", canvas(cid2))}
</div>
{view_card("Impression Delivery Table", tbl, full_width=True)}
{scripts}"""


def render_1d(data):
    weeks  = [r["week"] for r in data]
    labels = [w[-5:] for w in weeks]

    cid1 = next_chart_id()
    cid2 = next_chart_id()

    scripts = bar_chart(cid1, labels, [
        {"label": "Test (T7) enrolls",    "data": [r["test_enrolls"] for r in data], "backgroundColor": CHART_COLORS["test"]},
        {"label": "Control (T3) enrolls", "data": [r["ctrl_enrolls"] for r in data], "backgroundColor": CHART_COLORS["ctrl"]},
    ], "Weekly enroll count per treatment")

    scripts += line_chart(cid2, labels, [
        {"label": "Test debt≤3k %",  "data": [r["test_debt_rate"] for r in data],
         "borderColor": CHART_COLORS["test"], "backgroundColor": "transparent", "tension": 0.3},
        {"label": "Ctrl debt≤3k %",  "data": [r["ctrl_debt_rate"] for r in data],
         "borderColor": CHART_COLORS["ctrl"], "backgroundColor": "transparent", "tension": 0.3, "borderDash": [4,4]},
        {"label": "Test CS≥540 %",   "data": [r["test_cs_rate"] for r in data],
         "borderColor": "#f59e0b", "backgroundColor": "transparent", "tension": 0.3},
        {"label": "Ctrl CS≥540 %",   "data": [r["ctrl_cs_rate"] for r in data],
         "borderColor": "#d97706", "backgroundColor": "transparent", "tension": 0.3, "borderDash": [4,4]},
    ], "User quality proxy: debt & credit score rates by treatment")

    tbl = table_html(
        ["Week", "Test Enrolls", "Ctrl Enrolls", "T7 Share%",
         "Test Debt≤3k%", "Ctrl Debt≤3k%", "Test CS≥540%", "Ctrl CS≥540%"],
        [[r["week"], r["test_enrolls"], r["ctrl_enrolls"],
          fmt_pct(r["t7_share"]),
          fmt_pct(r["test_debt_rate"]), fmt_pct(r["ctrl_debt_rate"]),
          fmt_pct(r["test_cs_rate"]),   fmt_pct(r["ctrl_cs_rate"])]
         for r in data],
    )

    return f"""
<div class="view-grid">
{view_card("Weekly Enroll Split by Treatment", canvas(cid1))}
{view_card("User Quality Proxy (Test vs Control)", canvas(cid2))}
</div>
{view_card("Assignment Balance Table", tbl, full_width=True)}
{scripts}"""


def render_1e(data):
    segments = [r["segment"] for r in data]

    cid1 = next_chart_id()

    scripts = bar_chart(cid1, segments, [
        {"label": "Control (T3)", "data": [r["ctrl_pct"] for r in data], "backgroundColor": CHART_COLORS["ctrl"]},
        {"label": "Test (T7)",    "data": [r["test_pct"] for r in data], "backgroundColor": CHART_COLORS["test"]},
    ], "Segment share % — Control vs Test")

    tbl = table_html(
        ["Segment", "Control Count", "Control %", "Test Count", "Test %", "Δ %"],
        [[r["segment"], r["ctrl_count"], fmt_pct(r["ctrl_pct"]),
          r["test_count"], fmt_pct(r["test_pct"]),
          f"{r['delta_pct']:+.2f}%"]
         for r in data],
        col_classes=["", "", "", "", "", ""],
    )

    return f"""
<div class="view-grid">
{view_card("Segment Share: Control vs Test", canvas(cid1))}
</div>
{view_card("User Segment Overlap Table", tbl, full_width=True)}
{scripts}"""


def render_2a(data, cumul):
    rev = list(reversed(data))  # oldest → newest for chart x-axis
    labels = [r["week"][-5:] for r in rev]

    cid1 = next_chart_id()
    cid2 = next_chart_id()
    cid3 = next_chart_id()

    # Chart 1 — Test vs Control RPU line
    scripts = line_chart(cid1, labels, [
        {"label": "Test RPU",    "data": [r["test_rpu"] for r in rev],
         "borderColor": CHART_COLORS["test"], "backgroundColor": "transparent", "tension": 0.3, "pointRadius": 4},
        {"label": "Control RPU", "data": [r["ctrl_rpu"] for r in rev],
         "borderColor": CHART_COLORS["ctrl"], "backgroundColor": "transparent", "tension": 0.3, "pointRadius": 4},
    ], "Weekly RPU: Test vs Control")

    # Chart 2 — RPU composition: Test (Loan + C1B stacked) vs Control
    scripts += bar_chart(cid2, labels, [
        {"label": "Test: Loan RPU", "data": [r["test_aff_rpu"] for r in rev],
         "backgroundColor": CHART_COLORS["loan"], "stack": "test"},
        {"label": "Test: C1B RPU",  "data": [r["test_c1b_rpu"] for r in rev],
         "backgroundColor": CHART_COLORS["c1b"], "stack": "test"},
        {"label": "Control: Loan RPU", "data": [r["ctrl_rpu"] for r in rev],
         "backgroundColor": CHART_COLORS["ctrl"], "stack": "ctrl"},
    ], "RPU composition: Test (Loan + C1B) vs Control", stacked=True)

    # Chart 3 — Δ RPU bar
    scripts += bar_chart(cid3, labels, [
        {"label": "Δ RPU (Test − Control)",
         "data": [r["delta_rpu"] for r in rev],
         "backgroundColor": [CHART_COLORS["c1b"] if r["delta_rpu"] >= 0 else "#dc2626" for r in rev]},
    ], "Weekly RPU Delta (Test − Control)")

    tbl = table_html(
        ["Week", "Test Enrolls", "Ctrl Enrolls",
         "Test Loan RPU", "Test C1B RPU", "Test Total RPU",
         "Ctrl RPU", "Δ RPU", "Lift %"],
        [[r["week"], r["test_enrolls"], r["ctrl_enrolls"],
          fmt_dollar(r["test_aff_rpu"]), fmt_dollar(r["test_c1b_rpu"]),
          fmt_dollar(r["test_rpu"]),     fmt_dollar(r["ctrl_rpu"]),
          fmt_dollar(r["delta_rpu"]),
          (fmt_pct(r["pct_lift"]) if r["pct_lift"] is not None else "—")]
         for r in data],
        col_classes=["","","","","","positive","",
                     *[delta_class(r["delta_rpu"]) for r in data[:1]], ""],
    )

    return f"""
<div class="view-grid">
{view_card("Weekly RPU: Test vs Control", canvas(cid1))}
{view_card("RPU Composition: Test (Loan + C1B) vs Control", canvas(cid2))}
</div>
{view_card("Weekly RPU Delta (Test − Control)", canvas(cid3), full_width=True)}
{view_card("RPU Weekly Detail", tbl, full_width=True)}
{scripts}"""


def render_2b(data):
    # Split into Test and Control for side-by-side
    test_rows = [r for r in data if "treatment7" in r["grp"]]
    ctrl_rows = [r for r in data if "treatment3" in r["grp"]]

    weeks  = sorted(set(r["week"] for r in data), reverse=True)
    labels = [w[-5:] for w in reversed(weeks)]

    cid1 = next_chart_id()
    cid2 = next_chart_id()

    # Test stacked: loan + c1b
    test_map = {r["week"]: r for r in test_rows}
    ctrl_map = {r["week"]: r for r in ctrl_rows}

    scripts = bar_chart(cid1, labels, [
        {"label": "Test: Loan Affiliate RPU", "data": [test_map.get(w, {}).get("loan_rpu", 0) for w in reversed(weeks)],
         "backgroundColor": CHART_COLORS["loan"], "stack": "test"},
        {"label": "Test: C1B RPU",            "data": [test_map.get(w, {}).get("c1b_rpu",  0) for w in reversed(weeks)],
         "backgroundColor": CHART_COLORS["c1b"], "stack": "test"},
        {"label": "Control: Loan Affiliate RPU","data": [ctrl_map.get(w, {}).get("loan_rpu", 0) for w in reversed(weeks)],
         "backgroundColor": CHART_COLORS["ctrl"], "stack": "ctrl"},
    ], "RPU composition: Test (loan + C1B) vs Control (loan only)", stacked=True)

    scripts += line_chart(cid2, labels, [
        {"label": "Test total RPU",    "data": [test_map.get(w, {}).get("total_rpu", 0) for w in reversed(weeks)],
         "borderColor": CHART_COLORS["test"], "backgroundColor": "transparent", "tension": 0.3},
        {"label": "Test loan RPU",     "data": [test_map.get(w, {}).get("loan_rpu",  0) for w in reversed(weeks)],
         "borderColor": CHART_COLORS["loan"], "backgroundColor": "transparent", "tension": 0.3, "borderDash": [4,4]},
        {"label": "Test C1B RPU",      "data": [test_map.get(w, {}).get("c1b_rpu",   0) for w in reversed(weeks)],
         "borderColor": CHART_COLORS["c1b"],  "backgroundColor": "transparent", "tension": 0.3},
        {"label": "Control loan RPU",  "data": [ctrl_map.get(w, {}).get("loan_rpu",  0) for w in reversed(weeks)],
         "borderColor": CHART_COLORS["ctrl"], "backgroundColor": "transparent", "tension": 0.3},
    ], "RPU components over time")

    tbl_rows = []
    for w in weeks:
        t = test_map.get(w, {})
        c = ctrl_map.get(w, {})
        tbl_rows.append([
            w,
            fmt_dollar(t.get("loan_rpu", 0)),
            fmt_dollar(t.get("c1b_rpu",  0)),
            fmt_dollar(t.get("total_rpu",0)),
            fmt_dollar(c.get("loan_rpu", 0)),
            fmt_dollar(c.get("total_rpu",0)),
        ])

    tbl = table_html(
        ["Week", "Test: Loan RPU", "Test: C1B RPU", "Test: Total RPU",
         "Ctrl: Loan RPU", "Ctrl: Total RPU"],
        tbl_rows,
    )

    return f"""
<div class="view-grid">
{view_card("RPU Composition: Test vs Control", canvas(cid1))}
{view_card("RPU Components Over Time", canvas(cid2))}
</div>
{view_card("RPU Decomposition Table", tbl, full_width=True)}
{scripts}"""


def render_2c(rpu_rows):
    """Cohort maturity: each enroll_week cohort's RPU vs its age (weeks since enroll)."""
    rows = [r for r in rpu_rows if r["weeks_maturity"] is not None]

    # Separate Test and Control
    # rpu_rows already has test_rpu and ctrl_rpu per week
    # Plot: x = weeks_maturity, y = cumulative RPU (proxy: test_rpu cumulative at that maturity)
    # Since we don't have time-series per cohort, we show the achieved RPU of each cohort
    # plotted against its current maturity — older cohorts should have higher RPU

    sorted_rows = sorted(rows, key=lambda r: r.get("weeks_maturity", 0))
    maturities = [r["weeks_maturity"] for r in sorted_rows]
    test_rpus  = [r["test_rpu"]       for r in sorted_rows]
    ctrl_rpus  = [r["ctrl_rpu"]       for r in sorted_rows]
    labels     = [f"W{r['weeks_maturity']} ({r['week'][-5:]})" for r in sorted_rows]

    cid1 = next_chart_id()

    scripts = line_chart(cid1, labels, [
        {"label": "Test RPU",    "data": test_rpus,
         "borderColor": CHART_COLORS["test"], "backgroundColor": "rgba(37,99,235,0.1)", "fill": True, "tension": 0.3, "pointRadius": 5},
        {"label": "Control RPU","data": ctrl_rpus,
         "borderColor": CHART_COLORS["ctrl"], "backgroundColor": "rgba(156,163,175,0.1)", "fill": True, "tension": 0.3, "pointRadius": 5},
    ], "RPU by cohort maturity (weeks since enrollment)")

    tbl = table_html(
        ["Enroll Week", "Weeks Mature", "Test Enrolls", "Ctrl Enrolls",
         "Test RPU", "Ctrl RPU", "Δ RPU", "C1B Revenue", "Test Total Revenue"],
        [[r["week"], r.get("weeks_maturity","?"),
          r["test_enrolls"], r["ctrl_enrolls"],
          fmt_dollar(r["test_rpu"]),
          fmt_dollar(r["ctrl_rpu"]),
          fmt_dollar(r["delta_rpu"]),
          f"${r['c1b_rev']:.2f}",
          f"${r['t_total_rev']:.2f}"]
         for r in sorted(rpu_rows, key=lambda x: x["week"])],
    )

    return f"""
{view_card("RPU by Cohort Maturity", canvas(cid1, height=320), full_width=True)}
{view_card("Cohort Detail Table", tbl, full_width=True)}
{scripts}"""


def render_4a(data):
    weeks  = [r["week"] for r in data]
    labels = [w[-5:] for w in reversed(weeks)]
    rev_data = list(reversed(data))

    cid1 = next_chart_id()
    cid2 = next_chart_id()

    scripts = bar_chart(cid1, labels, [
        {"label": "Test: Loan Affiliate RPU",    "data": [r["test_loan_rpu"]  for r in rev_data],
         "backgroundColor": CHART_COLORS["test"]},
        {"label": "Control: Loan Affiliate RPU", "data": [r["ctrl_loan_rpu"]  for r in rev_data],
         "backgroundColor": CHART_COLORS["ctrl"]},
    ], "Loan affiliate RPU: Test vs Control (cannibalization check)")

    scripts += bar_chart(cid2, labels, [
        {"label": "C1B RPU (incremental)",        "data": [r["test_c1b_rpu"]   for r in rev_data],
         "backgroundColor": CHART_COLORS["c1b"]},
        {"label": "Loan RPU delta (Test−Ctrl)",   "data": [r["loan_rpu_delta"] for r in rev_data],
         "backgroundColor": [CHART_COLORS["c1b"] if r["loan_rpu_delta"] >= 0 else "#dc2626"
                             for r in rev_data]},
        {"label": "Net lift RPU",                 "data": [r["net_lift_rpu"]   for r in rev_data],
         "backgroundColor": "#7c3aed"},
    ], "Cannibalization decomposition: C1B gain vs Loan loss → Net lift")

    tbl = table_html(
        ["Week", "Test Enr", "Ctrl Enr",
         "Ctrl Loan RPU", "Test Loan RPU", "Loan Δ (cannibaliz.)",
         "C1B RPU", "Gross Lift", "Net Lift"],
        [[r["week"], r["test_enrolls"], r["ctrl_enrolls"],
          fmt_dollar(r["ctrl_loan_rpu"]),
          fmt_dollar(r["test_loan_rpu"]),
          fmt_dollar(r["loan_rpu_delta"]),
          fmt_dollar(r["test_c1b_rpu"]),
          fmt_dollar(r["gross_lift_rpu"]),
          fmt_dollar(r["net_lift_rpu"])]
         for r in data],
        col_classes=["","","","","",
                     *[delta_class(r["loan_rpu_delta"]) for r in data[:1]],
                     "positive",
                     *[delta_class(r["gross_lift_rpu"]) for r in data[:1]],
                     *[delta_class(r["net_lift_rpu"])   for r in data[:1]]],
    )

    return f"""
<div class="view-grid">
{view_card("Loan Affiliate RPU: Test vs Control", canvas(cid1))}
{view_card("C1B Gain vs Loan Loss vs Net Lift", canvas(cid2))}
</div>
{view_card("Cannibalization Detail Table", tbl, full_width=True)}
{scripts}"""


# ═══════════════════════════════════════════════════════════════════════════════
#  KPI cards
# ═══════════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 0 — Report Card
# ═══════════════════════════════════════════════════════════════════════════════

def process_0(funnel_data, api_data, imp_data, rpu_rows):
    funnel_idx = {r["week"]: r for r in funnel_data}
    api_idx    = {r["week"]: r for r in api_data}
    imp_idx    = {r["week"]: r for r in imp_data}
    rpu_idx    = {r["week"]: r for r in rpu_rows}

    all_weeks = sorted(
        set(funnel_idx) | set(api_idx) | set(imp_idx) | set(rpu_idx),
        reverse=True,
    )

    out = []
    for wk in all_weeks:
        f = funnel_idx.get(wk, {})
        a = api_idx.get(wk, {})
        i = imp_idx.get(wk, {})
        r = rpu_idx.get(wk, {})

        enrolls  = f.get("enroll_count", 0)
        t7       = f.get("t7_count", 0)
        eligible = f.get("eligible_count", 0)

        api_calls = a.get("total", 0)
        api_succ  = a.get("success", 0)

        imps   = i.get("users_with_impression", 0)
        clicks = i.get("users_clicked", 0)

        test_rpu  = r.get("test_rpu",  0.0)
        ctrl_rpu  = r.get("ctrl_rpu",  0.0)
        delta_rpu = r.get("delta_rpu", 0.0)
        pct_lift  = r.get("pct_lift",  None)

        out.append({
            "week":            wk,
            "enrolls":         enrolls,
            "t7":              t7,
            "t7_pct":          pct(t7,       enrolls),
            "eligible":        eligible,
            "net_elig_pct":    pct(eligible,  t7),
            "api_calls":       api_calls,
            "api_call_pct":    pct(api_calls, eligible),
            "api_success":     api_succ,
            "api_succ_pct":    pct(api_succ,  api_calls),
            "impressions":     imps,
            "imp_pct":         pct(imps,      api_succ),
            "clicks":          clicks,
            "ctr":             pct(clicks,    imps),
            "test_rpu":        test_rpu,
            "ctrl_rpu":        ctrl_rpu,
            "delta_rpu":       delta_rpu,
            "pct_lift":        pct_lift,
        })
    return out


def _agg_0_month(rc_weekly):
    buckets = defaultdict(lambda: defaultdict(float))
    for r in rc_weekly:
        key = r["week"][:7]
        for col in ("enrolls", "t7", "eligible", "api_calls", "api_success", "impressions", "clicks"):
            buckets[key][col] += r[col]
    out = []
    for key in sorted(buckets.keys(), reverse=True):
        b  = buckets[key]
        en, t7, el = int(b["enrolls"]), int(b["t7"]), int(b["eligible"])
        ac, as_ = int(b["api_calls"]), int(b["api_success"])
        im, cl  = int(b["impressions"]), int(b["clicks"])
        out.append({
            "week": key,
            "enrolls": en,  "t7": t7,  "t7_pct": pct(t7, en),
            "eligible": el, "net_elig_pct": pct(el, t7),
            "api_calls": ac,  "api_call_pct": pct(ac, el),
            "api_success": as_, "api_succ_pct": pct(as_, ac),
            "impressions": im, "imp_pct": pct(im, as_),
            "clicks": cl,      "ctr": pct(cl, im),
        })
    return out


def _build_rc_day(funnel_day, api_daily, imp_daily):
    """Day-level Report Card using per-day API and impression data."""
    api_idx = {r["date"]: r for r in api_daily}
    imp_idx = {r["date"]: r for r in imp_daily}
    out = []
    for fd in funnel_day:
        day = fd["week"][:10]
        en, t7, el = fd["enroll_count"], fd["t7_count"], fd["eligible_count"]
        a  = api_idx.get(day, {})
        i  = imp_idx.get(day, {})
        ac  = a.get("total",                 0)
        as_ = a.get("success",               0)
        im  = i.get("users_with_impression", 0)
        cl  = i.get("users_clicked",         0)
        out.append({
            "week": fd["week"],
            "enrolls": en,  "t7": t7,  "t7_pct": pct(t7, en),
            "eligible": el, "net_elig_pct": pct(el, t7),
            "api_calls": ac,  "api_call_pct": pct(ac, el),
            "api_success": as_, "api_succ_pct": pct(as_, ac),
            "impressions": im, "imp_pct": pct(im, as_),
            "clicks": cl,      "ctr": pct(cl, im),
        })
    return out


def render_0(rc_data, funnel_day, api_daily, imp_daily):
    def _build(period_data, period):
        rows = list(reversed(period_data))
        lbl  = [r["week"] if period == "month" else r["week"][-5:] for r in rows]
        tbl  = table_html(
            ["Period", "Enrolls", "T7", "T7%",
             "Eligible", "Net Elig%",
             "API Called", "API Call%",
             "API Success", "API Succ%",
             "Impressions", "Imp%",
             "Clicks", "CTR%"],
            [[r["week"],
              r["enrolls"],     r["t7"],          fmt_pct(r["t7_pct"]),
              r["eligible"],    fmt_pct(r["net_elig_pct"]),
              r["api_calls"],   fmt_pct(r["api_call_pct"]),
              r["api_success"], fmt_pct(r["api_succ_pct"]),
              r["impressions"], fmt_pct(r["imp_pct"]),
              r["clicks"],      fmt_pct(r["ctr"])]
             for r in period_data],
            col_classes=["","","","","","","","","positive","positive","","","",""],
        )
        return {
            "labels": lbl,
            "vol_ds": [
                [r["enrolls"]     for r in rows],
                [r["t7"]          for r in rows],
                [r["eligible"]    for r in rows],
                [r["api_calls"]   for r in rows],
                [r["api_success"] for r in rows],
                [r["impressions"] for r in rows],
                [r["clicks"]      for r in rows],
            ],
            "rate_ds": [
                [r["t7_pct"]       for r in rows],
                [r["net_elig_pct"] for r in rows],
                [r["api_call_pct"] for r in rows],
                [r["api_succ_pct"] for r in rows],
                [r["imp_pct"]      for r in rows],
                [r["ctr"]          for r in rows],
            ],
            "tbl": tbl,
        }

    views = {
        "day":   _build(_build_rc_day(funnel_day, api_daily, imp_daily), "day"),
        "week":  _build(rc_data, "week"),
        "month": _build(_agg_0_month(rc_data), "month"),
    }
    dw = views["week"]

    cid1 = next_chart_id()
    cid2 = next_chart_id()
    tid  = f"tbl0_{cid1}"
    fn   = f"set0View_{cid1}"

    vol_cfg = {
        "type": "line",
        "data": {"labels": dw["labels"], "datasets": [
            {"label": "Enrolls",     "data": dw["vol_ds"][0], "borderColor": "#94a3b8", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "T7",          "data": dw["vol_ds"][1], "borderColor": "#3b82f6", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Eligible",    "data": dw["vol_ds"][2], "borderColor": "#8b5cf6", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "API Called",  "data": dw["vol_ds"][3], "borderColor": "#f59e0b", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "API Success", "data": dw["vol_ds"][4], "borderColor": "#22c55e", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Impressions", "data": dw["vol_ds"][5], "borderColor": "#06b6d4", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Clicks",      "data": dw["vol_ds"][6], "borderColor": "#f43f5e", "backgroundColor": "transparent", "tension": 0.3},
        ]},
        "options": {"responsive": True, "maintainAspectRatio": False,
            "plugins": {"title": {"display": True, "text": "Funnel volume", "font": {"size": 12}},
                        "legend": {"position": "top", "labels": {"boxWidth": 12, "font": {"size": 11}}}},
            "scales": {"x": {"ticks": {"font": {"size": 10}}}, "y": {"ticks": {"font": {"size": 10}}}}},
    }
    rate_cfg = {
        "type": "line",
        "data": {"labels": dw["labels"], "datasets": [
            {"label": "T7 % of Enrolls",       "data": dw["rate_ds"][0], "borderColor": "#3b82f6", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Net Eligible % (of T7)", "data": dw["rate_ds"][1], "borderColor": "#8b5cf6", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "API Called % (of Elig)", "data": dw["rate_ds"][2], "borderColor": "#f59e0b", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "API Success %",          "data": dw["rate_ds"][3], "borderColor": "#22c55e", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "Imp Rate % (of Succ)",   "data": dw["rate_ds"][4], "borderColor": "#06b6d4", "backgroundColor": "transparent", "tension": 0.3},
            {"label": "CTR %",                  "data": dw["rate_ds"][5], "borderColor": "#f43f5e", "backgroundColor": "transparent", "tension": 0.3},
        ]},
        "options": {"responsive": True, "maintainAspectRatio": False,
            "plugins": {"title": {"display": True, "text": "Stage conversion rates (%)", "font": {"size": 12}},
                        "legend": {"position": "top", "labels": {"boxWidth": 12, "font": {"size": 11}}}},
            "scales": {"x": {"ticks": {"font": {"size": 10}}}, "y": {"ticks": {"font": {"size": 10}}}}},
    }

    js_views     = {p: {k: v for k, v in views[p].items() if k != "tbl"} for p in views}
    js_tbls      = {p: views[p]["tbl"] for p in views}
    vol_cfg_json  = json.dumps(vol_cfg)
    rate_cfg_json = json.dumps(rate_cfg)
    js_views_json = json.dumps(js_views)
    js_tbls_json  = json.dumps(js_tbls)

    toggle = f"""<div style="display:flex;gap:6px;align-items:center;margin-bottom:16px;">
  <span style="font-size:11px;font-weight:600;color:#718096;margin-right:2px;">Granularity:</span>
  <button class="period-btn-0" data-p="day"   onclick="{fn}('day',this)"   style="padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer;border-radius:20px;border:1.5px solid #d1e8d8;background:#fff;color:#5c7a62;font-family:inherit;transition:.15s;">Day on Day</button>
  <button class="period-btn-0 period-btn-0-active" data-p="week" onclick="{fn}('week',this)" style="padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer;border-radius:20px;border:1.5px solid #0f4625;background:#0f4625;color:#fff;font-family:inherit;transition:.15s;">Week on Week</button>
  <button class="period-btn-0" data-p="month" onclick="{fn}('month',this)" style="padding:5px 14px;font-size:11px;font-weight:700;cursor:pointer;border-radius:20px;border:1.5px solid #d1e8d8;background:#fff;color:#5c7a62;font-family:inherit;transition:.15s;">Month on Month</button>
</div>"""

    script = f"""
<script>
(function(){{
  var ctx1 = document.getElementById('{cid1}').getContext('2d');
  var chart1 = new Chart(ctx1, {vol_cfg_json});
  var ctx2 = document.getElementById('{cid2}').getContext('2d');
  var chart2 = new Chart(ctx2, {rate_cfg_json});
  var _views = {js_views_json};
  var _tbls  = {js_tbls_json};
  window['{fn}'] = function(period, el) {{
    document.querySelectorAll('.period-btn-0').forEach(function(b) {{
      b.style.background = '#fff'; b.style.color = '#5c7a62'; b.style.borderColor = '#d1e8d8';
    }});
    el.style.background = '#0f4625'; el.style.color = '#fff'; el.style.borderColor = '#0f4625';
    var d = _views[period];
    chart1.data.labels = d.labels;
    d.vol_ds.forEach(function(vals, i) {{ chart1.data.datasets[i].data = vals; }});
    chart1.update();
    chart2.data.labels = d.labels;
    d.rate_ds.forEach(function(vals, i) {{ chart2.data.datasets[i].data = vals; }});
    chart2.update();
    document.getElementById('{tid}').innerHTML = _tbls[period];
  }};
}})();
</script>"""

    return f"""{toggle}
<div class="view-grid">
{view_card("Funnel Volume", canvas(cid1))}
{view_card("Stage Conversion Rates (%)", canvas(cid2))}
</div>
{view_card("Report Card Table", f'<div id="{tid}">{dw["tbl"]}</div>', full_width=True)}
{script}"""


def render_kpis(rpu_data, cumul, api_data, imp_data, funnel_data):
    # Aggregate totals across all weeks
    test_enrolls = cumul["test_n"]
    eligible     = sum(r["eligible_count"]        for r in funnel_data)
    offers       = sum(r["users_with_offers"]      for r in imp_data)
    impressions  = sum(r["users_with_impression"]  for r in imp_data)
    clicks       = sum(r["users_clicked"]          for r in imp_data)

    def conv(n, d):
        return fmt_pct(pct(n, d)) if d else "—"

    def step(label, n, rate_label, rate_val):
        return f"""<div class="funnel-card">
  <div class="fc-label">{label}</div>
  <div class="fc-value">{n:,}</div>
  <div class="fc-rate">{rate_label}: <strong>{rate_val}</strong></div>
</div>"""

    arrow = '<div class="funnel-arrow">&#8250;</div>'

    cards = "".join([
        step("Test Enrolls",      test_enrolls, "of total", "100%"),
        arrow,
        step("Eligible Users",    eligible,    "of enrolls",    conv(eligible,    test_enrolls)),
        arrow,
        step("Offers Available",  offers,      "of eligible",   conv(offers,      eligible)),
        arrow,
        step("Impressions Shown", impressions, "of offers",     conv(impressions, offers)),
        arrow,
        step("Clicks",            clicks,      "of impressions",conv(clicks,      impressions)),
    ])
    return f'<div class="funnel-row">{cards}</div>'


# ═══════════════════════════════════════════════════════════════════════════════
#  Full HTML template
# ═══════════════════════════════════════════════════════════════════════════════

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>C1B Impact Dashboard</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{
  --bg:#f0f2f5; --card:#ffffff; --border:#e2e8f0;
  --text:#1a1a2e; --muted:#718096; --subtle:#a0aec0;
  --blue:#3b82f6; --green:#16a34a; --red:#dc2626; --amber:#d97706;
  --primary:#0f172a;
}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);font-size:13px;line-height:1.5;overflow-x:hidden}}

/* ── Main tabs (match recon sub-nav style) ── */
.nav-wrap{{padding:0 28px;background:var(--card);border-bottom:2px solid var(--border);display:flex;gap:0}}
.main-tab{{padding:11px 20px;border:none;background:none;cursor:pointer;font-size:12px;font-weight:600;color:var(--muted);border-bottom:2px solid transparent;margin-bottom:-2px;white-space:nowrap;font-family:inherit;transition:color .15s,border-color .15s}}
.main-tab.active{{color:var(--blue);border-bottom-color:var(--blue)}}
.main-tab:hover:not(.active){{color:var(--text)}}

/* ── Tab content ── */
.tab-pane{{display:none;padding:24px 28px 36px}}
.tab-pane.active{{display:block}}

/* ── Sub-tabs (pills) ── */
.sub-tabs{{display:flex;gap:6px;margin-bottom:18px;flex-wrap:wrap}}
.sub-tab{{padding:6px 14px;border:1.5px solid var(--border);border-radius:20px;background:var(--card);cursor:pointer;font-size:11px;font-weight:700;color:var(--muted);font-family:inherit;transition:.15s}}
.sub-tab.active{{background:var(--primary);color:#fff;border-color:var(--primary)}}
.sub-tab:hover:not(.active){{border-color:var(--blue);color:var(--text)}}
.subtab-pane{{display:none}}
.subtab-pane.active{{display:block}}

/* ── Cards & grid ── */
.view-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}}
@media(max-width:900px){{.view-grid{{grid-template-columns:1fr}}}}
.card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:20px;box-shadow:0 1px 3px rgba(0,0,0,.05)}}
.card h3{{font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-bottom:16px}}
.card.full{{grid-column:1/-1}}
.chart-wrap{{position:relative}}

/* ── Tables ── */
.tbl-wrap{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th{{text-align:left;padding:8px 12px;background:#f8fafc;color:var(--muted);font-weight:700;font-size:10px;text-transform:uppercase;letter-spacing:.6px;border-bottom:1px solid var(--border);white-space:nowrap}}
td{{padding:8px 12px;border-bottom:1px solid var(--border);white-space:nowrap;color:var(--text)}}
tr:last-child td{{border-bottom:none}}
tr:hover td{{background:#f8fafc}}
.positive{{color:var(--green);font-weight:600}}
.negative{{color:var(--red);font-weight:600}}
.neutral-val{{color:var(--muted)}}
</style>
</head>
<body>

<div class="nav-wrap">
  <button class="main-tab active" onclick="showTab('l0',this)">Report Card</button>
  <button class="main-tab"        onclick="showTab('l1',this)">Operational Health</button>
  <button class="main-tab"        onclick="showTab('l2',this)">Revenue Impact</button>
</div>

<!-- Report Card -->
<div id="tab-l0" class="tab-pane active">
{content_0}
</div>

<!-- Operational Health -->
<div id="tab-l1" class="tab-pane">
  <div class="sub-tabs">
    <button class="sub-tab active" onclick="showSub('l1','1a',this)">1A · Eligibility Funnel</button>
    <button class="sub-tab"        onclick="showSub('l1','1b',this)">1B · API Health</button>
    <button class="sub-tab"        onclick="showSub('l1','1c',this)">1C · Impression Delivery</button>
    <button class="sub-tab"        onclick="showSub('l1','1d',this)">1D · Assignment Balance</button>
    <button class="sub-tab"        onclick="showSub('l1','1e',this)">1E · Segment Overlap</button>
  </div>
  <div id="l1-1a" class="subtab-pane active">{content_1a}</div>
  <div id="l1-1b" class="subtab-pane">{content_1b}</div>
  <div id="l1-1c" class="subtab-pane">{content_1c}</div>
  <div id="l1-1d" class="subtab-pane">{content_1d}</div>
  <div id="l1-1e" class="subtab-pane">{content_1e}</div>
</div>

<!-- Revenue Impact -->
<div id="tab-l2" class="tab-pane">
  <div class="sub-tabs">
    <button class="sub-tab active" onclick="showSub('l2','2a',this)">2A · RPU</button>
  </div>
  <div id="l2-2a" class="subtab-pane active">{content_2a}</div>
</div>

<script>
function showTab(id, btn) {{
  document.querySelectorAll('.tab-pane').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.main-tab').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + id).classList.add('active');
  btn.classList.add('active');
  notifyHeight();
}}
function showSub(layer, sub, btn) {{
  var parent = document.getElementById('tab-' + layer);
  parent.querySelectorAll('.subtab-pane').forEach(el => el.classList.remove('active'));
  parent.querySelectorAll('.sub-tab').forEach(el => el.classList.remove('active'));
  document.getElementById(layer + '-' + sub).classList.add('active');
  btn.classList.add('active');
  notifyHeight();
}}
function notifyHeight() {{
  try {{ parent.postMessage({{type:'c1b-height', h: document.body.scrollHeight}}, '*'); }} catch(e) {{}}
}}
if (window.ResizeObserver) {{
  new ResizeObserver(notifyHeight).observe(document.body);
}} else {{
  window.addEventListener('load', notifyHeight);
}}
</script>
</body>
</html>"""


def generate_html(data):
    html = HTML_TEMPLATE.format(
        exp_start    = EXP_START,
        refresh_date = date.today().strftime("%B %d, %Y"),
        content_0    = render_0(data["rc"], data["funnel"], data["api_daily"], data["imp_daily"]),
        content_1a   = render_1a(data["funnel"]),
        content_1b   = render_1b(data["api_health"]),
        content_1c   = render_1c(data["impression"]),
        content_1d   = render_1d(data["balance"]),
        content_1e   = render_1e(data["overlap"]),
        content_2a   = render_2a(data["rpu_rows"], data["cumul"]),
    )
    return html


# ═══════════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 60)
    print("C1B Impact Dashboard")
    print("=" * 60)

    print("\n[1] Metabase auth...", end=" ", flush=True)
    session = metabase_auth()
    print(f"OK")

    print("[2] Google Sheets (C1B bounty pivot)...", end=" ", flush=True)
    creds  = Credentials.from_service_account_file(SA_KEY_PATH, scopes=SCOPES)
    gc     = gspread.authorize(creds)
    sh     = gc.open_by_key(PERF_SHEET_ID)
    c1b_map = fetch_c1b_pivot(sh)
    print(f"OK  {len(c1b_map)} weeks of C1B bounty data")

    queries = [
        ("1A Funnel",        SQL_1A_FUNNEL),
        ("1B API Health",    SQL_1B_API_HEALTH),
        ("1B API Daily",     SQL_1B_API_HEALTH_DAILY),
        ("1C Impressions",   SQL_1C_IMPRESSION),
        ("1C Imp Daily",     SQL_1C_IMPRESSION_DAILY),
        ("1D Balance",       SQL_1D_BALANCE),
        ("1E User Overlap",  SQL_1E_USER_OVERLAP),
        ("2A Base RPU",      SQL_BASE_RPU),
        ("2B Partner Pays",  SQL_PARTNER_PAYOUTS),
    ]

    results = {}
    print("\n[3] Running Metabase queries...")
    for name, sql in queries:
        print(f"  -> {name}...", end=" ", flush=True)
        try:
            cols, rows = run_query(session, sql)
            results[name] = (cols, rows)
            print(f"OK  {len(rows)} rows")
        except Exception as e:
            print(f"FAIL  {e}")
            results[name] = ([], [])

    print("\n[4] Processing data...")
    funnel_data  = process_1a(*results["1A Funnel"])   # day-level
    funnel_weekly = agg_1a(funnel_data, "week")         # week-level for report card
    api_data     = process_1b(*results["1B API Health"])
    api_daily    = process_1b_daily(*results["1B API Daily"])
    imp_data     = process_1c(*results["1C Impressions"])
    imp_daily    = process_1c_daily(*results["1C Imp Daily"])
    bal_data     = process_1d(*results["1D Balance"])
    overlap_data = process_1e(*results["1E User Overlap"])
    rpu_rows, cumul = process_2a(*results["2A Base RPU"], c1b_map)
    decomp_data  = process_2b(*results["2B Partner Pays"], c1b_map)
    cannibal     = process_4a(rpu_rows)
    rc_data      = process_0(funnel_weekly, api_data, imp_data, rpu_rows)

    all_data = {
        "funnel":     funnel_data,
        "api_health": api_data,
        "api_daily":  api_daily,
        "impression": imp_data,
        "imp_daily":  imp_daily,
        "balance":    bal_data,
        "overlap":    overlap_data,
        "rc":         rc_data,
        "rpu_rows":   rpu_rows,
        "cumul":      cumul,
        "decomp":     decomp_data,
        "cannibal":   cannibal,
    }

    print("\n[5] Generating HTML dashboard...")
    html = generate_html(all_data)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'=' * 60}")
    print(f"DONE!  {OUTPUT_PATH}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
