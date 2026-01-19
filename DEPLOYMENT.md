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

Environment variables (set in Lambda):
- `DATABASE_URL`: MySQL connection to RDS
- `SECRET_KEY`: Flask secret key
- `ENVIRONMENT`: production

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
