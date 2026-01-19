#!/bin/bash

# AWS Lambda Container Deployment Script

echo "☁️  VCore AWS Lambda Deployment"
echo "==============================="

# Configuration
AWS_REGION="ap-south-1"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_REPO_NAME="vcore-api"
IMAGE_TAG="latest"

echo ""
echo "📋 Configuration:"
echo "   AWS Region: $AWS_REGION"
echo "   AWS Account: $AWS_ACCOUNT_ID"
echo "   ECR Repo: $ECR_REPO_NAME"

# Create ECR repository if it doesn't exist
echo ""
echo "📦 Creating ECR repository..."
aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION 2>/dev/null || \
aws ecr create-repository --repository-name $ECR_REPO_NAME --region $AWS_REGION

# Login to ECR
echo ""
echo "🔐 Logging in to ECR..."
aws ecr get-login-password --region $AWS_REGION | \
docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Build Docker image for Lambda
echo ""
echo "🏗️  Building Lambda Docker image..."
docker build -t $ECR_REPO_NAME:$IMAGE_TAG -f Dockerfile .

# Tag image for ECR
echo ""
echo "🏷️  Tagging image..."
docker tag $ECR_REPO_NAME:$IMAGE_TAG \
  $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

# Push to ECR
echo ""
echo "⬆️  Pushing image to ECR..."
docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG

echo ""
echo "✅ Image pushed successfully!"
echo ""
echo "📝 Next steps:"
echo "   1. Create Lambda function with container image"
echo "   2. Set environment variables (DATABASE_URL, SECRET_KEY)"
echo "   3. Configure API Gateway"
echo "   4. Set up custom domain (vcore.glassy.in)"
echo ""
echo "🔗 Image URI:"
echo "   $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:$IMAGE_TAG"
