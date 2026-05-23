# VCore AWS Lambda Deployment - Quick Reference

## 🌐 Live Application

**Production URL**: https://vcore.glassy.in

- Health Check: https://vcore.glassy.in/health
- Login: https://vcore.glassy.in/login

## 🔑 Default Credentials

After running `seed_data.py`:
- **Admin**: username: `admin`, password: `admin123`
- **Manager**: username: `manager`, password: `manager123`
- **Promotor**: username: `promotor1`, password: `promotor123`

⚠️ **Change these passwords in production!**

## 🚀 Redeployment

To update the Lambda function:

```bash
# Quick redeploy
./deploy-lambda.sh

# Or manual steps:
docker build --platform linux/amd64 -t vcore-api:latest .
docker tag vcore-api:latest 112036182987.dkr.ecr.ap-south-1.amazonaws.com/vcore-api:latest
docker push 112036182987.dkr.ecr.ap-south-1.amazonaws.com/vcore-api:latest

aws lambda update-function-code \
  --function-name vcore-api \
  --image-uri 112036182987.dkr.ecr.ap-south-1.amazonaws.com/vcore-api:latest \
  --region ap-south-1
```

## 📊 AWS Resources

| Resource | Name/ID | Region |
|----------|---------|--------|
| Lambda Function | `vcore-api` | ap-south-1 |
| API Gateway | `0xhvubq63e` | ap-south-1 |
| Custom Domain | `vcore.glassy.in` | ap-south-1 |
| ECR Repository | `vcore-api` | ap-south-1 |
| ACM Certificate (Regional) | `f1d1ac43-3678-4af4-9c7e-0514f657b2b5` | ap-south-1 |
| ACM Certificate (Global) | `e7549f26-37f5-4043-a4cf-37476ead1470` | us-east-1 |

## 🔧 Configuration

