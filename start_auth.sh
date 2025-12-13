#!/bin/bash
# Quick Start Script for Vigil Self-Hosted

set -e

echo "🛡️  Vigil Self-Hosted Setup"
echo "=" 60

# Step 1: Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Step 2: Initialize database
echo "🗄️  Initializing database..."
python3 << 'EOF'
from auth_manager import AuthManager
auth = AuthManager()
print("✅ Database initialized!")
EOF

# Step 3: Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  Creating .env file..."
    cat > .env << 'ENVFILE'
# JWT Secret (CHANGE THIS!)
JWT_SECRET=$(openssl rand -hex 32)

# Stripe Keys (ADD YOUR KEYS)
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_secret

# Database
AUTH_DB_PATH=vigil_users.db

# Server
PORT=8080
HOST=0.0.0.0
ENVFILE
    
    echo "⚠️  IMPORTANT: Edit .env file and add your Stripe keys!"
    echo "   1. Get keys from https://dashboard.stripe.com/apikeys"
    echo "   2. Update STRIPE_SECRET_KEY"
    echo "   3. Setup webhook and update STRIPE_WEBHOOK_SECRET"
fi

# Step 4: Start server
echo ""
echo "🚀 Starting Vigil Auth Server..."
echo "=" * 60
echo "Landing Page: http://localhost:8080/"
echo "Pricing Page: http://localhost:8080/pricing"
echo "Dashboard:    http://localhost:8080/dashboard"
echo "=" * 60
echo ""

python auth_server.py
