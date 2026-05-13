# Affiliates Recon Dashboard

## Project Overview
Python-based reconciliation dashboard for affiliate partners. Pulls data from Metabase + Google Sheets, computes variances, generates a static HTML dashboard, and emails a daily report.

## Repo
- GitHub: https://github.com/rushit-bm-ai/affiliates-product
- Server: `ssh ubuntu@10.0.204.191` (VPN required)
- Server path: `~/recon-dashboard/`

## Directory Structure (by tab)

```
affiliates-product/
├── config.py               # All shared config (paths, credentials, partner config)
├── run_recon.py            # Root entrypoint → delegates to recon/run.py (cron-safe)
├── run_email_report.py     # Root entrypoint → delegates to recon/run_email.py (cron-safe)
├── run_all.py              # Run all pipelines (recon + experiments)
├── refresh_server.py       # Root entrypoint → delegates to dashboard/refresh_server.py
│
├── recon/                  # Recon tab: Reports↔Invoice, Invoice↔Cash
│   ├── queries/            # SQL files for Metabase pulls
│   │   └── reports_by_payout_cycle.sql
│   ├── pull.py             # Fetches data from Metabase (all queries)
│   ├── compute.py          # Recon logic — validation, l1 and l3 reconciliation
│   ├── email.py            # Email HTML builder + SMTP sender
│   ├── run.py              # Recon pipeline orchestrator (pull → compute → render)
│   └── run_email.py        # Email report sender
│
├── monitor/                # Monitor tab: payout trends, enrolls
│   ├── queries/            # SQL files for monitor pulls
│   │   ├── daily_by_partner.sql
│   │   ├── weekly_by_partner.sql
│   │   └── monthly_by_partner.sql
│   └── compute.py          # Monitor compute — payout KPIs, enrolls, app completion
│
├── experiments/            # Experiments tab: C1B impact dashboard
│   └── run.py              # C1B dashboard — fetches from Metabase + renders HTML
│
├── dashboard/              # Dashboard shell and refresh server
│   ├── render.py           # Builds index.html (Recon + Monitor + Experiments tabs)
│   └── refresh_server.py   # HTTP API for refresh button (port 8765)
│
├── cron/                   # Cron shell scripts (recon only)
│   ├── recon_pipeline.sh   # 03:30 UTC — runs recon/run.py
│   └── recon_email.sh      # 03:50 UTC — runs recon/run_email.py
│
├── computed/               # Generated JSON (l1, l3, monitor, enroll data)
├── input_data/             # Pulled CSVs from Metabase
└── logs/                   # health_log.json, email_log.json, cron.log
```

## Key Files
| File | Purpose |
|---|---|
| `config.py` | All config — reads secrets from `.env` via python-dotenv |
| `recon/pull.py` | Fetches CSV data from Metabase for all tabs |
| `recon/compute.py` | Reports vs Invoice + Invoice vs Cash reconciliation |
| `recon/email.py` | Email HTML builder (formatters, tables, SMTP send) |
| `recon/run.py` | Full recon pipeline: pull → compute → dashboard |
| `recon/run_email.py` | Loads computed data and sends daily email |
| `monitor/compute.py` | Monitor KPIs, enrolls, app completion (Metabase queries) |
| `dashboard/render.py` | Builds `index.html` from all computed JSON data |
| `dashboard/refresh_server.py` | HTTP refresh API for the dashboard refresh button |
| `experiments/run.py` | C1B experiment impact dashboard (self-contained) |

## Local Setup
```bash
pip install -r requirements-dev.txt   # Python 3.10 compatible
cp .env.example .env                  # fill in secrets
python3 run_recon.py                  # run full recon pipeline
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
30 3 * * *  cd ~/recon-dashboard && python3 recon/run.py >> logs/cron.log 2>&1
50 3 * * *  cd ~/recon-dashboard && python3 recon/run_email.py >> logs/cron.log 2>&1
```
(Or equivalently via cron/ shell scripts)

## CI/CD
- GitHub Actions runs on every push to `main`
- Checks: Python syntax + no hardcoded secrets
- Auto-deploy (Step 4) is not yet set up — after pushing, SSH to server and run `git pull`

## Partners
moneylion, amone, kashkick, freecash, brigit, supermoney
