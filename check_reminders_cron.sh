#!/bin/bash
# Cron job script to check and send pending reminders
# Add to crontab: */15 * * * * /path/to/check_reminders_cron.sh

# Load environment variables
cd /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore
source .env

# Get the app URL and cron secret
APP_URL="${APP_URL:-http://localhost:5000}"
CRON_SECRET="${CRON_SECRET:-vcore-cron-secret-2026-change-in-production}"

# Call the reminder check endpoint
curl -s -X GET "${APP_URL}/api/reminders/check?secret=${CRON_SECRET}" \
  -H "Content-Type: application/json" \
  >> /tmp/vcore_reminder_cron.log 2>&1

# Log timestamp
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Reminder check completed" >> /tmp/vcore_reminder_cron.log
