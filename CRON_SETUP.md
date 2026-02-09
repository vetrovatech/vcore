# Cron Job Setup for Email Reminders

## Overview
The reminder system needs a cron job to check for pending reminders every 15 minutes and send them automatically.

## Option 1: Local Cron (for testing)

### Setup
1. Make the script executable (already done):
   ```bash
   chmod +x /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore/check_reminders_cron.sh
   ```

2. Edit your crontab:
   ```bash
   crontab -e
   ```

3. Add this line to run every 15 minutes:
   ```
   */15 * * * * /Users/montygupta/My/personal/bin/azure/vetrova/github/vcore/check_reminders_cron.sh
   ```

4. Save and exit. Check cron log:
   ```bash
   tail -f /tmp/vcore_reminder_cron.log
   ```

## Option 2: AWS EventBridge (Recommended for Production)

### Setup AWS EventBridge Rule

1. **Go to AWS EventBridge Console**:
   https://console.aws.amazon.com/events/

2. **Create Rule**:
   - Name: `vcore-reminder-checker`
   - Description: `Check and send pending email reminders every 15 minutes`
   - Event bus: `default`
   - Rule type: `Schedule`

3. **Configure Schedule**:
   - Schedule pattern: `Rate-based schedule`
   - Rate expression: `15 minutes`

4. **Select Target**:
   - Target type: `AWS Lambda function`
   - Function: Select your VCore Lambda function
   - Configure input: `Constant (JSON text)`
   - JSON input:
     ```json
     {
       "httpMethod": "GET",
       "path": "/api/reminders/check",
       "headers": {
         "X-Cron-Secret": "vcore-cron-secret-2026-change-in-production"
       }
     }
     ```

5. **Create Rule**

### Verify EventBridge Setup
- Check CloudWatch Logs for your Lambda function
- Look for reminder check executions every 15 minutes
- Monitor `/aws/lambda/vcore-api` log group

## Option 3: External Cron Service (Alternative)

### Using cron-job.org or similar

1. Go to: https://cron-job.org/
2. Create account
3. Add new cron job:
   - Title: `VCore Reminder Checker`
   - URL: `https://your-lambda-url.amazonaws.com/api/reminders/check?secret=vcore-cron-secret-2026-change-in-production`
   - Schedule: Every 15 minutes
   - HTTP Method: GET
   - Headers: `X-Cron-Secret: vcore-cron-secret-2026-change-in-production`

## Testing the Cron Endpoint

### Manual Test
```bash
# Local
curl -X GET "http://localhost:5000/api/reminders/check?secret=vcore-cron-secret-2026-change-in-production"

# Production
curl -X GET "https://your-lambda-url.amazonaws.com/api/reminders/check?secret=vcore-cron-secret-2026-change-in-production"
```

### Expected Response
```json
{
  "success": true,
  "result": {
    "total": 5,
    "sent": 4,
    "failed": 1
  }
}
```

## Monitoring

### Check Logs
```bash
# Local cron log
tail -f /tmp/vcore_reminder_cron.log

# AWS CloudWatch
aws logs tail /aws/lambda/vcore-api --follow
```

### Database Check
```sql
-- See recent reminder activity
SELECT id, reminder_type, status, sent_at, error_message 
FROM reminders 
WHERE created_at > DATE_SUB(NOW(), INTERVAL 1 DAY)
ORDER BY created_at DESC;

-- Count by status
SELECT status, COUNT(*) as count 
FROM reminders 
GROUP BY status;
```

## Troubleshooting

### Cron not running
- Check crontab: `crontab -l`
- Check cron service: `sudo service cron status` (Linux)
- Check logs: `grep CRON /var/log/syslog` (Linux)

### Reminders not sending
- Check email service logs
- Verify AWS SES credentials
- Check reminder status in database
- Test email service: `python3 test_email.py`

### Authentication errors
- Verify CRON_SECRET matches in .env and cron job
- Check Lambda environment variables

## Security Notes

⚠️ **IMPORTANT**: Change the default CRON_SECRET in production!

Update in `.env`:
```bash
CRON_SECRET=your-secure-random-secret-here
```

Generate a secure secret:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```
