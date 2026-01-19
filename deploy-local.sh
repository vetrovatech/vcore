#!/bin/bash

# VCore Docker Deployment Script

echo "🐳 VCore Docker Deployment"
echo "=========================="

# Build the Docker image
echo ""
echo "📦 Building Docker image..."
docker-compose build

# Start the container
echo ""
echo "🚀 Starting VCore application..."
docker-compose up -d

# Wait for application to be ready
echo ""
echo "⏳ Waiting for application to start..."
sleep 5

# Check health
echo ""
echo "🏥 Checking application health..."
curl -f http://localhost:8080/health || echo "❌ Health check failed"

echo ""
echo "✅ VCore is running at http://localhost:8080"
echo ""
echo "📝 Login credentials:"
echo "   Admin:    admin / admin123"
echo "   Manager:  manager / manager123"
echo "   Promotor: promotor1 / promotor123"
echo ""
echo "📊 View logs: docker-compose logs -f"
echo "🛑 Stop app:  docker-compose down"
