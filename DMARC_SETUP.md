# DMARC Setup Instructions for glassy.in

## What is DMARC?

DMARC (Domain-based Message Authentication, Reporting & Conformance) is an email authentication protocol that helps prevent email spoofing and phishing. AWS SES requires it for better email deliverability.

## DNS Records to Add

You need to add these DNS records to your domain registrar (where you manage glassy.in DNS):

### 1. DMARC Record (Required)

**Type**: TXT  
**Name**: `_dmarc.glassy.in` (or just `_dmarc` depending on your DNS provider)  
**Value**: `v=DMARC1; p=none; rua=mailto:dmarc@glassy.in; pct=100; adkim=r; aspf=r`

**Explanation**:
- `v=DMARC1` - DMARC version
- `p=none` - Policy (start with "none" for monitoring, later change to "quarantine" or "reject")
- `rua=mailto:dmarc@glassy.in` - Where to send aggregate reports
- `pct=100` - Apply policy to 100% of emails
- `adkim=r` - Relaxed DKIM alignment
- `aspf=r` - Relaxed SPF alignment

### 2. SPF Record (If not already set)

**Type**: TXT  
**Name**: `glassy.in` (or `@`)  
**Value**: `v=spf1 include:amazonses.com ~all`

**Note**: If you already have an SPF record, add `include:amazonses.com` to it. You can only have ONE SPF record per domain.

### 3. DKIM Records (AWS SES provides these)

Get your DKIM records from AWS SES:

```bash
# Get DKIM tokens for glassy.in
aws ses verify-domain-dkim --domain glassy.in --region ap-south-1
```

This will return 3 CNAME records. Add all 3 to your DNS:

**Type**: CNAME  
**Name**: `<token1>._domainkey.glassy.in`  
**Value**: `<token1>.dkim.amazonses.com`

(Repeat for all 3 tokens)

---

## Step-by-Step Setup

### Step 1: Get DKIM Tokens from AWS

```bash
aws ses verify-domain-dkim --domain glassy.in --region ap-south-1
```

### Step 2: Add DNS Records

Go to your DNS provider (GoDaddy, Cloudflare, Route53, etc.) and add:

1. **DMARC TXT Record**:
   - Host: `_dmarc`
   - Value: `v=DMARC1; p=none; rua=mailto:dmarc@glassy.in; pct=100; adkim=r; aspf=r`

2. **SPF TXT Record** (if not exists):
   - Host: `@`
   - Value: `v=spf1 include:amazonses.com ~all`

3. **DKIM CNAME Records** (3 records from Step 1):
   - Host: `<token>._domainkey`
   - Value: `<token>.dkim.amazonses.com`

### Step 3: Verify Domain in AWS SES

```bash
# Verify the domain
aws ses verify-domain-identity --domain glassy.in --region ap-south-1

# Check verification status
aws ses get-identity-verification-attributes --identities glassy.in --region ap-south-1
```

### Step 4: Wait for DNS Propagation

DNS changes can take 15 minutes to 48 hours to propagate. Check status:

```bash
# Check DMARC record
dig TXT _dmarc.glassy.in

# Check SPF record
dig TXT glassy.in

# Check DKIM records
dig CNAME <token>._domainkey.glassy.in
```

---

## Quick Commands

### Get Current DNS Records
```bash
# Check DMARC
dig TXT _dmarc.glassy.in +short

# Check SPF
dig TXT glassy.in +short | grep spf

# Check domain verification status
aws ses get-identity-verification-attributes --identities glassy.in --region ap-south-1
```

### Verify Email Addresses (Alternative to Domain Verification)
```bash
# Verify individual email addresses
aws ses verify-email-identity --email-address rohit.kr0714@gmail.com --region ap-south-1
aws ses verify-email-identity --email-address rohitsangall@gmail.com --region ap-south-1
```

---

## Recommended DMARC Policy Progression

1. **Start**: `p=none` (monitoring only, no action taken)
2. **After 1 week**: `p=quarantine; pct=10` (quarantine 10% of failing emails)
3. **After 2 weeks**: `p=quarantine; pct=50` (quarantine 50%)
4. **After 1 month**: `p=quarantine; pct=100` (quarantine all failing emails)
5. **After 2 months**: `p=reject; pct=100` (reject all failing emails)

---

## Testing

After setup, test email sending:

```bash
# Send test email
curl -X GET "https://vcore.glassy.in/api/reminders/check?secret=vcore-cron-secret-2026-change-in-production"
```

Check email headers for DMARC pass/fail status.

---

## Troubleshooting

### DMARC Record Not Found
- Wait 15-60 minutes for DNS propagation
- Verify record name is exactly `_dmarc.glassy.in`
- Check with: `dig TXT _dmarc.glassy.in`

### SPF Record Issues
- Only ONE SPF record allowed per domain
- If you have multiple mail providers, combine them:
  ```
  v=spf1 include:amazonses.com include:_spf.google.com ~all
  ```

### DKIM Not Verified
- Ensure all 3 CNAME records are added correctly
- Wait for DNS propagation
- Check with: `dig CNAME <token>._domainkey.glassy.in`

---

## Current Status

- ⚠️ DMARC: Not configured
- ❓ SPF: Unknown (need to check)
- ❓ DKIM: Unknown (need to verify)

**Action Required**: Add DNS records as described above.
