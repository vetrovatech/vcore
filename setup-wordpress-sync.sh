#!/bin/bash

# WordPress Sync Quick Start Script
# This script sets up the WordPress sync integration

echo "🚀 WordPress Sync Quick Start"
echo "=============================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found"
    echo "Please create .env file with WordPress credentials"
    exit 1
fi

# Check if WordPress credentials are set
if ! grep -q "WORDPRESS_API_PASSWORD=" .env || grep -q "WORDPRESS_API_PASSWORD=$" .env; then
    echo "⚠️  Warning: WordPress API password not set in .env"
    echo ""
    echo "Please add the following to your .env file:"
    echo "WORDPRESS_URL=https://glassy.in"
    echo "WORDPRESS_API_USER=admin"
    echo "WORDPRESS_API_PASSWORD=xxxx xxxx xxxx xxxx"
    echo ""
    echo "Get the Application Password from:"
    echo "https://glassy.in/wp-admin/profile.php"
    exit 1
fi

echo "✓ Environment variables configured"
echo ""

# Run database migration
echo "📊 Running database migration..."
python3 migrate_add_wordpress_sync.py

if [ $? -eq 0 ]; then
    echo "✓ Database migration completed"
else
    echo "❌ Database migration failed"
    exit 1
fi

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Install the WordPress plugin from wordpress-plugin/ folder"
echo "2. Create Application Password in WordPress"
echo "3. Update .env with the Application Password"
echo "4. Access WordPress Sync at: http://localhost:8080/admin/wordpress-sync"
echo ""
echo "📖 See wordpress-plugin/README.md for detailed instructions"
