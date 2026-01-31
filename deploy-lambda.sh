#!/bin/bash

# Complete AWS Lambda Deployment Script for VCore
# This script handles: ECR, Lambda Function, API Gateway, and IAM roles

set -e  # Exit on any error

echo "☁️  VCore AWS Lambda Complete Deployment"
echo "=========================================="

# Configuration
AWS_REGION="ap-south-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="vcore-api"
LAMBDA_FUNCTION_NAME="vcore-api"
API_GATEWAY_NAME="vcore-api-gateway"
LAMBDA_ROLE_NAME="vcore-lambda-execution-role"
IMAGE_TAG="latest"

echo ""
echo "📋 Configuration:"
echo "   AWS Region: $AWS_REGION"
echo "   AWS Account: $AWS_ACCOUNT_ID"
echo "   ECR Repo: $ECR_REPO_NAME"
echo "   Lambda Function: $LAMBDA_FUNCTION_NAME"

# ============================================================================
# Step 1: Create IAM Role for Lambda (if not exists)
# ============================================================================
echo ""
echo "🔐 Setting up IAM Role..."

ROLE_ARN=$(aws iam get-role --role-name $LAMBDA_ROLE_NAME --query 'Role.Arn' --output text 2>/dev/null || echo "")

if [ -z "$ROLE_ARN" ]; then
    echo "   Creating Lambda execution role..."
    
    # Create trust policy
    cat > /tmp/lambda-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

    # Create role
    ROLE_ARN=$(aws iam create-role \
        --role-name $LAMBDA_ROLE_NAME \
        --assume-role-policy-document file:///tmp/lambda-trust-policy.json \
        --query 'Role.Arn' \
        --output text)
    
    # Attach basic Lambda execution policy
    aws iam attach-role-policy \
        --role-name $LAMBDA_ROLE_NAME \
        --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
    
    echo "   ✅ Role created: $ROLE_ARN"
    echo "   ⏳ Waiting 10 seconds for IAM role to propagate..."
    sleep 10
else
    echo "   ✅ Role already exists: $ROLE_ARN"
fi

# ============================================================================
# Step 2: Create ECR Repository (if not exists)
# ============================================================================
echo ""
echo "📦 Setting up ECR repository..."

aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION 2>/dev/null || \
aws ecr create-repository --repository-name $ECR_REPO_NAME --region $AWS_REGION

echo "   ✅ ECR repository ready"

# ============================================================================
# Step 3: Build and Push Docker Image
# ============================================================================
echo ""
echo "🏗️  Building Docker image..."
docker build -t $ECR_REPO_NAME:$IMAGE_TAG -f Dockerfile .

echo ""
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | \
docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

echo ""
echo "🏷️  Tagging image..."
docker tag $ECR_REPO_NAME:$IMAGE_TAG \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

echo ""
echo "⬆️  Pushing image to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

IMAGE_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG"
echo "   ✅ Image pushed: $IMAGE_URI"

# ============================================================================
# Step 4: Create or Update Lambda Function
# ============================================================================
echo ""
echo "⚡ Setting up Lambda function..."

# Read environment variables from .env
DATABASE_URL=$(grep DATABASE_URL .env | cut -d '=' -f2)
SECRET_KEY=$(grep SECRET_KEY .env | cut -d '=' -f2)
WORDPRESS_URL=$(grep WORDPRESS_URL .env | cut -d '=' -f2)
WORDPRESS_API_USER=$(grep WORDPRESS_API_USER .env | cut -d '=' -f2)
WORDPRESS_API_PASSWORD=$(grep WORDPRESS_API_PASSWORD .env | cut -d '=' -f2)
WORDPRESS_SYNC_ENABLED=$(grep WORDPRESS_SYNC_ENABLED .env | cut -d '=' -f2)

# Check if Lambda function exists
LAMBDA_EXISTS=$(aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION 2>/dev/null || echo "")

if [ -z "$LAMBDA_EXISTS" ]; then
    echo "   Creating new Lambda function..."
    aws lambda create-function \
        --function-name $LAMBDA_FUNCTION_NAME \
        --package-type Image \
        --code ImageUri=$IMAGE_URI \
        --role $ROLE_ARN \
        --timeout 120 \
        --memory-size 512 \
        --region $AWS_REGION \
        --environment "Variables={DATABASE_URL=$DATABASE_URL,SECRET_KEY=$SECRET_KEY,ENVIRONMENT=production,WORDPRESS_URL=$WORDPRESS_URL,WORDPRESS_API_USER=$WORDPRESS_API_USER,WORDPRESS_API_PASSWORD=$WORDPRESS_API_PASSWORD,WORDPRESS_SYNC_ENABLED=$WORDPRESS_SYNC_ENABLED}" \
        --description "VCore Project Tracking System"
    
    echo "   ✅ Lambda function created"
