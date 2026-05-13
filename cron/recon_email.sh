#!/bin/bash
# Recon email report — runs daily at 03:50 UTC (after pipeline)
# Cron entry: 50 3 * * * /bin/bash ~/recon-dashboard/cron/recon_email.sh >> ~/recon-dashboard/logs/cron.log 2>&1

set -e
cd "$(dirname "$0")/.."
python3 recon/run_email.py
