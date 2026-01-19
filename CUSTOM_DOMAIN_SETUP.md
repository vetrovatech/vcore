# Custom Domain Setup Instructions for GoDaddy

## 🎯 Objective
Configure `vcore.glassy.in` to point to your AWS Lambda application.

---

## Step 1: Validate SSL Certificate in GoDaddy

You need to add a CNAME record in GoDaddy to validate the SSL certificate.

### DNS Record to Add in GoDaddy:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| **CNAME** | `_33da199f9f9b4a9c77cbab91b279ac2e.vcore` | `_c5dc42c1ebd4c3cecf585bf3ae6b1667.jkddzztszm.acm-validations.aws.` | 600 |

### Instructions:

1. **Log in to GoDaddy** → Go to your domain management
2. **Select `glassy.in`** domain
3. **Go to DNS Management**
4. **Add a new CNAME record**:
   - **Name**: `_33da199f9f9b4a9c77cbab91b279ac2e.vcore`
   - **Value**: `_c5dc42c1ebd4c3cecf585bf3ae6b1667.jkddzztszm.acm-validations.aws.`
   - **TTL**: 600 seconds (or 1 hour)
5. **Save** the record

> [!IMPORTANT]
> **Wait 5-10 minutes** for DNS propagation. AWS will automatically validate the certificate once the DNS record is detected.

---

## Step 2: Point vcore.glassy.in to API Gateway

Now add the final CNAME record to point your domain to the API Gateway.

### DNS Record to Add in GoDaddy:

| Type | Name | Value | TTL |
|------|------|-------|-----|
| **CNAME** | `vcore` | `d-un4alk9b4b.execute-api.ap-south-1.amazonaws.com` | 600 |

### Instructions:

1. **Log in to GoDaddy** → Go to DNS Management for `glassy.in`
2. **Add a new CNAME record**:
   - **Name**: `vcore`
   - **Value**: `d-un4alk9b4b.execute-api.ap-south-1.amazonaws.com`
   - **TTL**: 600 seconds (or 1 hour)
3. **Save** the record

> [!IMPORTANT]
> **Wait 5-10 minutes** for DNS propagation before testing.

---

## Verification

After the DNS record is added and propagated (5-10 minutes):

```bash
# Test health endpoint
curl https://vcore.glassy.in/health

# Test login page
curl https://vcore.glassy.in/login
```

You should see the same responses as the API Gateway URL!

---

## Current Status

✅ **ACM Certificates Created**:
- us-east-1: `arn:aws:acm:us-east-1:112036182987:certificate/e7549f26-37f5-4043-a4cf-37476ead1470`
- ap-south-1: `arn:aws:acm:ap-south-1:112036182987:certificate/f1d1ac43-3678-4af4-9c7e-0514f657b2b5`

✅ **API Gateway Custom Domain**: `vcore.glassy.in` → `d-un4alk9b4b.execute-api.ap-south-1.amazonaws.com`

✅ **API Mapping**: Connected to Lambda function via API Gateway `0xhvubq63e`

⏳ **Waiting for**: Final CNAME record to be added in GoDaddy

📝 **Next**: Add the CNAME record above, wait 5-10 minutes, then test `https://vcore.glassy.in/health`
