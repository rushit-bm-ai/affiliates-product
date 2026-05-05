# Affiliates Recon Dashboard

## Project Overview
Python-based reconciliation dashboard for affiliate partners. Pulls data from Metabase + Google Sheets, computes variances, generates a static HTML dashboard, and emails a weekly report.

## Repo
- GitHub: https://github.com/rushit-bm-ai/affiliates-product
- Server: `ssh ubuntu@10.0.204.191` (VPN required)
- Server path: `~/recon-dashboard/`

## Key Files
| File | Purpose |
|---|---|
| `config.py` | All config — reads secrets from `.env` via python-dotenv |
| `pull_data.py` | Fetches data from Metabase and Google Sheets |
| `compute.py` | Reconciliation logic and variance calculations |
| `generate_dashboard.py` | Builds `index.html` from computed data |
| `run_recon.py` | Main entrypoint — runs full pipeline |
| `run_email_report.py` | Sends weekly email report |
| `send_email.py` | Email sending helpers |
| `fetch_amone_invoice.py` | AmONE-specific invoice fetching |

## Local Setup
```bash
pip install -r requirements-dev.txt   # Python 3.10 compatible
cp .env.example .env                  # fill in secrets
python3 run_recon.py                  # run full pipeline
open index.html                       # view dashboard
```

## Secrets (.env)
```
METABASE_PASSWORD=...
SLACK_WEBHOOK_URL=...
SMTP_PASSWORD=...
GOOGLE_SA_KEY_PATH=/path/to/google_sa_key.json
```
- Server `.env` is at `~/recon-dashboard/.env`
- Local SA key is at `~/Downloads/affiliates-491804-92fc4ff25d72.json`

## Server Cron Jobs
```
03:30 UTC daily  →  run_recon.py        (generates dashboard)
03:50 UTC daily  →  run_email_report.py (sends email)
```

## CI/CD
- GitHub Actions runs on every push to `main`
- Checks: Python syntax + no hardcoded secrets
- Auto-deploy (Step 4) is not yet set up — after pushing, SSH to server and run `git pull`

## Partners
moneylion, amone, kashkick, freecash, brigit, supermoney