Environment variables (set in Lambda — `deploy-lambda.sh` reads them from local `.env` and pushes them to Lambda's `--environment Variables`):
- `DATABASE_URL`: PostgreSQL connection to Lightsail
- `SECRET_KEY`: Flask secret key
- `ENVIRONMENT`: production
- `WORDPRESS_URL`, `WORDPRESS_API_USER`, `WORDPRESS_API_PASSWORD`, `WORDPRESS_SYNC_ENABLED`
- `CRON_SECRET`, `APP_URL`, `SES_SENDER_EMAIL`, `AWS_BUCKET_NAME`
- `VCORE_INGEST_SECRET`: HMAC secret shared with glassyplatform — see Bathqube webhook section below
- `BATHQUBE_FROM_EMAIL`: sender for Bathqube quotation stage emails (e.g. `Bathqube <support@bathqube.com>`)
- `FB_PAGE_ACCESS_TOKEN`, `FB_PAGE_ID`: needed by `/leads/facebook/sync` (Sync Facebook button) and the cron endpoint at `/api/leads/facebook-sync`. Without these, the sync returns `500 FB_PAGE_ACCESS_TOKEN not configured`. **Note:** there is currently NO EventBridge rule invoking this — the only way FB leads enter vcore is via the manual "Sync Facebook" button on `/leads`. If a scheduler is ever wanted, add an EventBridge rule modelled on `vcore-reminder-checker`.

**When adding a new Lambda env var: update `deploy-lambda.sh` in TWO places** —
the `grep ... .env` block (around line 115) AND both `--environment Variables={…}`
strings (in the `create-function` and `update-function-configuration` calls).
Forgetting the second part means the var is read from `.env` but never reaches Lambda.

## 🪝 Bathqube webhook integration (added 2026-05-23)

Live glassyplatform (bathqube.com) POSTs each new bathspace-quote submission
to `https://vcore.glassy.in/api/bathqube/quotes/ingest`, HMAC-signed with
`VCORE_INGEST_SECRET`. The mirrored quote appears at `/quotes/bathqube` in vcore.

**For the integration to work, the SAME secret must exist on BOTH sides:**

| Side | Where | Variable |
|---|---|---|
| vcore | Lambda env vars (via `deploy-lambda.sh`) | `VCORE_INGEST_SECRET` |
| glassyplatform | `/home/ubuntu/glassy.env` on Lightsail box | `VCORE_INGEST_URL` + `VCORE_INGEST_SECRET` |

Verify the wiring is alive without submitting a real quote:
```bash
# Should return: HTTP 401 {"error":"invalid signature"}
curl -X POST -H 'X-Bathqube-Signature: sha256=bogus' \
  -d '{}' https://vcore.glassy.in/api/bathqube/quotes/ingest
```
401 (not 404) means the route exists and the secret is being checked. 404 means
the Lambda image is from before the bathqube feature was deployed.

## ⚠️ Deployment gotchas (hard-won during 2026-05-23 deploy)

### AWS profile must be `ansar`, not the default
The default profile (`cdc-app-uploader`) lacks `lambda:GetFunction` and
related permissions. `deploy-lambda.sh` doesn't set a profile, so either:
```bash
AWS_PROFILE=ansar ./deploy-lambda.sh
# or
export AWS_PROFILE=ansar && ./deploy-lambda.sh
```

### Docker BuildKit produces OCI manifests Lambda can't read
Plain `docker build` on modern Docker emits an OCI image manifest, which
Lambda's container runtime rejects with: *"The image manifest, config or
layer media type for the source image is not supported."*

The script now uses `docker buildx build --provenance=false --sbom=false
--output type=docker` to force the Docker v2 manifest format. **Do not
revert this back to plain `docker build`** — the push will succeed but the
`UpdateFunctionCode` call will fail.

### Rollback path is via ECR image tags, not Lambda Versions
Lambda only retains `$LATEST` plus rarely-pinned numbered versions. The
durable rollback target is an **ECR image tag**. Before any risky deploy:
```bash
# Tag the currently-running image so we can swap back to it
CURRENT_DIGEST=$(aws lambda get-function --function-name vcore-api \
  --region ap-south-1 --query 'Code.ImageUri' --output text | cut -d@ -f2)
# (if Lambda points at :latest, look up the digest of :latest in ECR first)
MANIFEST=$(aws ecr batch-get-image --repository-name vcore-api \
  --region ap-south-1 --image-ids imageDigest=$CURRENT_DIGEST \
  --query 'images[0].imageManifest' --output text)
aws ecr put-image --repository-name vcore-api --region ap-south-1 \
  --image-tag pre-<feature-name>-YYYYMMDD --image-manifest "$MANIFEST"
```
To roll back: `aws lambda update-function-code --function-name vcore-api
--image-uri 112036182987.dkr.ecr.ap-south-1.amazonaws.com/vcore-api:pre-<tag>
--region ap-south-1`.

## 📝 DNS Records (GoDaddy)

For `glassy.in` domain:

1. **Certificate Validation**:
   - Type: CNAME
   - Name: `_33da199f9f9b4a9c77cbab91b279ac2e.vcore`
   - Value: `_c5dc42c1ebd4c3cecf585bf3ae6b1667.jkddzztszm.acm-validations.aws.`

2. **Domain Mapping**:
   - Type: CNAME
   - Name: `vcore`
   - Value: `d-un4alk9b4b.execute-api.ap-south-1.amazonaws.com`

## 🐛 Troubleshooting

**Check Lambda logs**:
```bash
aws logs tail /aws/lambda/vcore-api --follow --region ap-south-1
```

**Test health endpoint**:
```bash
curl https://vcore.glassy.in/health
```

**Verify DNS**:
```bash
dig vcore.glassy.in CNAME +short
```

## 📚 Documentation

- [Full Walkthrough](walkthrough.md) - Complete deployment details
- [Custom Domain Setup](CUSTOM_DOMAIN_SETUP.md) - DNS configuration guide
- [Implementation Plan](implementation_plan.md) - Technical architecture
