#!/bin/bash
# Recon pipeline — runs daily at 03:30 UTC
# Cron entry: 30 3 * * * /bin/bash ~/recon-dashboard/cron/recon_pipeline.sh >> ~/recon-dashboard/logs/cron.log 2>&1

set -e
cd "$(dirname "$0")/.."
python3 recon/run.py
