#!/bin/bash
# Auto-reminder creation cron script
# Creates daily reminders for all incomplete projects
# Run twice daily: 9 AM and 5 PM IST
# Add to crontab:
# 30 3 * * * /path/to/create_auto_reminders_cron.sh  # 9:00 AM IST (3:30 AM UTC)
# 30 11 * * * /path/to/create_auto_reminders_cron.sh # 5:00 PM IST (11:30 AM UTC)

# Load environment variables
cd /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore
source .env

# Get the app URL and cron secret
APP_URL="${APP_URL:-http://localhost:5000}"
CRON_SECRET="${CRON_SECRET:-vcore-cron-secret-2026-change-in-production}"

# Call the auto-create endpoint
curl -s -X GET "${APP_URL}/api/reminders/auto-create?secret=${CRON_SECRET}" \
  -H "Content-Type: application/json" \
  >> /tmp/vcore_auto_reminder.log 2>&1

# Log timestamp
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Auto-reminder creation completed" >> /tmp/vcore_auto_reminder.log
