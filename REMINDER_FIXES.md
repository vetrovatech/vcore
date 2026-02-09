# Reminder System - Quick Reference

## Issues Fixed

### 1. ✅ Project Filter Expanded
- **Before**: Only showed "In Progress" projects
- **After**: Shows both "New" and "In Progress" projects
- **Location**: `/reminders/new` form

### 2. ✅ Scheduler Catches Overdue Reminders  
- **Before**: Only checked next 15 minutes
- **After**: Checks past 24 hours + next 15 minutes
- **Benefit**: Won't miss reminders if cron job fails temporarily

### 3. ✅ Auto-Reminders for Incomplete Projects
- **Feature**: Automatic daily reminders for all incomplete projects
- **Frequency**: Twice daily (9 AM and 5 PM IST)
- **Script**: `create_auto_reminders.py`
- **Cron**: `auto_reminder_cron.sh`

## Setup Auto-Reminders

### Add to Crontab
```bash
# Edit crontab
crontab -e

# Add these lines:
# 9:00 AM IST (3:30 AM UTC)
30 3 * * * /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore/auto_reminder_cron.sh

# 5:00 PM IST (11:30 AM UTC)  
30 11 * * * /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore/auto_reminder_cron.sh
```

### Manual Test
```bash
cd /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore
python3 create_auto_reminders.py
```

## Trigger Reminder Check Manually

### Production
```bash
curl -X GET "https://vcore.glassy.in/api/reminders/check?secret=vcore-cron-secret-2026-change-in-production"
```

### Local
```bash
curl -X GET "http://localhost:5000/api/reminders/check?secret=vcore-cron-secret-2026-change-in-production"
```

## Check Reminder Status

```sql
-- View all reminders
SELECT id, reminder_type, project_id, user_id, 
       reminder_datetime, status, sent_at, error_message 
FROM reminders 
ORDER BY created_at DESC;

-- Count by status
SELECT status, COUNT(*) as count 
FROM reminders 
GROUP BY status;
```

## Troubleshooting

### Reminder Not Sending
1. Check reminder status in database
2. Manually trigger cron endpoint
3. Check CloudWatch logs for Lambda errors
4. Verify AWS SES sender email is verified
5. Check user email is verified (if in sandbox mode)

### Auto-Reminders Not Creating
1. Check cron job is running: `crontab -l`
2. Check log file: `tail -f /tmp/vcore_auto_reminder.log`
3. Run manually: `python3 create_auto_reminders.py`
4. Verify projects exist with status 'New', 'In Progress', or 'On Hold'

### Email Not Received
1. Check spam folder
2. Verify email address in user profile
3. Check AWS SES sending limits
4. View CloudWatch logs for delivery status