else
    echo "   Updating existing Lambda function..."
    aws lambda update-function-code \
        --function-name $LAMBDA_FUNCTION_NAME \
        --image-uri $IMAGE_URI \
        --region $AWS_REGION
    
    # Wait for update to complete
    echo "   ⏳ Waiting for function update..."
    aws lambda wait function-updated \
        --function-name $LAMBDA_FUNCTION_NAME \
        --region $AWS_REGION
    
    # Update environment variables
    aws lambda update-function-configuration \
        --function-name $LAMBDA_FUNCTION_NAME \
        --environment "Variables={DATABASE_URL=$DATABASE_URL,SECRET_KEY=$SECRET_KEY,ENVIRONMENT=production,WORDPRESS_URL=$WORDPRESS_URL,WORDPRESS_API_USER=$WORDPRESS_API_USER,WORDPRESS_API_PASSWORD=$WORDPRESS_API_PASSWORD,WORDPRESS_SYNC_ENABLED=$WORDPRESS_SYNC_ENABLED}" \
        --region $AWS_REGION
    
    echo "   ✅ Lambda function updated"
fi

# Get Lambda ARN
LAMBDA_ARN=$(aws lambda get-function --function-name $LAMBDA_FUNCTION_NAME --region $AWS_REGION --query 'Configuration.FunctionArn' --output text)

# ============================================================================
# Step 5: Create or Update API Gateway
# ============================================================================
echo ""
echo "🌐 Setting up API Gateway..."

# Check if API exists
API_ID=$(aws apigatewayv2 get-apis --region $AWS_REGION --query "Items[?Name=='$API_GATEWAY_NAME'].ApiId" --output text)

if [ -z "$API_ID" ]; then
    echo "   Creating new HTTP API..."
    API_ID=$(aws apigatewayv2 create-api \
        --name $API_GATEWAY_NAME \
        --protocol-type HTTP \
        --region $AWS_REGION \
        --query 'ApiId' \
        --output text)
    
    echo "   ✅ API created: $API_ID"
else
    echo "   ✅ API already exists: $API_ID"
fi

# Create integration
echo "   Setting up Lambda integration..."
INTEGRATION_ID=$(aws apigatewayv2 create-integration \
    --api-id $API_ID \
    --integration-type AWS_PROXY \
    --integration-uri $LAMBDA_ARN \
    --payload-format-version 2.0 \
    --region $AWS_REGION \
    --query 'IntegrationId' \
    --output text 2>/dev/null || \
    aws apigatewayv2 get-integrations --api-id $API_ID --region $AWS_REGION --query 'Items[0].IntegrationId' --output text)

# Create routes
echo "   Setting up routes..."
aws apigatewayv2 create-route \
    --api-id $API_ID \
    --route-key 'ANY /{proxy+}' \
    --target "integrations/$INTEGRATION_ID" \
    --region $AWS_REGION 2>/dev/null || echo "   Route /{proxy+} already exists"

aws apigatewayv2 create-route \
    --api-id $API_ID \
    --route-key 'ANY /' \
    --target "integrations/$INTEGRATION_ID" \
    --region $AWS_REGION 2>/dev/null || echo "   Route / already exists"

# Create or update stage
echo "   Setting up stage..."
aws apigatewayv2 create-stage \
    --api-id $API_ID \
    --stage-name '$default' \
    --auto-deploy \
    --region $AWS_REGION 2>/dev/null || \
aws apigatewayv2 update-stage \
    --api-id $API_ID \
    --stage-name '$default' \
    --auto-deploy \
    --region $AWS_REGION

# Add Lambda permission for API Gateway
echo "   Adding Lambda invoke permission..."
aws lambda add-permission \
    --function-name $LAMBDA_FUNCTION_NAME \
    --statement-id apigateway-invoke \
    --action lambda:InvokeFunction \
    --principal apigateway.amazonaws.com \
    --source-arn "arn:aws:execute-api:$AWS_REGION:$AWS_ACCOUNT_ID:$API_ID/*/*" \
    --region $AWS_REGION 2>/dev/null || echo "   Permission already exists"

# Get API endpoint
API_ENDPOINT=$(aws apigatewayv2 get-api --api-id $API_ID --region $AWS_REGION --query 'ApiEndpoint' --output text)

# ============================================================================
# Deployment Complete
# ============================================================================
echo ""
echo "✅ Deployment Complete!"
echo "======================="
echo ""
echo "🔗 API Endpoint:"
echo "   $API_ENDPOINT"
echo ""
echo "📝 Quick Test:"
echo "   curl $API_ENDPOINT/health"
echo ""
echo "🌐 Open in Browser:"
echo "   $API_ENDPOINT/login"
echo ""
echo "⚙️  Lambda Function:"
echo "   Name: $LAMBDA_FUNCTION_NAME"
echo "   ARN: $LAMBDA_ARN"
echo ""
echo "🌐 API Gateway:"
echo "   ID: $API_ID"
echo "   Endpoint: $API_ENDPOINT"
echo ""
