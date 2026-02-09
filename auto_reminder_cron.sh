#!/bin/bash
# Auto-reminder cron script - creates daily reminders for incomplete projects
# Run twice daily: 9 AM and 5 PM IST
# Add to crontab:
# 30 3 * * * /path/to/auto_reminder_cron.sh  # 9:00 AM IST (3:30 AM UTC)
# 30 11 * * * /path/to/auto_reminder_cron.sh # 5:00 PM IST (11:30 AM UTC)

cd /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore
source .env

# Create auto-reminders
python3 create_auto_reminders.py >> /tmp/vcore_auto_reminder.log 2>&1

# Log timestamp
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Auto-reminder creation completed" >> /tmp/vcore_auto_reminder.log
