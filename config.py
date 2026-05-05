import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

IST = timezone(timedelta(hours=5, minutes=30))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input_data")
COMPUTED_DIR = os.path.join(BASE_DIR, "computed")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
QUERIES_DIR = os.path.join(BASE_DIR, "queries")
OUTPUT_HTML = os.path.join(BASE_DIR, "index.html")

# ── Metabase ──────────────────────────────────────────────────────────────────
METABASE_HOST = "https://cosmos-metabase.brightmoney.co"
METABASE_USERNAME = "n8n-bot@brightmoney.co"
METABASE_PASSWORD = os.getenv("METABASE_PASSWORD")
METABASE_DATABASE_ID = 2  # dataplatform (Athena)

QUERIES = {
    "reports_by_payout_cycle": {
        "sql_file": os.path.join(QUERIES_DIR, "reports_by_payout_cycle.sql"),
        "file": os.path.join(INPUT_DIR, "reports_by_payout_cycle.csv"),
        "expected_columns": [
            "invoice_month", "partner", "cycle", "reports_revenue",
        ],
    },
}

# ── Google Sheets (Live Finance Data) ─────────────────────────────────────────
GOOGLE_SERVICE_ACCOUNT_KEY = os.getenv("GOOGLE_SA_KEY_PATH", os.path.join(BASE_DIR, "google_sa_key.json"))
GOOGLE_SHEET_ID = "1EJPJubKrClHduO-_EgK-6Sh53dTB7Mmf0o5NHgxVsnQ"
GOOGLE_SHEET_GID = 1688298716
GOOGLE_SHEET_HEADER_ROW = 10
GOOGLE_SHEET_DATA_START = 11

# ── Slack ─────────────────────────────────────────────────────────────────────
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL")

# ── Partners ──────────────────────────────────────────────────────────────────
EXPECTED_PARTNERS = ["moneylion", "amone", "kashkick", "freecash", "brigit", "supermoney"]

GSHEET_PARTNER_MAP = {
    "Engine": "moneylion",
    "AmOne": "amone",
    "Supermoney": "supermoney",
    "Kashkick": "kashkick",
    "Freecash": "freecash",
    "Brigit": "brigit",
}

PARTNER_DISPLAY_NAMES = {
    "moneylion": "MoneyLion",
    "amone": "AmONE",
    "kashkick": "Kashkick",
    "freecash": "Freecash",
    "brigit": "Brigit",
    "supermoney": "Supermoney",
}

PARTNER_CONFIG = {
    "moneylion": {"cycles": "C1+C2", "payment_term": 7, "accel_charge": "3%",
                  "gsheet_name": "Engine"},
    "amone":     {"cycles": "C1", "payment_term": 30, "accel_charge": "—",
                  "gsheet_name": "AmOne"},
    "kashkick":  {"cycles": "C1", "payment_term": 45, "accel_charge": "—",
                  "gsheet_name": "Kashkick"},
    "freecash":  {"cycles": "C1", "payment_term": 30, "accel_charge": "—",
                  "gsheet_name": "Freecash"},
    "brigit":    {"cycles": "C1", "payment_term": 60, "accel_charge": "—",
                  "gsheet_name": "Brigit"},
    "supermoney":{"cycles": "C1", "payment_term": 30, "accel_charge": "—",
                  "gsheet_name": "Supermoney"},
}

# ── Variance Thresholds ──────────────────────────────────────────────────────
VARIANCE_THRESHOLDS = {
    "moneylion": {"green": 5, "amber": 10},
    "amone":     {"green": 5, "amber": 10},
    "DEFAULT":   {"green": 2, "amber": 5},
}

# ── Email (SMTP) ──────────────────────────────────────────────────────────────
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_SENDER = "automation_ops@brightmoney.co"
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_TO = ["rushit.virani@brightmoney.co"]
EMAIL_SUBJECT_TEMPLATE = "Affiliates Recon Report — Week of {date}"
EMAIL_LOG_FILE = os.path.join(LOGS_DIR, "email_log.json")
EMAIL_LOG_MAX_ENTRIES = 90

# ── Health Log ────────────────────────────────────────────────────────────────
HEALTH_LOG_FILE = os.path.join(LOGS_DIR, "health_log.json")
HEALTH_MAX_ENTRIES = 90


def default_close_month():
    today = datetime.now()
    first = today.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.strftime("%Y-%m")


def now_ist():
    return datetime.now(IST)


def utc_to_ist_str(iso_str):
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST)
        return ist_dt.strftime("%Y-%m-%d %H:%M IST")
    except (ValueError, TypeError):
        return iso_str
